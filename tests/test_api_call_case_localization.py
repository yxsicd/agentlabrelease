import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROPOSE = ROOT / "scripts/propose-api-call-case-localization.py"
REVIEW = ROOT / "scripts/review-api-call-case-localization.py"
CONSTRUCT = ROOT / "scripts/run-multi-repo-intent-construction.py"
SCORE = ROOT / "scripts/score-multi-repo-intent.py"
PLAN = ROOT / "scripts/propose-multi-repo-case-plan.py"
REVIEW_PLAN = ROOT / "scripts/review-multi-repo-case-plan.py"
FREEZE = ROOT / "scripts/generate-multi-repo-case.py"
CALIBRATE = ROOT / "examples/multi-repo-case/calibrate.py"
MOCK = ROOT / "examples/multi-repo-case/mock-construction-agent.py"
ORACLE = ROOT / "examples/multi-repo-case/oracle-contract.json"


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApiCallCaseLocalizationTest(unittest.TestCase):
    def write(self, root, name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        return path

    def repository(self, root, name):
        repository = root / name
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        for path, body in {
            "target.ets": "target();\n",
            "reference.ets": "reference();\n",
            "lifecycle.ets": "lifecycle();\n",
        }.items():
            (repository / path).write_text(body)
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "-c",
                "user.name=Localization Test",
                "-c",
                "user.email=localization@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        revision = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
        ).strip()
        return repository, revision

    def fixture(self, root):
        one, revision_one = self.repository(root, "one")
        two, revision_two = self.repository(root, "two")
        manifest = self.write(
            root,
            "manifest.json",
            {
                "schema": "agentlab.multi_repo_manifest.v1",
                "repositories": [
                    {"id": "one", "repository": "fixture://one", "root": str(one), "revision": revision_one},
                    {"id": "two", "repository": "fixture://two", "root": str(two), "revision": revision_two},
                ],
                "moduleBindings": {},
            },
        )
        facts = []
        for repository_id, revision in (("one", revision_one), ("two", revision_two)):
            for role, owner in (("target", "Late::aboutToAppear"), ("reference", "EntryAbility::onCreate")):
                facts.append(
                    {
                        "id": f"call-{repository_id}-{role}",
                        "kind": "call",
                        "repositoryId": repository_id,
                        "path": f"{role}.ets",
                        "owner": owner,
                        "targetExpression": "webview.WebviewController.initializeWebEngine",
                        "span": {"startLine": 1, "endLine": 1},
                        "sourceIdentity": f"git:fixture://{repository_id}@{revision}",
                    }
                )
        facts_path = root / "facts.jsonl"
        facts_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in facts))
        sources = [
            {"id": "one", "repository": "fixture://one", "revision": revision_one},
            {"id": "two", "repository": "fixture://two", "revision": revision_two},
        ]
        difficulty = self.write(
            root,
            "difficulty.json",
            {
                "schema": "agentlab.difficulty_candidates.v2",
                "sourceSetSha256": "a" * 64,
                "sources": sources,
                "moduleBindings": {},
                "candidates": [
                    {
                        "id": "difficulty-api",
                        "dimensionId": "multi-repository-change-impact",
                        "relationType": "shared-external-api-call-contract",
                        "seed": {
                            "specifier": "@kit.ArkWeb",
                            "exportedSymbol": "webview",
                            "callTarget": "webview.WebviewController.initializeWebEngine",
                        },
                        "affectedRepositoryCount": 2,
                        "affectedFiles": [
                            {"repositoryId": repository_id, "path": f"{role}.ets", "dependencyDepth": 1}
                            for repository_id in ("one", "two")
                            for role in ("target", "reference")
                        ],
                        "evidenceIds": [row["id"] for row in facts],
                        "verificationContract": {"caseReady": False},
                        "maturityState": "candidate",
                        "automaticPromotion": False,
                    }
                ],
                "automaticPromotion": False,
            },
        )
        selection = self.write(
            root,
            "selection.json",
            {
                "schema": "agentlab.api_call_case_localization_selection.v1",
                "candidateId": "difficulty-api",
                "title": "Pre-initialize ArkWeb at the application lifecycle boundary",
                "hypothesis": "Moving initialization from component appearance to ability creation preserves behavior while removing late startup work.",
                "targetCallFactIds": ["call-one-target", "call-two-target"],
                "referenceCallFactIds": ["call-one-reference", "call-two-reference"],
                "editablePaths": [
                    {"repositoryId": repository_id, "path": "target.ets", "reason": "localized late call"}
                    for repository_id in ("one", "two")
                ]
                + [
                    {"repositoryId": repository_id, "path": "lifecycle.ets", "reason": "owning lifecycle destination"}
                    for repository_id in ("one", "two")
                ],
                "contextPaths": [
                    {"repositoryId": repository_id, "path": "reference.ets", "reason": "same API at an earlier lifecycle"}
                    for repository_id in ("one", "two")
                ],
                "proposedChecks": {
                    "repair": [{"id": "early-init", "behavior": "Initialization occurs before page construction."}],
                    "preservation": [{"id": "keep-page", "behavior": "Existing page behavior remains present."}],
                    "device": [{"id": "launch", "behavior": "The page launches on the emulator."}],
                    "performance": [{"id": "startup", "behavior": "Startup workload identity is preserved."}],
                },
                "automaticPromotion": False,
            },
        )
        return manifest, difficulty, facts_path, selection

    def test_proposal_binds_exact_calls_paths_and_independent_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, selection = self.fixture(root)
            proposal_path = root / "proposal.json"
            proposed = subprocess.run(
                [
                    sys.executable,
                    str(PROPOSE),
                    "--manifest",
                    str(manifest),
                    "--difficulty",
                    str(difficulty),
                    "--facts",
                    str(facts),
                    "--candidate-id",
                    "difficulty-api",
                    "--selection",
                    str(selection),
                    "--method-revision",
                    "b" * 40,
                    "--output",
                    str(proposal_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(proposed.returncode, 0, proposed.stderr)
            proposal = json.loads(proposal_path.read_text())
            self.assertEqual(proposal["status"], "review-required")
            self.assertEqual(len(proposal["targetCallSites"]), 2)
            self.assertEqual(len(proposal["referenceCallSites"]), 2)
            self.assertEqual(len(proposal["editablePaths"]), 4)
            self.assertEqual(len(proposal["expandedPaths"]), 2)
            self.assertTrue(all(row["gitBlobOid"] for row in proposal["editablePaths"]))
            self.assertFalse(proposal["automaticPromotion"])

            review = self.write(
                root,
                "review.json",
                {
                    "schema": "agentlab.api_call_case_localization_review.v1",
                    "proposalSha256": file_digest(proposal_path),
                    "reviewer": "independent-maintainer",
                    "rationale": "The selected calls and expanded lifecycle paths are a coherent calibration input.",
                    "acknowledgedRiskIds": [row["id"] for row in proposal["risks"]],
                    "verdict": "approve-for-intent-construction",
                    "automaticPromotion": False,
                },
            )
            reviewed_path = root / "reviewed.json"
            reviewed = subprocess.run(
                [sys.executable, str(REVIEW), "--proposal", str(proposal_path), "--review", str(review), "--output", str(reviewed_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            result = json.loads(reviewed_path.read_text())
            self.assertEqual(result["status"], "reviewed-for-intent-construction")
            self.assertEqual(result["review"]["proposalSha256"], file_digest(proposal_path))
            self.assertFalse(result["automaticPromotion"])

            construction = root / "construction"
            constructed = subprocess.run(
                [
                    sys.executable,
                    str(CONSTRUCT),
                    "--manifest",
                    str(manifest),
                    "--difficulty",
                    str(difficulty),
                    "--facts",
                    str(facts),
                    "--candidate-id",
                    "difficulty-api",
                    "--oracle-contract",
                    str(ORACLE),
                    "--participant",
                    str(MOCK),
                    "--participant-id",
                    "deterministic-localization-test",
                    "--localization",
                    str(reviewed_path),
                    "--localization-proposal",
                    str(proposal_path),
                    "--localization-review",
                    str(review),
                    "--output",
                    str(construction),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(constructed.returncode, 0, constructed.stderr)
            receipt = json.loads((construction / "construction-receipt.json").read_text())
            self.assertEqual(receipt["localization"]["sha256"], file_digest(reviewed_path))
            self.assertEqual(len(receipt["localization"]["editablePaths"]), 4)
            self.assertEqual(len(receipt["localization"]["contextPaths"]), 2)
            self.assertEqual(len(receipt["sourceFiles"]), 6)
            self.assertEqual(sum(row["editable"] for row in receipt["sourceFiles"]), 4)

            quality = construction / "intent-quality.json"
            scored = subprocess.run(
                [
                    sys.executable,
                    str(SCORE),
                    "--intent",
                    str(construction / "intent.json"),
                    "--construction-receipt",
                    str(construction / "construction-receipt.json"),
                    "--oracle-contract",
                    str(ORACLE),
                    "--output",
                    str(quality),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(scored.returncode, 0, scored.stderr)
            plan_path = root / "case-plan-proposal.json"
            planned = subprocess.run(
                [
                    sys.executable,
                    str(PLAN),
                    "--difficulty",
                    str(difficulty),
                    "--intent",
                    str(construction / "intent.json"),
                    "--construction-receipt",
                    str(construction / "construction-receipt.json"),
                    "--quality-report",
                    str(quality),
                    "--output",
                    str(plan_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(planned.returncode, 0, planned.stderr)
            plan = json.loads(plan_path.read_text())
            self.assertEqual(
                {(row["repositoryId"], row["path"]) for row in plan["allowedEdits"]},
                {(row["repositoryId"], row["path"]) for row in proposal["editablePaths"]},
            )
            self.assertNotIn(("one", "reference.ets"), {(row["repositoryId"], row["path"]) for row in plan["allowedEdits"]})

            plan_review = self.write(
                root,
                "case-plan-review.json",
                {
                    "schema": "agentlab.multi_repo_case_plan_review.v1",
                    "proposalSha256": file_digest(plan_path),
                    "reviewer": "independent-case-reviewer",
                    "rationale": "The reviewed localization and staged checks are suitable for calibration.",
                    "acknowledgedRiskIds": [row["id"] for row in plan["risks"]],
                    "verdict": "approve-for-calibration",
                },
            )
            reviewed_plan = root / "case-plan.json"
            reviewed = subprocess.run(
                [sys.executable, str(REVIEW_PLAN), "--proposal", str(plan_path), "--review", str(plan_review), "--output", str(reviewed_plan)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            calibration_root = root / "calibration"
            calibrated = subprocess.run(
                [
                    sys.executable,
                    str(CALIBRATE),
                    "--baseline",
                    str(ROOT / "examples/multi-repo-case/baseline"),
                    "--reference",
                    str(ROOT / "examples/multi-repo-case/reference"),
                    "--source-set-sha256",
                    "a" * 64,
                    "--candidate-id",
                    "difficulty-api",
                    "--output",
                    str(calibration_root),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(calibrated.returncode, 0, calibrated.stderr)
            frozen_path = root / "case.json"
            frozen = subprocess.run(
                [
                    sys.executable,
                    str(FREEZE),
                    "--difficulty",
                    str(difficulty),
                    "--plan",
                    str(reviewed_plan),
                    "--proposal",
                    str(plan_path),
                    "--review",
                    str(plan_review),
                    "--construction-quality",
                    str(quality),
                    "--calibration",
                    str(calibration_root / "summary.json"),
                    "--output",
                    str(frozen_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(frozen.returncode, 0, frozen.stderr)
            frozen_case = json.loads(frozen_path.read_text())
            self.assertEqual(
                frozen_case["lineage"]["apiCallLocalization"]["sha256"],
                file_digest(reviewed_path),
            )

    def test_proposal_rejects_call_outside_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, selection_path = self.fixture(root)
            selection = json.loads(selection_path.read_text())
            selection["targetCallFactIds"][0] = "call-outside-candidate"
            selection_path.write_text(json.dumps(selection))
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROPOSE),
                    "--manifest",
                    str(manifest),
                    "--difficulty",
                    str(difficulty),
                    "--facts",
                    str(facts),
                    "--candidate-id",
                    "difficulty-api",
                    "--selection",
                    str(selection_path),
                    "--method-revision",
                    "b" * 40,
                    "--output",
                    str(root / "proposal.json"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside the candidate", result.stderr)

    def test_api_call_construction_rejects_localization_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, _ = self.fixture(root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(CONSTRUCT),
                    "--manifest",
                    str(manifest),
                    "--difficulty",
                    str(difficulty),
                    "--facts",
                    str(facts),
                    "--candidate-id",
                    "difficulty-api",
                    "--oracle-contract",
                    str(ORACLE),
                    "--participant",
                    str(MOCK),
                    "--participant-id",
                    "must-not-run",
                    "--output",
                    str(root / "construction"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires reviewed localization evidence", result.stderr)
            self.assertFalse((root / "construction").exists())


if __name__ == "__main__":
    unittest.main()
