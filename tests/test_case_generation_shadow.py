import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "case_generation_shadow",
    ROOT / "examples/maintainer-knowledge-gate/case_generation_shadow.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
KNOWLEDGE = ROOT / "examples/maintainer-knowledge-gate/first-four"


class CaseGenerationShadowTest(unittest.TestCase):
    def successor_fixture(self):
        import hashlib
        request = self.request()
        request["schema"] = "agentlab.operation_case_shadow_request.v1"
        request.pop("loopReceiptSha256")
        request["operationInputsSha256"] = "3" * 64
        request["policy"]["caseCalibrationInherited"] = False
        context = {"selectedFiles":[{"path":"verification/existing.test", "gitBlobOid":"a"*40,
                                     "contentUtf8":"existing independent test"}]}
        edit = {"edits":[{"path":request["fact"]["evidence"][0]["path"]},
                         {"path":"verification/new.test"}], "sourceContext":context}
        bound = {"schema":"agentlab.shadow_case_successor_inputs.v1", "calibrationInherited":False,
                 "formalCaseQualified":False,"automaticPromotion":False,"parentCandidateId":"shadow-case-parent-example",
                 "sourceContext":context,"editBoundary":edit,"bindings":{"operationInputsSha256":"3"*64,"runtimeTarget":"harmony-emulator"}}
        for key, raw, value in [("parentRequestSha256","parentRequestUtf8", {}),
                               ("parentProposalSha256","parentProposalUtf8", {}),
                               ("reviewSha256","reviewUtf8", {}), ("contextSha256","contextUtf8",context),
                               ("editBoundarySha256","editBoundaryUtf8",edit)]:
            bound[raw] = json.dumps(value)
            bound["bindings"][key] = hashlib.sha256(bound[raw].encode()).hexdigest()
        request["successorConstruction"] = bound
        request["candidateScopeSkillIds"] = [request["scope"]["id"], "verification-owner"]
        return request

    def test_successor_proposal_consumes_explicit_paths_and_preserves_parent_lineage(self):
        request = self.successor_fixture()
        proposal = self.proposal(request)
        proposal["scopeSkillIds"] = request["candidateScopeSkillIds"]
        proposal["editablePaths"] = ["verification/new.test"]
        proposal["contextPaths"] = ["verification/existing.test"]
        retained = MODULE.validate_proposal(request, proposal)
        self.assertEqual(retained["lineage"]["parentCandidateId"], "shadow-case-parent-example")
        self.assertEqual(retained["lineage"]["editBoundarySha256"], request["successorConstruction"]["bindings"]["editBoundarySha256"])
        self.assertEqual(retained["oracleHypothesis"]["status"], "hypothesis-unqualified")
        proposal["editablePaths"] = ["verification/unselected.test"]
        with self.assertRaisesRegex(ValueError, "not selected"):
            MODULE.validate_proposal(request, proposal)
        request["successorConstruction"]["contextUtf8"] += " "
        with self.assertRaisesRegex(ValueError, "digest differs"):
            MODULE.request_origin(request)

    def test_successor_dispatch_requires_native_preflight_and_excludes_draft_revision(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_file = root / "request.json"
            MODULE.write_json(request_file, self.successor_fixture())
            args = SimpleNamespace(request=request_file, source=root, output=root/"attempt",
                                   flywheel_tool=Path("/native/flywheel"), knowledge=root, operation_inputs=root/"inputs.json")
            with patch.dict(MODULE.os.environ, {}, clear=True), patch.object(MODULE.subprocess, "run") as native, patch.object(MODULE, "run_agent_inner") as dispatch:
                MODULE.run_agent(args)
                self.assertIn("--validate-operation-case-successor", native.call_args.args[0])
                self.assertTrue(native.call_args.kwargs["check"])
                dispatch.assert_called_once_with(args)
            args.output = root / "failed-attempt"
            with patch.object(MODULE.subprocess, "run", side_effect=subprocess.CalledProcessError(1,"native")), patch.object(MODULE, "run_agent_inner") as dispatch:
                with self.assertRaises(subprocess.CalledProcessError):
                    MODULE.run_agent(args)
                dispatch.assert_not_called()
            args.revision_request = root / "revision.json"
            with self.assertRaisesRegex(ValueError, "exclusive"):
                MODULE.run_agent(args)

    def test_participant_options_keep_defaults_and_explicit_configuration(self):
        from types import SimpleNamespace
        self.assertEqual(MODULE.participant_options(SimpleNamespace()),
                         {"reasoning_effort":None, "max_output_tokens":None})
        self.assertEqual(MODULE.participant_options(SimpleNamespace(reasoning_effort="low", max_output_tokens=16384)),
                         {"reasoning_effort":"low", "max_output_tokens":16384})
        for args in [SimpleNamespace(reasoning_effort="unknown"),
                     SimpleNamespace(max_output_tokens=True), SimpleNamespace(max_output_tokens=8193)]:
            with self.assertRaises(ValueError):
                MODULE.participant_options(args)

    def test_declared_framework_tracks_runtime_not_existing_test_inventory(self):
        request = self.request()
        request["scope"]["testEntrypoints"] = []
        request["policy"]["oracleFramework"] = "ohosTest"
        proposal = self.proposal(request)
        proposal["oracleHypothesis"]["framework"] = "ohosTest"
        MODULE.validate_proposal(request, proposal)
        proposal["oracleHypothesis"]["framework"] = "repository-test"
        with self.assertRaisesRegex(ValueError, "framework differs"):
            MODULE.validate_proposal(request, proposal)
        request["policy"]["runtimeTarget"] = "repository-test"
        with self.assertRaisesRegex(ValueError, "conflicts with runtime"):
            MODULE.oracle_framework(request["policy"], request["scope"])
        request["policy"]["oracleFramework"] = "repository-test"
        self.assertEqual(MODULE.oracle_framework(request["policy"], request["scope"]), "repository-test")

    def test_isolated_source_projection_is_exact_fresh_and_revision_bound(self):
        import hashlib
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "checkout"
            source.mkdir()
            def git(*args):
                return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
            git("init", "-q")
            (source / "unit.ts").write_text("export const value = 1;\n")
            (source / "unselected.ts").write_text("not constructor context\n")
            git("add", ".")
            git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
            request = {"repository":{"revision":git("rev-parse", "HEAD")},
                       "fact":{"evidence":[{"path":"unit.ts", "gitBlobOid":git("rev-parse", "HEAD:unit.ts")}]}}
            template = root / "template.json"
            original = {"schema":"agentlab.participant_docker_runtime.v1", "executor":"docker",
                        "caseInputRoot":"old-input", "participantManifestSha256":"0"*64,
                        "forbiddenHostPaths":["/operator/private"], "imageId":"sha256:"+"1"*64}
            template.write_text(json.dumps(original))
            output = root / "attempt"
            runtime = MODULE.prepare_isolated_source(request, source, output, template)
            config = MODULE.load(runtime)
            case = Path(config["caseInputRoot"])
            self.assertEqual((case / "source/unit.ts").read_bytes(), (source / "unit.ts").read_bytes())
            self.assertFalse((case / "source/unselected.ts").exists())
            self.assertFalse((case / "source/.git").exists())
            self.assertEqual(config["participantManifestSha256"], hashlib.sha256((case / "manifest.json").read_bytes()).hexdigest())
            self.assertEqual(MODULE.load(template), original)
            self.assertIn(str(source.resolve()), config["forbiddenHostPaths"])
            self.assertEqual(config["imageId"], original["imageId"])
            context_item = {"path":"unselected.ts","gitBlobOid":git("rev-parse","HEAD:unselected.ts"),
                            "contentUtf8":(source / "unselected.ts").read_text()}
            request["successorConstruction"] = {"sourceContext":{"selectedFiles":[context_item]},
                                                  "editBoundary":{"sourceContext":{"selectedFiles":[]}}}
            with_context = MODULE.prepare_isolated_source(request, source, root / "context-attempt", template)
            context_case = Path(MODULE.load(with_context)["caseInputRoot"])
            self.assertEqual((context_case / "source/unselected.ts").read_bytes(), (source / "unselected.ts").read_bytes())
            self.assertFalse((context_case / "source/.git").exists())
            with self.assertRaises(FileExistsError):
                MODULE.prepare_isolated_source(request, source, output, template)
            request["fact"]["evidence"][0]["gitBlobOid"] = "0"*40
            with self.assertRaisesRegex(ValueError, "Blob differs"):
                MODULE.prepare_isolated_source(request, source, root / "bad-attempt", template)
            self.assertFalse((root / "bad-attempt").exists())

    def test_operation_origin_retains_distinct_lineage_without_semantic_gain(self):
        request = self.request()
        request["schema"] = "agentlab.operation_case_shadow_request.v1"
        request.pop("loopReceiptSha256")
        request["operationInputsSha256"] = "3" * 64
        request["policy"]["caseCalibrationInherited"] = False
        request["knowledgeCoverage"] = request.pop("loopAfter")
        request.pop("loopBefore")
        candidate = MODULE.validate_proposal(request, self.proposal(request))
        self.assertNotIn("loopReceiptSha256", candidate["lineage"])
        self.assertEqual(candidate["lineage"]["operationInputsSha256"], "3" * 64)
        round_row = MODULE.build_round(request, [{"id":"parent", "roundIndex":1}], candidate["id"], True, None, "test")
        self.assertEqual(round_row["coverage"]["behaviorReadyBefore"], round_row["coverage"]["behaviorReadyAfter"])
        self.assertEqual(round_row["qualification"]["qualifiedCaseIds"], [])
        self.assertNotIn("advanced semantic coverage", " ".join(round_row["decisionEvidence"]))
        request["loopReceiptSha256"] = "4" * 64
        with self.assertRaisesRegex(ValueError, "borrows"):
            MODULE.request_origin(request)

    def test_fact_source_verifies_git_blobs_and_rejects_dirty_or_borrowed_evidence(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
            git("init", "-q")
            (source / "unit.ts").write_text("export const value = 1;\n")
            git("add", "unit.ts")
            git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
            revision = git("rev-parse", "HEAD")
            request = {"repository":{"revision":revision},"fact":{"evidence":[{
                "path":"unit.ts","gitBlobOid":git("rev-parse", "HEAD:unit.ts")} ]}}
            MODULE.verify_fact_source(request, source)
            request["fact"]["evidence"][0]["gitBlobOid"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "Blob differs"):
                MODULE.verify_fact_source(request, source)
            (source / "unit.ts").write_text("export const value = 2;\n")
            with self.assertRaisesRegex(ValueError, "dirty"):
                MODULE.verify_fact_source(request, source)

    def request(self):
        cut = MODULE.load(KNOWLEDGE / "maintainer-knowledge-cut.json")
        scopes = {row["id"]: row for row in MODULE.rows(KNOWLEDGE / "maintainer_scope_skills.jsonl")}
        facts = [
            row for row in MODULE.rows(KNOWLEDGE / "program_facts.jsonl")
            if row["id"].startswith("agent-analysis-")
        ]
        fact = facts[-1]
        scope = scopes[fact["scopeSkillIds"][0]]
        repository = next(row for row in cut["repositories"] if row["id"] == fact["repositoryId"])
        latest = max(MODULE.rows(KNOWLEDGE / "maintainer_skill_refresh_rounds.jsonl"),
                     key=lambda row: row["roundIndex"])
        return {
            "schema": "agentlab.case_generation_shadow_request.v1",
            "automaticPromotion": False,
            "sourceSetSha256": cut["sourceSetSha256"],
            "knowledgeCutSha256": "1" * 64,
            "maintainerSkillRefreshRoundId": latest["id"],
            "loopReceiptSha256": "2" * 64,
            "loopBefore": {
                "scopeSkillCount": 480, "programBoundCount": 18,
                "semanticReadyCount": 11, "maintenanceReadyCount": 2,
            },
            "loopAfter": {
                "scopeSkillCount": 480, "programBoundCount": 19,
                "semanticReadyCount": 12, "maintenanceReadyCount": 2,
            },
            "repository": repository,
            "scope": scope,
            "fact": fact,
            "candidateId": f"shadow-case-{fact['id'].removeprefix('agent-analysis-')}",
            "policy": {
                "candidateLimit": 1, "constructionMode": "shadow",
                "candidateGateRequired": True, "independentOracleRequired": True,
                "wrongVariantCalibrationRequired": True,
                "runtimeTarget": "harmony-emulator",
                "externalHardwareAllowed": False,
                "physicalDeviceFallbackAllowed": False,
                "shadowEligible": True,
                "blockers": [],
            },
            "output": "shadow-case-proposal.json",
        }

    def proposal(self, request):
        fact = request["fact"]
        scope = request["scope"]
        inside = [
            row["path"] for row in fact["evidence"]
            if MODULE.scope_owns_path(scope, row["path"])
        ]
        outside = [row["path"] for row in fact["evidence"] if row["path"] not in inside]
        framework = "ohosTest" if any("ohosTest" in path for path in scope.get("testEntrypoints", [])) else "repository-test"
        return {
            "schema": "agentlab.shadow_case_candidate.v1",
            "id": request["candidateId"],
            "repositoryId": fact["repositoryId"],
            "sourceRevision": fact["sourceRevision"],
            "scopeSkillIds": fact["scopeSkillIds"],
            "factIds": [fact["id"]],
            "title": "Preserve the bounded state transition contract",
            "mechanism": "Change the bounded implementation while preserving its cross-file state transition and make a later requirement expose an earlier shortcut in the selected mechanism.",
            "stagedDemands": [
                "Implement the bounded behavior without changing unrelated source.",
                "Extend the behavior while preserving the first-stage state transition.",
            ],
            "editablePaths": [inside[0]],
            "contextPaths": outside[:1],
            "oracleHypothesis": {
                "framework": framework,
                "observables": ["the first-stage state is preserved", "the second-stage transition is observable"],
                "requiredEnvironment": ["a pinned HarmonyOS emulator image and repository test environment"],
                "wrongVariants": ["drop the first-stage state", "apply the second-stage rule unconditionally"],
                "status": "hypothesis-unqualified",
            },
            "limitations": ["the Oracle has not executed", "the wrong variants have not been calibrated"],
            "status": "shadow-proposal",
            "automaticPromotion": False,
        }

    def test_prepare_binds_one_exported_loop_gain_to_the_exact_cut(self):
        request_fixture = self.request()
        fact = request_fixture["fact"]
        iteration = {
            "iteration": 1,
            "repository": fact["repositoryId"],
            "scope": fact["scopeSkillIds"][0],
            "acceptedFactId": fact["id"],
            "before": request_fixture["loopBefore"],
            "after": request_fixture["loopAfter"],
            "automaticPromotion": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loop_path = root / "loop-receipt.json"
            output = root / "request.json"
            MODULE.write_json(loop_path, {
                "schema": "agentlab.maintainer_skill_bounded_loop_receipt.v1",
                "requestedIterations": 1,
                "completedIterations": 1,
                "automaticPromotion": False,
                "iterations": [iteration],
            })
            MODULE.prepare(type("Args", (), {
                "knowledge": KNOWLEDGE, "loop_receipt": loop_path, "output": output,
            }))
            prepared = MODULE.load(output)
            self.assertEqual(prepared["fact"]["id"], fact["id"])
            self.assertEqual(
                prepared["candidateId"],
                f"shadow-case-{fact['id'].removeprefix('agent-analysis-')}",
            )
            self.assertEqual(prepared["scope"]["id"], fact["scopeSkillIds"][0])
            self.assertEqual(
                prepared["knowledgeCutSha256"],
                MODULE.file_digest(KNOWLEDGE / "maintainer-knowledge-cut.json"),
            )
            self.assertFalse(prepared["automaticPromotion"])
            self.assertEqual(prepared["policy"]["runtimeTarget"], "harmony-emulator")

    def test_prepare_samples_one_exact_fact_from_a_parallel_scope_batch(self):
        request_fixture = self.request()
        selected_fact = request_fixture["fact"]
        selected_scope = selected_fact["scopeSkillIds"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loop_path = root / "loop-receipt.json"
            output = root / "request.json"
            MODULE.write_json(loop_path, {
                "schema": "agentlab.maintainer_skill_bounded_loop_receipt.v1",
                "requestedIterations": 1,
                "completedIterations": 1,
                "automaticPromotion": False,
                "iterations": [{
                    "iteration": 1,
                    "repository": selected_fact["repositoryId"],
                    "scopeIds": [selected_scope],
                    "acceptedFactIds": [selected_fact["id"]],
                    "batchSize": 1,
                    "before": request_fixture["loopBefore"],
                    "after": request_fixture["loopAfter"],
                    "automaticPromotion": False,
                }],
            })
            MODULE.prepare(type("Args", (), {
                "knowledge": KNOWLEDGE, "loop_receipt": loop_path, "output": output,
            }))
            prepared = MODULE.load(output)
            self.assertEqual(prepared["fact"]["id"], selected_fact["id"])
            self.assertEqual(prepared["scope"]["id"], selected_scope)

    def test_workflow_does_not_block_exact_export_when_shadow_sampling_fails(self):
        workflow = (ROOT / ".github/workflows/maintainer-skill-agent-flywheel.yml").read_text()
        shadow_step = workflow.split(
            "      - name: Sample one non-promoted shadow case from the knowledge gain\n", 1
        )[1].split("      - name: Propose the fixed-revision Release export\n", 1)[0]
        self.assertIn("if ! scripts/run-case-generation-shadow.sh", shadow_step)
        self.assertIn("preserving the exact TableGit export", shadow_step)

    def test_retained_shadow_candidate_and_round_are_exactly_bound(self):
        request = self.request()
        proposal = self.proposal(request)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            proposal_path = root / "proposal.json"
            rounds_path = root / "rounds.jsonl"
            candidates_path = root / "candidates.jsonl"
            receipt_path = root / "receipt.json"
            MODULE.write_json(request_path, request)
            MODULE.write_json(proposal_path, proposal)
            rounds_path.write_text((KNOWLEDGE / "case_generation_rounds.jsonl").read_text())
            MODULE.record_success(type("Args", (), {
                "request": request_path, "proposal": proposal_path,
                "rounds": rounds_path, "candidates": candidates_path,
                "receipt": receipt_path, "run_id": "42",
            }))
            candidate = MODULE.rows(candidates_path)[0]
            round_row = MODULE.rows(rounds_path)[-1]
            schema = json.loads((ROOT / "schemas/shadow-case-candidate.schema.json").read_text())
            self.assertEqual(set(candidate), set(schema["required"]))
            self.assertRegex(candidate["id"], schema["properties"]["id"]["pattern"])
            self.assertEqual(candidate["schema"], schema["properties"]["schema"]["const"])
            self.assertEqual(candidate["knowledgeCutSha256"], request["knowledgeCutSha256"])
            self.assertEqual(round_row["candidates"]["retainedIds"], [candidate["id"]])
            self.assertEqual(round_row["coverage"]["behaviorReadyBefore"], 11)
            self.assertEqual(round_row["coverage"]["behaviorReadyAfter"], 12)
            self.assertEqual(round_row["coverage"]["oracleReadyAfter"], 0)
            self.assertFalse(round_row["automaticPromotion"])

    def test_invalid_shadow_proposal_becomes_feedback_without_blocking_knowledge(self):
        request = self.request()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            rounds_path = root / "rounds.jsonl"
            receipt_path = root / "receipt.json"
            MODULE.write_json(request_path, request)
            rounds_path.write_text((KNOWLEDGE / "case_generation_rounds.jsonl").read_text())
            MODULE.record_failure(type("Args", (), {
                "request": request_path, "rounds": rounds_path,
                "receipt": receipt_path, "run_id": "43",
                "reason": "shadow-proposal-hard-gate-rejected",
            }))
            round_row = MODULE.rows(rounds_path)[-1]
            self.assertEqual(round_row["candidates"]["retainedIds"], [])
            self.assertEqual(
                round_row["candidates"]["rejected"][0]["reason"],
                "shadow-proposal-hard-gate-rejected",
            )
            self.assertEqual(MODULE.load(receipt_path)["status"], "rejected-shadow-attempt")

    def test_validator_rejects_editable_path_outside_scope(self):
        request = self.request()
        proposal = self.proposal(request)
        evidence_paths = [row["path"] for row in request["fact"]["evidence"]]
        outside = next(
            (path for path in evidence_paths if not MODULE.path_is_within(path, request["scope"]["pathBoundary"])),
            None,
        )
        if outside is None:
            self.skipTest("selected fixture has no cross-boundary evidence")
        proposal["editablePaths"] = [outside]
        proposal["contextPaths"] = []
        with self.assertRaisesRegex(ValueError, "escapes"):
            MODULE.validate_proposal(request, proposal)

    def test_validator_rejects_scalar_environment_contract(self):
        request = self.request()
        proposal = self.proposal(request)
        proposal["oracleHypothesis"]["requiredEnvironment"] = "one environment"
        with self.assertRaisesRegex(ValueError, "requiredEnvironment is incomplete"):
            MODULE.validate_proposal(request, proposal)

    def test_agent_prompt_and_gate_share_shadow_text_limits(self):
        contract = MODULE.proposal_field_constraints()
        self.assertIn(
            f"{MODULE.TITLE_MIN_LENGTH}-{MODULE.TITLE_MAX_LENGTH} characters",
            contract,
        )
        for label, limits in (
            ("stagedDemands", MODULE.STAGED_DEMANDS_LIMITS),
            ("editablePaths", MODULE.EDITABLE_PATHS_LIMITS),
            ("contextPaths", MODULE.CONTEXT_PATHS_LIMITS),
        ):
            self.assertIn(f"{label}: {limits[0]}-{limits[1]}", contract)
        self.assertIn(
            f"{MODULE.MECHANISM_MIN_LENGTH}-{MODULE.MECHANISM_MAX_LENGTH} characters",
            contract,
        )

        request = self.request()
        proposal = self.proposal(request)
        proposal["mechanism"] = "x" * (MODULE.MECHANISM_MAX_LENGTH + 1)
        with self.assertRaisesRegex(ValueError, "shadow mechanism is invalid"):
            MODULE.validate_proposal(request, proposal)

    def test_validator_rejects_physical_or_external_hardware_environment(self):
        request = self.request()
        proposal = self.proposal(request)
        proposal["oracleHypothesis"]["requiredEnvironment"] = [
            "a HarmonyOS emulator plus an attached USB serial port",
        ]
        with self.assertRaisesRegex(ValueError, "requires external hardware"):
            MODULE.validate_proposal(request, proposal)

        proposal["oracleHypothesis"]["requiredEnvironment"] = [
            "a physical device running the pinned HarmonyOS image",
        ]
        with self.assertRaisesRegex(ValueError, "physical device"):
            MODULE.validate_proposal(request, proposal)

    def test_validator_understands_explicitly_negated_hardware_requirements(self):
        request = self.request()
        proposal = self.proposal(request)
        proposal["oracleHypothesis"]["requiredEnvironment"] = [
            "HarmonyOS emulator: no physical device and no USB, serial, or other external hardware.",
            "无需真机，不依赖外接设备的 API 24 模拟器镜像",
        ]
        validated = MODULE.validate_proposal(request, proposal)
        self.assertEqual(validated["id"], proposal["id"])

        proposal["oracleHypothesis"]["requiredEnvironment"] = [
            "HarmonyOS emulator without a physical device, but an attached UART is required",
        ]
        with self.assertRaisesRegex(ValueError, "requires external hardware"):
            MODULE.validate_proposal(request, proposal)

    def test_serial_scope_is_blocked_before_the_construction_agent_runs(self):
        scopes = {row["id"]: row for row in MODULE.rows(KNOWLEDGE / "maintainer_scope_skills.jsonl")}
        facts = {row["id"]: row for row in MODULE.rows(KNOWLEDGE / "program_facts.jsonl")}
        scope = scopes["skill-scope-guide-snippets-serial-serialmanagersample"]
        fact = facts["agent-analysis-serial-port-demo-app"]
        self.assertIn("serial-peripheral", MODULE.external_hardware_blockers(scope, fact))
        self.assertIn("usb-peripheral", MODULE.external_hardware_blockers(scope, fact))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loop_path = root / "loop-receipt.json"
            request_path = root / "shadow-request.json"
            MODULE.write_json(loop_path, {
                "schema": "agentlab.maintainer_skill_bounded_loop_receipt.v1",
                "requestedIterations": 1,
                "completedIterations": 1,
                "automaticPromotion": False,
                "iterations": [{
                    "iteration": 1,
                    "repository": fact["repositoryId"],
                    "scope": scope["id"],
                    "acceptedFactId": fact["id"],
                    "before": self.request()["loopBefore"],
                    "after": self.request()["loopAfter"],
                    "automaticPromotion": False,
                }],
            })
            MODULE.prepare(type("Args", (), {
                "knowledge": KNOWLEDGE,
                "loop_receipt": loop_path,
                "output": request_path,
            }))
            policy = MODULE.load(request_path)["policy"]
            self.assertFalse(policy["shadowEligible"])
            self.assertEqual(policy["runtimeTarget"], "harmony-emulator")


if __name__ == "__main__":
    unittest.main()
