import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import shutil


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

    def test_interpretation_repair_is_only_requested_for_string_length_violation(self):
        self.assertEqual(
            MODULE.interpretation_length_to_repair({"interpretation": "x" * 1601}),
            1601,
        )
        self.assertEqual(
            MODULE.interpretation_length_to_repair({"interpretation": "x" * 79}),
            79,
        )
        self.assertIsNone(
            MODULE.interpretation_length_to_repair({"interpretation": "x" * 1600})
        )
        self.assertIsNone(MODULE.interpretation_length_to_repair({"interpretation": []}))

    def test_bounded_repair_removes_extras_without_mutating_agent_evidence(self):
        before = {key: key for key in MODULE.PROPOSAL_FIELDS}
        before.update({"interpretation": "x" * 1601, "agentProposal": {"derived": True}})
        plan = MODULE.proposal_repair_plan(before)
        self.assertEqual(plan, {
            "interpretationLength": 1601,
            "extraFields": ["agentProposal"],
        })
        after = {key: value for key, value in before.items() if key != "agentProposal"}
        after["interpretation"] = "y" * 500
        self.assertEqual(MODULE.validate_bounded_repair(before, after, plan), 500)
        with self.assertRaisesRegex(ValueError, "protected field: evidence"):
            MODULE.validate_bounded_repair(
                before,
                {**after, "evidence": "different"},
                plan,
            )
        with self.assertRaisesRegex(ValueError, "requested length range"):
            MODULE.validate_bounded_repair(
                before,
                {**after, "interpretation": "z" * 399},
                plan,
            )

    def test_missing_required_field_is_not_automatically_repaired(self):
        proposal = {key: key for key in MODULE.PROPOSAL_FIELDS - {"evidence"}}
        self.assertEqual(MODULE.proposal_repair_plan(proposal)["extraFields"], [])

    def test_extra_only_repair_must_preserve_valid_interpretation(self):
        before = {key: key for key in MODULE.PROPOSAL_FIELDS}
        before.update({"interpretation": "x" * 500, "agentProposal": {"derived": True}})
        plan = MODULE.proposal_repair_plan(before)
        after = {key: value for key, value in before.items() if key != "agentProposal"}
        self.assertEqual(MODULE.validate_bounded_repair(before, after, plan), 500)
        with self.assertRaisesRegex(ValueError, "protected field: interpretation"):
            MODULE.validate_bounded_repair(
                before,
                {**after, "interpretation": "y" * 500},
                plan,
            )

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

    def test_rebind_candidate_advances_only_to_qualification_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            knowledge = root / "knowledge"
            shutil.copytree(KNOWLEDGE, knowledge)
            facts_path = knowledge / "program_facts.jsonl"
            facts = MODULE.READINESS.rows(facts_path)
            fact = next(row for row in facts if row["id"] == "agent-analysis-uiability-backup-restore-state-recovery")
            existing_paths = {row["path"] for row in fact["evidence"]}
            for path in (
                "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets",
                "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets",
            ):
                if path not in existing_paths:
                    fact["evidence"].append({"path": path, "gitBlobOid": "1" * 40})
            facts_path.write_bytes(b"".join(
                MODULE.READINESS.canonical(row) + b"\n" for row in sorted(facts, key=lambda row: row["id"])
            ))
            cut_path = knowledge / "maintainer-knowledge-cut.json"
            cut = json.loads(cut_path.read_text())
            cut["tableGitAuthority"]["revision"] = "f" * 40
            cut_path.write_text(json.dumps(cut, sort_keys=True) + "\n")
            receipt = root / "focused-receipt.json"
            receipt.write_text(json.dumps({
                "acceptedFactId": fact["id"], "changeKind": "updated",
            }) + "\n")
            output = root / "rebind-receipt.json"
            plan = knowledge / "construction-plans/uiability-backup-restore.json"
            MODULE.rebind_candidate(type("Args", (), {
                "knowledge": knowledge, "candidate_id": CANDIDATE_ID,
                "plan": plan, "focused_receipt": receipt,
                "evidence_root": ROOT, "output": output,
            }))
            result = json.loads(output.read_text())
            self.assertEqual(result["readinessDecision"], "blocked-qualification")
            self.assertEqual(result["nextGate"], "implement-and-calibrate-independent-oracle")
            self.assertEqual(result["addedEditablePaths"], [
                "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets",
            ])
            self.assertEqual(result["addedContextPaths"], [
                "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets",
            ])


if __name__ == "__main__":
    unittest.main()
