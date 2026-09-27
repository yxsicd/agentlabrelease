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

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "agentlab-ohostest-candidate-{}-{}-{}",
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

fn run(output: &Path, report: &Path, observation: &Path) -> std::process::Output {
    let evidence = evidence();
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-candidate-qualification"
    ))
    .args([
        "--reference-qualification",
        evidence
            .join("purchase-data-ohostest-reference-qualification.json")
            .to_str()
            .unwrap(),
        "--execution-receipt",
        evidence
            .join("purchase-data-ohostest-candidate-execution-receipt.json")
            .to_str()
            .unwrap(),
        "--native-report",
        report.to_str().unwrap(),
        "--observation",
        observation.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn qualifies_candidate_without_claiming_independent_review_or_upstream_publication() {
    let temp = root();
    let evidence = evidence();
    let report = evidence.join("purchase-data-ohostest-candidate-native-report.json");
    let observation = evidence.join("purchase-data-ohostest-candidate-observation.json");
    let output = temp.join("qualification.json");
    let result = run(&output, &report, &observation);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(value["coverage"]["testCount"], 7);
    assert_eq!(value["coverage"]["emulatorStopped"], true);
    assert_eq!(
        value["projectTreeSha256"],
        "85d851734450a611e2bed1c5f15ddf9da150309ca97c3b914b0d3d19eb443144"
    );
    assert_eq!(value["publishedToUpstream"], false);
    assert_eq!(value["independentReviewVerified"], false);
    assert_eq!(value["behaviorOracleVerified"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_parent_count_and_inventory_drift() {
    let temp = root();
    let evidence = evidence();
    let original_report = evidence.join("purchase-data-ohostest-candidate-native-report.json");
    let original_observation = evidence.join("purchase-data-ohostest-candidate-observation.json");
    let report = temp.join("report.json");
    let observation = temp.join("observation.json");

    let mut value = read(&original_observation);
    value["parentRevision"] = json!("0000000000000000000000000000000000000000");
    write(&observation, &value);
    let result = run(
        &temp.join("qualification-parent.json"),
        &original_report,
        &observation,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("parent revision differs"));

    value = read(&original_observation);
    value["testNames"]
        .as_array_mut()
        .unwrap()
        .push(json!("missingJwsDoesNotFinish"));
    write(&observation, &value);
    let result = run(
        &temp.join("qualification-inventory.json"),
        &original_report,
        &observation,
    );
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("inventory differs"),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );

    value = read(&original_report);
    value["counts"]["total"] = json!(6);
    write(&report, &value);
    let result = run(
        &temp.join("qualification-count.json"),
        &report,
        &original_observation,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("count total differs"));

    value = read(&original_observation);
    value["executionBinding"]["projectTreeSha256"] =
        json!("0000000000000000000000000000000000000000000000000000000000000000");
    write(&observation, &value);
    let result = run(
        &temp.join("qualification-project-tree.json"),
        &original_report,
        &observation,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("clean project tree digest differs"));
    fs::remove_dir_all(temp).unwrap();
}
