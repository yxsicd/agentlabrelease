use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    time::{SystemTime, UNIX_EPOCH},
};

const RISKS: &str = "self-authored-candidate,signature-verification-outside-test-seam,live-vendor-iap-service-unexecuted,x86-emulator-not-real-device,performance-power-thermal-uncalibrated,semantic-and-behavior-oracle-review-pending";

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

fn packet() -> PathBuf {
    repository().join(
        "release/qualifications/alpha13-payment-feedback-analysis-165bcbd/purchase-data-ohostest-review-packet.json",
    )
}

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "agentlab-ohostest-source-review-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn answers(answer: &str) -> Value {
    json!({
        "schema": "agentlab.purchase_data_ohostest_review_answers.v1",
        "responses": [
            {"id": "exact-lineage", "answer": answer, "rationale": "The exact source and evidence lineage was inspected."},
            {"id": "production-seam-preservation", "answer": answer, "rationale": "The production extraction and caller behavior were inspected."},
            {"id": "guard-and-field-correctness", "answer": answer, "rationale": "The guards and forwarded request fields were inspected."},
            {"id": "ohostest-discrimination", "answer": answer, "rationale": "The seven OHOS Test behaviors and gaps were inspected."},
            {"id": "failure-observability", "answer": answer, "rationale": "Decode and finish failure observability was inspected."},
            {"id": "boundary-honesty", "answer": answer, "rationale": "The remaining runtime and performance boundaries were inspected."}
        ]
    })
}

fn run(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agentlab-purchase-data-ohostest-review"))
        .args(args)
        .output()
        .unwrap()
}

fn decide(packet: &Path, answers: &Path, output: &Path, verdict: &str) -> Output {
    let packet_sha = digest(&fs::read(packet).unwrap());
    run(&[
        "decide",
        "--packet",
        packet.to_str().unwrap(),
        "--repository-root",
        repository().to_str().unwrap(),
        "--expected-packet-sha256",
        &packet_sha,
        "--answers",
        answers.to_str().unwrap(),
        "--reviewer",
        "github:independent-reviewer",
        "--acknowledged-risk-ids",
        RISKS,
        "--verdict",
        verdict,
        "--rationale",
        "Exact patch, OHOS Test evidence, risks and remaining gates were independently reviewed.",
        "--output",
        output.to_str().unwrap(),
    ])
}

#[test]
fn approval_allows_only_exact_upstream_publication() {
    let temp = root();
    let packet = packet();
    let answers_path = temp.join("answers.json");
    let decision = temp.join("decision.json");
    let gate = temp.join("gate.json");
    write(&answers_path, &answers("yes"));
    let result = decide(
        &packet,
        &answers_path,
        &decision,
        "approve-for-upstream-publication",
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let result = run(&[
        "compile",
        "--packet",
        packet.to_str().unwrap(),
        "--repository-root",
        repository().to_str().unwrap(),
        "--decision",
        decision.to_str().unwrap(),
        "--output",
        gate.to_str().unwrap(),
    ]);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let result = run(&[
        "validate",
        "--packet",
        packet.to_str().unwrap(),
        "--repository-root",
        repository().to_str().unwrap(),
        "--decision",
        decision.to_str().unwrap(),
        "--gate",
        gate.to_str().unwrap(),
    ]);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&gate);
    assert_eq!(value["allowsUpstreamPublication"], true);
    assert_eq!(value["requiresExactUpstreamRevisionReexecution"], true);
    assert_eq!(value["behaviorOracleVerified"], false);
    assert_eq!(value["performanceCalibrated"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_non_unanimous_approval_and_tampered_gate() {
    let temp = root();
    let packet = packet();
    let answers_path = temp.join("answers.json");
    let decision = temp.join("decision.json");
    let gate = temp.join("gate.json");
    let mut responses = answers("yes");
    responses["responses"][0]["answer"] = json!("unknown");
    write(&answers_path, &responses);
    let result = decide(
        &packet,
        &answers_path,
        &decision,
        "approve-for-upstream-publication",
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("approval requires every source-review answer to be yes"));

    write(&answers_path, &answers("yes"));
    assert!(decide(
        &packet,
        &answers_path,
        &decision,
        "approve-for-upstream-publication"
    )
    .status
    .success());
    assert!(run(&[
        "compile",
        "--packet",
        packet.to_str().unwrap(),
        "--repository-root",
        repository().to_str().unwrap(),
        "--decision",
        decision.to_str().unwrap(),
        "--output",
        gate.to_str().unwrap(),
    ])
    .status
    .success());
    let mut value = read(&gate);
    value["allowsCaseContract"] = json!(true);
    fs::remove_file(&gate).unwrap();
    write(&gate, &value);
    let result = run(&[
        "validate",
        "--packet",
        packet.to_str().unwrap(),
        "--repository-root",
        repository().to_str().unwrap(),
        "--decision",
        decision.to_str().unwrap(),
        "--gate",
        gate.to_str().unwrap(),
    ]);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("source-review gate allowsCaseContract differs"));
    fs::remove_dir_all(temp).unwrap();
}
