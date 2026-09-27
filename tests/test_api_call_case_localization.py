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
CREATE_REVIEW = ROOT / "scripts/create-api-call-localization-review.py"
CONSTRUCT = ROOT / "scripts/run-multi-repo-intent-construction.py"
SCORE = ROOT / "scripts/score-multi-repo-intent.py"
PLAN = ROOT / "scripts/propose-multi-repo-case-plan.py"
REVIEW_PLAN = ROOT / "scripts/review-multi-repo-case-plan.py"
FREEZE = ROOT / "scripts/generate-multi-repo-case.py"
CALIBRATE = ROOT / "examples/multi-repo-case/calibrate.py"
MOCK = ROOT / "examples/multi-repo-case/mock-construction-agent.py"
ORACLE = ROOT / "examples/multi-repo-case/oracle-contract.json"
SEMANTIC_REVIEW = ROOT / "scripts/review-multi-repo-candidate-semantics.py"


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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

    def semantic_authorization(self, root, difficulty_path, *, approved=True):
        difficulty = json.loads(difficulty_path.read_text())
        candidate = difficulty["candidates"][0]
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
        packet = self.write(
            root,
            "semantic-packet.json",
            {
                "schema": "agentlab.multi_repo_candidate_review_packet.v1",
                "status": "independent-semantic-review-required",
                "candidateId": candidate["id"],
                "candidateSha256": canonical_digest(candidate),
                "sourceSetSha256": difficulty["sourceSetSha256"],
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
                    "schema": "agentlab.multi_repo_candidate_semantic_review.v1",
                    "allowedVerdicts": [
                        "advance-to-case-contract",
                        "reject-as-noncoherent",
                        "defer-for-more-evidence",
                    ],
                    "requiredQuestionIds": question_ids,
                    "requiredRiskIds": risk_ids,
                    "reviewerMustBeIndependentOfPacketGenerator": True,
                },
                "automaticPromotion": False,
            },
        )
        verdict = "advance-to-case-contract" if approved else "defer-for-more-evidence"
        responses = [
            {
                "id": question_id,
                "answer": "unknown" if not approved and question_id == "environment" else "yes",
                "rationale": f"Independent retained evidence supports this answer for {question_id}.",
            }
            for question_id in sorted(question_ids)
        ]
        decision = self.write(
            root,
            "semantic-decision.json",
            {
                "schema": "agentlab.multi_repo_candidate_semantic_review.v1",
                "candidateId": candidate["id"],
                "packetSha256": file_digest(packet),
                "packetGenerator": f"git:{'1' * 40}",
                "reviewer": "github:independent-test-reviewer",
                "responses": responses,
                "acknowledgedRiskIds": sorted(risk_ids),
                "verdict": verdict,
                "rationale": "The candidate semantic evidence was inspected independently for this test.",
                "allowsCaseContract": approved,
                "automaticPromotion": False,
            },
        )
        gate = root / "semantic-gate.json"
        compiled = subprocess.run(
            [
                sys.executable,
                str(SEMANTIC_REVIEW),
                "compile",
                "--packet",
                str(packet),
                "--decision",
                str(decision),
                "--output",
                str(gate),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        return packet, decision, gate

    def test_proposal_binds_exact_calls_paths_and_independent_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, selection = self.fixture(root)
            semantic_packet, semantic_decision, semantic_gate = self.semantic_authorization(root, difficulty)
            candidate = json.loads(difficulty.read_text())["candidates"][0]
            case_source = {
                "lane": "derived",
                "strategy": "semantic-program-analysis",
                "authority": "exact-difficulty-evidence",
            }
            candidate_summary = {
                "id": candidate["id"],
                "candidateSha256": canonical_digest(candidate),
                "caseSource": case_source,
            }
            candidate_cohort = self.write(
                root,
                "candidate-cohort.json",
                {
                    "schema": "agentlab.multi_repo_candidate_cohort.v1",
                    "cohortId": "cohort-localization",
                    "methodRevision": "1" * 40,
                    "proposalMethodRevision": "2" * 40,
                    "sourceSetSha256": "a" * 64,
                    "difficultyEvidenceSha256": file_digest(difficulty),
                    "selectedCandidates": [
                        candidate_summary,
                        {
                            "id": "another-reviewed-candidate",
                            "candidateSha256": "d" * 64,
                            "caseSource": case_source,
                        },
                    ],
                    "selectedCandidateCount": 2,
                    "review": {
                        "authority": "explicit-candidate-cohort-review",
                        "verdict": "approve-for-independent-case-construction",
                    },
                    "declaredRepresentative": False,
                    "automaticPromotion": False,
                },
            )
            cohort_selection = self.write(
                root,
                "candidate-selection.json",
                {
                    "schema": "agentlab.multi_repo_candidate_selection.v2",
                    "cohortId": "cohort-localization",
                    "cohortSha256": file_digest(candidate_cohort),
                    "candidateId": candidate["id"],
                    "candidateSha256": canonical_digest(candidate),
                    "caseSource": case_source,
                    "sourceSetSha256": "a" * 64,
                    "difficultyEvidenceSha256": file_digest(difficulty),
                    "methodRevision": "1" * 40,
                    "proposalMethodRevision": "2" * 40,
                    "declaredRepresentative": False,
                    "automaticPromotion": False,
                },
            )
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
                    "--cohort-selection",
                    str(cohort_selection),
                    "--candidate-cohort",
                    str(candidate_cohort),
                    "--semantic-packet",
                    str(semantic_packet),
                    "--semantic-decision",
                    str(semantic_decision),
                    "--semantic-gate",
                    str(semantic_gate),
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
            self.assertTrue(proposal["semanticAuthorization"]["allowsCaseContract"])
            self.assertEqual(proposal["semanticAuthorization"]["gateSha256"], file_digest(semantic_gate))
            self.assertEqual(
                proposal["lineage"]["candidateCohortSelectionSha256"],
                file_digest(cohort_selection),
            )
            self.assertEqual(
                proposal["lineage"]["candidateCohortSha256"],
                file_digest(candidate_cohort),
            )
            self.assertFalse(proposal["automaticPromotion"])

            drifted_selection = json.loads(cohort_selection.read_text())
            drifted_selection["candidateSha256"] = "c" * 64
            cohort_selection.write_text(json.dumps(drifted_selection, sort_keys=True) + "\n")
            drift_command = list(proposed.args)
            drift_command[-1] = str(root / "cohort-drift-proposal.json")
            drifted = subprocess.run(
                drift_command, text=True, capture_output=True
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("reviewed cohort selection candidate digest mismatch", drifted.stderr)
            self.assertFalse((root / "cohort-drift-proposal.json").exists())

            review = root / "review.json"
            decision = subprocess.run(
                [
                    sys.executable,
                    str(CREATE_REVIEW),
                    "--proposal",
                    str(proposal_path),
                    "--expected-sha256",
                    file_digest(proposal_path),
                    "--reviewer",
                    "independent-maintainer",
                    "--rationale",
                    "The selected calls and expanded lifecycle paths are a coherent calibration input.",
                    "--acknowledged-risk-ids",
                    ",".join(row["id"] for row in proposal["risks"]),
                    "--output",
                    str(review),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(decision.returncode, 0, decision.stderr)
            reviewed_path = root / "reviewed.json"
            reviewed = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW),
                    "--proposal",
                    str(proposal_path),
                    "--review",
                    str(review),
                    "--semantic-packet",
                    str(semantic_packet),
                    "--semantic-decision",
                    str(semantic_decision),
                    "--semantic-gate",
                    str(semantic_gate),
                    "--output",
                    str(reviewed_path),
                ],
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
                    "--semantic-packet",
                    str(semantic_packet),
                    "--semantic-decision",
                    str(semantic_decision),
                    "--semantic-gate",
                    str(semantic_gate),
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

            tampered_gate = json.loads(semantic_gate.read_text())
            tampered_gate["reviewer"] = "github:late-substitution"
            semantic_gate.write_text(json.dumps(tampered_gate, sort_keys=True) + "\n")
            rejected = subprocess.run(
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
                    "must-not-run-after-semantic-tamper",
                    "--localization",
                    str(reviewed_path),
                    "--localization-proposal",
                    str(proposal_path),
                    "--localization-review",
                    str(review),
                    "--semantic-packet",
                    str(semantic_packet),
                    "--semantic-decision",
                    str(semantic_decision),
                    "--semantic-gate",
                    str(semantic_gate),
                    "--output",
                    str(root / "tampered-construction"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("semantic gate validation failed", rejected.stderr)
            self.assertFalse((root / "tampered-construction").exists())

    def test_proposal_rejects_call_outside_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, selection_path = self.fixture(root)
            semantic_packet, semantic_decision, semantic_gate = self.semantic_authorization(root, difficulty)
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
                    "--semantic-packet",
                    str(semantic_packet),
                    "--semantic-decision",
                    str(semantic_decision),
                    "--semantic-gate",
                    str(semantic_gate),
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

    def test_proposal_rejects_deferred_semantic_gate_before_writing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, selection = self.fixture(root)
            packet, decision, gate = self.semantic_authorization(root, difficulty, approved=False)
            output = root / "proposal.json"
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
                    str(selection),
                    "--semantic-packet",
                    str(packet),
                    "--semantic-decision",
                    str(decision),
                    "--semantic-gate",
                    str(gate),
                    "--method-revision",
                    "b" * 40,
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not approved for case-contract proposal", result.stderr)
            self.assertFalse(output.exists())

    def test_proposal_rejects_tampered_semantic_gate_before_writing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, difficulty, facts, selection = self.fixture(root)
            packet, decision, gate = self.semantic_authorization(root, difficulty)
            tampered = json.loads(gate.read_text())
            tampered["reviewer"] = "github:substituted-reviewer"
            gate.write_text(json.dumps(tampered, sort_keys=True) + "\n")
            output = root / "proposal.json"
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
                    str(selection),
                    "--semantic-packet",
                    str(packet),
                    "--semantic-decision",
                    str(decision),
                    "--semantic-gate",
                    str(gate),
                    "--method-revision",
                    "b" * 40,
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("semantic gate validation failed", result.stderr)
            self.assertFalse(output.exists())

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

    def test_review_workflow_is_manual_trusted_main_and_secret_free(self):
        proposal = (ROOT / ".github/workflows/api-call-localization-proposal.yml").read_text()
        workflow = (ROOT / ".github/workflows/api-call-localization-review.yml").read_text()
        self.assertIn("multi-repo-candidate-cohort-review.yml", proposal)
        self.assertIn("multi-repo-candidate-semantic-review.yml", proposal)
        self.assertIn("scripts/multi-repo-analysis-run.py validate", proposal)
        self.assertIn("scripts/prepare-multi-repo-analysis-sources.py", proposal)
        self.assertIn("scripts/select-multi-repo-cohort-candidate.py", proposal)
        self.assertIn("--cohort-selection", proposal)
        self.assertIn("--candidate-cohort", proposal)
        self.assertIn("propose-api-call-case-localization.py", proposal)
        self.assertNotIn("secrets.", proposal)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.actor", workflow)
        self.assertIn("create-api-call-localization-review.py", workflow)
        self.assertIn("review-api-call-case-localization.py", workflow)
        self.assertIn("expected_proposal_sha256", workflow)
        self.assertIn("proposal_run_id", workflow)
        self.assertIn("api-call-localization-proposal.yml", workflow)
        self.assertIn("supply exactly one of qualification_path or proposal_run_id", workflow)
        self.assertIn("semantic_review_run_id", workflow)
        self.assertIn("expected_semantic_gate_sha256", workflow)
        self.assertIn("multi-repo-candidate-semantic-review.yml", workflow)
        self.assertIn("--semantic-gate", workflow)
        self.assertIn("acknowledged_risk_ids", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
