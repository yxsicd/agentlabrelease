import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('validator', Path(__file__).parents[1]/'scripts/channel-validate.py')
validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)

class ValidationTests(unittest.TestCase):
    def test_frozen_dependencies_and_failure_retained(self):
        publication = json.loads((Path(__file__).parents[1]/'release/candidates/40ecdf4b-linux-x64/publication.json').read_text())
        lock = json.loads((Path(__file__).parents[1]/'release/candidates/40ecdf4b-linux-x64/environment-lock.json').read_text())
        plan = dict(publication=publication, environmentLock=lock, targetChannel='aldev',
                    sourceChannelOrCandidate=publication['tag'], compositionIdentity='identity',
                    sourceLockSha256='lock', requiredChecks=['clean_install', 'protocol_discovery', 'tablegit_recovery'])
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=1 if command[1] == 'examples/run.py' else 0)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory); root = source/'evidence'
            receipt = validator.execute(plan, source, root, run)
            self.assertFalse(receipt['qualified'])
            self.assertEqual(receipt['checks']['protocol_discovery']['status'], 'failed')
            self.assertEqual(receipt['checks']['tablegit_recovery']['status'], 'passed')
            self.assertEqual(json.loads((source/'session-sdk.json').read_text()), publication['sessionSdk'])
            self.assertIn('--sdk-program', calls[-1])
            self.assertFalse(receipt['activated'])
