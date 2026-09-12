import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = ROOT / "target/release"


@unittest.skipUnless((BIN / "alharmony-ops").exists(), "build public binaries first")
class MockCampaignTests(unittest.TestCase):
    def test_false_success_is_rejected_and_failure_evidence_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            scenario = json.loads((ROOT / "examples/mock-agent/scenario.json").read_text())
            scenario["turns"][1]["actions"][0]["arguments"]["replace"] = "Wrong implementation"
            fixture = root / "scenario.json"
            fixture.write_text(json.dumps(scenario))
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/ci-mock-agent-smoke.py"),
                "--bin-dir", str(BIN), "--storage", str(root / "storage"),
                "--evidence", str(root / "evidence"), "--scenario", str(fixture)
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stderr)
            summary = json.loads((root / "evidence/summary.json").read_text())
            self.assertFalse(summary["ok"])
            self.assertEqual(summary["failure"], "AssertionError: firstEditObserved")
            events = [json.loads(line) for line in (root / "evidence/events.jsonl").read_text().splitlines()]
            self.assertTrue(any(e.get("message", {}).get("claimedSuccess") for e in events))
            self.assertTrue((root / "evidence/SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()
