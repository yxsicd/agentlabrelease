import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "agent_flywheel", ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerSkillAgentFlywheelTest(unittest.TestCase):
    def test_workflow_defaults_to_the_code_workshop_focus_repository(self):
        workflow = (ROOT / ".github/workflows/maintainer-skill-agent-flywheel.yml").read_text()
        repository_input = workflow.split("      repository:\n", 1)[1].split(
            "      iterations:\n", 1
        )[0]
        self.assertIn("        default: code-workshop\n", repository_input)

    def test_scope_checkout_materializes_only_exact_requested_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
            (source / "wanted").mkdir()
            (source / "wanted" / "main.ets").write_text("wanted\n")
            (source / "sibling").mkdir()
            (source / "sibling" / "large.bin").write_bytes(b"x" * 4096)
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip()
            bare = root / "remote.git"
            subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True)
            subprocess.run(
                ["git", "-C", str(bare), "config", "uploadpack.allowFilter", "true"], check=True
            )
            destination = root / "checkout"
            subprocess.run([
                str(ROOT / "scripts/checkout-maintainer-scope.sh"),
                bare.as_uri(), revision, "wanted", str(destination),
            ], check=True)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
                ).strip(),
                revision,
            )
            self.assertTrue((destination / "wanted/main.ets").is_file())
            self.assertFalse((destination / "sibling").exists())
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(destination), "status", "--porcelain"], text=True
                ),
                "",
            )
            root_checkout = root / "root-checkout"
            subprocess.run([
                str(ROOT / "scripts/checkout-maintainer-scope.sh"),
                bare.as_uri(), revision, ".", str(root_checkout),
            ], check=True)
            self.assertTrue((root_checkout / "wanted/main.ets").is_file())
            self.assertTrue((root_checkout / "sibling/large.bin").is_file())

    def test_selection_prefers_small_tested_unbound_scope(self):
        scopes = [
            {"id": "large", "repositoryId": "r", "pathBoundary": "large", "sourceFileCount": 40, "testFileCount": 8, "evidence": [{"path": "large/main.rs"}]},
            {"id": "small-no-tests", "repositoryId": "r", "pathBoundary": "small", "sourceFileCount": 2, "testFileCount": 0, "evidence": [{"path": "small/main.rs"}]},
            {"id": "small-tested", "repositoryId": "r", "pathBoundary": "tested", "sourceFileCount": 3, "testFileCount": 1, "evidence": [{"path": "tested/main.rs"}]},
        ]
        assessment = {"skills": [
            {"skillId": "large", "maturity": "L1-structural-ready"},
            {"skillId": "small-no-tests", "maturity": "L1-structural-ready"},
            {"skillId": "small-tested", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_scope(scopes, assessment, "r")["id"], "small-tested")

    def test_selection_skips_scope_whose_inventory_evidence_is_outside_boundary(self):
        scopes = [
            {"id": "broken", "repositoryId": "r", "pathBoundary": "entry/_build", "sourceFileCount": 1,
             "testFileCount": 1, "evidence": [{"path": "entry/build-profile.json5"}]},
            {"id": "reachable", "repositoryId": "r", "pathBoundary": "entry/src", "sourceFileCount": 2,
             "testFileCount": 0, "evidence": [{"path": "entry/src/main.ets"}]},
        ]
        assessment = {"skills": [
            {"skillId": "broken", "maturity": "L1-structural-ready"},
            {"skillId": "reachable", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_scope(scopes, assessment, "r")["id"], "reachable")

    def test_convergence_plan_explains_every_scope_without_repository_branches(self):
        scopes = [
            {"id": "ready", "repositoryId": "arbitrary-repository", "pathBoundary": "src", "sourceFileCount": 3,
             "testFileCount": 1, "evidence": [{"path": "src/main.rs"}]},
            {"id": "large", "repositoryId": "arbitrary-repository", "pathBoundary": "library", "sourceFileCount": 81,
             "testFileCount": 0, "evidence": [{"path": "library/lib.rs"}]},
            {"id": "config", "repositoryId": "arbitrary-repository", "pathBoundary": "config", "sourceFileCount": 0,
             "testFileCount": 0, "evidence": [{"path": "config/app.json"}]},
            {"id": "done", "repositoryId": "arbitrary-repository", "pathBoundary": "done", "sourceFileCount": 2,
             "testFileCount": 0, "evidence": [{"path": "done/mod.rs"}]},
        ]
        assessment = {"skills": [
            {"skillId": "ready", "maturity": "L1-structural-ready"},
            {"skillId": "large", "maturity": "L1-structural-ready"},
            {"skillId": "config", "maturity": "L1-structural-ready"},
            {"skillId": "done", "maturity": "L2-semantic-ready"},
        ]}
        plan = MODULE.repository_plan(scopes, assessment, "arbitrary-repository", "a" * 40)
        plan["sourceAssessmentSha256"] = "b" * 64
        schema = json.loads((ROOT / "schemas/maintainer-skill-convergence-plan.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema"]["const"], plan["schema"])
        self.assertEqual(set(schema["required"]), set(plan))
        self.assertEqual(plan["summary"], {"scopeCount": 4, "eligible": 2, "blocked": 1, "alreadyAdvanced": 1})
        self.assertEqual(plan["decision"], "advance-eligible-scopes")
        blockers = {row["skillId"]: row.get("blockerCode") for row in plan["scopes"]}
        self.assertEqual(blockers["large"], "MS-SCOPE-DECOMPOSITION-REQUIRED")
        modes = {row["skillId"]: row["analysisMode"] for row in plan["scopes"]}
        self.assertEqual(modes["config"], "configuration-asset")
        self.assertEqual(modes["ready"], "source-behavior")
        self.assertFalse(plan["selectionPolicy"]["repositorySpecificBranches"])

    def test_root_scope_uses_repository_contract_mode_and_root_evidence(self):
        scope = {"id": "root", "repositoryId": "r", "pathBoundary": ".", "sourceFileCount": 1,
                 "testFileCount": 0, "evidence": [{"path": "build.json"}]}
        state = {"maturity": "L1-structural-ready"}
        result = MODULE.classify_scope(scope, state)
        self.assertEqual(result["disposition"], "eligible")
        self.assertEqual(result["analysisMode"], "repository-contract")
        self.assertTrue(MODULE.path_is_within("any/nested/file", "."))

    def test_configuration_proposal_uses_only_required_dimensions(self):
        request = {
            "repository": {"id": "r", "revision": "a" * 40},
            "scope": {"id": "config", "pathBoundary": "config"},
            "requiredDimensions": ["boundary", "relations", "responsibility"],
            "sourceAssessment": {"sha256": "b" * 64},
        }
        proposal = {
            "schema": "agentlab.maintainer_skill_fact_proposal.v1",
            "id": "agent-analysis-generic-config-contract",
            "repositoryId": "r", "sourceRevision": "a" * 40,
            "scopeSkillIds": ["config"], "kind": "analysis",
            "dimensions": ["responsibility", "boundary", "relations"],
            "interpretation": "Configuration owns a declared application boundary and relates its inputs to direct consumers. " * 2,
            "evidence": [
                {"path": "config/a.json", "gitBlobOid": "1" * 40},
                {"path": "config/b.json", "gitBlobOid": "2" * 40},
            ],
            "limitations": ["Runtime use is not executed.", "Build success is not established."],
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
            (source / "config").mkdir()
            (source / "config/a.json").write_text("{}\n")
            (source / "config/b.json").write_text("{}\n")
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            request["repository"]["revision"] = revision
            proposal["sourceRevision"] = revision
            for evidence in proposal["evidence"]:
                evidence["gitBlobOid"] = subprocess.check_output(
                    ["git", "-C", str(source), "rev-parse", f"HEAD:{evidence['path']}"], text=True
                ).strip()
            fact = MODULE.validate_proposal(request, proposal, source)
        self.assertEqual(fact["dimensions"], ["boundary", "relations", "responsibility"])

    def test_auto_repository_selection_prefers_lowest_normalized_coverage(self):
        scopes = [
            {"id": "a1", "repositoryId": "a", "pathBoundary": "a1", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "a1/main.ets"}]},
            {"id": "a2", "repositoryId": "a", "pathBoundary": "a2", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "a2/main.ets"}]},
            {"id": "b1", "repositoryId": "b", "pathBoundary": "b1", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "b1/main.ets"}]},
            {"id": "b2", "repositoryId": "b", "pathBoundary": "b2", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "b2/main.ets"}]},
        ]
        assessment = {"skills": [
            {"skillId": "a1", "maturity": "L2-semantic-ready"},
            {"skillId": "a2", "maturity": "L1-structural-ready"},
            {"skillId": "b1", "maturity": "L1-structural-ready"},
            {"skillId": "b2", "maturity": "L1-structural-ready"},
        ]}
        self.assertEqual(MODULE.select_repository(scopes, assessment, ["a", "b"]), "b")

    def test_local_entrypoint_can_converge_all_current_eligible_scopes(self):
        script = (ROOT / "scripts/run-maintainer-skill-local-flywheel.sh").read_text()
        loop = (ROOT / "scripts/run-maintainer-skill-agent-loop.sh").read_text()
        self.assertIn("iterations == converge", script)
        self.assertIn("convergence-plan.json", script)
        self.assertIn("convergence-report.json", script)
        self.assertIn(".summary.eligible", script)
        self.assertIn("AGENTLAB_MAX_ITERATIONS=64", script)
        self.assertIn("max_iterations=${AGENTLAB_MAX_ITERATIONS:-3}", loop)

    def test_agent_prompt_names_the_exact_evidence_object_schema(self):
        source = (ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py").read_text()
        self.assertIn("the keys path and gitBlobOid", source)
        self.assertIn("never repositoryPath", source)
        self.assertIn("no other evidence fields are allowed", source)

    def test_agent_prompt_has_a_bounded_exploration_budget(self):
        source = (ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py").read_text()
        self.assertIn("Use at most 24 shell tool calls", source)
        self.assertIn("do not enumerate or read the whole repository", source)
        self.assertIn("Reserve the final two tool calls", source)
        self.assertIn("tool_call_limit=24", source)

    def test_compare_requires_one_l2_gain_without_l3_promotion(self):
        before = {
            "totals": {"scopeSkillCount": 5, "structuralReadyCount": 5, "programBoundCount": 1,
                       "semanticReadyCount": 1, "maintenanceReadyCount": 0}
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before_path = root / "before.json"
            before_path.write_text(json.dumps(before) + "\n")
            after = {
                "parentAssessmentSha256": MODULE.digest(before_path),
                "totals": {"scopeSkillCount": 5, "structuralReadyCount": 5, "programBoundCount": 2,
                           "semanticReadyCount": 2, "maintenanceReadyCount": 0},
            }
            after_path = root / "after.json"
            after_path.write_text(json.dumps(after) + "\n")
            output = root / "result.json"
            MODULE.compare(type("Args", (), {"before": before_path, "after": after_path, "output": output}))
            self.assertEqual(json.loads(output.read_text())["decision"], "review-proposed-knowledge")

    def test_compare_accepts_semantic_gain_for_an_already_bound_scope(self):
        before = {
            "totals": {"scopeSkillCount": 5, "structuralReadyCount": 5, "programBoundCount": 2,
                       "semanticReadyCount": 1, "maintenanceReadyCount": 0}
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before_path = root / "before.json"
            before_path.write_text(json.dumps(before) + "\n")
            after = {
                "parentAssessmentSha256": MODULE.digest(before_path),
                "totals": {"scopeSkillCount": 5, "structuralReadyCount": 5, "programBoundCount": 2,
                           "semanticReadyCount": 2, "maintenanceReadyCount": 0},
            }
            after_path = root / "after.json"
            after_path.write_text(json.dumps(after) + "\n")
            output = root / "result.json"
            MODULE.compare(type("Args", (), {"before": before_path, "after": after_path, "output": output}))
            self.assertEqual(json.loads(output.read_text())["decision"], "review-proposed-knowledge")


if __name__ == "__main__":
    unittest.main()
