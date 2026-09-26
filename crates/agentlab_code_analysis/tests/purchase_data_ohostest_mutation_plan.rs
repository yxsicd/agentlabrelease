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

fn evidence() -> PathBuf {
    repository().join("release/qualifications/alpha13-payment-feedback-analysis-165bcbd")
}

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "agentlab-ohostest-mutation-plan-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
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

fn run(output: &Path, packet: &Path, patch: &Path) -> std::process::Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-ohostest-mutation-plan"
    ))
    .args([
        "--review-packet",
        packet.to_str().unwrap(),
        "--candidate-patch",
        patch.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn builds_source_bound_fail_closed_mutation_plan() {
    let temp = root();
    let evidence = evidence();
    let output = temp.join("plan.json");
    let result = run(
        &output,
        &evidence.join("purchase-data-ohostest-review-packet.json"),
        &evidence.join("purchase-data-ohostest-candidate.patch"),
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let plan = read(&output);
    assert_eq!(
        plan["schema"],
        "agentlab.purchase_data_ohostest_mutation_plan.v1"
    );
    assert_eq!(plan["status"], "mutation-calibration-planned-not-executed");
    assert_eq!(plan["coverage"]["variantCount"], 6);
    assert_eq!(plan["coverage"]["testCount"], 7);
    assert_eq!(plan["coverage"]["everyTestTargeted"], true);
    assert_eq!(plan["execution"]["sourceVariantsBuilt"], false);
    assert_eq!(plan["execution"]["linuxX86EmulatorExecuted"], false);
    assert!(plan["execution"]["mutationScore"].is_null());
    assert_eq!(plan["allowsCaseContract"], false);
    assert_eq!(plan["automaticPromotion"], false);

    for variant in plan["variants"].as_array().unwrap() {
        assert_eq!(variant["role"], "meaningful-wrong");
        assert_eq!(variant["edit"]["expectedOccurrenceCount"], 1);
        assert!(!variant["expectedKilledTests"]
            .as_array()
            .unwrap()
            .is_empty());
    }
    for test in plan["testNames"].as_array().unwrap() {
        assert!(
            !plan["coverage"]["testToExpectedKillingVariants"][test.as_str().unwrap()]
                .as_array()
                .unwrap()
                .is_empty()
        );
    }
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_patch_drift_and_review_packet_overreach() {
    let temp = root();
    let evidence = evidence();
    let original_packet = evidence.join("purchase-data-ohostest-review-packet.json");
    let original_patch = evidence.join("purchase-data-ohostest-candidate.patch");

    let patch = temp.join("candidate.patch");
    let mut bytes = fs::read(&original_patch).unwrap();
    bytes.extend_from_slice(b"# drift\n");
    fs::write(&patch, bytes).unwrap();
    let result = run(&temp.join("patch-drift.json"), &original_packet, &patch);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("candidate patch digest differs"));

    let packet = temp.join("review-packet.json");
    let mut value = read(&original_packet);
    value["allowsCaseContract"] = json!(true);
    write(&packet, &value);
    let result = run(&temp.join("overreach.json"), &packet, &original_patch);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("review packet allowsCaseContract differs"));

    let mut value = read(&original_packet);
    value["testNames"].as_array_mut().unwrap().pop();
    write(&packet, &value);
    let result = run(&temp.join("inventory-drift.json"), &packet, &original_patch);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("OHOS Test inventory differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_source_anchor_drift_even_with_matching_patch_digest() {
    let temp = root();
    let evidence = evidence();
    let original_packet = evidence.join("purchase-data-ohostest-review-packet.json");
    let original_patch = evidence.join("purchase-data-ohostest-candidate.patch");

    let patch = temp.join("candidate.patch");
    let original = String::from_utf8(fs::read(&original_patch).unwrap()).unwrap();
    let changed = original.replacen(
        "shouldFinish: boolean = false;",
        "shouldFinish: boolean = falsE;",
        1,
    );
    assert_ne!(changed, original);
    fs::write(&patch, changed.as_bytes()).unwrap();

    let packet = temp.join("review-packet.json");
    let mut value = read(&original_packet);
    value["artifacts"]["patch"]["sha256"] = json!(digest(changed.as_bytes()));
    value["artifacts"]["patch"]["byteLength"] = json!(changed.len());
    write(&packet, &value);

    let result = run(&temp.join("anchor-drift.json"), &packet, &patch);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("mutation anchor occurrence differs: \"unsafe-default-finish\""));
    fs::remove_dir_all(temp).unwrap();
}
