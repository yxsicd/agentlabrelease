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


if __name__ == '__main__':
    unittest.main()
