use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
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
];

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
        "agentlab-purchase-data-integrated-review-{}-{}-{}",
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

fn run(root: &Path, output: &Path) -> std::process::Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-integrated-review-packet"
    ))
    .args([
        "--qualification-root",
        root.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn binds_current_semantic_runtime_and_performance_evidence_without_self_approval() {
    let root = fixture();
    let output = root.join("packet.json");
    let result = run(&root, &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let packet = read(&output);
    assert_eq!(
        packet["schema"],
        "agentlab.purchase_data_integrated_review_packet.v1"
    );
    assert_eq!(packet["evidenceAttachments"].as_object().unwrap().len(), 8);
    assert_eq!(packet["coverage"]["repositoryCount"], 2);
    assert_eq!(packet["coverage"]["functionalMutationScore"], 1.0);
    assert_eq!(packet["coverage"]["controlledPerformanceWrongRunCount"], 2);
    assert_eq!(
        packet["reviewDecisionContract"]["minimumDistinctReviewerCount"],
        2
    );
    assert_eq!(packet["relativePerformanceDetectorCalibrated"], true);
    assert_eq!(packet["semanticAlignmentVerified"], false);
    assert_eq!(packet["behaviorOracleVerified"], false);
    assert_eq!(packet["performanceCalibrated"], false);
    assert_eq!(packet["allowsCaseContract"], false);
    assert_eq!(packet["automaticPromotion"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_semantic_packet_drift_without_oracle_lineage_rebind() {
    let root = fixture();
    let path = root.join("review-packets/purchase-data-control-flow-v11.json");
    let mut value = read(&path);
    value["risks"][0]["statement"] = json!("drifted semantic risk");
    write(&path, &value);
    let result = run(&root, &root.join("packet.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("Oracle plan semantic packet digest differs"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_forged_full_performance_calibration() {
    let root = fixture();
    let path = root.join("purchase-data-ohostest-performance-detector-qualification.json");
    let mut value = read(&path);
    value["performanceCalibrated"] = json!(true);
    write(&path, &value);
    let result = run(&root, &root.join("packet.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("detector qualification performanceCalibrated differs"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_forged_cordova_runtime_coverage() {
    let root = fixture();
    let path = root.join("purchase-data-runtime-oracle-bridge.json");
    let mut value = read(&path);
    value["cordovaRuntimeCalibrated"] = json!(true);
    value["coverage"]["cordovaRuntimeBoundCheckCount"] = json!(5);
    write(&path, &value);
    let result = run(&root, &root.join("packet.json"));
    assert!(!result.status.success());
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(
        stderr.contains("runtime bridge coverage cordovaRuntimeBoundCheckCount differs")
            || stderr.contains("runtime bridge cordovaRuntimeCalibrated differs")
    );
    fs::remove_dir_all(root).unwrap();
}
