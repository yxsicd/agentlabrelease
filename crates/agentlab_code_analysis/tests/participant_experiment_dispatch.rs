use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-participant-dispatch-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

struct Fixture {
    root: PathBuf,
    case: PathBuf,
    manifest: PathBuf,
    archive: PathBuf,
    dispatch: PathBuf,
    runtime: PathBuf,
    attestation: PathBuf,
    plan: PathBuf,
    receipt: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let root = temp_root();
        let case = root.join("case.json");
        write(
            &case,
            &json!({"id": "case-one", "sourceSetSha256": "a".repeat(64)}),
        );
        let manifest = root.join("manifest.json");
        write(
            &manifest,
            &json!({"schema": "agentlab.blind_case_participant_bundle.v1"}),
        );
        let archive = root.join("participant-runtime-image.tar");
        fs::write(&archive, b"portable image fixture").unwrap();
        let runtime = root.join("runtime.json");
        let lock = repository().join("examples/real-code-agent/participant/package-lock.json");
        write(
            &runtime,
            &json!({
                "schema": "agentlab.participant_docker_runtime.v1",
                "imageId": format!("sha256:{}", "b".repeat(64)),
                "piPackageLockSha256": digest(&fs::read(lock).unwrap()),
                "participantManifestSha256": digest(&fs::read(&manifest).unwrap()),
            }),
        );
        Self {
            dispatch: root.join("dispatch.json"),
            attestation: root.join("attestation.json"),
            plan: root.join("plan.json"),
            receipt: root.join("receipt.json"),
            root,
            case,
            manifest,
            archive,
            runtime,
        }
    }

    fn freeze(&self) -> Output {
        let repo = repository();
        Command::new(env!("CARGO_BIN_EXE_agentlab-participant-experiment-dispatch"))
            .args([
                "freeze",
                "--repository-root",
                repo.to_str().unwrap(),
                "--repository",
                "example/agentlab",
                "--workflow-run-id",
                "1001",
                "--workflow-run-attempt",
                "2",
                "--case",
                self.case.to_str().unwrap(),
                "--case-review-run-id",
                "901",
                "--method-revision",
                &"c".repeat(40),
                "--profiles-json",
                r#"[{"participantId":"weak","model":"model-a"},{"participantId":"middle","model":"model-b"},{"participantId":"strong","model":"model-c"}]"#,
                "--provider-route",
                "gateway",
                "--trials",
                "5",
                "--participant-adapter",
                repo.join("examples/multi-repo-case/pi-assessed-agent.py")
                    .to_str()
                    .unwrap(),
                "--participant-driver",
                repo.join("examples/real-code-agent/participant.py")
                    .to_str()
                    .unwrap(),
                "--participant-package-lock",
                repo.join("examples/real-code-agent/participant/package-lock.json")
                    .to_str()
                    .unwrap(),
                "--participant-manifest",
                self.manifest.to_str().unwrap(),
                "--runtime-dockerfile",
                repo.join("examples/knowledge-seed/subject/participant.Dockerfile")
                    .to_str()
                    .unwrap(),
                "--runtime-build-script",
                repo.join("examples/knowledge-seed/subject/participant-runtime.sh")
                    .to_str()
                    .unwrap(),
                "--runtime-image-id",
                &format!("sha256:{}", "b".repeat(64)),
                "--runtime-image-archive",
                self.archive.to_str().unwrap(),
                "--output",
                self.dispatch.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn attest(&self) {
        write(
            &self.attestation,
            &json!([{
                "verificationResult": {
                    "statement": {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "subject": [{"digest": {"sha256": digest(&fs::read(&self.dispatch).unwrap())}}],
                        "predicate": {"runDetails": {"metadata": {
                            "invocationId": "https://github.com/example/agentlab/actions/runs/1001/attempts/2"
                        }}}
                    }
                }
            }]),
        );
    }

    fn materialize(&self) -> Output {
        let repo = repository();
        Command::new(env!(
            "CARGO_BIN_EXE_agentlab-participant-experiment-dispatch"
        ))
        .args([
            "materialize",
            "--repository-root",
            repo.to_str().unwrap(),
            "--repository",
            "example/agentlab",
            "--workflow-run-id",
            "1001",
            "--workflow-run-attempt",
            "2",
            "--method-revision",
            &"c".repeat(40),
            "--dispatch",
            self.dispatch.to_str().unwrap(),
            "--attestation-verification",
            self.attestation.to_str().unwrap(),
            "--case",
            self.case.to_str().unwrap(),
            "--runtime-image-archive",
            self.archive.to_str().unwrap(),
            "--runtime-config",
            self.runtime.to_str().unwrap(),
            "--output",
            self.plan.to_str().unwrap(),
            "--verification-output",
            self.receipt.to_str().unwrap(),
        ])
        .output()
        .unwrap()
    }
}

#[test]
fn freezes_attested_portable_dispatch_and_materializes_local_plan() {
    let fixture = Fixture::new();
    let result = fixture.freeze();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let dispatch = read(&fixture.dispatch);
    assert_eq!(
        dispatch["status"],
        "attested-plan-gate-frozen-before-assessment"
    );
    assert_eq!(dispatch["participantProfileCount"], 3);
    assert_eq!(
        dispatch["executionProtocol"]["portableRuntimeQualified"],
        true
    );
    assert_eq!(
        dispatch["executionProtocol"]["runtimeImageArchive"]["byteLength"],
        22
    );
    fixture.attest();
    let result = fixture.materialize();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let plan = read(&fixture.plan);
    let receipt = read(&fixture.receipt);
    assert_eq!(plan["schema"], "agentlab.participant_experiment_plan.v1");
    assert_eq!(plan["participantProfiles"], dispatch["participantProfiles"]);
    assert_eq!(
        plan["executionProtocol"]["runtimeImageId"],
        format!("sha256:{}", "b".repeat(64))
    );
    assert_eq!(
        receipt["status"],
        "attested-portable-dispatch-materialized-before-attempts"
    );
    assert_eq!(receipt["attemptsStarted"], false);
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn rejects_archive_drift_before_plan_materialization() {
    let fixture = Fixture::new();
    assert!(fixture.freeze().status.success());
    fixture.attest();
    fs::write(&fixture.archive, b"different archive").unwrap();
    let result = fixture.materialize();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("runtime image archive byte length differs"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn rejects_attestation_from_another_run() {
    let fixture = Fixture::new();
    assert!(fixture.freeze().status.success());
    fixture.attest();
    let mut value = read(&fixture.attestation);
    value[0]["verificationResult"]["statement"]["predicate"]["runDetails"]["metadata"]
        ["invocationId"] =
        json!("https://github.com/example/agentlab/actions/runs/1002/attempts/2");
    write(&fixture.attestation, &value);
    let result = fixture.materialize();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("dispatch attestation does not bind the exact workflow run"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn rejects_repository_input_drift() {
    let fixture = Fixture::new();
    assert!(fixture.freeze().status.success());
    fixture.attest();
    let mut dispatch = read(&fixture.dispatch);
    dispatch["executionProtocol"]["participantAdapter"]["sha256"] = json!("d".repeat(64));
    write(&fixture.dispatch, &dispatch);
    fixture.attest();
    let result = fixture.materialize();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("participant adapter digest differs"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_symlinked_portable_archive() {
    use std::os::unix::fs::symlink;

    let fixture = Fixture::new();
    let target = fixture.root.join("archive-target.tar");
    fs::rename(&fixture.archive, &target).unwrap();
    symlink(&target, &fixture.archive).unwrap();
    let result = fixture.freeze();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("participant runtime image archive must be a regular file"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn workflow_requires_attested_freeze_job_before_assessment() {
    let root = repository();
    let workflow =
        fs::read_to_string(root.join(".github/workflows/multi-repo-assessed-campaign.yml"))
            .unwrap();
    let schema: Value = serde_json::from_slice(
        &fs::read(root.join("schemas/participant-experiment-dispatch.schema.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(
        schema["properties"]["schema"]["const"],
        "agentlab.participant_experiment_dispatch.v1"
    );
    assert_eq!(
        schema["properties"]["executionProtocol"]["properties"]["portableRuntimeQualified"]
            ["const"],
        true
    );
    assert!(workflow.contains("freeze-plan:"));
    assert!(workflow.contains("needs: freeze-plan"));
    assert!(workflow.contains("agentlab-participant-experiment-dispatch -- freeze"));
    assert!(workflow.contains("agentlab-participant-experiment-dispatch -- materialize"));
    assert!(workflow.contains("gh attestation verify"));
    assert!(workflow.contains("participant-runtime-image.tar"));
    assert!(!workflow.contains("participant-experiment-plan.py create"));
    assert!(
        workflow
            .find("Attest the pre-execution participant dispatch")
            .unwrap()
            < workflow
                .find("Run fresh staged attempts for every predeclared capability tier")
                .unwrap()
    );
}
