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


ENRICH = load_module(
    "multi_repo_candidate_review_packet_enrichment",
    ROOT / "scripts/enrich-multi-repo-candidate-review-packet.py",
)
REVIEW = load_module(
    "multi_repo_candidate_semantic_review_for_enrichment",
    ROOT / "scripts/review-multi-repo-candidate-semantics.py",
)


class MultiRepoCandidateReviewPacketEnrichmentTests(unittest.TestCase):
    def fixture(self, root: Path):
        candidate_id = "difficulty-test"
        source_set = "a" * 64
        base = root / "base.json"
        base.write_text(json.dumps({
            "schema": ENRICH.BASE_SCHEMA,
            "status": "independent-semantic-review-required",
            "candidateId": candidate_id,
            "candidateSha256": "f" * 64,
            "sourceSetSha256": source_set,
            "packetMethodRevision": "1" * 40,
            "domainIdentifierContract": {"normalizedIdentifier": "purchase-data", "tokens": ["purchase", "data"]},
            "domainFactEvidence": [{"repositoryId": "a"}, {"repositoryId": "b"}],
            "allowsCaseContract": False,
            "automaticPromotion": False,
        }) + "\n")
        base_sha = hashlib.sha256(base.read_bytes()).hexdigest()
        build = root / "build.json"
        build.write_text(json.dumps({
            "schema": ENRICH.BUILD_SCHEMA,
            "status": "partial-build-qualified-review-required",
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
            "reviewPacketSha256": base_sha,
            "environment": {"environmentIdentity": "fixture:x86_64"},
            "roots": [{"status": "passed"}, {"status": "failed"}, {"status": "failed"}],
            "interpretation": {"qualifiedRootCount": 1, "failedRootCount": 2, "sourceProjectBoundaryStatus": "partially-build-qualified"},
            "allowsCaseContract": False,
            "automaticPromotion": False,
        }) + "\n")
        expression = root / "expression.json"
        expression.write_text(json.dumps({
            "schema": ENRICH.EXPRESSION_SCHEMA,
            "status": "expression-facts-qualified-dataflow-unresolved",
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
            "reviewPacketSha256": base_sha,
            "analyzerDigest": "b" * 64,
            "grammarDigest": "c" * 64,
            "repositoryCount": 2,
            "selectedExpressionFactCount": 3,
            "semanticAlignmentVerified": False,
            "allowsCaseContract": False,
            "automaticPromotion": False,
        }) + "\n")
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "schema": "agentlab.bounded_expression_flow_plan.v1",
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
        }) + "\n")
        flow = root / "flow.json"
        flow.write_text(json.dumps({
            "schema": ENRICH.FLOW_SCHEMA,
            "status": "bounded-syntactic-flow-proposal-review-required",
            "candidateId": candidate_id,
            "sourceSetSha256": source_set,
            "reviewPacketSha256": base_sha,
            "planSha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
            "repositoryCount": 2,
            "flowCount": 2,
            "allBoundedPathsEstablished": True,
            "sourceBridges": [{"path": "fixture.html"}],
            "flows": [{"edgeCount": 2}, {"edgeCount": 3}],
            "semanticAlignmentVerified": False,
            "behaviorOracleVerified": False,
            "allowsCaseContract": False,
            "automaticPromotion": False,
        }) + "\n")
        return base, build, expression, plan, flow

    def test_later_exact_evidence_is_bound_without_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            value = ENRICH.enrich(*paths, "2" * 40, Path(directory))
            self.assertEqual(value["schema"], ENRICH.SCHEMA)
            self.assertEqual(len(value["evidenceAttachments"]), 3)
            self.assertEqual(value["basePacket"]["domainFactCount"], 2)
            self.assertEqual(value["evidenceAttachments"]["bounded-expression-flow-proposal"]["edgeCount"], 5)
            self.assertEqual(value["risks"][0]["id"], "syntactic-flow-is-not-semantics")
            self.assertFalse(value["semanticAlignmentVerified"])
            self.assertFalse(value["behaviorOracleVerified"])
            self.assertFalse(value["allowsCaseContract"])
            self.assertFalse(value["automaticPromotion"])

    def test_changed_flow_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            paths[3].write_text(paths[3].read_text() + "\n")
            with self.assertRaisesRegex(ENRICH.PacketEnrichmentError, "flow plan digest differs"):
                ENRICH.enrich(*paths, "2" * 40, Path(directory))

    def test_changed_base_packet_is_rejected_by_every_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            base = json.loads(paths[0].read_text())
            base["candidateId"] = "difficulty-changed"
            paths[0].write_text(json.dumps(base) + "\n")
            with self.assertRaisesRegex(ENRICH.PacketEnrichmentError, "candidate differs"):
                ENRICH.enrich(*paths, "2" * 40, Path(directory))

    def test_review_replays_every_referenced_file_before_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.fixture(root)
            packet = root / "packet-v6.json"
            packet.write_text(json.dumps(ENRICH.enrich(*paths, "2" * 40, root), sort_keys=True) + "\n")
            receipt = REVIEW.verify_evidence(packet, root)
            self.assertEqual(receipt["status"], "verified-exact-v6-evidence")
            self.assertEqual(len(receipt["verifiedFiles"]), 5)
            paths[1].write_text(paths[1].read_text() + "\n")
            with self.assertRaisesRegex(REVIEW.SemanticReviewError, "build-qualification digest differs"):
                REVIEW.verify_evidence(packet, root)

    def test_program_analysis_produces_v7_and_is_replayed_before_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.fixture(root)
            base_sha = hashlib.sha256(paths[0].read_bytes()).hexdigest()
            flow_sha = hashlib.sha256(paths[4].read_bytes()).hexdigest()
            program = root / "program-analysis.json"
            program.write_text(json.dumps({
                "schema": ENRICH.PROGRAM_ANALYSIS_SCHEMA,
                "status": "bounded-program-flow-partially-resolved-review-required",
                "candidateId": "difficulty-test",
                "sourceSetSha256": "a" * 64,
                "reviewPacketSha256": base_sha,
                "flowPlanSha256": hashlib.sha256(paths[3].read_bytes()).hexdigest(),
                "flowProposalSha256": flow_sha,
                "flowReplayExact": True,
                "repositoryCount": 2,
                "flowCount": 2,
                "coverage": {
                    "localCallTargetCount": 3,
                    "localCallTargetsUniquelyResolved": True,
                    "typedParameterMappingCount": 2,
                    "untypedParameterMappingCount": 1,
                    "exactDependencyCount": 7,
                    "exactDependencyReferencesVerified": True,
                },
                "unresolvedCount": 6,
                "typeResolutionComplete": False,
                "aliasResolutionComplete": False,
                "externalCallContractsResolved": False,
                "reachabilityAndDominanceResolved": False,
                "semanticAlignmentVerified": False,
                "behaviorOracleVerified": False,
                "allowsCaseContract": False,
                "automaticPromotion": False,
            }) + "\n")
            packet = root / "packet-v7.json"
            packet.write_text(
                json.dumps(
                    ENRICH.enrich(*paths, "2" * 40, root, program),
                    sort_keys=True,
                )
                + "\n"
            )
            value = json.loads(packet.read_text())
            self.assertEqual(value["schema"], ENRICH.SCHEMA_V7)
            self.assertEqual(len(value["evidenceAttachments"]), 4)
            self.assertEqual(
                value["risks"][0]["id"],
                "partial-program-flow-is-not-semantics",
            )
            receipt = REVIEW.verify_evidence(packet, root)
            self.assertEqual(receipt["status"], "verified-exact-v7-evidence")
            self.assertEqual(len(receipt["verifiedFiles"]), 6)
            program_value = json.loads(program.read_text())
            program_value["unresolvedCount"] = 0
            program.write_text(json.dumps(program_value) + "\n")
            with self.assertRaisesRegex(
                REVIEW.SemanticReviewError,
                "bounded-expression-flow-program-analysis digest differs",
            ):
                REVIEW.verify_evidence(packet, root)


if __name__ == "__main__":
    unittest.main()
