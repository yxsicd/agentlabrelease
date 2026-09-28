import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "agent_flywheel", ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerSkillAgentFlywheelTest(unittest.TestCase):
    def test_scope_checkout_materializes_only_exact_requested_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
            (source / "wanted").mkdir()
            (source / "wanted" / "main.ets").write_text("wanted\n")
            (source / "sibling").mkdir()
            (source / "sibling" / "large.bin").write_bytes(b"x" * 4096)
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip()
            bare = root / "remote.git"
            subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True)
            subprocess.run(
                ["git", "-C", str(bare), "config", "uploadpack.allowFilter", "true"], check=True
            )
            destination = root / "checkout"
            subprocess.run([
                str(ROOT / "scripts/checkout-maintainer-scope.sh"),
                bare.as_uri(), revision, "wanted", str(destination),
            ], check=True)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
                ).strip(),
                revision,
            )
            self.assertTrue((destination / "wanted/main.ets").is_file())
            self.assertFalse((destination / "sibling").exists())
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(destination), "status", "--porcelain"], text=True
                ),
                "",
            )

    def test_selection_prefers_small_tested_unbound_scope(self):
        scopes = [
            {"id": "large", "repositoryId": "r", "pathBoundary": "large", "sourceFileCount": 40, "testFileCount": 8, "evidence": [{"path": "large/main.rs"}]},
            {"id": "small-no-tests", "repositoryId": "r", "pathBoundary": "small", "sourceFileCount": 2, "testFileCount": 0, "evidence": [{"path": "small/main.rs"}]},
            {"id": "small-tested", "repositoryId": "r", "pathBoundary": "tested", "sourceFileCount": 3, "testFileCount": 1, "evidence": [{"path": "tested/main.rs"}]},
        ]
        assessment = {"skills": [
            {"skillId": "large", "maturity": "L1-structural-ready"},
            {"skillId": "small-no-tests", "maturity": "L1-structural-ready"},
            {"skillId": "small-tested", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_scope(scopes, assessment, "r")["id"], "small-tested")

    def test_selection_skips_scope_whose_inventory_evidence_is_outside_boundary(self):
        scopes = [
            {"id": "broken", "repositoryId": "r", "pathBoundary": "entry/_build", "sourceFileCount": 1,
             "testFileCount": 1, "evidence": [{"path": "entry/build-profile.json5"}]},
            {"id": "reachable", "repositoryId": "r", "pathBoundary": "entry/src", "sourceFileCount": 2,
             "testFileCount": 0, "evidence": [{"path": "entry/src/main.ets"}]},
        ]
        assessment = {"skills": [
            {"skillId": "broken", "maturity": "L1-structural-ready"},
            {"skillId": "reachable", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_scope(scopes, assessment, "r")["id"], "reachable")

    def test_auto_repository_selection_prefers_lowest_normalized_coverage(self):
        scopes = [
            {"id": "a1", "repositoryId": "a", "pathBoundary": "a1", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "a1/main.ets"}]},
            {"id": "a2", "repositoryId": "a", "pathBoundary": "a2", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "a2/main.ets"}]},
            {"id": "b1", "repositoryId": "b", "pathBoundary": "b1", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "b1/main.ets"}]},
            {"id": "b2", "repositoryId": "b", "pathBoundary": "b2", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "b2/main.ets"}]},
        ]
        assessment = {"skills": [
            {"skillId": "a1", "maturity": "L2-semantic-ready"},
            {"skillId": "a2", "maturity": "L1-structural-ready"},
            {"skillId": "b1", "maturity": "L1-structural-ready"},
            {"skillId": "b2", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_repository(scopes, assessment, ["a", "b"]), "b")

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
