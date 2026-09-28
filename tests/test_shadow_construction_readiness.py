import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shadow_construction_readiness",
    ROOT / "examples/maintainer-knowledge-gate/shadow_construction_readiness.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
KNOWLEDGE = ROOT / "examples/maintainer-knowledge-gate/first-four"
CANDIDATE_ID = "shadow-case-uiability-backup-restore-state-recovery"
PLAN = KNOWLEDGE / "construction-plans/uiability-backup-restore.json"


class ShadowConstructionReadinessTest(unittest.TestCase):
    def test_uiability_candidate_returns_exact_knowledge_feedback(self):
        receipt = MODULE.assess(KNOWLEDGE, CANDIDATE_ID, PLAN, ROOT)
        self.assertEqual(receipt["decision"], "blocked-knowledge-refresh")
        self.assertEqual(receipt["nextGate"], "refresh-program-facts-and-shadow-candidate")
        self.assertIn(
            "implementation path is absent from bound fact evidence: "
            "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets",
            receipt["knowledgeBlockers"],
        )
        self.assertIn(
            "Oracle path is absent from bound fact evidence: "
            "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets",
            receipt["knowledgeBlockers"],
        )
        self.assertFalse(receipt["automaticPromotion"])

    def test_candidate_digest_drift_fails_closed(self):
        plan = json.loads(PLAN.read_text())
        plan["candidateSha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "candidate digest differs"):
                MODULE.assess(KNOWLEDGE, CANDIDATE_ID, path, ROOT)

    def test_qualified_runtime_requires_byte_bound_evidence(self):
        plan = json.loads(PLAN.read_text())
        plan["runtimeRequirements"][0]["status"] = "qualified"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "has no qualifying evidence"):
                MODULE.assess(KNOWLEDGE, CANDIDATE_ID, path, ROOT)

    def test_ready_decision_requires_every_independent_gate(self):
        candidate = next(
            row for row in MODULE.rows(KNOWLEDGE / "case_generation_candidates.jsonl")
            if row["id"] == CANDIDATE_ID
        )
        fact = next(
            row for row in MODULE.rows(KNOWLEDGE / "program_facts.jsonl")
            if row["id"] == candidate["factIds"][0]
        )
        plan = json.loads(PLAN.read_text())
        plan["requiredImplementationPaths"] = [{
            "path": candidate["editablePaths"][0], "reason": "covered implementation path",
        }]
        plan["requiredOraclePaths"] = [{
            "path": candidate["contextPaths"][0], "reason": "covered Oracle context path",
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "receipt.json"
            evidence.write_text("{}\n")
            ref = {"path": "receipt.json", "sha256": MODULE.file_digest(evidence)}
            for item in plan["runtimeRequirements"]:
                item.update(status="qualified", evidence=[ref])
            plan["oracleExecution"] = {"status": "qualified", "evidence": [ref]}
            plan["wrongVariantCalibration"] = {
                "status": "qualified", "evidence": [ref], "requiredCount": 2, "executedCount": 2,
            }
            path = root / "plan.json"
            path.write_text(json.dumps(plan))
            receipt = MODULE.assess(KNOWLEDGE, CANDIDATE_ID, path, root)
            self.assertEqual(receipt["decision"], "ready-for-construction")
            self.assertEqual(receipt["knowledgeBlockers"], [])
            self.assertEqual(receipt["qualificationBlockers"], [])
            self.assertIn(plan["requiredImplementationPaths"][0]["path"], {
                row["path"] for row in fact["evidence"]
            })


if __name__ == "__main__":
    unittest.main()
