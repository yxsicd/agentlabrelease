from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


REVIEW = load_module(
    "multi_repo_candidate_semantic_review",
    ROOT / "scripts/review-multi-repo-candidate-semantics.py",
)


class MultiRepoCandidateSemanticReviewTests(unittest.TestCase):
    def packet(self, root: Path, schema: str = REVIEW.PACKET_SCHEMA) -> Path:
        question_ids = [
            "shared-behavior",
            "observable-gap",
            "prompt-completeness",
            "repair-oracle",
            "preservation-oracle",
            "environment",
            "cross-repo-necessity",
        ]
        risk_ids = [
            "api-name-is-not-semantics",
            "issue-contract-absent",
            "build-boundary-unqualified",
            "oracle-unqualified",
        ]
        path = root / "packet.json"
        value = {
            "schema": schema,
            "status": "independent-semantic-review-required",
            "candidateId": "difficulty-test",
            "candidateSha256": "a" * 64,
            "sourceSetSha256": "b" * 64,
            "packetMethodRevision": "1" * 40,
            "reviewQuestions": [
                {"id": question_id, "question": f"Question for {question_id}?"}
                for question_id in question_ids
            ],
            "risks": [
                {"id": risk_id, "statement": f"Risk for {risk_id}."}
                for risk_id in risk_ids
            ],
            "reviewDecisionContract": {
                "schema": REVIEW.DECISION_SCHEMA,
                "allowedVerdicts": sorted(REVIEW.VERDICTS),
                "requiredQuestionIds": question_ids,
                "requiredRiskIds": risk_ids,
                "reviewerMustBeIndependentOfPacketGenerator": True,
            },
            "automaticPromotion": False,
        }
        if schema in {
            REVIEW.PACKET_SCHEMA_V2,
            REVIEW.PACKET_SCHEMA_V3,
            REVIEW.PACKET_SCHEMA_V4,
        }:
            value["callResultHandleEvidence"] = [{
                "selectedCallFactId": "fact-call", "status": "unbound-result",
            }]
            value["callResultHandleCoverage"] = {
                "selectedCallCount": 1,
                "bindingInitializerCount": 0,
                "assignmentCount": 0,
                "unboundResultCount": 1,
                "ambiguousContainerCount": 0,
                "directMemberNameCounts": {},
            }
        if schema in {REVIEW.PACKET_SCHEMA_V3, REVIEW.PACKET_SCHEMA_V4}:
            value["callControlContextEvidence"] = [{
                "factId": "fact-call",
                "controlContext": {"resolution": "syntactic-ancestor-context"},
            }]
            value["callControlContextCoverage"] = {
                "selectedCallCount": 1,
                "awaitedCallCount": 0,
                "callbackNestedCallCount": 0,
                "controlRegionKindCounts": {},
            }
        if schema == REVIEW.PACKET_SCHEMA_V4:
            value["callCleanupPairingEvidence"] = [{
                "selectedCallFactId": "fact-call",
                "status": "no-direct-release",
                "releasePairings": [],
            }]
            value["callCleanupPairingCoverage"] = {
                "selectedCallCount": 1,
                "directReleaseCount": 0,
                "handleStatusCounts": {"no-direct-release": 1},
                "releaseRelationCounts": {},
            }
        if schema in {
            REVIEW.PACKET_SCHEMA_V5,
            REVIEW.PACKET_SCHEMA_V6,
            REVIEW.PACKET_SCHEMA_V7,
        }:
            value["domainIdentifierContract"] = {
                "normalizedIdentifier": "purchase-data",
                "tokens": ["purchase", "data"],
            }
            value["domainFactEvidence"] = [
                {"factId": "fact-a", "kind": "property", "repositoryId": "repo-a"},
                {"factId": "fact-b", "kind": "member-access", "repositoryId": "repo-b"},
            ]
            value["apiContract"] = None
            value["callSiteEvidence"] = None
            value["callResultHandleEvidence"] = None
            value["callResultHandleCoverage"] = None
        if schema in {REVIEW.PACKET_SCHEMA_V6, REVIEW.PACKET_SCHEMA_V7}:
            value["basePacket"] = {
                "schema": REVIEW.PACKET_SCHEMA_V5,
                "sha256": "c" * 64,
                "relativePath": "release/base.json",
                "packetMethodRevision": "1" * 40,
                "status": "independent-semantic-review-required",
                "domainIdentifierContract": {
                    "normalizedIdentifier": "purchase-data",
                    "tokens": ["purchase", "data"],
                },
                "domainFactCount": 2,
                "coveredRepositoryCount": 2,
            }
            value["evidenceAttachments"] = {
                "build-qualification": {
                    "schema": "agentlab.multi_repo_source_build_qualification.v1",
                    "sha256": "d" * 64,
                    "relativePath": "release/build.json",
                    "status": "partial-build-qualified-review-required",
                    "qualifiedRootCount": 1,
                    "failedRootCount": 2,
                    "sourceProjectBoundaryStatus": "partially-build-qualified",
                },
                "expression-fact-qualification": {
                    "schema": "agentlab.multi_repo_expression_fact_qualification.v1",
                    "sha256": "e" * 64,
                    "relativePath": "release/expression.json",
                    "status": "expression-facts-qualified-dataflow-unresolved",
                    "repositoryCount": 2,
                    "selectedExpressionFactCount": 4,
                },
                "bounded-expression-flow-proposal": {
                    "schema": "agentlab.bounded_expression_flow_proposal.v1",
                    "sha256": "f" * 64,
                    "relativePath": "release/flow.json",
                    "planSha256": "a" * 64,
                    "planRelativePath": "release/plan.json",
                    "status": "bounded-syntactic-flow-proposal-review-required",
                    "repositoryCount": 2,
                    "flowCount": 2,
                    "edgeCount": 5,
                    "sourceBridgeCount": 1,
                    "allBoundedPathsEstablished": True,
                },
            }
            value["semanticAlignmentVerified"] = False
            value["behaviorOracleVerified"] = False
            if schema == REVIEW.PACKET_SCHEMA_V7:
                value["evidenceAttachments"]["bounded-expression-flow-program-analysis"] = {
                    "schema": "agentlab.bounded_expression_flow_program_analysis.v1",
                    "sha256": "1" * 64,
                    "relativePath": "release/program-analysis.json",
                    "status": "bounded-program-flow-partially-resolved-review-required",
                    "flowProposalSha256": "f" * 64,
                    "flowReplayExact": True,
                    "repositoryCount": 2,
                    "flowCount": 2,
                    "localCallTargetCount": 3,
                    "typedParameterMappingCount": 2,
                    "untypedParameterMappingCount": 1,
                    "exactDependencyCount": 7,
                    "unresolvedCount": 6,
                }
            value["reviewDecisionContract"]["requiredEvidenceAttachmentIds"] = sorted(value["evidenceAttachments"])
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        return path

    def test_v2_handle_aware_packet_uses_the_same_fail_closed_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root, REVIEW.PACKET_SCHEMA_V2)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"observable-gap": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])

    def test_v3_control_context_packet_uses_the_same_fail_closed_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root, REVIEW.PACKET_SCHEMA_V3)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"repair-oracle": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])

    def test_v4_cleanup_pairing_packet_uses_the_same_fail_closed_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root, REVIEW.PACKET_SCHEMA_V4)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"observable-gap": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])

    def test_v5_domain_identifier_packet_uses_the_same_fail_closed_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root, REVIEW.PACKET_SCHEMA_V5)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"observable-gap": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])

    def test_v6_evidence_enriched_packet_uses_the_same_fail_closed_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root, REVIEW.PACKET_SCHEMA_V6)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"observable-gap": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])

    def test_v7_program_analyzed_packet_uses_the_same_fail_closed_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root, REVIEW.PACKET_SCHEMA_V7)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"observable-gap": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])

    def answers(self, root: Path, overrides: dict[str, str] | None = None) -> Path:
        overrides = overrides or {}
        packet = json.loads((root / "packet.json").read_text())
        path = root / f"answers-{len(list(root.glob('answers-*.json')))}.json"
        path.write_text(json.dumps({
            "schema": REVIEW.ANSWERS_SCHEMA,
            "responses": [
                {
                    "id": row["id"],
                    "answer": overrides.get(row["id"], "yes"),
                    "rationale": f"The retained evidence supports this answer for {row['id']}.",
                }
                for row in packet["reviewQuestions"]
            ],
        }, sort_keys=True) + "\n")
        return path

    def decide(self, root: Path, verdict: str, overrides: dict[str, str] | None = None):
        packet = root / "packet.json"
        risks = ",".join(
            row["id"] for row in json.loads(packet.read_text())["risks"]
        )
        return REVIEW.decide(
            packet,
            hashlib.sha256(packet.read_bytes()).hexdigest(),
            self.answers(root, overrides),
            "github:independent-reviewer",
            risks,
            verdict,
            "The exact call sites and source boundaries were inspected independently.",
        )

    def test_all_yes_answers_are_required_to_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root)
            decision_value = self.decide(root, "advance-to-case-contract")
            decision = root / "decision.json"
            decision.write_text(json.dumps(decision_value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "approved-for-case-contract-proposal")
            self.assertTrue(gate["allowsCaseContract"])
            self.assertFalse(gate["declaredRepresentative"])
            self.assertFalse(gate["automaticPromotion"])

            with self.assertRaisesRegex(REVIEW.SemanticReviewError, "every semantic answer"):
                self.decide(
                    root,
                    "advance-to-case-contract",
                    {"observable-gap": "unknown"},
                )

    def test_noncoherent_core_answer_must_reject_not_defer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.packet(root)
            decision = self.decide(
                root,
                "reject-as-noncoherent",
                {"shared-behavior": "no"},
            )
            self.assertFalse(decision["allowsCaseContract"])
            with self.assertRaisesRegex(REVIEW.SemanticReviewError, "must be rejected"):
                self.decide(
                    root,
                    "defer-for-more-evidence",
                    {"shared-behavior": "no", "environment": "unknown"},
                )

    def test_unknown_evidence_can_only_defer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root)
            value = self.decide(
                root,
                "defer-for-more-evidence",
                {"environment": "unknown"},
            )
            decision = root / "decision.json"
            decision.write_text(json.dumps(value, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(packet, decision)
            self.assertEqual(gate["status"], "deferred-for-more-evidence")
            self.assertFalse(gate["allowsCaseContract"])
            with self.assertRaisesRegex(REVIEW.SemanticReviewError, "at least one no"):
                self.decide(
                    root,
                    "reject-as-noncoherent",
                    {"environment": "unknown"},
                )

    def test_exact_answers_risks_identity_and_gate_bytes_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = self.packet(root)
            answers = json.loads(self.answers(root).read_text())
            answers["responses"].pop()
            incomplete = root / "incomplete.json"
            incomplete.write_text(json.dumps(answers) + "\n")
            packet_sha = hashlib.sha256(packet.read_bytes()).hexdigest()
            with self.assertRaisesRegex(REVIEW.SemanticReviewError, "every required question"):
                REVIEW.decide(
                    packet, packet_sha, incomplete, "github:reviewer", "api-name-is-not-semantics",
                    "advance-to-case-contract", "This rationale is sufficiently detailed for review.",
                )

            decision_value = self.decide(root, "advance-to-case-contract")
            decision = root / "decision.json"
            decision.write_text(json.dumps(decision_value, sort_keys=True) + "\n")
            gate_path = root / "gate.json"
            gate_path.write_text(json.dumps(REVIEW.compile_gate(packet, decision), sort_keys=True) + "\n")
            REVIEW.validate_gate(packet, decision, gate_path)
            tampered = json.loads(gate_path.read_text())
            tampered["allowsCaseContract"] = False
            gate_path.write_text(json.dumps(tampered) + "\n")
            with self.assertRaisesRegex(REVIEW.SemanticReviewError, "differs from exact"):
                REVIEW.validate_gate(packet, decision, gate_path)

    def test_workflow_binds_trusted_main_actor_and_preserves_all_inputs(self):
        workflow = (
            ROOT / ".github/workflows/multi-repo-candidate-semantic-review.yml"
        ).read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("REVIEWER: github:${{ github.actor }}", workflow)
        self.assertIn("review-multi-repo-candidate-semantics.py verify-evidence", workflow)
        self.assertIn("evidence-verification.json", workflow)
        self.assertIn("review-multi-repo-candidate-semantics.py decide", workflow)
        self.assertIn("review-multi-repo-candidate-semantics.py compile", workflow)
        self.assertIn("review-multi-repo-candidate-semantics.py validate", workflow)
        self.assertIn("multi-repo-candidate-semantic-review", workflow)
        self.assertIn("packet_run_id", workflow)
        self.assertIn(".github/workflows/multi-repo-candidate-review-packet.yml", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("supply exactly one of packet_path or packet_run_id", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
