import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = (
    ROOT
    / "release/qualifications/code-workshop-7aa95cac-componentlibrary-build/build-qualification.json"
)
SPEC = importlib.util.spec_from_file_location(
    "maintainer_scope_build_qualification",
    ROOT / "scripts/validate-maintainer-scope-build-qualification.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerScopeBuildQualificationTests(unittest.TestCase):
    def receipt(self):
        return json.loads(QUALIFICATION.read_text())

    def test_real_componentlibrary_receipt_is_build_only_qualified(self):
        receipt = MODULE.validate(self.receipt())
        self.assertEqual(receipt["status"], "qualified")
        self.assertEqual(
            receipt["scope"]["scopeSkillIds"],
            ["skill-scope-code-workshop-componentlibrary-framework"],
        )
        self.assertEqual(receipt["scope"]["lane"], "build-only")
        self.assertEqual(receipt["build"]["task"], "assembleHar")
        self.assertTrue(receipt["build"]["canonicalContentReproducible"])
        self.assertFalse(receipt["build"]["rawArchiveReproducible"])
        self.assertFalse(receipt["qualificationScope"]["runtime"])
        self.assertFalse(receipt["qualificationScope"]["tests"])
        self.assertFalse(receipt["automaticPromotion"])

    def test_blocked_or_single_build_cannot_qualify(self):
        receipt = self.receipt()
        receipt["status"] = "blocked"
        with self.assertRaisesRegex(MODULE.QualificationError, "status must be qualified"):
            MODULE.validate(receipt)

        receipt = self.receipt()
        receipt["build"]["attempts"] = receipt["build"]["attempts"][:1]
        with self.assertRaisesRegex(MODULE.QualificationError, "exactly two clean build attempts"):
            MODULE.validate(receipt)

    def test_scope_binding_must_be_exact_and_single(self):
        receipt = self.receipt()
        receipt["scope"]["scopeSkillIds"].append("another-scope")
        with self.assertRaisesRegex(MODULE.QualificationError, "exactly one scopeSkillId"):
            MODULE.validate(receipt)

        receipt = self.receipt()
        receipt["scope"]["scopeSpecificBinding"] = False
        with self.assertRaisesRegex(MODULE.QualificationError, "scope-specific binding"):
            MODULE.validate(receipt)

    def test_canonical_member_content_must_match(self):
        receipt = self.receipt()
        receipt["build"]["attempts"][1]["canonicalMemberSha256"] = "0" * 64
        with self.assertRaisesRegex(MODULE.QualificationError, "identical canonical member content"):
            MODULE.validate(receipt)

    def test_build_only_receipt_cannot_claim_runtime_test_or_performance(self):
        for field in ("runtime", "tests", "performance"):
            receipt = self.receipt()
            receipt["qualificationScope"][field] = True
            with self.assertRaises(MODULE.QualificationError):
                MODULE.validate(receipt)


if __name__ == "__main__":
    unittest.main()
