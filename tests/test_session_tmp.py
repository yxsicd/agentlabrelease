import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/agentlab-session-tmp.py'


class SessionTmpTest(unittest.TestCase):
    def call(self, action, root, session):
        return subprocess.run(['python3', str(SCRIPT), action, '--root', str(root), '--session', session], capture_output=True, text=True)

    def test_resume_is_bound_to_exact_session_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / 'one'
            self.assertEqual(self.call('init', root, 'session-a').returncode, 0)
            self.assertNotEqual(self.call('init', root, 'session-a').returncode, 0)
            (root / 'tmp' / 'scratch').write_text('student scratch')
            result = self.call('mount', root, 'session-a')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f'type=bind,source={root}/tmp,target=/tmp')
            self.assertEqual((root / 'tmp' / 'scratch').read_text(), 'student scratch')
            self.assertNotEqual(self.call('mount', root, 'session-b').returncode, 0)
            self.assertEqual(json.loads((root / 'identity.json').read_text())['session'], 'session-a')
            os.chmod(root / 'tmp', 0o755)
            self.assertNotEqual(self.call('mount', root, 'session-a').returncode, 0)

    def test_independent_sessions_do_not_share(self):
        with tempfile.TemporaryDirectory() as parent:
            a, b = Path(parent) / 'a', Path(parent) / 'b'
            self.assertEqual(self.call('init', a, 'a').returncode, 0)
            self.assertEqual(self.call('init', b, 'b').returncode, 0)
            (a / 'tmp' / 'private').write_text('a')
            self.assertFalse((b / 'tmp' / 'private').exists())
            self.assertNotEqual(self.call('mount', a, 'b').returncode, 0)

    def test_mount_refuses_symlinked_tmp(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / 'one'
            self.assertEqual(self.call('init', root, 'a').returncode, 0)
            (root / 'tmp').rmdir()
            (root / 'tmp').symlink_to(parent)
            self.assertNotEqual(self.call('mount', root, 'a').returncode, 0)


if __name__ == '__main__':
    unittest.main()
