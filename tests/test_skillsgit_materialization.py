import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "skillsgit_materialization", ROOT / "scripts/materialize-skillsgit-maintainer-tree.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SkillsGitMaterializationTest(unittest.TestCase):
    def test_scope_skill_has_standard_sections_and_bounded_length(self):
        scope = {
            "pathBoundary": "features/example",
            "responsibility": "Maintain the example Harmony module.",
            "sourceRevision": "a" * 40,
            "buildEntrypoints": ["features/example/build-profile.json5"],
            "testEntrypoints": ["features/example/src/ohosTest/Ability.test.ets"],
        }
        fact = {
            "id": "fact",
            "interpretation": "The module exports one stable boundary and delegates lifecycle work.",
            "evidence": [{"path": "features/example/Index.ets", "gitBlobOid": "b" * 40}],
            "limitations": ["Build execution is unproved.", "Device behavior is unproved."],
        }
        skill_id, body = MODULE.render_scope_skill(
            "code-workshop", scope, {"maturity": "L2-semantic-ready"}, [fact],
        )
        self.assertEqual(skill_id, "code-workshop-features-example-maintenance")
        for section in ("## Purpose", "## Trigger", "## Workflow", "## Verification", "## Governance"):
            self.assertIn(section, body)
        self.assertLessEqual(len(body.splitlines()), 120)
        self.assertIn("Do not use as proof of build, device, or runtime behavior", body)

    def test_materializer_binds_tablegit_authority_in_its_receipt(self):
        source = (ROOT / "scripts/materialize-skillsgit-maintainer-tree.py").read_text()
        self.assertIn('"tableGitAuthority": cut["tableGitAuthority"]', source)
        self.assertIn('"tableGitRevision": cut["tableGitAuthority"]["revision"]', source)


if __name__ == "__main__":
    unittest.main()
