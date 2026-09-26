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

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "agentlab-runtime-oracle-bridge-{}-{}-{}",
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

fn run(
    output: &Path,
    seam: &Path,
    observation: &Path,
    candidate_qualification: &Path,
    mutation_plan: &Path,
    mutation_qualification: &Path,
) -> std::process::Output {
    let repository = repository();
    let evidence = evidence();
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-runtime-oracle-bridge"
    ))
    .args([
        "--behavior-plan",
        evidence
            .join("purchase-data-behavior-oracle-plan.json")
            .to_str()
            .unwrap(),
        "--behavior-calibration",
        evidence
            .join("purchase-data-behavior-oracle-calibration.json")
            .to_str()
            .unwrap(),
        "--behavior-seam",
        seam.to_str().unwrap(),
        "--candidate-observation",
        observation.to_str().unwrap(),
        "--candidate-qualification",
        candidate_qualification.to_str().unwrap(),
        "--mutation-plan",
        mutation_plan.to_str().unwrap(),
        "--mutation-calibration",
        evidence
            .join("purchase-data-ohostest-mutation-calibration.json")
            .to_str()
            .unwrap(),
        "--mutation-qualification",
        mutation_qualification.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .current_dir(repository)
    .output()
    .unwrap()
}

fn retained_inputs() -> (PathBuf, PathBuf, PathBuf, PathBuf, PathBuf) {
    let repository = repository();
    let evidence = evidence();
    (
        repository.join("scripts/purchase-data-behavior-seam.js"),
        evidence.join("purchase-data-ohostest-candidate-observation.json"),
        evidence.join("purchase-data-ohostest-candidate-qualification.json"),
        evidence.join("purchase-data-ohostest-mutation-plan.json"),
        evidence.join("purchase-data-ohostest-mutation-qualification.json"),
    )
}

#[test]
fn qualifies_exact_harmony_source_to_runtime_oracle_bridge() {
    let temp = root();
    let (seam, observation, candidate, mutation_plan, mutation_qualification) = retained_inputs();
    let output = temp.join("bridge.json");
    let result = run(
        &output,
        &seam,
        &observation,
        &candidate,
        &mutation_plan,
        &mutation_qualification,
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let bridge = read(&output);
    assert_eq!(
        bridge["status"],
        "harmony-runtime-oracle-bridge-qualified-independent-review-required"
    );
    assert_eq!(bridge["coverage"]["crossRepositoryBehaviorCheckCount"], 10);
    assert_eq!(bridge["coverage"]["harmonyRuntimeBoundCheckCount"], 5);
    assert_eq!(bridge["coverage"]["cordovaRuntimeBoundCheckCount"], 0);
    assert_eq!(bridge["coverage"]["ohosTestCount"], 7);
    assert_eq!(bridge["coverage"]["runtimeMutationScore"], 1.0);
    assert_eq!(
        bridge["harmonyRuntimeMappings"].as_array().unwrap().len(),
        5
    );
    assert_eq!(bridge["behaviorOracleVerified"], false);
    assert_eq!(bridge["allowsCaseContract"], false);
    assert_eq!(bridge["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_behavior_seam_and_base_revision_drift() {
    let temp = root();
    let (seam, observation, candidate, mutation_plan, mutation_qualification) = retained_inputs();
    let changed_seam = temp.join("seam.js");
    let mut seam_bytes = fs::read(&seam).unwrap();
    seam_bytes.extend_from_slice(b"\n// drift\n");
    fs::write(&changed_seam, seam_bytes).unwrap();
    let result = run(
        &temp.join("seam-drift.json"),
        &changed_seam,
        &observation,
        &candidate,
        &mutation_plan,
        &mutation_qualification,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("behavior seam digest differs"));

    let changed_observation = temp.join("observation.json");
    let mut observation_value = read(&observation);
    observation_value["baseRevision"] = json!("0000000000000000000000000000000000000000");
    write(&changed_observation, &observation_value);
    let changed_candidate = temp.join("candidate.json");
    let mut candidate_value = read(&candidate);
    candidate_value["lineage"]["observationSha256"] =
        json!(digest(&fs::read(&changed_observation).unwrap()));
    write(&changed_candidate, &candidate_value);
    let result = run(
        &temp.join("base-drift.json"),
        &seam,
        &changed_observation,
        &changed_candidate,
        &mutation_plan,
        &mutation_qualification,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("Harmony base revision differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_incomplete_runtime_test_mapping_even_when_digest_is_rebound() {
    let temp = root();
    let (seam, observation, candidate, retained_plan, retained_qualification) = retained_inputs();
    let mutation_plan = temp.join("mutation-plan.json");
    let mut plan_value = read(&retained_plan);
    plan_value["testNames"]
        .as_array_mut()
        .unwrap()
        .retain(|value| value != "decodeFailureDoesNotFinish");
    write(&mutation_plan, &plan_value);

    let mutation_qualification = temp.join("mutation-qualification.json");
    let mut qualification_value = read(&retained_qualification);
    qualification_value["mutationPlanSha256"] = json!(digest(&fs::read(&mutation_plan).unwrap()));
    write(&mutation_qualification, &qualification_value);
    let result = run(
        &temp.join("mapping-drift.json"),
        &seam,
        &observation,
        &candidate,
        &mutation_plan,
        &mutation_qualification,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("runtime test inventory differs for harmony-invalid-data-is-not-finished"));
    fs::remove_dir_all(temp).unwrap();
}
