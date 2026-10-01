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


IMPLEMENTATION_PATH = "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets"
ORACLE_PATH = "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets"


def latest_assessment(knowledge=KNOWLEDGE):
    values = []
    for path in (knowledge / "assessments").glob("*.json"):
        value = json.loads(path.read_text())
        values.append((value["roundIndex"], path))
    return max(values)[1]


def make_blocked_knowledge(target: Path) -> Path:
    """Create the pre-refresh state without depending on the live flywheel cut."""
    shutil.copytree(KNOWLEDGE, target)
    facts_path = target / "program_facts.jsonl"
    facts = MODULE.READINESS.rows(facts_path)
    fact = next(row for row in facts if row["id"] == "agent-analysis-uiability-backup-restore-state-recovery")
    fact["evidence"] = [row for row in fact["evidence"] if row["path"] not in {IMPLEMENTATION_PATH, ORACLE_PATH}]
    facts_path.write_bytes(b"".join(
        MODULE.READINESS.canonical(row) + b"\n" for row in sorted(facts, key=lambda row: row["id"])
    ))
    candidates_path = target / "case_generation_candidates.jsonl"
    candidates = MODULE.READINESS.rows(candidates_path)
    candidate = next(row for row in candidates if row["id"] == CANDIDATE_ID)
    candidate["editablePaths"] = [path for path in candidate["editablePaths"] if path != IMPLEMENTATION_PATH]
    candidate["contextPaths"] = [path for path in candidate["contextPaths"] if path != ORACLE_PATH]
    candidates_path.write_bytes(b"".join(
        MODULE.READINESS.canonical(row) + b"\n" for row in sorted(candidates, key=lambda row: row["id"])
    ))
    plan_path = target / "construction-plans/uiability-backup-restore.json"
    plan = json.loads(plan_path.read_text())
    plan["candidateSha256"] = MODULE.READINESS.value_digest(candidate)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return target


class FocusedFactRefreshTest(unittest.TestCase):
    def prepare_request(self, output: Path, knowledge=KNOWLEDGE):
        MODULE.prepare(type("Args", (), {
            "knowledge": knowledge,
            "assessment": latest_assessment(knowledge),
            "candidate_id": CANDIDATE_ID,
            "plan": knowledge / "construction-plans/uiability-backup-restore.json",
            "evidence_root": ROOT,
            "output": output,
        }))
        return json.loads(output.read_text())

    def test_prepare_consumes_exact_blocked_candidate_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            knowledge = make_blocked_knowledge(root / "knowledge")
            output = root / "request.json"
            request = self.prepare_request(output, knowledge)
            self.assertEqual(request["readinessDecision"], "blocked-knowledge-refresh")
            self.assertEqual(request["requiredDimensions"], request["existingFact"]["dimensions"])
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
            "limitationIndices": [],
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

    def test_limitation_length_repair_preserves_valid_sibling_and_source_evidence(self):
        before = {key: key for key in MODULE.PROPOSAL_FIELDS}
        before.update(interpretation="x" * 500, limitations=["a" * 314, "b" * 143])
        plan = MODULE.proposal_repair_plan(before)
        self.assertEqual(plan["limitationIndices"], [0])
        after = {**before, "limitations": ["a" * 250, before["limitations"][1]]}
        self.assertEqual(MODULE.validate_bounded_repair(before, after, plan), 500)
        for key in ("evidence", "sourceRevision", "dimensions", "interpretation"):
            with self.assertRaisesRegex(ValueError, "protected field"):
                MODULE.validate_bounded_repair(before, {**after, key: "changed"}, plan)
        with self.assertRaisesRegex(ValueError, "protected limitation"):
            MODULE.validate_bounded_repair(before, {**after, "limitations": ["a" * 250, "c" * 143]}, plan)
        with self.assertRaisesRegex(ValueError, "length range"):
            MODULE.validate_bounded_repair(before, {**after, "limitations": ["a" * 301, "b" * 143]}, plan)

    def test_malformed_limitations_are_not_length_repaired(self):
        for values in (None, ["x"], ["x", 0], ["x", "y", "z"]):
            self.assertEqual(MODULE.proposal_repair_plan({"limitations": values})["limitationIndices"], [])

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
            knowledge = make_blocked_knowledge(root / "knowledge")
            request_path = root / "request.json"
            request = self.prepare_request(request_path, knowledge)
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
                    "program_facts": knowledge / "program_facts.jsonl",
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
            knowledge = make_blocked_knowledge(root / "knowledge")
            facts_path = knowledge / "program_facts.jsonl"
            facts = MODULE.READINESS.rows(facts_path)
            fact = next(row for row in facts if row["id"] == "agent-analysis-uiability-backup-restore-state-recovery")
            existing_paths = {row["path"] for row in fact["evidence"]}
            for path in (
                IMPLEMENTATION_PATH,
                ORACLE_PATH,
            ):
                if path not in existing_paths:
                    fact["evidence"].append({"path": path, "gitBlobOid": "1" * 40})
            facts_path.write_bytes(b"".join(
                MODULE.READINESS.canonical(row) + b"\n" for row in sorted(facts, key=lambda row: row["id"])
            ))
            cut_path = knowledge / "maintainer-knowledge-cut.json"
            cut = json.loads(cut_path.read_text())
            cut["tableGitAuthority"]["revision"] = "f" * 40
            cut["tables"]["programFacts"]["sha256"] = MODULE.BASE.digest(facts_path)
            cut_path.write_text(json.dumps(cut, sort_keys=True) + "\n")
            receipt = root / "focused-receipt.json"
            receipt.write_text(json.dumps({
                "acceptedFactId": fact["id"], "changeKind": "updated",
                "candidateId": CANDIDATE_ID,
                "acceptedFactSha256": MODULE.READINESS.value_digest(fact),
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
                IMPLEMENTATION_PATH,
            ])
            self.assertEqual(result["addedContextPaths"], [
                ORACLE_PATH,
            ])


if __name__ == "__main__":
    unittest.main()
