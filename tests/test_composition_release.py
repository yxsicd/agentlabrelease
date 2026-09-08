import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validator", ROOT / "scripts/validate-composition-release.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ReferenceReleaseTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "release/candidates/e921d102-linux-x64"
        self.publication = json.loads((path / "publication.json").read_text())
        self.raw = (path / "environment-lock.json").read_bytes()
        self.lock = json.loads(self.raw)

    def check(self, publication=None, lock=None):
        return validator.validate(publication or self.publication, lock or self.lock, self.raw)

    def test_candidate_retains_failed_gate_without_claiming_qualification(self):
        self.assertEqual(len(self.check()), 11)
        self.publication["status"] = "qualified"
        with self.assertRaisesRegex(ValueError, "unpassed"):
            self.check()

    def test_rehosted_payload_is_rejected(self):
        self.publication["tag"] = "runtime-e921d102-linux-x64"
        with self.assertRaisesRegex(ValueError, "host component"):
            self.check()

    def test_candidate_cannot_self_classify_rehosted_payload(self):
        self.publication["tag"] = "runtime-e921d102-linux-x64"
        self.publication["retainedSameTagReferences"] = [self.publication["assets"][0]["url"]]
        with self.assertRaisesRegex(ValueError, "host component"):
            self.check()

    def test_digest_drift_is_rejected(self):
        self.publication["assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "archive digest"):
            self.check()

    def test_missing_descriptor_is_rejected(self):
        self.publication["assets"].pop(1)
        with self.assertRaisesRegex(ValueError, "missing component"):
            self.check()

    def test_incompatible_provider_is_rejected(self):
        graph = self.lock["componentGraph"]
        graph["nodes"][-1]["provides"]["mcpgit.session-template-contract"] = 2
        graph["resolvedContracts"]["linux-x64"]["mcpgit.session-template-contract"] = 2
        with self.assertRaisesRegex(ValueError, "unsatisfied"):
            self.check()

    def test_untrusted_download_url_is_rejected(self):
        for url in ["http://github.com/a", "https://example.com/payload", "https://github.com/yxsicd/agentlabrelease/releases/download/a/b?token=x"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validator.asset_location(url)


if __name__ == "__main__":
    unittest.main()
