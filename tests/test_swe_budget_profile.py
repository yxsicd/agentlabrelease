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


if __name__ == '__main__':
    unittest.main()
