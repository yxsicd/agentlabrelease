use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}
fn evidence() -> PathBuf {
    repo().join("examples/maintainer-knowledge-gate/first-four")
}
fn temp() -> PathBuf {
    let p = std::env::temp_dir().join(format!(
        "agentlab-uiability-mutation-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&p).unwrap();
    p
}
fn read(p: &Path) -> Value {
    serde_json::from_slice(&fs::read(p).unwrap()).unwrap()
}
fn write(p: &Path, v: &Value) {
    let mut b = serde_json::to_vec_pretty(v).unwrap();
    b.push(b'\n');
    fs::write(p, b).unwrap();
}
fn run(root: &Path, calibration: &Path, name: &str) -> std::process::Output {
    let e = evidence();
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-uiability-recovery-mutation-qualification"
    ))
    .args([
        "--oracle-plan",
        e.join("qualification-plans/uiability-backup-restore-oracle.json")
            .to_str()
            .unwrap(),
        "--reference-runtime-receipt",
        e.join("qualification-receipts/uiability-backup-restore-reference-runtime.json")
            .to_str()
            .unwrap(),
        "--mutation-calibration",
        calibration.to_str().unwrap(),
        "--output",
        root.join(name).to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn qualifies_two_killed_variants_without_promoting_case() {
    let root = temp();
    let e = evidence();
    let r = run(
        &root,
        &e.join("qualification-receipts/uiability-backup-restore-mutation-calibration.json"),
        "out.json",
    );
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    let out = read(&root.join("out.json"));
    assert_eq!(
        out["status"],
        "mutation-discrimination-qualified-normal-exit-negative-control-required"
    );
    assert_eq!(out["variantCount"], 2);
    assert_eq!(out["killedVariantCount"], 2);
    assert_eq!(out["mutationScore"], 1.0);
    assert_eq!(out["referenceSandwichVerified"], true);
    assert_eq!(out["identityIsolationVerified"], true);
    assert_eq!(out["normalExitNegativeControl"], false);
    assert_eq!(out["allowsCaseContract"], false);
    assert_eq!(out["automaticPromotion"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_failed_reference_sandwich_and_reused_bundle_identity() {
    let root = temp();
    let original = evidence()
        .join("qualification-receipts/uiability-backup-restore-mutation-calibration.json");
    let mut v = read(&original);
    v["referenceControls"][1]["oraclePassed"] = json!(false);
    let changed = root.join("failed-ref.json");
    write(&changed, &v);
    let r = run(&root, &changed, "out-ref.json");
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("reference post oraclePassed differs"));
    let mut v = read(&original);
    v["variants"][0]["bundleName"] = v["referenceControls"][0]["bundleName"].clone();
    let changed = root.join("same-bundle.json");
    write(&changed, &v);
    let r = run(&root, &changed, "out-bundle.json");
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("bundle identities are not isolated"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_artifact_drift_and_variant_that_survives_oracle() {
    let root = temp();
    let original = evidence()
        .join("qualification-receipts/uiability-backup-restore-mutation-calibration.json");
    let mut v = read(&original);
    v["variants"][0]["sourceMutation"]["normalizedPatchSha256"] = json!("0".repeat(64));
    let changed = root.join("bad-hash.json");
    write(&changed, &v);
    let r = run(&root, &changed, "out-hash.json");
    assert!(!r.status.success());
    assert!(
        String::from_utf8_lossy(&r.stderr).contains("hardcoded normalized patch digest differs")
    );
    let mut v = read(&original);
    v["variants"][0]["after"] =
        json!({"visibleText":"Recovered Twice","launchReason":"APP_RECOVERY"});
    let changed = root.join("survived.json");
    write(&changed, &v);
    let r = run(&root, &changed, "out-survived.json");
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("was not killed"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn public_schemas_and_retained_qualification_are_bound() {
    let root = repo();
    let calibration_schema =
        read(&root.join("schemas/uiability-recovery-mutation-calibration.schema.json"));
    let qualification_schema =
        read(&root.join("schemas/uiability-recovery-mutation-qualification.schema.json"));
    assert_eq!(
        calibration_schema["properties"]["schema"]["const"],
        "agentlab.uiability_recovery_mutation_calibration.v1"
    );
    assert_eq!(
        calibration_schema["properties"]["automaticPromotion"]["const"],
        false
    );
    assert_eq!(
        qualification_schema["properties"]["schema"]["const"],
        "agentlab.uiability_recovery_mutation_qualification.v1"
    );
    assert_eq!(
        qualification_schema["properties"]["normalExitNegativeControl"]["const"],
        false
    );
    let retained = read(
        &evidence()
            .join("qualification-receipts/uiability-backup-restore-mutation-qualification.json"),
    );
    let calibration = fs::read(
        evidence()
            .join("qualification-receipts/uiability-backup-restore-mutation-calibration.json"),
    )
    .unwrap();
    assert_eq!(
        retained["mutationCalibrationSha256"],
        agentlab_code_analysis::digest(&calibration)
    );
    assert_eq!(retained["allowsCaseContract"], false);
    assert_eq!(retained["automaticPromotion"], false);
}
