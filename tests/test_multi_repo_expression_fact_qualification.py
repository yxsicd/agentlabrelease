from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
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
    "multi_repo_expression_fact_qualification",
    ROOT / "scripts/qualify-multi-repo-expression-facts.py",
)


class MultiRepoExpressionFactQualificationTests(unittest.TestCase):
    def fixture(self, root: Path):
        packet = root / "packet.json"
        packet.write_text(json.dumps({
            "schema": QUALIFY.PACKET_SCHEMA,
            "candidateId": "difficulty-test",
            "sourceSetSha256": "f" * 64,
            "domainIdentifierContract": {
                "normalizedIdentifier": "purchase-data",
                "tokens": ["purchase", "data"],
            },
            "domainFactEvidence": [
                {"repositoryId": "a", "sourceIdentity": f"git:a@{'1' * 40}", "path": "A.ts"},
                {"repositoryId": "b", "sourceIdentity": f"git:b@{'2' * 40}", "path": "B.ts"},
            ],
        }) + "\n")
        analyses = {}
        facts = {}
        for repository_id, revision, path, row in (
            ("a", "1" * 40, "A.ts", {"id": "a1", "kind": "call", "path": "A.ts", "owner": "A::buy", "span": {"startByte": 1}, "targetExpression": "deal", "argumentExpressions": ["result.purchaseData"]}),
            ("b", "2" * 40, "B.ts", {"id": "b1", "kind": "assignment", "path": "B.ts", "owner": "B", "span": {"startByte": 2}, "leftExpression": "product.purchaseData", "rightExpression": "purchaseData", "resolution": "syntactic-unresolved"}),
        ):
            fact_path = root / f"{repository_id}.jsonl"
            fact_path.write_text(json.dumps(row, sort_keys=True) + "\n")
            analysis_path = root / f"{repository_id}.json"
            analysis_path.write_text(json.dumps({
                "schema": QUALIFY.ANALYSIS_SCHEMA,
                "sourceRevision": revision,
                "analyzerDigest": "a" * 64,
                "grammarDigest": "b" * 64,
                "rows": 1,
                "sha256": hashlib.sha256(fact_path.read_bytes()).hexdigest(),
            }))
            analyses[repository_id] = analysis_path
            facts[repository_id] = fact_path
        return packet, analyses, facts

    def test_exact_expression_facts_are_qualified_without_dataflow_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            packet, analyses, facts = self.fixture(Path(directory))
            value = QUALIFY.qualify(packet, analyses, facts)
            self.assertEqual(value["repositoryCount"], 2)
            self.assertEqual(value["selectedExpressionFactCount"], 2)
            self.assertEqual(value["status"], "expression-facts-qualified-dataflow-unresolved")
            self.assertFalse(value["semanticAlignmentVerified"])
            self.assertFalse(value["allowsCaseContract"])

    def test_tampered_program_facts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            packet, analyses, facts = self.fixture(Path(directory))
            facts["a"].write_text(facts["a"].read_text() + "{}\n")
            with self.assertRaisesRegex(QUALIFY.ExpressionQualificationError, "digest differs"):
                QUALIFY.qualify(packet, analyses, facts)

    def test_missing_expression_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            packet, analyses, facts = self.fixture(Path(directory))
            row = json.loads(facts["b"].read_text())
            del row["rightExpression"]
            facts["b"].write_text(json.dumps(row) + "\n")
            analysis = json.loads(analyses["b"].read_text())
            analysis["sha256"] = hashlib.sha256(facts["b"].read_bytes()).hexdigest()
            analyses["b"].write_text(json.dumps(analysis))
            with self.assertRaisesRegex(QUALIFY.ExpressionQualificationError, "lacks rightExpression"):
                QUALIFY.qualify(packet, analyses, facts)


if __name__ == "__main__":
    unittest.main()
