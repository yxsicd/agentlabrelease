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

    def test_v3_packet_binds_supplemental_control_context_without_replacing_base_facts(self):
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
            self.assertEqual(packet["schema"], "agentlab.multi_repo_candidate_review_packet.v3")
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

    def test_packet_lineage_binds_every_input(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            packet = PACKET.build_packet(*paths[:4], paths[4]["id"], "3" * 40)
            for key, path in zip(
                ("manifestSha256", "difficultyEvidenceSha256", "workspaceFactsSha256", "currentMethodProposalSha256"),
                paths[:4],
            ):
                self.assertEqual(packet["lineage"][key], hashlib.sha256(path.read_bytes()).hexdigest())

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
            "05233f0e5bd63959af02ec39f2576c855ccb3aa0",
        ])
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
            self.assertEqual(value["sweStyleTaskContract"]["satisfiedByThisPacket"], expected)
            self.assertFalse(value["automaticPromotion"])

        alert = json.loads((root / "review-packets/alert-dialog.json").read_text())
        calls = json.loads((root / "review-packets/call-make-call.json").read_text())
        image_packer = json.loads(
            (root / "review-packets/image-create-image-packer.json").read_text()
        )
        self.assertEqual(
            image_packer["schema"],
            "agentlab.multi_repo_candidate_review_packet.v2",
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


if __name__ == "__main__":
    unittest.main()
