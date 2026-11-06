import http.server
import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('budget_participant', Path(__file__).resolve().parents[1] / 'examples/real-code-agent/participant.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GatewayBudgetTest(unittest.TestCase):
    def exercise(self, response, expected_reason, expected_used):
        calls = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                calls.append(1)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

        upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'AGENTLAB_LM_GATEWAY_KEY': 'fixture'}):
                root = Path(tmp)
                evidence = root / 'evidence'
                evidence.mkdir()
                participant = module.Participant(evidence, root / 'state', '/bin/true',
                    f'http://127.0.0.1:{upstream.server_port}', 'fixture', token_budget=10)
                url = f'http://127.0.0.1:{participant.server.server_port}/v1/chat/completions'
                def request():
                    return urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'})
                try:
                    with urllib.request.urlopen(request(), timeout=5) as first:
                        self.assertEqual(first.status, 200)
                        first.read()
                    with self.assertRaises(urllib.error.HTTPError) as second:
                        urllib.request.urlopen(request(), timeout=5)
                    self.assertEqual(second.exception.code, 429)
                    second.exception.close()
                finally:
                    participant.close()
                decision = json.loads((evidence / 'token-budget-decision.json').read_text())
                self.assertEqual(decision['reason'], expected_reason)
                self.assertEqual(decision['used'], expected_used)
                self.assertEqual(len(calls), 1)
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join()

    def test_budget_prevents_next_upstream_call_after_overshoot(self):
        self.exercise({'usage': {'prompt_tokens': 7, 'completion_tokens': 5}}, 'budget_exhausted', 12)

    def test_missing_usage_prevents_next_upstream_call(self):
        self.exercise({'choices': []}, 'usage_unknown', 0)

    def test_concurrent_requests_do_not_share_the_same_remaining_budget(self):
        calls = []
        entered = threading.Event()
        release = threading.Event()
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                calls.append(1)
                entered.set()
                release.wait(3)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"usage":{"prompt_tokens":8,"completion_tokens":2}}')
        upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        server_thread = threading.Thread(target=upstream.serve_forever)
        server_thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'AGENTLAB_LM_GATEWAY_KEY': 'fixture'}):
                root = Path(tmp)
                evidence = root / 'evidence'
                evidence.mkdir()
                participant = module.Participant(evidence, root / 'state', '/bin/true',
                    f'http://127.0.0.1:{upstream.server_port}', 'fixture', token_budget=10)
                url = f'http://127.0.0.1:{participant.server.server_port}/v1/chat/completions'
                results = []
                def call():
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url, data=b'{}'), timeout=5) as response:
                            response.read()
                            results.append(response.status)
                    except urllib.error.HTTPError as error:
                        results.append(error.code)
                        error.close()
                first = threading.Thread(target=call)
                second = threading.Thread(target=call)
                try:
                    first.start()
                    self.assertTrue(entered.wait(3))
                    second.start()
                    release.set()
                    first.join(5)
                    second.join(5)
                finally:
                    release.set()
                    participant.close()
                self.assertEqual(sorted(results), [200, 429])
                self.assertEqual(len(calls), 1)
        finally:
            release.set()
            upstream.shutdown()
            upstream.server_close()
            server_thread.join()

    def test_separate_attempts_have_separate_budgets(self):
        calls = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                calls.append(1)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"usage":{"prompt_tokens":7,"completion_tokens":3}}')
        upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'AGENTLAB_LM_GATEWAY_KEY': 'fixture'}):
                root = Path(tmp)
                participants = []
                try:
                    for name in ('a', 'b'):
                        evidence = root / name
                        evidence.mkdir()
                        participants.append(module.Participant(evidence, root / ('state-' + name), '/bin/true',
                            f'http://127.0.0.1:{upstream.server_port}', 'fixture', token_budget=10))
                    for participant in participants:
                        url = f'http://127.0.0.1:{participant.server.server_port}/v1/chat/completions'
                        with urllib.request.urlopen(urllib.request.Request(url, data=b'{}'), timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            response.read()
                    self.assertEqual([p.token_budget_used for p in participants], [10, 10])
                    self.assertEqual(len(calls), 2)
                finally:
                    for participant in participants:
                        participant.close()
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
