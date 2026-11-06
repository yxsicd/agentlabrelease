import http.server
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture_only', ROOT / 'examples/real-code-agent/participant.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureOnlyTest(unittest.TestCase):
    def test_responses_authentication_capture_and_budget(self):
        calls = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                calls.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body = json.dumps({'id': 'r1', 'status': 'completed', 'usage': {
                    'input_tokens': 7, 'output_tokens': 5,
                    'input_tokens_details': {'cached_tokens': 3},
                    'output_tokens_details': {'reasoning_tokens': 2}}}).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'AGENTLAB_LM_GATEWAY_KEY': 'upstream-secret'}, clear=True):
                root = Path(tmp); evidence = root / 'evidence'; evidence.mkdir()
                p = module.Participant(evidence, root / 'state', '/bin/true',
                    f'http://127.0.0.1:{server.server_port}', 'model', route='fixture',
                    implementation='capture-only', api='openai-responses', token_budget=10)
                base = f'http://127.0.0.1:{p.server.server_port}'
                def req(path='/v1/responses', token=None):
                    headers = {'Content-Type': 'application/json'}
                    if token: headers['Authorization'] = 'Bearer ' + token
                    return urllib.request.Request(base + path, data=b'{"input":"hello"}', headers=headers)
                try:
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(req(), timeout=5)
                    self.assertEqual(denied.exception.code, 401); denied.exception.close()
                    with self.assertRaises(urllib.error.HTTPError) as wrong_path:
                        urllib.request.urlopen(req('/v1/chat/completions', p.local_proxy_token), timeout=5)
                    self.assertEqual(wrong_path.exception.code, 404); wrong_path.exception.close()
                    with urllib.request.urlopen(req(token=p.local_proxy_token), timeout=5) as response:
                        self.assertEqual(response.status, 200); response.read()
                    with self.assertRaises(urllib.error.HTTPError) as exhausted:
                        urllib.request.urlopen(req(token=p.local_proxy_token), timeout=5)
                    self.assertEqual(exhausted.exception.code, 429); exhausted.exception.close()
                    with self.assertRaisesRegex(RuntimeError, 'does not dispatch'):
                        p.turn('no-dispatch', root, prompt='test')
                finally:
                    p.close()
                self.assertEqual(len(calls), 1); self.assertEqual(calls[0][0], '/v1/responses')
                decision = json.loads((evidence / 'token-budget-decision.json').read_text())
                self.assertEqual((decision['reason'], decision['used']), ('budget_exhausted', 12))
                summary = p.token_usage.summarize(evidence / 'gateway')
                self.assertEqual(summary['totalsObserved'], {'input': 7, 'output': 5, 'cached_input': 3, 'reasoning_output': 2})
                capture = json.loads((root / 'state/capture-config.json').read_text())
                self.assertEqual(capture['reasoningPolicy'], 'unchanged')
                self.assertEqual(capture['apiKey'], p.local_proxy_token)
                self.assertNotIn('upstream-secret', (root / 'state/capture-config.json').read_text())
                self.assertIsNone(json.loads((evidence / 'participant.json').read_text())['packageName'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_requires_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'per-attempt token budget'):
                module.Participant(Path(tmp), Path(tmp) / 'state', '/bin/true', 'http://127.0.0.1:1',
                                   'model', implementation='capture-only', api='openai-responses')

    def test_rejects_container_runtime_configuration(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'AGENTLAB_LM_GATEWAY_KEY': 'fixture', 'AGENTLAB_PARTICIPANT_RUNTIME_CONFIG': '/unrelated'
        }, clear=True):
            with self.assertRaisesRegex(ValueError, 'loopback transport'):
                module.Participant(Path(tmp), Path(tmp) / 'state', '/bin/true', 'http://127.0.0.1:1',
                    'model', implementation='capture-only', api='openai-responses', token_budget=10)

    def test_responses_stream_records_nested_usage(self):
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body = (b'data: {"type":"response.completed","response":{"status":"completed",'
                        b'"usage":{"input_tokens":4,"output_tokens":3}}}\n\n')
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'AGENTLAB_LM_GATEWAY_KEY': 'fixture'}, clear=True):
                root = Path(tmp); evidence = root / 'evidence'; evidence.mkdir()
                p = module.Participant(evidence, root / 'state', '/bin/true',
                    f'http://127.0.0.1:{server.server_port}', 'model', implementation='capture-only',
                    api='openai-responses', token_budget=10)
                req = urllib.request.Request(f'http://127.0.0.1:{p.server.server_port}/v1/responses',
                    data=b'{"input":"hi","stream":true}', headers={'Authorization': 'Bearer ' + p.local_proxy_token})
                try:
                    with urllib.request.urlopen(req, timeout=5) as response: response.read()
                finally:
                    p.close()
                summary = p.token_usage.summarize(evidence / 'gateway')
                self.assertTrue(summary['inputOutputComplete'])
                self.assertEqual(summary['totalsObserved']['input'], 4)
                self.assertEqual(summary['totalsObserved']['output'], 3)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
