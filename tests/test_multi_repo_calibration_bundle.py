import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/multi-repo-calibration-bundle.py"
SPEC = importlib.util.spec_from_file_location("multi_repo_calibration_bundle", SCRIPT)
BUNDLE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BUNDLE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MultiRepoCalibrationBundleTest(unittest.TestCase):
    def prepare(self, root: Path):
        source = ROOT / "examples/multi-repo-case"
        bundle_source = root / "source"
        bundle_source.mkdir()
        for name in ("calibrate.py", "oracle.mjs", "calibration-bundle.json"):
            shutil.copyfile(source / name, bundle_source / name)
        shutil.copytree(source / "reference", bundle_source / "reference")
        shutil.copytree(source / "alternatives", bundle_source / "alternatives")
        contract = root / "construction-contract.json"
        contract.write_text(json.dumps({
            "schema": "agentlab.multi_repo_construction_contract.v1",
            "status": "reviewed-for-model-construction",
            "candidateId": "fixture-candidate",
            "candidateSha256": "b" * 64,
            "sourceSetSha256": "a" * 64,
            "oracleContract": json.loads((source / "oracle-contract.json").read_text()),
            "automaticPromotion": False,
        }, indent=2, sort_keys=True) + "\n")
        descriptor = bundle_source / "calibration-bundle.json"
        proposal = root / "proposal.json"
        proposal.write_text(json.dumps(
            BUNDLE.propose(bundle_source, descriptor, contract), indent=2, sort_keys=True
        ) + "\n")
        review = root / "review.json"
        review.write_text(json.dumps(BUNDLE.decide(
            proposal,
            sha256(proposal),
            "maintainer-a",
            ",".join(sorted(BUNDLE.RISK_IDS)),
            "These exact executable and reference bytes are suitable for retained calibration.",
        ), indent=2, sort_keys=True) + "\n")
        reviewed = root / "calibration-bundle.json"
        reviewed.write_text(json.dumps(
            BUNDLE.compile_contract(proposal, review), indent=2, sort_keys=True
        ) + "\n")
        return bundle_source, descriptor, contract, proposal, review, reviewed

    def test_review_stage_validate_and_execute_exact_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_source, descriptor, construction, proposal, review, contract = self.prepare(root)
            BUNDLE.validate(contract, proposal, review, bundle_source, descriptor, construction)
            staged = root / "staged"
            BUNDLE.stage(bundle_source, descriptor, construction, proposal, staged)
            BUNDLE.validate(
                contract, proposal, review, staged, staged / "descriptor.json",
                staged / "construction-contract.json",
            )
            output = root / "calibration"
            receipt = BUNDLE.run_bundle(
                staged, contract, proposal, review, staged / "construction-contract.json",
                ROOT / "examples/multi-repo-case/baseline", output,
            )
            self.assertEqual(receipt["status"], "passed")
            self.assertFalse(receipt["automaticPromotion"])
            self.assertEqual(receipt["oracleSha256"], sha256(staged / "oracle.mjs"))
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(set(summary["variants"]), {"baseline", "reference", "equivalent-policy-loop", "hardcoded-premium", "stale-consumer"})
            self.assertEqual(summary["variantRoles"]["equivalent-policy-loop"], "alternative-valid")
            self.assertTrue(all(
                row["pass"]
                for row in summary["variants"]["equivalent-policy-loop"]["stages"].values()
            ))
            self.assertEqual(receipt["alternativeTrees"][0]["id"], "equivalent-policy-loop")
            self.assertTrue(summary["variants"]["stale-consumer"]["stages"]["turn-1"]["pass"])
            self.assertFalse(summary["variants"]["stale-consumer"]["stages"]["turn-2"]["pass"])

    def test_tampered_oracle_and_incomplete_risk_review_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_source, descriptor, construction, proposal, _review, _contract = self.prepare(root)
            with self.assertRaisesRegex(BUNDLE.BundleError, "acknowledge every"):
                BUNDLE.decide(
                    proposal, sha256(proposal), "maintainer-a", "driver-semantics-unverified",
                    "This deliberately incomplete review must fail closed before calibration.",
                )
            (bundle_source / "oracle.mjs").write_text("tampered\n")
            with self.assertRaisesRegex(BUNDLE.BundleError, "Oracle bytes differ"):
                BUNDLE.propose(bundle_source, descriptor, construction)

    def test_alternative_solution_tamper_and_role_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_source, descriptor, construction, _proposal, _review, _contract = self.prepare(root)
            value = json.loads(descriptor.read_text())
            value["variantRoles"]["equivalent-policy-loop"] = "wrong"
            descriptor.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(BUNDLE.BundleError, "alternative valid solution"):
                BUNDLE.propose(bundle_source, descriptor, construction)

            value["variantRoles"]["equivalent-policy-loop"] = "alternative-valid"
            descriptor.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            alternative = bundle_source / "alternatives/equivalent-policy-loop/app/src/checkout.ts"
            alternative.write_text(alternative.read_text() + "\n// tampered after proposal\n")
            with self.assertRaisesRegex(BUNDLE.BundleError, "proposal differs from exact inputs"):
                BUNDLE.stage(bundle_source, descriptor, construction, _proposal, root / "staged")

    def test_portable_source_receipt_binds_repository_revision_and_every_staged_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_source, descriptor, construction, proposal, _review, _contract = self.prepare(root)
            staged = root / "staged"
            BUNDLE.stage(bundle_source, descriptor, construction, proposal, staged)
            receipt_path = root / "source-receipt.json"
            receipt = BUNDLE.portable_source_receipt(
                staged,
                construction,
                "https://github.com/acme/calibration-cases.git",
                "1" * 40,
                "cases/checkout-policy",
            )
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            validated = BUNDLE.validate_portable_source_receipt(receipt_path, staged, construction)
            self.assertEqual(validated["status"], "staged-for-calibration-proposal")
            self.assertFalse(validated["automaticPromotion"])
            self.assertEqual(validated["source"]["revision"], "1" * 40)
            self.assertEqual(
                {row["path"] for row in validated["files"]},
                {path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()},
            )
            portable_proposal = BUNDLE.propose(
                staged, staged / "descriptor.json", construction, receipt_path
            )
            self.assertEqual(portable_proposal["portableSource"]["receiptSha256"], sha256(receipt_path))
            self.assertEqual(
                portable_proposal["portableSource"]["fileManifestSha256"],
                validated["fileManifestSha256"],
            )
            portable_proposal_path = root / "portable-proposal.json"
            portable_proposal_path.write_text(
                json.dumps(portable_proposal, indent=2, sort_keys=True) + "\n"
            )
            portable_review_path = root / "portable-review.json"
            portable_review_path.write_text(json.dumps(BUNDLE.decide(
                portable_proposal_path,
                sha256(portable_proposal_path),
                "maintainer-portable",
                ",".join(sorted(BUNDLE.RISK_IDS)),
                "The exact portable source and executable bytes are approved for calibration.",
            ), indent=2, sort_keys=True) + "\n")
            portable_contract_path = root / "portable-contract.json"
            portable_contract_path.write_text(json.dumps(BUNDLE.compile_contract(
                portable_proposal_path, portable_review_path
            ), indent=2, sort_keys=True) + "\n")
            BUNDLE.validate(
                portable_contract_path,
                portable_proposal_path,
                portable_review_path,
                staged,
                staged / "descriptor.json",
                construction,
                receipt_path,
            )

            (staged / "oracle.mjs").write_text("tampered after source receipt\n")
            with self.assertRaisesRegex(BUNDLE.BundleError, "Oracle bytes differ|receipt differs"):
                BUNDLE.validate_portable_source_receipt(receipt_path, staged, construction)

    def test_portable_source_rejects_mutable_or_credential_bearing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_source, descriptor, construction, proposal, _review, _contract = self.prepare(root)
            staged = root / "staged"
            BUNDLE.stage(bundle_source, descriptor, construction, proposal, staged)
            with self.assertRaisesRegex(BUNDLE.BundleError, "public GitHub HTTPS"):
                BUNDLE.portable_source_receipt(
                    staged, construction, "https://token@github.com/acme/cases.git", "1" * 40, "case"
                )
            with self.assertRaisesRegex(BUNDLE.BundleError, "full Git SHA"):
                BUNDLE.portable_source_receipt(
                    staged, construction, "https://github.com/acme/cases.git", "main", "case"
                )
            with self.assertRaisesRegex(BUNDLE.BundleError, "unsafe"):
                BUNDLE.portable_source_receipt(
                    staged, construction, "https://github.com/acme/cases.git", "1" * 40, "../case"
                )

    def test_workflows_keep_proposal_review_execution_and_freeze_separate(self):
        proposal = (ROOT / ".github/workflows/multi-repo-calibration-bundle-proposal.yml").read_text()
        source = (ROOT / ".github/workflows/multi-repo-calibration-bundle-source.yml").read_text()
        review = (ROOT / ".github/workflows/multi-repo-calibration-bundle-review.yml").read_text()
        freeze = (ROOT / ".github/workflows/multi-repo-case-review.yml").read_text()
        self.assertNotIn("AGENTLAB_LM_GATEWAY_KEY", source + proposal + review + freeze)
        self.assertIn("source-receipt", source)
        self.assertIn("SOURCE_REVISION", source)
        self.assertIn("rev-parse HEAD", source)
        self.assertIn("multi-repo-calibration-bundle-source.yml", proposal)
        self.assertIn("validate-source-receipt", proposal)
        self.assertIn("expected_bundle_source_sha256", proposal)
        self.assertIn("multi-repo-calibration-bundle.py stage", proposal)
        self.assertIn("calibration-bundle-source.json", review)
        self.assertIn("--source-receipt", review)
        self.assertIn("calibration-bundle-source.json", freeze)
        self.assertIn("--source-receipt", freeze)
        self.assertIn("expected_proposal_sha256", review)
        self.assertIn("multi-repo-calibration-bundle.py validate", review)
        self.assertIn("calibration_bundle_review_run_id", freeze)
        self.assertIn("multi-repo-calibration-bundle.py run", freeze)
        self.assertIn("--calibration-run", freeze)
        self.assertNotIn("source/operator-fixture", freeze)
        self.assertIn("source/cohort/source/analysis-source/analysis/difficulty_candidates.json", freeze)


if __name__ == "__main__":
    unittest.main()
