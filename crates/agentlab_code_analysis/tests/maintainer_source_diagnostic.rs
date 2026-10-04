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
#[test]
fn frozen_rubric_native_preflight_checks_criteria_without_source_or_model() {
    use agentlab_code_analysis::maintainer_source_review::validate_rubric;
    let path = root().join("examples/maintainer-knowledge-gate/source-quality-rubric.json");
    let bytes = fs::read(&path).unwrap();
    let rubric = validate_rubric(&bytes).unwrap();
    assert_eq!(rubric["criteria"].as_array().unwrap().len(), 6);
    let mut negatives = Vec::new();
    let mut changed = rubric.clone();
    changed["criteria"] = json!([]);
    negatives.push(changed);
    let mut changed = rubric.clone();
    changed["criteria"][1] = changed["criteria"][0].clone();
    negatives.push(changed);
    for key in ["id", "requirement", "evidence"] {
        for bad in [json!(" "), json!(null), json!("x".repeat(8193))] {
            let mut changed = rubric.clone();
            changed["criteria"][0][key] = bad;
            negatives.push(changed);
        }
    }
    let mut changed = rubric.clone();
    changed["criteria"][0]["extra"] = json!(true);
    negatives.push(changed);
    for key in ["repositoryAgnostic", "frozenBeforeDispatch"] {
        let mut changed = rubric.clone();
        changed[key] = json!(false);
        negatives.push(changed);
    }
    for bad in negatives {
        assert!(validate_rubric(&serde_json::to_vec(&bad).unwrap()).is_err());
    }
    assert!(validate_rubric(&vec![b' '; 128 * 1024 + 1]).is_err());
    let output = std::env::temp_dir().join(format!(
        "agentlab-rubric-preflight-{}-{}.json",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    ));
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--validate-source-quality-rubric")
            .arg("--quality-rubric")
            .arg(&path)
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap()
    };
    assert!(run().status.success());
    let original = fs::read(&output).unwrap();
    let receipt: Value = serde_json::from_slice(&original).unwrap();
    assert_eq!(receipt["qualityRubricSha256"], digest(&bytes));
    assert_eq!(receipt["criterionCount"], 6);
    assert_eq!(receipt["semanticQualityVerified"], false);
    assert_eq!(receipt["qualified"], false);
    assert!(!run().status.success());
    assert_eq!(fs::read(&output).unwrap(), original);
    fs::remove_file(output).unwrap();
}
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
    suite_fixture_with_outcome(
        wrongs,
        binding,
        binding.is_some_and(|b| b["fixtureDisagreement"] == true),
        false,
    )
}

fn suite_fixture_with_outcome(
    wrongs: usize,
    binding: Option<&Value>,
    disagrees: bool,
    extra_failure: bool,
) -> PathBuf {
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
        if let Some(target) = binding.get("sourceRecipeTarget") {
            request["sourceRecipeTarget"] = target.clone();
        }
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
    design["invariant"] = json!("Retain the fixture's declared source observations.");
    design["limitations"] = json!([
        "Synthetic source seam only",
        "No semantic or framework qualification"
    ]);
    design["scenarios"][0]["inputs"]["seams"] = json!({});
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
    manifest["scenarios"] = design["scenarios"].clone();
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
        let mut actual = json!({"scenario":{"value":if id.starts_with("wrong") && !disagrees {8} else {7},"nullable":null}});
        if extra_failure && id.starts_with("wrong") {
            actual["scenario"]["nullable"] = json!(false);
        }
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

#[test]
fn reviewed_successor_reconstructs_rejected_wire_and_preserves_frozen_oracle() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_outcome(2, None, false, true);
    let observation = base.join("successor-observations");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let rubric = json!({"schema":"agentlab.prospective_source_quality_review.v1",
        "repositoryAgnostic":true,"frozenBeforeDispatch":true,"verdicts":["pass","fail","unverified"],
        "criteria":[{"id":"controls","requirement":"Exact failures.","evidence":"Original capture."}]});
    let rubric_bytes = serde_json::to_vec(&rubric).unwrap();
    let packet = reviewer::prepare(&observation, &rubric_bytes).unwrap();
    let judgments = suite_lesson_review(&observation);
    let finding = "The wrong controls have an undeclared additional state failure.";
    let response = json!({"schema":"agentlab.independent_source_suite_review_response.v1",
        "reviewerId":"synthetic-review","reviewRequestSha256":digest(&serde_json::to_vec(&packet).unwrap()),
        "qualityRubricSha256":packet["qualityRubricSha256"],"reviewBindings":packet["reviewBindings"],
        "automaticPromotion":false,"verdict":"reject","lessonReview":null,"unresolvedFindings":[finding],
        "scenarioReviews":judgments["scenarioReviews"],"checkReviews":judgments["checkReviews"],
        "controlReviews":judgments["controlReviews"],"criterionReviews":[{"id":"controls","verdict":"fail",
            "rationale":"Synthetic source/capture binding, not semantic proof.",
            "evidence":[{"pointer":"/originalSourceFiles/0/content","quote":"module.exports"}]}]});
    let response_bytes = serde_json::to_vec(&response).unwrap();
    let evidence = base.join("successor-review-evidence");
    fs::create_dir_all(evidence.join("gateway")).unwrap();
    let prompt = reviewer::prompt(&observation, &rubric_bytes).unwrap();
    fs::write(evidence.join("source-suite-review-prompt.txt"), &prompt).unwrap();
    file(
        &evidence.join("review-intent.json"),
        &json!({"schema":"agentlab.independent_source_suite_review_intent.v1",
        "reviewRequestSha256":digest(&serde_json::to_vec(&packet).unwrap()),"qualityRubricSha256":digest(&rubric_bytes),
        "promptSha256":digest(&prompt),"participantBudgetSeconds":420,"transportRetryLimit":0,
        "participantIdentity":{"model":"fixture","providerRoute":"fixture","providerReasoningEffort":null}}),
    );
    file(
        &evidence.join("gateway/1.upstream-request.json"),
        &json!({"model":"fixture","providerId":"fixture","stream":true,
        "messages":[{"role":"system","content":"Fixture only."},{"role":"user","content":String::from_utf8(prompt).unwrap()}]}),
    );
    let upstream = format!(
        "data: {}\n\ndata: [DONE]\n\n",
        json!({"choices":[{"index":0,
        "delta":{"content":String::from_utf8(response_bytes.clone()).unwrap()},"finish_reason":"stop"}]})
    );
    fs::write(evidence.join("gateway/1.response"), &upstream).unwrap();
    file(
        &evidence.join("gateway/1.status.json"),
        &json!({"exchangeId":"1","durationMs":1,"status":200,
        "upstreamEof":true,"semanticComplete":true,"outcome":"completed","streamError":null,"responseBytes":upstream.len()}),
    );
    let final_path = evidence.join("source-suite-review-final-assistant-message.json");
    file(
        &final_path,
        &json!({"role":"assistant","stopReason":"stop",
        "content":[{"type":"text","text":String::from_utf8(response_bytes.clone()).unwrap()}]}),
    );
    file(
        &evidence.join("source-suite-review-lifecycle.json"),
        &json!({"label":"source-suite-review",
        "captureAuthority":"operator","exitCode":0,"timedOut":false,"finalAssistantMessagePresent":true,
        "participantBudgetSeconds":420,"participantBudgetScope":"native-process-watchdog","transportRetryLimit":0,
        "finalAssistantMessageSha256":digest(&fs::read(final_path).unwrap())}),
    );
    let request_bytes = fs::read(observation.join("source-stage/request.json")).unwrap();
    let parent_bytes = fs::read(observation.join("source-stage/design.json")).unwrap();
    let parent: Value = serde_json::from_slice(&parent_bytes).unwrap();
    let changes = parent["controls"].as_array().unwrap().iter().filter(|control| control["role"] == "wrong")
        .map(|control| { let mut after = control.clone(); after["expectedFailedCheckIds"] = json!(["answer","nullable"]);
            json!({"id":control["id"],"before":control,"after":after,"findingId":"additional-state"}) }).collect::<Vec<_>>();
    let feedback = json!({"schema":"agentlab.source_recipe_design_review.v3",
        "parentRequestSha256":digest(&request_bytes),"parentDesignSha256":digest(&parent_bytes),
        "reviewed":true,"verdict":"revise","reviewer":"maintained-change-review","automaticPromotion":false,
        "findings":[{"id":"additional-state","observed":finding,"requiredChange":"Account for the reviewed state effect without weakening checks.","sourcePaths":["unit.js"]}],
        "checkChanges":[],"scenarioChanges":[],"controlChanges":changes});
    let feedback_bytes = serde_json::to_vec(&feedback).unwrap();
    let policy = json!({"schema":"agentlab.source_successor_policy.v1","reviewed":true,"maximumSuccessors":2,
        "participantBudgetSeconds":420,"designRevisionLimit":0,"codeRevisionLimit":0,"transportRetryLimit":0,"automaticPromotion":false});
    let policy_bytes = serde_json::to_vec(&policy).unwrap();
    let prepare = |f: &[u8], p: &[u8], previous: Option<&[u8]>| {
        reviewer::prepare_reviewed_successor(
            &observation,
            &rubric_bytes,
            &evidence,
            &response_bytes,
            None,
            f,
            p,
            previous,
        )
    };
    let successor = prepare(&feedback_bytes, &policy_bytes, None).unwrap();
    assert_eq!(successor["successorIndex"], 1);
    assert_eq!(successor["dispatchPerformed"], false);
    assert_eq!(successor["oldBudgetReopened"], false);
    assert_eq!(successor["historicalFeedbackCaptureVerified"], false);
    let target: Value =
        serde_json::from_str(successor["targetDesignOriginal"].as_str().unwrap()).unwrap();
    assert_eq!(target["checks"], parent["checks"]);
    assert_eq!(target["scenarios"], parent["scenarios"]);
    assert_eq!(
        target["controls"][3]["expectedFailedCheckIds"],
        json!(["answer", "nullable"])
    );
    for key in [
        "maximumSuccessors",
        "participantBudgetSeconds",
        "designRevisionLimit",
        "codeRevisionLimit",
        "transportRetryLimit",
        "automaticPromotion",
        "reviewed",
    ] {
        let mut bad = policy.clone();
        bad[key] = json!(99);
        assert!(
            prepare(&feedback_bytes, &serde_json::to_vec(&bad).unwrap(), None).is_err(),
            "{key}"
        );
    }
    let mut paraphrased = feedback.clone();
    paraphrased["findings"][0]["observed"] = json!("Operator-rewritten finding");
    assert!(prepare(
        &serde_json::to_vec(&paraphrased).unwrap(),
        &policy_bytes,
        None
    )
    .is_err());
    assert!(prepare(
        &feedback_bytes,
        &policy_bytes,
        Some(&serde_json::to_vec(&successor).unwrap())
    )
    .is_err());
    let original = fs::read(evidence.join("gateway/1.response")).unwrap();
    fs::write(evidence.join("gateway/1.response"), b"incomplete").unwrap();
    assert!(prepare(&feedback_bytes, &policy_bytes, None).is_err());
    fs::write(evidence.join("gateway/1.response"), original).unwrap();
    assert_eq!(
        prepare(&feedback_bytes, &policy_bytes, None).unwrap(),
        successor
    );
    for (name, bytes) in [
        ("successor-rubric.json", &rubric_bytes),
        ("successor-response.json", &response_bytes),
        ("successor-feedback.json", &feedback_bytes),
        ("successor-policy.json", &policy_bytes),
    ] {
        fs::write(base.join(name), bytes).unwrap();
    }
    let output = base.join("successor-request.json");
    let cli = |mode: &str, output: &Path| {
        let mut command = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"));
        command
            .arg(mode)
            .arg("--source")
            .arg(&observation)
            .arg("--quality-rubric")
            .arg(base.join("successor-rubric.json"))
            .arg("--review-response")
            .arg(base.join("successor-response.json"))
            .arg("--participant-evidence")
            .arg(&evidence)
            .arg("--review-feedback")
            .arg(base.join("successor-feedback.json"))
            .arg("--successor-policy")
            .arg(base.join("successor-policy.json"))
            .arg("--output")
            .arg(output);
        if mode == "--check-source-reviewed-successor" {
            command
                .arg("--successor-request")
                .arg(base.join("successor-request.json"));
        }
        command.output().unwrap()
    };
    let created = cli("--prepare-source-reviewed-successor", &output);
    assert!(
        created.status.success(),
        "{}",
        String::from_utf8_lossy(&created.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&output).unwrap()).unwrap(),
        successor
    );
    let retained = fs::read(&output).unwrap();
    assert!(!cli("--prepare-source-reviewed-successor", &output)
        .status
        .success());
    assert_eq!(fs::read(&output).unwrap(), retained);
    let verified_output = base.join("successor-reconstruction.json");
    assert!(cli("--check-source-reviewed-successor", &verified_output)
        .status
        .success());
    let mut forged = successor.clone();
    forged["successorIndex"] = json!(8);
    file(&output, &forged);
    let rejected_output = base.join("forged-successor-reconstruction.json");
    assert!(!cli("--check-source-reviewed-successor", &rejected_output)
        .status
        .success());
    assert!(!rejected_output.exists());
    assert_eq!(
        fs::read(observation.join("source-stage/design.json")).unwrap(),
        parent_bytes
    );
    fs::remove_dir_all(base).unwrap();
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
from types import SimpleNamespace
args=SimpleNamespace(run='123',source_revision='a'*40)
constructor=dict(id=123,status='completed',event='workflow_dispatch',head_branch='main',head_sha='a'*40,
                 name='Maintainer source recipe construction',path='.github/workflows/maintainer-source-recipe-author.yml')
reviewer=dict(constructor,name='Maintainer independent source suite review',path='.github/workflows/maintainer-source-suite-review.yml')
assert module.validate_run_identity(constructor,args,True) is True
assert module.validate_run_identity(constructor,args,False) is False
assert module.validate_run_identity(reviewer,args,True) is False
args.coordinator_request_id='c'*64
tagged=dict(constructor,name='AgentLab gap '+'c'*64,display_title='AgentLab gap '+'c'*64)
assert module.validate_run_identity(tagged,args,True) is True
for row in [constructor,dict(tagged,name='AgentLab gap '+'d'*64),dict(tagged,display_title='wrong'),
            dict(tagged,path=reviewer['path'])]:
    try:module.validate_run_identity(row,args,True)
    except ValueError:pass
    else:raise AssertionError('Coordinator identity mismatch accepted')
args.coordinator_request_id=None
try:module.validate_run_identity(tagged,args,True)
except ValueError:pass
else:raise AssertionError('Undeclared coordinator run accepted')
for row,feedback in [(reviewer,False),(dict(constructor,status='in_progress'),True),
                     (dict(constructor,event='pull_request'),True),(dict(constructor,head_branch='fork'),True),
                     (dict(constructor,head_sha='b'*40),True),(dict(constructor,path='.github/workflows/arbitrary.yml'),True)]:
    try:module.validate_run_identity(row,args,feedback)
    except ValueError:pass
    else:raise AssertionError('Untrusted automatic review identity accepted')
archive=base/'good.zip'
with zipfile.ZipFile(archive,'w') as z:
    z.writestr('observation-export/source-stage/request.json','original bytes')
    z.writestr('agent/participant-state/session.json','not reviewer instructions')
module.extract_observations(archive,base/'selected')
required=['enrollment.json','rubric.json','agent/response.json',
    'agent/evidence/review-intent.json','agent/evidence/source-suite-review-prompt.txt',
    'agent/evidence/source-suite-review-lifecycle.json','agent/evidence/source-suite-review-final-assistant-message.json',
    'source/observations/export.json','source/observations/source-suite-inputs.json',
    'agent/evidence/gateway/0001.response','feedback/receipt.json']
archive=base/'review.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name in required:z.writestr(name,'original '+name)
    z.writestr('agent/evidence/source-suite-review-events.jsonl',b'x'*(5*1024*1024))
    z.writestr('agent/participant-state/session.json','excluded full home')
    z.writestr('agent/repair-attempt/response.json','original repaired response')
    z.writestr('agent/repair-attempt/evidence/review-repair-policy.json','original policy')
    z.writestr('agent/repair-attempt/evidence/source-suite-review-events.jsonl',b'x'*(5*1024*1024))
    z.writestr('agent/repair-attempt/participant-state/session.json','excluded repair home')
module.extract_observations(archive,base/'received',True)
assert (base/'received/agent/evidence/gateway/0001.response').read_text()=='original agent/evidence/gateway/0001.response'
assert (base/'received/feedback/receipt.json').read_text()=='original feedback/receipt.json'
assert not (base/'received/agent/evidence/source-suite-review-events.jsonl').exists()
assert not (base/'received/agent/participant-state').exists()
assert (base/'received/agent/repair-attempt/response.json').read_text()=='original repaired response'
assert not (base/'received/agent/repair-attempt/evidence/source-suite-review-events.jsonl').exists()
assert not (base/'received/agent/repair-attempt/participant-state').exists()
for name in ['missing-wire','missing-intent','oversized-selected','unselected-traversal']:
    archive=base/(name+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for member in required:
            if name=='missing-wire' and member.startswith('agent/evidence/gateway/'):continue
            if name=='missing-intent' and member=='agent/evidence/review-intent.json':continue
            z.writestr(member,'original '+member)
        if name=='oversized-selected':z.writestr('feedback/too-large.json',b'x'*(4*1024*1024+1))
        if name=='unselected-traversal':z.writestr('agent/participant-state/../../escape','invalid')
    try:module.extract_observations(archive,base/('received-'+name),True)
    except ValueError:pass
    else:raise AssertionError(name+' accepted')
    assert not (base/('received-'+name)).exists()
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
fn original_construction_target_survives_export_into_independent_review() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let rubric = fs::read(
        root().join("examples/maintainer-knowledge-gate/source-target-quality-rubric.json"),
    )
    .unwrap();
    let legacy = suite_fixture_with_binding(2, None);
    let observation = legacy.join("observations");
    lesson::export(
        &legacy.join("stage"),
        &legacy.join("suite"),
        None,
        &observation,
    )
    .unwrap();
    assert!(reviewer::prepare(&observation, &rubric)
        .unwrap_err()
        .contains("requires a frozen original request target"));
    for repository in ["unrelated-target-one", "independent-target-two"] {
        let target = json!({"scopeSkillId":"scope","sourcePaths":["unit.js"],"demand":"Exercise the source mechanism and verify its declared result; preserve runtime limitations."});
        let binding = json!({"source":{"repositoryId":repository,"revision":"1".repeat(40)},
            "cutSha256":"a".repeat(64),"revision":"b".repeat(40),"sourceRecipeTarget":target});
        let base = suite_fixture_with_binding(2, Some(&binding));
        let observation = base.join("observations");
        lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
        let original = fs::read(base.join("stage/request.json")).unwrap();
        assert_eq!(
            fs::read(observation.join("source-stage/request.json")).unwrap(),
            original
        );
        let packet = reviewer::prepare(&observation, &rubric).unwrap();
        let old_rubric =
            fs::read(root().join("examples/maintainer-knowledge-gate/source-quality-rubric.json"))
                .unwrap();
        assert!(reviewer::prepare(&observation, &old_rubric)
            .unwrap_err()
            .contains("requires construction-target-coverage rubric"));
        assert_eq!(packet["constructionTarget"], target);
        assert_eq!(packet["reviewBindings"]["requestSha256"], digest(&original));
        let prompt = reviewer::prompt(&observation, &rubric).unwrap();
        let prompt = String::from_utf8(prompt).unwrap();
        let presented: Value =
            serde_json::from_str(prompt.split("\nORIGINAL REVIEW REQUEST:\n").nth(1).unwrap())
                .unwrap();
        assert_eq!(presented["constructionTarget"], target);
        assert_eq!(packet["semanticQualified"], false);
        assert_eq!(packet["reviewerExecuted"], false);
        fs::remove_dir_all(base).unwrap();
    }
    fs::remove_dir_all(legacy).unwrap();
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
    assert!(packet.get("constructionTarget").is_none());
    let prompt = String::from_utf8(
        reviewer::prompt_with_git(&observation, &rubric, Some(&checkout)).unwrap(),
    )
    .unwrap();
    let presentation = prompt.split("\nORIGINAL REVIEW REQUEST:\n").nth(1).unwrap();
    assert_eq!(serde_json::from_str::<Value>(presentation).unwrap(), packet);
    assert_eq!(
        presentation.as_bytes(),
        serde_json::to_vec(&packet).unwrap()
    );
    assert!(presentation.len() < serde_json::to_vec_pretty(&packet).unwrap().len());
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
    let mut response = json!({"schema":"agentlab.independent_source_suite_review_response.v2",
        "reviewerId":review["reviewerId"],"unresolvedFindings":[],
        "lessonInterpretation":{"phenomenon":review["phenomenon"],"cause":review["cause"],"change":review["change"],"body":review["body"]},
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
    for key in response.as_object().unwrap().keys() {
        let mut missing = response.clone();
        missing.as_object_mut().unwrap().remove(key);
        assert!(validate(&missing)
            .unwrap_err()
            .contains("field set differs"));
    }
    let mut old_schema = response.clone();
    old_schema["schema"] = json!("agentlab.independent_source_suite_review_response.v1");
    assert!(validate(&old_schema).is_err());
    for key in ["skillId", "skillStage", "scopeSha256", "automaticPromotion"] {
        let mut wrong = response.clone();
        wrong["lessonInterpretation"][key] = json!("forged");
        assert!(validate(&wrong).is_err());
    }
    for key in [
        "verdict",
        "automaticPromotion",
        "reviewBindings",
        "reviewRequestSha256",
        "lessonReview",
    ] {
        let mut wrong = response.clone();
        wrong[key] = json!(false);
        assert!(validate(&wrong).unwrap_err().contains("field set differs"));
    }
    for key in ["phenomenon", "cause", "change", "body"] {
        let mut wrong = response.clone();
        wrong["lessonInterpretation"][key] = json!("");
        assert!(validate(&wrong).is_err());
    }
    let mut incomplete = response.clone();
    incomplete["controlReviews"].as_array_mut().unwrap().pop();
    assert!(validate(&incomplete).is_err());
    let mut unsupported = response.clone();
    unsupported["criterionReviews"][0]["evidence"][0]["quote"] = json!("fabricated quote");
    assert!(validate(&unsupported).is_err());
    // Synthetic wire fixture: exercise v2 completion/export/reception, not an Agent.
    let evidence = base.join("git-review-evidence");
    fs::create_dir_all(evidence.join("gateway")).unwrap();
    let prompt = reviewer::prompt_with_git(&observation, &rubric, Some(&checkout)).unwrap();
    fs::write(evidence.join("source-suite-review-prompt.txt"), &prompt).unwrap();
    file(
        &evidence.join("review-intent.json"),
        &json!({"schema":"agentlab.independent_source_suite_review_intent.v1",
        "reviewRequestSha256":digest(&serde_json::to_vec(&packet).unwrap()),"qualityRubricSha256":packet["qualityRubricSha256"],
        "promptSha256":digest(&prompt),"participantBudgetSeconds":420,"transportRetryLimit":0,
        "participantIdentity":{"model":"fixture","providerRoute":"fixture","providerReasoningEffort":null}}),
    );
    file(
        &evidence.join("gateway/1.upstream-request.json"),
        &json!({"model":"fixture","providerId":"fixture","stream":false,
        "messages":[{"role":"user","content":String::from_utf8(prompt).unwrap()}]}),
    );
    let response_bytes = serde_json::to_vec(&response).unwrap();
    let response_text = String::from_utf8(response_bytes.clone()).unwrap();
    let wire = serde_json::to_vec(&json!({"choices":[{"index":0,"message":{"role":"assistant","content":response_text},"finish_reason":"stop"}]})).unwrap();
    fs::write(evidence.join("gateway/1.response"), &wire).unwrap();
    file(
        &evidence.join("gateway/1.status.json"),
        &json!({"exchangeId":"1","durationMs":1,"status":200,"upstreamEof":true,
        "semanticComplete":true,"outcome":"completed","streamError":null,"responseBytes":wire.len()}),
    );
    let final_path = evidence.join("source-suite-review-final-assistant-message.json");
    file(
        &final_path,
        &json!({"role":"assistant","stopReason":"stop","content":[{"type":"text","text":response_text}]}),
    );
    file(
        &evidence.join("source-suite-review-lifecycle.json"),
        &json!({"label":"source-suite-review","captureAuthority":"operator",
        "exitCode":0,"timedOut":false,"finalAssistantMessagePresent":true,"participantBudgetSeconds":420,
        "participantBudgetScope":"native-process-watchdog","transportRetryLimit":0,"finalAssistantMessageSha256":digest(&fs::read(final_path).unwrap())}),
    );
    let envelope = base.join("git-review-feedback");
    reviewer::export_accepted_feedback(
        &observation,
        &rubric,
        &evidence,
        &response_bytes,
        Some(&checkout),
        &envelope,
    )
    .unwrap();
    let received = reviewer::verify_feedback_export(
        &observation,
        &rubric,
        &evidence,
        &response_bytes,
        Some(&checkout),
        &envelope,
    )
    .unwrap();
    assert_eq!(received["candidateReadyForObservationImport"], true);
    assert_eq!(received["authorityWritePerformed"], false);
    assert_eq!(
        fs::read(envelope.join("original-response.json")).unwrap(),
        response_bytes
    );
    let derived: Value = serde_json::from_slice(
        &fs::read(envelope.join("lesson-export/lesson-review.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(derived["skillId"], template["skillId"]);
    assert_eq!(derived["body"], response["lessonInterpretation"]["body"]);
    assert_eq!(derived["controlReviews"], response["controlReviews"]);
    // Predeclared native repair fixture, never an operator-corrected real review.
    let policy = json!({"schema":"agentlab.review_repair_policy.v1","reviewRepairLimit":1,
        "maximumReviewerAttempts":2,"participantBudgetSeconds":420,"totalParticipantBudgetSeconds":840,"transportRetryLimit":0});
    let parent = base.join("policy-parent");
    fs::create_dir(&parent).unwrap();
    file(&parent.join("review-repair-policy.json"), &policy);
    let parent_prompt =
        reviewer::prompt_for_review_attempt(&observation, &rubric, &parent, Some(&checkout))
            .unwrap();
    assert_eq!(
        std::str::from_utf8(&parent_prompt)
            .unwrap()
            .trim()
            .as_bytes(),
        parent_prompt
    );
    let capture = |dir: &Path, reply: &Value, prompt: &[u8]| {
        fs::create_dir_all(dir.join("gateway")).unwrap();
        fs::write(dir.join("source-suite-review-prompt.txt"), prompt).unwrap();
        let mut intent: Value =
            serde_json::from_slice(&fs::read(evidence.join("review-intent.json")).unwrap())
                .unwrap();
        intent["reviewRepairPolicySha256"] = json!(digest(&serde_json::to_vec(&policy).unwrap()));
        intent["promptSha256"] = json!(digest(prompt));
        file(&dir.join("review-intent.json"), &intent);
        file(
            &dir.join("gateway/1.upstream-request.json"),
            &json!({"model":"fixture","providerId":"fixture","stream":false,
            "messages":[{"role":"user","content":String::from_utf8(prompt.to_vec()).unwrap()}]}),
        );
        let text = serde_json::to_string(reply).unwrap();
        let raw = serde_json::to_vec(
            &json!({"choices":[{"index":0,"message":{"content":text},"finish_reason":"stop"}]}),
        )
        .unwrap();
        fs::write(dir.join("gateway/1.response"), &raw).unwrap();
        file(
            &dir.join("gateway/1.status.json"),
            &json!({"exchangeId":"1","durationMs":1,"status":200,"upstreamEof":true,
            "semanticComplete":true,"outcome":"completed","streamError":null,"responseBytes":raw.len()}),
        );
        let final_path = dir.join("source-suite-review-final-assistant-message.json");
        file(
            &final_path,
            &json!({"role":"assistant","stopReason":"stop","content":[{"type":"text","text":text}]}),
        );
        file(
            &dir.join("source-suite-review-lifecycle.json"),
            &json!({"label":"source-suite-review","captureAuthority":"operator",
            "exitCode":0,"timedOut":false,"finalAssistantMessagePresent":true,"participantBudgetSeconds":420,
            "participantBudgetScope":"native-process-watchdog","transportRetryLimit":0,"finalAssistantMessageSha256":digest(&fs::read(final_path).unwrap())}),
        );
    };
    capture(&parent, &unsupported, &parent_prompt);
    let child = base.join("repair-child");
    let retained = child.join("repair-inputs/evidence");
    fs::create_dir_all(retained.join("gateway")).unwrap();
    file(&child.join("review-repair-policy.json"), &policy);
    for name in [
        "review-repair-policy.json",
        "review-intent.json",
        "source-suite-review-prompt.txt",
        "source-suite-review-final-assistant-message.json",
        "source-suite-review-lifecycle.json",
        "gateway/1.upstream-request.json",
        "gateway/1.response",
        "gateway/1.status.json",
    ] {
        fs::copy(parent.join(name), retained.join(name)).unwrap();
    }
    file(&child.join("repair-inputs/response.json"), &unsupported);
    let repair_prompt =
        reviewer::prompt_for_review_attempt(&observation, &rubric, &child, Some(&checkout))
            .unwrap();
    assert_eq!(
        std::str::from_utf8(&repair_prompt)
            .unwrap()
            .trim()
            .as_bytes(),
        repair_prompt
    );
    let prompt_output = base.join("native-repair-prompt.txt");
    let rubric_path = base.join("repair-rubric.json");
    fs::write(&rubric_path, &rubric).unwrap();
    let cli = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .args(["--prepare-source-suite-review-attempt-prompt", "--source"])
        .arg(&observation)
        .arg("--quality-rubric")
        .arg(&rubric_path)
        .arg("--participant-evidence")
        .arg(&child)
        .arg("--source-git-checkout")
        .arg(&checkout)
        .arg("--output")
        .arg(&prompt_output)
        .output()
        .unwrap();
    assert!(
        cli.status.success(),
        "{}",
        String::from_utf8_lossy(&cli.stderr)
    );
    assert_eq!(fs::read(prompt_output).unwrap(), repair_prompt);
    assert!(String::from_utf8(repair_prompt.clone())
        .unwrap()
        .contains("/criterionReviews/0/evidence/0"));
    capture(&child, &response, &repair_prompt);
    let repaired_envelope = base.join("repair-envelope");
    reviewer::export_accepted_feedback(
        &observation,
        &rubric,
        &child,
        &response_bytes,
        Some(&checkout),
        &repaired_envelope,
    )
    .unwrap();
    assert_eq!(
        reviewer::verify_feedback_export(
            &observation,
            &rubric,
            &child,
            &response_bytes,
            Some(&checkout),
            &repaired_envelope
        )
        .unwrap()["candidateReadyForObservationImport"],
        true
    );
    let repaired_completion: Value =
        serde_json::from_slice(&fs::read(repaired_envelope.join("completion.json")).unwrap())
            .unwrap();
    assert_eq!(repaired_completion["reviewRepair"]["repairIndex"], 1);
    assert_eq!(
        repaired_completion["reviewRepair"]["originalResponseSha256"],
        digest(&serde_json::to_vec(&unsupported).unwrap())
    );
    // Whitespace stability belongs to generation, not permissive wire verification.
    let child_wire_path = child.join("gateway/1.upstream-request.json");
    let child_wire_bytes = fs::read(&child_wire_path).unwrap();
    let mut child_wire: Value = serde_json::from_slice(&child_wire_bytes).unwrap();
    child_wire["messages"][0]["content"] =
        json!(format!("{}\n", String::from_utf8(repair_prompt).unwrap()));
    file(&child_wire_path, &child_wire);
    assert!(reviewer::verify_completion_with_git(
        &observation,
        &rubric,
        &child,
        &response_bytes,
        Some(&checkout)
    )
    .is_err());
    fs::write(child_wire_path, child_wire_bytes).unwrap();
    let expect_repair_reject = || {
        assert!(
            reviewer::prompt_for_review_attempt(&observation, &rubric, &child, Some(&checkout))
                .is_err()
        )
    };
    // Forged policy cannot grant allowance to an original one-attempt capture.
    fs::remove_file(retained.join("review-repair-policy.json")).unwrap();
    expect_repair_reject();
    file(&retained.join("review-repair-policy.json"), &policy);
    let original_prompt = fs::read(retained.join("source-suite-review-prompt.txt")).unwrap();
    fs::write(
        retained.join("source-suite-review-prompt.txt"),
        reviewer::prompt_with_git(&observation, &rubric, Some(&checkout)).unwrap(),
    )
    .unwrap();
    expect_repair_reject();
    fs::write(
        retained.join("source-suite-review-prompt.txt"),
        original_prompt,
    )
    .unwrap();
    fs::create_dir(retained.join("repair-inputs")).unwrap();
    expect_repair_reject();
    fs::remove_dir(retained.join("repair-inputs")).unwrap();
    file(&child.join("repair-inputs/response.json"), &response);
    expect_repair_reject();
    file(&child.join("repair-inputs/response.json"), &unsupported);
    let status_bytes = fs::read(retained.join("gateway/1.status.json")).unwrap();
    let mut status: Value = serde_json::from_slice(&status_bytes).unwrap();
    status["semanticComplete"] = json!(false);
    file(&retained.join("gateway/1.status.json"), &status);
    expect_repair_reject();
    fs::write(retained.join("gateway/1.status.json"), status_bytes).unwrap();
    capture(&retained, &response, &parent_prompt);
    file(&child.join("repair-inputs/response.json"), &response);
    expect_repair_reject(); // A passing review never enters repair.
    capture(&retained, &unsupported, &parent_prompt);
    file(&child.join("repair-inputs/response.json"), &unsupported);
    let child_intent_path = child.join("review-intent.json");
    let child_intent_bytes = fs::read(&child_intent_path).unwrap();
    let mut child_intent: Value = serde_json::from_slice(&child_intent_bytes).unwrap();
    child_intent["participantBudgetSeconds"] = json!(421);
    file(&child_intent_path, &child_intent);
    assert!(reviewer::verify_completion_with_git(
        &observation,
        &rubric,
        &child,
        &response_bytes,
        Some(&checkout)
    )
    .is_err());
    fs::write(child_intent_path, child_intent_bytes).unwrap();
    // Actual thin coordinator with synthetic participants and real native gates.
    file(&base.join("coordinator-good.json"), &response);
    file(&base.join("coordinator-citation.json"), &unsupported);
    let transport = base.join("coordinator-fixture.py");
    fs::write(&transport, r#"
import argparse,hashlib,importlib.util,json,os,sys
from pathlib import Path
repo,base,checkout,mode=sys.argv[1:];base=Path(base)
spec=importlib.util.spec_from_file_location('review_transport',Path(repo)/'scripts/run-source-suite-review.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def put(path,value):path.write_text(json.dumps(value))
class Participant:
    @staticmethod
    def process_budget_seconds(wall):return 420
    def __init__(self,evidence,state,binary,gateway,model,**kw):
        self.evidence=evidence;self.model=model;self.route=kw['route'];state.mkdir();(evidence/'gateway').mkdir()
    def turn(self,label,workspace,**kw):
        assert not list(workspace.iterdir()) and label=='source-suite-review' and kw['transport_retry_limit']==0
        child='repair-attempt' in self.evidence.parts
        with (base/('launches-'+mode+'.txt')).open('a') as f:f.write('repair\n' if child else 'initial\n')
        prompt=kw['prompt'];assert 'fixture-external-secret' not in prompt
        if child:assert 'BOUNDED AGENT-OWNED CITATION REPAIR' in prompt and '/criterionReviews/0/evidence/0' in prompt
        text=(base/('coordinator-good.json' if child and mode=='repair' else 'coordinator-citation.json')).read_text()
        if mode=='noncitation':
            value=json.loads(text);value.pop('reviewerId');text=json.dumps(value)
        (self.evidence/(label+'-prompt.txt')).write_text(prompt)
        (self.evidence/(label+'-events.jsonl')).write_text('original events retained outside repair input')
        # Match the pinned Pi stdin behavior, not an idealized raw-byte transport.
        put(self.evidence/'gateway/1.upstream-request.json',dict(model=self.model,providerId=self.route,stream=False,messages=[dict(role='user',content=[dict(type='text',text=prompt.strip())])]))
        raw=json.dumps(dict(choices=[dict(index=0,message=dict(content=text),finish_reason='stop')])).encode()
        (self.evidence/'gateway/1.response').write_bytes(raw)
        put(self.evidence/'gateway/1.status.json',dict(exchangeId='1',durationMs=1,status=200,upstreamEof=True,
            semanticComplete=mode!='incomplete',outcome='completed',streamError=None,responseBytes=len(raw)))
        final=self.evidence/(label+'-final-assistant-message.json')
        put(final,dict(role='assistant',stopReason='stop',content=[dict(type='text',text=text)]))
        put(self.evidence/(label+'-lifecycle.json'),dict(label=label,captureAuthority='operator',exitCode=0,timedOut=False,
            finalAssistantMessagePresent=True,participantBudgetSeconds=420,participantBudgetScope='native-process-watchdog',
            transportRetryLimit=0,finalAssistantMessageSha256=hashlib.sha256(final.read_bytes()).hexdigest()))
        return dict(content=text)
args=argparse.Namespace(source=base/'git-observations',rubric=base/'repair-rubric.json',output=base/('coordinator-'+mode),
    gate=Path(os.environ['FIXTURE_NATIVE_GATE']),pi=Path('/fixture/pi'),gateway_timeout_seconds=240,
    source_git_checkout=Path(checkout),review_repair_limit=0 if mode=='zero' else 1,
    thinking_type='disabled',reasoning_effort='default',max_output_tokens=16384)
m.run(args,participant_class=Participant)
"#).unwrap();
    let invoke = |mode: &str| {
        Command::new("python3")
            .arg(&transport)
            .arg(root())
            .arg(&base)
            .arg(&checkout)
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
                base.join(format!("coordinator-runtime-{mode}")),
            )
            .env("AGENTLAB_LM_GATEWAY_URL", "http://fixture.invalid")
            .env("AGENTLAB_LM_GATEWAY_KEY", "fixture-external-secret")
            .env("AGENTLAB_MODEL", "fixture")
            .env("AGENTLAB_PROVIDER_ROUTE", "fixture")
            .output()
            .unwrap()
    };
    let coordinated = invoke("repair");
    assert!(
        coordinated.status.success(),
        "{}",
        String::from_utf8_lossy(&coordinated.stderr)
    );
    let run_root = base.join("coordinator-repair");
    let coordinated_receipt: Value =
        serde_json::from_slice(&fs::read(run_root.join("attempt-coordinator.json")).unwrap())
            .unwrap();
    assert_eq!(coordinated_receipt["selectedAttempt"], "repair-attempt");
    assert_eq!(
        coordinated_receipt["attempts"],
        json!(["initial", "repair-1"])
    );
    assert_eq!(
        fs::read(run_root.join("response.json")).unwrap(),
        fs::read(base.join("coordinator-citation.json")).unwrap()
    );
    assert_eq!(
        fs::read(run_root.join("repair-attempt/response.json")).unwrap(),
        fs::read(base.join("coordinator-good.json")).unwrap()
    );
    assert!(!run_root
        .join("repair-attempt/evidence/repair-inputs/evidence/source-suite-review-events.jsonl")
        .exists());
    assert!(run_root
        .join("evidence/source-suite-review-events.jsonl")
        .exists());
    let coordinated_feedback = base.join("coordinator-feedback");
    let coordinated_response = fs::read(run_root.join("repair-attempt/response.json")).unwrap();
    reviewer::export_accepted_feedback(
        &observation,
        &rubric,
        &run_root.join("repair-attempt/evidence"),
        &coordinated_response,
        Some(&checkout),
        &coordinated_feedback,
    )
    .unwrap();
    assert_eq!(
        reviewer::verify_feedback_export(
            &observation,
            &rubric,
            &run_root.join("repair-attempt/evidence"),
            &coordinated_response,
            Some(&checkout),
            &coordinated_feedback
        )
        .unwrap()["candidateReadyForObservationImport"],
        true
    );
    let before = fs::read(run_root.join("attempt-coordinator.json")).unwrap();
    assert!(!invoke("repair").status.success());
    assert_eq!(
        fs::read(run_root.join("attempt-coordinator.json")).unwrap(),
        before
    );
    assert_eq!(
        fs::read_to_string(base.join("launches-repair.txt")).unwrap(),
        "initial\nrepair\n"
    );
    for (mode, launches) in [
        ("zero", "initial\n"),
        ("noncitation", "initial\n"),
        ("incomplete", "initial\n"),
        ("failed", "initial\nrepair\n"),
    ] {
        assert!(!invoke(mode).status.success(), "{mode} must stop");
        assert_eq!(
            fs::read_to_string(base.join(format!("launches-{mode}.txt"))).unwrap(),
            launches
        );
    }
    // Valid changed interpretation without corresponding original upstream text rejects.
    let mut changed = response.clone();
    changed["lessonInterpretation"]["body"] = json!("Changed independent interpretation.");
    assert!(reviewer::verify_completion_with_git(
        &observation,
        &rubric,
        &evidence,
        &serde_json::to_vec(&changed).unwrap(),
        Some(&checkout)
    )
    .is_err());
    let mut failed = response.clone();
    failed["criterionReviews"][0]["verdict"] = json!("fail");
    failed["lessonInterpretation"] = Value::Null;
    failed["unresolvedFindings"] = json!(["Synthetic negative review."]);
    assert_eq!(validate(&failed).unwrap()["verdict"], "reject");
    response["lessonInterpretation"] = Value::Null;
    response["unresolvedFindings"] = json!(["Synthetic reviewer has insufficient support."]);
    response["criterionReviews"][0]["verdict"] = json!("unverified");
    response["criterionReviews"][0]["evidence"] = json!([]);
    assert_eq!(validate(&response).unwrap()["verdict"], "unverified");
    let legacy = reviewer::prepare(&observation, &rubric).unwrap();
    assert!(legacy["responseContract"]
        .get("lessonReviewTemplate")
        .is_none());
    let prompt = reviewer::prompt_with_git(&observation, &rubric, Some(&checkout)).unwrap();
    let prompt = String::from_utf8(prompt).unwrap();
    assert!(prompt.contains("Emit each review array only once"));
    assert!(!prompt.contains("Copy every template field exactly"));
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
    let receive = |name: &str| {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--verify-source-suite-review-feedback")
            .arg("--source")
            .arg(&observation)
            .arg("--quality-rubric")
            .arg(&rubric_path)
            .arg("--review-response")
            .arg(base.join("review-accept/response.json"))
            .arg("--participant-evidence")
            .arg(base.join("review-accept/evidence"))
            .arg("--feedback")
            .arg(&envelope)
            .arg("--output")
            .arg(base.join(name))
            .output()
            .unwrap()
    };
    let received = receive("reception.json");
    assert!(
        received.status.success(),
        "{}",
        String::from_utf8_lossy(&received.stderr)
    );
    let reception: Value =
        serde_json::from_slice(&fs::read(base.join("reception.json")).unwrap()).unwrap();
    assert_eq!(reception["nativeOperationalExportReconstructed"], true);
    assert_eq!(reception["originalRawSourceBytesVerified"], true);
    assert_eq!(reception["candidateReadyForObservationImport"], true);
    assert_eq!(
        reception["lessonManifestSha256"],
        digest(&fs::read(envelope.join("lesson-export/export.json")).unwrap())
    );
    for key in [
        "authorityWritePerformed",
        "committedReadbackVerified",
        "runtimeIsolationVerified",
        "qualified",
        "learningBenefitVerified",
    ] {
        assert_eq!(reception[key], false);
    }
    let original_reception = fs::read(base.join("reception.json")).unwrap();
    assert!(!receive("reception.json").status.success());
    assert_eq!(
        fs::read(base.join("reception.json")).unwrap(),
        original_reception
    );
    for (path, name) in [
        ("original-response.json", "changed-response-reception.json"),
        ("completion.json", "changed-completion-reception.json"),
        (
            "lesson-export/lesson-review.json",
            "changed-lesson-reception.json",
        ),
        (
            "lesson-export/source-stage/controls.cjs",
            "changed-source-reception.json",
        ),
    ] {
        let path = envelope.join(path);
        let bytes = fs::read(&path).unwrap();
        let mut changed = bytes.clone();
        changed.push(b' ');
        fs::write(&path, changed).unwrap();
        assert!(!receive(name).status.success());
        assert!(!base.join(name).exists());
        fs::write(&path, bytes).unwrap();
    }
    let original_receipt = fs::read(envelope.join("receipt.json")).unwrap();
    let mut forged_receipt: Value = serde_json::from_slice(&original_receipt).unwrap();
    forged_receipt["sourceGitBindingVerified"] = json!(true);
    file(&envelope.join("receipt.json"), &forged_receipt);
    assert!(!receive("forged-proof-reception.json").status.success());
    assert!(!base.join("forged-proof-reception.json").exists());
    fs::write(envelope.join("receipt.json"), &original_receipt).unwrap();
    // Rehashing a changed table/manifest and producer receipt cannot bypass raw reconstruction.
    let table = envelope.join("lesson-export/checks.jsonl");
    let original_table = fs::read(&table).unwrap();
    let mut rows: Vec<Value> = String::from_utf8(original_table.clone())
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    rows[0]["passed"] = json!(!rows[0]["passed"].as_bool().unwrap());
    let changed_table = rows
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>()
        .into_bytes();
    fs::write(&table, &changed_table).unwrap();
    let manifest_path = envelope.join("lesson-export/export.json");
    let original_manifest = fs::read(&manifest_path).unwrap();
    let mut manifest: Value = serde_json::from_slice(&original_manifest).unwrap();
    manifest["tables"]["checks"]["sha256"] = json!(digest(&changed_table));
    file(&manifest_path, &manifest);
    forged_receipt["sourceGitBindingVerified"] = json!(false);
    forged_receipt["lessonExport"] = manifest;
    file(&envelope.join("receipt.json"), &forged_receipt);
    assert!(!receive("rehashed-row-reception.json").status.success());
    assert!(!base.join("rehashed-row-reception.json").exists());
    fs::write(&table, original_table).unwrap();
    fs::write(&manifest_path, original_manifest).unwrap();
    fs::write(envelope.join("receipt.json"), original_receipt).unwrap();
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
    assert!(!receive("changed-wire-reception.json").status.success());
    assert!(!base.join("changed-wire-reception.json").exists());
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
    let successor_policy = json!({"schema":"agentlab.source_successor_policy.v1",
        "reviewed":true,"maximumSuccessors":2,"participantBudgetSeconds":420,
        "designRevisionLimit":0,"codeRevisionLimit":0,"transportRetryLimit":0,
        "automaticPromotion":false});
    let rejection = reviewer::prepare_reviewed_successor(
        &observation,
        &rubric_bytes,
        &evidence,
        &serde_json::to_vec(&response).unwrap(),
        None,
        b"{}",
        &serde_json::to_vec(&successor_policy).unwrap(),
        None,
    )
    .unwrap_err();
    assert!(rejection.contains("requires complete rejected review"));
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
fn complete_failed_suite_is_reviewable_but_cannot_be_promoted_or_rehashed() {
    use agentlab_code_analysis::{
        maintainer_source_review as reviewer, maintainer_source_suite_lesson as lesson,
    };
    let base = suite_fixture_with_outcome(2, None, false, true);
    let observation = base.join("failed-observations");
    lesson::export(&base.join("stage"), &base.join("suite"), None, &observation).unwrap();
    let rubric =
        fs::read(root().join("examples/maintainer-knowledge-gate/source-quality-rubric.json"))
            .unwrap();
    let packet = reviewer::prepare(&observation, &rubric).unwrap();
    assert_eq!(
        packet["reconstructedSuite"]["status"],
        "review-declaration-mismatch"
    );
    assert_eq!(
        packet["reconstructedSuite"]["completeInventoryReconstructed"],
        true
    );
    assert_eq!(
        packet["reconstructedSuite"]["acceptedReferenceRecoveryReconstructed"],
        true
    );
    assert_eq!(packet["reviewerExecuted"], false);
    assert_eq!(packet["authorityWritePerformed"], false);
    assert_eq!(
        packet["reconstructedSuite"]["controls"][3]["unexpectedFailedCheckIds"],
        json!(["nullable"])
    );
    assert_eq!(
        packet["reconstructedSuite"]["controls"][3]["missingExpectedFailureIds"],
        json!([])
    );
    let review = suite_lesson_review(&observation);
    let rejected = base.join("forged-acceptance");
    let error = lesson::export(
        &base.join("stage"),
        &base.join("suite"),
        Some(&serde_json::to_vec(&review).unwrap()),
        &rejected,
    )
    .unwrap_err();
    assert!(error.contains("matched complete controls"), "{error}");
    assert_eq!(
        fs::read(rejected.join("source-suite/result.json")).unwrap(),
        fs::read(base.join("suite/result.json")).unwrap()
    );
    assert!(!rejected.join("export.json").exists());
    assert!(!rejected.join("experiment_lessons.jsonl").exists());
    assert!(!rejected.join("lesson_validations.jsonl").exists());
    fs::write(
        observation.join("source-stage/controls.cjs"),
        "changed observer",
    )
    .unwrap();
    assert!(reviewer::prepare(&observation, &rubric).is_err());
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
fn prospective_baseline_continuation_keeps_old_budget_and_reconstructs_original_failure() {
    use agentlab_code_analysis::maintainer_source_repair::{
        check, check_output, prepare_continuation,
    };
    let base = fixture();
    prepared(&base);
    let capture = captured(&base, 0, json!({"scenario":{"value":8,"nullable":null}}));
    let process_path = capture.join("process.json");
    let mut process: Value = serde_json::from_slice(&fs::read(&process_path).unwrap()).unwrap();
    for (key, value) in [
        ("cleanupExitCode", json!(0)),
        ("network", json!("none")),
        ("rootFilesystemReadOnly", json!(true)),
        ("capabilitiesDropped", json!(true)),
        ("durationMs", json!(206)),
    ] {
        process[key] = value;
    }
    file(&process_path, &process);
    let stage = base.join("stage");
    let inputs = base.join("inputs");
    let mut enrollment = json!({"schema":"agentlab.source_recipe_diagnostic_continuation_enrollment.v1",
        "enrollmentId":"prospective-test-only","maximumSuccessors":1,"participantBudgetSeconds":420,
        "transportRetryLimit":0,"designRevisionLimit":0,"codeRevisionLimit":0,
        "reviewed":true,"automaticPromotion":false});
    for (field, path) in [
        ("authorRequestSha256", stage.join("request.json")),
        ("parentStageReceiptSha256", stage.join("stage-receipt.json")),
        ("parentDesignSha256", stage.join("design.json")),
        ("parentProposalSha256", stage.join("proposal.json")),
        ("diagnosticIntentSha256", inputs.join("intent.json")),
        ("diagnosticProcessSha256", process_path),
        ("diagnosticStdoutSha256", capture.join("worker-stdout.log")),
        ("diagnosticStderrSha256", capture.join("worker-stderr.log")),
    ] {
        enrollment[field] = json!(digest(&fs::read(path).unwrap()));
    }
    let original_stage = fs::read(stage.join("stage-receipt.json")).unwrap();
    let enrolled = serde_json::to_vec(&enrollment).unwrap();
    let output = base.join("continuation.json");
    prepare_continuation(&stage, &inputs, &capture, &enrolled, &output).unwrap();
    let packet_bytes = fs::read(&output).unwrap();
    let packet: Value = serde_json::from_slice(&packet_bytes).unwrap();
    let request = fs::read(stage.join("request.json")).unwrap();
    let policy_path = base.join("prospective-enrollment.json");
    fs::write(&policy_path, &enrolled).unwrap();
    // Cross the actual ZIP selection -> Action preparation -> native consumer
    // boundary. Only GitHub acquisition is replaced; subprocess/native admission
    // must execute, otherwise missing retained sidecars can escape the test.
    let code = r#"
import argparse,importlib.util,json,os,subprocess,zipfile
from pathlib import Path
from unittest.mock import patch
base=Path(os.environ['FIXTURE_ROOT']);repo=Path(os.environ['REPOSITORY_ROOT'])
def load(name):
    spec=importlib.util.spec_from_file_location(name,repo/'scripts'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
acquisition=load('acquire-source-suite-review-input.py')
preparation=load('prepare-baseline-continuation-action.py')
envelope=dict(schema='agentlab.baseline_continuation_action_enrollment.v1',parentRun='123',
    parentArtifact='456',parentMethodRevision='a'*40,parentArchiveSha256='b'*64,
    continuationEnrollment=json.loads((base/'prospective-enrollment.json').read_bytes()))
(base/'action-enrollment.json').write_text(json.dumps(envelope))
captured_request='baseline-diagnostic/contained-input-original/request.json'
for scenario in ['good','missing-captured-request','changed-captured-request']:
    archive=base/(scenario+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('successor-request.json','original successor')
        bundle.writestr('successor-enrollment.json','original review')
        bundle.writestr('agent/participant-state/auth.json','excluded private state')
        for member in (base/'stage').iterdir():
            if member.is_file():bundle.write(member,'agent/proposal-stage/'+member.name)
        for name in ['intent.json','request.json','descriptor.json','support.json']:
            bundle.write(base/'inputs'/name,'baseline-diagnostic/'+name)
        for name in ['request.json','process.json','worker-stdout.log','worker-stderr.log']:
            target='baseline-diagnostic/contained-input-original/'+name
            if target==captured_request and scenario=='missing-captured-request':continue
            if target==captured_request and scenario=='changed-captured-request':bundle.writestr(target,'{}')
            else:bundle.write(base/'capture'/name,target)
    def acquire(args):
        args.output.mkdir()
        (args.output/'original-artifact.zip').write_bytes(archive.read_bytes())
        acquisition.extract_observations(archive,args.output/'baseline-inputs',baseline=True)
    args=argparse.Namespace(enrollment=base/'action-enrollment.json',output=base/('action-'+scenario),
        request=base/'stage/request.json',gate=Path(os.environ['NATIVE_GATE']),repository='generic/fixture')
    with patch.object(acquisition,'acquire',side_effect=acquire),patch.object(preparation,'module_from_spec',return_value=acquisition),patch.object(preparation,'spec_from_file_location') as spec:
        spec.return_value.loader.exec_module=lambda module:None
        try:result=preparation.prepare(args)
        except ValueError:assert scenario=='missing-captured-request'
        except subprocess.CalledProcessError:assert scenario=='changed-captured-request'
        else:
            assert scenario=='good'
            assert Path(result['diagnostic_repair']).read_bytes()==(base/'continuation.json').read_bytes()
            selected=args.output/'acquired/baseline-inputs'
            assert (selected/captured_request).read_bytes()==(base/'capture/request.json').read_bytes()
            assert not (selected/'agent/participant-state').exists()
        if scenario!='good':
            assert not (args.output/'diagnostic-repair.json').exists()
            assert not (args.output/'local-claims').exists()
print('actual baseline ZIP preparation and native captured-request admission passed')
"#;
    let reception = Command::new("python3")
        .args(["-c", code])
        .env("FIXTURE_ROOT", &base)
        .env("REPOSITORY_ROOT", root())
        .env(
            "NATIVE_GATE",
            env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"),
        )
        .output()
        .unwrap();
    assert!(
        reception.status.success(),
        "{}",
        String::from_utf8_lossy(&reception.stderr)
    );
    let cli_output = base.join("cli-continuation.json");
    let invoke = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--prepare-source-recipe-diagnostic-continuation")
            .arg("--stage")
            .arg(&stage)
            .arg("--diagnostic-inputs")
            .arg(&inputs)
            .arg("--worker-capture")
            .arg(&capture)
            .arg("--continuation-enrollment")
            .arg(&policy_path)
            .arg("--output")
            .arg(&cli_output)
            .output()
            .unwrap()
    };
    let executed = invoke();
    assert!(
        executed.status.success(),
        "{}",
        String::from_utf8_lossy(&executed.stderr)
    );
    assert_eq!(fs::read(&cli_output).unwrap(), packet_bytes);
    assert!(!invoke().status.success());
    assert_eq!(fs::read(&cli_output).unwrap(), packet_bytes);
    let admitted = check(&request, &packet_bytes).unwrap();
    assert_eq!(
        admitted["feedback"]["classification"],
        "baseline-observations-rejected"
    );
    assert_eq!(admitted["feedback"]["checks"][0]["actual"], 8);
    assert_eq!(admitted["semanticQualified"], false);
    assert!(packet["loopIntentOriginal"].is_null());
    assert_eq!(
        fs::read(stage.join("stage-receipt.json")).unwrap(),
        original_stage
    );
    assert!(!stage.join("diagnostic-loop-intent.json").exists());
    assert!(prepare_continuation(&stage, &inputs, &capture, &enrolled, &output).is_err());
    // The legacy path still requires its pre-generation allowance.
    assert!(agentlab_code_analysis::maintainer_source_repair::prepare(
        &stage,
        &inputs,
        &capture,
        1,
        &base.join("legacy.json")
    )
    .is_err());
    for (field, value) in [
        ("reviewed", json!(false)),
        ("maximumSuccessors", json!(2)),
        ("participantBudgetSeconds", json!(840)),
        ("transportRetryLimit", json!(1)),
        ("codeRevisionLimit", json!(1)),
        ("diagnosticStdoutSha256", json!("a".repeat(64))),
    ] {
        let mut bad = packet.clone();
        let mut policy = enrollment.clone();
        policy[field] = value;
        bad["continuationEnrollmentOriginal"] = json!(serde_json::to_string(&policy).unwrap());
        assert!(
            check(&request, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "{field}"
        );
    }
    for (field, value) in [
        ("maximumRepairs", json!(2)),
        ("repairIndex", json!(2)),
        ("previousRepairOriginal", json!("{}")),
        ("stdoutOriginal", json!("{}")),
    ] {
        let mut bad = packet.clone();
        bad[field] = value;
        assert!(
            check(&request, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "{field}"
        );
    }
    // Even a rehashed enrollment cannot admit unsafe/incomplete execution.
    for (field, value) in [
        ("timedOut", json!(true)),
        ("cleanupExitCode", json!(1)),
        ("durationMs", json!(0)),
        ("network", json!("bridge")),
        ("rootFilesystemReadOnly", json!(false)),
        ("exitCode", json!(1)),
    ] {
        let mut bad = packet.clone();
        let mut changed_process = process.clone();
        changed_process[field] = value;
        let raw = serde_json::to_string(&changed_process).unwrap();
        let mut policy = enrollment.clone();
        policy["diagnosticProcessSha256"] = json!(digest(raw.as_bytes()));
        bad["processOriginal"] = json!(raw);
        bad["continuationEnrollmentOriginal"] = json!(serde_json::to_string(&policy).unwrap());
        assert!(
            check(&request, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "{field}"
        );
    }
    let mut proposal: Value =
        serde_json::from_slice(&fs::read(stage.join("proposal.json")).unwrap()).unwrap();
    proposal["verifierSource"] = json!("changed candidate, not qualified");
    let design = fs::read(stage.join("design.json")).unwrap();
    assert!(check_output(
        &request,
        &packet_bytes,
        &serde_json::to_vec(&proposal).unwrap(),
        &design
    )
    .is_ok());
    proposal["contract"]["checks"][0]["expected"] = json!(8);
    assert!(check_output(
        &request,
        &packet_bytes,
        &serde_json::to_vec(&proposal).unwrap(),
        &design
    )
    .is_err());
    fs::remove_dir_all(base).unwrap();
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
