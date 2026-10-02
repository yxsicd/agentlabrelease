use agentlab_code_analysis::{
    digest,
    maintainer_flywheel_business::{prepare, run},
    maintainer_flywheel_cycles,
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .canonicalize()
        .unwrap()
}
fn temp() -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let path = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "business-gates-{}-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&path).unwrap();
    path
}
fn selected(directory: &Path) -> (PathBuf, PathBuf) {
    let knowledge = root().join("examples/maintainer-knowledge-gate/first-four");
    let original = root().join("examples/maintainer-knowledge-gate/reviewed-guidance/environment-lifecycle-evaluation-selection.json");
    let mut request: Value = serde_json::from_slice(&fs::read(original).unwrap()).unwrap();
    let cut_bytes = fs::read(knowledge.join("maintainer-knowledge-cut.json")).unwrap();
    let cut: Value = serde_json::from_slice(&cut_bytes).unwrap();
    // This is a newly selected test request, never a rewrite of historical
    // guidance consumption or a claim that its earlier Agent run used this cut.
    request["knowledgeCutSha256"] = json!(digest(&cut_bytes));
    request["knowledgeRevision"] = cut["tableGitAuthority"]["revision"].clone();
    let selection = directory.join("current-selection.json");
    fs::write(&selection, serde_json::to_vec_pretty(&request).unwrap()).unwrap();
    (knowledge, selection)
}
#[test]
fn published_cut_runs_real_business_gates_and_preserves_missing_operation_boundary() {
    let directory = temp();
    let (knowledge, selection) = selected(&directory);
    let cli = env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel");
    let result = Command::new(cli)
        .arg("--prepare-business-cycles")
        .arg("--knowledge")
        .arg(&knowledge)
        .arg("--guidance-request")
        .arg(&selection)
        .arg("--reviewed")
        .arg("--output")
        .arg(directory.join("prepared"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let prepared: Value = serde_json::from_slice(&result.stdout).unwrap();
    let bytes = fs::read(prepared["recipePath"].as_str().unwrap()).unwrap();
    let captured = maintainer_flywheel_cycles::execute(&bytes, &directory.join("capture")).unwrap();
    assert_eq!(captured["status"], "review-required");
    assert_eq!(captured["completedRounds"], 0);
    let stages = captured["stages"].as_array().unwrap();
    assert_eq!(stages.len(), 3);
    assert_eq!(stages[0]["result"]["status"], "completed");
    assert_eq!(stages[1]["result"]["status"], "completed");
    let report: Value = serde_json::from_slice(
        &fs::read(directory.join("capture/round-0-program-analysis/business/report.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(report["strictReproductionVerified"], true);
    assert_eq!(report["freshProgramGraphGenerated"], false);
    let gap: Value = serde_json::from_slice(
        &fs::read(directory.join("capture/round-0-maintenance-verification/business/report.json"))
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        gap["gap"],
        "revision-bound-maintenance-operation-capture-required"
    );
    assert!(!directory.join("capture/round-0-case-execution").exists());
    assert_eq!(captured["qualified"], false);
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn explicit_review_and_exact_cut_are_required_without_borrowing_source_applicability() {
    let directory = temp();
    let (knowledge, selection) = selected(&directory);
    let program = Path::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"));
    let historical = root().join("examples/maintainer-knowledge-gate/reviewed-guidance/environment-lifecycle-evaluation-selection.json");
    assert!(prepare(
        &knowledge,
        &historical,
        program,
        true,
        &directory.join("stale-selection")
    )
    .is_err());
    assert!(!directory.join("stale-selection").exists());
    assert!(prepare(
        &knowledge,
        &selection,
        program,
        false,
        &directory.join("unreviewed")
    )
    .is_err());
    assert!(!directory.join("unreviewed").exists());
    let prepared = prepare(
        &knowledge,
        &selection,
        program,
        true,
        &directory.join("prepared"),
    )
    .unwrap();
    let recipe: Value =
        serde_json::from_slice(&fs::read(prepared["recipePath"].as_str().unwrap()).unwrap())
            .unwrap();
    let mut state: Value = serde_json::from_slice(
        &fs::read(recipe["initialState"]["path"].as_str().unwrap()).unwrap(),
    )
    .unwrap();
    for (name, field) in [("cut", "knowledge"), ("source", "sourceRevision")] {
        let mut modified = state.clone();
        if field == "knowledge" {
            modified["knowledge"]["cutSha256"] = json!("0".repeat(64));
        } else {
            modified["sourceRevision"] = json!("0".repeat(40));
        }
        let path = directory.join(format!("{name}.json"));
        let bytes = serde_json::to_vec(&modified).unwrap();
        fs::write(&path, &bytes).unwrap();
        let request = json!({"schema":"agentlab.flywheel_stage_request.v1","round":0,"stage":"repository-understanding",
            "automaticPromotion":false,"inputState":{"path":path,"sha256":digest(&bytes)}});
        let out = directory.join(name);
        fs::create_dir(&out).unwrap();
        assert_eq!(
            run(&serde_json::to_vec(&request).unwrap(), &out).unwrap()["status"],
            "rejected"
        );
    }
    state["automaticPromotion"] = json!(true);
    let bytes = serde_json::to_vec(&state).unwrap();
    let path = directory.join("promotion.json");
    fs::write(&path, &bytes).unwrap();
    let request = json!({"schema":"agentlab.flywheel_stage_request.v1","round":0,"stage":"repository-understanding",
        "automaticPromotion":false,"inputState":{"path":path,"sha256":digest(&bytes)}});
    assert!(run(&serde_json::to_vec(&request).unwrap(), &directory).is_err());
    fs::remove_dir_all(directory).unwrap();
}
