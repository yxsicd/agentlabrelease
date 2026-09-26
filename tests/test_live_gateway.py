import http.server
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
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
    def test_container_launcher_gets_docker_control_but_not_gateway_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(
            os.environ,
            {
                'AGENTLAB_LM_GATEWAY_KEY': 'synthetic-external-key',
                'AGENTLAB_PARTICIPANT_RUNTIME_CONFIG': str(Path(tmp) / 'runtime.json'),
                'AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT': str(Path(tmp) / 'receipts'),
                'DOCKER_CONFIG': str(Path(tmp) / 'docker-config'),
                'DOCKER_CONTEXT': 'fixture-context',
            },
            clear=False,
            ):
                evidence = root / 'evidence'
                evidence.mkdir()
                captured = {}
                participant = MODULE.Participant(
                    evidence, root / 'state', '/bin/true', 'http://127.0.0.1:1', 'test-model'
                )
                try:
                    models = json.loads((root / 'state/models.json').read_text())
                    provider = models['providers']['agentlab-ci']
                    self.assertEqual(provider['baseUrl'], 'http://agentlab-gateway:18765/v1')
                    self.assertNotEqual(provider['apiKey'], 'synthetic-external-key')
                    probe_url = (
                        f'http://127.0.0.1:{participant.server.server_port}'
                        '/__agentlab_runtime_probe'
                    )
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(probe_url, timeout=5)
                    self.assertEqual(denied.exception.code, 401)
                    denied.exception.close()
                    request = urllib.request.Request(
                        probe_url,
                        headers={'Authorization': 'Bearer ' + provider['apiKey']},
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, 204)
                    denied_path = urllib.request.Request(
                        f'http://127.0.0.1:{participant.server.server_port}/v1/other',
                        data=b'{}',
                        headers={'Authorization': 'Bearer ' + provider['apiKey']},
                    )
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        urllib.request.urlopen(denied_path, timeout=5)
                    self.assertEqual(rejected.exception.code, 404)
                    rejected.exception.close()

                    def capture(command, project, environment, label, lifecycle):
                        captured.update(command=command, environment=environment)

                    with patch.object(participant, '_run_turn', side_effect=capture):
                        participant.turn('sandbox-stage', root, prompt='fixture prompt')
                finally:
                    participant.close()
                environment = captured['environment']
                self.assertEqual(environment['DOCKER_CONTEXT'], 'fixture-context')
                self.assertEqual(environment['DOCKER_CONFIG'], str(root / 'docker-config'))
                self.assertEqual(
                    int(environment['AGENTLAB_OPERATOR_GATEWAY_PORT']),
                    participant.server.server_port,
                )
                self.assertNotIn('AGENTLAB_LM_GATEWAY_KEY', environment)
                session = captured['command'][captured['command'].index('--session') + 1]
                self.assertEqual(Path(session), root / 'state/pi-session.jsonl')

    def test_failed_participant_retains_actual_source_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                {'AGENTLAB_LM_GATEWAY_KEY': 'synthetic-external-key'}):
            root=Path(tmp);evidence=root/'evidence';evidence.mkdir()
            project=root/'project';source=project/'entry/src/main/ets/pages/Index.ets'
            source.parent.mkdir(parents=True);source.write_bytes(b'partially edited source\r\n')
            participant=MODULE.Participant(evidence,root/'state',shutil.which('false'),'http://127.0.0.1:1','test-model')
            try:
                with self.assertRaisesRegex(RuntimeError,'Pi exited 1'):
                    participant.turn('failed',project,'not reached')
            finally:
                participant.close()
            self.assertEqual((evidence/'failed-actual-source.ets').read_bytes(),source.read_bytes())
            lifecycle=json.loads((evidence/'failed-lifecycle.json').read_text())
            self.assertEqual(lifecycle['exitCode'],1)
            self.assertFalse(lifecycle['timedOut'])
            self.assertTrue(lifecycle['sourcePresent'])
            self.assertGreaterEqual(lifecycle['durationMs'],0)
            self.assertLessEqual(lifecycle['startedAt'],lifecycle['endedAt'])

    def test_python_virtualenv_executable_retains_its_runtime_prefix(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                {'AGENTLAB_LM_GATEWAY_KEY':'synthetic-external-key'}):
            root=Path(tmp)
            subprocess.run([sys.executable,'-m','venv','--without-pip',str(root/'runtime')],check=True)
            evidence=root/'evidence';evidence.mkdir()
            binary=root/'runtime/bin/python'
            participant=MODULE.Participant(evidence,root/'state',binary,'http://127.0.0.1:1',
                                           'test-model')
            try:
                prefix=subprocess.check_output([participant.binary,'-c','import sys; print(sys.prefix)']).decode().strip()
                self.assertEqual(Path(prefix).resolve(),(root/'runtime').resolve())
            finally:participant.close()

    def test_missing_mini_runtime_is_harness_failure_before_proxy_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,
                {'AGENTLAB_LM_GATEWAY_KEY':'synthetic-key'}):
            root=Path(tmp);evidence=root/'evidence';evidence.mkdir()
            with patch.object(MODULE.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'missing test runtime')):
                with self.assertRaisesRegex(RuntimeError,'preflight failed before dispatch'):
                    MODULE.Participant(evidence,root/'state',sys.executable,'http://127.0.0.1:1',
                                       'test-model',implementation='mini-swe-agent')
            self.assertEqual(json.loads((evidence/'runtime-probe.json').read_text())['exitCode'],1)
            self.assertFalse((evidence/'gateway').exists())

    def test_native_banner_is_retained_without_vetoing_completed_tools(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,
                {'AGENTLAB_LM_GATEWAY_KEY':'synthetic-key'}):
            root=Path(tmp);evidence=root/'evidence';evidence.mkdir()
            participant=MODULE.Participant(evidence,root/'state',sys.executable,'http://127.0.0.1:1','test-model')
            try:
                participant._run_turn([sys.executable,'-c',
                    "import json; print('native startup diagnostic'); print(json.dumps(dict(type='tool_execution_end')))"],
                    root,{'PATH':os.environ['PATH']},'banner',{})
            finally:participant.close()
            self.assertIn(b'native startup diagnostic',(evidence/'banner-events.jsonl').read_bytes())
            errors=json.loads((evidence/'banner-native-parse-errors.json').read_text())
            self.assertEqual(len(errors),1)

    def test_native_final_assistant_message_is_returned_and_digest_bound(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"AGENTLAB_LM_GATEWAY_KEY": "synthetic-key"}
        ):
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            participant = MODULE.Participant(
                evidence,
                root / "state",
                sys.executable,
                "http://127.0.0.1:1",
                "test-model",
            )
            lifecycle = {}
            try:
                result = participant._run_turn(
                    [
                        sys.executable,
                        "-c",
                        "import json; "
                        "print(json.dumps({'type':'tool_execution_end'})); "
                        "print(json.dumps({'type':'message_end','message':{'role':'assistant','content':'native final'}}))",
                    ],
                    root,
                    {"PATH": os.environ["PATH"]},
                    "final",
                    lifecycle,
                )
            finally:
                participant.close()
            self.assertEqual(result["content"], "native final")
            final_path = evidence / "final-final-assistant-message.json"
            self.assertTrue(final_path.is_file())
            self.assertEqual(
                lifecycle["finalAssistantMessageSha256"],
                hashlib.sha256(final_path.read_bytes()).hexdigest(),
            )
            self.assertTrue(lifecycle["finalAssistantTextPresent"])

    def test_disconnect_still_captures_complete_upstream(self):
        release=threading.Event()
        body=b'data: {"delta":"first"}\n'+b'data: {"delta":"remaining"}\n'*4000
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.end_headers()
                self.wfile.write(body[:24]);self.wfile.flush()
                release.wait(5)
                self.wfile.write(body[24:])
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                    {'AGENTLAB_LM_GATEWAY_KEY':'synthetic-external-key'}):
                root=Path(tmp);evidence=root/'evidence';evidence.mkdir()
                participant=MODULE.Participant(evidence,root/'state','/bin/true',
                    f'http://127.0.0.1:{server.server_port}','test-model')
                try:
                    client=socket.create_connection(('127.0.0.1',participant.server.server_port),timeout=5)
                    client.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}')
                    client.recv(1024)
                    client.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
                    client.close();release.set()
                finally:
                    release.set();participant.close()
                self.assertEqual((evidence/'gateway/0001.response').read_bytes(),body)
                receipt=json.loads((evidence/'gateway/0001.status.json').read_text())
                self.assertTrue(receipt['clientDisconnected'])
                self.assertTrue(receipt['upstreamEof'])
                self.assertEqual(receipt['responseBytes'],len(body))
        finally:
            release.set();server.shutdown();server.server_close();thread.join()

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
                self.assertEqual(json.loads(received['body']), {
                    **json.loads(body), 'providerId': 'glm', 'model': 'test-model'
                })
                self.assertEqual((evidence / 'gateway/0001.request.json').read_bytes(), body)
                self.assertEqual((evidence / 'gateway/0001.response').read_bytes(), response)
                receipt=json.loads((evidence/'gateway/0001.status.json').read_text())
                self.assertEqual(receipt['responseBytes'],len(response))
                self.assertTrue(receipt['upstreamEof'])
                self.assertEqual(receipt['outcome'],'completed')
                self.assertGreaterEqual(receipt['durationMs'],0)
                for path in root.rglob('*'):
                    if path.is_file():
                        self.assertNotIn(b'synthetic-external-key', path.read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
