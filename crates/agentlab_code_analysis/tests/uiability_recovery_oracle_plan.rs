use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);
const ENTRY: &str = "Ability/UIAbilityRecover/entry/src/main/ets/entryability/EntryAbility.ets";
const PAGE: &str = "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets";
const TEST: &str = "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets";

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "agentlab-uiability-oracle-plan-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&path).unwrap();
    path
}

fn write(path: &Path, bytes: &[u8]) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, bytes).unwrap();
}

fn git(root: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}

fn fixture(root: &Path) -> (PathBuf, PathBuf, PathBuf, PathBuf) {
    let source = root.join("source");
    fs::create_dir_all(&source).unwrap();
    git(&source, &["init"]);
    git(
        &source,
        &["config", "user.email", "agentlab@example.invalid"],
    );
    git(&source, &["config", "user.name", "AgentLab Test"]);
    write(
        &source.join(ENTRY),
        b"let recoveryMyData = want.parameters['myData'];\nwantParam['myData'] = 'my1234567';\n",
    );
    write(
        &source.join(PAGE),
        b"@State message: string = 'Hello World';\nthis.message = 'Welcome';\n",
    );
    write(
        &source.join(TEST),
        b"it('UIAbility_Recover_01', 0, async () => {});\n",
    );
    git(&source, &["add", "."]);
    git(&source, &["commit", "-m", "fixture"]);
    let revision = git(&source, &["rev-parse", "HEAD"]);

    let candidate_value = json!({
        "automaticPromotion": false,
        "contextPaths": [TEST],
        "editablePaths": [ENTRY, PAGE],
        "id": "shadow-case-uiability-backup-restore-state-recovery",
        "repositoryId": "guide-snippets",
        "schema": "agentlab.shadow_case_candidate.v1",
        "sourceRevision": revision,
        "status": "shadow-proposal"
    });
    let candidate = root.join("candidate.json");
    write(&candidate, &(serde_json::to_vec(&candidate_value).unwrap()));
    let candidate_sha = digest(&serde_json::to_vec(&candidate_value).unwrap());
    let plan_value = json!({
        "automaticPromotion": false,
        "candidateId": "shadow-case-uiability-backup-restore-state-recovery",
        "candidateSha256": candidate_sha,
        "requiredImplementationPaths": [{"path": ENTRY}, {"path": PAGE}],
        "requiredOraclePaths": [{"path": TEST}, {"path": PAGE}],
        "schema": "agentlab.shadow_case_construction_plan.v1"
    });
    let plan = root.join("plan.json");
    write(&plan, &serde_json::to_vec(&plan_value).unwrap());
    let patch = root.join("reference.patch");
    write(
        &patch,
        format!(
            "diff --git a/{ENTRY} b/{ENTRY}\n\
             diff --git a/{PAGE} b/{PAGE}\n\
             diff --git a/{TEST} b/{TEST}\n"
        )
        .as_bytes(),
    );
    (source, candidate, plan, patch)
}

fn run(
    root: &Path,
    source: &Path,
    candidate: &Path,
    plan: &Path,
    patch: &Path,
    name: &str,
) -> std::process::Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-uiability-recovery-oracle-plan"
    ))
    .args([
        "--candidate",
        candidate.to_str().unwrap(),
        "--construction-plan",
        plan.to_str().unwrap(),
        "--source",
        source.to_str().unwrap(),
        "--reference-patch",
        patch.to_str().unwrap(),
        "--output",
        root.join(name).to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

fn load(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

#[test]
fn plans_supervisor_owned_multiphase_oracle_and_wrong_variants() {
    let temp = root();
    let (source, candidate, plan, patch) = fixture(&temp);
    let result = run(&temp, &source, &candidate, &plan, &patch, "oracle.json");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = load(&temp.join("oracle.json"));
    assert_eq!(
        value["status"],
        "oracle-and-calibration-planned-trigger-probe-required"
    );
    assert_eq!(
        value["oracle"]["authority"],
        "supervisor-owned-multi-process-orchestration"
    );
    assert_eq!(value["oracle"]["phases"].as_array().unwrap().len(), 5);
    assert!(value["oracle"]["phases"][2]["selectedTrigger"].is_null());
    assert_eq!(value["wrongVariants"].as_array().unwrap().len(), 3);
    assert_eq!(
        value["referenceContract"]["patch"]["changedPaths"]
            .as_array()
            .unwrap()
            .len(),
        3
    );
    assert_eq!(value["qualification"]["requiredWrongVariants"], 2);
    assert_eq!(value["qualification"]["independentOracleExecuted"], false);
    assert_eq!(value["allowsCaseContract"], false);
    assert_eq!(value["automaticPromotion"], false);
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_source_drift_and_candidate_digest_drift() {
    let temp = root();
    let (source, candidate, plan, patch) = fixture(&temp);
    fs::write(source.join(PAGE), "dirty\n").unwrap();
    let result = run(&temp, &source, &candidate, &plan, &patch, "dirty.json");
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("source checkout is dirty"));
    git(&source, &["restore", "."]);

    let mut plan_value = load(&plan);
    plan_value["candidateSha256"] = json!("0".repeat(64));
    write(&plan, &serde_json::to_vec(&plan_value).unwrap());
    let result = run(&temp, &source, &candidate, &plan, &patch, "digest.json");
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("candidate digest differs"));
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn rejects_missing_or_duplicated_semantic_anchors() {
    let temp = root();
    let (source, candidate, plan, patch) = fixture(&temp);
    fs::write(
        source.join(ENTRY),
        "let recoveryMyData = want.parameters['myData'];\nlet recoveryMyData = want.parameters['myData'];\nwantParam['myData'] = 'my1234567';\n",
    )
    .unwrap();
    git(&source, &["add", "."]);
    git(&source, &["commit", "-m", "anchor drift"]);
    let mut candidate_value = load(&candidate);
    candidate_value["sourceRevision"] = json!(git(&source, &["rev-parse", "HEAD"]));
    write(&candidate, &serde_json::to_vec(&candidate_value).unwrap());
    let mut plan_value = load(&plan);
    plan_value["candidateSha256"] = json!(digest(&serde_json::to_vec(&candidate_value).unwrap()));
    write(&plan, &serde_json::to_vec(&plan_value).unwrap());
    let result = run(&temp, &source, &candidate, &plan, &patch, "anchor.json");
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("restore read anchor occurrence differs")
    );
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn public_schema_matches_generated_contract() {
    let schema = load(&repository().join("schemas/uiability-recovery-oracle-plan.schema.json"));
    assert_eq!(
        schema["properties"]["schema"]["const"],
        "agentlab.uiability_recovery_oracle_plan.v1"
    );
    assert_eq!(schema["properties"]["automaticPromotion"]["const"], false);
    assert_eq!(schema["properties"]["allowsCaseContract"]["const"], false);
}
