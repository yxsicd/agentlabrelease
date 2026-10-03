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
    let base = fixture();
    let stage = base.join("stage");
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
    fs::write(
        stage.join("design-runtime.cjs"),
        format!("const manifest = {manifest};\nmodule.exports=()=>({{}});"),
    )
    .unwrap();
    let mut receipt: Value =
        serde_json::from_slice(&fs::read(stage.join("stage-receipt.json")).unwrap()).unwrap();
    for (name, key) in [
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
        let actual =
            json!({"scenario":{"value":if id.starts_with("wrong") {8} else {7},"nullable":null}});
        let capture = captured_inputs(&inputs, &inputs.join("contained-input-fixture"), 0, actual);
        let report = feedback(&inputs, &capture, &inputs.join("feedback.json")).unwrap();
        rows.push(json!({"controlId":id,"role":if index==0 {"baseline"} else if id.starts_with("wrong") {"wrong"} else {"reference"},"recovery":index==ids.len()-1,
            "feedbackSha256":digest(&fs::read(inputs.join("feedback.json")).unwrap()),"classification":report["classification"],"declarationMatched":report["declarationMatched"]}));
    }
    file(
        &suite.join("result.json"),
        &json!({"schema":"agentlab.source_recipe_control_suite_result.v1","status":"declarations-matched",
        "attempts":rows,"designSha256":receipt["designSha256"],"diagnosticOnly":true,"qualified":false,"semanticQualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    );
    base
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
