use agentlab_code_analysis::{
    digest,
    maintainer_source_diagnostic::{feedback, prepare},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
fn file(path: &Path, value: &Value) {
    fs::write(path, serde_json::to_vec(value).unwrap()).unwrap();
}
fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}
fn fixture() -> PathBuf {
    let base = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "agentlab-source-diagnostic-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    ));
    fs::create_dir(&base).unwrap();
    let stage = base.join("stage");
    fs::create_dir(&stage).unwrap();
    fs::write(base.join("compiler.js"), "module.exports={};").unwrap();
    let source = "module.exports={};\n";
    let source_file = json!({"path":"unit.js","content":source,"byteCount":source.len(),"sha256":digest(source.as_bytes()),"gitBlobOid":"a".repeat(40)});
    let checks = json!([{"id":"answer","pointer":"/scenario/value","expected":7},{"id":"nullable","pointer":"/scenario/nullable","expected":null}]);
    let controls =
        json!([{"id":"baseline","role":"baseline","edits":[],"expectedFailedCheckIds":[]}]);
    let scenarios = json!([{"id":"scenario","initialState":{},"inputs":{},"expectedObservations":{"value":7,"nullable":null}}]);
    let request = json!({"schema":"agentlab.source_recipe_author_request.v1","reviewed":false,"automaticPromotion":false,"scope":{"id":"scope"},"source":{"revision":"1".repeat(40)},"sourceFiles":[source_file],"policy":{"methodDependencies":[{"path":"/missing/original/compiler.js","sha256":digest(b"module.exports={};")}]}});
    let verifier = "process.stdout.write(JSON.stringify({scenario:{value:7,nullable:null}}));";
    let proposal = json!({"schema":"agentlab.source_recipe_author_proposal.v1","scopeSkillId":"scope","verifierSource":verifier,"sourcePaths":["unit.js"],"contract":{"checks":checks}});
    let design = json!({"schema":"agentlab.source_recipe_design.v2","scopeSkillId":"scope","checks":checks,"controls":controls,"scenarios":scenarios});
    file(&stage.join("request.json"), &request);
    file(&stage.join("proposal.json"), &proposal);
    file(&stage.join("design.json"), &design);
    fs::write(stage.join("controls.cjs"), verifier).unwrap();
    fs::write(
        stage.join("design-runtime.cjs"),
        format!(
            "const manifest = {};\nmodule.exports=()=>({{}});",
            json!({"files":[source_file],"controls":controls,"scenarios":scenarios})
        ),
    )
    .unwrap();
    let mut receipt = json!({"schema":"agentlab.source_recipe_author_stage.v1","reviewed":false,"automaticPromotion":false,"executionPerformed":false});
    for (name, key) in [
        ("request.json", "requestSha256"),
        ("proposal.json", "proposalSha256"),
        ("design.json", "designSha256"),
        ("design-runtime.cjs", "designRuntimeSha256"),
    ] {
        receipt[key] = json!(digest(&fs::read(stage.join(name)).unwrap()));
    }
    file(&stage.join("stage-receipt.json"), &receipt);
    base
}
fn prepared(base: &Path) -> Value {
    prepare(
        &base.join("stage"),
        &base.join("compiler.js"),
        &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
        &format!("sha256:{}", "a".repeat(64)),
        &base.join("inputs"),
    )
    .unwrap()
}
fn captured(base: &Path, code: i32, observations: Value) -> PathBuf {
    let inputs = base.join("inputs");
    let capture = base.join("capture");
    fs::create_dir(&capture).unwrap();
    let request: Value =
        serde_json::from_slice(&fs::read(inputs.join("request.json")).unwrap()).unwrap();
    let stdout = if code == 0 {
        let raw = serde_json::to_string(&observations).unwrap();
        serde_json::to_vec(&json!({"id":request["id"],"submittedSource":request["submittedSource"],"submittedSourceSha256":request["submittedSourceSha256"],"observations":observations,"verifierStdout":raw,"verifierStdoutSha256":digest(raw.as_bytes())})).unwrap()
    } else {
        vec![]
    };
    let stderr = if code == 0 {
        b"".as_slice()
    } else {
        b"Error: unbound import: explicit-seam".as_slice()
    };
    fs::write(capture.join("worker-stdout.log"), &stdout).unwrap();
    fs::write(capture.join("worker-stderr.log"), stderr).unwrap();
    fs::copy(inputs.join("request.json"), capture.join("request.json")).unwrap();
    file(
        &capture.join("process.json"),
        &json!({"schema":"agentlab.contained_behavior_process.v1","requestSha256":digest(&fs::read(inputs.join("request.json")).unwrap()),"descriptorSha256":digest(&fs::read(inputs.join("descriptor.json")).unwrap()),"imageId":format!("sha256:{}","a".repeat(64)),"exitCode":code,"timedOut":false,"logBudgetExceeded":false,"stdoutSha256":digest(&stdout),"stderrSha256":digest(stderr)}),
    );
    capture
}
#[test]
fn portable_preparation_does_not_dereference_original_runner_paths_or_grant_approval() {
    let base = fixture();
    let result = prepared(&base);
    assert_eq!(result["diagnosticOnly"], true);
    assert_eq!(result["qualified"], false);
    assert_eq!(result["runtimeEquivalentToOriginal"], false);
    assert_eq!(result["verifierReviewed"], false);
    assert!(prepare(
        &base.join("stage"),
        &base.join("compiler.js"),
        &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
        &format!("sha256:{}", "a".repeat(64)),
        &base.join("inputs")
    )
    .is_err());
}
#[test]
fn original_drift_and_unpinned_worker_fail_before_output() {
    let base = fixture();
    fs::write(base.join("stage/controls.cjs"), "changed").unwrap();
    assert!(prepare(
        &base.join("stage"),
        &base.join("compiler.js"),
        &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
        &format!("sha256:{}", "a".repeat(64)),
        &base.join("inputs")
    )
    .is_err());
    assert!(!base.join("inputs").exists());
    let base = fixture();
    fs::write(base.join("worker.cjs"), "unreviewed adapter").unwrap();
    assert!(prepare(
        &base.join("stage"),
        &base.join("compiler.js"),
        &base.join("worker.cjs"),
        &format!("sha256:{}", "a".repeat(64)),
        &base.join("inputs")
    )
    .is_err());
    assert!(!base.join("inputs").exists());
}
#[test]
fn infrastructure_failure_has_no_failed_behavior_checks_or_killed_controls() {
    let base = fixture();
    prepared(&base);
    let capture = captured(&base, 1, json!({}));
    let result = feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).unwrap();
    assert_eq!(
        result["classification"],
        "verifier-execution-infrastructure-failure"
    );
    assert_eq!(result["checks"], json!([]));
    assert_eq!(result["wrongControlsExecuted"], 0);
    assert_eq!(result["baselinePassed"], false);
}
#[test]
fn normal_exit_is_compared_and_missing_null_is_not_a_pass() {
    for (actual, passed) in [
        (json!({"scenario":{"value":7,"nullable":null}}), true),
        (json!({"scenario":{"value":7}}), false),
        (json!({"scenario":{"value":8,"nullable":null}}), false),
    ] {
        let base = fixture();
        prepared(&base);
        let capture = captured(&base, 0, actual);
        let result = feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).unwrap();
        assert_eq!(result["baselinePassed"], passed);
        assert_eq!(result["checks"].as_array().unwrap().len(), 2);
        assert_eq!(result["qualified"], false);
    }
}
#[test]
fn changed_raw_capture_cannot_produce_feedback() {
    let base = fixture();
    prepared(&base);
    let capture = captured(&base, 1, json!({}));
    fs::write(capture.join("worker-stderr.log"), "changed").unwrap();
    assert!(feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).is_err());
    assert!(!base.join("feedback.json").exists());
}
#[test]
fn actual_cli_prepares_portable_inputs() {
    let base = fixture();
    let result = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .args(["--prepare-source-recipe-diagnostic", "--stage"])
        .arg(base.join("stage"))
        .arg("--typescript")
        .arg(base.join("compiler.js"))
        .arg("--worker")
        .arg(root().join("scripts/source-recipe-diagnostic-worker.cjs"))
        .arg("--image-id")
        .arg(format!("sha256:{}", "a".repeat(64)))
        .arg("--output")
        .arg(base.join("inputs"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(base.join("inputs/intent.json").exists());
}

#[test]
fn frozen_oracle_cannot_be_rewritten_after_capture() {
    let base = fixture();
    prepared(&base);
    let capture = captured(&base, 0, json!({"scenario":{"value":8,"nullable":null}}));
    let path = base.join("inputs/intent.json");
    let mut intent: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    intent["checks"][0]["expected"] = json!(8);
    file(&path, &intent);
    assert!(feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).is_err());
    assert!(!base.join("feedback.json").exists());
}
