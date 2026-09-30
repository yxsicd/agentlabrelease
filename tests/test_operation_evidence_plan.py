import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "operation_evidence_plan",
    ROOT / "examples/maintainer-knowledge-gate/operation_evidence_plan.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def skill(skill_id, capabilities, maintenance=False, semantic=True):
    return {
        "skillId": skill_id,
        "repositoryId": "repo",
        "sourceRevision": "a" * 40,
        "capabilities": capabilities,
        "maturity": "L3-maintenance-ready" if maintenance else "L2-semantic-ready",
        "checks": {
            "semanticReady": semantic,
            "maintenanceReady": maintenance,
        },
        "gaps": [] if maintenance else [{
            "code": "MS-OPERATION-EVIDENCE-MISSING",
            "dimension": "operation",
            "severity": "P1",
        }],
    }


class OperationEvidencePlanTests(unittest.TestCase):
    def assessment(self):
        return {
            "schema": "agentlab.maintainer_skill_assessment.v1",
            "assessmentId": "assessment-1",
            "skills": [
                skill("build-test", ["source-maintenance", "build-maintenance", "test-maintenance"]),
                skill("build-only", ["source-maintenance", "build-maintenance"]),
                skill("test-only", ["source-maintenance", "test-maintenance"]),
                skill("source-only", ["source-maintenance"]),
                skill("support", ["support-maintenance"]),
                skill("done", ["source-maintenance", "build-maintenance"], maintenance=True),
            ],
        }

    def test_all_operation_lanes_are_deterministic_and_non_promoting(self):
        plan = MODULE.build_plan(self.assessment(), "repo")
        self.assertEqual(plan["schema"], MODULE.SCHEMA)
        self.assertEqual(plan["sourceRevision"], "a" * 40)
        self.assertEqual(plan["summary"]["scopeCount"], 6)
        self.assertEqual(plan["summary"]["operationEvidencePendingCount"], 5)
        self.assertEqual(
            plan["summary"]["laneCounts"],
            {
                "build-test": 1,
                "build-only": 1,
                "test-only": 1,
                "source-only": 1,
                "support-config": 1,
            },
        )
        self.assertFalse(plan["automaticPromotion"])
        self.assertTrue(plan["sharedEvidencePolicy"]["scopeSpecificOperationFactRequired"])
        self.assertIn("failed or blocked preflight", plan["sharedEvidencePolicy"]["neverSufficientAlone"])

        by_id = {row["skillId"]: row for row in plan["lanes"]}
        self.assertEqual(by_id["build-test"]["lane"], "build-test")
        self.assertEqual(by_id["build-only"]["lane"], "build-only")
        self.assertEqual(by_id["test-only"]["lane"], "test-only")
        self.assertEqual(by_id["source-only"]["lane"], "source-only")
        self.assertEqual(by_id["support"]["lane"], "support-config")
        for row in plan["lanes"]:
            self.assertFalse(row["automaticPromotion"])
            self.assertTrue(row["operationFactRequirements"]["exactScopeBindingRequired"])
            self.assertTrue(row["operationFactRequirements"]["passReceiptRequired"])
            self.assertEqual(row["operationFactRequirements"]["dimensions"], ["operation"])
            self.assertEqual(row["operationFactRequirements"]["scopeSkillIds"], [row["skillId"]])

    def test_planner_ignores_non_semantic_and_already_maintenance_ready_rows(self):
        assessment = self.assessment()
        assessment["skills"].append(skill("not-semantic", ["source-maintenance"], semantic=False))
        plan = MODULE.build_plan(assessment, "repo")
        ids = {row["skillId"] for row in plan["lanes"]}
        self.assertNotIn("done", ids)
        self.assertNotIn("not-semantic", ids)

    def test_cli_writes_plan_without_creating_operation_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assessment = root / "assessment.json"
            output = root / "plan.json"
            assessment.write_text(json.dumps(self.assessment()))
            plan = MODULE.build_plan(json.loads(assessment.read_text()), "repo")
            MODULE.write(output, plan)
            written = json.loads(output.read_text())
            self.assertEqual(written["decision"], "collect-operation-evidence")
            self.assertNotIn("programFacts", written)
            self.assertNotIn("operationFacts", written)
            self.assertFalse(written["automaticPromotion"])

    def test_repository_revision_must_be_unambiguous(self):
        assessment = self.assessment()
        assessment["skills"][0]["sourceRevision"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "source revision is ambiguous"):
            MODULE.build_plan(assessment, "repo")


if __name__ == "__main__":
    unittest.main()
