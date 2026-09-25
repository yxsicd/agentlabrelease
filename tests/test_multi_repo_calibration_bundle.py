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
            self.assertEqual(set(summary["variants"]), {"baseline", "reference", "hardcoded-premium", "stale-consumer"})
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

    def test_workflows_keep_proposal_review_execution_and_freeze_separate(self):
        proposal = (ROOT / ".github/workflows/multi-repo-calibration-bundle-proposal.yml").read_text()
        review = (ROOT / ".github/workflows/multi-repo-calibration-bundle-review.yml").read_text()
        freeze = (ROOT / ".github/workflows/multi-repo-case-review.yml").read_text()
        self.assertNotIn("AGENTLAB_LM_GATEWAY_KEY", proposal + review + freeze)
        self.assertIn("multi-repo-calibration-bundle.py stage", proposal)
        self.assertIn("expected_proposal_sha256", review)
        self.assertIn("multi-repo-calibration-bundle.py validate", review)
        self.assertIn("calibration_bundle_review_run_id", freeze)
        self.assertIn("multi-repo-calibration-bundle.py run", freeze)
        self.assertIn("--calibration-run", freeze)
        self.assertNotIn("source/operator-fixture", freeze)
        self.assertIn("source/cohort/source/analysis-source/analysis/difficulty_candidates.json", freeze)


if __name__ == "__main__":
    unittest.main()
