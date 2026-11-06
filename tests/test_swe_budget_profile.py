import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('participant_budget', ROOT / 'examples/real-code-agent/participant.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SweBudgetProfileTest(unittest.TestCase):
    def test_zero_step_limit_and_exit_status_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'evidence'
            evidence.mkdir()
            participant = module.Participant.__new__(module.Participant)
            participant.evidence = evidence
            participant.state = root / 'state'
            participant.binary = '/fixture/python'
            participant.model = 'fixture'
            participant.reasoning_effort = None
            participant.implementation = 'mini-swe-agent'
            participant.supervisor = None
            participant.server = SimpleNamespace(server_port=1234)
            observed = {}

            def run(command, project, env, label, lifecycle, **options):
                observed.update(command=command, options=options)
                (evidence / f'{label}-events.jsonl').write_text(json.dumps({
                    'type': 'participant_exit', 'result': {'exit_status': 'TimeExceeded'}
                }) + '\n')
                raise RuntimeError('fixture exit')

            participant._run_turn = run
            with patch.dict('os.environ', {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'fixture exit'):
                    participant.turn('swe', root, prompt='task', step_limit=0,
                                     wall_time_limit_seconds=1800, transport_retry_limit=0)
            lifecycle = json.loads((evidence / 'swe-lifecycle.json').read_text())
            self.assertEqual(lifecycle['stepLimit'], 0)
            self.assertEqual(lifecycle['wallTimeLimitSeconds'], 1800)
            self.assertEqual(lifecycle['participantExitStatus'], 'TimeExceeded')
            self.assertEqual(lifecycle['transportRetryLimit'], 0)
            self.assertEqual(observed['options']['timeout_seconds'], 1860)
            self.assertEqual(observed['command'][observed['command'].index('--step-limit') + 1], '0')

    def test_local_mini_container_receives_only_resolved_docker_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'evidence'
            evidence.mkdir()
            participant = module.Participant.__new__(module.Participant)
            participant.evidence = evidence
            participant.state = root / 'state'
            participant.binary = '/fixture/python'
            participant.model = 'fixture'
            participant.reasoning_effort = None
            participant.implementation = 'mini-swe-agent'
            participant.supervisor = None
            participant.server = SimpleNamespace(server_port=1234)
            observed = {}
            def run(command, project, env, label, lifecycle, **options):
                observed.update(env=env, command=command)
                (evidence / f'{label}-events.jsonl').write_text(json.dumps({
                    'type': 'tool_execution_end', 'result': {'returncode': 0}
                }) + '\n')
                return {}
            participant._run_turn = run
            with patch.dict('os.environ', {'PATH': '/usr/bin', 'SECRET_FIXTURE': 'must-not-forward'}, clear=True), \
                 patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='unix:///tmp/docker.sock\n')):
                participant.turn('swe', root, prompt='task', container='fixture', transport_retry_limit=0)
            self.assertEqual(observed['env']['DOCKER_HOST'], 'unix:///tmp/docker.sock')
            self.assertNotIn('SECRET_FIXTURE', observed['env'])
            self.assertNotIn('DOCKER_CONTEXT', observed['env'])

    def test_unresolved_docker_context_stops_before_model_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); evidence = root / 'evidence'; evidence.mkdir()
            participant = module.Participant.__new__(module.Participant)
            participant.evidence = evidence; participant.state = root / 'state'
            participant.binary = '/fixture/python'; participant.model = 'fixture'
            participant.reasoning_effort = None; participant.implementation = 'mini-swe-agent'
            participant.supervisor = None; participant.server = SimpleNamespace(server_port=1234)
            participant._run_turn = lambda *args, **kwargs: self.fail('must not dispatch')
            with patch.dict('os.environ', {'PATH': '/usr/bin'}, clear=True), \
                 patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='tcp://remote:2375\n')):
                with self.assertRaisesRegex(RuntimeError, 'local Docker context'):
                    participant.turn('swe', root, prompt='task', container='fixture', transport_retry_limit=0)

    def test_nonzero_command_return_is_counted_as_tool_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); evidence = root / 'evidence'; evidence.mkdir()
            participant = module.Participant.__new__(module.Participant)
            participant.evidence = evidence; participant.state = root / 'state'
            participant.binary = '/fixture/python'; participant.model = 'fixture'
            participant.reasoning_effort = None; participant.implementation = 'mini-swe-agent'
            participant.supervisor = None; participant.server = SimpleNamespace(server_port=1234)
            def run(command, project, env, label, lifecycle, **options):
                events = [{'type':'tool_execution_end','result':{'returncode':1}},
                          {'type':'tool_execution_end','result':{'returncode':0}},
                          {'type':'tool_execution_end','exceptionClass':'TimeoutError'}]
                (evidence / f'{label}-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
                return {}
            participant._run_turn = run
            with patch.dict('os.environ', {}, clear=True):
                participant.turn('swe', root, prompt='task', transport_retry_limit=0)
            lifecycle=json.loads((evidence/'swe-lifecycle.json').read_text())
            self.assertEqual(lifecycle['completedToolCalls'], 3)
            self.assertEqual(lifecycle['toolErrors'], 2)


if __name__ == '__main__':
    unittest.main()
