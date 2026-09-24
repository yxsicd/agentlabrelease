from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples/multi-repo-case/pi-assessed-agent.py"
SPEC = importlib.util.spec_from_file_location("pi_assessed_agent", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PiAssessedBlindInputTests(unittest.TestCase):
    def prepare(self, root: Path):
        task = root / "task.json"
        task.write_text(json.dumps({
            "schema": "agentlab.multi_repo_participant_task.v1",
            "caseId": "case-1",
            "sourceSetSha256": "a" * 64,
            "stages": [{"id": "one", "demand": "Repair one."}],
        }))
        manifest = {
            "schema": "agentlab.blind_case_participant_bundle.v1",
            "files": [{
                "path": "task.json", "role": "task",
                "sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
            }],
            "constraints": {"allowedEditPaths": ["repo/src/file.ts"]},
        }
        (root / "manifest.json").write_text(json.dumps(manifest))
        return task

    def test_loads_digest_bound_participant_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            value = MODULE.load_blind_input(str(root))
            self.assertEqual(value["caseId"], "case-1")
            self.assertEqual(value["stages"], {"one": "Repair one."})
            self.assertEqual(value["allowedEdits"], ["repo/src/file.ts"])

    def test_rejects_task_digest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = self.prepare(root)
            task.write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "digest differs"):
                MODULE.load_blind_input(str(root))

    def test_v2_hides_allowed_edit_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "task.json"
            task.write_text(json.dumps({
                "schema": "agentlab.multi_repo_participant_task.v2",
                "caseId": "case-2",
                "sourceSetSha256": "b" * 64,
                "stages": [{"id": "one", "demand": "Discover and repair."}],
            }))
            (root / "manifest.json").write_text(json.dumps({
                "schema": "agentlab.blind_case_participant_bundle.v1",
                "files": [{
                    "path": "task.json", "role": "task",
                    "sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
                }],
                "constraints": {"budget": {"stages": 1}},
            }))
            value = MODULE.load_blind_input(str(root))
            self.assertEqual(value["caseId"], "case-2")
            self.assertIsNone(value["allowedEdits"])


if __name__ == "__main__":
    unittest.main()
