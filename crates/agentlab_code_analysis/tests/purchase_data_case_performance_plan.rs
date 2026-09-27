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
    "purchase-data-integrated-review-packet.json",
    "purchase-data-ohostest-mutation-plan.json",
    "purchase-data-ohostest-mutation-qualification.json",
    "purchase-data-ohostest-profile-qualification.json",
    "purchase-data-ohostest-performance-detector-qualification.json",
    "purchase-data-case-performance-policy.json",
    "purchase-data-case-performance-workload.tsv",
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
        "agentlab-purchase-data-case-performance-{}-{}-{}",
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
        fs::copy(evidence().join(relative), root.join(relative)).unwrap();
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
        "CARGO_BIN_EXE_agentlab-purchase-data-case-performance-plan"
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
fn plans_exact_case_bound_three_role_matrix_without_claiming_execution() {
    let root = fixture();
    let output = root.join("plan.json");
    let result = run(&root, &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let plan = read(&output);
    assert_eq!(
        plan["schema"],
        "agentlab.purchase_data_case_performance_calibration_plan.v1"
    );
    assert_eq!(
        plan["status"],
        "case-bound-performance-calibration-planned-not-executed"
    );
    assert_eq!(plan["evidenceAttachments"].as_object().unwrap().len(), 7);
    assert_eq!(
        plan["casePerformanceRequirement"]["caseBoundFunction"],
        "planPurchaseFinalization"
    );
    assert_eq!(
        plan["evaluatorWorkloadEdit"]["testName"],
        "purchaseFinalizationPerformanceWorkload"
    );
    assert_eq!(plan["evaluatorWorkloadEdit"]["iterationCount"], 5000);
    assert_eq!(plan["calibrationRoles"].as_array().unwrap().len(), 3);
    assert_eq!(plan["executionMatrix"]["totalColdRunCount"], 6);
    assert_eq!(
        plan["executionMatrix"]["expectedFunctionalVerdictCountPerRole"],
        96
    );
    for value in plan["execution"].as_object().unwrap().values() {
        assert_eq!(value, false);
    }
    assert_eq!(
        plan["distinctBaselineReferenceWrongCaseCalibrationComplete"],
        false
    );
    assert_eq!(plan["performanceCalibrated"], false);
    assert_eq!(plan["allowsCaseContract"], false);
    assert_eq!(plan["automaticPromotion"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_forged_full_performance_calibration() {
    let root = fixture();
    let path = root.join("purchase-data-ohostest-performance-detector-qualification.json");
    let mut value = read(&path);
    value["performanceCalibrated"] = json!(true);
    write(&path, &value);
    let result = run(&root, &root.join("plan.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("detector qualification performanceCalibrated differs"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_workload_iteration_or_test_count_drift() {
    let root = fixture();
    let path = root.join("purchase-data-case-performance-workload.tsv");
    let text = fs::read_to_string(&path).unwrap();
    fs::write(&path, text.replace("\t5000\n", "\t4999\n")).unwrap();
    let result = run(&root, &root.join("plan.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("case workload contract differs"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_mutation_plan_drift_without_qualification_rebind() {
    let root = fixture();
    let path = root.join("purchase-data-ohostest-mutation-plan.json");
    let mut value = read(&path);
    value["variants"][0]["expectedFailure"] = json!("drifted expectation");
    write(&path, &value);
    let result = run(&root, &root.join("plan.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("mutation qualification plan digest differs"));
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_symlinked_evidence_input() {
    use std::os::unix::fs::symlink;

    let root = fixture();
    let path = root.join("purchase-data-case-performance-policy.json");
    let target = root.join("policy-target.json");
    fs::rename(&path, &target).unwrap();
    symlink(&target, &path).unwrap();
    let result = run(&root, &root.join("plan.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("case-performance-policy must be a regular file"));
    fs::remove_dir_all(root).unwrap();
}
