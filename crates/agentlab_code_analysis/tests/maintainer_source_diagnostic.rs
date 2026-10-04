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
    let request = json!({"schema":"agentlab.source_recipe_author_request.v1","reviewed":false,"automaticPromotion":false,"scope":{"id":"scope","repositoryId":"generic-fixture","sourceRevision":"1".repeat(40)},"source":{"repositoryId":"generic-fixture","revision":"1".repeat(40)},"sourceFiles":[source_file],"policy":{"methodDependencies":[{"path":"/missing/original/compiler.js","sha256":digest(b"module.exports={};")}]}});
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
    captured_inputs(&inputs, &capture, code, observations)
}
fn captured_inputs(inputs: &Path, capture: &Path, code: i32, observations: Value) -> PathBuf {
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
    capture.to_path_buf()
}

fn suite_fixture() -> PathBuf {
    suite_fixture_with_wrong_count(1)
}

fn suite_fixture_with_wrong_count(wrongs: usize) -> PathBuf {
    suite_fixture_with_binding(wrongs, None)
}

fn suite_fixture_with_binding(wrongs: usize, binding: Option<&Value>) -> PathBuf {
    let base = fixture();
    let stage = base.join("stage");
    if let Some(binding) = binding {
        let mut request: Value =
            serde_json::from_slice(&fs::read(stage.join("request.json")).unwrap()).unwrap();
        request["source"] = binding["source"].clone();
        request["scope"]["repositoryId"] = binding["source"]["repositoryId"].clone();
        request["scope"]["sourceRevision"] = binding["source"]["revision"].clone();
        request["knowledgeCutSha256"] = binding["cutSha256"].clone();
        request["authorityRevision"] = binding["revision"].clone();
        if let Some(blob) = binding["gitBlobOid"].as_str() {
            request["sourceFiles"][0]["gitBlobOid"] = json!(blob);
            request["scope"]["stage"] = json!("repository-scope");
        }
        file(&stage.join("request.json"), &request);
    }
    let mut controls = json!([
        {"id":"baseline","role":"baseline","edits":[],"expectedFailedCheckIds":[]},
        {"id":"valid-a","role":"reference","edits":[{"path":"unit.js","before":"{}","after":"{a:1}"}],"expectedFailedCheckIds":[]},
        {"id":"valid-b","role":"reference","edits":[{"path":"unit.js","before":"{}","after":"{b:1}"}],"expectedFailedCheckIds":[]},
        {"id":"wrong","role":"wrong","edits":[{"path":"unit.js","before":"{}","after":"{wrong:1}"}],"expectedFailedCheckIds":["answer"]}
    ]);
    if wrongs >= 2 {
        controls.as_array_mut().unwrap().push(json!({"id":"wrong-b","role":"wrong","edits":[{"path":"unit.js","before":"{}","after":if wrongs==3 {"{wrong:1}"} else {"{wrong:2}"}}],"expectedFailedCheckIds":["answer"]}));
    }
    let mut design: Value =
        serde_json::from_slice(&fs::read(stage.join("design.json")).unwrap()).unwrap();
    design["controls"] = controls.clone();
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
    manifest["controls"] = controls.clone();
    if binding.is_some_and(|b| b["gitBlobOid"].is_string()) {
        let request: Value =
            serde_json::from_slice(&fs::read(stage.join("request.json")).unwrap()).unwrap();
        manifest["files"] = request["sourceFiles"].clone();
    }
    fs::write(
        stage.join("design-runtime.cjs"),
        format!("const manifest = {manifest};\nmodule.exports=()=>({{}});"),
    )
    .unwrap();
    let mut receipt: Value =
        serde_json::from_slice(&fs::read(stage.join("stage-receipt.json")).unwrap()).unwrap();
    for (name, key) in [
        ("request.json", "requestSha256"),
        ("design.json", "designSha256"),
        ("design-runtime.cjs", "designRuntimeSha256"),
    ] {
        receipt[key] = json!(digest(&fs::read(stage.join(name)).unwrap()));
    }
    file(&stage.join("stage-receipt.json"), &receipt);
    let suite = base.join("suite");
    fs::create_dir(&suite).unwrap();
    let mut rows = Vec::new();
    let mut ids = vec!["baseline", "valid-a", "valid-b", "wrong"];
    if wrongs >= 2 {
        ids.push("wrong-b");
    }
    ids.push("valid-a");
    for (index, id) in ids.iter().enumerate() {
        let inputs = suite.join(format!("control-{index}"));
        agentlab_code_analysis::maintainer_source_diagnostic::prepare_control(
            &stage,
            &base.join("compiler.js"),
            &root().join("scripts/source-recipe-diagnostic-worker.cjs"),
            &format!("sha256:{}", "a".repeat(64)),
            &inputs,
            id,
        )
        .unwrap();
        let disagrees = binding.is_some_and(|b| b["fixtureDisagreement"] == true);
        let actual = json!({"scenario":{"value":if id.starts_with("wrong") && !disagrees {8} else {7},"nullable":null}});
        let capture = captured_inputs(&inputs, &inputs.join("contained-input-fixture"), 0, actual);
        let report = feedback(&inputs, &capture, &inputs.join("feedback.json")).unwrap();
        rows.push(json!({"controlId":id,"role":if index==0 {"baseline"} else if id.starts_with("wrong") {"wrong"} else {"reference"},"recovery":index==ids.len()-1,
            "feedbackSha256":digest(&fs::read(inputs.join("feedback.json")).unwrap()),"classification":report["classification"],"declarationMatched":report["declarationMatched"]}));
    }
    file(
        &suite.join("result.json"),
        &json!({"schema":"agentlab.source_recipe_control_suite_result.v1","status":if rows.iter().all(|r|r["declarationMatched"]==true){"declarations-matched"}else{"review-declaration-mismatch"},
        "attempts":rows,"designSha256":receipt["designSha256"],"diagnosticOnly":true,"qualified":false,"semanticQualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    );
    base
}

#[test]
fn business_returns_original_source_suite_without_wrapping_or_fresh_execution_claims() {
    for disagrees in [false, true] {
        let knowledge = root()
            .join("examples/maintainer-knowledge-gate/first-four")
            .canonicalize()
            .unwrap();
        let cut_bytes = fs::read(knowledge.join("maintainer-knowledge-cut.json")).unwrap();
        let cut: Value = serde_json::from_slice(&cut_bytes).unwrap();
        let source = cut["repositories"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["id"] == "code-workshop")
            .unwrap();
        let binding = json!({"fixtureDisagreement":disagrees,"source":{"repositoryId":source["id"],"revision":source["revision"]},
        "cutSha256":digest(&cut_bytes),"revision":cut["tableGitAuthority"]["revision"]});
        let base = suite_fixture_with_binding(1, Some(&binding));
        let capture = json!({"stageDirectory":base.join("stage"),"suiteDirectory":base.join("suite"),
        "stageReceiptSha256":digest(&fs::read(base.join("stage/stage-receipt.json")).unwrap()),
        "suiteResultSha256":digest(&fs::read(base.join("suite/result.json")).unwrap())});
        let mut state = json!({"schema":"agentlab.flywheel_business_state.v1","automaticPromotion":false,
        "repositoryId":source["id"],"sourceRevision":source["revision"],"candidateId":"scope",
        "knowledge":{"directory":knowledge,"cutSha256":binding["cutSha256"],"revision":binding["revision"]},
        "guidanceMode":"reviewed-bootstrap","bootstrapReview":{"reviewed":true,"knowledgeCutSha256":binding["cutSha256"]},
        "sourceSuiteCapture":capture});
        let invoke = |state: &Value, stage: &str, round: u64, name: &str| {
            let path = base.join(format!("{name}-state.json"));
            file(&path, state);
            let out = base.join(name);
            fs::create_dir(&out).unwrap();
            let request = json!({"schema":"agentlab.flywheel_stage_request.v1","automaticPromotion":false,
            "stage":stage,"round":round,"inputState":{"path":path,"sha256":digest(&fs::read(&path).unwrap())}});
            let result = agentlab_code_analysis::maintainer_flywheel_business::run(
                &serde_json::to_vec(&request).unwrap(),
                &out,
            )
            .unwrap();
            (result, out)
        };
        let (case, case_out) = invoke(&state, "case-execution", 0, "case");
        assert_eq!(case["status"], "completed");
        let report: Value =
            serde_json::from_slice(&fs::read(case_out.join("business/report.json")).unwrap())
                .unwrap();
        assert_eq!(report["freshExecutionPerformed"], false);
        assert_eq!(report["formalCaseQualified"], false);
        assert_eq!(report["taskPassed"], !disagrees);
        state = serde_json::from_slice(&fs::read(case_out.join("business/state.json")).unwrap())
            .unwrap();
        let (returned, out) = invoke(&state, "evidence-return", 0, "return");
        assert_eq!(returned["status"], "review-required");
        let returned_report: Value =
            serde_json::from_slice(&fs::read(out.join("business/report.json")).unwrap()).unwrap();
        assert_eq!(returned_report["observationExported"], true);
        assert_eq!(returned_report["lessonCreated"], false);
        assert_eq!(returned_report["authorityWritePerformed"], false);
        assert_eq!(returned_report["taskPassed"], !disagrees);
        assert_eq!(
            fs::read(out.join("business/observations/source-suite/result.json")).unwrap(),
            fs::read(base.join("suite/result.json")).unwrap()
        );
        assert!(!out
            .join("business/observations/behavior-capture.json")
            .exists());
        // Exact current source bytes reach the ordinary admission gate. They
        // lack a reviewed committed lesson, so this must still reject there.
        // Changed historical lesson bytes stop earlier at the binding gate.
        let lesson_source = out.join("business/observations");
        for (name, changed_file, expected_error) in [
            ("unreviewed-lesson", None, None),
            (
                "borrowed-inventory",
                Some("source-suite-inputs.json"),
                Some("inventory borrows"),
            ),
            (
                "borrowed-worker",
                Some("source-suite/control-0/contained-input-fixture/worker-stdout.log"),
                Some("raw bytes borrow"),
            ),
            (
                "borrowed-candidate",
                Some("candidate.json"),
                Some("candidate differs"),
            ),
        ] {
            let changed_path = changed_file.map(|p| lesson_source.join(p));
            let original = changed_path.as_ref().map(|p| fs::read(p).unwrap());
            if let Some(path) = &changed_path {
                fs::write(path, b"{}").unwrap();
            }
            let mut reviewed_state = state.clone();
            reviewed_state["lessonAdmission"] = json!({"proposalDirectory":knowledge,
                "lessonSourceDirectory":lesson_source,"lessonId":"suite-lesson"});
            let (result, output) = invoke(&reviewed_state, "evidence-return", 0, name);
            assert_eq!(
                result["status"],
                if changed_file.is_none() {
                    "review-required"
                } else {
                    "rejected"
                }
            );
            let rejection: Value =
                serde_json::from_slice(&fs::read(output.join("business/report.json")).unwrap())
                    .unwrap();
            assert!(!output.join("business/staged-admission").exists());
            if changed_file.is_none() {
                assert_eq!(rejection["gap"], "reviewed-source-suite-lesson-required");
                continue;
            }
            let error = rejection["error"].as_str().unwrap();
            if let Some(expected) = expected_error {
                assert!(error.contains(expected), "{error}");
            } else {
                assert!(!error.contains("business source lesson"), "{error}");
            }
            assert!(!output.join("business/staged-admission").exists());
            if let Some(path) = changed_path {
                fs::write(path, original.unwrap()).unwrap();
            }
        }
        for (name, mut changed, stage, round) in [
            ("round", state.clone(), "evidence-return", 1),
            ("scope", state.clone(), "evidence-return", 0),
            ("digest", state.clone(), "evidence-return", 0),
            ("ambiguous", state.clone(), "case-execution", 0),
        ] {
            if name == "scope" {
                changed["candidateId"] = json!("borrowed");
            }
            if name == "digest" {
                changed["sourceSuiteCapture"]["suiteResultSha256"] = json!("0".repeat(64));
            }
            if name == "ambiguous" {
                changed["behaviorExecution"] = json!({});
            }
            let (result, out) = invoke(&changed, stage, round, name);
            assert_eq!(result["status"], "rejected");
            assert!(!out.join("business/observations").exists());
        }
        fs::remove_dir_all(base).unwrap();
    }
}

#[test]
fn suite_readback_reconstructs_every_control_and_recovery_without_approval() {
    let base = suite_fixture();
    let result = agentlab_code_analysis::maintainer_source_diagnostic::validate_suite(
        &base.join("stage"),
        &base.join("suite"),
        &base.join("readback.json"),
    )
    .unwrap();
    assert_eq!(result["completeInventoryReconstructed"], true);
    assert_eq!(result["controlCount"], 4);
    assert_eq!(result["controls"].as_array().unwrap().len(), 5);
    assert_eq!(result["acceptedReferenceRecoveryReconstructed"], true);
    assert_eq!(result["qualified"], false);
    assert_eq!(result["producerAuthenticated"], false);
}

fn suite_lesson_review(export: &Path) -> Value {
    let request: Value =
        serde_json::from_slice(&fs::read(export.join("source-stage/request.json")).unwrap())
            .unwrap();
    let design: Value =
        serde_json::from_slice(&fs::read(export.join("source-stage/design.json")).unwrap())
            .unwrap();
    let mut review = json!({"schema":"agentlab.source_suite_lesson_review.v1","reviewed":true,"verdict":"accept",
        "automaticPromotion":false,"unresolvedFindings":[],"id":"suite-lesson","scope":"fixture source seam",
        "reviewerId":"fixture-review","phenomenon":"Frozen checks distinguish controls","cause":"Explicit source variants change behavior",
        "change":"Reconstruct all observations before promotion","factId":"suite-fact","skillId":"suite-skill",
        "body":"Review original source and all controls before admission.","skillStage":"calibration",
        "scopeSha256":digest(&serde_json::to_vec(&request["scope"]).unwrap()),
        "requestSha256":digest(&fs::read(export.join("source-stage/request.json")).unwrap()),
        "designSha256":digest(&fs::read(export.join("source-stage/design.json")).unwrap()),
        "proposalSha256":digest(&fs::read(export.join("source-stage/proposal.json")).unwrap()),
        "suiteResultSha256":digest(&fs::read(export.join("source-suite/result.json")).unwrap()),
        "inputInventorySha256":digest(&fs::read(export.join("source-suite-inputs.json")).unwrap())});
    for (key, rows) in [
        ("checkReviews", &design["checks"]),
        ("scenarioReviews", &design["scenarios"]),
        ("controlReviews", &design["controls"]),
    ] {
        review[key] = json!(rows.as_array().unwrap().iter().map(|r| json!({"id":r["id"],"accepted":true,
            "rationale":"Synthetic review tests bindings, not semantic truth.","exercisedByScenarioIds":["scenario"],
            "sourceEvidence":[{"path":"unit.js","quote":"module.exports"}]})).collect::<Vec<_>>());
    }
    review
}

#[test]
fn source_review_artifact_transport_rejects_unsafe_members_and_ignores_sessions() {
    let base = fixture();
    let script = base.join("artifact-transport-fixture.py");
    fs::write(&script, r#"
import importlib.util,stat,sys,warnings,zipfile
from pathlib import Path
repo,base=sys.argv[1:];base=Path(base)
spec=importlib.util.spec_from_file_location('acquisition',Path(repo)/'scripts/acquire-source-suite-review-input.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
archive=base/'good.zip'
with zipfile.ZipFile(archive,'w') as z:
    z.writestr('observation-export/source-stage/request.json','original bytes')
    z.writestr('agent/participant-state/session.json','not reviewer instructions')
module.extract_observations(archive,base/'selected')
for name in ['traversal','absolute','backslash','duplicate','symlink','missing']:
    archive=base/(name+'.zip')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with zipfile.ZipFile(archive,'w') as z:
            if name!='missing':z.writestr('observation-export/valid.json','original')
            if name=='traversal':z.writestr('observation-export/../../escape','bad')
            if name=='absolute':z.writestr('/escape','bad')
            if name=='backslash':z.writestr('observation-export\\escape','bad')
            if name=='duplicate':z.writestr('observation-export/valid.json','second')
            if name=='symlink':
                info=zipfile.ZipInfo('observation-export/link');info.create_system=3
                info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../escape')
            if name=='missing':z.writestr('agent/session.json','not observations')
    try:module.extract_observations(archive,base/('selected-'+name))
    except ValueError:pass
    else:raise AssertionError(name+' accepted')
    assert not (base/('selected-'+name)).exists()
"#).unwrap();
    let result = Command::new("python3")
        .arg(&script)
        .arg(root())
        .arg(&base)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        fs::read(base.join("selected/source-stage/request.json")).unwrap(),
        b"original bytes"
    );
    assert!(!base.join("selected/agent").exists());
    assert!(!base.join("escape").exists());
    fs::remove_dir_all(base).unwrap();
}

#[test]
fn git_bound_review_native_template_keeps_source_evidence_and_independent_verdicts() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let git_root = fixture();
    let checkout = git_root.join("checkout");
    fs::create_dir(&checkout).unwrap();
    fs::write(checkout.join("unit.js"), "module.exports={};\n").unwrap();
    let git = |args: &[&str]| {
        let out = Command::new("git")
            .args(args)
            .current_dir(&checkout)
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        String::from_utf8(out.stdout).unwrap().trim().to_owned()
    };
    git(&["init", "-q"]);
    let repository = "https://example.invalid/unrelated-template-source.git";
    git(&["remote", "add", "origin", repository]);
    git(&["add", "unit.js"]);
    git(&[
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "frozen source",
    ]);
    let binding = json!({"source":{"repository":repository,"repositoryId":"unrelated-template-source","revision":git(&["rev-parse", "HEAD"])},
        "gitBlobOid":git(&["rev-parse", "HEAD:unit.js"]),"cutSha256":"a".repeat(64),"revision":"b".repeat(40)});
    let base = suite_fixture_with_binding(2, Some(&binding));
    let observation = base.join("git-observations");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let rubric = serde_json::to_vec(&json!({"schema":"agentlab.prospective_source_quality_review.v1","repositoryAgnostic":true,
        "frozenBeforeDispatch":true,"verdicts":["pass","fail","unverified"],
        "criteria":[{"id":"semantics","requirement":"Fixture source membership.","evidence":"Original source."}]})).unwrap();
    let packet = reviewer::prepare_with_git(&observation, &rubric, Some(&checkout)).unwrap();
    let template = &packet["responseContract"]["lessonReviewTemplate"];
    assert_eq!(template["skillStage"], "calibration");
    assert_ne!(template["skillId"], packet["scope"]["id"]);
    let mut review = suite_lesson_review(&observation);
    for (key, value) in template.as_object().unwrap() {
        review
            .as_object_mut()
            .unwrap()
            .insert(key.clone(), value.clone());
    }
    let mut response = json!({"schema":"agentlab.independent_source_suite_review_response.v1",
        "reviewerId":review["reviewerId"],"reviewRequestSha256":digest(&serde_json::to_vec(&packet).unwrap()),
        "qualityRubricSha256":packet["qualityRubricSha256"],"reviewBindings":packet["reviewBindings"],
        "automaticPromotion":false,"verdict":"accept","unresolvedFindings":[],"lessonReview":review,
        "scenarioReviews":review["scenarioReviews"],"checkReviews":review["checkReviews"],"controlReviews":review["controlReviews"],
        "criterionReviews":[{"id":"semantics","verdict":"pass","rationale":"Synthetic fixture membership only.",
            "evidence":[{"pointer":"/originalSourceFiles/0/content","quote":"module.exports"}]}]});
    let validate = |r: &Value| {
        reviewer::validate_response_with_git(
            &observation,
            &rubric,
            &serde_json::to_vec(r).unwrap(),
            Some(&checkout),
        )
    };
    assert_eq!(validate(&response).unwrap()["lessonContentVerified"], true);
    for key in ["skillId", "skillStage"] {
        let mut wrong = response.clone();
        wrong["lessonReview"][key] =
            packet["scope"][if key == "skillId" { "id" } else { "stage" }].clone();
        assert!(validate(&wrong)
            .unwrap_err()
            .contains(&format!("/lessonReview/{key}")));
    }
    let mut unsupported = response.clone();
    unsupported["criterionReviews"][0]["evidence"][0]["quote"] = json!("fabricated quote");
    assert!(validate(&unsupported).is_err());
    response["verdict"] = json!("unverified");
    response["lessonReview"] = Value::Null;
    response["unresolvedFindings"] = json!(["Synthetic reviewer has insufficient support."]);
    response["criterionReviews"][0]["verdict"] = json!("unverified");
    response["criterionReviews"][0]["evidence"] = json!([]);
    assert_eq!(validate(&response).unwrap()["verdict"], "unverified");
    let legacy = reviewer::prepare(&observation, &rubric).unwrap();
    assert!(legacy["responseContract"]
        .get("lessonReviewTemplate")
        .is_none());
    let prompt = reviewer::prompt_with_git(&observation, &rubric, Some(&checkout)).unwrap();
    assert!(String::from_utf8(prompt)
        .unwrap()
        .contains(&serde_json::to_string_pretty(template).unwrap()));
    fs::remove_dir_all(base).unwrap();
    fs::remove_dir_all(git_root).unwrap();
}

#[test]
fn isolated_review_transport_uses_native_gates_and_preserves_original_rejections() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_wrong_count(2);
    let observation = base.join("transport-observations");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let rubric = json!({"schema":"agentlab.prospective_source_quality_review.v1", "repositoryAgnostic":true,
        "frozenBeforeDispatch":true,"verdicts":["pass","fail","unverified"],
        "criteria":[{"id":"provenance","requirement":"Independent identity.","evidence":"Original Git capture."}]});
    let rubric_path = base.join("transport-rubric.json");
    file(&rubric_path, &rubric);
    let packet = reviewer::prepare(&observation, &fs::read(&rubric_path).unwrap()).unwrap();
    let mut response = json!({"schema":"agentlab.independent_source_suite_review_response.v1",
        "reviewerId":"synthetic-transport-fixture","reviewRequestSha256":digest(&serde_json::to_vec(&packet).unwrap()),
        "qualityRubricSha256":packet["qualityRubricSha256"],"reviewBindings":packet["reviewBindings"],
        "automaticPromotion":false,"verdict":"unverified","unresolvedFindings":["Fixture cannot authenticate source."],
        "lessonReview":null,"criterionReviews":[{"id":"provenance","verdict":"unverified",
            "rationale":"No independent source authentication.","evidence":[]}]});
    for (key, declared) in [
        ("scenarioReviews", "scenarios"),
        ("checkReviews", "checks"),
        ("controlReviews", "controls"),
    ] {
        response[key] = json!(packet["design"][declared].as_array().unwrap().iter()
            .map(|r| json!({"id":r["id"],"accepted":null,"rationale":"Not semantically reviewed in transport fixture.","sourceEvidence":[]}))
            .collect::<Vec<_>>());
    }
    file(&base.join("fixture-response.json"), &response);
    let review = suite_lesson_review(&observation);
    let accepted = json!({"schema":"agentlab.independent_source_suite_review_response.v1",
        "reviewerId":review["reviewerId"],"reviewRequestSha256":response["reviewRequestSha256"],
        "qualityRubricSha256":packet["qualityRubricSha256"],"reviewBindings":packet["reviewBindings"],
        "automaticPromotion":false,"verdict":"accept","unresolvedFindings":[],"lessonReview":review,
        "scenarioReviews":review["scenarioReviews"],"checkReviews":review["checkReviews"],"controlReviews":review["controlReviews"],
        "criterionReviews":[{"id":"provenance","verdict":"pass","rationale":"Synthetic fixture membership, not source authentication.",
            "evidence":[{"pointer":"/originalSourceFiles/0/content","quote":"module.exports"}]}]});
    file(&base.join("fixture-accepted-response.json"), &accepted);
    let fixture = base.join("review-transport-fixture.py");
    fs::write(&fixture, r#"
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
repo,base,mode=sys.argv[1:];base=Path(base)
spec=importlib.util.spec_from_file_location('review_transport',Path(repo)/'scripts/run-source-suite-review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def put(path,value):path.write_text(json.dumps(value))
class FixtureParticipant:
    @staticmethod
    def process_budget_seconds(wall):return 420
    def __init__(self,evidence,state,binary,gateway,model,**kwargs):
        self.evidence=evidence;self.model=model;self.route=kwargs['route'];state.mkdir();(evidence/'gateway').mkdir()
        assert kwargs['api']=='openai-completions' and kwargs['response_format']=='json_object'
    def turn(self,label,workspace,**kwargs):
        assert label=='source-suite-review' and not list(workspace.iterdir())
        assert kwargs['transport_retry_limit']==0 and not kwargs['require_completed_tool_call']
        prompt=kwargs['prompt'];assert 'fixture-external-secret' not in prompt
        text=(base/'fixture-response.json').read_text() if mode in ('valid','citations') else 'not JSON'
        if mode=='accept':text=(base/'fixture-accepted-response.json').read_text()
        if mode=='reject':
            bad=json.loads((base/'fixture-response.json').read_text());bad['verdict']='reject'
            bad['criterionReviews'][0].update(verdict='fail',evidence=[dict(pointer='/originalSourceFiles/0/content',quote='module.exports')])
            text=json.dumps(bad)
        if mode=='citations':
            bad=json.loads(text);bad['checkReviews'][0]['sourceEvidence']=[dict(path='rawWorkerEvidence/2/content',quote='observed')]
            text=json.dumps(bad)
        (self.evidence/(label+'-prompt.txt')).write_text(prompt)
        put(self.evidence/'gateway/1.upstream-request.json',dict(model=self.model,providerId=self.route,stream=False,
            messages=[dict(role='user',content=prompt)]))
        raw=json.dumps(dict(choices=[dict(index=0,message=dict(role='assistant',content=text),finish_reason='stop')])).encode()
        (self.evidence/'gateway/1.response').write_bytes(raw)
        put(self.evidence/'gateway/1.status.json',dict(exchangeId='1',durationMs=1,status=200,upstreamEof=True,
            semanticComplete=True,outcome='completed',streamError=None,responseBytes=len(raw)))
        final=self.evidence/(label+'-final-assistant-message.json')
        put(final,dict(role='assistant',stopReason='stop',content=[dict(type='text',text=text)]))
        put(self.evidence/(label+'-lifecycle.json'),dict(label=label,captureAuthority='operator',exitCode=0,timedOut=False,
            finalAssistantMessagePresent=True,participantBudgetSeconds=420,participantBudgetScope='native-process-watchdog',
            transportRetryLimit=0,finalAssistantMessageSha256=hashlib.sha256(final.read_bytes()).hexdigest()))
        return dict(content=text)
args=argparse.Namespace(source=base/'transport-observations',rubric=base/'transport-rubric.json',output=base/('review-'+mode),
    gate=Path(os.environ['FIXTURE_NATIVE_GATE']),pi=Path('/fixture/pi'),gateway_timeout_seconds=240,
    thinking_type='disabled',reasoning_effort='default',max_output_tokens=16384)
module.run(args,participant_class=FixtureParticipant)
"#).unwrap();
    let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let invoke = |mode: &str| {
        Command::new("python3")
            .arg(&fixture)
            .arg(repo)
            .arg(&base)
            .arg(mode)
            .env(
                "FIXTURE_NATIVE_GATE",
                env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"),
            )
            .env(
                "AGENTLAB_PARTICIPANT_RUNTIME_CONFIG",
                base.join("fixture-runtime.json"),
            )
            .env(
                "AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT",
                base.join(format!("runtime-{mode}")),
            )
            .env("AGENTLAB_LM_GATEWAY_URL", "http://fixture.invalid")
            .env("AGENTLAB_LM_GATEWAY_KEY", "fixture-external-secret")
            .env("AGENTLAB_MODEL", "fixture")
            .env("AGENTLAB_PROVIDER_ROUTE", "fixture")
            .output()
            .unwrap()
    };
    let valid = invoke("valid");
    assert!(
        valid.status.success(),
        "{}",
        String::from_utf8_lossy(&valid.stderr)
    );
    let report: Value =
        serde_json::from_slice(&fs::read(base.join("review-valid/validation.json")).unwrap())
            .unwrap();
    assert_eq!(report["verdict"], "unverified");
    assert_eq!(report["recordedCompletionVerified"], true);
    assert_eq!(report["qualified"], false);
    let original = fs::read(base.join("review-valid/response.json")).unwrap();
    assert_eq!(
        original,
        fs::read(base.join("fixture-response.json")).unwrap()
    );
    assert!(!invoke("valid").status.success());
    assert_eq!(
        original,
        fs::read(base.join("review-valid/response.json")).unwrap()
    );
    assert!(!invoke("invalid").status.success());
    assert_eq!(
        fs::read(base.join("review-invalid/response.json")).unwrap(),
        b"not JSON"
    );
    let failed: Value = serde_json::from_slice(
        &fs::read(base.join("review-invalid/transport-receipt.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(failed["completed"], false);
    assert!(!base.join("review-invalid/validation.json").exists());
    assert!(!base.join("review-valid/lesson.json").exists());
    assert!(!invoke("citations").status.success());
    let diagnostic: Value = serde_json::from_slice(
        &fs::read(base.join("review-citations/citation-diagnostic.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(diagnostic["citationFindingCount"], 1);
    assert_eq!(diagnostic["diagnosticOnly"], true);
    assert_eq!(diagnostic["responseContentAccepted"], false);
    assert!(!base.join("review-citations/validation.json").exists());
    let export = |mode: &str, name: &str| {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--export-source-suite-review-feedback")
            .arg("--source")
            .arg(&observation)
            .arg("--quality-rubric")
            .arg(&rubric_path)
            .arg("--review-response")
            .arg(base.join(format!("review-{mode}/response.json")))
            .arg("--participant-evidence")
            .arg(base.join(format!("review-{mode}/evidence")))
            .arg("--output")
            .arg(base.join(name))
            .output()
            .unwrap()
    };
    for mode in ["valid", "invalid", "citations", "reject"] {
        if mode == "reject" {
            let rejected = invoke(mode);
            assert!(
                rejected.status.success(),
                "{}",
                String::from_utf8_lossy(&rejected.stderr)
            );
        }
        let name = format!("feedback-{mode}");
        assert!(!export(mode, &name).status.success());
        assert!(!base.join(name).exists());
    }
    let accepted_run = invoke("accept");
    assert!(
        accepted_run.status.success(),
        "{}",
        String::from_utf8_lossy(&accepted_run.stderr)
    );
    let exported = export("accept", "accepted-feedback");
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    let envelope = base.join("accepted-feedback");
    let original_accepted = fs::read(base.join("review-accept/response.json")).unwrap();
    assert_eq!(
        fs::read(envelope.join("original-response.json")).unwrap(),
        original_accepted
    );
    let receipt: Value =
        serde_json::from_slice(&fs::read(envelope.join("receipt.json")).unwrap()).unwrap();
    assert_eq!(
        receipt["originalResponseSha256"],
        digest(&original_accepted)
    );
    assert_eq!(
        receipt["completionSha256"],
        digest(&fs::read(envelope.join("completion.json")).unwrap())
    );
    assert_eq!(receipt["lessonCreated"], true);
    for key in [
        "qualified",
        "authorityWritePerformed",
        "automaticPromotion",
        "runtimeIsolationVerified",
        "learningBenefitVerified",
    ] {
        assert_eq!(receipt[key], false);
    }
    let lesson_bytes = fs::read(envelope.join("lesson-export/lesson-review.json")).unwrap();
    assert_eq!(
        serde_json::from_slice::<Value>(&lesson_bytes).unwrap(),
        accepted["lessonReview"]
    );
    assert_eq!(receipt["lessonReviewSha256"], digest(&lesson_bytes));
    // The ordinary downstream consumer reconstructs the same native format.
    agentlab_code_analysis::maintainer_observation_store::reconstructed_source_binding(
        &envelope.join("lesson-export"),
    )
    .unwrap();
    assert!(!export("accept", "accepted-feedback").status.success());
    assert_eq!(
        fs::read(envelope.join("original-response.json")).unwrap(),
        original_accepted
    );
    assert!(reviewer::export_accepted_feedback(
        &observation,
        &fs::read(&rubric_path).unwrap(),
        &base.join("review-accept/evidence"),
        &original_accepted,
        Some(&base),
        &base.join("unverified-git-feedback"),
    )
    .is_err());
    assert!(!base.join("unverified-git-feedback").exists());
    // An accepted content verdict cannot bypass changed wire or lifecycle gates.
    let status = base.join("review-accept/evidence/gateway/1.status.json");
    let original_status = fs::read(&status).unwrap();
    let mut changed: Value = serde_json::from_slice(&original_status).unwrap();
    changed["semanticComplete"] = json!(false);
    file(&status, &changed);
    assert!(!export("accept", "changed-wire-feedback").status.success());
    assert!(!base.join("changed-wire-feedback").exists());
    fs::write(&status, original_status).unwrap();
    let lifecycle = base.join("review-accept/evidence/source-suite-review-lifecycle.json");
    let mut changed: Value = serde_json::from_slice(&fs::read(&lifecycle).unwrap()).unwrap();
    changed["participantBudgetSeconds"] = json!(421);
    file(&lifecycle, &changed);
    assert!(!export("accept", "changed-budget-feedback").status.success());
    assert!(!base.join("changed-budget-feedback").exists());
    fs::remove_dir_all(base).unwrap();
}

#[test]
fn independent_review_response_retains_negative_feedback_without_promoting() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_wrong_count(2);
    let observation = base.join("response-observations");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let rubric = json!({"schema":"agentlab.prospective_source_quality_review.v1",
        "repositoryAgnostic":true,"frozenBeforeDispatch":true,"verdicts":["pass","fail","unverified"],
        "criteria":[{"id":"semantics","requirement":"Trace source.","evidence":"Original source."},
            {"id":"provenance","requirement":"Independent identity.","evidence":"Original capture."}]});
    let rubric_bytes = serde_json::to_vec(&rubric).unwrap();
    let packet = reviewer::prepare(&observation, &rubric_bytes).unwrap();
    let review = suite_lesson_review(&observation);
    let mut response = json!({"schema":"agentlab.independent_source_suite_review_response.v1",
        "reviewerId":review["reviewerId"],"reviewRequestSha256":digest(&serde_json::to_vec(&packet).unwrap()),
        "qualityRubricSha256":packet["qualityRubricSha256"],"reviewBindings":packet["reviewBindings"],
        "automaticPromotion":false,"verdict":"accept","unresolvedFindings":[],"lessonReview":review,
        "scenarioReviews":review["scenarioReviews"],"checkReviews":review["checkReviews"],"controlReviews":review["controlReviews"],
        "criterionReviews":[{"id":"semantics","verdict":"pass","rationale":"Fixture membership only.",
            "evidence":[{"pointer":"/originalSourceFiles/0/content","quote":"module.exports"}]},
            {"id":"provenance","verdict":"pass","rationale":"Fixture, not real authentication.",
            "evidence":[{"pointer":"/originalSourceFiles/0/content","quote":"module.exports"}]}]});
    let validate = |r: &Value| {
        reviewer::validate_response(&observation, &rubric_bytes, &serde_json::to_vec(r).unwrap())
    };
    let accepted = validate(&response).unwrap();
    assert_eq!(accepted["verdict"], "accept");
    assert_eq!(accepted["lessonContentVerified"], true);
    assert_eq!(accepted["reviewerExecuted"], false);
    assert_eq!(accepted["quotationClaimSupportVerified"], false);
    assert_eq!(accepted["qualified"], false);
    for (key, alias) in [
        ("scenarioReviews", "scenarioId"),
        ("checkReviews", "checkId"),
        ("controlReviews", "controlId"),
    ] {
        let mut aliased = response.clone();
        let row = aliased[key][0].as_object_mut().unwrap();
        let id = row.remove("id").unwrap();
        row.insert(alias.into(), id);
        let error = validate(&aliased).unwrap_err();
        assert!(error.contains(&format!("/{key}/0/id")), "{error}");
    }
    let mut nested_alias = response.clone();
    let row = nested_alias["lessonReview"]["controlReviews"][0]
        .as_object_mut()
        .unwrap();
    let id = row.remove("id").unwrap();
    row.insert("controlId".into(), id);
    assert!(validate(&nested_alias)
        .unwrap_err()
        .contains("lesson inventory"));
    let clean_diagnostic = reviewer::diagnose_citations(
        &observation,
        &rubric_bytes,
        &serde_json::to_vec(&response).unwrap(),
    )
    .unwrap();
    assert_eq!(clean_diagnostic["citationFindingCount"], 0);
    assert_eq!(clean_diagnostic["responseContentAccepted"], false);
    assert_eq!(clean_diagnostic["fullResponseValidationPerformed"], false);
    let prompt = String::from_utf8(reviewer::prompt(&observation, &rubric_bytes).unwrap()).unwrap();
    let catalog: Value = serde_json::from_str(
        prompt
            .split("judgments):\n")
            .nth(1)
            .unwrap()
            .split("\nORIGINAL REVIEW REQUEST:\n")
            .next()
            .unwrap(),
    )
    .unwrap();
    for entry in catalog.as_array().unwrap() {
        let pointer = entry["pointer"].as_str().unwrap();
        assert!(packet.pointer(pointer).unwrap().is_string());
    }
    assert!(catalog
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["path"] == "unit.js" && e["pointer"] == "/originalSourceFiles/0/content"));
    let mut nonstring = response.clone();
    nonstring["criterionReviews"][0]["evidence"][0] =
        json!({"pointer":"/rubricFreezeAuthenticated","quote":"false"});
    let error = validate(&nonstring).unwrap_err();
    assert!(
        error.contains("/criterionReviews/0/evidence/0")
            && error.contains("/rubricFreezeAuthenticated")
    );
    nonstring["checkReviews"][0]["sourceEvidence"][0]["path"] =
        json!("rawWorkerEvidence/2/content");
    let diagnosed = reviewer::diagnose_citations(
        &observation,
        &rubric_bytes,
        &serde_json::to_vec(&nonstring).unwrap(),
    )
    .unwrap();
    assert_eq!(diagnosed["citationFindingCount"], 2);
    assert_eq!(
        diagnosed["citationFindings"][0]["responsePointer"],
        "/criterionReviews/0/evidence/0"
    );
    assert_eq!(
        diagnosed["citationFindings"][1]["responsePointer"],
        "/checkReviews/0/sourceEvidence/0"
    );
    assert_eq!(diagnosed["fullResponseValidationPerformed"], false);
    assert_eq!(diagnosed["qualified"], false);
    let mut drifted = nonstring.clone();
    drifted["reviewRequestSha256"] = json!("different");
    assert!(reviewer::diagnose_citations(
        &observation,
        &rubric_bytes,
        &serde_json::to_vec(&drifted).unwrap()
    )
    .is_err());
    for change in [
        "binding",
        "rubric",
        "duplicate",
        "missing",
        "quote",
        "pointer",
        "lesson",
        "finding",
        "promotion",
        "extra",
    ] {
        let mut bad = response.clone();
        match change {
            "binding" => bad["reviewRequestSha256"] = json!("wrong"),
            "rubric" => bad["qualityRubricSha256"] = json!("wrong"),
            "duplicate" => {
                let row = bad["criterionReviews"][0].clone();
                bad["criterionReviews"].as_array_mut().unwrap().push(row);
            }
            "missing" => {
                bad["checkReviews"].as_array_mut().unwrap().pop();
            }
            "quote" => {
                bad["criterionReviews"][0]["evidence"][0]["quote"] = json!("fabricated evidence")
            }
            "pointer" => bad["criterionReviews"][0]["evidence"][0]["pointer"] = json!("/absent"),
            "lesson" => bad["lessonReview"]["reviewerId"] = json!("other"),
            "finding" => bad["unresolvedFindings"] = json!(["Unresolved contradiction"]),
            "promotion" => bad["automaticPromotion"] = json!(true),
            "extra" => bad["qualified"] = json!(true),
            _ => unreachable!(),
        }
        assert!(validate(&bad).is_err(), "{change}");
    }
    response["criterionReviews"][1]["verdict"] = json!("unverified");
    response["criterionReviews"][1]["evidence"] = json!([]);
    response["verdict"] = json!("unverified");
    response["lessonReview"] = Value::Null;
    response["unresolvedFindings"] = json!(["Independent source authentication missing."]);
    assert_eq!(validate(&response).unwrap()["verdict"], "unverified");
    let mut contradiction = response.clone();
    contradiction["verdict"] = json!("accept");
    assert!(validate(&contradiction).is_err());
    response["checkReviews"][0]["accepted"] = json!(false);
    response["verdict"] = json!("reject");
    let rejected = validate(&response).unwrap();
    assert_eq!(rejected["lessonContentVerified"], false);
    response["lessonReview"] = review.clone();
    assert!(validate(&response).is_err());
    response["lessonReview"] = Value::Null;
    response["checkReviews"][0]["accepted"] = Value::Null;
    response["checkReviews"][0]["sourceEvidence"] = json!([]);
    response["verdict"] = json!("unverified");
    assert!(validate(&response).is_ok());
    let mut absent = response.clone();
    absent["checkReviews"][0]
        .as_object_mut()
        .unwrap()
        .remove("accepted");
    assert!(validate(&absent).is_err());
    let rubric_file = base.join("review-rubric.json");
    let response_file = base.join("review-response.json");
    let output = base.join("validated-response.json");
    file(&rubric_file, &rubric);
    file(&response_file, &response);
    let invoke = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args(["--validate-source-suite-review-response", "--source"])
            .arg(&observation)
            .arg("--quality-rubric")
            .arg(&rubric_file)
            .arg("--review-response")
            .arg(&response_file)
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap()
    };
    let result = invoke();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&output).unwrap()).unwrap(),
        validate(&response).unwrap()
    );
    let retained = fs::read(&output).unwrap();
    assert!(!invoke().status.success());
    assert_eq!(fs::read(&output).unwrap(), retained);
    assert!(!observation.join("review.json").exists());
    // Synthetic transport exercises native gates; this is not a real reviewer run.
    let evidence = base.join("review-participant");
    fs::create_dir_all(evidence.join("gateway")).unwrap();
    let prompt = reviewer::prompt(&observation, &rubric_bytes).unwrap();
    fs::write(evidence.join("source-suite-review-prompt.txt"), &prompt).unwrap();
    let intent = json!({"schema":"agentlab.independent_source_suite_review_intent.v1",
        "reviewRequestSha256":packet["reviewBindings"]["requestSha256"],
        "qualityRubricSha256":packet["qualityRubricSha256"],"promptSha256":digest(&prompt),
        "participantBudgetSeconds":420,"transportRetryLimit":0,
        "participantIdentity":{"model":"fixture","providerRoute":"fixture","providerReasoningEffort":null}});
    let mut intent = intent;
    intent["reviewRequestSha256"] = json!(digest(&serde_json::to_vec(&packet).unwrap()));
    file(&evidence.join("review-intent.json"), &intent);
    let wire = json!({"model":"fixture","providerId":"fixture","stream":true,
        "messages":[{"role":"system","content":"Fixture adapter."},{"role":"user","content":String::from_utf8(prompt).unwrap()}]});
    file(&evidence.join("gateway/1.upstream-request.json"), &wire);
    let response_text = serde_json::to_string(&response).unwrap();
    let upstream = format!(
        "data: {}\n\ndata: [DONE]\n\n",
        json!({"choices":[{"index":0,"delta":{"content":response_text},"finish_reason":"stop"}]})
    );
    fs::write(evidence.join("gateway/1.response"), &upstream).unwrap();
    let status = json!({"exchangeId":"1","durationMs":1,"status":200,"upstreamEof":true,
        "semanticComplete":true,"outcome":"completed","streamError":null,"responseBytes":upstream.len()});
    file(&evidence.join("gateway/1.status.json"), &status);
    let final_message = json!({"role":"assistant","stopReason":"stop","content":[{"type":"text","text":response_text}]});
    file(
        &evidence.join("source-suite-review-final-assistant-message.json"),
        &final_message,
    );
    let lifecycle = json!({"label":"source-suite-review","captureAuthority":"operator","exitCode":0,
        "timedOut":false,"finalAssistantMessagePresent":true,"participantBudgetSeconds":420,
        "participantBudgetScope":"native-process-watchdog","transportRetryLimit":0,
        "finalAssistantMessageSha256":digest(&fs::read(evidence.join("source-suite-review-final-assistant-message.json")).unwrap())});
    file(
        &evidence.join("source-suite-review-lifecycle.json"),
        &lifecycle,
    );
    let complete = || {
        reviewer::verify_completion(
            &observation,
            &rubric_bytes,
            &evidence,
            &serde_json::to_vec(&response).unwrap(),
        )
    };
    let completed = complete().unwrap();
    assert_eq!(completed["recordedCompletionVerified"], true);
    assert_eq!(completed["verdict"], "unverified");
    assert_eq!(completed["reviewerAuthenticated"], false);
    assert_eq!(completed["qualified"], false);
    let completion_output = base.join("review-completion.json");
    let cli = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .args(["--verify-source-suite-review-completion", "--source"])
        .arg(&observation)
        .arg("--quality-rubric")
        .arg(&rubric_file)
        .arg("--review-response")
        .arg(&response_file)
        .arg("--participant-evidence")
        .arg(&evidence)
        .arg("--output")
        .arg(&completion_output)
        .output()
        .unwrap();
    assert!(
        cli.status.success(),
        "{}",
        String::from_utf8_lossy(&cli.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&completion_output).unwrap()).unwrap(),
        completed
    );
    for change in [
        "truncated",
        "context",
        "budget",
        "edited-final",
        "incomplete",
        "retry",
        "tool",
    ] {
        match change {
            "truncated" => {
                let changed = upstream.replace("\"stop\"", "\"length\"");
                fs::write(evidence.join("gateway/1.response"), &changed).unwrap();
                let mut changed_status = status.clone();
                changed_status["responseBytes"] = json!(changed.len());
                file(&evidence.join("gateway/1.status.json"), &changed_status);
            }
            "context" => {
                let mut v = wire.clone();
                v["messages"]
                    .as_array_mut()
                    .unwrap()
                    .push(json!({"role":"assistant","content":"Prior constructor answer"}));
                file(&evidence.join("gateway/1.upstream-request.json"), &v);
            }
            "budget" => {
                let mut v = lifecycle.clone();
                v["participantBudgetSeconds"] = json!(300);
                file(&evidence.join("source-suite-review-lifecycle.json"), &v);
            }
            "edited-final" => {
                let mut v = final_message.clone();
                v["content"][0]["text"] = json!("{}");
                file(
                    &evidence.join("source-suite-review-final-assistant-message.json"),
                    &v,
                );
                let mut l = lifecycle.clone();
                l["finalAssistantMessageSha256"] = json!(digest(
                    &fs::read(evidence.join("source-suite-review-final-assistant-message.json"))
                        .unwrap()
                ));
                file(&evidence.join("source-suite-review-lifecycle.json"), &l);
            }
            "incomplete" => {
                let mut v = status.clone();
                v["semanticComplete"] = json!(false);
                file(&evidence.join("gateway/1.status.json"), &v);
            }
            "retry" => file(
                &evidence.join("source-suite-review-transport-retry.json"),
                &json!({}),
            ),
            "tool" => {
                let changed = format!(
                    "data: {}\n\ndata: [DONE]\n\n",
                    json!({"choices":[{"index":0,"delta":{"content":response_text,"tool_calls":[]},"finish_reason":"stop"}]})
                );
                fs::write(evidence.join("gateway/1.response"), &changed).unwrap();
                let mut v = status.clone();
                v["responseBytes"] = json!(changed.len());
                file(&evidence.join("gateway/1.status.json"), &v);
            }
            _ => unreachable!(),
        }
        assert!(complete().is_err(), "{change}");
        fs::write(evidence.join("gateway/1.response"), &upstream).unwrap();
        file(&evidence.join("gateway/1.upstream-request.json"), &wire);
        file(&evidence.join("gateway/1.status.json"), &status);
        file(
            &evidence.join("source-suite-review-final-assistant-message.json"),
            &final_message,
        );
        file(
            &evidence.join("source-suite-review-lifecycle.json"),
            &lifecycle,
        );
        if evidence
            .join("source-suite-review-transport-retry.json")
            .exists()
        {
            fs::remove_file(evidence.join("source-suite-review-transport-retry.json")).unwrap();
        }
    }
    assert!(complete().is_ok());
    fs::remove_dir_all(base).unwrap();
}

#[test]
fn independent_review_request_reconstructs_originals_and_never_preapproves() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_wrong_count(2);
    let observation = base.join("review-observations");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let rubric = json!({"schema":"agentlab.prospective_source_quality_review.v1",
        "repositoryAgnostic":true,"frozenBeforeDispatch":true,"verdicts":["pass","fail","unverified"],
        "criteria":[{"id":"independent-semantics","requirement":"Trace original source and expected behavior.","evidence":"Complete source and raw controls."}]});
    let rubric_bytes = serde_json::to_vec(&rubric).unwrap();
    let packet = reviewer::prepare(&observation, &rubric_bytes).unwrap();
    let original_request: Value =
        serde_json::from_slice(&fs::read(observation.join("source-stage/request.json")).unwrap())
            .unwrap();
    assert_eq!(packet["source"], original_request["source"]);
    assert_eq!(
        packet["originalSourceFiles"],
        original_request["sourceFiles"]
    );
    assert_eq!(packet["qualityRubricSha256"], digest(&rubric_bytes));
    assert_eq!(packet["reviewPreparedOnly"], true);
    assert_eq!(packet["reviewerExecuted"], false);
    assert_eq!(packet["semanticQualified"], false);
    assert_eq!(packet["reviewed"], false);
    assert_eq!(packet["authorityWritePerformed"], false);
    assert_eq!(
        packet["reconstructedSuite"]["acceptedReferenceRecoveryReconstructed"],
        true
    );
    assert!(!packet["rawWorkerEvidence"].as_array().unwrap().is_empty());
    assert!(packet.get("maintainerGuidance").is_none());
    let input = base.join("rubric.json");
    file(&input, &rubric);
    let output = base.join("independent-request.json");
    let invoke = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--prepare-source-suite-review")
            .arg("--source")
            .arg(&observation)
            .arg("--quality-rubric")
            .arg(&input)
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap()
    };
    let result = invoke();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&output).unwrap()).unwrap(),
        packet
    );
    let retained = fs::read(&output).unwrap();
    assert!(!invoke().status.success());
    assert_eq!(fs::read(&output).unwrap(), retained);
    for change in ["duplicate", "missing", "verdict", "specific"] {
        let mut bad = rubric.clone();
        match change {
            "duplicate" => {
                let row = bad["criteria"][0].clone();
                bad["criteria"].as_array_mut().unwrap().push(row);
            }
            "missing" => {
                bad["criteria"][0]
                    .as_object_mut()
                    .unwrap()
                    .remove("evidence");
            }
            "verdict" => bad["verdicts"] = json!(["pass", "fail"]),
            "specific" => bad["repositoryAgnostic"] = json!(false),
            _ => unreachable!(),
        }
        assert!(
            reviewer::prepare(&observation, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "{change}"
        );
    }
    let reviewed = base.join("already-reviewed");
    lesson::export(
        &base.join("stage"),
        &base.join("suite"),
        Some(&serde_json::to_vec(&suite_lesson_review(&observation)).unwrap()),
        &reviewed,
    )
    .unwrap();
    assert!(reviewer::prepare(&reviewed, &rubric_bytes)
        .unwrap_err()
        .contains("without a prior lesson review"));
    let checks_path = observation.join("checks.jsonl");
    let mut checks: Vec<Value> = fs::read_to_string(&checks_path)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    checks[0]["passed"] = json!(!checks[0]["passed"].as_bool().unwrap());
    let raw = checks
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    fs::write(&checks_path, &raw).unwrap();
    let manifest_path = observation.join("export.json");
    let mut manifest: Value = serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
    manifest["tables"]["checks"]["sha256"] = json!(digest(raw.as_bytes()));
    file(&manifest_path, &manifest);
    assert!(reviewer::prepare(&observation, &rubric_bytes)
        .unwrap_err()
        .contains("raw reconstruction"));
    fs::remove_dir_all(base).unwrap();
}

#[test]
fn source_suite_import_reconstructs_observations_lessons_and_historical_projection() {
    use agentlab_code_analysis::{
        maintainer_observation_store as store, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_wrong_count(2);
    let observation = base.join("import-observation");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let review = serde_json::to_vec(&suite_lesson_review(&observation)).unwrap();
    let reviewed = base.join("import-reviewed");
    lesson::export(
        &base.join("stage"),
        &base.join("suite"),
        Some(&review),
        &reviewed,
    )
    .unwrap();
    // Model an older analyzer without changing any original capture bytes.
    let historical = lesson::assets(&reviewed, Some(&review), Some(&"c".repeat(64))).unwrap();
    agentlab_code_analysis::asset_exchange::export(&reviewed, "evaluation-instance", &historical);
    let destination = json!({"schema":"agentlab.observation_store_destination.v1","reviewed":true,
        "automaticPromotion":false,"repository":"operation","knowledgeRepository":"knowledge",
        "expectedRevision":"a".repeat(40),"tablePrefix":"data/","transactionId":"a1122026-1003-4a11-8811-221190128101"});
    for (export, has_lesson) in [(&observation, false), (&reviewed, true)] {
        let manifest: Value =
            serde_json::from_slice(&fs::read(export.join("export.json")).unwrap()).unwrap();
        let tables: serde_json::Map<String, Value> = manifest["tables"]
            .as_object()
            .unwrap()
            .keys()
            .map(|name| {
                (
                    name.clone(),
                    json!({"revision":"a".repeat(40),"dirty":false,"truncated":false,"rows":[]}),
                )
            })
            .collect();
        let baseline = json!({"schema":"agentlab.observation_store_snapshot.v1","repository":"operation",
            "revision":"a".repeat(40),"tablePrefix":"data/","tables":tables});
        let encode = |v: &Value| serde_json::to_vec(v).unwrap();
        let planned = store::plan(export, &encode(&baseline), &encode(&destination)).unwrap();
        assert_eq!(planned["source"]["captureKind"], "source-suite");
        assert_eq!(
            planned["expectedTables"]
                .get("experiment_lessons")
                .is_some(),
            has_lesson
        );
        if has_lesson {
            assert_eq!(
                planned["source"]["projectionRevalidation"]["declaredOriginalConsumerSha256"],
                "c".repeat(64)
            );
            assert_eq!(
                planned["expectedTables"]["analysis_records"],
                serde_json::to_value(&historical["analysis_records"]).unwrap()
            );
        }
        let after_tables: serde_json::Map<String, Value> = planned["expectedTables"].as_object().unwrap().iter()
            .map(|(name, rows)| (name.clone(), json!({"revision":"e".repeat(40),"dirty":false,"truncated":false,
                "rows":rows.as_object().unwrap().iter().map(|(key,row)|json!({"key":key,"row":row})).collect::<Vec<_>>()}))).collect();
        let after = json!({"schema":"agentlab.observation_store_snapshot.v1","repository":"operation",
            "revision":"e".repeat(40),"tablePrefix":"data/","tables":after_tables});
        let receipt = json!({"repo":"operation","revision":"e".repeat(40),"previous_revision":"a".repeat(40),"outcome":"applied","conflicts":[]});
        let verified = store::verify(
            export,
            &encode(&planned),
            &encode(&receipt),
            &encode(&after),
            &encode(&baseline),
        )
        .unwrap();
        assert_eq!(verified["allRowsExact"], true);
        assert_eq!(verified["remoteRawBytesPreserved"], false);
        let mut next = destination.clone();
        next["expectedRevision"] = receipt["revision"].clone();
        assert!(
            store::plan(export, &encode(&after), &encode(&next)).unwrap()["transaction"].is_null()
        );
        // Even rehashed rows must match reconstruction of original evidence.
        let row_path = export.join("runs.jsonl");
        let original = fs::read(&row_path).unwrap();
        let mut row: Value = serde_json::from_slice(&original).unwrap();
        row["qualified"] = json!(true);
        let forged = encode(&row);
        fs::write(&row_path, &forged).unwrap();
        let mut rehashed = manifest.clone();
        rehashed["tables"]["runs"]["sha256"] = json!(digest(&forged));
        file(&export.join("export.json"), &rehashed);
        assert!(
            store::plan(export, &encode(&baseline), &encode(&destination))
                .unwrap_err()
                .contains("raw reconstruction")
        );
        fs::write(&row_path, &original).unwrap();
        file(&export.join("export.json"), &manifest);
        if has_lesson {
            let review_path = export.join("lesson-review.json");
            let retained = fs::read(&review_path).unwrap();
            fs::remove_file(&review_path).unwrap();
            assert!(store::plan(export, &encode(&baseline), &encode(&destination)).is_err());
            let mut unresolved: Value = serde_json::from_slice(&retained).unwrap();
            unresolved["unresolvedFindings"] = json!(["remaining semantic gap"]);
            file(&review_path, &unresolved);
            assert!(store::plan(export, &encode(&baseline), &encode(&destination)).is_err());
            fs::write(&review_path, &retained).unwrap();
        }
        fs::write(export.join("behavior-contract.json"), b"{}").unwrap();
        assert!(
            store::plan(export, &encode(&baseline), &encode(&destination))
                .unwrap_err()
                .contains("formats ambiguous")
        );
        fs::remove_file(export.join("behavior-contract.json")).unwrap();
        let raw = export.join("source-stage/controls.cjs");
        fs::write(&raw, b"forged verifier").unwrap();
        assert!(store::plan(export, &encode(&baseline), &encode(&destination)).is_err());
    }
}

#[test]
fn source_suite_raw_archive_recovers_exact_export_and_rejects_partial_or_changed_chunks() {
    use agentlab_code_analysis::{
        maintainer_observation_store as store, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_wrong_count(2);
    let source = base.join("archive-source");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &source).unwrap();
    fs::write(source.join("unowned-private-home"), b"must not be archived").unwrap();
    let descriptor = store::archive_descriptor(&source).unwrap();
    let encode = |v: &Value| serde_json::to_vec(v).unwrap();
    let manifest: Value =
        serde_json::from_slice(&fs::read(source.join("export.json")).unwrap()).unwrap();
    let mut tables: serde_json::Map<String, Value> = manifest["tables"]
        .as_object()
        .unwrap()
        .keys()
        .map(|name| {
            (
                name.clone(),
                json!({"revision":"a".repeat(40),"dirty":false,"truncated":false,"rows":[]}),
            )
        })
        .collect();
    tables.insert(
        "raw_archive_chunks".into(),
        json!({"revision":"a".repeat(40),"dirty":false,"truncated":false,"rows":[]}),
    );
    let baseline = json!({"schema":"agentlab.observation_store_snapshot.v1","repository":"operation","revision":"a".repeat(40),"tablePrefix":"data/","tables":tables});
    let dest = json!({"schema":"agentlab.observation_store_destination.v1","reviewed":true,"automaticPromotion":false,"preserveRawFiles":true,"repository":"operation","knowledgeRepository":"knowledge","expectedRevision":"a".repeat(40),"tablePrefix":"data/","transactionId":"a1122026-1003-4a11-8811-221190128101"});
    let planned = store::plan(&source, &encode(&baseline), &encode(&dest)).unwrap();
    assert_eq!(planned["source"]["rawArchive"], descriptor["rawArchive"]);
    assert_eq!(
        planned,
        store::plan(&source, &encode(&baseline), &encode(&dest)).unwrap()
    );
    let after_tables:serde_json::Map<String,Value>=planned["expectedTables"].as_object().unwrap().iter().map(|(name,rows)|(name.clone(),json!({"revision":"e".repeat(40),"dirty":false,"truncated":false,"rows":rows.as_object().unwrap().iter().map(|(key,row)|json!({"key":key,"row":row})).collect::<Vec<_>>()}))).collect();
    let after = json!({"schema":"agentlab.observation_store_snapshot.v1","repository":"operation","revision":"e".repeat(40),"tablePrefix":"data/","tables":after_tables});
    let receipt = json!({"repo":"operation","revision":"e".repeat(40),"previous_revision":"a".repeat(40),"outcome":"applied","conflicts":[]});
    assert_eq!(
        store::verify(
            &source,
            &encode(&planned),
            &encode(&receipt),
            &encode(&after),
            &encode(&baseline)
        )
        .unwrap()["remoteRawBytesPreserved"],
        true
    );
    let out = base.join("recovered-export");
    let recovery = store::recover(&encode(&planned), &encode(&after), &out).unwrap();
    assert_eq!(recovery["allFileBytesVerified"], true);
    for entry in descriptor["rawArchive"]["files"].as_array().unwrap() {
        let name = entry["path"].as_str().unwrap();
        assert_eq!(
            fs::read(source.join(name)).unwrap(),
            fs::read(out.join(name)).unwrap()
        );
    }
    assert!(!out.join("unowned-private-home").exists());
    let bound = base.join("bound-export");
    let bound_report = store::bind_committed_export(
        &out,
        &encode(&planned),
        &encode(&receipt),
        &encode(&after),
        &encode(&baseline),
        &bound,
    )
    .unwrap();
    assert_eq!(bound_report["revision"], receipt["revision"]);
    assert_eq!(
        fs::read(bound.join("original-export.json")).unwrap(),
        fs::read(source.join("export.json")).unwrap()
    );
    let bound_manifest: Value =
        serde_json::from_slice(&fs::read(bound.join("export.json")).unwrap()).unwrap();
    assert_eq!(bound_manifest["repository"], "operation");
    assert_eq!(bound_manifest["revision"], receipt["revision"]);
    assert_eq!(bound_manifest["tablePrefix"], "data/");
    assert_eq!(bound_manifest["tables"], manifest["tables"]);
    for name in manifest["tables"].as_object().unwrap().keys() {
        assert_eq!(
            fs::read(bound.join(format!("{name}.jsonl"))).unwrap(),
            fs::read(source.join(format!("{name}.jsonl"))).unwrap()
        );
    }
    let mut invalid_receipt = receipt.clone();
    invalid_receipt["revision"] = json!("f".repeat(40));
    let rejected = base.join("rejected-bound-export");
    assert!(store::bind_committed_export(
        &out,
        &encode(&planned),
        &encode(&invalid_receipt),
        &encode(&after),
        &encode(&baseline),
        &rejected
    )
    .is_err());
    assert!(!rejected.exists());
    assert_eq!(
        planned,
        store::plan(&out, &encode(&baseline), &encode(&dest)).unwrap()
    );
    assert!(store::recover(&encode(&planned), &encode(&after), &out).is_err());
    let mut next = dest.clone();
    next["expectedRevision"] = receipt["revision"].clone();
    assert!(store::plan(&out, &encode(&after), &encode(&next)).unwrap()["transaction"].is_null());
    for mode in ["missing", "changed", "ordinal", "dirty"] {
        let mut bad = after.clone();
        match mode {
            "missing" => {
                bad["tables"]["raw_archive_chunks"]["rows"]
                    .as_array_mut()
                    .unwrap()
                    .pop();
            }
            "changed" => bad["tables"]["raw_archive_chunks"]["rows"][0]["row"]["hex"] = json!("00"),
            "ordinal" => {
                bad["tables"]["raw_archive_chunks"]["rows"][0]["row"]["ordinal"] = json!(999)
            }
            _ => bad["tables"]["raw_archive_chunks"]["dirty"] = json!(true),
        }
        let rejected = base.join(format!("reject-{mode}"));
        assert!(store::recover(&encode(&planned), &encode(&bad), &rejected).is_err());
        assert!(!rejected.exists());
    }
}

#[test]
fn source_suite_observation_and_reviewed_lesson_preserve_original_evidence() {
    use agentlab_code_analysis::maintainer_source_suite_lesson as lesson;
    let base = suite_fixture_with_wrong_count(2);
    let observation = base.join("observation");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    assert!(!observation.join("experiment_lessons.jsonl").exists());
    assert_eq!(
        fs::read(observation.join("source-stage/controls.cjs")).unwrap(),
        fs::read(base.join("stage/controls.cjs")).unwrap()
    );
    let review = suite_lesson_review(&observation);
    let review_bytes = serde_json::to_vec(&review).unwrap();
    file(&base.join("review.json"), &review);
    let exported = base.join("lesson");
    let result = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .arg("--export-source-suite-lesson")
        .arg("--stage")
        .arg(base.join("stage"))
        .arg("--suite")
        .arg(base.join("suite"))
        .arg("--lesson-review")
        .arg(base.join("review.json"))
        .arg("--output")
        .arg(&exported)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let tables = lesson::assets(&exported, Some(&review_bytes), None).unwrap();
    assert_eq!(tables["calibration_controls"].len(), 6);
    assert_eq!(tables["checks"].len(), 12);
    assert_eq!(
        tables["experiment_lessons"]["suite-lesson"]["promotionContract"]["qualification"]
            ["learningBenefitVerified"],
        false
    );
    assert_eq!(
        tables["experiment_lessons"]["suite-lesson"]["promotionContract"]["qualification"]
            ["caseQualified"],
        false
    );
    assert_eq!(
        lesson::assets(
            &exported,
            Some(&review_bytes),
            Some(&lesson::current_consumer_digest())
        )
        .unwrap(),
        tables
    );
    assert!(lesson::export(
        &base.join("stage"),
        &base.join("suite"),
        Some(&review_bytes),
        &exported
    )
    .is_err());
    for change in [
        "unresolved",
        "omission",
        "quote",
        "exercise",
        "binding",
        "rejected",
        "promotion",
    ] {
        let mut bad = review.clone();
        match change {
            "unresolved" => bad["unresolvedFindings"] = json!(["unexercised branch"]),
            "omission" => {
                bad["checkReviews"].as_array_mut().unwrap().pop();
            }
            "quote" => {
                bad["controlReviews"][0]["sourceEvidence"][0]["quote"] = json!("invented source")
            }
            "exercise" => bad["controlReviews"][1]["exercisedByScenarioIds"] = json!([]),
            "binding" => bad["proposalSha256"] = json!("f".repeat(64)),
            "rejected" => bad["scenarioReviews"][0]["accepted"] = json!(false),
            "promotion" => bad["automaticPromotion"] = json!(true),
            _ => unreachable!(),
        }
        assert!(
            lesson::assets(&exported, Some(&serde_json::to_vec(&bad).unwrap()), None).is_err(),
            "{change}"
        );
    }
    let capture = exported.join("source-suite/control-0/contained-input-fixture/worker-stdout.log");
    fs::write(capture, b"{}").unwrap();
    assert!(lesson::assets(&exported, Some(&review_bytes), None).is_err());
    let one = suite_fixture();
    let one_out = one.join("observation");
    lesson::export(&one.join("stage"), &one.join("suite"), None, &one_out).unwrap();
    assert!(lesson::assets(
        &one_out,
        Some(&serde_json::to_vec(&suite_lesson_review(&one_out)).unwrap()),
        None
    )
    .is_err());
    let duplicate = suite_fixture_with_wrong_count(3);
    let duplicate_out = duplicate.join("observation");
    lesson::export(
        &duplicate.join("stage"),
        &duplicate.join("suite"),
        None,
        &duplicate_out,
    )
    .unwrap();
    assert!(lesson::assets(
        &duplicate_out,
        Some(&serde_json::to_vec(&suite_lesson_review(&duplicate_out)).unwrap()),
        None
    )
    .unwrap_err()
    .contains("duplicate source variant"));
    #[cfg(unix)]
    {
        let alias = base.join("output-alias");
        std::os::unix::fs::symlink(&base, &alias).unwrap();
        assert!(lesson::export(
            &base.join("stage"),
            &base.join("suite"),
            None,
            &alias.join("must-not-exist")
        )
        .is_err());
        assert!(!base.join("must-not-exist").exists());
    }
}

#[test]
fn source_suite_lesson_uses_existing_promotion_and_native_admission_without_authority_write() {
    use agentlab_code_analysis::maintainer_source_suite_lesson as lesson;
    let base = suite_fixture_with_wrong_count(2);
    let observation = base.join("observation");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let review = suite_lesson_review(&observation);
    let exported = base.join("lesson");
    lesson::export(
        &base.join("stage"),
        &base.join("suite"),
        Some(&serde_json::to_vec(&review).unwrap()),
        &exported,
    )
    .unwrap();
    // Synthetic committed metadata exercises reconstruction, not a remote write.
    let mut export: Value =
        serde_json::from_slice(&fs::read(exported.join("export.json")).unwrap()).unwrap();
    export["repository"] = json!("fixture-operation");
    export["revision"] = json!("e".repeat(40));
    export["tablePrefix"] = json!("data/");
    file(&exported.join("export.json"), &export);
    let knowledge = base.join("knowledge");
    fs::create_dir(&knowledge).unwrap();
    for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        fs::write(knowledge.join(format!("{name}.jsonl")), b"").unwrap();
    }
    let promoted = base.join("promoted");
    let output = Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
        .env("GITHUB_SHA", "e".repeat(40))
        .arg("promote")
        .arg(&exported)
        .arg(&knowledge)
        .arg(&promoted)
        .arg("suite-lesson")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(fs::read(promoted.join("evaluation_cases.jsonl"))
        .unwrap()
        .is_empty());
    let baseline = base.join("baseline");
    fs::create_dir(&baseline).unwrap();
    let mut cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1","tableGitAuthority":{"repo":"fixture-knowledge","revision":"a".repeat(40)},"tables":{}});
    let mut round = json!({"id":"initial","roundIndex":1,"ownershipPlane":"target-operations","automaticPromotion":false,
        "coverage":{"processSkillCount":0},"tables":{},"assessment":{"path":"fixture-assessment.json","sha256":"d".repeat(64)}});
    for (key, table, round_key) in [
        (
            "maintainerSkills",
            "maintainer_skills",
            "processSkillsSha256",
        ),
        ("programFacts", "program_facts", "programFactsSha256"),
        (
            "maintainerScopeSkills",
            "maintainer_scope_skills",
            "scopeSkillsSha256",
        ),
        ("evaluationCases", "evaluation_cases", ""),
    ] {
        let bytes = if table == "maintainer_scope_skills" {
            fs::read(exported.join("candidate.json")).unwrap()
        } else {
            Vec::new()
        };
        fs::write(baseline.join(format!("{table}.jsonl")), &bytes).unwrap();
        cut["tables"][key] = json!({"path":format!("{table}.jsonl"),"sha256":digest(&bytes)});
        if !round_key.is_empty() {
            round["tables"][round_key] = json!(digest(&bytes));
        }
    }
    let history = serde_json::to_vec(&round).unwrap();
    fs::write(
        baseline.join("maintainer_skill_refresh_rounds.jsonl"),
        &history,
    )
    .unwrap();
    cut["tables"]["maintainerSkillRefreshRounds"] =
        json!({"path":"maintainer_skill_refresh_rounds.jsonl","sha256":digest(&history)});
    file(&baseline.join("maintainer-knowledge-cut.json"), &cut);
    let prepare = || {
        agentlab_code_analysis::maintainer_lesson_admission::prepare(
            &baseline,
            &promoted,
            &exported,
            "suite-lesson",
            &"a".repeat(40),
        )
    };
    let plan = prepare().unwrap();
    assert_eq!(plan["authorityWritePerformed"], false);
    assert_eq!(
        plan["projectionRevalidation"]["currentSemanticReconstructionRequired"],
        true
    );
    assert_eq!(
        plan["tables"]["maintainer_skills"]["row"]["stage"],
        "calibration"
    );
    assert_eq!(plan["tables"].as_object().unwrap().len(), 3);
    let review_path = exported.join("lesson-review.json");
    let mut bad = review;
    bad["unresolvedFindings"] = json!(["unexercised reference"]);
    file(&review_path, &bad);
    assert!(prepare().is_err());
}

#[test]
fn suite_readback_rejects_omissions_forged_summary_and_borrowed_capture() {
    for mode in [
        "missing-row",
        "false-summary",
        "wrong-recovery",
        "raw-drift",
        "extra-control",
        "borrowed-source",
        "copied-recovery",
    ] {
        let base = suite_fixture();
        let suite = base.join("suite");
        let result_path = suite.join("result.json");
        let mut result: Value = serde_json::from_slice(&fs::read(&result_path).unwrap()).unwrap();
        match mode {
            "missing-row" => {
                result["attempts"].as_array_mut().unwrap().pop();
            }
            "false-summary" => result["status"] = json!("review-declaration-mismatch"),
            "wrong-recovery" => result["attempts"][4]["controlId"] = json!("valid-b"),
            "raw-drift" => {
                fs::write(
                    suite.join("control-3/contained-input-fixture/worker-stdout.log"),
                    "{}",
                )
                .unwrap();
            }
            "extra-control" => {
                fs::create_dir(suite.join("control-99")).unwrap();
            }
            "borrowed-source" => {
                let p = suite.join("control-1/intent.json");
                let mut v: Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
                v["source"] = json!({"revision":"2".repeat(40)});
                file(&p, &v);
            }
            "copied-recovery" => {
                fs::copy(
                    suite.join("control-1/contained-input-fixture/process.json"),
                    suite.join("control-4/contained-input-fixture/process.json"),
                )
                .unwrap();
            }
            _ => unreachable!(),
        }
        file(&result_path, &result);
        assert!(
            agentlab_code_analysis::maintainer_source_diagnostic::validate_suite(
                &base.join("stage"),
                &suite,
                &base.join("readback.json")
            )
            .is_err(),
            "{mode}"
        );
        assert!(!base.join("readback.json").exists());
    }
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
