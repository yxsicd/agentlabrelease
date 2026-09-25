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
            "evidenceIds": ["fact-call-a", "fact-call-b"],
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
            self.assertEqual(
                packet["sweStyleTaskContract"]["satisfiedByThisPacket"],
                ["exact base source set", "source-localized call evidence"],
            )
            self.assertFalse(packet["automaticPromotion"])

    def test_packet_rejects_candidate_drift_and_non_shortlisted_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, proposal, candidate = self.fixture(root)
            value = json.loads(difficulty.read_text())
            value["candidates"][0]["seed"]["callTarget"] = "api.changed"
            difficulty.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(PACKET.ReviewPacketError, "candidate digest differs"):
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


if __name__ == "__main__":
    unittest.main()
