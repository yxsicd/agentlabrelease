use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);
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
    qualification_root().join("purchase-data-case-performance-matrix-v2")
}
fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-case-performance-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}
fn copy_tree(source: &Path, target: &Path) {
    fs::create_dir_all(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let from = entry.path();
        let to = target.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&from, &to)
        } else {
            fs::copy(from, to).unwrap();
        }
    }
}
fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}
fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap()
}
fn run(evidence: &Path, output: &Path) -> std::process::Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-case-performance-qualification"
    ))
    .args([
        "--plan",
        qualification_root()
            .join("purchase-data-case-performance-plan.json")
            .to_str()
            .unwrap(),
        "--evidence",
        evidence.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .current_dir(repository())
    .output()
    .unwrap()
}

#[test]
fn qualifies_six_case_bound_cold_runs_without_promoting_case() {
    let temp = temp_root();
    let output = temp.join("qualification.json");
    let result = run(&evidence(), &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(value["coverage"]["functionalVerdictCount"], 288);
    assert_eq!(value["coverage"]["profileSampleCount"], 288);
    assert_eq!(
        value["distinctBaselineReferenceWrongCaseCalibrationComplete"],
        true
    );
    assert_eq!(value["performanceCalibrated"], true);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_forged_second_wrong_cpu_verdict() {
    let temp = temp_root();
    let copied = temp.join("evidence");
    copy_tree(&evidence(), &copied);
    let path = copied.join("meaningful-wrong-comparison-2.json");
    let mut value = read(&path);
    value["decision"] = json!("within-relative-guardrails");
    value["metrics"][0]["status"] = json!("passed");
    write(&path, &value);
    let result = run(&copied, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("comparison decision differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_symlinked_run_manifest() {
    use std::os::unix::fs::symlink;
    let temp = temp_root();
    let copied = temp.join("evidence");
    copy_tree(&evidence(), &copied);
    let path = copied.join("reference/run-1/run-manifest.json");
    let target = temp.join("manifest.json");
    fs::rename(&path, &target).unwrap();
    symlink(&target, &path).unwrap();
    let result = run(&copied, &temp.join("qualification.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("run manifest must be a regular file"));
    fs::remove_dir_all(temp).unwrap();
}
