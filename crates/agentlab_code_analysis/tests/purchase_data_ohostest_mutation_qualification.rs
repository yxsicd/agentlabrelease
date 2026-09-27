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
        "agentlab-ohostest-mutation-qualification-{}-{}-{}",
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

fn run(output: &Path, plan: &Path, calibration: &Path) -> std::process::Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-mutation-qualification"
    ))
    .args([
        "--mutation-plan",
        plan.to_str().unwrap(),
        "--mutation-calibration",
        calibration.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn qualifies_exact_observed_mutation_matrix_without_promoting_the_case() {
    let temp = root();
    let evidence = evidence();
    let output = temp.join("qualification.json");
    let result = run(
        &output,
        &evidence.join("purchase-data-ohostest-mutation-plan.json"),
        &evidence.join("purchase-data-ohostest-mutation-calibration.json"),
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let qualification = read(&output);
    assert_eq!(
        qualification["status"],
        "mutation-discrimination-qualified-source-review-still-required"
    );
    assert_eq!(qualification["variantCount"], 6);
    assert_eq!(qualification["testCount"], 7);
    assert_eq!(qualification["killedVariantCount"], 6);
    assert_eq!(qualification["mutationScore"], 1.0);
    assert_eq!(qualification["expectedMatrixVerified"], true);
    assert_eq!(qualification["allowsCaseContract"], false);
    assert_eq!(qualification["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_incomplete_execution_and_score_overstatement() {
    let temp = root();
    let evidence = evidence();
    let original_plan = evidence.join("purchase-data-ohostest-mutation-plan.json");
    let original_calibration = evidence.join("purchase-data-ohostest-mutation-calibration.json");
    let calibration = temp.join("calibration.json");

    let mut value = read(&original_calibration);
    value["results"][0]["emulatorExecutionAttempted"] = json!(false);
    write(&calibration, &value);
    let result = run(&temp.join("incomplete.json"), &original_plan, &calibration);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("mutation result unsafe-default-finish emulatorExecutionAttempted differs"));

    let mut value = read(&original_calibration);
    value["mutationScore"] = json!(0.99);
    write(&calibration, &value);
    let result = run(&temp.join("score.json"), &original_plan, &calibration);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("mutation calibration score differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_observed_kill_matrix_drift() {
    let temp = root();
    let evidence = evidence();
    let original_plan = evidence.join("purchase-data-ohostest-mutation-plan.json");
    let original_calibration = evidence.join("purchase-data-ohostest-mutation-calibration.json");
    let calibration = temp.join("calibration.json");
    let mut value = read(&original_calibration);
    value["results"][1]["observedKilledTests"] = json!([]);
    write(&calibration, &value);

    let result = run(&temp.join("matrix.json"), &original_plan, &calibration);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("mutation result drop-already-finished-guard kill matrix differs"));
    fs::remove_dir_all(temp).unwrap();
}
