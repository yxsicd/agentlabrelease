import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "case_generation_shadow",
    ROOT / "examples/maintainer-knowledge-gate/case_generation_shadow.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
KNOWLEDGE = ROOT / "examples/maintainer-knowledge-gate/first-four"


class CaseGenerationShadowTest(unittest.TestCase):
    def request(self):
        cut = MODULE.load(KNOWLEDGE / "maintainer-knowledge-cut.json")
        scopes = {row["id"]: row for row in MODULE.rows(KNOWLEDGE / "maintainer_scope_skills.jsonl")}
        facts = [
            row for row in MODULE.rows(KNOWLEDGE / "program_facts.jsonl")
            if row["id"].startswith("agent-analysis-")
        ]
        fact = facts[-1]
        scope = scopes[fact["scopeSkillIds"][0]]
        repository = next(row for row in cut["repositories"] if row["id"] == fact["repositoryId"])
        latest = max(MODULE.rows(KNOWLEDGE / "maintainer_skill_refresh_rounds.jsonl"),
                     key=lambda row: row["roundIndex"])
        return {
            "schema": "agentlab.case_generation_shadow_request.v1",
            "automaticPromotion": False,
            "sourceSetSha256": cut["sourceSetSha256"],
            "knowledgeCutSha256": "1" * 64,
            "maintainerSkillRefreshRoundId": latest["id"],
            "loopReceiptSha256": "2" * 64,
            "loopBefore": {
                "scopeSkillCount": 480, "programBoundCount": 18,
                "semanticReadyCount": 11, "maintenanceReadyCount": 2,
            },
            "loopAfter": {
                "scopeSkillCount": 480, "programBoundCount": 19,
                "semanticReadyCount": 12, "maintenanceReadyCount": 2,
            },
            "repository": repository,
            "scope": scope,
            "fact": fact,
            "candidateId": f"shadow-case-{fact['id'].removeprefix('agent-analysis-')}",
            "policy": {
                "candidateLimit": 1, "constructionMode": "shadow",
                "candidateGateRequired": True, "independentOracleRequired": True,
                "wrongVariantCalibrationRequired": True,
            },
            "output": "shadow-case-proposal.json",
        }

    def proposal(self, request):
        fact = request["fact"]
        scope = request["scope"]
        inside = [
            row["path"] for row in fact["evidence"]
            if MODULE.path_is_within(row["path"], scope["pathBoundary"])
        ]
        outside = [row["path"] for row in fact["evidence"] if row["path"] not in inside]
        framework = "ohosTest" if any("ohosTest" in path for path in scope.get("testEntrypoints", [])) else "repository-test"
        return {
            "schema": "agentlab.shadow_case_candidate.v1",
            "id": request["candidateId"],
            "repositoryId": fact["repositoryId"],
            "sourceRevision": fact["sourceRevision"],
            "scopeSkillIds": fact["scopeSkillIds"],
            "factIds": [fact["id"]],
            "title": "Preserve the bounded state transition contract",
            "mechanism": "Change the bounded implementation while preserving its cross-file state transition and make a later requirement expose an earlier shortcut in the selected mechanism.",
            "stagedDemands": [
                "Implement the bounded behavior without changing unrelated source.",
                "Extend the behavior while preserving the first-stage state transition.",
            ],
            "editablePaths": [inside[0]],
            "contextPaths": outside[:1],
            "oracleHypothesis": {
                "framework": framework,
                "observables": ["the first-stage state is preserved", "the second-stage transition is observable"],
                "requiredEnvironment": ["the exact pinned repository test environment"],
                "wrongVariants": ["drop the first-stage state", "apply the second-stage rule unconditionally"],
                "status": "hypothesis-unqualified",
            },
            "limitations": ["the Oracle has not executed", "the wrong variants have not been calibrated"],
            "status": "shadow-proposal",
            "automaticPromotion": False,
        }

    def test_prepare_binds_one_exported_loop_gain_to_the_exact_cut(self):
        request_fixture = self.request()
        fact = request_fixture["fact"]
        iteration = {
            "iteration": 1,
            "repository": fact["repositoryId"],
            "scope": fact["scopeSkillIds"][0],
            "acceptedFactId": fact["id"],
            "before": request_fixture["loopBefore"],
            "after": request_fixture["loopAfter"],
            "automaticPromotion": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loop_path = root / "loop-receipt.json"
            output = root / "request.json"
            MODULE.write_json(loop_path, {
                "schema": "agentlab.maintainer_skill_bounded_loop_receipt.v1",
                "requestedIterations": 1,
                "completedIterations": 1,
                "automaticPromotion": False,
                "iterations": [iteration],
            })
            MODULE.prepare(type("Args", (), {
                "knowledge": KNOWLEDGE, "loop_receipt": loop_path, "output": output,
            }))
            prepared = MODULE.load(output)
            self.assertEqual(prepared["fact"]["id"], fact["id"])
            self.assertEqual(
                prepared["candidateId"],
                f"shadow-case-{fact['id'].removeprefix('agent-analysis-')}",
            )
            self.assertEqual(prepared["scope"]["id"], fact["scopeSkillIds"][0])
            self.assertEqual(
                prepared["knowledgeCutSha256"],
                MODULE.file_digest(KNOWLEDGE / "maintainer-knowledge-cut.json"),
            )
            self.assertFalse(prepared["automaticPromotion"])

    def test_retained_shadow_candidate_and_round_are_exactly_bound(self):
        request = self.request()
        proposal = self.proposal(request)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            proposal_path = root / "proposal.json"
            rounds_path = root / "rounds.jsonl"
            candidates_path = root / "candidates.jsonl"
            receipt_path = root / "receipt.json"
            MODULE.write_json(request_path, request)
            MODULE.write_json(proposal_path, proposal)
            rounds_path.write_text((KNOWLEDGE / "case_generation_rounds.jsonl").read_text())
            MODULE.record_success(type("Args", (), {
                "request": request_path, "proposal": proposal_path,
                "rounds": rounds_path, "candidates": candidates_path,
                "receipt": receipt_path, "run_id": "42",
            }))
            candidate = MODULE.rows(candidates_path)[0]
            round_row = MODULE.rows(rounds_path)[-1]
            schema = json.loads((ROOT / "schemas/shadow-case-candidate.schema.json").read_text())
            self.assertEqual(set(candidate), set(schema["required"]))
            self.assertRegex(candidate["id"], schema["properties"]["id"]["pattern"])
            self.assertEqual(candidate["schema"], schema["properties"]["schema"]["const"])
            self.assertEqual(candidate["knowledgeCutSha256"], request["knowledgeCutSha256"])
            self.assertEqual(round_row["candidates"]["retainedIds"], [candidate["id"]])
            self.assertEqual(round_row["coverage"]["behaviorReadyBefore"], 11)
            self.assertEqual(round_row["coverage"]["behaviorReadyAfter"], 12)
            self.assertEqual(round_row["coverage"]["oracleReadyAfter"], 0)
            self.assertFalse(round_row["automaticPromotion"])

    def test_invalid_shadow_proposal_becomes_feedback_without_blocking_knowledge(self):
        request = self.request()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            rounds_path = root / "rounds.jsonl"
            receipt_path = root / "receipt.json"
            MODULE.write_json(request_path, request)
            rounds_path.write_text((KNOWLEDGE / "case_generation_rounds.jsonl").read_text())
            MODULE.record_failure(type("Args", (), {
                "request": request_path, "rounds": rounds_path,
                "receipt": receipt_path, "run_id": "43",
                "reason": "shadow-proposal-hard-gate-rejected",
            }))
            round_row = MODULE.rows(rounds_path)[-1]
            self.assertEqual(round_row["candidates"]["retainedIds"], [])
            self.assertEqual(
                round_row["candidates"]["rejected"][0]["reason"],
                "shadow-proposal-hard-gate-rejected",
            )
            self.assertEqual(MODULE.load(receipt_path)["status"], "rejected-shadow-attempt")

    def test_validator_rejects_editable_path_outside_scope(self):
        request = self.request()
        proposal = self.proposal(request)
        evidence_paths = [row["path"] for row in request["fact"]["evidence"]]
        outside = next(
            (path for path in evidence_paths if not MODULE.path_is_within(path, request["scope"]["pathBoundary"])),
            None,
        )
        if outside is None:
            self.skipTest("selected fixture has no cross-boundary evidence")
        proposal["editablePaths"] = [outside]
        proposal["contextPaths"] = []
        with self.assertRaisesRegex(ValueError, "escapes"):
            MODULE.validate_proposal(request, proposal)


if __name__ == "__main__":
    unittest.main()
