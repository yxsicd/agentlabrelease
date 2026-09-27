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


FLOW = load_module(
    "bounded_expression_flow_proposal",
    ROOT / "scripts/build-bounded-expression-flow-proposal.py",
)


class BoundedExpressionFlowProposalTests(unittest.TestCase):
    def fixture(self, root: Path):
        packet = root / "packet.json"
        repos, analyses, facts, revisions = {}, {}, {}, {}
        rows = {
            "a": [
                {"id": "a-scope", "kind": "symbol", "path": "A.ts", "owner": "A", "qualifiedName": "A::source", "symbol": "source", "parameterExpressions": [], "span": {"startByte": 0, "endByte": 100}},
                {"id": "a-target", "kind": "symbol", "path": "A.ts", "owner": "A", "qualifiedName": "A::target", "symbol": "target", "parameterExpressions": ["value: string"], "span": {"startByte": 101, "endByte": 200}},
                {"id": "a-call", "kind": "call", "path": "A.ts", "owner": "A::source", "targetExpression": "this.target", "argumentExpressions": ["seed.value"], "span": {"startByte": 10, "endByte": 20}},
                {"id": "a-bind", "kind": "binding", "path": "A.ts", "owner": "A::target", "name": "payload", "initializerExpression": "wrap(value)", "span": {"startByte": 120, "endByte": 130}},
                {"id": "a-sink", "kind": "call", "path": "A.ts", "owner": "A::target", "targetExpression": "api.finish", "argumentExpressions": ["payload"], "span": {"startByte": 140, "endByte": 150}},
            ],
            "b": [
                {"id": "b-make", "kind": "property", "path": "B.ts", "owner": "B", "name": "make", "parameterExpressions": ["purchaseData"], "span": {"startByte": 0, "endByte": 100}},
                {"id": "b-consume", "kind": "property", "path": "B.ts", "owner": "B", "name": "consume", "parameterExpressions": ["product", "purchaseData"], "span": {"startByte": 101, "endByte": 220}},
                {"id": "b-assign", "kind": "assignment", "path": "B.ts", "owner": "B", "leftExpression": "product.purchaseData", "rightExpression": "purchaseData", "span": {"startByte": 20, "endByte": 40}},
                {"id": "b-entry", "kind": "object-entry", "path": "B.ts", "owner": "B", "keyExpression": "inAppPurchaseData", "valueExpression": "purchaseData", "span": {"startByte": 150, "endByte": 160}},
                {"id": "b-sink", "kind": "call", "path": "B.ts", "owner": "B", "targetExpression": "api.consume", "argumentExpressions": ["{inAppPurchaseData: purchaseData}"], "span": {"startByte": 140, "endByte": 170}},
            ],
        }
        for repository_id in ("a", "b"):
            repo = root / f"repo-{repository_id}"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            if repository_id == "b":
                (repo / "B.html").write_text("consume(product, product.purchaseData)\n", encoding="utf-8")
            else:
                (repo / "A.ts").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            repos[repository_id], revisions[repository_id] = repo, revision
            fact_path = root / f"{repository_id}.jsonl"
            fact_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows[repository_id]))
            analysis_path = root / f"{repository_id}.analysis.json"
            analysis_path.write_text(json.dumps({
                "schema": FLOW.ANALYSIS_SCHEMA,
                "sourceRevision": revision,
                "rows": len(rows[repository_id]),
                "sha256": hashlib.sha256(fact_path.read_bytes()).hexdigest(),
            }))
            facts[repository_id], analyses[repository_id] = fact_path, analysis_path
        packet.write_text(json.dumps({
            "schema": FLOW.PACKET_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "f" * 64,
            "domainFactEvidence": [
                {"repositoryId": key, "sourceIdentity": f"git:test@{revision}", "path": f"{key}.ts"}
                for key, revision in revisions.items()
            ],
        }))
        blob = subprocess.check_output(["git", "-C", str(repos["b"]), "rev-parse", "HEAD:B.html"], text=True).strip()
        bridge_content = (repos["b"] / "B.html").read_bytes()
        plan_value = {
            "schema": FLOW.PLAN_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "f" * 64,
            "flows": [
                {"flowId": "a", "repositoryId": "a", "sourceNode": "A::source::seed.value", "sinkNode": "A::target::sink:api.finish[0]", "steps": [
                    {"kind": "call-argument-to-parameter", "callFactId": "a-call", "callScope": "A::source", "argumentIndex": 0, "callableFactId": "a-target", "parameterIndex": 0},
                    {"kind": "binding-dependency", "factId": "a-bind", "dependsOn": "value"},
                    {"kind": "call-argument-to-sink", "callFactId": "a-sink", "callScope": "A::target", "argumentIndex": 0, "dependsOn": "payload", "targetExpression": "api.finish"},
                ]},
                {"flowId": "b", "repositoryId": "b", "sourceNode": "B::make::purchaseData", "sinkNode": "B::consume::sink:api.consume[0]", "steps": [
                    {"kind": "assignment-dependency", "factId": "b-assign"},
                    {"kind": "template-event-bridge", "callableFactId": "b-consume", "path": "B.html", "gitBlobOid": blob, "contentSha256": hashlib.sha256(bridge_content).hexdigest(), "exactExpression": "consume(product, product.purchaseData)", "occurrences": 1, "fromScope": "B::make", "fromExpression": "product.purchaseData", "argumentExpressions": ["product", "product.purchaseData"], "argumentIndex": 1, "parameterIndex": 1},
                    {"kind": "call-argument-to-sink", "callFactId": "b-sink", "callScope": "B::consume", "argumentIndex": 0, "dependsOn": "purchaseData", "objectEntryFactId": "b-entry", "objectKey": "inAppPurchaseData", "targetExpression": "api.consume"},
                ]},
            ],
        }
        plan = root / "plan.json"
        plan.write_text(json.dumps(plan_value))
        return plan, packet, analyses, facts, repos

    def test_exact_bounded_paths_remain_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, packet, analyses, facts, repos = self.fixture(Path(directory))
            value = FLOW.build(plan, packet, analyses, facts, repos)
            self.assertEqual(value["status"], "bounded-syntactic-flow-proposal-review-required")
            self.assertEqual(value["flowCount"], 2)
            self.assertTrue(value["allBoundedPathsEstablished"])
            self.assertFalse(value["semanticAlignmentVerified"])
            self.assertFalse(value["behaviorOracleVerified"])
            self.assertFalse(value["allowsCaseContract"])
            self.assertFalse(value["automaticPromotion"])

    def test_missing_template_bridge_prevents_cordova_path(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, packet, analyses, facts, repos = self.fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["flows"][1]["steps"].pop(1)
            plan.write_text(json.dumps(value))
            with self.assertRaisesRegex(FLOW.FlowProposalError, "not contiguous"):
                FLOW.build(plan, packet, analyses, facts, repos)

    def test_tampered_fact_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, packet, analyses, facts, repos = self.fixture(Path(directory))
            facts["a"].write_text(facts["a"].read_text() + "{}\n")
            with self.assertRaisesRegex(FLOW.FlowProposalError, "digest differs"):
                FLOW.build(plan, packet, analyses, facts, repos)

    def test_tampered_bridge_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, packet, analyses, facts, repos = self.fixture(Path(directory))
            (repos["b"] / "B.html").write_text("changed\n")
            subprocess.run(["git", "-C", str(repos["b"]), "add", "B.html"], check=True)
            subprocess.run(["git", "-C", str(repos["b"]), "commit", "-qm", "changed"], check=True)
            with self.assertRaisesRegex(FLOW.FlowProposalError, "checkout revision differs"):
                FLOW.build(plan, packet, analyses, facts, repos)

    def test_bridge_argument_position_must_match_parameter_position(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, packet, analyses, facts, repos = self.fixture(Path(directory))
            value = json.loads(plan.read_text())
            value["flows"][1]["steps"][1]["parameterIndex"] = 0
            plan.write_text(json.dumps(value))
            with self.assertRaisesRegex(FLOW.FlowProposalError, "argument-to-parameter position differs"):
                FLOW.build(plan, packet, analyses, facts, repos)


if __name__ == "__main__":
    unittest.main()
