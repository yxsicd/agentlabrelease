use agentlab_code_analysis::digest;
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

fn qualification_root() -> PathBuf {
    repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd")
}

fn evidence() -> PathBuf {
    qualification_root().join("purchase-data-ohostest-performance-detector")
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-ohostest-performance-detector-{}-{}-{}",
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

fn copy_tree(source: &Path, target: &Path) {
    fs::create_dir_all(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&source_path, &target_path);
        } else {
            fs::copy(source_path, target_path).unwrap();
        }
    }
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn run(calibration: &Path, output: &Path) -> std::process::Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-performance-detector-qualification"
    ))
    .args([
        "--profile-qualification",
        qualification_root()
            .join("purchase-data-ohostest-profile-qualification.json")
            .to_str()
            .unwrap(),
        "--calibration-evidence",
        calibration.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .current_dir(repository())
    .output()
    .unwrap()
}

#[test]
fn qualifies_functionally_passing_controlled_cpu_regression_twice() {
    let temp = temp_root();
    let output = temp.join("qualification.json");
    let result = run(&evidence(), &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(
        value["coverage"]["controlledWrongFunctionalAssertionCount"],
        84
    );
    assert_eq!(value["coverage"]["controlledWrongProfileSampleCount"], 96);
    assert_eq!(
        value["controlledMeaningfulWrongFunctionallyQualified"],
        true
    );
    assert_eq!(value["relativePerformanceDetectorCalibrated"], true);
    assert!(value["metrics"]["consistentRegressedMetrics"]
        .as_array()
        .unwrap()
        .iter()
        .any(|metric| metric == "appCpuUsagePercent"));
    assert_eq!(value["performanceCalibrated"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_controlled_source_drift() {
    let temp = temp_root();
    let calibration = temp.join("calibration");
    copy_tree(&evidence(), &calibration);
    let source = calibration.join("EntryPage.controlled-wrong.ets");
    let mut bytes = fs::read(&source).unwrap();
    bytes.extend_from_slice(b"\n");
    fs::write(source, bytes).unwrap();
    let result = run(&calibration, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("controlled wrong source digest differs")
    );
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_package_install_inside_profile_window_even_when_manifest_is_rebound() {
    let temp = temp_root();
    let calibration = temp.join("calibration");
    copy_tree(&evidence(), &calibration);
    let receipt_path = calibration.join("wrong-run-1/tests/1/receipt.json");
    let mut receipt = read(&receipt_path);
    receipt["packagesInstalled"] = json!(true);
    write(&receipt_path, &receipt);
    let manifest_path = calibration.join("wrong-run-1/run-manifest.json");
    let mut manifest = read(&manifest_path);
    manifest["functionalRepeats"][0]["receiptSha256"] =
        json!(digest(&fs::read(&receipt_path).unwrap()));
    write(&manifest_path, &manifest);
    let result = run(&calibration, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("packagesInstalled differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_forged_cpu_verdict_even_when_comparison_digest_is_rebound() {
    let temp = temp_root();
    let calibration = temp.join("calibration");
    copy_tree(&evidence(), &calibration);
    let comparison_path = calibration.join("wrong-comparison-2.json");
    let mut comparison = read(&comparison_path);
    comparison["decision"] = json!("within-relative-guardrails");
    comparison["metrics"][0]["status"] = json!("passed");
    write(&comparison_path, &comparison);
    let calibration_path = calibration.join("controlled-performance-calibration.json");
    let mut manifest = read(&calibration_path);
    manifest["comparisonSha256s"][1] = json!(digest(&fs::read(&comparison_path).unwrap()));
    write(&calibration_path, &manifest);
    let result = run(&calibration, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("comparison decision differs"));
    fs::remove_dir_all(temp).unwrap();
}
