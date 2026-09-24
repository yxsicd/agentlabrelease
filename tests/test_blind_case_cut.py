from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-blind-case-cut.py"
SPEC = importlib.util.spec_from_file_location("blind_case_cut", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fixture(root: Path, visibility: str = "private-maintenance") -> Path:
    source = root / "source"
    participant = source / "participant"
    evaluator = source / "evaluator"
    participant.mkdir(parents=True)
    evaluator.mkdir()
    (participant / "task.md").write_text("Repair the registered page without changing existing routes.\n", encoding="utf-8")
    (participant / "source.json").write_text('{"revision":"baseline"}\n', encoding="utf-8")
    (evaluator / "oracle.ui").write_text("assert-text\ttarget\tExample Domain\n", encoding="utf-8")
    (evaluator / "reference.patch").write_text("+pages/UserAgent_four\n", encoding="utf-8")
    value = {
        "schema": "agentlab.blind_case_source.v1",
        "cutId": "private-cut-001",
        "caseId": "harmony-page-registration-001",
        "methodRevision": "1" * 40,
        "sourceSetSha256": "2" * 64,
        "participantFiles": [
            {"path": "task.md", "role": "task", "sha256": sha(participant / "task.md")},
            {"path": "source.json", "role": "source", "sha256": sha(participant / "source.json")},
        ],
        "evaluatorFiles": [
            {"path": "oracle.ui", "role": "oracle", "sha256": sha(evaluator / "oracle.ui")},
            {"path": "reference.patch", "role": "reference", "sha256": sha(evaluator / "reference.patch")},
        ],
        "participantConstraints": {
            "allowedEditPaths": ["entry/src/main/resources/base/profile/main_pages.json"],
            "budget": {"turns": 8},
            "environmentRef": "harmony-linux-x86-pinned",
            "networkPolicy": "disabled",
        },
        "freshness": {
            "sourceVisibility": visibility,
            "cutConstructedAt": "2026-09-24T21:00:00Z",
            "participantAccessBeforeCut": False,
            "modelTrainingExclusionKnown": False,
            "contaminationReview": "not-performed",
        },
    }
    (source / "case-source.json").write_text(json.dumps(value), encoding="utf-8")
    return source


class BlindCaseCutTests(unittest.TestCase):
    def test_builds_separate_digest_bound_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "cut"
            receipt = MODULE.build_cut(source_fixture(root), output)
            self.assertTrue(MODULE.validate_cut(output))
            self.assertEqual(receipt["freshness"]["declaredHeldOutAtCut"], True)
            self.assertEqual(receipt["freshness"]["heldOutEvidenceStatus"], "declaration-only")
            self.assertTrue(receipt["freshness"]["eligibleForBlindPilot"])
            self.assertFalse(receipt["freshness"]["eligibleForUnseenAgentDiscrimination"])
            participant_manifest = (output / "participant/manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("oracle.ui", participant_manifest)
            self.assertNotIn("reference.patch", participant_manifest)
            self.assertEqual(
                {path.name for path in (output / "participant").iterdir()},
                {"manifest.json", "task.md", "source.json"},
            )

    def test_public_fixture_is_not_held_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = MODULE.build_cut(source_fixture(root, "public-fixture"), root / "cut")
            self.assertFalse(receipt["freshness"]["declaredHeldOutAtCut"])

    def test_rejects_cross_bundle_byte_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_fixture(root)
            oracle = source / "evaluator/oracle.ui"
            oracle.write_bytes((source / "participant/task.md").read_bytes())
            value = json.loads((source / "case-source.json").read_text())
            value["evaluatorFiles"][0]["sha256"] = sha(oracle)
            (source / "case-source.json").write_text(json.dumps(value))
            with self.assertRaisesRegex(MODULE.BlindCutError, "byte-identical"):
                MODULE.build_cut(source, root / "cut")

    def test_rejects_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_fixture(root)
            (source / "participant/task.md").write_text("changed")
            with self.assertRaisesRegex(MODULE.BlindCutError, "digest differs"):
                MODULE.build_cut(source, root / "cut")

    def test_validator_rejects_unbound_participant_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "cut"
            MODULE.build_cut(source_fixture(root), output)
            (output / "participant/leaked-oracle.txt").write_text("leak")
            with self.assertRaisesRegex(MODULE.BlindCutError, "unbound files"):
                MODULE.validate_cut(output)

    def test_build_refuses_to_overwrite_cut(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = source_fixture(root)
            output = root / "cut"
            MODULE.build_cut(source, output)
            with self.assertRaisesRegex(MODULE.BlindCutError, "refusing to overwrite"):
                MODULE.build_cut(source, output)

    def test_validator_rejects_evaluator_inventory_in_participant_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "cut"
            MODULE.build_cut(source_fixture(root), output)
            manifest_path = output / "participant/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["evaluatorFiles"] = ["oracle.ui"]
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MODULE.BlindCutError, "evaluator or unsupported"):
                MODULE.validate_cut(output)

    def test_stages_participant_without_evaluator_or_operator_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut = root / "cut"
            dispatch = root / "dispatch-input"
            receipt_path = root / "operator/dispatch-receipt.json"
            MODULE.build_cut(source_fixture(root), cut)
            receipt = MODULE.stage_participant(cut, dispatch, receipt_path)
            self.assertEqual(MODULE.validate_dispatch(dispatch, receipt_path), receipt)
            self.assertFalse(receipt["boundary"]["filesystemIsolationQualified"])
            self.assertNotIn("oracle.ui", "\n".join(path.name for path in dispatch.rglob("*")))
            self.assertFalse((dispatch / "dispatch-receipt.json").exists())

    def test_dispatch_rejects_extra_participant_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut = root / "cut"
            dispatch = root / "dispatch-input"
            receipt_path = root / "dispatch-receipt.json"
            MODULE.build_cut(source_fixture(root), cut)
            MODULE.stage_participant(cut, dispatch, receipt_path)
            (dispatch / "extra.txt").write_text("unbound")
            with self.assertRaisesRegex(MODULE.BlindCutError, "unbound files"):
                MODULE.validate_dispatch(dispatch, receipt_path)


if __name__ == "__main__":
    unittest.main()
