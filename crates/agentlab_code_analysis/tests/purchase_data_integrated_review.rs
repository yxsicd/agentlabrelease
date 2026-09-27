use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

const INPUTS: &[&str] = &[
    "review-packets/purchase-data-control-flow-v11.json",
    "purchase-data-behavior-oracle-plan.json",
    "purchase-data-behavior-oracle-calibration.json",
    "purchase-data-ohostest-review-packet.json",
    "purchase-data-ohostest-mutation-qualification.json",
    "purchase-data-runtime-oracle-bridge.json",
    "purchase-data-ohostest-profile-qualification.json",
    "purchase-data-ohostest-performance-detector-qualification.json",
    "purchase-data-case-performance-qualification.json",
    "purchase-data-integrated-review-packet-v2.json",
];

const RISKS: &str = "independent-semantic-review-pending,self-authored-source-candidate,cordova-runtime-source-seam-only,live-vendor-iap-unexecuted,x86-emulator-not-real-device,controlled-performance-variants-not-agent-evaluation,absolute-power-thermal-unavailable,upstream-source-unpublished";

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

fn evidence() -> PathBuf {
    repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd")
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-purchase-data-integrated-review-gate-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}

fn fixture() -> PathBuf {
    let root = temp_root();
    for relative in INPUTS {
        let source = evidence().join(relative);
        let target = root.join(relative);
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        fs::copy(source, target).unwrap();
    }
    root
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
        "schema": "agentlab.purchase_data_integrated_review_answers.v1",
        "responses": [
            {"id": "cross-repository-semantic-coherence", "answer": answer, "rationale": "The exact two-repository facts and control-flow evidence were inspected."},
            {"id": "source-patch-preservation", "answer": answer, "rationale": "The exact source patch and production-preservation boundary were inspected."},
            {"id": "functional-oracle-discrimination", "answer": answer, "rationale": "The OHOS Test cases and all killed meaningful wrong variants were inspected."},
            {"id": "runtime-mapping-scope", "answer": answer, "rationale": "The Harmony runtime mapping and absent Cordova runtime mapping were inspected."},
            {"id": "case-performance-discrimination", "answer": answer, "rationale": "The six case-bound cold runs and both consistently rejected controlled performance faults were inspected."},
            {"id": "residual-boundary-honesty", "answer": answer, "rationale": "Every retained unqualified runtime and device boundary was inspected."}
        ]
    })
}

fn run(args: &[&str]) -> Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-integrated-review"
    ))
    .args(args)
    .output()
    .unwrap()
}

fn decide(
    root: &Path,
    role: &str,
    reviewer: &str,
    answers_path: &Path,
    verdict: &str,
    output: &Path,
) -> Output {
    let packet = root.join("purchase-data-integrated-review-packet-v2.json");
    let packet_sha = digest(&fs::read(&packet).unwrap());
    run(&[
        "decide",
        "--packet",
        packet.to_str().unwrap(),
        "--qualification-root",
        root.to_str().unwrap(),
        "--expected-packet-sha256",
        &packet_sha,
        "--role",
        role,
        "--reviewer",
        reviewer,
        "--answers",
        answers_path.to_str().unwrap(),
        "--acknowledged-risk-ids",
        RISKS,
        "--verdict",
        verdict,
        "--rationale",
        "The exact integrated evidence, review questions, risks and remaining authority boundaries were independently inspected.",
        "--output",
        output.to_str().unwrap(),
    ])
}

fn compile(root: &Path, semantic: &Path, oracle: &Path, gate: &Path) -> Output {
    run(&[
        "compile",
        "--packet",
        root.join("purchase-data-integrated-review-packet-v2.json")
            .to_str()
            .unwrap(),
        "--qualification-root",
        root.to_str().unwrap(),
        "--semantic-decision",
        semantic.to_str().unwrap(),
        "--oracle-decision",
        oracle.to_str().unwrap(),
        "--output",
        gate.to_str().unwrap(),
    ])
}

fn validate(root: &Path, semantic: &Path, oracle: &Path, gate: &Path) -> Output {
    run(&[
        "validate",
        "--packet",
        root.join("purchase-data-integrated-review-packet-v2.json")
            .to_str()
            .unwrap(),
        "--qualification-root",
        root.to_str().unwrap(),
        "--semantic-decision",
        semantic.to_str().unwrap(),
        "--oracle-decision",
        oracle.to_str().unwrap(),
        "--gate",
        gate.to_str().unwrap(),
    ])
}

#[test]
fn two_distinct_unanimous_reviewers_authorize_only_next_gates() {
    let root = fixture();
    let answers_path = root.join("answers.json");
    let semantic = root.join("semantic-decision.json");
    let oracle = root.join("oracle-decision.json");
    let gate = root.join("gate.json");
    write(&answers_path, &answers("yes"));
    assert!(decide(
        &root,
        "semantic",
        "github:semantic-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &semantic,
    )
    .status
    .success());
    assert!(decide(
        &root,
        "oracle",
        "github:oracle-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &oracle,
    )
    .status
    .success());
    let result = compile(&root, &semantic, &oracle, &gate);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(validate(&root, &semantic, &oracle, &gate).status.success());
    let value = read(&gate);
    assert_eq!(
        value["status"],
        "independent-dual-review-approved-next-calibration-only"
    );
    assert_eq!(value["distinctAuthenticatedReviewerCount"], 2);
    assert_eq!(value["semanticAlignmentVerified"], true);
    assert_eq!(value["independentSourceReviewCompleted"], true);
    assert_eq!(value["independentOracleReviewCompleted"], true);
    assert_eq!(value["allowsExactPatchPublication"], true);
    assert_eq!(value["allowsDistinctCasePerformanceCalibration"], false);
    assert_eq!(value["allowsUnseenAgentCohortEvaluation"], true);
    assert_eq!(value["behaviorOracleVerified"], false);
    assert_eq!(value["performanceCalibrated"], true);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_same_authenticated_actor_in_both_roles() {
    let root = fixture();
    let answers_path = root.join("answers.json");
    let semantic = root.join("semantic-decision.json");
    let oracle = root.join("oracle-decision.json");
    write(&answers_path, &answers("yes"));
    for (role, reviewer, output) in [
        ("semantic", "github:Same-Reviewer", &semantic),
        ("oracle", "github:same-reviewer", &oracle),
    ] {
        assert!(decide(
            &root,
            role,
            reviewer,
            &answers_path,
            "approve-for-next-calibration-gate",
            output,
        )
        .status
        .success());
    }
    let result = compile(&root, &semantic, &oracle, &root.join("gate.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("semantic and Oracle reviewers must be distinct"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_attachment_drift_even_when_packet_bytes_are_unchanged() {
    let root = fixture();
    let attachment = root.join("purchase-data-runtime-oracle-bridge.json");
    let mut value = read(&attachment);
    value["boundary"] =
        json!("A changed boundary that is not bound by the retained packet digest.");
    write(&attachment, &value);
    let answers_path = root.join("answers.json");
    write(&answers_path, &answers("yes"));
    let result = decide(
        &root,
        "semantic",
        "github:semantic-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &root.join("semantic-decision.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("evidence attachment digest runtime-oracle-bridge differs"));
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_symlinked_evidence_attachment() {
    use std::os::unix::fs::symlink;

    let root = fixture();
    let attachment = root.join("purchase-data-runtime-oracle-bridge.json");
    let target = root.join("runtime-oracle-bridge-target.json");
    fs::rename(&attachment, &target).unwrap();
    symlink(&target, &attachment).unwrap();
    let answers_path = root.join("answers.json");
    write(&answers_path, &answers("yes"));
    let result = decide(
        &root,
        "semantic",
        "github:semantic-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &root.join("semantic-decision.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("evidence attachment must be a regular file: runtime-oracle-bridge"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_non_unanimous_approval() {
    let root = fixture();
    let answers_path = root.join("answers.json");
    let mut value = answers("yes");
    value["responses"][0]["answer"] = json!("unknown");
    write(&answers_path, &value);
    let result = decide(
        &root,
        "oracle",
        "github:oracle-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &root.join("oracle-decision.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("approval requires every integrated-review answer to be yes"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_tampered_case_contract_authority() {
    let root = fixture();
    let answers_path = root.join("answers.json");
    let semantic = root.join("semantic-decision.json");
    let oracle = root.join("oracle-decision.json");
    let gate = root.join("gate.json");
    write(&answers_path, &answers("yes"));
    assert!(decide(
        &root,
        "semantic",
        "github:semantic-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &semantic,
    )
    .status
    .success());
    assert!(decide(
        &root,
        "oracle",
        "github:oracle-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &oracle,
    )
    .status
    .success());
    assert!(compile(&root, &semantic, &oracle, &gate).status.success());
    let mut value = read(&gate);
    value["allowsCaseContract"] = json!(true);
    fs::remove_file(&gate).unwrap();
    write(&gate, &value);
    let result = validate(&root, &semantic, &oracle, &gate);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("integrated gate allowsCaseContract differs"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_weakened_minimum_reviewer_contract() {
    let root = fixture();
    let packet = root.join("purchase-data-integrated-review-packet-v2.json");
    let mut value = read(&packet);
    value["reviewDecisionContract"]["minimumDistinctReviewerCount"] = json!(1);
    write(&packet, &value);
    let answers_path = root.join("answers.json");
    write(&answers_path, &answers("yes"));
    let result = decide(
        &root,
        "semantic",
        "github:semantic-reviewer",
        &answers_path,
        "approve-for-next-calibration-gate",
        &root.join("semantic-decision.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("review contract minimumDistinctReviewerCount differs"));
    fs::remove_dir_all(root).unwrap();
}
