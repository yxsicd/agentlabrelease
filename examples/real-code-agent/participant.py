"""Operator-owned gateway capture and a replaceable Pi participant launcher."""
import http.server
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error


CONTAINER_GATEWAY_PORT = 18765


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Participant:
    def __init__(self, evidence, state, binary, gateway, model, route='glm', implementation='pi', reasoning_effort=None,
                 gateway_timeout_seconds=180, thinking_type=None, response_format=None,
                 api='openai-completions'):
        if api not in ('openai-completions', 'openai-responses'):
            raise ValueError('unsupported participant API')
        if api == 'openai-responses' and (implementation != 'pi' or thinking_type is not None):
            raise ValueError('Responses requires Pi and native reasoning policy, not thinking.type')
        self.api = api
        self.api_path = '/v1/responses' if api == 'openai-responses' else '/v1/chat/completions'
        if response_format not in (None, 'json_object'):
            raise ValueError('response_format must be omitted or json_object')
        self.response_format = response_format
        if thinking_type not in (None, 'enabled', 'disabled'):
            raise ValueError('thinking_type must be omitted, enabled or disabled')
        self.thinking_type = thinking_type
        if (not isinstance(gateway_timeout_seconds, int)
                or not 30 <= gateway_timeout_seconds <= 180):
            raise ValueError('gateway_timeout_seconds must be from 30 through 180')
        self.implementation = implementation
        self.evidence = evidence
        self.state = state
        self.binary = str(Path(binary).absolute())
        if implementation == 'mini-swe-agent':
            probe = subprocess.run([self.binary, '-c',
                'import sys,json,minisweagent; from minisweagent.agents.default import DefaultAgent; '
                'from minisweagent.environments.local import LocalEnvironment; '
                'from minisweagent.models.litellm_model import LitellmModel; '
                'print(json.dumps(dict(prefix=sys.prefix,version=minisweagent.__version__)))'],
                capture_output=True,timeout=60,
                env={k:os.environ[k] for k in ('PATH','LANG','LC_ALL','TMPDIR') if k in os.environ})
            (evidence/'runtime-probe-stdout.log').write_bytes(probe.stdout)
            (evidence/'runtime-probe-stderr.log').write_bytes(probe.stderr)
            (evidence/'runtime-probe.json').write_text(json.dumps(dict(implementation=implementation,
                executable=self.binary,exitCode=probe.returncode,captureAuthority='operator'),indent=2)+'\n')
            if probe.returncode:
                raise RuntimeError('Harness participant runtime preflight failed before dispatch')
        self.gateway = gateway.rstrip('/')
        self.model = model
        self.route = route
        self.reasoning_effort = reasoning_effort if reasoning_effort not in (None, '', 'default') else None
        self.active_reasoning_effort = self.reasoning_effort
        self.gateway_timeout_seconds = gateway_timeout_seconds
        self.key = os.environ['AGENTLAB_LM_GATEWAY_KEY']
        self.runtime_isolated = bool(os.environ.get('AGENTLAB_PARTICIPANT_RUNTIME_CONFIG'))
        self.local_proxy_token = (
            secrets.token_urlsafe(32)
            if self.runtime_isolated
            else 'agentlab-local-test-credential'
        )
        self.requests = 0
        self.lock = threading.Lock()
        state.mkdir()
        capture = evidence / 'gateway'
        capture.mkdir()
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def locally_authorized(self):
                return (
                    not owner.runtime_isolated
                    or self.headers.get('Authorization')
                    == 'Bearer ' + owner.local_proxy_token
                )

            def do_GET(self):
                if self.path != '/__agentlab_runtime_probe':
                    self.send_error(404)
                    return
                if not self.locally_authorized():
                    self.send_error(401, 'Invalid participant proxy credential')
                    return
                self.send_response(204)
                self.end_headers()

            def do_POST(self):
                if not self.locally_authorized():
                    self.send_error(401, 'Invalid participant proxy credential')
                    return
                if owner.runtime_isolated and self.path != owner.api_path:
                    self.send_error(404, 'Participant proxy path is not allowed')
                    return
                with owner.lock:
                    owner.requests += 1
                    number = owner.requests
                stem = capture / f'{number:04d}'
                started = time.monotonic()
                receipt = dict(exchangeId=f'{number:04d}',
                    startedAt=datetime.now(timezone.utc).isoformat(),
                    status=None, responseBytes=0, upstreamEof=False, semanticComplete=False, streamError=None,
                    clientDisconnected=False, outcome='in_progress')
                try:
                    self.forward(stem, receipt)
                except Exception as error:
                    receipt.update(outcome='capture_error', errorClass=type(error).__name__,
                                   error=str(error))
                    stem.with_suffix('.error.txt').write_text(str(error))
                    try:
                        self.send_error(502, 'Gateway exchange failed')
                    except OSError:
                        receipt['clientDisconnected'] = True
                finally:
                    receipt.update(endedAt=datetime.now(timezone.utc).isoformat(),
                                   durationMs=round((time.monotonic()-started)*1000))
                    stem.with_suffix('.status.json').write_text(json.dumps(receipt, indent=2)+'\n')

            def forward(self, stem, receipt):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                # Authentication is transport configuration, not test payload.
                stem.with_suffix('.request.json').write_bytes(raw)
                wire = json.loads(raw)
                wire['providerId'] = owner.route
                wire['model'] = owner.model
                if owner.active_reasoning_effort:
                    if owner.api == 'openai-responses':
                        wire.setdefault('reasoning', {})['effort'] = owner.active_reasoning_effort
                    else:
                        wire['reasoning_effort'] = owner.active_reasoning_effort
                if owner.thinking_type is not None:
                    wire['thinking'] = {'type': owner.thinking_type}
                if owner.response_format is not None:
                    if owner.api == 'openai-responses':
                        wire.setdefault('text', {})['format'] = {'type': owner.response_format}
                    else:
                        wire['response_format'] = {'type': owner.response_format}
                upstream = json.dumps(wire).encode()
                stem.with_suffix('.upstream-request.json').write_bytes(upstream)
                request = urllib.request.Request(owner.gateway + self.path, data=upstream,
                          headers={'Authorization': 'Bearer ' + owner.key,
                                   'Content-Type': 'application/json'}, method='POST')
                upstream_deadline = time.monotonic() + owner.gateway_timeout_seconds
                opened = concurrent.futures.Future()

                def open_upstream():
                    try:
                        try:
                            result = urllib.request.build_opener(NoRedirect).open(
                                request, timeout=owner.gateway_timeout_seconds
                            )
                        except urllib.error.HTTPError as error:
                            result = error
                        opened.set_result(result)
                    except Exception as error:
                        opened.set_exception(error)

                opener_thread = threading.Thread(
                    target=open_upstream,
                    name=f'agentlab-upstream-open-{receipt["exchangeId"]}',
                    daemon=True,
                )
                opener_thread.start()
                try:
                    response = opened.result(timeout=max(
                        0, upstream_deadline - time.monotonic()))
                except concurrent.futures.TimeoutError:
                    def close_late_response(future):
                        try:
                            future.result().close()
                        except Exception:
                            pass

                    opened.add_done_callback(close_late_response)
                    receipt.update(
                        upstreamDeadlineExceeded=True,
                        upstreamDeadlinePhase='response_headers',
                        outcome='upstream_deadline_exceeded',
                    )
                    try:
                        self.send_error(504, 'Upstream response deadline exceeded')
                    except OSError:
                        receipt['clientDisconnected'] = True
                    return
                with response:
                    receipt['status'] = response.status
                    try:
                        self.send_response(response.status)
                        self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                        self.end_headers()
                    except OSError:
                        receipt['clientDisconnected'] = True
                    with stem.with_suffix('.response').open('wb') as output:
                        semantic_buffer = b''

                        def observe_semantic_line(line):
                            if not wire.get('stream') or not line.startswith(b'data:'):
                                return
                            data = line[5:].strip()
                            if data == b'[DONE]' and owner.api == 'openai-completions':
                                receipt['semanticComplete'] = True
                                return
                            try:
                                event = json.loads(data)
                                if event.get('error'):
                                    receipt['streamError'] = event['error']
                                if owner.api == 'openai-responses':
                                    kind = event.get('type')
                                    result = event.get('response', {})
                                    if kind == 'response.completed' and result.get('status') == 'completed' and not result.get('error') and not result.get('incomplete_details'):
                                        receipt['semanticComplete'] = True
                                    elif kind in ('error', 'response.failed', 'response.incomplete'):
                                        receipt['streamError'] = result.get('error') or result.get('incomplete_details') or event.get('error') or event
                                elif any(isinstance(c.get('finish_reason'), str)
                                         for c in event.get('choices', [])):
                                    receipt['semanticComplete'] = True
                            except (ValueError, TypeError):
                                pass

                        while True:
                            if time.monotonic() >= upstream_deadline:
                                receipt.update(
                                    upstreamDeadlineExceeded=True,
                                    upstreamDeadlinePhase='response_body',
                                    outcome='upstream_deadline_exceeded',
                                )
                                break
                            # readline() can wait forever when an upstream drips bytes
                            # without a newline. read1() returns the bytes currently
                            # available, so the absolute deadline is checked even for
                            # a malformed or adversarial streaming response.
                            chunk = response.read1(65536)
                            if not chunk:
                                if semantic_buffer:
                                    observe_semantic_line(semantic_buffer)
                                receipt.update(upstreamEof=True, outcome=('stream_error' if receipt['streamError'] else 'completed' if receipt['semanticComplete'] or not wire.get('stream') else 'incomplete_stream'))
                                break
                            semantic_buffer += chunk
                            lines = semantic_buffer.split(b'\n')
                            semantic_buffer = lines.pop()
                            for line in lines:
                                observe_semantic_line(line)
                            output.write(chunk)
                            output.flush()
                            receipt['responseBytes'] += len(chunk)
                            if not receipt['clientDisconnected']:
                                try:
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                                except OSError:
                                    # Keep observing upstream after participant cancellation.
                                    receipt['clientDisconnected'] = True

        bind_host = '0.0.0.0' if self.runtime_isolated else '127.0.0.1'
        self.server = http.server.ThreadingHTTPServer((bind_host, 0), Handler)
        self.server.daemon_threads = False
        self.server.block_on_close = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        model_base_url = f'http://127.0.0.1:{self.server.server_port}/v1'
        if self.runtime_isolated:
            model_base_url = f'http://agentlab-gateway:{CONTAINER_GATEWAY_PORT}/v1'
        models = {'providers': {'agentlab-ci': {
            'baseUrl': model_base_url,
            'api': self.api, 'apiKey': self.local_proxy_token,
            'compat': {'supportsDeveloperRole': False, 'supportsReasoningEffort': False},
            'models': [{'id': model, 'reasoning': False, 'input': ['text'],
                        'contextWindow': 128000, 'maxTokens': 8192}]}}}
        (state / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
        (evidence / 'participant.json').write_text(json.dumps({
            'implementation': implementation, 'packageVersion': '0.73.1' if implementation=='pi' else '2.4.6', 'model': model,
            'gateway': gateway, 'providerRoute': route,
            'reasoningEffort': self.reasoning_effort, 'piThinkingMode': 'off',
            'providerThinkingType': self.thinking_type,
            'providerResponseFormat': self.response_format,
            'providerApi': self.api,
            'captureAuthority': 'operator-owned local forwarding proxy',
            'externalCredentialInParticipant': False}, indent=2) + '\n')

    @staticmethod
    def _is_transient_transport_error(message):
        text = message.lower()
        return any(token in text for token in ('frp', '404 <!doctype', 'http 404', 'gateway exchange failed', '502 bad gateway'))

    def turn(self, label, project, marker=None, repair=False, prompt=None, container=None, requirement=None,
             reasoning_effort=None, step_limit=None, wall_time_limit_seconds=None,
             tool_call_limit=None, transport_retry_limit=1,
             require_completed_tool_call=True,
             _transport_retry=0):
        if not isinstance(transport_retry_limit, int) or not 0 <= transport_retry_limit <= 1:
            raise ValueError('transport_retry_limit must be zero or one')
        self.active_reasoning_effort = reasoning_effort if reasoning_effort is not None else self.reasoning_effort
        prompt = prompt or (f'Work in the current Harmony ArkTS project. Read the page source and '
                  f'{"repair its invalid trailing text, then " if repair else ""}'
                  f'change its displayed Text to exactly "{marker}". Keep the Stage application '
                  'structure and valid ArkTS syntax. Use your file tools to perform the edit. '
                  'Do not install dependencies or change build configuration. '
                  'The independent operator compiles and evaluates the actual files afterwards. '
                  'Briefly describe your change when done.')
        if requirement: prompt += '\nAdditional requirement: '+requirement
        (self.evidence / f'{label}-prompt.txt').write_text(prompt)
        runtime_config = os.environ.get('AGENTLAB_PARTICIPANT_RUNTIME_CONFIG')
        session_path = self.state / 'pi-session.jsonl' if runtime_config else self.evidence / 'pi-session.jsonl'
        command = [self.binary, '--print', '--mode', 'json', '--provider', 'agentlab-ci',
                   '--model', self.model, '--thinking', 'off', '--no-extensions',
                   '--no-skills', '--no-context-files',
                   '--session', str(session_path), prompt]
        if self.implementation == 'mini-swe-agent':
            command = [self.binary, str(Path(__file__).with_name('mini_runner.py')),
                       '--base-url', f'http://127.0.0.1:{self.server.server_port}/v1',
                       '--model', self.model, '--trajectory',
                       str(self.evidence / f'{label}-mini-trajectory.json')]
            if container: command += ['--container',container]
            if step_limit is not None: command += ['--step-limit',str(step_limit)]
            if wall_time_limit_seconds is not None:
                command += ['--wall-time-limit-seconds',str(wall_time_limit_seconds)]
            command.append(prompt)
        # Only the operator-side proxy has the external credential.
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR') if k in os.environ}
        env.update(HOME=str(self.state.parent), PI_CODING_AGENT_DIR=str(self.state))
        if runtime_config:
            env.update(
                AGENTLAB_PARTICIPANT_RUNTIME_CONFIG=runtime_config,
                AGENTLAB_PARTICIPANT_RUNTIME_LABEL=label,
                AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT=os.environ[
                    'AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'
                ],
                AGENTLAB_OPERATOR_GATEWAY_PORT=str(self.server.server_port),
                DOCKER_CONFIG=os.environ['DOCKER_CONFIG'],
            )
            for key in ('DOCKER_HOST', 'DOCKER_CONTEXT'):
                if key in os.environ:
                    env[key] = os.environ[key]
        (self.evidence / f'{label}-command.json').write_text(json.dumps(command, indent=2) + '\n')
        lifecycle = {'label': label, 'startedAt': datetime.now(timezone.utc).isoformat(),
                     'captureAuthority': 'operator', 'exitCode': None, 'timedOut': False,
                     'providerReasoningEffort': self.active_reasoning_effort,
                     'transportRetryLimit': transport_retry_limit,
                     'requireCompletedToolCall': require_completed_tool_call}
        if tool_call_limit is not None:
            if not isinstance(tool_call_limit, int) or tool_call_limit < 1:
                raise ValueError('tool_call_limit must be a positive integer')
            lifecycle.update(maxToolCalls=tool_call_limit, toolCallBudgetExceeded=False)
        if self.implementation == 'mini-swe-agent':
            lifecycle.update(stepLimit=step_limit or 30,
                             wallTimeLimitSeconds=wall_time_limit_seconds or 360)
        started = time.monotonic()
        turn_error = None
        turn_result = None
        try:
            run_options = {}
            if wall_time_limit_seconds is not None:
                run_options['timeout_seconds'] = max(420, wall_time_limit_seconds + 60)
                lifecycle['supervisorTimeoutSeconds'] = run_options['timeout_seconds']
            if tool_call_limit is not None:
                run_options['tool_call_limit'] = tool_call_limit
            if not require_completed_tool_call:
                run_options['require_completed_tool_call'] = False
            turn_result = self._run_turn(command, project, env, label, lifecycle, **run_options)
        except RuntimeError as error:
            turn_error = error
        finally:
            lifecycle.update(endedAt=datetime.now(timezone.utc).isoformat(),
                             durationMs=round((time.monotonic()-started)*1000))
            events_path = self.evidence / f'{label}-events.jsonl'
            completed_tools = tool_errors = parse_errors = 0
            if events_path.is_file():
                for line in events_path.read_bytes().splitlines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        parse_errors += 1
                        continue
                    if event.get('type') == 'tool_execution_end':
                        completed_tools += 1
                        if event.get('result', {}).get('isError'):
                            tool_errors += 1
            lifecycle.update(completedToolCalls=completed_tools,
                             toolErrors=tool_errors,nativeParseErrors=parse_errors)
            source = project / 'entry/src/main/ets/pages/Index.ets'
            lifecycle['sourcePresent'] = source.is_file()
            if source.is_file():
                (self.evidence / f'{label}-actual-source.ets').write_bytes(source.read_bytes())
            (self.evidence / f'{label}-lifecycle.json').write_text(json.dumps(lifecycle, indent=2)+'\n')
        if turn_error is not None:
            combined = str(turn_error)
            if (_transport_retry < transport_retry_limit
                    and lifecycle.get('completedToolCalls') == 0
                    and self._is_transient_transport_error(combined)):
                preserved = []
                for suffix in ('events.jsonl','stderr.log','lifecycle.json','command.json','prompt.txt'):
                    source = self.evidence / f'{label}-{suffix}'
                    if source.is_file():
                        target = self.evidence / f'{label}-transport-attempt-1-{suffix}'
                        shutil.copy2(source, target); preserved.append(target.name)
                (self.evidence / f'{label}-transport-retry.json').write_text(json.dumps(dict(
                    schema='agentlab.participant_transport_retry.v1', label=label, retryCount=1,
                    reason=combined, preserved=preserved), indent=2)+'\n')
                return self.turn(label, project, marker=marker, repair=repair, prompt=prompt, container=container,
                                 requirement=requirement, reasoning_effort=reasoning_effort,
                                 step_limit=step_limit,
                                 wall_time_limit_seconds=wall_time_limit_seconds,
                                 tool_call_limit=tool_call_limit,
                                 transport_retry_limit=transport_retry_limit,
                                 require_completed_tool_call=require_completed_tool_call,
                                 _transport_retry=1)
            raise turn_error
        source = project / 'entry/src/main/ets/pages/Index.ets'
        if marker is not None and marker not in source.read_text():
            raise RuntimeError(f'{label}: Agent did not change actual source')
        print(f'{label}: real {self.implementation} turn completed', flush=True)
        return turn_result

    def _run_turn(self, command, project, env, label, lifecycle, timeout_seconds=420,
                  tool_call_limit=None, require_completed_tool_call=True):
        lifecycle['participantBudgetSeconds'] = timeout_seconds
        lifecycle['participantBudgetScope'] = 'native-process-watchdog'
        def terminate(process):
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

        events_path = self.evidence / f'{label}-events.jsonl'
        with (self.evidence / f'{label}-events.jsonl').open('wb') as out, \
             (self.evidence / f'{label}-stderr.log').open('wb') as err:
            process = subprocess.Popen(command, cwd=project, env=env, stdout=out, stderr=err,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + timeout_seconds
            while True:
                started_tools = 0
                if tool_call_limit is not None and events_path.is_file():
                    for line in events_path.read_bytes().splitlines():
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        started_tools += event.get('type') == 'tool_execution_start'
                    lifecycle['startedToolCalls'] = started_tools
                    if started_tools > tool_call_limit:
                        lifecycle['toolCallBudgetExceeded'] = True
                        terminate(process)
                        lifecycle['exitCode'] = process.returncode
                        raise RuntimeError(
                            f'{label}: participant exceeded tool-call limit '
                            f'{tool_call_limit}; partial events retained'
                        )
                code = process.poll()
                if code is not None:
                    break
                if time.monotonic() >= deadline:
                    lifecycle['timedOut'] = True
                    terminate(process)
                    lifecycle['exitCode'] = process.returncode
                    raise RuntimeError(f'{label}: participant timeout; partial events retained')
                time.sleep(0.1)
        lifecycle['exitCode'] = code
        if code:
            raise RuntimeError(f'{label}: {"Pi" if self.implementation=="pi" else self.implementation} exited {code}; inspect participant evidence')
        events, parse_errors = [], []
        for number,line in enumerate((self.evidence / f'{label}-events.jsonl').read_bytes().splitlines(),1):
            if not line.strip(): continue
            try:
                event=json.loads(line)
                if not isinstance(event,dict): raise ValueError('native event must be an object')
                events.append(event)
            except (ValueError,UnicodeDecodeError) as error:
                parse_errors.append(dict(line=number,error=str(error),rawBase64=base64.b64encode(line).decode()))
        if parse_errors:
            (self.evidence / f'{label}-native-parse-errors.json').write_text(json.dumps(parse_errors,indent=2)+'\n')
        errors = [e['message'].get('errorMessage', 'Model request failed') for e in events
                  if e.get('type') == 'message_end' and e.get('message', {}).get('stopReason') == 'error']
        if errors:
            raise RuntimeError(f'{label}: ' + '; '.join(errors))
        if (require_completed_tool_call
                and not any(e.get('type') == 'tool_execution_end' for e in events)):
            raise RuntimeError(f'{label}: no completed native tool call')
        final_messages = [
            e['message'] for e in events
            if e.get('type') == 'message_end'
            and isinstance(e.get('message'), dict)
            and e['message'].get('role') == 'assistant'
            and e['message'].get('stopReason') != 'error'
        ]
        final_message = final_messages[-1] if final_messages else None
        final_content = final_message.get('content') if final_message else None
        if isinstance(final_content, list):
            final_content = ''.join(
                row.get('text', '')
                for row in final_content
                if isinstance(row, dict) and row.get('type') == 'text'
            )
        if final_content is not None and not isinstance(final_content, str):
            final_content = None
        lifecycle['finalAssistantMessagePresent'] = final_message is not None
        lifecycle['finalAssistantTextPresent'] = final_content is not None
        if final_message is not None:
            final_bytes = (json.dumps(final_message, ensure_ascii=False, sort_keys=True) + '\n').encode()
            final_path = self.evidence / f'{label}-final-assistant-message.json'
            final_path.write_bytes(final_bytes)
            lifecycle['finalAssistantMessageSha256'] = hashlib.sha256(final_bytes).hexdigest()
        else:
            lifecycle['finalAssistantMessageSha256'] = None
        return {'message': final_message, 'content': final_content}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
