import subprocess
import sys
from pathlib import Path
import tempfile
import unittest


class FormalCaptureEntryTests(unittest.TestCase):
    def test_local_demo_refuses_formal_before_creating_workspace(self):
        script = Path(__file__).parents[1]/'examples/harmony-build/run.py'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'must-not-exist'
            result = subprocess.run([sys.executable, str(script), '--install-root', temp,
                '--root', str(root), '--evaluation-mode', 'formal'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Attempt-bound durable capture admission', result.stderr)
            self.assertFalse(root.exists())

if __name__ == '__main__': unittest.main()
