import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "agent_flywheel", ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerSkillAgentFlywheelTest(unittest.TestCase):
    def test_selection_prefers_small_tested_unbound_scope(self):
        scopes = [
            {"id": "large", "repositoryId": "r", "pathBoundary": "large", "sourceFileCount": 40, "testFileCount": 8},
            {"id": "small-no-tests", "repositoryId": "r", "pathBoundary": "small", "sourceFileCount": 2, "testFileCount": 0},
            {"id": "small-tested", "repositoryId": "r", "pathBoundary": "tested", "sourceFileCount": 3, "testFileCount": 1},
        ]
        assessment = {"skills": [
            {"skillId": "large", "maturity": "L1-structural-ready"},
            {"skillId": "small-no-tests", "maturity": "L1-structural-ready"},
            {"skillId": "small-tested", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_scope(scopes, assessment, "r")["id"], "small-tested")

    def test_compare_requires_one_l2_gain_without_l3_promotion(self):
        before = {
            "totals": {"scopeSkillCount": 5, "structuralReadyCount": 5, "programBoundCount": 1,
                       "semanticReadyCount": 1, "maintenanceReadyCount": 0}
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before_path = root / "before.json"
            before_path.write_text(json.dumps(before) + "\n")
            after = {
                "parentAssessmentSha256": MODULE.digest(before_path),
                "totals": {"scopeSkillCount": 5, "structuralReadyCount": 5, "programBoundCount": 2,
                           "semanticReadyCount": 2, "maintenanceReadyCount": 0},
            }
            after_path = root / "after.json"
            after_path.write_text(json.dumps(after) + "\n")
            output = root / "result.json"
            MODULE.compare(type("Args", (), {"before": before_path, "after": after_path, "output": output}))
            self.assertEqual(json.loads(output.read_text())["decision"], "review-proposed-knowledge")


if __name__ == "__main__":
    unittest.main()
