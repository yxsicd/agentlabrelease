from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PACKET = load_module(
    "multi_repo_candidate_review_packet",
    ROOT / "scripts/build-multi-repo-candidate-review-packet.py",
)


class MultiRepoCandidateReviewPacketTests(unittest.TestCase):
    def git_repository(self, root: Path, repository_id: str, body: str) -> tuple[Path, str]:
        repository = root / repository_id
        (repository / "project/src").mkdir(parents=True)
        (repository / "project/build-profile.json5").write_text("{}\n")
        (repository / "project/hvigorfile.ts").write_text("export default {}\n")
        (repository / "project/oh-package.json5").write_text("{}\n")
        (repository / "project/src/page.ets").write_text(body)
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(
            [
                "git", "-C", str(repository), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture",
            ],
            check=True,
        )
        revision = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
        ).strip()
        return repository, revision

    def fixture(self, root: Path):
        repo_a, rev_a = self.git_repository(
            root, "repo-a", "import { api } from '@kit/Test';\napi.run('a');\n",
        )
        repo_b, rev_b = self.git_repository(
            root, "repo-b", "import { api } from '@kit/Test';\napi.run('b');\n",
        )
        sources = [
            {"id": "repo-a", "repository": "https://example.invalid/a.git", "revision": rev_a},
            {"id": "repo-b", "repository": "https://example.invalid/b.git", "revision": rev_b},
        ]
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "schema": "agentlab.multi_repo_manifest.v1",
            "moduleBindings": {},
            "repositories": [
                {**sources[0], "root": str(repo_a)},
                {**sources[1], "root": str(repo_b)},
            ],
        }, sort_keys=True) + "\n")
        facts = []
        for suffix, repository_id, repository, revision in (
            ("a", "repo-a", "a", rev_a), ("b", "repo-b", "b", rev_b),
        ):
            body = "import { api } from '@kit/Test';\napi.run('" + suffix + "');\n"
            facts.append({
                "id": f"fact-call-{suffix}",
                "kind": "call",
                "repositoryId": repository_id,
                "path": "project/src/page.ets",
                "owner": f"Owner{suffix.upper()}",
                "targetExpression": "api.run",
                "sourceIdentity": f"git:https://example.invalid/{repository}.git@{revision}",
                "span": {"startLine": 1, "endLine": 1, "startByte": 38, "endByte": 51},
            })
            facts.append({
                "id": f"fact-owner-{suffix}",
                "kind": "symbol",
                "repositoryId": repository_id,
                "path": "project/src/page.ets",
                "owner": None,
                "qualifiedName": f"Owner{suffix.upper()}",
                "symbol": f"Owner{suffix.upper()}",
                "sourceIdentity": f"git:https://example.invalid/{repository}.git@{revision}",
                "span": {
                    "startLine": 0,
                    "endLine": 1,
                    "startByte": 0,
                    "endByte": len(body.encode()),
                },
            })
        facts_path = root / "facts.jsonl"
        facts_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in facts))
        candidate = {
            "id": "difficulty-test",
            "schema": "agentlab.difficulty_point.v1",
            "dimensionId": "multi-repository-change-impact",
            "relationType": "shared-external-api-call-contract",
            "status": "candidate",
            "maturityState": "candidate",
            "mechanism": "same external API call target is observed across repository boundaries",
            "seed": {"specifier": "@kit/Test", "exportedSymbol": "api", "callTarget": "api.run"},
            "affectedFiles": [
                {"repositoryId": "repo-a", "path": "project/src/page.ets", "dependencyDepth": 1},
                {"repositoryId": "repo-b", "path": "project/src/page.ets", "dependencyDepth": 1},
            ],
            "affectedRepositoryCount": 2,
            "maxDependencyDepth": 1,
            "evidenceIds": ["fact-call-a", "fact-call-b", "fact-owner-a", "fact-owner-b"],
            "verificationContract": {"caseReady": False, "required": ["semantic review"]},
            "automaticPromotion": False,
        }
        difficulty = root / "difficulty.json"
        difficulty.write_text(json.dumps({
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": "a" * 64,
            "sources": sources,
            "moduleBindings": {},
            "candidates": [candidate],
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        proposal = root / "proposal.json"
        proposal.write_text(json.dumps({
            "schema": "agentlab.real_multi_repo_current_method_proposal.v1",
            "sourceSetSha256": "a" * 64,
            "analysisRunSha256": "b" * 64,
            "proposalMethodRevision": "2" * 40,
            "difficultyEvidenceSha256": hashlib.sha256(difficulty.read_bytes()).hexdigest(),
            "programFactsSha256": hashlib.sha256(facts_path.read_bytes()).hexdigest(),
            "proposedCandidates": [{
                "id": candidate["id"],
                "candidateSha256": PACKET.canonical_digest(candidate),
                "selectionRoles": ["minimum-api-call-file-count"],
            }],
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        return manifest, difficulty, facts_path, proposal, candidate

    def test_project_boundaries_recognize_cordova_and_npm_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cordova"
            (root / "plugin/example/src").mkdir(parents=True)
            (root / "plugin/package.json").write_text("{}\n")
            (root / "plugin/plugin.xml").write_text("<plugin/>\n")
            (root / "plugin/example/package.json").write_text("{}\n")
            (root / "plugin/example/tsconfig.json").write_text("{}\n")
            (root / "plugin/example/src/page.ts").write_text("export const value = 1;\n")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Test",
                    "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture",
                ],
                check=True,
            )
            revision = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(
                PACKET.project_boundaries(
                    {"root": root, "revision": revision},
                    "plugin/example/src/page.ts",
                ),
                [
                    {"path": "plugin", "markers": ["package.json", "plugin.xml"]},
                    {"path": "plugin/example", "markers": ["package.json", "tsconfig.json"]},
                ],
            )

    def live_lineage(self, root: Path, paths):
        manifest, difficulty, facts, _, candidate = paths
        fact_rows = [json.loads(line) for line in facts.read_text().splitlines() if line]
        for row in fact_rows:
            if row.get("kind") == "call":
                row["controlContext"] = {
                    "awaitAncestorCount": 0,
                    "callbackDepth": 0,
                    "controlRegions": [],
                    "enclosingCalls": [],
                    "resolution": "syntactic-ancestor-context",
                }
        facts.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in fact_rows))
        difficulty_value = json.loads(difficulty.read_text())
        second = json.loads(json.dumps(candidate))
        second["id"] = "difficulty-second"
        second["relationType"] = "shared-external-module-contract"
        difficulty_value["candidates"].append(second)
        difficulty.write_text(json.dumps(difficulty_value, sort_keys=True) + "\n")
        analysis_run = root / "analysis-run.json"
        analysis_run.write_text(json.dumps({
            "schema": "agentlab.multi_repo_analysis_run.v1",
            "methodRevision": "2" * 40,
            "sourceSetSha256": difficulty_value["sourceSetSha256"],
            "manifestSha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "difficultyEvidenceSha256": hashlib.sha256(difficulty.read_bytes()).hexdigest(),
            "programFactsSha256": hashlib.sha256(facts.read_bytes()).hexdigest(),
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        selected = []
        for row in difficulty_value["candidates"]:
            selected.append({
                "id": row["id"],
                "candidateSha256": PACKET.canonical_digest(row),
                "caseSource": {
                    "lane": "derived",
                    "strategy": "semantic-program-analysis",
                    "authority": "exact-difficulty-evidence",
                },
                "relationType": row["relationType"],
                "affectedRepositoryCount": row["affectedRepositoryCount"],
                "maxDependencyDepth": row["maxDependencyDepth"],
                "affectedFileCount": len(row["affectedFiles"]),
            })
        cohort = root / "cohort.json"
        cohort.write_text(json.dumps({
            "schema": "agentlab.multi_repo_candidate_cohort.v1",
            "cohortId": "cohort-live",
            "methodRevision": "2" * 40,
            "proposalMethodRevision": "5" * 40,
            "sourceSetSha256": difficulty_value["sourceSetSha256"],
            "difficultyEvidenceSha256": hashlib.sha256(difficulty.read_bytes()).hexdigest(),
            "samplingFrame": {"declaredRepresentative": False},
            "selectedCandidates": selected,
            "selectedCandidateCount": len(selected),
            "review": {
                "authority": "explicit-candidate-cohort-review",
                "reviewer": "github:reviewer",
                "proposalSha256": "6" * 64,
                "decisionSha256": "7" * 64,
                "verdict": "approve-for-independent-case-construction",
            },
            "declaredRepresentative": False,
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        selection = root / "selection.json"
        selection.write_text(json.dumps({
            "schema": "agentlab.multi_repo_candidate_selection.v2",
            "cohortId": "cohort-live",
            "cohortSha256": hashlib.sha256(cohort.read_bytes()).hexdigest(),
            "candidateId": candidate["id"],
            "candidateSha256": PACKET.canonical_digest(candidate),
            "caseSource": selected[0]["caseSource"],
            "sourceSetSha256": difficulty_value["sourceSetSha256"],
            "difficultyEvidenceSha256": hashlib.sha256(difficulty.read_bytes()).hexdigest(),
            "methodRevision": "2" * 40,
            "proposalMethodRevision": "5" * 40,
            "declaredRepresentative": False,
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        return analysis_run, cohort, selection

    def test_packet_binds_exact_sources_and_exposes_semantic_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            packet = PACKET.build_packet(*paths[:4], paths[4]["id"], "3" * 40, 0)
            self.assertEqual(packet["schema"], "agentlab.multi_repo_candidate_review_packet.v2")
            self.assertEqual(packet["status"], "independent-semantic-review-required")
            self.assertEqual(len(packet["callSiteEvidence"]), 2)
            self.assertEqual(
                {row["excerpt"][0]["text"] for row in packet["callSiteEvidence"]},
                {"api.run('a');", "api.run('b');"},
            )
            self.assertTrue(all(
                row["projectBoundaryCandidates"] == [{
                    "path": "project",
                    "markers": ["build-profile.json5", "hvigorfile.ts", "oh-package.json5"],
                }]
                for row in packet["callSiteEvidence"]
            ))
            self.assertEqual(packet["sourceProjectBoundary"]["status"], "review-required")
            self.assertEqual(packet["ownerEvidenceCoverage"]["ownerCount"], 2)
            self.assertEqual(packet["ownerEvidenceCoverage"]["completeOwnerCount"], 2)
            self.assertEqual(packet["ownerEvidenceCoverage"]["boundedExcerptOwnerCount"], 0)
            self.assertEqual(packet["ownerEvidenceCoverage"]["unresolvedOwnerCount"], 0)
            self.assertTrue(all(row["status"] == "complete" for row in packet["ownerContextEvidence"]))
            self.assertEqual(
                {row["callFacts"][0]["targetExpression"] for row in packet["ownerContextEvidence"]},
                {"api.run"},
            )
            self.assertEqual(
                packet["sweStyleTaskContract"]["satisfiedByThisPacket"],
                [
                    "exact base source set",
                    "source-localized call evidence",
                    "owner-scoped call-neighborhood evidence",
                ],
            )
            self.assertEqual(packet["callResultHandleCoverage"]["selectedCallCount"], 2)
            self.assertEqual(packet["callResultHandleCoverage"]["unboundResultCount"], 2)
            self.assertFalse(packet["automaticPromotion"])

    def test_v5_packet_binds_shortlisted_domain_identifier_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body_a = "export interface Receipt {\n  purchaseData: string;\n}\n"
            body_b = "export function finish(order: Receipt) {\n  return order.purchaseData;\n}"
            repo_a, rev_a = self.git_repository(root, "repo-a", body_a)
            repo_b, rev_b = self.git_repository(root, "repo-b", body_b)
            sources = [
                {"id": "repo-a", "repository": "https://example.invalid/a.git", "revision": rev_a},
                {"id": "repo-b", "repository": "https://example.invalid/b.git", "revision": rev_b},
            ]
            manifest = root / "manifest-domain.json"
            manifest.write_text(json.dumps({
                "schema": "agentlab.multi_repo_manifest.v1",
                "moduleBindings": {},
                "repositories": [
                    {**sources[0], "root": str(repo_a)},
                    {**sources[1], "root": str(repo_b)},
                ],
            }, sort_keys=True) + "\n")
            facts = [
                {
                    "id": "fact-property-a", "kind": "property", "repositoryId": "repo-a",
                    "path": "project/src/page.ets", "owner": "Receipt", "name": "purchaseData",
                    "typeExpression": "string", "sourceIdentity": f"git:https://example.invalid/a.git@{rev_a}",
                    "span": {"startLine": 1, "endLine": 1, "startByte": body_a.index("purchaseData"), "endByte": body_a.index("purchaseData") + len("purchaseData: string")},
                },
                {
                    "id": "fact-member-b", "kind": "member-access", "repositoryId": "repo-b",
                    "path": "project/src/page.ets", "owner": "finish", "property": "purchaseData",
                    "objectExpression": "order", "sourceIdentity": f"git:https://example.invalid/b.git@{rev_b}",
                    "span": {"startLine": 1, "endLine": 1, "startByte": body_b.index("order.purchaseData"), "endByte": body_b.index("order.purchaseData") + len("order.purchaseData")},
                },
                {
                    "id": "fact-owner-a", "kind": "symbol", "repositoryId": "repo-a",
                    "path": "project/src/page.ets", "qualifiedName": "Receipt", "symbol": "Receipt",
                    "sourceIdentity": f"git:https://example.invalid/a.git@{rev_a}",
                    "span": {"startLine": 0, "endLine": 2, "startByte": 0, "endByte": len(body_a.encode())},
                },
                {
                    "id": "fact-owner-b", "kind": "symbol", "repositoryId": "repo-b",
                    "path": "project/src/page.ets", "qualifiedName": "finish", "symbol": "finish",
                    "sourceIdentity": f"git:https://example.invalid/b.git@{rev_b}",
                    "span": {"startLine": 0, "endLine": 3, "startByte": 0, "endByte": len(body_b.encode())},
                },
            ]
            facts_path = root / "domain-facts.jsonl"
            facts_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in facts))
            observations = [
                {
                    "factId": "fact-property-a", "factKind": "property", "identifier": "purchaseData",
                    "normalizedIdentifier": "purchase-data", "tokens": ["purchase", "data"],
                    "repositoryId": "repo-a", "path": "project/src/page.ets",
                },
                {
                    "factId": "fact-member-b", "factKind": "member-access", "identifier": "purchaseData",
                    "normalizedIdentifier": "purchase-data", "tokens": ["purchase", "data"],
                    "repositoryId": "repo-b", "path": "project/src/page.ets",
                },
            ]
            candidate = {
                "id": "difficulty-domain", "schema": "agentlab.difficulty_point.v1",
                "dimensionId": "multi-repository-change-impact",
                "relationType": "shared-domain-identifier-contract",
                "status": "candidate", "maturityState": "candidate",
                "mechanism": "same compound property identifier is observed in exact AST facts across repository boundaries",
                "seed": {"normalizedIdentifier": "purchase-data", "tokens": ["purchase", "data"]},
                "observations": observations,
                "affectedFiles": [
                    {"repositoryId": "repo-a", "path": "project/src/page.ets", "dependencyDepth": 1},
                    {"repositoryId": "repo-b", "path": "project/src/page.ets", "dependencyDepth": 1},
                ],
                "affectedRepositoryCount": 2, "maxDependencyDepth": 1,
                "evidenceIds": ["fact-property-a", "fact-member-b"],
                "verificationContract": {"caseReady": False, "required": ["semantic review"]},
                "automaticPromotion": False,
            }
            difficulty = root / "domain-difficulty.json"
            difficulty.write_text(json.dumps({
                "schema": "agentlab.difficulty_candidates.v2", "sourceSetSha256": "a" * 64,
                "sources": sources, "moduleBindings": {}, "candidates": [candidate],
                "automaticPromotion": False,
            }, sort_keys=True) + "\n")
            proposal = root / "feedback-proposal.json"
            proposal.write_text(json.dumps({
                "schema": "agentlab.feedback_analysis_cut_proposal.v1", "status": "review-required",
                "cutId": "feedback-cut-domain", "automaticPromotion": False,
                "nextAnalysis": {
                    "candidateId": candidate["id"], "sourceSetSha256": "a" * 64,
                    "difficultyEvidenceSha256": hashlib.sha256(difficulty.read_bytes()).hexdigest(),
                    "analysisReceiptSha256": "b" * 64, "methodRevision": "2" * 40,
                    "evidenceIds": candidate["evidenceIds"],
                    "verificationContract": candidate["verificationContract"],
                },
            }, sort_keys=True) + "\n")
            triage = root / "feedback-triage.json"
            triage.write_text(json.dumps({
                "schema": "agentlab.feedback_analysis_proposal_queue_triage.v1",
                "status": "one-proposal-shortlisted-review-required",
                "semanticAlignmentVerified": False, "automaticPromotion": False,
                "selectedProposal": {
                    "proposalSha256": hashlib.sha256(proposal.read_bytes()).hexdigest(),
                    "difficultyCandidateId": candidate["id"], "cutId": "feedback-cut-domain",
                },
            }, sort_keys=True) + "\n")
            packet = PACKET.build_packet(
                manifest, difficulty, facts_path, proposal, candidate["id"], "3" * 40,
                context_lines=0, feedback_triage_path=triage,
            )
            self.assertEqual(packet["schema"], "agentlab.multi_repo_candidate_review_packet.v5")
            self.assertEqual(packet["domainIdentifierContract"]["normalizedIdentifier"], "purchase-data")
            self.assertEqual(len(packet["domainFactEvidence"]), 2)
            self.assertEqual(
                {row["kind"] for row in packet["domainFactEvidence"]},
                {"property", "member-access"},
            )
            self.assertEqual(packet["ownerEvidenceCoverage"]["completeOwnerCount"], 2)
            self.assertIsNone(packet["callResultHandleEvidence"])
            self.assertEqual(packet["selectionRoles"], ["feedback-analysis-queue-shortlist"])
            self.assertEqual(
                packet["lineage"]["feedbackAnalysisTriageSha256"],
                hashlib.sha256(triage.read_bytes()).hexdigest(),
            )
            self.assertFalse(packet["automaticPromotion"])

    def test_call_result_handles_distinguish_binding_assignment_and_exact_receiver(self):
        calls = [
            {
                "id": "factory-binding", "kind": "call", "repositoryId": "repo-a",
                "path": "a.ets", "owner": "A::run", "targetExpression": "api.create",
                "span": {"startByte": 10, "endByte": 22},
            },
            {
                "id": "factory-assignment", "kind": "call", "repositoryId": "repo-b",
                "path": "b.ets", "owner": "B::run", "targetExpression": "api.create",
                "span": {"startByte": 40, "endByte": 52},
            },
        ]
        facts = [
            *calls,
            {
                "id": "binding", "kind": "binding", "repositoryId": "repo-a",
                "path": "a.ets", "owner": "A::run", "name": "handle",
                "initializerExpression": "api.create()",
                "span": {"startByte": 0, "endByte": 23},
            },
            {
                "id": "binding-release", "kind": "call", "repositoryId": "repo-a",
                "path": "a.ets", "owner": "A::run", "targetExpression": "handle.release",
                "span": {"startByte": 30, "endByte": 46},
            },
            {
                "id": "binding-lookalike", "kind": "call", "repositoryId": "repo-a",
                "path": "a.ets", "owner": "A::run", "targetExpression": "handle2.release",
                "span": {"startByte": 50, "endByte": 67},
            },
            {
                "id": "assignment", "kind": "assignment", "repositoryId": "repo-b",
                "path": "b.ets", "owner": "B::run", "leftExpression": "this.packer",
                "span": {"startByte": 25, "endByte": 53},
            },
            {
                "id": "assignment-use", "kind": "call", "repositoryId": "repo-b",
                "path": "b.ets", "owner": "B::run", "targetExpression": "this.packer.packToFile",
                "span": {"startByte": 60, "endByte": 82},
            },
        ]
        evidence, coverage = PACKET.call_result_handles(calls, facts)
        self.assertEqual(coverage["bindingInitializerCount"], 1)
        self.assertEqual(coverage["assignmentCount"], 1)
        self.assertEqual(coverage["unboundResultCount"], 0)
        self.assertEqual(coverage["directMemberNameCounts"], {"packToFile": 1, "release": 1})
        by_call = {row["selectedCallFactId"]: row for row in evidence}
        self.assertEqual(by_call["factory-binding"]["handleExpression"], "handle")
        self.assertEqual(
            [row["factId"] for row in by_call["factory-binding"]["directMemberCalls"]],
            ["binding-release"],
        )
        self.assertEqual(by_call["factory-assignment"]["handleExpression"], "this.packer")
        self.assertEqual(
            by_call["factory-assignment"]["directMemberCalls"][0]["member"],
            "packToFile",
        )

    def test_v4_packet_binds_supplemental_control_context_without_replacing_base_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            context_rows = []
            for line in paths[2].read_text().splitlines():
                row = json.loads(line)
                if row.get("kind") == "call":
                    row["controlContext"] = {
                        "awaitAncestorCount": 1,
                        "callbackDepth": 0,
                        "controlRegions": [{
                            "syntaxKind": "try_statement",
                            "span": row["span"],
                        }],
                        "enclosingCalls": [],
                        "resolution": "syntactic-ancestor-context",
                    }
                context_rows.append(row)
            context = Path(directory) / "context-facts.jsonl"
            context.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in context_rows)
            )
            packet = PACKET.build_packet(
                *paths[:4], paths[4]["id"], "3" * 40, 4, 240,
                context, "4" * 40,
            )
            self.assertEqual(packet["schema"], "agentlab.multi_repo_candidate_review_packet.v4")
            self.assertEqual(packet["callControlContextCoverage"]["selectedCallCount"], 2)
            self.assertEqual(packet["callControlContextCoverage"]["awaitedCallCount"], 2)
            self.assertEqual(
                packet["callControlContextCoverage"]["controlRegionKindCounts"],
                {"try_statement": 2},
            )
            self.assertEqual(
                packet["lineage"]["contextWorkspaceFactsSha256"],
                hashlib.sha256(context.read_bytes()).hexdigest(),
            )
            self.assertEqual(packet["lineage"]["contextMethodRevision"], "4" * 40)
            self.assertIn(
                "syntactic async and control-region evidence",
                packet["sweStyleTaskContract"]["satisfiedByThisPacket"],
            )
            self.assertEqual(
                packet["callCleanupPairingCoverage"]["handleStatusCounts"],
                {"no-direct-release": 2},
            )
            self.assertIn(
                "same-handle syntactic cleanup-pairing evidence",
                packet["sweStyleTaskContract"]["satisfiedByThisPacket"],
            )

    def test_cleanup_pairing_separates_finalizers_from_same_try_release(self):
        try_span = {"startByte": 20, "endByte": 120}
        factory_context = {
            "controlRegions": [{"syntaxKind": "try_statement", "span": try_span}],
            "enclosingCalls": [],
        }
        calls = [{
            "id": "factory", "kind": "call", "repositoryId": "repo-a",
            "path": "a.ets", "owner": "A::run", "targetExpression": "api.create",
            "span": {"startByte": 30, "endByte": 42},
            "controlContext": factory_context,
        }]
        handles = [{
            "selectedCallFactId": "factory", "repositoryId": "repo-a",
            "path": "a.ets", "owner": "A::run", "handleExpression": "handle",
            "sameHandleReassignments": [],
            "directMemberCalls": [
                {
                    "factId": "release-body", "member": "release",
                    "span": {"startByte": 60, "endByte": 76},
                    "controlContext": {
                        "controlRegions": [{"syntaxKind": "try_statement", "span": try_span}],
                        "enclosingCalls": [],
                    },
                },
                {
                    "factId": "release-finally", "member": "release",
                    "span": {"startByte": 100, "endByte": 116},
                    "controlContext": {
                        "controlRegions": [
                            {"syntaxKind": "finally_clause", "span": {"startByte": 90, "endByte": 120}},
                            {"syntaxKind": "try_statement", "span": try_span},
                        ],
                        "enclosingCalls": [],
                    },
                },
            ],
        }]
        evidence, coverage = PACKET.call_cleanup_pairings(calls, handles)
        self.assertEqual(evidence[0]["status"], "multiple-release-shapes")
        self.assertEqual(
            [row["relation"] for row in evidence[0]["releasePairings"]],
            ["same-try-non-finalizer", "matching-try-finally"],
        )
        self.assertEqual(coverage["directReleaseCount"], 2)
        self.assertEqual(coverage["releaseRelationCounts"], {
            "matching-try-finally": 1,
            "same-try-non-finalizer": 1,
        })

    def test_packet_rejects_candidate_drift_and_non_shortlisted_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, proposal, candidate = self.fixture(root)
            value = json.loads(difficulty.read_text())
            value["candidates"][0]["seed"]["callTarget"] = "api.changed"
            difficulty.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "difficulty evidence differs"):
                PACKET.build_packet(manifest, difficulty, facts, proposal, candidate["id"], "3" * 40)

            value["candidates"][0] = candidate
            difficulty.write_text(json.dumps(value, sort_keys=True) + "\n")
            proposal_value = json.loads(proposal.read_text())
            proposal_value["proposedCandidates"] = []
            proposal.write_text(json.dumps(proposal_value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "frozen review shortlist"):
                PACKET.build_packet(manifest, difficulty, facts, proposal, candidate["id"], "3" * 40)

    def test_packet_rejects_workspace_facts_not_bound_by_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            paths[2].write_text(paths[2].read_text() + "\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "workspace facts differ"):
                PACKET.build_packet(*paths[:4], paths[4]["id"], "3" * 40)

    def test_packet_lineage_binds_every_input(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            packet = PACKET.build_packet(*paths[:4], paths[4]["id"], "3" * 40)
            for key, path in zip(
                ("manifestSha256", "difficultyEvidenceSha256", "workspaceFactsSha256", "currentMethodProposalSha256"),
                paths[:4],
            ):
                self.assertEqual(packet["lineage"][key], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_live_reviewed_cohort_lineage_builds_a_context_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.fixture(root)
            analysis_run, cohort, selection = self.live_lineage(root, paths)
            materialized_manifest = root / "materialized-manifest.json"
            materialized_value = json.loads(paths[0].read_text())
            for repository in materialized_value["repositories"]:
                repository["root"] += "/"
            materialized_manifest.write_text(
                json.dumps(materialized_value, sort_keys=True) + "\n"
            )
            packet = PACKET.build_packet(
                materialized_manifest, paths[1], paths[2], None,
                paths[4]["id"], "3" * 40,
                context_facts_path=paths[2],
                context_method_revision="2" * 40,
                analysis_run_path=analysis_run,
                cohort_path=cohort,
                selection_path=selection,
                analysis_manifest_path=paths[0],
            )
            self.assertEqual(packet["schema"], "agentlab.multi_repo_candidate_review_packet.v4")
            self.assertEqual(packet["selectionRoles"], ["explicit-reviewed-cohort-member"])
            self.assertNotIn("currentMethodProposalSha256", packet["lineage"])
            self.assertNotEqual(
                packet["lineage"]["analysisManifestSha256"],
                packet["lineage"]["materializedManifestSha256"],
            )
            self.assertEqual(
                packet["lineage"]["analysisManifestSha256"],
                hashlib.sha256(paths[0].read_bytes()).hexdigest(),
            )
            self.assertEqual(
                packet["lineage"]["analysisRunSha256"],
                hashlib.sha256(analysis_run.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                packet["lineage"]["candidateCohortSha256"],
                hashlib.sha256(cohort.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                packet["lineage"]["candidateSelectionSha256"],
                hashlib.sha256(selection.read_bytes()).hexdigest(),
            )

    def test_live_lineage_rejects_fact_selection_and_cohort_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.fixture(root)
            analysis_run, cohort, selection = self.live_lineage(root, paths)
            facts_bytes = paths[2].read_bytes()
            paths[2].write_bytes(facts_bytes + b"\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "workspace facts differ from analysis run"):
                PACKET.build_packet(
                    paths[0], paths[1], paths[2], None, paths[4]["id"], "3" * 40,
                    analysis_run_path=analysis_run, cohort_path=cohort,
                    selection_path=selection, analysis_manifest_path=paths[0],
                )
            paths[2].write_bytes(facts_bytes)

            selection_value = json.loads(selection.read_text())
            selection_value["candidateSha256"] = "8" * 64
            selection.write_text(json.dumps(selection_value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "candidate digest differs from selection"):
                PACKET.build_packet(
                    paths[0], paths[1], paths[2], None, paths[4]["id"], "3" * 40,
                    analysis_run_path=analysis_run, cohort_path=cohort,
                    selection_path=selection, analysis_manifest_path=paths[0],
                )

            selection_value["candidateSha256"] = PACKET.canonical_digest(paths[4])
            selection.write_text(json.dumps(selection_value, sort_keys=True) + "\n")
            cohort_value = json.loads(cohort.read_text())
            cohort_value["review"]["verdict"] = "defer"
            cohort.write_text(json.dumps(cohort_value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "was not approved"):
                PACKET.build_packet(
                    paths[0], paths[1], paths[2], None, paths[4]["id"], "3" * 40,
                    analysis_run_path=analysis_run, cohort_path=cohort,
                    selection_path=selection, analysis_manifest_path=paths[0],
                )

    def test_packet_requires_one_complete_lineage_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "either a current-method proposal"):
                PACKET.build_packet(
                    paths[0], paths[1], paths[2], None, paths[4]["id"], "3" * 40,
                )
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "supplied together"):
                PACKET.build_packet(
                    paths[0], paths[1], paths[2], None, paths[4]["id"], "3" * 40,
                    analysis_run_path=Path(directory) / "missing.json",
                )

    def test_packet_fail_closes_when_owner_context_is_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            facts = [
                json.loads(line)
                for line in paths[2].read_text().splitlines()
                if line.strip()
            ]
            paths[2].write_text(
                "".join(
                    json.dumps(
                        {
                            **row,
                            **({"qualifiedName": "DifferentOwner"}
                               if row["id"] == "fact-owner-b" else {}),
                        },
                        sort_keys=True,
                    ) + "\n"
                    for row in facts
                )
            )
            proposal = json.loads(paths[3].read_text())
            proposal["programFactsSha256"] = hashlib.sha256(paths[2].read_bytes()).hexdigest()
            paths[3].write_text(json.dumps(proposal, sort_keys=True) + "\n")
            packet = PACKET.build_packet(*paths[:4], paths[4]["id"], "3" * 40)
            self.assertEqual(packet["ownerEvidenceCoverage"]["unresolvedOwnerCount"], 1)
            self.assertIn("owner-context-incomplete", {
                row["id"] for row in packet["risks"]
            })
            self.assertIn(
                "owner-context-incomplete",
                packet["reviewDecisionContract"]["requiredRiskIds"],
            )

    def test_retained_real_packets_are_exact_and_still_unqualified(self):
        root = ROOT / "release/qualifications/harmony-real-multi-repo-34661ff"
        index = json.loads((root / "review-packets/index.json").read_text())
        proposal_sha = hashlib.sha256((root / "current-method-proposal.json").read_bytes()).hexdigest()
        self.assertEqual(index["currentMethodProposalSha256"], proposal_sha)
        self.assertEqual(index["schema"], "agentlab.multi_repo_candidate_review_packet_index.v2")
        self.assertEqual(index["packetMethodRevisions"], [
            "5d730d1fbc7a6fa6eaee58fc4f7d580bb7a39469",
            "c3b4a662cdeefcaf9be811994236e55c770ce9fd",
        ])
        self.assertEqual(index["supplementalContextMethods"], [{
            "methodRevision": "f13c0439f5762a09ee32f4a2d02b6f074838187a",
            "workspaceFactsSha256": "b8745ea924235dc8c24390b06042668c502a1981fea70c52c8d6e8cdde1493e2",
        }])
        self.assertFalse(index["semanticReviewCompleted"])
        self.assertFalse(index["automaticPromotion"])
        self.assertEqual(len(index["packets"]), 3)
        for row in index["packets"]:
            path = root / "review-packets" / row["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            value = json.loads(path.read_text())
            self.assertEqual(value["candidateId"], row["candidateId"])
            self.assertEqual(value["status"], "independent-semantic-review-required")
            self.assertEqual(value["lineage"]["currentMethodProposalSha256"], proposal_sha)
            expected = ["exact base source set", "source-localized call evidence"]
            if row["path"] == "image-create-image-packer.json":
                expected.append("owner-scoped call-neighborhood evidence")
                expected.append("syntactic async and control-region evidence")
                expected.append("same-handle syntactic cleanup-pairing evidence")
            self.assertEqual(value["sweStyleTaskContract"]["satisfiedByThisPacket"], expected)
            self.assertFalse(value["automaticPromotion"])

        alert = json.loads((root / "review-packets/alert-dialog.json").read_text())
        calls = json.loads((root / "review-packets/call-make-call.json").read_text())
        image_packer = json.loads(
            (root / "review-packets/image-create-image-packer.json").read_text()
        )
        self.assertEqual(
            image_packer["schema"],
            "agentlab.multi_repo_candidate_review_packet.v4",
        )
        alert_source = "\n".join(
            line["text"] for site in alert["callSiteEvidence"] for line in site["excerpt"]
        )
        call_source = "\n".join(
            line["text"] for site in calls["callSiteEvidence"] for line in site["excerpt"]
        )
        self.assertIn("logoutDirect", alert_source)
        self.assertIn("handleConfirm", alert_source)
        self.assertIn("call.makeCall('',", call_source)
        self.assertIn("url.substring(6)", call_source)
        self.assertEqual(image_packer["ownerEvidenceCoverage"]["ownerCount"], 12)
        self.assertEqual(image_packer["ownerEvidenceCoverage"]["completeOwnerCount"], 12)
        self.assertEqual(image_packer["ownerEvidenceCoverage"]["boundedExcerptOwnerCount"], 0)
        self.assertEqual(image_packer["ownerEvidenceCoverage"]["unresolvedOwnerCount"], 0)
        self.assertEqual(
            image_packer["callResultHandleCoverage"],
            {
                "selectedCallCount": 12,
                "bindingInitializerCount": 10,
                "assignmentCount": 2,
                "unboundResultCount": 0,
                "ambiguousContainerCount": 0,
                "directMemberNameCounts": {
                    "packToData": 6,
                    "packToFile": 5,
                    "packing": 1,
                    "release": 6,
                },
                "interpretation": (
                    "Containment can associate a selected call with one lexical binding or assignment and "
                    "enumerate exact direct-member call spellings on that handle. It does not prove aliases, "
                    "escapes, receiver types, control-flow coverage, exception safety or runtime release."
                ),
            },
        )
        release_owners = sum(
            any(
                (call.get("targetExpression") or "").endswith(".release")
                for call in owner["callFacts"]
            )
            for owner in image_packer["ownerContextEvidence"]
        )
        self.assertEqual(release_owners, 6)
        self.assertEqual(image_packer["callControlContextCoverage"], {
            "selectedCallCount": 12,
            "awaitedCallCount": 0,
            "callbackNestedCallCount": 2,
            "controlRegionKindCounts": {
                "arrow_function": 2,
                "if_statement": 5,
                "try_statement": 5,
            },
            "interpretation": (
                "Ancestor syntax identifies lexical await, callback and control regions only. It does not "
                "prove reachability, branch coverage, dominance, post-dominance or exception-safe cleanup."
            ),
        })
        self.assertEqual(
            image_packer["lineage"]["contextWorkspaceFactsSha256"],
            "b8745ea924235dc8c24390b06042668c502a1981fea70c52c8d6e8cdde1493e2",
        )
        self.assertEqual(
            image_packer["lineage"]["contextMethodRevision"],
            "f13c0439f5762a09ee32f4a2d02b6f074838187a",
        )
        release_calls = [
            call
            for handle in image_packer["callResultHandleEvidence"]
            for call in handle["directMemberCalls"]
            if call["member"] == "release"
        ]
        self.assertEqual(sum(
            any(region["syntaxKind"] == "finally_clause"
                for region in call["controlContext"]["controlRegions"])
            for call in release_calls
        ), 3)
        self.assertEqual(sum(
            any(target["targetExpression"].endswith(".finally")
                for target in call["controlContext"]["enclosingCalls"])
            for call in release_calls
        ), 1)
        self.assertEqual(
            image_packer["callCleanupPairingCoverage"]["handleStatusCounts"],
            {
                "later-try-finally": 1,
                "matching-try-finally": 2,
                "no-direct-release": 6,
                "promise-finally-callback": 1,
                "same-try-non-finalizer": 2,
            },
        )
        self.assertEqual(
            image_packer["callCleanupPairingCoverage"]["releaseRelationCounts"],
            {
                "later-try-finally": 1,
                "matching-try-finally": 2,
                "promise-finally-callback": 1,
                "same-try-non-finalizer": 2,
            },
        )

    def test_dynamic_packet_workflow_rematerializes_and_binds_the_full_lineage(self):
        workflow = (
            ROOT / ".github/workflows/multi-repo-candidate-review-packet.yml"
        ).read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn(".github/workflows/multi-repo-candidate-cohort-review.yml", workflow)
        self.assertIn("scripts/multi-repo-analysis-run.py validate", workflow)
        self.assertIn("scripts/prepare-multi-repo-analysis-sources.py", workflow)
        self.assertIn("scripts/select-multi-repo-cohort-candidate.py", workflow)
        self.assertIn("scripts/build-multi-repo-candidate-review-packet.py", workflow)
        self.assertIn('--analysis-manifest "$AGENTLAB_ROOT/source/source/analysis-source/manifest.json"', workflow)
        self.assertIn("multi-repo-candidate-review-packet", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("AGENTLAB_LM_GATEWAY", workflow)


if __name__ == "__main__":
    unittest.main()
