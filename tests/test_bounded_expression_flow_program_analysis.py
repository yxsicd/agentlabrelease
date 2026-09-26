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
    "bounded_expression_flow_program_analysis",
    ROOT / "scripts/qualify-bounded-expression-flow.py",
)
FLOW = load_module(
    "bounded_expression_flow_proposal_for_qualification",
    ROOT / "scripts/build-bounded-expression-flow-proposal.py",
)
FIXTURE = load_module(
    "bounded_expression_flow_fixture_for_qualification",
    ROOT / "tests/test_bounded_expression_flow_proposal.py",
)


class BoundedExpressionFlowProgramAnalysisTests(unittest.TestCase):
    def fixture(self, root: Path):
        plan, packet, analyses, facts, repositories = (
            FIXTURE.BoundedExpressionFlowProposalTests().fixture(root)
        )
        proposal = root / "proposal.json"
        proposal.write_text(
            json.dumps(
                FLOW.build(plan, packet, analyses, facts, repositories),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return plan, packet, proposal, analyses, facts, repositories

    def test_exact_replay_narrows_resolved_and_unresolved_program_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.fixture(Path(directory))
            result = QUALIFY.qualify(*values)
            self.assertEqual(
                result["status"],
                "bounded-program-flow-partially-resolved-review-required",
            )
            self.assertTrue(result["flowReplayExact"])
            self.assertTrue(result["coverage"]["localCallTargetsUniquelyResolved"])
            self.assertEqual(result["coverage"]["localCallTargetCount"], 1)
            self.assertEqual(result["coverage"]["typedParameterMappingCount"], 1)
            self.assertEqual(result["coverage"]["untypedParameterMappingCount"], 0)
            self.assertTrue(result["coverage"]["exactDependencyReferencesVerified"])
            self.assertFalse(result["typeResolutionComplete"])
            self.assertFalse(result["aliasResolutionComplete"])
            self.assertFalse(result["externalCallContractsResolved"])
            self.assertFalse(result["reachabilityAndDominanceResolved"])
            self.assertFalse(result["allowsCaseContract"])
            self.assertFalse(result["automaticPromotion"])

    def test_retained_proposal_must_equal_exact_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            values = list(self.fixture(Path(directory)))
            proposal = json.loads(values[2].read_text())
            proposal["allBoundedPathsEstablished"] = False
            values[2].write_text(json.dumps(proposal) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                QUALIFY.ProgramFlowQualificationError,
                "differs from exact replay",
            ):
                QUALIFY.qualify(*values)

    def test_ambiguous_local_callable_definition_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            values = list(self.fixture(Path(directory)))
            facts = values[4]
            analyses = values[3]
            rows = [json.loads(line) for line in facts["a"].read_text().splitlines()]
            duplicate = dict(next(row for row in rows if row["id"] == "a-target"))
            duplicate["id"] = "a-target-duplicate"
            rows.append(duplicate)
            facts["a"].write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            analysis = json.loads(analyses["a"].read_text())
            analysis["rows"] = len(rows)
            analysis["sha256"] = hashlib.sha256(facts["a"].read_bytes()).hexdigest()
            analyses["a"].write_text(json.dumps(analysis), encoding="utf-8")
            replayed = FLOW.build(values[0], values[1], analyses, facts, values[5])
            values[2].write_text(
                json.dumps(replayed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                QUALIFY.ProgramFlowQualificationError,
                "local call target is not unique",
            ):
                QUALIFY.qualify(*values)

    def test_dependency_matching_uses_identifier_tokens_not_substrings(self):
        self.assertTrue(QUALIFY.expression_references("wrap(value)", "value"))
        self.assertTrue(
            QUALIFY.expression_references(
                "{ inAppPurchaseData: purchaseData }",
                "purchaseData",
            )
        )
        self.assertTrue(
            QUALIFY.expression_references("product.purchaseData", "product.purchaseData")
        )
        self.assertFalse(QUALIFY.expression_references("wrap(myvalue)", "value"))
        self.assertFalse(
            QUALIFY.expression_references("other.purchaseData", "product.purchaseData")
        )


if __name__ == "__main__":
    unittest.main()
