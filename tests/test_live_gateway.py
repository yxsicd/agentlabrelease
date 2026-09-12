import http.server
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('participant',
    Path(__file__).resolve().parents[1] / 'examples/real-code-agent/participant.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GatewayCaptureTests(unittest.TestCase):
    def test_stream_is_preserved_and_external_auth_is_not_captured(self):
        received = {}
        response = b'data: {"choices":[]}\n\ndata: [DONE]\n\n'

        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received['authorization'] = self.headers['Authorization']
                received['body'] = self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(response)

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                       {'AGENTLAB_LM_GATEWAY_KEY': 'synthetic-external-key'}):
                root = Path(directory)
                evidence = root / 'evidence'
                evidence.mkdir()
                participant = MODULE.Participant(evidence, root / 'state', '/bin/true',
                              f'http://127.0.0.1:{server.server_port}', 'test-model')
                try:
                    body = json.dumps({'model': 'test-model', 'messages': [
                        {'role': 'user', 'content': 'retain this full benchmark payload'}]}).encode()
                    request = urllib.request.Request(
                        f'http://127.0.0.1:{participant.server.server_port}/v1/chat/completions',
                        data=body, headers={'Authorization': 'Bearer harmless-local-token'})
                    with urllib.request.urlopen(request, timeout=5) as result:
                        self.assertEqual(result.read(), response)
                finally:
                    participant.close()
                self.assertEqual(received['authorization'], 'Bearer synthetic-external-key')
                self.assertEqual(received['body'], body)
                self.assertEqual((evidence / 'gateway/0001.request.json').read_bytes(), body)
                self.assertEqual((evidence / 'gateway/0001.response').read_bytes(), response)
                for path in root.rglob('*'):
                    if path.is_file():
                        self.assertNotIn(b'synthetic-external-key', path.read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
