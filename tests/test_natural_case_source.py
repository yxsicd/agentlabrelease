from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


IMPORT = load_module("natural_case_source_import", ROOT / "scripts/import-natural-case-source.py")
MERGE = load_module("case_candidate_source_merge", ROOT / "scripts/merge-case-candidate-sources.py")
PROPOSE = load_module("natural_cohort_propose", ROOT / "scripts/propose-multi-repo-candidate-cohort.py")
REVIEW = load_module("natural_cohort_review", ROOT / "scripts/review-multi-repo-candidate-cohort.py")
SELECT = load_module("natural_cohort_select", ROOT / "scripts/select-multi-repo-cohort-candidate.py")
GENERATE = load_module("natural_case_generate", ROOT / "scripts/generate-multi-repo-case.py")


class NaturalCaseSourceTests(unittest.TestCase):
    def sources(self) -> list[dict]:
        return [
            {"id": "app", "repository": "example/app", "revision": "1" * 40},
            {"id": "service", "repository": "example/service", "revision": "2" * 40},
        ]

    def source_set_sha256(self) -> str:
        return IMPORT.canonical_digest(
            {
                "schema": "agentlab.multi_repo_source_set.v1",
                "repositories": self.sources(),
                "moduleBindings": {},
            }
        )

    def write_historical_manifest(self, root: Path) -> Path:
        artifacts = {
            "problem.md": "The shared contract breaks both consumers.\n",
            "repair.patch": "diff --git a/a b/a\n",
            "tests.patch": "diff --git a/test b/test\n",
        }
        for name, body in artifacts.items():
            (root / name).write_text(body)
        evidence = [
            {
                "id": evidence_id,
                "role": role,
                "path": name,
                "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
            }
            for evidence_id, role, name in (
                ("problem", "problem-statement", "problem.md"),
                ("repair", "repair-patch", "repair.patch"),
                ("tests", "test-patch", "tests.patch"),
            )
        ]
        manifest = {
            "schema": "agentlab.natural_case_source_manifest.v1",
            "id": "natural-coordinated-repair",
            "strategy": "historical-repair",
            "title": "Repair a coordinated contract regression",
            "sourceSetSha256": self.source_set_sha256(),
            "sources": self.sources(),
            "moduleBindings": {},
            "affectedFiles": [
                {"repositoryId": "app", "path": "src/app.ts", "dependencyDepth": 1},
                {"repositoryId": "service", "path": "src/service.ts", "dependencyDepth": 0},
            ],
            "evidence": evidence,
            "origin": {
                "issueUrls": ["https://example.com/issues/7"],
                "repairs": [
                    {"repositoryId": "app", "repairUrl": "https://example.com/app/pull/8", "fixRevision": "3" * 40},
                    {"repositoryId": "service", "repairUrl": "https://example.com/service/pull/9", "fixRevision": "4" * 40},
                ],
                "openedAt": "2026-09-20T10:00:00Z",
                "resolvedAt": "2026-09-21T11:00:00Z",
            },
            "testContract": {
                "observedFailureCheckIds": ["contract-fails-before"],
                "preservationCheckIds": ["existing-route-stays-green"],
            },
            "sourceVisibility": "public",
            "collectedAt": "2026-09-25T12:00:00Z",
            "automaticPromotion": False,
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return path

    def derived_difficulty(self, root: Path) -> Path:
        value = {
            "schema": "agentlab.difficulty_candidates.v2",
            "method": "fixture analyzer",
            "sourceSetSha256": self.source_set_sha256(),
            "sources": self.sources(),
            "moduleBindings": {},
            "candidates": [
                {
                    "id": "derived-analysis",
                    "schema": "agentlab.difficulty_point.v1",
                    "dimensionId": "multi-repository-change-impact",
                    "relationType": "recursive-reverse-impact",
                    "status": "candidate",
                    "maturityState": "candidate",
                    "affectedFiles": [
                        {"repositoryId": "app", "path": "src/a.ts", "dependencyDepth": 1},
                        {"repositoryId": "service", "path": "src/b.ts", "dependencyDepth": 0},
                    ],
                    "affectedRepositoryCount": 2,
                    "maxDependencyDepth": 1,
                    "automaticPromotion": False,
                }
            ],
            "automaticPromotion": False,
        }
        path = root / "derived.json"
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        return path

    def write_operator_manifest(self, root: Path) -> Path:
        artifacts = {
            "failure.json": '{"error":"shared contract rejected"}\n',
            "reproduce.md": "Run the app and service against the pinned source set.\n",
        }
        for name, body in artifacts.items():
            (root / name).write_text(body)
        evidence = [
            {
                "id": evidence_id,
                "role": role,
                "path": name,
                "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
            }
            for evidence_id, role, name in (
                ("failure", "failure-report", "failure.json"),
                ("reproduction", "reproduction", "reproduce.md"),
            )
        ]
        manifest = {
            "schema": "agentlab.natural_case_source_manifest.v1",
            "id": "natural-operator-incident",
            "strategy": "operator-reported-failure",
            "title": "Reproduce a cross-repository operator incident",
            "sourceSetSha256": self.source_set_sha256(),
            "sources": self.sources(),
            "moduleBindings": {},
            "affectedFiles": [
                {"repositoryId": "app", "path": "src/app.ts", "dependencyDepth": 1},
                {"repositoryId": "service", "path": "src/service.ts", "dependencyDepth": 0},
            ],
            "evidence": evidence,
            "origin": {
                "incidentId": "incident-2026-09-25-1",
                "observedAt": "2026-09-25T13:00:00Z",
                "reporterAuthority": "release-operations",
            },
            "testContract": {
                "observedFailureCheckIds": ["incident-reproduces"],
                "preservationCheckIds": ["unrelated-route-stays-green"],
            },
            "sourceVisibility": "internal",
            "collectedAt": "2026-09-25T14:00:00Z",
            "automaticPromotion": False,
        }
        path = root / "operator-manifest.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return path

    def test_natural_and_derived_candidates_share_one_reviewed_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_historical_manifest(root)
            natural_value = IMPORT.build(manifest)
            natural = root / "natural.json"
            natural.write_text(json.dumps(natural_value, sort_keys=True) + "\n")
            derived = self.derived_difficulty(root)
            merged_value = MERGE.merge([derived, natural])
            merged = root / "merged.json"
            merged.write_text(json.dumps(merged_value, sort_keys=True) + "\n")

            proposal_value = PROPOSE.propose(merged, "mixed-cohort", "5" * 40)
            self.assertEqual(
                proposal_value["samplingFrame"]["strata"]["caseSourceLane"],
                {"derived": 1, "natural": 1},
            )
            proposal = root / "proposal.json"
            proposal.write_text(json.dumps(proposal_value, sort_keys=True) + "\n")
            review_value = REVIEW.decide(
                proposal,
                hashlib.sha256(proposal.read_bytes()).hexdigest(),
                "derived-analysis,natural-coordinated-repair",
                "reviewer",
                ",".join(sorted(row["id"] for row in proposal_value["risks"])),
                "Predeclare both source lanes before construction.",
            )
            review = root / "review.json"
            review.write_text(json.dumps(review_value, sort_keys=True) + "\n")
            cohort_value = REVIEW.compile_cohort(proposal, review)
            cohort = root / "cohort.json"
            cohort.write_text(json.dumps(cohort_value, sort_keys=True) + "\n")
            cohort_sha256 = hashlib.sha256(cohort.read_bytes()).hexdigest()
            selection_value = SELECT.select(
                cohort,
                merged,
                cohort_sha256,
                "natural-coordinated-repair",
            )
            self.assertEqual(selection_value["caseSource"]["lane"], "natural")
            selection = root / "selection.json"
            selection.write_text(json.dumps(selection_value, sort_keys=True) + "\n")
            lineage = GENERATE.candidate_cohort_lineage(
                selection,
                merged,
                "natural-coordinated-repair",
                self.source_set_sha256(),
            )
            self.assertEqual(lineage["caseSource"], selection_value["caseSource"])
            candidate = next(row for row in merged_value["candidates"] if row["id"] == "natural-coordinated-repair")
            resolved = GENERATE.resolve_case_source(
                candidate,
                candidate["id"],
                self.source_set_sha256(),
                merged,
            )
            self.assertEqual(resolved["strategy"], "historical-repair")
            self.assertEqual(resolved["authority"], "exact-natural-source-manifest")

    def test_evidence_tamper_and_incomplete_coordinated_repair_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_historical_manifest(root)
            (root / "repair.patch").write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "evidence digest differs"):
                IMPORT.build(manifest)
            manifest = self.write_historical_manifest(root)
            value = json.loads(manifest.read_text())
            value["origin"]["repairs"] = value["origin"]["repairs"][:1]
            manifest.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValueError, "do not cover every affected repository"):
                IMPORT.build(manifest)

    def test_operator_reported_failure_normalizes_without_claiming_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = IMPORT.build(self.write_operator_manifest(root))
            candidate = value["candidates"][0]
            self.assertEqual(candidate["caseSource"]["lane"], "natural")
            self.assertEqual(candidate["caseSource"]["strategy"], "operator-reported-failure")
            self.assertEqual(candidate["naturalOrigin"]["origin"]["reporterAuthority"], "release-operations")
            self.assertFalse(candidate["verificationContract"]["caseReady"])
            self.assertFalse(candidate["automaticPromotion"])

    def test_natural_source_timeline_is_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_historical_manifest(root)
            value = json.loads(manifest.read_text())
            value["origin"]["resolvedAt"] = "2026-09-19T10:00:00Z"
            manifest.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValueError, "predates issue opening"):
                IMPORT.build(manifest)

            manifest = self.write_operator_manifest(root)
            value = json.loads(manifest.read_text())
            value["collectedAt"] = "2026-09-24T14:00:00Z"
            manifest.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValueError, "collection predates"):
                IMPORT.build(manifest)

    def test_candidate_sources_from_different_source_sets_cannot_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.derived_difficulty(root)
            value = json.loads(first.read_text())
            value["sourceSetSha256"] = "f" * 64
            second = root / "other.json"
            second.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValueError, "different source sets"):
                MERGE.merge([first, second])

    def test_manifest_schema_is_published(self) -> None:
        schema = json.loads((ROOT / "schemas/natural-case-source-manifest.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema"]["const"], "agentlab.natural_case_source_manifest.v1")


if __name__ == "__main__":
    unittest.main()
