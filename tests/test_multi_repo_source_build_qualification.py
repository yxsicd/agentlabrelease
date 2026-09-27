from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


VALIDATE = load_module(
    "multi_repo_source_build_qualification",
    ROOT / "scripts/validate-multi-repo-source-build-qualification.py",
)
QUALIFICATION = (
    ROOT
    / "release/qualifications/alpha13-payment-feedback-analysis-165bcbd/build-qualification.json"
)
PACKET = (
    ROOT
    / "release/qualifications/alpha13-payment-feedback-analysis-165bcbd/review-packets/purchase-data.json"
)


class MultiRepoSourceBuildQualificationTests(unittest.TestCase):
    def receipt(self):
        return json.loads(QUALIFICATION.read_text())

    def packet(self):
        return json.loads(PACKET.read_text())

    def validate(self, receipt):
        VALIDATE.validate(receipt, self.packet(), VALIDATE.digest(PACKET))

    def test_retained_qualification_is_exact_and_non_promoting(self):
        receipt = self.receipt()
        self.validate(receipt)
        by_id = {root["id"]: root for root in receipt["roots"]}
        self.assertEqual(by_id["harmony-entry"]["status"], "passed")
        self.assertEqual(by_id["harmony-entry"]["artifacts"][0]["kind"], "unsigned-hap")
        self.assertEqual(by_id["cordova-plugin-hms-iap"]["status"], "failed")
        self.assertEqual(by_id["ionic-iap-example"]["status"], "failed")
        self.assertFalse(receipt["allowsCaseContract"])
        self.assertFalse(receipt["automaticPromotion"])

    def test_unbound_root_is_rejected(self):
        receipt = self.receipt()
        receipt["roots"][0]["candidatePath"] = "unrelated"
        with self.assertRaisesRegex(VALIDATE.QualificationError, "not packet-bound"):
            self.validate(receipt)

    def test_failed_root_cannot_claim_artifact(self):
        receipt = self.receipt()
        failed = copy.deepcopy(receipt["roots"][1])
        failed["artifacts"] = [{"kind": "bundle", "sha256": "a" * 64, "size": 1}]
        receipt["roots"][1] = failed
        with self.assertRaisesRegex(VALIDATE.QualificationError, "claims an artifact"):
            self.validate(receipt)

    def test_non_direct_route_is_rejected(self):
        receipt = self.receipt()
        receipt["environment"]["routeDecision"] = "cached_topology"
        with self.assertRaisesRegex(VALIDATE.QualificationError, "not peer direct"):
            self.validate(receipt)


if __name__ == "__main__":
    unittest.main()
