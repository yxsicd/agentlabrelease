from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


QUALIFY = load_module(
    "selected_control_flow_qualification",
    ROOT / "scripts/qualify-selected-control-flow.py",
)


class SelectedControlFlowQualificationTests(unittest.TestCase):
    def make_repository(self, root: Path, name: str, prefix: str) -> tuple[Path, str, dict]:
        repository = root / name
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        source = "\n".join([
            f"{prefix}-entry",
            f"{prefix}-route",
            f"{prefix}-ui",
            f"{prefix}-async",
            f"{prefix}-sink",
            f"{prefix}-success",
            f"{prefix}-rejection",
        ]) + "\n"
        source_path = "flow.txt"
        (repository / source_path).write_text(source)
        subprocess.run(["git", "-C", str(repository), "add", source_path], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
        blob = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD:flow.txt"], text=True).strip()
        return repository, revision, {
            "path": source_path,
            "gitBlobOid": blob,
            "contentSha256": hashlib.sha256(source.encode()).hexdigest(),
            "exactSnippets": [f"{prefix}-entry", f"{prefix}-sink"],
        }

    def fixture(self, root: Path):
        harmony, harmony_revision, harmony_file = self.make_repository(root, "harmony", "h")
        cordova, cordova_revision, cordova_file = self.make_repository(root, "cordova", "c")
        program_path = root / "program.json"
        program = {
            "schema": QUALIFY.PROGRAM_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "reviewPacketSha256": "b" * 64,
            "flows": [
                {"flowId": "h-program", "repositoryId": "harmony-iap-client", "steps": [{"kind": "call-argument-to-sink", "callFactId": "h-fact"}]},
                {"flowId": "c-program", "repositoryId": "hms-cordova-iap", "steps": [{"kind": "call-argument-to-sink", "callFactId": "c-fact"}]},
            ],
        }
        program_path.write_text(json.dumps(program) + "\n")
        object_path = root / "object.json"
        object_value = {
            "schema": QUALIFY.OBJECT_SCHEMA,
            "status": "object-flow-qualified-control-flow-review-required",
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "programAnalysisSha256": hashlib.sha256(program_path.read_bytes()).hexdigest(),
            "remainingUnresolved": [{"id": "global:reachability-dominance-exception-flow", "class": "control-flow"}],
            "remainingUnresolvedCount": 1,
        }
        object_path.write_text(json.dumps(object_value) + "\n")

        def flow(repository_id: str, flow_id: str, program_flow_id: str, prefix: str, fact_id: str):
            nodes = []
            for suffix, kind in (
                ("entry", "route-entry"),
                ("route", "route-binding"),
                ("ui", "event-binding"),
                ("async", "promise-call"),
                ("sink", "external-sink"),
                ("success", "success-exit"),
                ("rejection", "rejection-exit"),
            ):
                node = {"id": f"{prefix}-{suffix}", "kind": kind, "path": "flow.txt", "exactSnippet": f"{prefix}-{suffix}"}
                if suffix == "sink":
                    node["factId"] = fact_id
                nodes.append(node)
            return {
                "flowId": flow_id,
                "programFlowId": program_flow_id,
                "repositoryId": repository_id,
                "entryNode": f"{prefix}-entry",
                "sinkNode": f"{prefix}-sink",
                "nodes": nodes,
                "edges": [
                    {"from": f"{prefix}-entry", "to": f"{prefix}-route", "kind": "route"},
                    {"from": f"{prefix}-route", "to": f"{prefix}-ui", "kind": "ui-event"},
                    {"from": f"{prefix}-ui", "to": f"{prefix}-async", "kind": "direct-call"},
                    {"from": f"{prefix}-async", "to": f"{prefix}-sink", "kind": "promise-fulfillment", "branchGroup": f"promise:{prefix}"},
                    {"from": f"{prefix}-async", "to": f"{prefix}-rejection", "kind": "promise-rejection", "branchGroup": f"promise:{prefix}"},
                    {"from": f"{prefix}-sink", "to": f"{prefix}-success", "kind": "direct-call"},
                ],
                "orderedRegions": [{
                    "path": "flow.txt",
                    "startSnippet": f"{prefix}-entry",
                    "endSnippet": f"{prefix}-success",
                    "nodeIds": [f"{prefix}-{suffix}" for suffix in ("entry", "route", "ui", "async", "sink", "success")],
                }],
                "requiredEdgeKinds": ["route", "ui-event", "direct-call", "promise-fulfillment", "promise-rejection"],
                "requiredSinkDominators": [f"{prefix}-{suffix}" for suffix in ("entry", "route", "ui", "async")],
                "terminalExitNodes": [f"{prefix}-success", f"{prefix}-rejection"],
                "recoveryHandoffNodes": [],
            }

        plan_path = root / "plan.json"
        plan = {
            "schema": QUALIFY.PLAN_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "a" * 64,
            "programAnalysisSha256": hashlib.sha256(program_path.read_bytes()).hexdigest(),
            "objectFlowQualificationSha256": hashlib.sha256(object_path.read_bytes()).hexdigest(),
            "resolvedBoundary": {"id": "global:reachability-dominance-exception-flow", "class": "control-flow"},
            "qualificationScope": {
                "selectedSourcePathsOnly": True,
                "wholeApplicationReachability": False,
                "externalApiSuccess": False,
                "frameworkRuntimeCorrectness": False,
            },
            "repositories": [
                {"repositoryId": "harmony-iap-client", "sourceRevision": harmony_revision, "files": [harmony_file]},
                {"repositoryId": "hms-cordova-iap", "sourceRevision": cordova_revision, "files": [cordova_file]},
            ],
            "flows": [
                flow("harmony-iap-client", "h-flow", "h-program", "h", "h-fact"),
                flow("hms-cordova-iap", "c-flow", "c-program", "c", "c-fact"),
            ],
        }
        plan_path.write_text(json.dumps(plan) + "\n")
        return program_path, object_path, plan_path, harmony, cordova

    def test_exact_selected_control_flow_resolves_last_program_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(Path(directory))
            result = QUALIFY.qualify(values[0], values[1], values[2], {
                "harmony-iap-client": values[3],
                "hms-cordova-iap": values[4],
            })
            self.assertEqual(result["remainingUnresolvedCount"], 0)
            self.assertEqual(result["flowCount"], 2)
            self.assertTrue(result["conditionalReachabilityEstablished"])
            self.assertTrue(result["sinkDominanceEstablished"])
            self.assertTrue(result["exceptionExitsEnumerated"])
            self.assertTrue(result["callbackSchedulingResolved"])
            self.assertFalse(result["semanticAlignmentVerified"])
            self.assertFalse(result["behaviorOracleVerified"])
            self.assertFalse(result["allowsCaseContract"])

    def test_missing_async_rejection_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(Path(directory))
            plan = json.loads(values[2].read_text())
            plan["flows"][0]["edges"] = [
                edge for edge in plan["flows"][0]["edges"] if edge["kind"] != "promise-rejection"
            ]
            values[2].write_text(json.dumps(plan) + "\n")
            with self.assertRaisesRegex(QUALIFY.SelectedControlFlowError, "selected edge coverage differs"):
                QUALIFY.qualify(values[0], values[1], values[2], {
                    "harmony-iap-client": values[3],
                    "hms-cordova-iap": values[4],
                })

    def test_required_dominator_fails_closed_on_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(Path(directory))
            plan = json.loads(values[2].read_text())
            plan["flows"][0]["edges"].append({"from": "h-entry", "to": "h-sink", "kind": "direct-call"})
            values[2].write_text(json.dumps(plan) + "\n")
            with self.assertRaisesRegex(QUALIFY.SelectedControlFlowError, "sink dominators are not established"):
                QUALIFY.qualify(values[0], values[1], values[2], {
                    "harmony-iap-client": values[3],
                    "hms-cordova-iap": values[4],
                })


if __name__ == "__main__":
    unittest.main()
