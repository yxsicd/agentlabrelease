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

fn evidence() -> PathBuf {
    repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd")
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-ohostest-profile-{}-{}-{}",
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

fn run(profile: &Path, output: &Path) -> std::process::Output {
    let evidence = evidence();
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-profile-qualification"
    ))
    .args([
        "--runtime-oracle-bridge",
        evidence
            .join("purchase-data-runtime-oracle-bridge.json")
            .to_str()
            .unwrap(),
        "--candidate-execution-receipt",
        evidence
            .join("purchase-data-ohostest-candidate-execution-receipt.json")
            .to_str()
            .unwrap(),
        "--candidate-native-report",
        evidence
            .join("purchase-data-ohostest-candidate-native-report.json")
            .to_str()
            .unwrap(),
        "--profile-evidence",
        profile.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .current_dir(repository())
    .output()
    .unwrap()
}

#[test]
fn qualifies_exact_rust_bound_emulator_repeatability_evidence() {
    let temp = temp_root();
    let output = temp.join("qualification.json");
    let result = run(&evidence().join("purchase-data-ohostest-profile"), &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(value["coverage"]["profileRunCount"], 2);
    assert_eq!(value["coverage"]["profileSampleCount"], 96);
    assert_eq!(value["coverage"]["functionalAssertionCount"], 84);
    assert_eq!(
        value["emulatorRelativePerformanceRepeatabilityQualified"],
        true
    );
    assert_eq!(value["performanceCalibrated"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_file(output).unwrap();
    fs::remove_dir(temp).unwrap();
}

#[test]
fn rejects_reinstall_inside_profile_window_even_when_digest_is_rebound() {
    let temp = temp_root();
    let profile = temp.join("profile");
    copy_tree(&evidence().join("purchase-data-ohostest-profile"), &profile);
    let receipt_path = profile.join("run-1/tests/1/receipt.json");
    let mut receipt = read(&receipt_path);
    receipt["packagesInstalled"] = json!(true);
    write(&receipt_path, &receipt);
    let mut manifest = read(&profile.join("run-1/run-manifest.json"));
    manifest["functionalRepeats"][0]["receiptSha256"] =
        json!(digest(&fs::read(&receipt_path).unwrap()));
    write(&profile.join("run-1/run-manifest.json"), &manifest);
    let result = run(&profile, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("packagesInstalled differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_functional_repeat_outside_profile_window() {
    let temp = temp_root();
    let profile = temp.join("profile");
    copy_tree(&evidence().join("purchase-data-ohostest-profile"), &profile);
    let receipt_path = profile.join("run-2/tests/6/receipt.json");
    let mut receipt = read(&receipt_path);
    receipt["finishedAt"] = json!("9999-01-01T00:00:00+00:00");
    write(&receipt_path, &receipt);
    let mut manifest = read(&profile.join("run-2/run-manifest.json"));
    manifest["functionalRepeats"][5]["receiptSha256"] =
        json!(digest(&fs::read(&receipt_path).unwrap()));
    write(&profile.join("run-2/run-manifest.json"), &manifest);
    let result = run(&profile, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("escaped profile window"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_regressed_comparison_verdict() {
    let temp = temp_root();
    let profile = temp.join("profile");
    copy_tree(&evidence().join("purchase-data-ohostest-profile"), &profile);
    let comparison_path = profile.join("smartperf-comparison.json");
    let mut comparison = read(&comparison_path);
    comparison["decision"] = json!("performance-regression-candidate");
    comparison["metrics"][0]["status"] = json!("regressed");
    write(&comparison_path, &comparison);
    let result = run(&profile, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("comparison decision differs"));
    fs::remove_dir_all(temp).unwrap();
}
