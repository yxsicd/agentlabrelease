from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


CAMPAIGN_TEST = module(
    ROOT / "tests/test_harmony_assessed_campaign.py", "agentlab_campaign_fixture"
)
IMPORT = module(
    ROOT / "scripts/harmony_device_campaign_import.py", "agentlab_device_import"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_binding(root: Path, path: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest(path),
        "byteLength": path.stat().st_size,
    }


def workspace_state(root: Path) -> dict:
    rows = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows[path.relative_to(root).as_posix()] = {
            "sha256": digest(path),
            "byteLength": path.stat().st_size,
            "unixMode": stat.S_IMODE(path.stat().st_mode),
        }
    return rows


class HarmonyDeviceCampaignImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = CAMPAIGN_TEST.HarmonyAssessedCampaignTests(
            methodName="test_static_passes_run_device_and_close_feedback_loop"
        )
        self.fixture.setUp()
        self.root = self.fixture.root
        self.run_id = 424242
        plan = json.loads(self.fixture.plan.read_text())
        for row in plan["attempts"]:
            row["producerRun"] = self.run_id
        self.fixture.plan.write_text(json.dumps(plan))
        self.output = self.root / "campaign-output"
        completed = self.fixture.execute(self.output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.plan = json.loads(self.fixture.plan.read_text())
        self.source_run = self.root / "source-run.json"
        self.source_run.write_text(
            json.dumps(
                {
                    "id": self.run_id,
                    "run_attempt": 1,
                    "head_sha": "d" * 40,
                    "path": ".github/workflows/multi-repo-assessed-campaign.yml",
                    "event": "workflow_dispatch",
                    "head_branch": "main",
                    "status": "completed",
                    "conclusion": "success",
                    "repository": {"full_name": "example/agentlab"},
                }
            )
        )
        self.handoff = self.root / "harmony-device-handoff.json"
        attempts = []
        for participant, assessment_root in (
            ("strong", self.fixture.strong),
            ("weak", self.fixture.weak),
        ):
            state = workspace_state(assessment_root / "workspace")
            attempts.append(
                {
                    "attemptId": f"{participant}-1",
                    "participantId": participant,
                    "producerRun": self.run_id,
                    "assessment": {
                        "path": assessment_root.relative_to(self.root).as_posix(),
                        "summary": file_binding(self.root, assessment_root / "summary.json"),
                        "decisionPackage": file_binding(
                            self.root, assessment_root / "decision-package.json"
                        ),
                        "finalSourceState": file_binding(
                            self.root, assessment_root / "final-source-state.json"
                        ),
                        "workspace": {
                            "path": (assessment_root / "workspace")
                            .relative_to(self.root)
                            .as_posix(),
                            "treeSha256": canonical(state),
                            "fileCount": len(state),
                        },
                    },
                }
            )
        collection = {
            "schema": "agentlab.case_attempt_collection.v2",
            "sourceSetSha256": self.fixture.source_set,
            "methodRevision": "d" * 40,
            "cases": [
                {
                    "id": "campaign-case",
                    "calibration": self.fixture.calibration.name,
                    "attempts": [
                        {
                            "attemptId": row["attemptId"],
                            "participantId": row["participantId"],
                            "producerRun": self.run_id,
                            "evidence": row["assessment"]["path"],
                        }
                        for row in attempts
                    ],
                }
            ],
        }
        collection_path = self.root / "attempts.json"
        collection_path.write_text(json.dumps(collection))
        self.handoff.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_assessed_campaign_handoff.v1",
                    "campaignId": "campaign-r1",
                    "caseId": "campaign-case",
                    "sourceSetSha256": self.fixture.source_set,
                    "methodRevision": "d" * 40,
                    "evaluationCase": file_binding(self.root, self.fixture.case),
                    "calibration": file_binding(self.root, self.fixture.calibration),
                    "attemptCollection": file_binding(self.root, collection_path),
                    "attempts": attempts,
                    "automaticPromotion": False,
                    "nextGate": "resolve-on-qualified-harmony-host",
                }
            )
        )
        self.profile = self.root / "host-profile.json"
        device = self.plan["device"]
        runtime = device["runtime"]
        profile_runtime = {
            key: value
            for key, value in runtime.items()
            if key
            not in {
                "runner",
                "runnerSha256",
                "toolsRoot",
                "imageRoot",
                "instancePath",
            }
        }
        profile_runtime.update(
            {
                "runner": {"path": "runner.py", "sha256": runtime["runnerSha256"]},
                "toolsRoot": "tools",
                "imageRoot": "image",
                "instancePath": "instance",
            }
        )
        self.profile.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_assessed_host_profile.v1",
                    "profileId": "test-host",
                    "programs": {
                        key: {"path": Path(value["path"]).name, "sha256": value["sha256"]}
                        for key, value in self.plan["programs"].items()
                    },
                    "sourceMaterialization": self.plan["sourceMaterialization"],
                    "build": {
                        "executable": {
                            "path": "builder.py",
                            "sha256": self.plan["build"]["executableSha256"],
                        },
                        **{
                            key: value
                            for key, value in self.plan["build"].items()
                            if key not in {"executable", "executableSha256"}
                        },
                    },
                    "device": {
                        "subjectOutcomePolicy": "retain-assessed-failure",
                        "functionalOracle": {
                            "path": "scenario.ui",
                            "sha256": device["functionalOracle"]["sha256"],
                            "scenarioId": device["functionalOracle"]["scenarioId"],
                        },
                        "runtime": profile_runtime,
                        "performance": {
                            "policy": {
                                "path": "policy.json",
                                "sha256": device["performance"]["policySha256"],
                            },
                            "workload": {
                                "path": "workload.tsv",
                                "sha256": device["performance"]["workloadSha256"],
                            },
                        },
                    },
                    "requiredTrials": 1,
                    "eligibilityThreshold": 0.6,
                    "automaticPromotion": False,
                }
            )
        )
        self.archive = self.root / "device-campaign.zip"

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def prepare(self) -> dict:
        return IMPORT.prepare_bundle(
            self.output,
            self.handoff,
            self.profile,
            self.fixture.plan,
            self.source_run,
            self.archive,
        )

    def test_round_trip_reconstructs_trusted_device_report(self) -> None:
        manifest = self.prepare()
        imported = self.root / "imported"
        result = IMPORT.verify_bundle(
            self.archive, self.root, self.source_run, imported, "e" * 40
        )
        report = json.loads(
            (imported / "verified/case-discrimination-report.json").read_text()
        )
        self.assertEqual(manifest["sourceAssessedCampaign"]["runId"], self.run_id)
        self.assertEqual(result["sourceMethodRevision"], "d" * 40)
        self.assertEqual(result["verificationMethodRevision"], "e" * 40)
        self.assertTrue(result["harmonyEndToEndEvidenceQualified"])
        self.assertTrue(
            report["ranking"][0]["processMeasurement"]["harmonyDevice"][
                "endToEndEvidenceQualified"
            ]
        )
        self.assertFalse(result["automaticPromotion"])

    def test_archive_member_tampering_is_rejected(self) -> None:
        self.prepare()
        replacement = self.root / "tampered.zip"
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(
            replacement, "w"
        ) as target:
            for info in source.infolist():
                body = source.read(info.filename)
                if info.filename == "campaign/summary.json":
                    body += b" "
                target.writestr(info, body)
        with self.assertRaisesRegex(IMPORT.ImportError, "byte length differs"):
            IMPORT.verify_bundle(
                replacement,
                self.root,
                self.source_run,
                self.root / "tampered-import",
                "e" * 40,
            )

    def test_older_derived_report_is_retained_but_trusted_report_is_rebuilt(self) -> None:
        report_path = self.output / "case-discrimination-report.json"
        report = json.loads(report_path.read_text())
        report["policy"]["legacyProducerMarker"] = True
        report_path.write_text(json.dumps(report))
        summary_path = self.output / "summary.json"
        summary = json.loads(summary_path.read_text())
        summary["discriminationReportSha256"] = digest(report_path)
        summary_path.write_text(json.dumps(summary))
        state_path = self.output / "campaign-state.json"
        state = json.loads(state_path.read_text())
        state["summarySha256"] = digest(summary_path)
        state_path.write_text(json.dumps(state))
        self.prepare()
        imported = self.root / "legacy-import"
        result = IMPORT.verify_bundle(
            self.archive, self.root, self.source_run, imported, "e" * 40
        )
        self.assertFalse(
            result["trustedReconstruction"]["originalReportMatched"]
        )
        rebuilt = json.loads(
            (imported / "verified/case-discrimination-report.json").read_text()
        )
        self.assertNotIn("legacyProducerMarker", rebuilt["policy"])

    def test_authoritative_handoff_drift_is_rejected(self) -> None:
        self.prepare()
        value = json.loads(self.handoff.read_text())
        value["campaignId"] = "different"
        self.handoff.write_text(json.dumps(value))
        with self.assertRaisesRegex(IMPORT.ImportError, "handoff differs"):
            IMPORT.verify_bundle(
                self.archive,
                self.root,
                self.source_run,
                self.root / "drift-import",
                "e" * 40,
            )

    def test_source_run_identity_drift_is_rejected(self) -> None:
        self.prepare()
        value = json.loads(self.source_run.read_text())
        value["id"] += 1
        self.source_run.write_text(json.dumps(value))
        with self.assertRaisesRegex(IMPORT.ImportError, "source workflow run differs"):
            IMPORT.verify_bundle(
                self.archive,
                self.root,
                self.source_run,
                self.root / "run-drift-import",
                "e" * 40,
            )

    def test_trusted_main_workflow_reconstructs_and_attests_import(self) -> None:
        workflow = (
            ROOT / ".github/workflows/harmony-device-campaign-import.yml"
        ).read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("multi-repo-assessed-campaign", workflow)
        self.assertIn("harmony-device-assessed-campaign", workflow)
        self.assertIn("import-harmony-device-campaign.py verify", workflow)
        self.assertIn("--verification-revision \"$GITHUB_SHA\"", workflow)
        self.assertIn("gh release download", workflow)
        self.assertIn("sha256sum -c -", workflow)
        self.assertIn("participant-experiment-plan.json", workflow)
        self.assertIn("static-plan-attestation-verification.json", workflow)
        self.assertIn("Re-attest the pre-outcome participant experiment plan", workflow)
        self.assertEqual(
            workflow.count(
                "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
