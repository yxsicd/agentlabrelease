"""Operator-owned gateway capture and a replaceable Pi participant launcher."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Participant:
    def __init__(self, evidence, state, binary, gateway, model, route='glm'):
        self.evidence = evidence
        self.state = state
        self.binary = str(Path(binary).resolve())
        self.gateway = gateway.rstrip('/')
        self.model = model
        self.route = route
        self.key = os.environ['AGENTLAB_LM_GATEWAY_KEY']
        self.requests = 0
        self.lock = threading.Lock()
        state.mkdir()
        capture = evidence / 'gateway'
        capture.mkdir()
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                with owner.lock:
                    owner.requests += 1
                    number = owner.requests
                stem = capture / f'{number:04d}'
                raw = self.rfile.read(int(self.headers['Content-Length']))
                # Authentication is transport configuration, not test payload.
                stem.with_suffix('.request.json').write_bytes(raw)
                wire = json.loads(raw)
                wire['providerId'] = owner.route
                upstream = json.dumps(wire).encode()
                stem.with_suffix('.upstream-request.json').write_bytes(upstream)
                request = urllib.request.Request(owner.gateway + self.path, data=upstream,
                          headers={'Authorization': 'Bearer ' + owner.key,
                                   'Content-Type': 'application/json'}, method='POST')
                try:
                    response = urllib.request.build_opener(NoRedirect).open(request, timeout=180)
                except urllib.error.HTTPError as error:
                    response = error
                except Exception as error:
                    stem.with_suffix('.error.txt').write_text(str(error))
                    self.send_error(502, 'Upstream gateway connection failed')
                    return
                with response:
                    status = response.status
                    stem.with_suffix('.status.json').write_text(json.dumps({'status': status}) + '\n')
                    self.send_response(status)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.end_headers()
                    with stem.with_suffix('.response').open('wb') as output:
                        while True:
                            chunk = response.readline()
                            if not chunk:
                                break
                            output.write(chunk)
                            output.flush()
                            self.wfile.write(chunk)
                            self.wfile.flush()

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        models = {'providers': {'agentlab-ci': {
            'baseUrl': f'http://127.0.0.1:{self.server.server_port}/v1',
            'api': 'openai-completions', 'apiKey': 'agentlab-local-test-credential',
            'compat': {'supportsDeveloperRole': False, 'supportsReasoningEffort': False},
            'models': [{'id': model, 'reasoning': False, 'input': ['text'],
                        'contextWindow': 128000, 'maxTokens': 8192}]}}}
        (state / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
        (evidence / 'participant.json').write_text(json.dumps({
            'implementation': 'pi', 'packageVersion': '0.73.1', 'model': model,
            'gateway': gateway, 'providerRoute': route,
            'captureAuthority': 'operator-owned local forwarding proxy',
            'externalCredentialInParticipant': False}, indent=2) + '\n')

    def turn(self, label, project, marker, repair=False):
        prompt = (f'Work in the current Harmony ArkTS project. Read the page source and '
                  f'{"repair its invalid trailing text, then " if repair else ""}'
                  f'change its displayed Text to exactly "{marker}". Keep the Stage application '
                  'structure and valid ArkTS syntax. Use your file tools to perform the edit. '
                  'Do not install dependencies or change build configuration. '
                  'The independent operator compiles and evaluates the actual files afterwards. '
                  'Briefly describe your change when done.')
        (self.evidence / f'{label}-prompt.txt').write_text(prompt)
        command = [self.binary, '--print', '--mode', 'json', '--provider', 'agentlab-ci',
                   '--model', self.model, '--thinking', 'off', '--no-extensions',
                   '--no-skills', '--no-context-files',
                   '--session', str(self.evidence / 'pi-session.jsonl'), prompt]
        # Only the operator-side proxy has the external credential.
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if k in os.environ}
        env.update(HOME=str(self.state.parent), PI_CODING_AGENT_DIR=str(self.state))
        (self.evidence / f'{label}-command.json').write_text(json.dumps(command, indent=2) + '\n')
        lifecycle = {'label': label, 'startedAt': datetime.now(timezone.utc).isoformat(),
                     'captureAuthority': 'operator', 'exitCode': None, 'timedOut': False}
        started = time.monotonic()
        try:
            self._run_turn(command, project, env, label, lifecycle)
        finally:
            lifecycle.update(endedAt=datetime.now(timezone.utc).isoformat(),
                             durationMs=round((time.monotonic()-started)*1000))
            source = project / 'entry/src/main/ets/pages/Index.ets'
            lifecycle['sourcePresent'] = source.is_file()
            if source.is_file():
                (self.evidence / f'{label}-actual-source.ets').write_bytes(source.read_bytes())
            (self.evidence / f'{label}-lifecycle.json').write_text(json.dumps(lifecycle, indent=2)+'\n')
        source = project / 'entry/src/main/ets/pages/Index.ets'
        if marker not in source.read_text():
            raise RuntimeError(f'{label}: Agent did not change actual source')
        print(f'{label}: real Pi turn completed', flush=True)

    def _run_turn(self, command, project, env, label, lifecycle):
        with (self.evidence / f'{label}-events.jsonl').open('wb') as out, \
             (self.evidence / f'{label}-stderr.log').open('wb') as err:
            process = subprocess.Popen(command, cwd=project, env=env, stdout=out, stderr=err,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                code = process.wait(timeout=420)
            except subprocess.TimeoutExpired:
                lifecycle['timedOut'] = True
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                lifecycle['exitCode'] = process.returncode
                raise RuntimeError(f'{label}: participant timeout; partial events retained')
        lifecycle['exitCode'] = code
        if code:
            raise RuntimeError(f'{label}: Pi exited {code}; inspect participant evidence')
        events = [json.loads(line) for line in (self.evidence / f'{label}-events.jsonl').read_text().splitlines() if line]
        errors = [e['message'].get('errorMessage', 'Model request failed') for e in events
                  if e.get('type') == 'message_end' and e.get('message', {}).get('stopReason') == 'error']
        if errors:
            raise RuntimeError(f'{label}: ' + '; '.join(errors))
        if not any(e.get('type') == 'tool_execution_end' for e in events):
            raise RuntimeError(f'{label}: no completed native tool call')

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
