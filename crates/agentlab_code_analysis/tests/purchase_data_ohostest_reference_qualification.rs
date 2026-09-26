use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
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
        "agentlab-reference-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

fn run(output: &Path, observation: &Path) -> std::process::Output {
    let evidence =
        repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd");
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-reference-qualification"
    ))
    .args([
        "--proposal",
        evidence
            .join("purchase-data-ohostest-proposal.json")
            .to_str()
            .unwrap(),
        "--execution-receipt",
        evidence
            .join("purchase-data-ohostest-reference-execution-receipt.json")
            .to_str()
            .unwrap(),
        "--native-report",
        evidence
            .join("purchase-data-ohostest-reference-native-report.json")
            .to_str()
            .unwrap(),
        "--observation",
        observation.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn qualifies_exact_reference_execution_without_promoting_upstream() {
    let temp = root();
    let evidence =
        repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd");
    let observation = evidence.join("purchase-data-ohostest-reference-observation.json");
    let output = temp.join("qualification.json");
    let result = run(&output, &observation);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(value["coverage"]["testCount"], 5);
    assert_eq!(value["coverage"]["emulatorExecuted"], true);
    assert_eq!(value["upstreamRevisionModified"], false);
    assert_eq!(value["behaviorOracleVerified"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_report_drift_and_test_inventory_drift() {
    let temp = root();
    let evidence =
        repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd");
    let original = evidence.join("purchase-data-ohostest-reference-observation.json");
    let observation = temp.join("observation.json");
    let mut value = read(&original);
    value["testNames"] = json!(["malformedDataDoesNotFinish"]);
    write(&observation, &value);
    let result = run(&temp.join("qualification.json"), &observation);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("inventory differs"));

    value = read(&original);
    value["testNames"]
        .as_array_mut()
        .unwrap()
        .push(json!("malformedDataDoesNotFinish"));
    write(&observation, &value);
    let result = run(&temp.join("qualification-duplicate.json"), &observation);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("inventory differs"));

    value = read(&original);
    value["sourceSetSha256"] = json!(digest(b"wrong source set"));
    write(&observation, &value);
    let result = run(&temp.join("qualification-2.json"), &observation);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("reference source set differs"));
    fs::remove_dir_all(temp).unwrap();
}
