use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
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

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-unseen-agent-cohort-{}-{}-{}",
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

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn run(
    packet: &Path,
    root: &Path,
    case_review: &Path,
    campaign: &Path,
    dispatch_source: &Path,
    dispatch_schema: &Path,
    publication_source: &Path,
    publication_schema: &Path,
    publication_workflow: &Path,
    reexecution_source: &Path,
    reexecution_schema: &Path,
    runtime_bundle_schema: &Path,
    reexecution_workflow: &Path,
    case_freeze_source: &Path,
    case_freeze_schema: &Path,
    case_freeze_workflow: &Path,
    output: &Path,
) -> Output {
    let packet_sha256 = format!("{:x}", Sha256::digest(fs::read(packet).unwrap()));
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-unseen-agent-cohort-contract"
    ))
    .args([
        "--packet",
        packet.to_str().unwrap(),
        "--expected-packet-sha256",
        &packet_sha256,
        "--qualification-root",
        root.to_str().unwrap(),
        "--case-review-workflow",
        case_review.to_str().unwrap(),
        "--assessed-campaign-workflow",
        campaign.to_str().unwrap(),
        "--participant-dispatch-source",
        dispatch_source.to_str().unwrap(),
        "--participant-dispatch-schema",
        dispatch_schema.to_str().unwrap(),
        "--exact-patch-publication-source",
        publication_source.to_str().unwrap(),
        "--exact-patch-publication-schema",
        publication_schema.to_str().unwrap(),
        "--exact-patch-publication-workflow",
        publication_workflow.to_str().unwrap(),
        "--published-revision-reexecution-source",
        reexecution_source.to_str().unwrap(),
        "--published-revision-reexecution-schema",
        reexecution_schema.to_str().unwrap(),
        "--published-revision-runtime-bundle-schema",
        runtime_bundle_schema.to_str().unwrap(),
        "--published-revision-reexecution-workflow",
        reexecution_workflow.to_str().unwrap(),
        "--trusted-case-freeze-source",
        case_freeze_source.to_str().unwrap(),
        "--trusted-case-freeze-schema",
        case_freeze_schema.to_str().unwrap(),
        "--trusted-case-freeze-workflow",
        case_freeze_workflow.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ])
    .current_dir(repository())
    .output()
    .unwrap()
}

fn normal_run(packet: &Path, root: &Path, output: &Path) -> Output {
    let repository = repository();
    run(
        packet,
        root,
        &repository.join(".github/workflows/multi-repo-case-review.yml"),
        &repository.join(".github/workflows/multi-repo-assessed-campaign.yml"),
        &repository.join("crates/agentlab_code_analysis/src/participant_experiment_dispatch.rs"),
        &repository.join("schemas/participant-experiment-dispatch.schema.json"),
        &repository
            .join("crates/agentlab_code_analysis/src/purchase_data_exact_patch_publication.rs"),
        &repository.join("schemas/purchase-data-exact-patch-publication.schema.json"),
        &repository.join(".github/workflows/purchase-data-exact-patch-publication.yml"),
        &repository.join(
            "crates/agentlab_code_analysis/src/purchase_data_published_revision_reexecution.rs",
        ),
        &repository.join("schemas/purchase-data-published-revision-reexecution.schema.json"),
        &repository.join("schemas/purchase-data-published-revision-runtime-bundle.schema.json"),
        &repository.join(".github/workflows/purchase-data-published-revision-reexecution.yml"),
        &repository.join("crates/agentlab_code_analysis/src/purchase_data_trusted_case_freeze.rs"),
        &repository.join("schemas/purchase-data-trusted-case-freeze.schema.json"),
        &repository.join(".github/workflows/purchase-data-trusted-case-freeze.yml"),
        output,
    )
}

#[test]
fn freezes_blocked_unseen_agent_execution_contract_without_promoting_case() {
    let temp = temp_root();
    let output = temp.join("contract.json");
    let root = qualification_root();
    let result = normal_run(
        &root.join("purchase-data-integrated-review-packet-v2.json"),
        &root,
        &output,
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(
        value["status"],
        "execution-contract-frozen-prerequisites-pending"
    );
    assert_eq!(value["requiredSequence"].as_array().unwrap().len(), 6);
    assert_eq!(value["participantCohort"]["minimumProfiles"], 3);
    assert_eq!(value["participantCohort"]["maximumProfiles"], 8);
    assert_eq!(
        value["participantCohort"]["allowedTrialsPerProfile"],
        json!([3, 5, 10, 20])
    );
    assert_eq!(
        value["participantCohort"]["portableDispatchSchema"],
        "agentlab.participant_experiment_dispatch.v1"
    );
    assert_eq!(
        value["implementationBindings"]["participantExperimentDispatch"]["path"],
        "crates/agentlab_code_analysis/src/participant_experiment_dispatch.rs"
    );
    assert_eq!(
        value["implementationBindings"]["exactPatchPublicationWorkflow"]["path"],
        ".github/workflows/purchase-data-exact-patch-publication.yml"
    );
    assert_eq!(
        value["implementationBindings"]["publishedRevisionReexecutionWorkflow"]["path"],
        ".github/workflows/purchase-data-published-revision-reexecution.yml"
    );
    assert_eq!(
        value["implementationBindings"]["trustedCaseFreezeWorkflow"]["path"],
        ".github/workflows/purchase-data-trusted-case-freeze.yml"
    );
    assert!(value["implementationBindings"]
        .get("participantExperimentPlan")
        .is_none());
    assert_eq!(
        value["performanceQualification"]["controlledVariantsAreAgentRuns"],
        false
    );
    assert_eq!(value["currentReadiness"]["readyToDispatch"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    assert_eq!(
        fs::read(&output).unwrap(),
        fs::read(root.join("purchase-data-unseen-agent-cohort-contract.json")).unwrap()
    );
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_packet_that_forges_performance_readiness() {
    let temp = temp_root();
    let source = qualification_root();
    let packet = temp.join("purchase-data-integrated-review-packet-v2.json");
    let performance = temp.join("purchase-data-case-performance-qualification.json");
    fs::copy(
        source.join("purchase-data-case-performance-qualification.json"),
        &performance,
    )
    .unwrap();
    let mut value = read(&source.join("purchase-data-integrated-review-packet-v2.json"));
    value["performanceCalibrated"] = json!(false);
    write(&packet, &value);
    let result = normal_run(&packet, &temp, &temp.join("contract.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("integrated packet performanceCalibrated differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_assessed_campaign_without_discrimination_scoring() {
    let temp = temp_root();
    let repository = repository();
    let campaign = temp.join("multi-repo-assessed-campaign.yml");
    let source =
        fs::read_to_string(repository.join(".github/workflows/multi-repo-assessed-campaign.yml"))
            .unwrap();
    fs::write(
        &campaign,
        source.replace("score-case-discrimination.py", "score.py"),
    )
    .unwrap();
    let root = qualification_root();
    let result = run(
        &root.join("purchase-data-integrated-review-packet-v2.json"),
        &root,
        &repository.join(".github/workflows/multi-repo-case-review.yml"),
        &campaign,
        &repository.join("crates/agentlab_code_analysis/src/participant_experiment_dispatch.rs"),
        &repository.join("schemas/participant-experiment-dispatch.schema.json"),
        &repository
            .join("crates/agentlab_code_analysis/src/purchase_data_exact_patch_publication.rs"),
        &repository.join("schemas/purchase-data-exact-patch-publication.schema.json"),
        &repository.join(".github/workflows/purchase-data-exact-patch-publication.yml"),
        &repository.join(
            "crates/agentlab_code_analysis/src/purchase_data_published_revision_reexecution.rs",
        ),
        &repository.join("schemas/purchase-data-published-revision-reexecution.schema.json"),
        &repository.join("schemas/purchase-data-published-revision-runtime-bundle.schema.json"),
        &repository.join(".github/workflows/purchase-data-published-revision-reexecution.yml"),
        &repository.join("crates/agentlab_code_analysis/src/purchase_data_trusted_case_freeze.rs"),
        &repository.join("schemas/purchase-data-trusted-case-freeze.schema.json"),
        &repository.join(".github/workflows/purchase-data-trusted-case-freeze.yml"),
        &temp.join("contract.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("assessed-campaign workflow contract fragment is absent"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_dispatch_schema_that_grants_automatic_promotion() {
    let temp = temp_root();
    let repository = repository();
    let schema = temp.join("participant-experiment-dispatch.schema.json");
    let source =
        fs::read_to_string(repository.join("schemas/participant-experiment-dispatch.schema.json"))
            .unwrap();
    fs::write(
        &schema,
        source.replace(
            "\"automaticPromotion\": {\"const\": false}",
            "\"automaticPromotion\": {\"const\": true}",
        ),
    )
    .unwrap();
    let root = qualification_root();
    let result = run(
        &root.join("purchase-data-integrated-review-packet-v2.json"),
        &root,
        &repository.join(".github/workflows/multi-repo-case-review.yml"),
        &repository.join(".github/workflows/multi-repo-assessed-campaign.yml"),
        &repository.join("crates/agentlab_code_analysis/src/participant_experiment_dispatch.rs"),
        &schema,
        &repository
            .join("crates/agentlab_code_analysis/src/purchase_data_exact_patch_publication.rs"),
        &repository.join("schemas/purchase-data-exact-patch-publication.schema.json"),
        &repository.join(".github/workflows/purchase-data-exact-patch-publication.yml"),
        &repository.join(
            "crates/agentlab_code_analysis/src/purchase_data_published_revision_reexecution.rs",
        ),
        &repository.join("schemas/purchase-data-published-revision-reexecution.schema.json"),
        &repository.join("schemas/purchase-data-published-revision-runtime-bundle.schema.json"),
        &repository.join(".github/workflows/purchase-data-published-revision-reexecution.yml"),
        &repository.join("crates/agentlab_code_analysis/src/purchase_data_trusted_case_freeze.rs"),
        &repository.join("schemas/purchase-data-trusted-case-freeze.schema.json"),
        &repository.join(".github/workflows/purchase-data-trusted-case-freeze.yml"),
        &temp.join("contract.json"),
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("participant dispatch schema contract fragment is absent"));
    fs::remove_dir_all(temp).unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_symlinked_integrated_packet() {
    use std::os::unix::fs::symlink;

    let temp = temp_root();
    let root = qualification_root();
    let packet = temp.join("packet.json");
    symlink(
        root.join("purchase-data-integrated-review-packet-v2.json"),
        &packet,
    )
    .unwrap();
    let result = normal_run(&packet, &root, &temp.join("contract.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("integrated packet must be a regular file"));
    fs::remove_dir_all(temp).unwrap();
}
