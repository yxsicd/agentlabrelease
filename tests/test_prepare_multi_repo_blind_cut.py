from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-multi-repo-blind-cut.py"
SPEC = importlib.util.spec_from_file_location("multi_repo_blind_cut", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture(root: Path) -> dict[str, Path]:
    oracle = root / "oracle.mjs"
    oracle.write_text("export const hidden = true;\n")
    reference = root / "reference"
    reference.mkdir()
    (reference / "contracts.ts").write_text("export const fixed = true;\n")
    calibration = root / "calibration.json"
    calibration.write_text('{"schema":"agentlab.multi_repo_calibration.v1"}\n')
    review = root / "review.json"
    review.write_text('{"verdict":"approved"}\n')
    case = root / "case.json"
    case.write_text(json.dumps({
        "schema": "agentlab.multi_repo_evaluation_case.v1",
        "id": "case-private-001",
        "status": "frozen-calibrated",
        "title": "Repair a cross-repository policy",
        "sourceSetSha256": "a" * 64,
        "sources": [
            {"id": "contracts", "repository": "repo-a", "revision": "1" * 40},
            {"id": "app", "repository": "repo-b", "revision": "2" * 40},
        ],
        "allowedEdits": [{"repositoryId": "contracts", "path": "src/policy.ts"}],
        "stages": [{"id": "repair", "demand": "Repair the policy.", "checkIds": ["hidden-check"]}],
        "oracle": {
            "sha256": hashlib.sha256(oracle.read_bytes()).hexdigest(),
            "receiptSchema": "oracle.v1",
        },
        "automaticPromotion": False,
    }))
    return {"case": case, "oracle": oracle, "reference": reference, "calibration": calibration, "review": review}


class PrepareMultiRepoBlindCutTests(unittest.TestCase):
    def test_projects_only_participant_visible_case_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = fixture(root)
            output = root / "cut"
            receipt = MODULE.project(
                case_path=paths["case"], oracle_path=paths["oracle"],
                reference_root=paths["reference"], calibration_path=paths["calibration"],
                review_path=paths["review"], output=output, method_revision="b" * 40,
                constructed_at="2026-09-24T00:00:00Z", source_visibility="held-out-public-revision",
            )
            task = json.loads((output / "participant/task.json").read_text())
            self.assertEqual(task["caseId"], "case-private-001")
            self.assertEqual(task["stages"], [{"id": "repair", "demand": "Repair the policy."}])
            self.assertNotIn("checkIds", json.dumps(task))
            self.assertNotIn("hidden-check", json.dumps(task))
            self.assertFalse(task["oracleVisibleToParticipant"])
            self.assertFalse(receipt["freshness"]["eligibleForUnseenAgentDiscrimination"])
            self.assertTrue((output / "evaluator/oracle.mjs").is_file())
            self.assertTrue((output / "evaluator/reference/contracts.ts").is_file())

    def test_rejects_oracle_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = fixture(root)
            paths["oracle"].write_text("changed")
            with self.assertRaisesRegex(MODULE.ProjectionError, "Oracle digest differs"):
                MODULE.project(
                    case_path=paths["case"], oracle_path=paths["oracle"],
                    reference_root=paths["reference"], calibration_path=paths["calibration"],
                    review_path=paths["review"], output=root / "cut", method_revision="b" * 40,
                    constructed_at="2026-09-24T00:00:00Z", source_visibility="private-maintenance",
                )


if __name__ == "__main__":
    unittest.main()
