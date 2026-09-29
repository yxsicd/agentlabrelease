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
    def test_agent_proposal_is_parsed_only_from_an_exact_json_object(self):
        proposal = {"schema": "agentlab.maintainer_skill_fact_proposal.v1"}
        self.assertEqual(MODULE.parse_agent_proposal(json.dumps(proposal)), proposal)
        with self.assertRaisesRegex(ValueError, "exactly one JSON proposal"):
            MODULE.parse_agent_proposal("```json\n{}\n```")
        with self.assertRaisesRegex(ValueError, "exactly one JSON proposal"):
            MODULE.parse_agent_proposal("proposal follows: {}")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            MODULE.parse_agent_proposal("[]")

    def test_agent_attempt_lifecycle_aggregates_one_format_finalization(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            initial = {
                "startedAt": "2026-01-01T00:00:00Z", "endedAt": "2026-01-01T00:01:00Z",
                "durationMs": 60000, "maxToolCalls": 24, "startedToolCalls": 8,
                "completedToolCalls": 8, "toolCallBudgetExceeded": False,
                "timedOut": False, "exitCode": 0, "finalAssistantTextPresent": False,
            }
            finalizer = {
                "startedAt": "2026-01-01T00:01:00Z", "endedAt": "2026-01-01T00:01:05Z",
                "durationMs": 5000, "maxToolCalls": 1, "startedToolCalls": 0,
                "completedToolCalls": 0, "toolCallBudgetExceeded": False,
                "timedOut": False, "exitCode": 0, "finalAssistantTextPresent": True,
            }
            (evidence / "maintainer-skill-author-lifecycle.json").write_text(
                json.dumps(initial))
            (evidence / "maintainer-skill-author-finalize-lifecycle.json").write_text(
                json.dumps(finalizer))
            result = MODULE.write_agent_attempt_lifecycle(
                evidence, True, "Agent final response did not contain a proposal")
            self.assertEqual(result["durationMs"], 65000)
            self.assertEqual(result["maxToolCalls"], 25)
            self.assertEqual(result["startedToolCalls"], 8)
            self.assertTrue(result["finalizationUsed"])
            self.assertTrue(result["finalAssistantTextPresent"])

    def test_workflow_defaults_to_the_code_workshop_focus_repository(self):
        workflow = (ROOT / ".github/workflows/maintainer-skill-agent-flywheel.yml").read_text()
        repository_input = workflow.split("      repository:\n", 1)[1].split(
            "      iterations:\n", 1
        )[0]
        self.assertIn("        default: code-workshop\n", repository_input)
        self.assertIn("AGENTLAB_SCOPE_BATCH_SIZE: ${{ inputs.scope_batch_size }}", workflow)
        self.assertIn("        default: '3'\n", workflow.split("      scope_batch_size:\n", 1)[1])

    def test_workflow_exposes_reviewed_scope_rewrite_without_agent_runtime(self):
        workflow = (ROOT / ".github/workflows/maintainer-skill-agent-flywheel.yml").read_text()
        self.assertIn("options: [expand, focused-refresh, scope-rewrite]", workflow)
        self.assertIn("if: inputs.mode != 'scope-rewrite'", workflow)
        self.assertIn("scripts/run-maintainer-scope-catalog-rewrite.sh", workflow)
        self.assertIn("steps.rewrite.outputs.snapshot", workflow)

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
            (source / "root-contract.json").write_text('{"modules": ["wanted"]}\n')
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
            self.assertTrue((root_checkout / "root-contract.json").is_file())
            self.assertFalse((root_checkout / "wanted").exists())
            self.assertFalse((root_checkout / "sibling").exists())

            request = root / "scope-request.json"
            request.write_text(json.dumps({"scope": {
                "pathBoundary": "wanted",
                "ownershipSelectors": [
                    {"type": "prefix", "path": "wanted"},
                    {"type": "files", "paths": ["root-contract.json"]},
                ],
            }}))
            composite_checkout = root / "composite-checkout"
            subprocess.run([
                str(ROOT / "scripts/checkout-maintainer-scope.sh"),
                bare.as_uri(), revision, "wanted", str(composite_checkout), str(request),
            ], check=True)
            self.assertTrue((composite_checkout / "wanted/main.ets").is_file())
            self.assertTrue((composite_checkout / "root-contract.json").is_file())
            self.assertFalse((composite_checkout / "sibling").exists())

            batch_request = root / "batch-request.json"
            batch_request.write_text(json.dumps({
                "schema": "agentlab.maintainer_skill_agent_batch_request.v1",
                "requests": [
                    {"scope": {"pathBoundary": "wanted"}},
                    {"scope": {"pathBoundary": "root", "ownershipSelectors": [
                        {"type": "files", "paths": ["root-contract.json"]},
                    ]}},
                ],
            }))
            batch_checkout = root / "batch-checkout"
            subprocess.run([
                str(ROOT / "scripts/checkout-maintainer-scope.sh"),
                bare.as_uri(), revision, "wanted", str(batch_checkout), str(batch_request),
            ], check=True)
            self.assertTrue((batch_checkout / "wanted/main.ets").is_file())
            self.assertTrue((batch_checkout / "root-contract.json").is_file())
            self.assertFalse((batch_checkout / "sibling").exists())

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

    def test_batch_selection_is_bounded_deterministic_and_keeps_root_isolated(self):
        scopes = [
            {"id": "tested-b", "repositoryId": "r", "pathBoundary": "b", "sourceFileCount": 4,
             "testFileCount": 1, "evidence": [{"path": "b/main.rs"}]},
            {"id": "tested-a", "repositoryId": "r", "pathBoundary": "a", "sourceFileCount": 3,
             "testFileCount": 1, "evidence": [{"path": "a/main.rs"}]},
            {"id": "plain", "repositoryId": "r", "pathBoundary": "plain", "sourceFileCount": 1,
             "testFileCount": 0, "evidence": [{"path": "plain/main.rs"}]},
        ]
        assessment = {"skills": [
            {"skillId": row["id"], "maturity": "L1-structural-ready"} for row in scopes
        ]}
        self.assertEqual(
            [row["id"] for row in MODULE.select_scope_batch(scopes, assessment, "r", 2)],
            ["tested-a", "tested-b"],
        )
        root = {"id": "root", "repositoryId": "r", "pathBoundary": ".", "sourceFileCount": 1,
                "testFileCount": 2, "evidence": [{"path": "build.json"}]}
        assessment["skills"].append({"skillId": "root", "maturity": "L1-structural-ready"})
        self.assertEqual(
            [row["id"] for row in MODULE.select_scope_batch(scopes + [root], assessment, "r", 4)],
            ["root"],
        )

    def test_operator_source_inventory_is_complete_scope_bound_and_blob_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            (root / "owned").mkdir()
            (root / "owned/main.rs").write_text("fn main() {}\n")
            (root / "sibling.rs").write_text("pub fn sibling() {}\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            scope = {
                "pathBoundary": "owned", "trackedFileCount": 1,
                "ownershipSelectors": [{"type": "prefix", "path": "owned"}],
            }
            inventory = MODULE.scope_source_inventory(scope, root)
            self.assertEqual([row["path"] for row in inventory], ["owned/main.rs"])
            self.assertEqual(
                inventory[0]["gitBlobOid"],
                subprocess.check_output(
                    ["git", "-C", str(root), "rev-parse", "HEAD:owned/main.rs"], text=True
                ).strip(),
            )
            self.assertEqual(inventory[0]["byteCount"], len("fn main() {}\n"))
            scope["trackedFileCount"] = 2
            with self.assertRaisesRegex(ValueError, "tracked-file count"):
                MODULE.scope_source_inventory(scope, root)

    def test_source_inventory_query_uses_scope_pathspecs_and_nonrecursive_root(self):
        recursive, pathspecs = MODULE.scope_inventory_query({
            "pathBoundary": "src",
            "ownershipSelectors": [
                {"type": "prefix", "path": "src/one"},
                {"type": "files", "paths": ["build.json", "src/root.ts"]},
            ],
        })
        self.assertTrue(recursive)
        self.assertEqual(pathspecs, ["build.json", "src/one", "src/root.ts"])
        self.assertEqual(
            MODULE.scope_inventory_query({"pathBoundary": "."}),
            (False, []),
        )

    def test_root_inventory_does_not_recurse_into_child_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            (root / "build.json").write_text("{}\n")
            (root / "nested").mkdir()
            (root / "nested/main.rs").write_text("fn main() {}\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            inventory = MODULE.scope_source_inventory(
                {"pathBoundary": ".", "trackedFileCount": 1}, root)
            self.assertEqual([row["path"] for row in inventory], ["build.json"])

    def test_composite_scope_ownership_excludes_unselected_siblings(self):
        scope = {
            "pathBoundary": "src",
            "ownershipSelectors": [
                {"type": "prefix", "path": "src/one"},
                {"type": "files", "paths": ["src/root.ts"]},
            ],
        }
        self.assertTrue(MODULE.scope_owns_path(scope, "src/one/main.ts"))
        self.assertTrue(MODULE.scope_owns_path(scope, "src/root.ts"))
        self.assertFalse(MODULE.scope_owns_path(scope, "src/two/main.ts"))

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

    def test_complete_decomposition_plan_changes_blocker_to_review_not_promotion(self):
        scope = {
            "id": "large", "repositoryId": "arbitrary-repository", "pathBoundary": "library",
            "sourceRevision": "a" * 40, "sourceTreeOid": "c" * 40,
            "sourceFileCount": 81, "trackedFileCount": 90,
            "testFileCount": 0, "evidence": [{"path": "library/lib.rs"}],
        }
        candidate = {
            "schema": "agentlab.maintainer_scope_decomposition_plan.v1",
            "automaticPromotion": False,
            "repositoryId": "arbitrary-repository", "sourceRevision": "a" * 40,
            "sourceTreeOid": "c" * 40, "maxSourceFilesPerLeaf": 80,
            "parent": {"scopeSkillId": "large", "pathBoundary": "library",
                       "sourceFileCount": 81, "trackedFileCount": 90},
            "leaves": [
                {"sourceFileCount": 40, "trackedFileCount": 44},
                {"sourceFileCount": 41, "trackedFileCount": 46},
            ],
            "verification": {"complete": True, "nonOverlapping": True,
                             "assignedFileCount": 90, "unassignedFileCount": 0,
                             "multiplyAssignedFileCount": 0},
        }
        result = MODULE.classify_scope(
            scope,
            {"maturity": "L1-structural-ready"},
            decomposition={"path": "decomposition-plans/large.json", "sha256": "b" * 64,
                           "plan": candidate},
        )
        self.assertEqual(result["disposition"], "blocked")
        self.assertEqual(result["blockerCode"], "MS-SCOPE-DECOMPOSITION-REVIEW-REQUIRED")
        self.assertEqual(result["decompositionPlan"]["leafCount"], 2)

        review = {
            "schema": "agentlab.maintainer_scope_decomposition_review.v1",
            "automaticCatalogApply": False,
            "repositoryId": "arbitrary-repository", "sourceRevision": "a" * 40,
            "sourceTreeOid": "c" * 40, "decompositionPlanSha256": "b" * 64,
            "parentScopeSkillId": "large",
            "groups": [
                {"trackedFileCount": 44, "sourceFileCount": 40},
                {"trackedFileCount": 46, "sourceFileCount": 41},
            ],
            "verification": {
                "complete": True, "nonOverlapping": True, "assignedFileCount": 90,
                "unassignedLeafCount": 0, "multiplyAssignedLeafCount": 0,
                "semanticGroupCount": 2,
            },
            "blockerCode": "MS-ATOMIC-CATALOG-APPLY-REQUIRED",
            "decision": "ready-for-atomic-catalog-apply",
        }
        result = MODULE.classify_scope(
            scope,
            {"maturity": "L1-structural-ready"},
            decomposition={"path": "decomposition-plans/large.json", "sha256": "b" * 64,
                           "plan": candidate},
            review={"path": "decomposition-reviews/large.json", "sha256": "d" * 64,
                    "review": review},
        )
        self.assertEqual(result["blockerCode"], "MS-ATOMIC-CATALOG-APPLY-REQUIRED")
        self.assertEqual(result["decompositionReview"]["semanticGroupCount"], 2)

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
                {"path": "config/c.json", "gitBlobOid": "3" * 40},
            ],
            "limitations": [
                "Runtime consumption of the declared configuration was not executed or observed.",
                "Build success and downstream packaging behavior are not established by this analysis.",
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.com"], check=True)
            (source / "config").mkdir()
            (source / "config/a.json").write_text("{}\n")
            (source / "config/b.json").write_text("{}\n")
            (source / "config/c.json").write_text("{}\n")
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
        self.assertIn("AGENTLAB_SCOPE_BATCH_SIZE", script)
        self.assertIn("prepare-batch", loop)
        self.assertIn("agent_failed", loop)
        self.assertIn('retried_scopes=("${failed_scopes[@]}")', loop)
        self.assertIn("agent-retries/scope-$scope_index", loop)
        self.assertIn("retriedScopeIndices", loop)
        self.assertIn("one isolated retry", loop)

    def test_agent_prompt_names_the_exact_evidence_object_schema(self):
        source = (ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py").read_text()
        self.assertIn("the keys path and gitBlobOid", source)
        self.assertIn("exactly three objects", source)
        self.assertIn("exactly two concrete unproved claims", source)
        self.assertIn("never repositoryPath", source)
        self.assertIn("no other evidence fields are allowed", source)

    def test_workflow_removes_transient_source_links_before_evidence_upload(self):
        workflow = (ROOT / ".github/workflows/maintainer-skill-agent-flywheel.yml").read_text()
        cleanup = workflow.index("Remove transient source checkout links from retained evidence")
        upload = workflow.index("Preserve the proposal, gateway capture and hard-gate result")
        self.assertLess(cleanup, upload)
        self.assertIn("-path '*/workspace/source' -type l -delete", workflow)

    def test_agent_prompt_has_a_bounded_exploration_budget(self):
        source = (ROOT / "examples/maintainer-knowledge-gate/agent_flywheel.py").read_text()
        self.assertIn("Budget at most eight shell tool calls", source)
        self.assertIn("hard limit of 24 is only a runaway guard", source)
        self.assertIn("bounded sampling, not a complete source census", source)
        self.assertIn("operator owns proposal serialization", source)
        self.assertIn("final assistant response must consist solely", source)
        self.assertIn("stop exploring and return the\nexact JSON response", source)
        self.assertIn("tool_call_limit=24", source)
        self.assertIn("wall_time_limit_seconds=360", source)
        self.assertIn("transport_retry_limit=0", source)
        self.assertIn("maintainer-skill-author-finalize", source)
        self.assertIn("Do not inspect files, call tools, explain, count characters", source)
        self.assertIn("require_completed_tool_call=False", source)
        self.assertIn('reasoning_effort="none"', source)
        self.assertIn("interpretation of 650-900 characters", source)
        self.assertIn("gateway_timeout_seconds=60", source)
        participant = (ROOT / "examples/real-code-agent/participant.py").read_text()
        self.assertIn("upstream_deadline = time.monotonic()", participant)
        self.assertIn("upstreamDeadlineExceeded=True", participant)
        self.assertIn("operator has already verified HEAD", source)
        self.assertIn("Do not spend", source)
        self.assertIn("git ls-files or git rev-parse for paths listed above", source)

    def test_compare_accepts_one_l2_gain_without_prebound_operation_evidence(self):
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

    def test_compare_accepts_l3_when_semantic_closure_meets_prebound_operation_evidence(self):
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
                           "semanticReadyCount": 2, "maintenanceReadyCount": 1},
            }
            after_path = root / "after.json"
            after_path.write_text(json.dumps(after) + "\n")
            output = root / "result.json"
            MODULE.compare(type("Args", (), {"before": before_path, "after": after_path, "output": output}))
            self.assertEqual(json.loads(output.read_text())["maintenanceReadyDelta"], 1)

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

    def test_compare_accepts_only_an_exact_selected_batch_gain(self):
        before = {
            "totals": {"scopeSkillCount": 8, "structuralReadyCount": 8, "programBoundCount": 1,
                       "semanticReadyCount": 1, "maintenanceReadyCount": 0}
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before_path = root / "before.json"
            before_path.write_text(json.dumps(before) + "\n")
            after = {
                "parentAssessmentSha256": MODULE.digest(before_path),
                "totals": {"scopeSkillCount": 8, "structuralReadyCount": 8,
                           "programBoundCount": 4, "semanticReadyCount": 4,
                           "maintenanceReadyCount": 1},
            }
            after_path = root / "after.json"
            after_path.write_text(json.dumps(after) + "\n")
            output = root / "result.json"
            MODULE.compare(type("Args", (), {
                "before": before_path, "after": after_path, "output": output,
                "expected_scopes": 3,
            }))
            result = json.loads(output.read_text())
            self.assertEqual(result["batchScopeCount"], 3)
            self.assertEqual(result["semanticReadyDelta"], 3)
            after["totals"]["semanticReadyCount"] = 3
            after_path.write_text(json.dumps(after) + "\n")
            with self.assertRaisesRegex(ValueError, "every selected scope"):
                MODULE.compare(type("Args", (), {
                    "before": before_path, "after": after_path, "output": output,
                    "expected_scopes": 3,
                }))


if __name__ == "__main__":
    unittest.main()
