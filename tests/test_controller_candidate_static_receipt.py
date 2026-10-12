import ast
import copy
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "scripts/validate-release.py").read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "validate_candidate_static_build")
namespace = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "scripts/validate-release.py"), "exec"), namespace)
check = namespace["validate_candidate_static_build"]


class CandidateStaticReceiptTests(unittest.TestCase):
    def setUp(self):
        self.build = {"target": "x86_64-unknown-linux-musl", "interpreterSegments": 0,
                      "neededDynamicLibraries": 0, "staticCrt": True, "relocationModel": "static"}
        self.receipt = {"download": {"anonymous": True, "usedFinalGitHubReleaseUrls": True,
                         "independentFromUpload": True, "staticElfVerified": True,
                         "binaryExecuted": False, "installed": False, "elfInterpreterSegments": 0,
                         "elfDynamicSegments": 0, "elfNeededLibraries": 0}}

    def test_legacy_static_evidence_retains_its_original_gate(self):
        legacy = {"target": "x86_64-unknown-linux-musl", "interpreterSegments": 0, "dynamicSegments": 0}
        check(legacy, None)
        legacy["dynamicSegments"] = 1
        with self.assertRaises(AssertionError):
            check(legacy, None)

    def test_new_descriptor_requires_independent_public_bytes(self):
        check(self.build, self.receipt)
        with self.assertRaises(AssertionError):
            check(self.build, None)

    def test_each_new_elf_or_authority_drift_is_rejected(self):
        changes = [("anonymous", False), ("usedFinalGitHubReleaseUrls", False),
                   ("independentFromUpload", False), ("staticElfVerified", False),
                   ("binaryExecuted", True), ("installed", True), ("elfInterpreterSegments", 1),
                   ("elfDynamicSegments", 1), ("elfNeededLibraries", 1)]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                changed = copy.deepcopy(self.receipt)
                changed["download"][key] = value
                check(self.build, changed)

    def test_new_build_cannot_omit_or_replace_static_identity(self):
        for key, value in [("staticCrt", False), ("relocationModel", "pic"),
                           ("interpreterSegments", 1), ("neededDynamicLibraries", 1)]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                changed = dict(self.build)
                changed[key] = value
                check(changed, self.receipt)
        changed = dict(self.build)
        del changed["neededDynamicLibraries"]
        with self.assertRaises(KeyError):
            check(changed, self.receipt)


if __name__ == "__main__":
    unittest.main()
