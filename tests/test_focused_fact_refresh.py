import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "focused_fact_refresh",
    ROOT / "examples/maintainer-knowledge-gate/focused_fact_refresh.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
KNOWLEDGE = ROOT / "examples/maintainer-knowledge-gate/first-four"
CANDIDATE_ID = "shadow-case-uiability-backup-restore-state-recovery"
PLAN = KNOWLEDGE / "construction-plans/uiability-backup-restore.json"


def latest_assessment():
    values = []
    for path in (KNOWLEDGE / "assessments").glob("*.json"):
        value = json.loads(path.read_text())
        values.append((value["roundIndex"], path))
    return max(values)[1]


class FocusedFactRefreshTest(unittest.TestCase):
    def prepare_request(self, output: Path):
        MODULE.prepare(type("Args", (), {
            "knowledge": KNOWLEDGE,
            "assessment": latest_assessment(),
            "candidate_id": CANDIDATE_ID,
            "plan": PLAN,
            "evidence_root": ROOT,
            "output": output,
        }))
        return json.loads(output.read_text())

    def test_prepare_consumes_exact_blocked_candidate_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "request.json"
            request = self.prepare_request(output)
            self.assertEqual(request["readinessDecision"], "blocked-knowledge-refresh")
            self.assertEqual(request["existingFact"]["id"], "agent-analysis-uiability-backup-restore-state-recovery")
            self.assertEqual(request["scope"]["id"], "skill-scope-guide-snippets-ability-uiabilityrecover")
            self.assertIn(
                "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets",
                {row["path"] for row in request["requiredImplementationPaths"]},
            )

    def test_prepare_rejects_a_plan_outside_the_knowledge_cut(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "plan.json"
            outside.write_text(PLAN.read_text())
            with self.assertRaisesRegex(ValueError, "must be under"):
                MODULE.prepare(type("Args", (), {
                    "knowledge": KNOWLEDGE, "assessment": latest_assessment(),
                    "candidate_id": CANDIDATE_ID, "plan": outside,
                    "evidence_root": ROOT, "output": Path(directory) / "request.json",
                }))

    def test_validate_replaces_one_fact_and_requires_every_feedback_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            request = self.prepare_request(request_path)
            refreshed = dict(request["existingFact"])
            refreshed["interpretation"] = refreshed["interpretation"] + " The refreshed evidence binds page and test owners."
            evidence = list(refreshed["evidence"])
            known = {row["path"] for row in evidence}
            for field in ("requiredImplementationPaths", "requiredOraclePaths"):
                for item in request[field]:
                    if item["path"] not in known:
                        evidence.append({"path": item["path"], "gitBlobOid": "1" * 40})
                        known.add(item["path"])
            refreshed["evidence"] = evidence
            source = root / "source"
            source.mkdir()
            proposal = root / "proposal.json"
            proposal.write_text("{}\n")
            output = root / "facts.jsonl"
            receipt = root / "receipt.json"
            with mock.patch.object(MODULE.BASE, "validate_proposal", return_value=refreshed):
                MODULE.validate(type("Args", (), {
                    "request": request_path, "proposal": proposal, "source": source,
                    "program_facts": KNOWLEDGE / "program_facts.jsonl",
                    "output": output, "receipt": receipt,
                }))
            result = json.loads(receipt.read_text())
            self.assertEqual(result["changeKind"], "updated")
            self.assertEqual(set(result["addedEvidencePaths"]), {
                "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets",
                "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets",
            })
            rows = MODULE.READINESS.rows(output)
            self.assertEqual(sum(row["id"] == refreshed["id"] for row in rows), 1)

    def test_compare_preserves_l2_counts_instead_of_claiming_a_new_scope(self):
        totals = {
            "scopeSkillCount": 480, "structuralReadyCount": 480,
            "programBoundCount": 24, "semanticReadyCount": 17,
            "maintenanceReadyCount": 2,
        }
        scope_id = "skill-scope-guide-snippets-ability-uiabilityrecover"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.json"
            before.write_text(json.dumps({
                "totals": totals, "skills": [{"skillId": scope_id, "maturity": "L2-semantic-ready"}],
            }) + "\n")
            after = root / "after.json"
            after.write_text(json.dumps({
                "parentAssessmentSha256": MODULE.BASE.digest(before),
                "totals": totals, "skills": [{"skillId": scope_id, "maturity": "L2-semantic-ready"}],
            }) + "\n")
            output = root / "result.json"
            MODULE.compare(type("Args", (), {
                "before": before, "after": after, "scope_id": scope_id, "output": output,
            }))
            result = json.loads(output.read_text())
            self.assertEqual(result["decision"], "review-proposed-knowledge-refresh")
            self.assertEqual(result["before"], result["after"])


if __name__ == "__main__":
    unittest.main()
