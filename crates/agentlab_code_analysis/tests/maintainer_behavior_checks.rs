use agentlab_code_analysis::{digest, maintainer_behavior_checks::verify};
use serde_json::{json, Value};

fn fixture() -> (Value, Value) {
    let mut contract = json!({"schema":"agentlab.frozen_behavior_checks.v1","candidateId":"generic-task","candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),"originalSourceSha256":digest(b"baseline"),"methodSha256":"c".repeat(64),"compilerSha256":"d".repeat(64),"runtime":"test-runtime","workerDeadlineMs":1000,"checks":[{"id":"preserve","input":{"response":false},"expected":[1,"retained"]},{"id":"success","input":null,"expected":{"cleared":true}}],"controls":[],"automaticPromotion":false});
    let mut workers = Vec::new();
    let mut controls = Vec::new();
    for (id, role, failure) in [
        ("baseline", "baseline", Some("preserve")),
        ("valid-a", "accepted", None),
        ("valid-b", "accepted", None),
        ("wrong-a", "wrong", Some("preserve")),
        ("wrong-b", "wrong", Some("success")),
    ] {
        controls.push(json!({"id":id,"role":role,"submittedSourceSha256":digest(id.as_bytes()),"expectedFailedCheckIds":failure.map(|id| vec![id]).unwrap_or_default()}));
        let raw = json!({"id":id,"submittedSource":id,"submittedSourceSha256":digest(id.as_bytes()),"originalSourceSha256":digest(b"baseline"),"observations":contract["checks"].as_array().unwrap().iter().map(|check|json!({"id":check["id"],"input":check["input"],"actual":if failure==check["id"].as_str() {json!("wrong")} else {check["expected"].clone()},"expected":"producer cannot override contract","passed":true})).collect::<Vec<_>>()});
        let stdout = serde_json::to_string(&raw).unwrap();
        workers.push(json!({"id":id,"execution":{"stdoutSha256":digest(stdout.as_bytes()),"stdout":stdout,"exitCode":0,"timedOut":false,"durationMs":10}}));
    }
    contract["controls"] = json!(controls);
    let capture = json!({"schema":"agentlab.behavior_worker_capture.v1","contractSha256":digest(&serde_json::to_vec(&contract).unwrap()),"candidateId":contract["candidateId"],"candidateSha256":contract["candidateSha256"],"sourceRevision":contract["sourceRevision"],"methodSha256":contract["methodSha256"],"compilerSha256":contract["compilerSha256"],"runtime":contract["runtime"],"workers":workers});
    (contract, capture)
}
fn check(contract: &Value, capture: &Value) -> Result<Value, String> {
    verify(
        &serde_json::to_vec(contract).unwrap(),
        &serde_json::to_vec(capture).unwrap(),
    )
}
fn modify(capture: &mut Value, worker: usize, edit: impl FnOnce(&mut Value)) {
    let execution = &mut capture["workers"][worker]["execution"];
    let mut raw: Value = serde_json::from_str(execution["stdout"].as_str().unwrap()).unwrap();
    edit(&mut raw);
    let stdout = serde_json::to_string(&raw).unwrap();
    execution["stdoutSha256"] = json!(digest(stdout.as_bytes()));
    execution["stdout"] = json!(stdout);
}

#[test]
fn reconstructs_mixed_json_checks_without_trusting_producer_boolean_or_expected() {
    let (contract, capture) = fixture();
    let feedback = check(&contract, &capture).unwrap();
    assert_eq!(feedback["nextAction"], "execute-agent-attempt");
    assert_eq!(
        feedback["controls"][0]["failedCheckIds"],
        json!(["preserve"])
    );
    assert_eq!(feedback["qualified"], false);
    assert_eq!(feedback["producerAuthenticated"], false);
}

#[test]
fn killed_wrong_control_with_extra_failure_blocks_automatic_attempt_dispatch() {
    let (contract, mut capture) = fixture();
    modify(&mut capture, 3, |raw| {
        raw["observations"][1]["actual"] = json!({"cleared":false});
    });
    let feedback = check(&contract, &capture).unwrap();
    assert_eq!(
        feedback["controls"][3]["failedCheckIds"],
        json!(["preserve", "success"])
    );
    assert_eq!(feedback["calibrationRecordedContentPassed"], false);
    assert_eq!(feedback["nextAction"], "review-unexpected-control-failures");
    assert_eq!(feedback["qualified"], false);
    // The existing ordinary controller must stop before reading a recipe or
    // creating a dispatch directory, not merely report an informational flag.
    let out = loop_output_for_adapter();
    let error = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &serde_json::to_vec(&contract).unwrap(),
        &serde_json::to_vec(&capture).unwrap(),
        b"{}",
        &out,
    )
    .unwrap_err();
    assert!(error.contains("calibration not ready"));
    assert!(!out.exists());
    // Do not silently redefine the expected failures from observed output.
    // An explicitly frozen multi-failure control is still supported.
    let mut successor = contract.clone();
    successor["controls"][3]["expectedFailedCheckIds"] = json!(["preserve", "success"]);
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&successor).unwrap()));
    assert_eq!(
        check(&successor, &capture).unwrap()["nextAction"],
        "execute-agent-attempt"
    );
}

#[test]
fn operational_observations_do_not_invent_review_or_drop_failed_calibration() {
    let (mut contract, mut capture) = fixture();
    let candidate = json!({"id":"generic-task","repositoryId":"unrelated-library","sourceRevision":"b".repeat(40)});
    let candidate_bytes = serde_json::to_vec(&candidate).unwrap();
    contract["candidateSha256"] = json!(digest(&candidate_bytes));
    capture["candidateSha256"] = contract["candidateSha256"].clone();
    // A surviving wrong control is a retained observation, not a verified lesson.
    modify(&mut capture, 4, |raw| {
        raw["observations"][1]["actual"] = json!({"cleared":true})
    });
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    capture["contractSha256"] = json!(digest(&contract_bytes));
    let capture_bytes = serde_json::to_vec(&capture).unwrap();
    let build = || {
        agentlab_code_analysis::maintainer_behavior_checks::observation_assets(
            &candidate_bytes,
            &contract_bytes,
            &capture_bytes,
        )
        .unwrap()
    };
    let tables = build();
    assert_eq!(tables, build());
    for name in [
        "experiment_lessons",
        "lesson_evidence",
        "lesson_validations",
        "maintainer_skills",
        "program_facts",
    ] {
        assert!(!tables.contains_key(name));
    }
    assert_eq!(tables["checks"].len(), 10);
    assert_eq!(tables["evidence_files"].len(), 3);
    let run = tables["runs"].values().next().unwrap();
    assert_eq!(run["calibrationRecordedContentPassed"], false);
    assert_eq!(run["qualified"], false);
    let directory = loop_output_for_adapter();
    agentlab_code_analysis::maintainer_behavior_checks::export_observation(
        &candidate_bytes,
        &contract_bytes,
        &capture_bytes,
        &directory,
    )
    .unwrap();
    assert_eq!(
        std::fs::read(directory.join("behavior-capture.json")).unwrap(),
        capture_bytes
    );
    assert!(!directory.join("lesson-review.json").exists());
    assert!(
        agentlab_code_analysis::maintainer_behavior_checks::export_observation(
            &candidate_bytes,
            &contract_bytes,
            &capture_bytes,
            &directory
        )
        .is_err()
    );
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn behavior_lesson_requires_bound_review_and_independent_positive_negative_controls() {
    let (mut contract, mut capture) = fixture();
    let candidate = json!({"id":"generic-task","repositoryId":"unrelated-library","sourceRevision":"b".repeat(40)});
    let candidate_bytes = serde_json::to_vec(&candidate).unwrap();
    contract["candidateSha256"] = json!(digest(&candidate_bytes));
    capture["candidateSha256"] = contract["candidateSha256"].clone();
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    capture["contractSha256"] = json!(digest(&contract_bytes));
    let capture_bytes = serde_json::to_vec(&capture).unwrap();
    let review = json!({"schema":"agentlab.behavior_lesson_review.v1","reviewed":true,"automaticPromotion":false,
        "candidateSha256":digest(&candidate_bytes),"sourceRevision":candidate["sourceRevision"],
        "contractSha256":digest(&contract_bytes),"captureSha256":digest(&capture_bytes),
        "id":"reviewed-behavior","scope":"explicit seam","reviewerId":"operator-review",
        "phenomenon":"Boundary variants distinguish retained state","cause":"A declared outcome changes ownership",
        "change":"Observe both outcomes independently","factId":"fact-behavior","skillId":"skill-behavior",
        "body":"Check state transitions independently of startup.","skillStage":"evaluation"});
    let build = |candidate: &[u8], capture: &[u8], review: &Value| {
        agentlab_code_analysis::maintainer_behavior_checks::lesson_assets(
            candidate,
            &contract_bytes,
            capture,
            &serde_json::to_vec(review).unwrap(),
        )
    };
    let tables = build(&candidate_bytes, &capture_bytes, &review).unwrap();
    let lesson = &tables["experiment_lessons"]["reviewed-behavior"];
    assert_eq!(lesson["repositoryId"], "unrelated-library");
    assert_eq!(lesson["promotionContract"]["skillStage"], "evaluation");
    assert_eq!(
        lesson["promotionContract"]["qualification"]["learningBenefitVerified"],
        false
    );
    assert_eq!(tables["checks"].len(), 10);
    assert_eq!(tables["evidence_files"].len(), 4);
    // Exercise the public export and promotion boundary, not only the library.
    let root = loop_output_for_adapter();
    std::fs::create_dir(&root).unwrap();
    let root = root.canonicalize().unwrap();
    for (name, bytes) in [
        ("candidates.jsonl", candidate_bytes.clone()),
        ("contract.json", contract_bytes.clone()),
        ("capture.json", capture_bytes.clone()),
        ("review.json", serde_json::to_vec(&review).unwrap()),
    ] {
        std::fs::write(root.join(name), bytes).unwrap();
    }
    let exported = root.join("exported");
    let result =
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--export-behavior-lesson")
            .args([
                "--candidates",
                root.join("candidates.jsonl").to_str().unwrap(),
            ])
            .args(["--candidate-id", "generic-task"])
            .args(["--contract", root.join("contract.json").to_str().unwrap()])
            .args(["--capture", root.join("capture.json").to_str().unwrap()])
            .args([
                "--lesson-review",
                root.join("review.json").to_str().unwrap(),
            ])
            .args(["--output", exported.to_str().unwrap()])
            .output()
            .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        std::fs::read(exported.join("behavior-capture.json")).unwrap(),
        capture_bytes
    );
    // Synthetic committed-source metadata tests reconstruction, not remote authority.
    let export_path = exported.join("export.json");
    let mut export: Value = serde_json::from_slice(&std::fs::read(&export_path).unwrap()).unwrap();
    export["repository"] = json!("fixture-behavior-instance");
    export["revision"] = json!("e".repeat(40));
    export["tablePrefix"] = json!("data/");
    std::fs::write(&export_path, serde_json::to_vec(&export).unwrap()).unwrap();
    let knowledge = root.join("knowledge");
    std::fs::create_dir(&knowledge).unwrap();
    for table in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        std::fs::write(knowledge.join(format!("{table}.jsonl")), "").unwrap();
    }
    let promoted = root.join("promoted");
    let result = std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
        .env("GITHUB_SHA", "e".repeat(40))
        .arg("promote")
        .args([&exported, &knowledge, &promoted])
        .arg("reviewed-behavior")
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let skill: Value = serde_json::from_str(
        std::fs::read_to_string(promoted.join("maintainer_skills.jsonl"))
            .unwrap()
            .trim(),
    )
    .unwrap();
    assert_eq!(skill["stage"], "evaluation");
    assert_eq!(skill["repositoryId"], "unrelated-library");
    assert_eq!(skill["body"], review["body"]);
    assert_eq!(skill["automaticPromotion"], false);
    assert!(
        std::fs::read_to_string(promoted.join("evaluation_cases.jsonl"))
            .unwrap()
            .is_empty()
    );
    let base = root.join("admission-baseline");
    std::fs::create_dir(&base).unwrap();
    let mut cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1",
        "tableGitAuthority":{"repo":"fixture-knowledge","revision":"a".repeat(40)},"tables":{}});
    let mut round = json!({"id":"initial","roundIndex":1,"ownershipPlane":"target-operations",
        "automaticPromotion":false,"coverage":{"processSkillCount":0},"tables":{},
        "assessment":{"path":"fixture-assessment.json","sha256":"d".repeat(64)}});
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
            serde_json::to_vec(&json!({"id":"fixture-scope","repositoryId":candidate["repositoryId"],"sourceRevision":candidate["sourceRevision"]})).unwrap()
        } else {
            Vec::new()
        };
        std::fs::write(base.join(format!("{table}.jsonl")), &bytes).unwrap();
        cut["tables"][key] = json!({"path":format!("{table}.jsonl"),"sha256":digest(&bytes)});
        if !round_key.is_empty() {
            round["tables"][round_key] = json!(digest(&bytes));
        }
    }
    let history = serde_json::to_vec(&round).unwrap();
    std::fs::write(base.join("maintainer_skill_refresh_rounds.jsonl"), &history).unwrap();
    cut["tables"]["maintainerSkillRefreshRounds"] =
        json!({"path":"maintainer_skill_refresh_rounds.jsonl","sha256":digest(&history)});
    std::fs::write(
        base.join("maintainer-knowledge-cut.json"),
        serde_json::to_vec(&cut).unwrap(),
    )
    .unwrap();
    let prepare = || {
        agentlab_code_analysis::maintainer_lesson_admission::prepare(
            &base,
            &promoted,
            &exported,
            "reviewed-behavior",
            &"a".repeat(40),
        )
    };
    let plan = prepare().unwrap();
    assert_eq!(plan["authorityWritePerformed"], false);
    assert_eq!(
        plan["tables"]["maintainer_skills"]["row"]["stage"],
        "evaluation"
    );
    assert_eq!(plan["tables"].as_object().unwrap().len(), 3);
    let capture_path = exported.join("behavior-capture.json");
    let mut tampered = capture.clone();
    modify(&mut tampered, 3, |raw| {
        raw["observations"][0]["actual"] = contract["checks"][0]["expected"].clone()
    });
    std::fs::write(&capture_path, serde_json::to_vec(&tampered).unwrap()).unwrap();
    assert!(prepare().is_err());
    std::fs::write(&capture_path, &capture_bytes).unwrap();
    let skill_path = promoted.join("maintainer_skills.jsonl");
    let original_skill = std::fs::read(&skill_path).unwrap();
    let mut tampered_skill = skill.clone();
    tampered_skill["stage"] = json!("calibration");
    std::fs::write(&skill_path, serde_json::to_vec(&tampered_skill).unwrap()).unwrap();
    assert!(prepare().is_err());
    std::fs::write(&skill_path, original_skill).unwrap();
    assert_eq!(prepare().unwrap(), plan);
    // Continue through the actual consumer and ordinary business return gate.
    // All remote metadata below is synthetic; this tests composition, not a
    // live authority, fresh participant or complete productive flywheel round.
    let publication = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples/maintainer-knowledge-gate/first-four");
    let mut scope: Value = serde_json::from_str(
        std::fs::read_to_string(publication.join("maintainer_scope_skills.jsonl"))
            .unwrap()
            .lines()
            .next()
            .unwrap(),
    )
    .unwrap();
    scope["id"] = json!("fixture-scope");
    scope["repositoryId"] = candidate["repositoryId"].clone();
    scope["sourceRevision"] = candidate["sourceRevision"].clone();
    let scope_bytes = serde_json::to_vec(&scope).unwrap();
    std::fs::write(base.join("maintainer_scope_skills.jsonl"), &scope_bytes).unwrap();
    std::fs::create_dir(base.join("operation-evidence")).unwrap();
    std::fs::create_dir(base.join("assessments")).unwrap();
    let assessment = agentlab_code_analysis::maintainer_skill_flywheel::assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        1,
        None,
        Some(&base.join("operation-evidence")),
    )
    .unwrap();
    let assessment_bytes = serde_json::to_vec(&assessment).unwrap();
    std::fs::write(base.join("assessments/before.json"), &assessment_bytes).unwrap();
    round["assessment"] =
        json!({"path":"assessments/before.json","sha256":digest(&assessment_bytes)});
    round["tables"]["scopeSkillsSha256"] = json!(digest(&scope_bytes));
    let history = serde_json::to_vec(&round).unwrap();
    std::fs::write(base.join("maintainer_skill_refresh_rounds.jsonl"), &history).unwrap();
    cut["automaticPromotion"] = json!(false);
    cut["repositories"] =
        json!([{"id":candidate["repositoryId"],"revision":candidate["sourceRevision"]}]);
    let inventory = b"retained fixture inventory\n";
    std::fs::write(base.join("source-set.txt"), inventory).unwrap();
    cut["sourceSetSha256"] = json!(digest(inventory));
    cut["tables"]["maintainerScopeSkills"]["sha256"] = json!(digest(&scope_bytes));
    cut["tables"]["maintainerSkillRefreshRounds"]["sha256"] = json!(digest(&history));
    let cut_bytes = serde_json::to_vec(&cut).unwrap();
    std::fs::write(base.join("maintainer-knowledge-cut.json"), &cut_bytes).unwrap();
    let staged = root.join("return-stage");
    agentlab_code_analysis::maintainer_lesson_admission::stage(
        &base,
        &promoted,
        &exported,
        "reviewed-behavior",
        &"a".repeat(40),
        &staged,
    )
    .unwrap();
    fn copy_tree(from: &std::path::Path, to: &std::path::Path) {
        std::fs::create_dir(to).unwrap();
        for entry in std::fs::read_dir(from).unwrap() {
            let path = entry.unwrap().path();
            let target = to.join(path.file_name().unwrap());
            if path.is_dir() {
                copy_tree(&path, &target);
            } else {
                std::fs::copy(path, target).unwrap();
            }
        }
    }
    let next = root.join("committed-return-cut");
    copy_tree(&staged, &next);
    let mut next_cut: Value =
        serde_json::from_slice(&std::fs::read(next.join("maintainer-knowledge-cut.json")).unwrap())
            .unwrap();
    next_cut.as_object_mut().unwrap().remove("staging");
    next_cut["tableGitAuthority"]["revision"] = json!("c".repeat(40));
    let next_bytes = serde_json::to_vec(&next_cut).unwrap();
    std::fs::write(next.join("maintainer-knowledge-cut.json"), &next_bytes).unwrap();
    let query = |directory: &std::path::Path, name: &str, revision: &str, wrapped: bool| {
        let rows: Vec<Value> = std::fs::read_to_string(directory.join(format!("{name}.jsonl")))
            .unwrap()
            .lines()
            .filter(|line| !line.trim().is_empty())
            .map(|line| {
                let row: Value = serde_json::from_str(line).unwrap();
                json!({"key":row["id"],"row":if wrapped {json!({"payload":row})} else {row}})
            })
            .collect();
        json!({"revision":revision,"dirty":false,"truncated":false,
            "row_count":rows.len(),"returned_count":rows.len(),"rows":rows})
    };
    let mut readback = json!({"schema":"agentlab.reviewed_lesson_committed_readback.v1",
        "knowledgeRepository":"fixture-knowledge","previousRevision":"a".repeat(40),"revision":"c".repeat(40),
        "before":{"revision":"c".repeat(40),"dirty":false},"after":{"revision":"c".repeat(40),"dirty":false},
        "tables":{},"lessonSource":{"repository":export["repository"],"revision":export["revision"],"tablePrefix":export["tablePrefix"],"tables":{}}});
    for name in [
        "maintainer_skills",
        "maintainer_scope_skills",
        "program_facts",
        "maintainer_skill_refresh_rounds",
        "evaluation_cases",
    ] {
        readback["tables"][name] = query(&next, name, &"c".repeat(40), true);
    }
    for name in export["tables"].as_object().unwrap().keys() {
        readback["lessonSource"]["tables"][name] = query(&exported, name, &"e".repeat(40), false);
    }
    let save_ref = |name: &str, value: &Value| {
        let path = root.join(name);
        let bytes = serde_json::to_vec(value).unwrap();
        std::fs::write(&path, &bytes).unwrap();
        json!({"path":path,"sha256":digest(&bytes)})
    };
    let selection = json!({"schema":"agentlab.maintainer_guidance_selection.v1","automaticPromotion":false,
        "knowledgeCutSha256":digest(&next_bytes),"knowledgeRevision":"c".repeat(40),"stage":"evaluation",
        "sources":[{"repositoryId":candidate["repositoryId"],"sourceRevision":candidate["sourceRevision"]}],
        "skills":[{"id":skill["id"],"objectId":skill["objectId"],"rowSha256":digest(&serde_json::to_vec(&skill).unwrap()),"applicabilityReason":"Explicit fixture review of original behavior"}]});
    let selection_ref = save_ref("returned-selection.json", &selection);
    let return_input = json!({"reviewed":true,
        "knowledge":{"directory":next,"revision":"c".repeat(40),"cutSha256":digest(&next_bytes)},
        "guidanceSelection":selection_ref,"readback":save_ref("returned-readback.json", &readback)});
    let transport = json!({"authorityWrites":1,"revision":"c".repeat(40),"committedReadbackVerified":true,
        "sourceReadbackVerified":true,"nextGuidanceBound":true,"automaticFiveStageLoopCompleted":false,
        "nextGuidanceSelection":selection_ref,"committedReturn":return_input});
    let case = json!({"schema":"agentlab.flywheel_behavior_execution.v1","round":0,"taskPassed":false,
        "latestAttemptEvidence":{"contract":save_ref("return-contract.json", &contract),"capture":save_ref("return-capture.json", &capture)}});
    let case_ref = save_ref("returned-case.json", &case);
    let state = json!({"schema":"agentlab.flywheel_business_state.v1","automaticPromotion":false,
        "repositoryId":candidate["repositoryId"],"sourceRevision":candidate["sourceRevision"],"candidateId":candidate["id"],
        "knowledge":{"directory":base,"revision":"a".repeat(40),"cutSha256":digest(&cut_bytes)},
        "guidanceMode":"reviewed-bootstrap","bootstrapReview":{"reviewed":true,"knowledgeCutSha256":digest(&cut_bytes)},
        "stageEvidence":{"case-execution":{"path":case_ref["path"],"sha256":case_ref["sha256"],"status":"completed"}},
        "operationCapture":{"old":true},"behaviorExecution":{"old":true},
        "lessonAdmission":{"proposalDirectory":promoted,"lessonSourceDirectory":exported,"lessonId":"reviewed-behavior"}});
    let consumer_request = json!({"schema":"agentlab.reviewed_return_consumer_request.v1","reviewed":true,
        "automaticPromotion":false,"round":0,"inputState":save_ref("return-original-state.json", &state),
        "transportResult":save_ref("return-transport-result.json", &transport)});
    let output = root.join("consumed-return");
    let request_ref = save_ref("return-consumer-request.json", &consumer_request);
    let consumed_process =
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--consume-reviewed-return")
            .arg("--return-request")
            .arg(request_ref["path"].as_str().unwrap())
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap();
    assert!(
        consumed_process.status.success(),
        "{}",
        String::from_utf8_lossy(&consumed_process.stderr)
    );
    let consumed: Value = serde_json::from_slice(&consumed_process.stdout).unwrap();
    assert_eq!(
        consumed["businessResult"]["status"],
        "completed",
        "{}",
        std::fs::read_to_string(output.join("business/report.json")).unwrap()
    );
    assert_eq!(consumed["committedReturnConsumed"], true);
    assert_eq!(consumed["nextRoundScheduled"], false);
    let next_state: Value =
        serde_json::from_slice(&std::fs::read(output.join("business/state.json")).unwrap())
            .unwrap();
    assert_eq!(next_state["knowledge"]["revision"], "c".repeat(40));
    assert_eq!(next_state["guidanceSelection"], selection_ref);
    assert_eq!(
        next_state["priorRoundEvidence"]["case-execution"]["sha256"],
        case_ref["sha256"]
    );
    for key in [
        "candidateId",
        "lessonAdmission",
        "operationCapture",
        "behaviorExecution",
        "bootstrapReview",
    ] {
        assert!(next_state.get(key).is_none(), "{key}");
    }
    let fresh_stage_output = root.join("next-maintenance-stage");
    std::fs::create_dir(&fresh_stage_output).unwrap();
    let next_request = json!({"schema":"agentlab.flywheel_stage_request.v1","automaticPromotion":false,
        "round":1,"stage":"maintenance-verification","inputState":save_ref("next-returned-state.json", &next_state)});
    let stopped = agentlab_code_analysis::maintainer_flywheel_business::run(
        &serde_json::to_vec(&next_request).unwrap(),
        &fresh_stage_output,
    )
    .unwrap();
    assert_eq!(stopped["status"], "review-required");
    let stop_report: Value = serde_json::from_slice(
        &std::fs::read(fresh_stage_output.join("business/report.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(
        stop_report["gap"],
        "revision-bound-maintenance-operation-capture-required"
    );
    // A complete-looking producer cannot advance dirty captured authority.
    readback["after"]["dirty"] = json!(true);
    let mut bad_transport = transport.clone();
    bad_transport["committedReturn"]["readback"] =
        save_ref("return-dirty-readback.json", &readback);
    let mut bad_request = consumer_request.clone();
    bad_request["transportResult"] = save_ref("return-dirty-transport.json", &bad_transport);
    let rejected_output = root.join("rejected-consumer");
    let rejected = agentlab_code_analysis::maintainer_flywheel_business::consume_reviewed_return(
        &serde_json::to_vec(&bad_request).unwrap(),
        &rejected_output,
    )
    .unwrap();
    assert_eq!(rejected["committedReturnConsumed"], false);
    assert_eq!(rejected["businessResult"]["status"], "rejected");
    let unchanged: Value = serde_json::from_slice(
        &std::fs::read(rejected_output.join("business/state.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(unchanged["knowledge"], state["knowledge"]);
    let mut reused_round = consumer_request.clone();
    reused_round["round"] = json!(1);
    let old_round_result =
        agentlab_code_analysis::maintainer_flywheel_business::consume_reviewed_return(
            &serde_json::to_vec(&reused_round).unwrap(),
            &root.join("rejected-old-round"),
        )
        .unwrap();
    assert_eq!(old_round_result["committedReturnConsumed"], false);
    for (index, pointer) in ["/reviewed", "/transportResult/sha256"].iter().enumerate() {
        let mut bad = consumer_request.clone();
        *bad.pointer_mut(pointer).unwrap() = if *pointer == "/reviewed" {
            json!(false)
        } else {
            json!("0".repeat(64))
        };
        let bad_output = root.join(format!("rejected-consumer-preflight-{index}"));
        assert!(
            agentlab_code_analysis::maintainer_flywheel_business::consume_reviewed_return(
                &serde_json::to_vec(&bad).unwrap(),
                &bad_output
            )
            .is_err()
        );
        assert!(!bad_output.exists());
    }
    let mut already_returned = state.clone();
    already_returned["lessonAdmission"]["committedReturn"] = return_input;
    let mut overwrite = consumer_request.clone();
    overwrite["inputState"] = save_ref("already-returned-state.json", &already_returned);
    let overwrite_output = root.join("rejected-existing-return");
    assert!(
        agentlab_code_analysis::maintainer_flywheel_business::consume_reviewed_return(
            &serde_json::to_vec(&overwrite).unwrap(),
            &overwrite_output
        )
        .is_err()
    );
    assert!(!overwrite_output.exists());
    std::fs::remove_dir_all(&root).unwrap();
    for (key, value) in [
        ("reviewed", json!(false)),
        ("automaticPromotion", json!(true)),
        ("contractSha256", json!("f".repeat(64))),
        ("captureSha256", json!("f".repeat(64))),
        ("candidateSha256", json!("f".repeat(64))),
        ("sourceRevision", json!("f".repeat(40))),
        ("skillStage", json!("invented")),
        ("skillId", review["factId"].clone()),
    ] {
        let mut bad = review.clone();
        bad[key] = value;
        assert!(
            build(&candidate_bytes, &capture_bytes, &bad).is_err(),
            "{key}"
        );
    }
    let mut changed = candidate.clone();
    changed["repositoryId"] = json!("borrowed-library");
    assert!(build(
        &serde_json::to_vec(&changed).unwrap(),
        &capture_bytes,
        &review
    )
    .is_err());
    let mut surviving = capture.clone();
    modify(&mut surviving, 3, |raw| {
        raw["observations"][0]["actual"] = json!([1, "retained"])
    });
    let bytes = serde_json::to_vec(&surviving).unwrap();
    let mut revised = review.clone();
    revised["captureSha256"] = json!(digest(&bytes));
    assert!(build(&candidate_bytes, &bytes, &revised).is_err());
    let mut contaminated = capture.clone();
    modify(&mut contaminated, 3, |raw| {
        raw["observations"][1]["actual"] = json!({"cleared":false});
    });
    let bytes = serde_json::to_vec(&contaminated).unwrap();
    revised["captureSha256"] = json!(digest(&bytes));
    // An otherwise complete, digest-bound review cannot promote a killed
    // control with unaccounted extra failures into maintained knowledge.
    assert!(build(&candidate_bytes, &bytes, &revised).is_err());
}

#[test]
fn distinguishes_valid_control_and_surviving_wrong_control_failures() {
    let (contract, mut capture) = fixture();
    modify(&mut capture, 1, |raw| {
        raw["observations"][0]["actual"] = json!(false)
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-valid-controls"
    );
    let (_, mut capture) = fixture();
    modify(&mut capture, 3, |raw| {
        raw["observations"][0]["actual"] = json!([1, "retained"])
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-oracle-or-wrong-controls"
    );
}

#[test]
fn infrastructure_or_incomplete_capture_never_counts_as_behavior_failure() {
    for scenario in [
        "exit",
        "timeout",
        "deadline",
        "stdout",
        "missing",
        "duplicate",
        "input",
        "source",
    ] {
        let (contract, mut capture) = fixture();
        match scenario {
            "exit" => capture["workers"][3]["execution"]["exitCode"] = json!(1),
            "timeout" => capture["workers"][3]["execution"]["timedOut"] = json!(true),
            "deadline" => capture["workers"][3]["execution"]["durationMs"] = json!(1001),
            "stdout" => capture["workers"][3]["execution"]["stdoutSha256"] = json!("0".repeat(64)),
            "missing" => modify(&mut capture, 3, |raw| {
                raw["observations"].as_array_mut().unwrap().pop();
            }),
            "duplicate" => modify(&mut capture, 3, |raw| {
                raw["observations"][1] = raw["observations"][0].clone();
            }),
            "input" => modify(&mut capture, 3, |raw| {
                raw["observations"][1]
                    .as_object_mut()
                    .unwrap()
                    .remove("input");
            }),
            _ => modify(&mut capture, 3, |raw| {
                raw["submittedSource"] = json!("swapped source")
            }),
        }
        assert!(check(&contract, &capture).is_err(), "{scenario}");
    }
}

#[test]
fn rejects_changed_contract_identity_and_duplicate_valid_sources() {
    let (mut contract, capture) = fixture();
    contract["checks"][0]["expected"] = json!("new expected after execution");
    assert!(check(&contract, &capture).is_err());
    let (contract, mut capture) = fixture();
    capture["runtime"] = json!("other-runtime");
    assert!(check(&contract, &capture).is_err());
    let (mut contract, mut capture) = fixture();
    contract["controls"][2]["submittedSourceSha256"] =
        contract["controls"][1]["submittedSourceSha256"].clone();
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&contract).unwrap()));
    assert!(check(&contract, &capture).is_err());
}

#[test]
fn lesson_exports_passing_and_rejected_attempts_without_calibration_or_identity_claims() {
    let (mut contract, mut capture) = fixture();
    let candidate = json!({"id":"generic-task","repositoryId":"another-repository","sourceRevision":"b".repeat(40)});
    let candidate_bytes = serde_json::to_vec(&candidate).unwrap();
    contract["candidateSha256"] = json!(digest(&candidate_bytes));
    capture["candidateSha256"] = contract["candidateSha256"].clone();
    for (name, failing) in [("attempt-pass", false), ("attempt-reject", true)] {
        contract["controls"].as_array_mut().unwrap().push(json!({"id":name,"role":"agent-attempt","submittedSourceSha256":digest(name.as_bytes()),"expectedFailedCheckIds":[]}));
        let mut worker = capture["workers"][1].clone();
        worker["id"] = json!(name);
        capture["workers"].as_array_mut().unwrap().push(worker);
        let index = capture["workers"].as_array().unwrap().len() - 1;
        modify(&mut capture, index, |raw| {
            raw["id"] = json!(name);
            raw["submittedSource"] = json!(name);
            raw["submittedSourceSha256"] = json!(digest(name.as_bytes()));
            if failing {
                raw["observations"][1]["actual"] = json!({"cleared":false});
            }
        });
    }
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    capture["contractSha256"] = json!(digest(&contract_bytes));
    let capture_bytes = serde_json::to_vec(&capture).unwrap();
    let review = json!({"schema":"agentlab.behavior_lesson_review.v1","reviewed":true,"automaticPromotion":false,
        "candidateSha256":digest(&candidate_bytes),"sourceRevision":candidate["sourceRevision"],
        "contractSha256":digest(&contract_bytes),"captureSha256":digest(&capture_bytes),
        "id":"review","scope":"seam","reviewerId":"operator","phenomenon":"observed",
        "cause":"reviewed interpretation","change":"retain outcomes","factId":"fact","skillId":"skill",
        "body":"Preserve rejected outcomes.","skillStage":"evaluation"});
    let build = || {
        agentlab_code_analysis::maintainer_behavior_checks::lesson_assets(
            &candidate_bytes,
            &contract_bytes,
            &capture_bytes,
            &serde_json::to_vec(&review).unwrap(),
        )
        .unwrap()
    };
    let tables = build();
    assert_eq!(tables, build());
    assert_eq!(tables["calibration_controls"].len(), 5);
    assert_eq!(tables["attempts"].len(), 2);
    assert_eq!(tables["checks"].len(), 14);
    for attempt in tables["attempts"].values() {
        let passing = attempt["variant"] == "attempt-pass";
        assert_eq!(attempt["behaviorPassed"], passing);
        assert_eq!(
            attempt["submittedSourceSha256"],
            digest(attempt["variant"].as_str().unwrap().as_bytes())
        );
        for field in [
            "participantCompletionVerified",
            "producerAuthenticated",
            "qualified",
        ] {
            assert_eq!(attempt[field], false);
        }
        let checks: Vec<_> = tables["checks"]
            .values()
            .filter(|row| row["attemptId"] == attempt["id"])
            .collect();
        assert_eq!(checks.len(), 2);
        assert!(checks.iter().all(|row| row["controlId"].is_null()));
        assert_eq!(
            checks.iter().filter(|row| row["passed"] == false).count(),
            if passing { 0 } else { 1 }
        );
    }
    assert_eq!(
        tables["experiment_lessons"]["review"]["promotionContract"]["expected"]
            .as_object()
            .unwrap()
            .len(),
        5
    );
    assert_eq!(
        tables["lesson_evidence"].values().next().unwrap()["attemptIds"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
}

#[test]
fn agent_outcomes_retain_every_frozen_check_and_select_behavioral_repair() {
    let (mut contract, mut capture) = fixture();
    contract["controls"].as_array_mut().unwrap().push(json!({"id":"agent","role":"agent-attempt","submittedSourceSha256":digest(b"agent subject"),"expectedFailedCheckIds":[]}));
    let mut worker = capture["workers"][1].clone();
    worker["id"] = json!("agent");
    capture["workers"].as_array_mut().unwrap().push(worker);
    modify(&mut capture, 5, |raw| {
        raw["id"] = json!("agent");
        raw["submittedSource"] = json!("agent subject");
        raw["submittedSourceSha256"] = json!(digest(b"agent subject"));
    });
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&contract).unwrap()));
    let success = check(&contract, &capture).unwrap();
    assert_eq!(success["nextAction"], "review-agent-outcome");
    assert_eq!(success["qualified"], false);
    modify(&mut capture, 5, |raw| {
        raw["observations"][1]["actual"] = json!({"cleared":false})
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-agent-behavior"
    );
    modify(&mut capture, 5, |raw| {
        raw["observations"].as_array_mut().unwrap().pop();
    });
    assert!(check(&contract, &capture).is_err());
}

#[cfg(unix)]
fn loop_fixture(failing_executor: bool, repeat: bool) -> (Vec<u8>, Vec<u8>, Vec<u8>) {
    let (contract, capture) = fixture();
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    let capture_bytes = serde_json::to_vec(&capture).unwrap();
    let command = |script: String| json!({"program":"/bin/sh","programSha256":digest(&std::fs::read("/bin/sh").unwrap()),"args":["-c",script,"adapter","{request}"],"cwd":".","timeoutMs":1000});
    let raw = |number: usize, source: &str, failed: bool| {
        serde_json::to_string(&json!({"id":format!("agent-attempt-{number}"),"submittedSource":source,"submittedSourceSha256":digest(source.as_bytes()),"originalSourceSha256":contract["originalSourceSha256"],"observations":contract["checks"].as_array().unwrap().iter().map(|c| json!({"id":c["id"],"input":c["input"],"actual":if failed && c["id"]=="preserve" {json!("wrong")} else {c["expected"].clone()}})).collect::<Vec<_>>()})).unwrap()
    };
    let participant = if repeat {
        "printf '%s' '{\"submittedSource\":\"bad subject\"}'".into()
    } else {
        "case \"$1\" in *attempt-0*) printf '%s' '{\"submittedSource\":\"bad subject\"}';; *) printf '%s' '{\"submittedSource\":\"valid-a\"}';; esac".into()
    };
    let executor = if failing_executor {
        "exit 9".into()
    } else {
        format!(
            "case \"$1\" in *attempt-0*) printf '%s' '{}';; *) printf '%s' '{}';; esac",
            raw(0, "bad subject", true),
            raw(1, "valid-a", false)
        )
    };
    let recipe = json!({"schema":"agentlab.behavior_loop_recipe.v1","reviewed":true,"automaticPromotion":false,"contractSha256":digest(&contract_bytes),"captureSha256":digest(&capture_bytes),"taskDemand":"Preserve data on failure and clear on success.","maximumAttempts":2,"immutableInputs":[],"participantCommand":command(participant),"executorCommand":command(executor)});
    (
        contract_bytes,
        capture_bytes,
        serde_json::to_vec(&recipe).unwrap(),
    )
}

#[cfg(unix)]
fn loop_output(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "agentlab-behavior-loop-{label}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[test]
#[cfg(unix)]
fn real_subprocess_loop_delivers_failed_feedback_then_rechecks_repaired_subject() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let out = loop_output("repair");
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out,
    )
    .unwrap();
    assert_eq!(result["status"], "recorded-attempt-passed");
    assert_eq!(result["attempts"].as_array().unwrap().len(), 2);
    assert_eq!(result["attempts"][0]["nextAction"], "repair-agent-behavior");
    let repair: Value = serde_json::from_slice(
        &std::fs::read(out.join("attempt-1/participant-request.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(repair["submittedSource"], "bad subject");
    assert_eq!(repair["feedback"]["nextAction"], "repair-agent-behavior");
    assert_eq!(
        result["latestFeedback"]["nextAction"],
        "review-agent-outcome"
    );
    assert_eq!(result["participantAuthenticated"], false);
    assert_eq!(result["qualified"], false);
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out
    )
    .is_err());
}

#[test]
#[cfg(unix)]
fn loop_stops_infrastructure_and_suppresses_identical_failed_subject() {
    let (contract, capture, recipe) = loop_fixture(true, false);
    let out = loop_output("infrastructure");
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out
    )
    .unwrap_err()
    .contains("infrastructure"));
    assert!(!out.join("attempt-1").exists());
    assert!(out.join("attempt-0/executor.json").is_file());
    let (contract, capture, recipe) = loop_fixture(false, true);
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &recipe,
        &loop_output("repeat"),
    )
    .unwrap();
    assert_eq!(result["status"], "unchanged-attempt-suppressed");
    assert_eq!(result["attempts"].as_array().unwrap().len(), 1);
}

#[test]
#[cfg(unix)]
fn participant_cannot_rewrite_frozen_checks_before_executor_dispatch() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    recipe["participantCommand"]["args"][1] = json!(
        "printf corrupt > ../frozen-contract.json; printf '%s' '{\"submittedSource\":\"valid-a\"}'"
    );
    let out = loop_output("tamper");
    let error = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap_err();
    assert!(error.contains("immutable input changed"));
    assert!(out.join("attempt-0/participant.json").is_file());
    assert!(!out.join("attempt-0/executor.json").exists());
}

#[test]
#[cfg(unix)]
fn nested_gateway_capture_is_retained_and_later_mutation_is_rejected() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    let original = recipe["participantCommand"]["args"][1]
        .as_str()
        .unwrap()
        .to_owned();
    recipe["participantCommand"]["args"][1]=json!(format!("mkdir -p participant-evidence/gateway; printf capture > participant-evidence/gateway/1.capture; {original}"));
    let out = loop_output("nested");
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap();
    assert_eq!(result["status"], "recorded-attempt-passed");
    assert_eq!(
        std::fs::read(out.join("attempt-0/participant-evidence/gateway/1.capture")).unwrap(),
        b"capture"
    );
    recipe["participantCommand"]["args"][1]=json!(format!("mkdir -p participant-evidence/gateway; printf capture > participant-evidence/gateway/1.capture; case \"$1\" in *attempt-1*) printf changed > ../attempt-0/participant-evidence/gateway/1.capture;; esac; {original}"));
    let out = loop_output("nested-tamper");
    let error = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap_err();
    assert!(error.contains("immutable input changed"));
    assert!(!out.join("attempt-1/executor.json").exists());
}

#[test]
#[cfg(unix)]
fn participant_environment_is_explicit_and_never_inherited_by_executor() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    let previous = std::env::var_os("AGENTLAB_MODEL");
    std::env::set_var("AGENTLAB_MODEL", "controller-test");
    recipe["participantEnvironmentNames"] = json!(["AGENTLAB_MODEL"]);
    let participant = recipe["participantCommand"]["args"][1].as_str().unwrap();
    recipe["participantCommand"]["args"][1] = json!(format!(
        "test \"$AGENTLAB_MODEL\" = controller-test || exit 44; {participant}"
    ));
    let executor = recipe["executorCommand"]["args"][1].as_str().unwrap();
    recipe["executorCommand"]["args"][1] = json!(format!(
        "test -z \"${{AGENTLAB_MODEL+x}}\" || exit 43; {executor}"
    ));
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &loop_output("environment"),
    );
    match previous {
        Some(value) => std::env::set_var("AGENTLAB_MODEL", value),
        None => std::env::remove_var("AGENTLAB_MODEL"),
    }
    assert_eq!(result.unwrap()["status"], "recorded-attempt-passed");
    recipe["participantEnvironmentNames"] = json!(["UNREVIEWED_SECRET"]);
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &loop_output("bad-environment")
    )
    .unwrap_err()
    .contains("not allowed"));
}

#[test]
#[cfg(unix)]
fn required_participant_completion_rejects_plain_subprocess_before_behavior_execution() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    recipe["participantCompletionRequired"] = json!(true);
    let out = loop_output("completion");
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out
    )
    .is_err());
    assert!(out.join("attempt-0/participant.json").is_file());
    assert!(!out.join("attempt-0/executor.json").exists());
}

#[test]
fn pi_adapter_protocol_fixture_binds_request_capture_submission_and_watchdog() {
    for guided in [false, true] {
        let out = loop_output_for_adapter();
        std::fs::create_dir(&out).unwrap();
        let mut request = json!({"schema":"agentlab.behavior_participant_request.v1","guidanceMode":"unguided","submittedSource":"baseline","taskDemand":"repair task","automaticPromotion":false});
        if guided {
            let skill =
                json!({"id":"fixture-skill","body":"Retain ownership until the declared release."});
            request["guidanceMode"] = json!("guided");
            request["maintainerGuidance"] = json!({"schema":"agentlab.maintainer_guidance_packet.v1",
            "knowledgeAuthority":{"repo":"fixture-knowledge","revision":"a".repeat(40)},
            "guidance":[{"skill":skill,"rowSha256":digest(&serde_json::to_vec(&skill).unwrap()),
                "bodySha256":digest(skill["body"].as_str().unwrap().as_bytes())}],"automaticPromotion":false});
        }
        let bytes = serde_json::to_vec(&request).unwrap();
        std::fs::write(out.join("request.json"), &bytes).unwrap();
        let adapter = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../examples/real-code-agent/behavior-participant.py");
        let result=std::process::Command::new("python3").current_dir(&out).args(["-c",r#"
import importlib.util,importlib.abc,json,sys,hashlib,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('behavior',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class FakeParticipant:
 def __init__(self,evidence,state,binary,gateway,model,route,reasoning_effort,gateway_timeout_seconds):
  assert gateway_timeout_seconds==60
  receipts=Path(os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT']).resolve(strict=True)
  assert receipts.is_dir() and receipts== (evidence/'runtime').resolve(strict=True)
  assert not list(receipts.iterdir())
  self.evidence=evidence;self.model=model;self.route=route;self.implementation='pi';self.reasoning_effort=None
 def _run_turn(self,*args,**kwargs): assert kwargs['timeout_seconds']==120
 def turn(self,label,workspace,prompt,tool_call_limit,transport_retry_limit):
  assert tool_call_limit==12 and transport_retry_limit==0
  self._run_turn()
  (workspace/'submitted-source.txt').write_text('valid-a')
  e=self.evidence;(e/'author-calibration-prompt.txt').write_text(prompt)
  final=b'{"role":"assistant","content":[]}'
  (e/'author-calibration-final-assistant-message.json').write_bytes(final)
  (e/'author-calibration-lifecycle.json').write_text(json.dumps({'label':label,'captureAuthority':'operator','exitCode':0,'timedOut':False,
   'participantBudgetSeconds':120,'participantBudgetScope':'native-process-watchdog','transportRetryLimit':0,
   'finalAssistantMessagePresent':True,'finalAssistantMessageSha256':hashlib.sha256(final).hexdigest()}))
  g=e/'gateway';g.mkdir()
  (g/'0001.upstream-request.json').write_text(json.dumps({'model':self.model,'providerId':self.route,'stream':True,'messages':[{'role':'user','content':prompt}]}))
  response=b'data: {"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
  (g/'0001.response').write_bytes(response)
  (g/'0001.status.json').write_text(json.dumps({'exchangeId':'0001','status':200,'durationMs':1,'upstreamEof':True,'semanticComplete':True,'outcome':'completed','streamError':None,'responseBytes':len(response)}))
 def close(self):pass
class Loader(importlib.abc.Loader):
 def create_module(self,spec):return None
 def exec_module(self,module):module.Participant=FakeParticipant
m.importlib.util.spec_from_file_location=lambda name,path:importlib.util.spec_from_loader(name,Loader())
sys.argv=['adapter','request.json'];m.main()
"#]).arg(adapter).env("AGENTLAB_PI_BINARY","fixture-pi").env("AGENTLAB_LM_GATEWAY_URL","http://fixture.invalid").env("AGENTLAB_MODEL","fixture-model").env("AGENTLAB_PROVIDER_ROUTE","fixture-route").env("AGENTLAB_PARTICIPANT_RUNTIME_CONFIG","fixture-runtime-config").output().unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let output: Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(output["submittedSource"], "valid-a");
        assert_eq!(
            std::fs::read(out.join("participant-evidence/behavior-submitted-source.txt")).unwrap(),
            b"valid-a"
        );
        let completion = if guided {
            agentlab_code_analysis::maintainer_guidance::guided_completion(
                &out.join("participant-evidence"),
                &bytes,
            )
        } else {
            agentlab_code_analysis::maintainer_guidance::completion(
                &out.join("participant-evidence"),
                &bytes,
            )
        }
        .unwrap();
        if guided {
            assert_eq!(completion["agentConsumptionVerified"], true);
            assert!(agentlab_code_analysis::maintainer_guidance::completion(
                &out.join("participant-evidence"),
                &bytes
            )
            .is_err());
        } else {
            assert_eq!(completion["authorCompletionVerified"], true);
        }
        assert_eq!(completion["participantBudgetSeconds"], 120);
        assert_eq!(completion["producerAuthenticated"], false);
    }
}

fn loop_output_for_adapter() -> std::path::PathBuf {
    static NEXT_OUTPUT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    std::env::temp_dir().join(format!(
        "agentlab-behavior-adapter-{}-{}-{}",
        std::process::id(),
        NEXT_OUTPUT.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[cfg(unix)]
#[test]
fn action_transport_exports_actual_failed_and_passing_attempts_without_lessons() {
    use std::{fs, process::Command};
    let root = loop_output_for_adapter();
    fs::create_dir(&root).unwrap();
    let root = root.canonicalize().unwrap();
    let candidate = json!({"id":"generic-task","repositoryId":"arbitrary-project","sourceRevision":"b".repeat(40)});
    let candidate_bytes = serde_json::to_vec(&candidate).unwrap();
    fs::write(root.join("candidates.jsonl"), &candidate_bytes).unwrap();
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut contract: Value = serde_json::from_slice(&contract).unwrap();
    let mut capture: Value = serde_json::from_slice(&capture).unwrap();
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    contract["candidateSha256"] = json!(digest(&candidate_bytes));
    let contract = serde_json::to_vec(&contract).unwrap();
    capture["candidateSha256"] = json!(digest(&candidate_bytes));
    capture["contractSha256"] = json!(digest(&contract));
    let capture = serde_json::to_vec(&capture).unwrap();
    recipe["contractSha256"] = json!(digest(&contract));
    recipe["captureSha256"] = json!(digest(&capture));
    agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &root.join("attempts"),
    )
    .unwrap();
    let script = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/export-behavior-loop-observations.cjs");
    let invoke = |output: &str| {
        Command::new("node")
            .arg(&script)
            .arg("--attempts")
            .arg(root.join("attempts"))
            .arg("--candidates")
            .arg(root.join("candidates.jsonl"))
            .args(["--candidate-id", "generic-task", "--flywheel-tool"])
            .arg(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--output")
            .arg(root.join(output))
            .output()
            .unwrap()
    };
    let result = invoke("observations");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let index: Value =
        serde_json::from_slice(&fs::read(root.join("observations/export-index.json")).unwrap())
            .unwrap();
    assert_eq!(index["exports"].as_array().unwrap().len(), 2);
    assert_eq!(index["remotePersistenceVerified"], false);
    assert_eq!(index["lessonCreated"], false);
    for n in 0..2 {
        let out = root.join(format!("observations/attempt-{n}"));
        assert!(!out.join("experiment_lessons.jsonl").exists());
        let attempts = fs::read_to_string(out.join("attempts.jsonl")).unwrap();
        let row: Value = serde_json::from_str(attempts.trim()).unwrap();
        assert_eq!(row["behaviorPassed"], n == 1);
        assert_eq!(
            fs::read(out.join("behavior-capture.json")).unwrap(),
            fs::read(root.join(format!("attempts/attempt-{n}/attempt-capture.json"))).unwrap()
        );
    }
    assert!(!invoke("observations").status.success());
    assert!(invoke("repeat").status.success());
    assert_eq!(
        fs::read(root.join("observations/export-index.json")).unwrap(),
        fs::read(root.join("repeat/export-index.json")).unwrap()
    );
    let path = root.join("attempts/attempt-0/feedback.json");
    fs::write(path, b"{}").unwrap();
    assert!(!invoke("changed").status.success());
    assert!(!root.join("changed").exists());
    fs::rename(
        root.join("attempts/loop-result.json"),
        root.join("retained-loop-result.json"),
    )
    .unwrap();
    let incomplete = invoke("incomplete");
    assert!(incomplete.status.success());
    let status: Value = serde_json::from_slice(&incomplete.stdout).unwrap();
    assert_eq!(status["observationExported"], false);
    assert!(!root.join("incomplete").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn contained_worker_rejects_unreviewed_or_changed_input_before_runtime() {
    let script = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/run-contained-behavior-worker.py");
    for (label, reviewed, source_sha, image, message) in [
        (
            "unreviewed",
            false,
            digest(b"source"),
            "invalid",
            "not reviewed",
        ),
        (
            "changed",
            true,
            "0".repeat(64),
            "invalid",
            "submitted source differs",
        ),
        (
            "image",
            true,
            digest(b"source"),
            "invalid",
            "exact local ID",
        ),
    ] {
        let dir = loop_output_for_adapter();
        std::fs::create_dir(&dir).unwrap();
        let dir = dir.canonicalize().unwrap();
        std::fs::write(dir.join("descriptor.json"),serde_json::to_vec(&json!({"schema":"agentlab.contained_behavior_executor.v1","reviewed":reviewed,"automaticPromotion":false,"imageId":image})).unwrap()).unwrap();
        std::fs::write(dir.join("request.json"),serde_json::to_vec(&json!({"schema":"agentlab.behavior_executor_request.v1","submittedSource":"source","submittedSourceSha256":source_sha})).unwrap()).unwrap();
        let result = std::process::Command::new("python3")
            .arg(&script)
            .arg(dir.join("descriptor.json"))
            .arg(dir.join("request.json"))
            .current_dir(&dir)
            .output()
            .unwrap();
        assert!(!result.status.success(), "{label}");
        assert!(
            String::from_utf8_lossy(&result.stderr).contains(message),
            "{label}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(std::fs::read_dir(dir).unwrap().count(), 2);
    }
}

#[test]
fn lifecycle_worker_executes_owned_zero_id_recreation_and_retry_behavior() {
    let repository = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let profile: Value = serde_json::from_slice(&std::fs::read(repository.join(
        "examples/maintainer-knowledge-gate/reviewed-behavior/environment-lifecycle-demand.json",
    )).unwrap()).unwrap();
    let dir = loop_output_for_adapter();
    std::fs::create_dir(&dir).unwrap();
    let compiler = dir.join("compiler.cjs");
    // JavaScript-only protocol fixture, not TypeScript/Harmony qualification.
    let compiler_bytes = b"module.exports={ModuleKind:{CommonJS:1},ScriptTarget:{ES2022:9},DiagnosticCategory:{Error:1},flattenDiagnosticMessageText(message){return message},transpileModule(source){return{outputText:source,diagnostics:source.includes('SYNTAX_REJECTED')?[{category:1,code:1128,file:{text:source},start:source.length-1,length:1,messageText:'Declaration or statement expected.'}]:source.includes('UNBOUND_COMPILER')?[{category:1,code:5107,messageText:'Compiler configuration error'}]:[]}}};";
    std::fs::write(&compiler, compiler_bytes).unwrap();
    let mut support = profile["supportFields"].clone();
    support["compilerSha256"] = json!(digest(compiler_bytes));
    std::fs::write(
        dir.join("support.json"),
        serde_json::to_vec(&support).unwrap(),
    )
    .unwrap();
    let valid = r#"// [Start myAbility_start]
exports.default = class extends require('@kit.AbilityKit').AbilityStage {
  id;
  onCreate() {
    if (this.id !== undefined) return;
    try {
      this.id = this.context.getApplicationContext().on('environment', {
        onConfigurationUpdated(config) { console.info('envCallback onConfigurationUpdated success: '+JSON.stringify(config)); },
        onMemoryLevel(level) { console.info('onMemoryLevel level: '+level); }
      });
    } catch (error) {}
  }
  onDestroy() {
    if (this.id !== undefined) {
      this.context.getApplicationContext().off('environment', this.id);
      this.id = undefined;
    }
  }
};
// [End myAbility_start]
"#;
    for (id, source, intended_failure) in [
        ("valid", valid.to_string(), None),
        (
            "syntax-rejected",
            format!("{valid}// SYNTAX_REJECTED\n}}"),
            Some("destroy-zero"),
        ),
        (
            "unbound-compiler",
            format!("{valid}// UNBOUND_COMPILER"),
            Some("destroy-zero"),
        ),
        (
            "zero-skipped",
            valid.replace("if (this.id !== undefined) {", "if (this.id) {"),
            Some("destroy-zero"),
        ),
        (
            "stale-owner",
            valid.replace("this.id = undefined;", "this.id = this.id;"),
            Some("recreate-positive"),
        ),
        (
            "duplicate",
            valid.replace(
                "if (this.id !== undefined) return;",
                "/* no duplicate guard */",
            ),
            Some("repeat-create-zero"),
        ),
    ] {
        let checks: Vec<_> = profile["checks"]
            .as_array()
            .unwrap()
            .iter()
            .map(|check| json!({"id":check["id"],"input":check["input"]}))
            .collect();
        let request = json!({"schema":"agentlab.behavior_executor_request.v1","id":id,
            "originalSourceSha256":digest(valid.as_bytes()),"submittedSource":source,
            "submittedSourceSha256":digest(source.as_bytes()),"checks":checks});
        let request_path = dir.join(format!("{id}.json"));
        std::fs::write(&request_path, serde_json::to_vec(&request).unwrap()).unwrap();
        let result = std::process::Command::new("node")
            .arg(repository.join("scripts/environment-lifecycle-worker.cjs"))
            .arg(request_path)
            .arg(dir.join("support.json"))
            .arg(&compiler)
            .output()
            .unwrap();
        if id == "unbound-compiler" {
            assert!(!result.status.success());
            assert!(String::from_utf8_lossy(&result.stderr).contains("Unbound compiler diagnostic"));
            assert!(result.stdout.is_empty());
            continue;
        }
        assert!(
            result.status.success(),
            "{id}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        let actual: Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(actual["id"], id);
        assert_eq!(
            actual["submittedSourceSha256"],
            request["submittedSourceSha256"]
        );
        assert_eq!(
            actual["observations"].as_array().unwrap().len(),
            checks.len()
        );
        let mut failed = Vec::new();
        for (expected, observed) in profile["checks"]
            .as_array()
            .unwrap()
            .iter()
            .zip(actual["observations"].as_array().unwrap())
        {
            assert_eq!(observed["input"], expected["input"]);
            if observed["actual"] != expected["expected"] {
                failed.push(expected["id"].as_str().unwrap());
            }
        }
        match intended_failure {
            None => assert!(failed.is_empty(), "{failed:?}"),
            Some(check) => assert!(failed.contains(&check), "{id}: {failed:?}"),
        }
        if id == "syntax-rejected" {
            assert_eq!(failed.len(), checks.len());
            for observed in actual["observations"].as_array().unwrap() {
                assert_eq!(observed["actual"]["sourceRejected"], true);
                assert_eq!(observed["actual"]["diagnostics"][0]["code"], 1128);
            }
        }
    }
}

#[test]
fn push_worker_preserves_pending_retry_and_rejects_answer_bearing_requests() {
    let repository = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let dir = loop_output_for_adapter();
    std::fs::create_dir(&dir).unwrap();
    let compiler = dir.join("compiler.cjs");
    // Executes JS protocol fixtures; real pinned ETS/compiler controls are external.
    let compiler_bytes = b"module.exports={ModuleKind:{CommonJS:1},ScriptTarget:{ES2020:7},DiagnosticCategory:{Error:1},flattenDiagnosticMessageText(m){return m},transpileModule(source){return{outputText:source,diagnostics:source.includes('SYNTAX_REJECTED')?[{category:1,code:1128,file:{text:source},start:0,length:1,messageText:'Syntax'}]:[]}}};";
    std::fs::write(&compiler, compiler_bytes).unwrap();
    std::fs::write(
        dir.join("support.json"),
        serde_json::to_vec(&json!({
            "adapter":"push-initialization-host-seam-v1","compilerSha256":digest(compiler_bytes)
        }))
        .unwrap(),
    )
    .unwrap();
    let valid = r#"
const notification = require('@kit.NotificationKit').notificationManager;
const push = require('@kit.PushKit').pushService;
const service = require('./PushService').PushService;
exports.PushServiceManager = class {
  static getInstance() { return this.instance ??= new this(); }
  initPushServiceManager(context) {
    if (this.flight) return this.flight;
    this.flight = this.initialize(context).finally(() => {this.flight = null;});
    return this.flight;
  }
  async initialize(context) {
    try {
      if (!notification.isNotificationEnabledSync()) await notification.requestEnableNotification(context);
      const pushToken = await push.getToken();
      await service.postPushToken({pushToken});
    } catch (error) { require('../util/Logger').default.error('push', error); }
  }
};
"#;
    for (id, source, expected) in [
        (
            "valid",
            valid.to_owned(),
            Some(json!({"token":2,"post":2,"settledCalls":3,"unhandled":0})),
        ),
        (
            "sticky",
            valid.replace(".finally(() => {this.flight = null;})", ""),
            Some(json!({"token":1,"post":1,"settledCalls":3,"unhandled":0})),
        ),
        ("syntax", format!("{valid}// SYNTAX_REJECTED"), None),
        ("answer", valid.to_owned(), None),
        ("bad-input", format!("{valid}// SYNTAX_REJECTED"), None),
        (
            "logged-failure",
            valid.to_owned(),
            Some(
                json!({"settledCalls":1,"unhandled":0,"payloads":["token-0"],"failureObserved":true}),
            ),
        ),
        (
            "silent-failure",
            valid.replace(".default.error(", ".default.info("),
            Some(
                json!({"settledCalls":1,"unhandled":0,"payloads":["token-0"],"failureObserved":false}),
            ),
        ),
        (
            "wrong-payload",
            valid.replace("{pushToken}", "{pushToken:'wrong-token'}"),
            Some(
                json!({"token":2,"post":2,"settledCalls":3,"unhandled":0,"payloads":["wrong-token","wrong-token"],"failureObserved":false}),
            ),
        ),
        (
            "token-pending",
            valid.to_owned(),
            Some(json!({"token":1,"post":0,"settledCalls":0})),
        ),
    ] {
        let mut check = json!({"id":"retry","input":{"mode":"retry-success"}});
        if id == "logged-failure" || id == "silent-failure" {
            check["input"] = json!({"mode":"post-failure","observe":"outcome"});
        }
        if id == "wrong-payload" {
            check["input"]["observe"] = json!("outcome");
        }
        if id == "token-pending" {
            check["input"]["mode"] = json!("token-pending");
        }
        if id == "answer" {
            check["expected"] = json!({"passed":true});
        }
        if id == "bad-input" {
            check["input"]["mode"] = json!("unknown");
        }
        let request = json!({"schema":"agentlab.behavior_executor_request.v1","id":id,
            "originalSourceSha256":digest(valid.as_bytes()),"submittedSource":source,
            "submittedSourceSha256":digest(source.as_bytes()),"checks":[check]});
        let request_path = dir.join(format!("{id}.json"));
        std::fs::write(&request_path, serde_json::to_vec(&request).unwrap()).unwrap();
        let result = std::process::Command::new("node")
            .arg(repository.join("scripts/push-initialization-worker.cjs"))
            .arg(request_path)
            .arg(dir.join("support.json"))
            .arg(&compiler)
            .output()
            .unwrap();
        if id == "answer" || id == "bad-input" {
            assert!(!result.status.success());
            assert!(result.stdout.is_empty());
            assert!(String::from_utf8_lossy(&result.stderr).contains("Unsupported push input"));
            continue;
        }
        assert!(
            result.status.success(),
            "{id}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        let actual: Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(
            actual["submittedSourceSha256"],
            request["submittedSourceSha256"]
        );
        assert_eq!(
            actual["observations"][0]["input"],
            request["checks"][0]["input"]
        );
        if let Some(expected) = expected {
            assert_eq!(actual["observations"][0]["actual"], expected);
        } else {
            assert_eq!(actual["observations"][0]["actual"]["sourceRejected"], true);
        }
    }
}
