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

fn control_fixture(role: &str, failures: Value) -> PathBuf {
    let base = fixture();
    let stage = base.join("stage");
    let mut design: Value =
        serde_json::from_slice(&fs::read(stage.join("design.json")).unwrap()).unwrap();
    design["controls"].as_array_mut().unwrap().push(json!({"id":"selected","role":role,
        "edits":[{"path":"unit.js","from":"module.exports={};","to":"module.exports={changed:true};"}],
        "expectedFailedCheckIds":failures}));
    file(&stage.join("design.json"), &design);
    let runtime = fs::read_to_string(stage.join("design-runtime.cjs")).unwrap();
    let mut manifest: Value = serde_json::from_str(
        runtime
            .lines()
            .next()
            .unwrap()
            .strip_prefix("const manifest = ")
            .unwrap()
            .strip_suffix(';')
            .unwrap(),
    )
    .unwrap();
    manifest["controls"] = design["controls"].clone();
    fs::write(
        stage.join("design-runtime.cjs"),
        format!("const manifest = {manifest};\nmodule.exports=()=>({{}});"),
    )
    .unwrap();
    let mut receipt: Value =
        serde_json::from_slice(&fs::read(stage.join("stage-receipt.json")).unwrap()).unwrap();
    receipt["designSha256"] = json!(digest(&fs::read(stage.join("design.json")).unwrap()));
    receipt["designRuntimeSha256"] =
        json!(digest(&fs::read(stage.join("design-runtime.cjs")).unwrap()));
    file(&stage.join("stage-receipt.json"), &receipt);
    base
}

fn prepared_control(base: &Path) -> Value {
    agentlab_code_analysis::maintainer_source_diagnostic::prepare_control(
        &base.join("stage"),
        &base.join("compiler.js"),
        &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
        &format!("sha256:{}", "a".repeat(64)),
        &base.join("inputs"),
        "selected",
    )
    .unwrap()
}

#[test]
fn control_diagnostics_compare_exact_failure_sets_without_approval() {
    for (actual, matched, missing, unexpected) in [
        (
            json!({"scenario":{"value":8,"nullable":null}}),
            true,
            json!([]),
            json!([]),
        ),
        (
            json!({"scenario":{"value":7,"nullable":null}}),
            false,
            json!(["answer"]),
            json!([]),
        ),
        (
            json!({"scenario":{"value":8}}),
            false,
            json!([]),
            json!(["nullable"]),
        ),
    ] {
        let base = control_fixture("wrong", json!(["answer"]));
        let intent = prepared_control(&base);
        assert_eq!(
            intent["schema"],
            "agentlab.source_recipe_control_diagnostic_intent.v1"
        );
        let capture = captured(&base, 0, actual);
        let result = feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).unwrap();
        assert_eq!(result["declarationMatched"], matched);
        assert_eq!(result["missingExpectedFailureIds"], missing);
        assert_eq!(result["unexpectedFailedCheckIds"], unexpected);
        assert_eq!(result["qualified"], false);
        assert_eq!(result["semanticQualified"], false);
        assert!(result.get("baselinePassed").is_none());
    }
}

#[test]
fn control_execution_failure_is_not_a_killed_wrong_implementation() {
    let base = control_fixture("wrong", json!(["answer"]));
    prepared_control(&base);
    let capture = captured(&base, 1, json!({}));
    let result = feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).unwrap();
    assert_eq!(result["executionCompleted"], false);
    assert_eq!(result["declarationMatched"], false);
    assert_eq!(result["observedFailedCheckIds"], Value::Null);
    assert_eq!(result["missingExpectedFailureIds"], Value::Null);
    assert_eq!(result["checks"], json!([]));
}

#[test]
fn accepted_control_is_checked_and_declaration_drift_is_rejected() {
    let base = control_fixture("reference", json!([]));
    prepared_control(&base);
    let capture = captured(&base, 0, json!({"scenario":{"value":7,"nullable":null}}));
    let result = feedback(&base.join("inputs"), &capture, &base.join("feedback.json")).unwrap();
    assert_eq!(result["declarationMatched"], true);
    let path = base.join("inputs/intent.json");
    let mut intent: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    intent["expectedFailedCheckIds"] = json!(["answer"]);
    file(&path, &intent);
    assert!(feedback(&base.join("inputs"), &capture, &base.join("drift.json")).is_err());
    assert!(!base.join("drift.json").exists());
}

#[test]
fn unknown_or_invalid_control_cannot_launch() {
    for (role, failures) in [
        ("wrong", json!([])),
        ("wrong", json!(["missing"])),
        ("wrong", json!(["answer", "answer"])),
        ("reference", json!(["answer"])),
        ("unknown", json!([])),
    ] {
        let base = control_fixture(role, failures);
        assert!(
            agentlab_code_analysis::maintainer_source_diagnostic::prepare_control(
                &base.join("stage"),
                &base.join("compiler.js"),
                &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
                &format!("sha256:{}", "a".repeat(64)),
                &base.join("inputs"),
                "selected"
            )
            .is_err()
        );
        assert!(!base.join("inputs").exists());
    }
    let base = fixture();
    assert!(
        agentlab_code_analysis::maintainer_source_diagnostic::prepare_control(
            &base.join("stage"),
            &base.join("compiler.js"),
            &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
            &format!("sha256:{}", "a".repeat(64)),
            &base.join("inputs"),
            "missing"
        )
        .is_err()
    );
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
fn actual_cli_selects_frozen_control_with_separate_intent_schema() {
    let base = control_fixture("wrong", json!(["answer"]));
    let result = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .args(["--prepare-source-recipe-control-diagnostic", "--stage"])
        .arg(base.join("stage"))
        .args(["--control-id", "selected", "--typescript"])
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
    let intent: Value =
        serde_json::from_slice(&fs::read(base.join("inputs/intent.json")).unwrap()).unwrap();
    assert_eq!(intent["controlId"], "selected");
    assert_eq!(
        intent["schema"],
        "agentlab.source_recipe_control_diagnostic_intent.v1"
    );
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

fn repair_fixture(maximum: u64) -> (PathBuf, PathBuf) {
    let base = fixture();
    let request = fs::read(base.join("stage/request.json")).unwrap();
    let intent =
        agentlab_code_analysis::maintainer_source_repair::loop_intent(&request, maximum).unwrap();
    file(&base.join("stage/diagnostic-loop-intent.json"), &intent);
    let mut receipt: Value =
        serde_json::from_slice(&fs::read(base.join("stage/stage-receipt.json")).unwrap()).unwrap();
    receipt["diagnosticLoopIntentSha256"] = json!(digest(
        &fs::read(base.join("stage/diagnostic-loop-intent.json")).unwrap()
    ));
    file(&base.join("stage/stage-receipt.json"), &receipt);
    prepared(&base);
    let capture = captured(&base, 1, json!({}));
    let mut process: Value =
        serde_json::from_slice(&fs::read(capture.join("process.json")).unwrap()).unwrap();
    for (key, value) in [
        ("cleanupExitCode", json!(0)),
        ("network", json!("none")),
        ("rootFilesystemReadOnly", json!(true)),
        ("capabilitiesDropped", json!(true)),
        ("durationMs", json!(206)),
    ] {
        process[key] = value;
    }
    file(&capture.join("process.json"), &process);
    (base, capture)
}
fn repair_packet(base: &Path, capture: &Path, maximum: u64) -> Value {
    agentlab_code_analysis::maintainer_source_repair::prepare(
        &base.join("stage"),
        &base.join("inputs"),
        capture,
        maximum,
        &base.join("repair.json"),
    )
    .unwrap()
}

#[test]
fn repair_reconstructs_failure_and_freezes_complete_design_contract_and_source_paths() {
    use agentlab_code_analysis::maintainer_source_repair::{check, check_output};
    let (base, capture) = repair_fixture(2);
    let packet = repair_packet(&base, &capture, 2);
    let request = fs::read(base.join("stage/request.json")).unwrap();
    let bytes = fs::read(base.join("repair.json")).unwrap();
    let admission = check(&request, &bytes).unwrap();
    assert_eq!(admission["repairIndex"], 1);
    assert_eq!(
        admission["feedback"]["classification"],
        "verifier-execution-infrastructure-failure"
    );
    assert_eq!(admission["feedback"]["checks"], json!([]));
    assert_eq!(admission["semanticQualified"], false);
    assert_eq!(
        packet["stderrOriginal"],
        "Error: unbound import: explicit-seam"
    );
    let mut successor: Value =
        serde_json::from_slice(&fs::read(base.join("stage/proposal.json")).unwrap()).unwrap();
    let original = successor.clone();
    let design = fs::read(base.join("stage/design.json")).unwrap();
    assert!(check_output(
        &request,
        &bytes,
        &serde_json::to_vec(&successor).unwrap(),
        &design
    )
    .is_err());
    successor["verifierSource"] = json!("new bounded candidate code");
    assert_eq!(
        check_output(
            &request,
            &bytes,
            &serde_json::to_vec(&successor).unwrap(),
            &design
        )
        .unwrap()["semanticQualified"],
        false
    );
    for change in [
        "expected",
        "pointer",
        "source",
        "controls",
        "scenario",
        "design-bytes",
    ] {
        let mut bad = successor.clone();
        let mut bad_design: Value = serde_json::from_slice(&design).unwrap();
        match change {
            "expected" => bad["contract"]["checks"][0]["expected"] = json!(8),
            "pointer" => bad["contract"]["checks"][0]["pointer"] = json!("/other"),
            "source" => bad["sourcePaths"] = json!(["other.js"]),
            "controls" => bad["contract"]["controls"] = json!([]),
            "scenario" => bad_design["scenarios"][0]["initialState"] = json!({"changed":true}),
            _ => {}
        }
        let changed_design = if change == "scenario" {
            serde_json::to_vec(&bad_design).unwrap()
        } else if change == "design-bytes" {
            [design.as_slice(), b"\n"].concat()
        } else {
            design.clone()
        };
        assert!(
            check_output(
                &request,
                &bytes,
                &serde_json::to_vec(&bad).unwrap(),
                &changed_design
            )
            .is_err(),
            "{change}"
        );
    }
    assert_eq!(
        original["verifierSource"],
        packet["parentProposalOriginal"]
            .as_str()
            .map(|s| serde_json::from_str::<Value>(s).unwrap()["verifierSource"].clone())
            .unwrap()
    );
    let mut changed = request.clone();
    changed.push(b'\n');
    assert!(check(&changed, &bytes).is_err());
}

#[test]
fn repair_stops_on_unfrozen_or_changed_budget_transport_cleanup_timeout_and_raw_log_drift() {
    for damage in [
        "timeout", "logs", "cleanup", "signal", "spawn", "budget", "legacy", "child", "stderr",
        "nonutf8", "passed",
    ] {
        let (base, capture) = repair_fixture(1);
        let path = capture.join("process.json");
        let mut process: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        match damage {
            "timeout" => process["timedOut"] = json!(true),
            "logs" => process["logBudgetExceeded"] = json!(true),
            "cleanup" => process["cleanupExitCode"] = json!(1),
            "signal" => process["exitCode"] = json!(137),
            "spawn" => process["exitCode"] = json!(125),
            "legacy" => {
                fs::remove_file(base.join("stage/diagnostic-loop-intent.json")).unwrap();
            }
            "child" => {
                fs::write(base.join("stage/revision-request.json"), "{}").unwrap();
            }
            "stderr" => {
                fs::write(capture.join("worker-stderr.log"), "changed").unwrap();
            }
            "nonutf8" => {
                fs::write(capture.join("worker-stderr.log"), [255]).unwrap();
                process["stderrSha256"] = json!(digest(&[255]));
            }
            "passed" => {
                let request: Value =
                    serde_json::from_slice(&fs::read(base.join("inputs/request.json")).unwrap())
                        .unwrap();
                let observations = json!({"scenario":{"value":7,"nullable":null}});
                let raw = serde_json::to_string(&observations).unwrap();
                let stdout=serde_json::to_vec(&json!({"id":request["id"],"submittedSource":request["submittedSource"],"submittedSourceSha256":request["submittedSourceSha256"],"observations":observations,"verifierStdout":raw,"verifierStdoutSha256":digest(raw.as_bytes())})).unwrap();
                fs::write(capture.join("worker-stdout.log"), &stdout).unwrap();
                process["exitCode"] = json!(0);
                process["stdoutSha256"] = json!(digest(&stdout));
            }
            _ => {}
        }
        file(&path, &process);
        let result = agentlab_code_analysis::maintainer_source_repair::prepare(
            &base.join("stage"),
            &base.join("inputs"),
            &capture,
            if damage == "budget" { 2 } else { 1 },
            &base.join("repair.json"),
        );
        assert!(result.is_err(), "{damage}");
        assert!(!base.join("repair.json").exists());
    }
}

#[test]
fn repair_second_round_requires_original_chain_and_cannot_reset_or_extend_budget() {
    use agentlab_code_analysis::maintainer_source_repair::{
        check, check_output, prepare as repair,
    };
    let (first, capture) = repair_fixture(2);
    let prior = repair_packet(&first, &capture, 2);
    let prior_bytes = fs::read(first.join("repair.json")).unwrap();
    let second = fixture();
    let request = fs::read(second.join("stage/request.json")).unwrap();
    let design = fs::read(second.join("stage/design.json")).unwrap();
    let mut proposal: Value =
        serde_json::from_slice(&fs::read(second.join("stage/proposal.json")).unwrap()).unwrap();
    proposal["verifierSource"] = json!("next candidate code");
    file(&second.join("stage/proposal.json"), &proposal);
    fs::write(second.join("stage/controls.cjs"), "next candidate code").unwrap();
    fs::write(second.join("stage/diagnostic-repair.json"), &prior_bytes).unwrap();
    fs::write(
        second.join("stage/diagnostic-loop-intent.json"),
        prior["loopIntentOriginal"].as_str().unwrap(),
    )
    .unwrap();
    let result = check_output(
        &request,
        &prior_bytes,
        &fs::read(second.join("stage/proposal.json")).unwrap(),
        &design,
    )
    .unwrap();
    file(&second.join("stage/diagnostic-repair-output.json"), &result);
    let mut receipt: Value =
        serde_json::from_slice(&fs::read(second.join("stage/stage-receipt.json")).unwrap())
            .unwrap();
    for (key, file_name) in [
        ("proposalSha256", "proposal.json"),
        ("diagnosticLoopIntentSha256", "diagnostic-loop-intent.json"),
        ("diagnosticRepairPacketSha256", "diagnostic-repair.json"),
        (
            "diagnosticRepairOutputSha256",
            "diagnostic-repair-output.json",
        ),
    ] {
        receipt[key] = json!(digest(
            &fs::read(second.join("stage").join(file_name)).unwrap()
        ));
    }
    file(&second.join("stage/stage-receipt.json"), &receipt);
    prepared(&second);
    let capture = captured(&second, 1, json!({}));
    let mut process: Value =
        serde_json::from_slice(&fs::read(capture.join("process.json")).unwrap()).unwrap();
    for (key, value) in [
        ("cleanupExitCode", json!(0)),
        ("network", json!("none")),
        ("rootFilesystemReadOnly", json!(true)),
        ("capabilitiesDropped", json!(true)),
        ("durationMs", json!(206)),
    ] {
        process[key] = value;
    }
    file(&capture.join("process.json"), &process);
    let packet = repair(
        &second.join("stage"),
        &second.join("inputs"),
        &capture,
        2,
        &second.join("repair.json"),
    )
    .unwrap();
    assert_eq!(packet["repairIndex"], 2);
    for damage in ["reset", "extend", "prior-source", "third"] {
        let mut bad = packet.clone();
        match damage {
            "reset" => {
                bad["repairIndex"] = json!(1);
                bad["previousRepairOriginal"] = Value::Null;
            }
            "extend" => bad["maximumRepairs"] = json!(3),
            "third" => bad["repairIndex"] = json!(3),
            _ => {
                let mut previous = prior.clone();
                previous["parentProposalOriginal"] = json!("{}");
                bad["previousRepairOriginal"] = json!(serde_json::to_string(&previous).unwrap());
            }
        }
        assert!(
            check(&request, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "{damage}"
        );
    }
}
