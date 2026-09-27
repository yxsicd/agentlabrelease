use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

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

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "agentlab-ohostest-review-packet-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
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

fn run(output: &Path, qualification: &Path, patch: &Path) -> std::process::Output {
    let evidence = evidence();
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-review-packet"
    ))
    .args([
        "--qualification",
        qualification.to_str().unwrap(),
        "--observation",
        evidence
            .join("purchase-data-ohostest-candidate-observation.json")
            .to_str()
            .unwrap(),
        "--execution-receipt",
        evidence
            .join("purchase-data-ohostest-candidate-execution-receipt.json")
            .to_str()
            .unwrap(),
        "--native-report",
        evidence
            .join("purchase-data-ohostest-candidate-native-report.json")
            .to_str()
            .unwrap(),
        "--patch",
        patch.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn builds_fail_closed_exact_source_review_packet() {
    let temp = root();
    let evidence = evidence();
    let qualification = evidence.join("purchase-data-ohostest-candidate-qualification.json");
    let patch = evidence.join("purchase-data-ohostest-candidate.patch");
    let output = temp.join("packet.json");
    let result = run(&output, &qualification, &patch);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let packet = read(&output);
    assert_eq!(packet["status"], "independent-source-review-required");
    assert_eq!(packet["change"]["fileCount"], 6);
    assert_eq!(packet["execution"]["passed"], 7);
    assert_eq!(
        packet["reviewDecisionContract"]["questions"]
            .as_array()
            .unwrap()
            .len(),
        6
    );
    assert_eq!(packet["risks"].as_array().unwrap().len(), 6);
    assert_eq!(packet["publishedToUpstream"], false);
    assert_eq!(packet["independentReviewVerified"], false);
    assert_eq!(packet["allowsCaseContract"], false);
    assert_eq!(packet["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_patch_drift_and_self_approved_qualification() {
    let temp = root();
    let evidence = evidence();
    let original_qualification =
        evidence.join("purchase-data-ohostest-candidate-qualification.json");
    let original_patch = evidence.join("purchase-data-ohostest-candidate.patch");

    let patch = temp.join("candidate.patch");
    let mut bytes = fs::read(&original_patch).unwrap();
    bytes.extend_from_slice(b"# drift\n");
    fs::write(&patch, bytes).unwrap();
    let result = run(
        &temp.join("patch-drift.json"),
        &original_qualification,
        &patch,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("patch digest differs"));

    let qualification = temp.join("qualification.json");
    let mut value = read(&original_qualification);
    value["independentReviewVerified"] = json!(true);
    write(&qualification, &value);
    let result = run(
        &temp.join("self-approved.json"),
        &qualification,
        &original_patch,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("candidate qualification independentReviewVerified differs"));
    fs::remove_dir_all(temp).unwrap();
}
