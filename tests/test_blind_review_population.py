from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "blind_review_population",
    ROOT / "scripts/summarize-blind-review-population.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def dimension(verdicts: list[str]) -> dict:
    verdicts = sorted(verdicts)
    unanimous = len(set(verdicts)) == 1
    return {
        "verdicts": verdicts,
        "unanimous": unanimous,
        "qualified": unanimous and verdicts[0] == "qualified",
    }


def adjudication(case_id: str, reviewers: list[str], dimensions: dict) -> dict:
    qualified = all(row["qualified"] for row in dimensions.values())
    return {
        "schema": "agentlab.blind_case_authenticated_review_adjudication.v1",
        "caseId": case_id,
        "cutId": f"{case_id}-cut",
        "sourceSetSha256": "a" * 64,
        "participantManifestSha256": "b" * 64,
        "evaluatorManifestSha256": "c" * 64,
        "reviewCount": len(reviewers),
        "reviews": [
            {"reviewer": reviewer, "decisionSha256": f"{index + 1:064x}"}
            for index, reviewer in enumerate(reviewers)
        ],
        "dimensions": dimensions,
        "reviewConsensusQualified": qualified,
        "reviewerIdentityAuthenticationQualified": True,
        "attestedWorkflowProvenanceQualified": True,
        "blindPilotReviewQualified": qualified,
        "modelTrainingExclusionQualified": False,
        "eligibleForUnseenAgentDiscrimination": False,
        "automaticPromotion": False,
    }


class BlindReviewPopulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        qualified = {name: dimension(["qualified", "qualified"]) for name in MODULE.DIMENSIONS}
        mixed = {
            "semanticLeakage": dimension(["qualified", "rejected"]),
            "contaminationRisk": dimension(["rejected", "rejected"]),
            "specificationFairness": dimension(["qualified", "qualified"]),
            "oracleBreadth": dimension(["unknown", "unknown"]),
        }
        self.values = {
            1001: adjudication("case-a", ["alice", "bob"], qualified),
            1002: adjudication("case-b", ["alice", "carol"], mixed),
        }
        for run_id in self.values:
            self.make_bundle(run_id)
        self.manifest = self.root / "manifest.json"
        self.write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_bundle(self, run_id: int) -> None:
        bundle = self.root / "bundles" / str(run_id)
        paths = (
            "authenticated-adjudication.json",
            "request.json",
            "source/blind-cut/cut-receipt.json",
            "source/blind-cut/participant/manifest.json",
            "source/blind-cut/evaluator/manifest.json",
            "first/artifact/decision.json",
            "first/provenance.json",
            "second/artifact/decision.json",
            "second/provenance.json",
        )
        for relative in paths:
            path = bundle / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"runId": run_id, "path": relative}, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def write_manifest(self, *, representative: bool = False) -> None:
        value = {
            "schema": "agentlab.blind_review_population_manifest.v1",
            "cohortId": "cohort-one",
            "methodRevision": "a" * 40,
            "samplingFrame": {
                "id": "frame-one",
                "description": "Two preselected maintenance cuts.",
                "selectionPolicy": "First two cuts frozen before reviewer outcomes.",
                "declaredRepresentative": representative,
            },
            "cases": [
                {
                    "caseId": value["caseId"],
                    "bundle": f"bundles/{run_id}",
                    "repository": "example/agentlab",
                    "adjudicationRunId": run_id,
                }
                for run_id, value in self.values.items()
            ],
        }
        self.manifest.write_text(json.dumps(value, indent=2), encoding="utf-8")

    def verifier(self, bundle: Path, repository: str, run_id: int, output: Path):
        self.assertEqual(repository, "example/agentlab")
        self.assertEqual(bundle.name, str(run_id))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema": "agentlab.blind_case_online_attestation_verification.v1",
                    "repository": repository,
                    "workflowPath": ".github/workflows/blind-case-review-adjudication.yml",
                    "workflowRunId": run_id,
                    "workflowRunAttempt": 1,
                    "workflowHeadSha": "d" * 40,
                    "policy": {
                        "repository": repository,
                        "signerWorkflow": f"{repository}/.github/workflows/blind-case-review-adjudication.yml",
                        "sourceRef": "refs/heads/main",
                        "sourceDigest": "d" * 40,
                        "denySelfHostedRunners": True,
                    },
                    "subjectPath": "authenticated-adjudication.json",
                    "subjectSha256": MODULE.digest(
                        bundle / "authenticated-adjudication.json"
                    ),
                    "verification": [{"verified": True}],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return self.values[run_id]

    def test_population_report_retains_denominators_and_disagreement(self) -> None:
        output = self.root / "population"
        report = MODULE.produce(self.manifest, output, self.verifier)
        self.assertEqual(report["denominators"]["caseCount"], 2)
        self.assertEqual(report["denominators"]["reviewRecordCount"], 4)
        self.assertEqual(report["denominators"]["uniqueAuthenticatedReviewerCount"], 3)
        semantic = report["dimensionStatistics"]["semanticLeakage"]
        self.assertEqual(semantic["qualifiedConsensusCaseCount"], 1)
        self.assertEqual(semantic["disagreementCaseCount"], 1)
        self.assertEqual(semantic["disagreementRate"], 0.5)
        self.assertLess(semantic["disagreementRateWilson95"]["lower"], 0.5)
        self.assertGreater(semantic["disagreementRateWilson95"]["upper"], 0.5)
        oracle = report["dimensionStatistics"]["oracleBreadth"]
        self.assertEqual(oracle["qualifiedConsensusCaseCount"], 1)
        self.assertEqual(oracle["unknownConsensusCaseCount"], 1)
        self.assertEqual(
            report["reviewerReuse"]["reviewersWithMultipleCases"], ["alice"]
        )
        self.assertEqual(
            report["qualification"]["blindPilotReviewQualifiedCaseCount"], 1
        )
        self.assertFalse(report["qualification"]["allCasesBlindPilotReviewQualified"])
        self.assertFalse(report["qualification"]["populationRepresentativenessQualified"])
        self.assertFalse(report["qualification"]["eligibleForUnseenAgentDiscrimination"])
        self.assertEqual(report["cases"][0]["adjudicationRunAttempt"], 1)
        self.assertEqual(report["cases"][0]["adjudicationWorkflowHeadSha"], "d" * 40)
        self.assertTrue((output / "input-manifest.json").is_file())
        self.assertTrue((output / "report.json").is_file())
        self.assertTrue((output / "verification/case-a.json").is_file())
        self.assertEqual(json.loads((output / "report.json").read_text()), report)

    def test_duplicate_case_and_run_id_fail_closed(self) -> None:
        value = json.loads(self.manifest.read_text())
        value["cases"][1]["caseId"] = value["cases"][0]["caseId"]
        self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "duplicate population caseId"):
            MODULE.produce(self.manifest, self.root / "duplicate-case", self.verifier)

        self.write_manifest()
        value = json.loads(self.manifest.read_text())
        value["cases"][1]["adjudicationRunId"] = value["cases"][0]["adjudicationRunId"]
        value["cases"][1]["repository"] = value["cases"][0]["repository"]
        self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "duplicate adjudication run"):
            MODULE.produce(self.manifest, self.root / "duplicate-run", self.verifier)

    def test_case_identity_mismatch_rejects_entire_report(self) -> None:
        self.values[1002] = {**self.values[1002], "caseId": "different-case"}
        output = self.root / "mismatch"
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "case identity differs"):
            MODULE.produce(self.manifest, output, self.verifier)
        self.assertFalse(output.exists())

    def test_online_verification_policy_tamper_rejects_entire_report(self) -> None:
        def tampered(bundle: Path, repository: str, run_id: int, output: Path):
            result = self.verifier(bundle, repository, run_id, output)
            value = json.loads(output.read_text())
            value["policy"]["denySelfHostedRunners"] = False
            output.write_text(json.dumps(value))
            return result

        output = self.root / "tampered-verification"
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "policy differs"):
            MODULE.produce(self.manifest, output, tampered)
        self.assertFalse(output.exists())

    def test_overall_consensus_must_match_dimension_results(self) -> None:
        self.values[1001] = {
            **self.values[1001],
            "reviewConsensusQualified": False,
        }
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "review consensus differs"):
            MODULE.produce(self.manifest, self.root / "bad-consensus", self.verifier)

    def test_path_escape_is_rejected(self) -> None:
        value = json.loads(self.manifest.read_text())
        value["cases"][0]["bundle"] = "../outside"
        self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "escapes or is absent"):
            MODULE.produce(self.manifest, self.root / "escaped", self.verifier)

    def test_representative_population_claim_requires_a_separate_review(self) -> None:
        self.write_manifest(representative=True)
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "representativeness"):
            MODULE.produce(self.manifest, self.root / "representative", self.verifier)

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaisesRegex(MODULE.PopulationReviewError, "refusing to overwrite"):
            MODULE.produce(self.manifest, output, self.verifier)

    def test_workflow_requires_trusted_main_online_verification_and_signing(self) -> None:
        workflow = (ROOT / ".github/workflows/blind-review-population.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("gh run download", workflow)
        self.assertIn("summarize-blind-review-population.py", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("declaredRepresentative\": False", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn(
            "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
            workflow,
        )
        self.assertIn("population/report.json", workflow)


if __name__ == "__main__":
    unittest.main()
