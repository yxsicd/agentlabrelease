//! Business-gate adapter for an existing fixed knowledge cut. Not a fresh
//! semantic producer, case generator, authority writer or qualification bypass.
use crate::{
    digest, maintainer_behavior_loop, maintainer_flywheel_plan, maintainer_guidance,
    maintainer_lesson_admission, maintainer_operation_exec, maintainer_operation_qualification,
    maintainer_skill_flywheel::assess_with_receipts,
};
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn text<'a>(value: &'a Value, name: &str) -> Result<&'a str, String> {
    value[name]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| format!("business {name} missing"))
}
fn absolute(value: &Value, name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(text(value, name)?);
    need(path.is_absolute(), "business input path must be absolute")?;
    for part in path.ancestors() {
        need(
            !fs::symlink_metadata(part)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "business input symlink",
        )?;
    }
    Ok(path)
}
fn read(path: &Path) -> Result<Vec<u8>, String> {
    let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    need(
        meta.is_file() && meta.len() <= 16 * 1024 * 1024,
        "business input must be bounded regular file",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    need(
        bytes.len() <= 16 * 1024 * 1024,
        "business input grew beyond budget",
    )?;
    Ok(bytes)
}
fn bound(value: &Value) -> Result<Vec<u8>, String> {
    let bytes = read(&absolute(value, "path")?)?;
    need(
        value["sha256"] == digest(&bytes),
        "business input digest differs",
    )?;
    Ok(bytes)
}
fn save(path: &Path, value: &Value) -> Result<Vec<u8>, String> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(&bytes)
        .map_err(|e| e.to_string())?;
    Ok(bytes)
}
fn save_raw(path: &Path, bytes: &[u8]) -> Result<(), String> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(bytes)
        .map_err(|e| e.to_string())
}
fn knowledge(state: &Value) -> Result<(PathBuf, Value, Value), String> {
    let base = absolute(&state["knowledge"], "directory")?;
    let cut_bytes = read(&base.join("maintainer-knowledge-cut.json"))?;
    need(
        state["knowledge"]["cutSha256"] == digest(&cut_bytes),
        "business knowledge cut changed",
    )?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    need(
        cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && cut["automaticPromotion"] == false
            && cut.get("staging").is_none(),
        "business requires committed knowledge without automatic promotion",
    )?;
    need(
        cut["sourceSetSha256"] == digest(&read(&base.join("source-set.txt"))?),
        "business source inventory binding differs",
    )?;
    need(
        state["knowledge"]["revision"] == cut["tableGitAuthority"]["revision"],
        "business knowledge revision differs",
    )?;
    let packet = if state["guidanceMode"] == "reviewed-bootstrap" {
        need(
            state["bootstrapReview"]["reviewed"] == true
                && state["bootstrapReview"]["knowledgeCutSha256"] == digest(&cut_bytes)
                && state.get("guidanceSelection").is_none(),
            "business bootstrap requires exact review and no declared guidance",
        )?;
        need(
            cut["repositories"].as_array().is_some_and(|repos| {
                repos.iter().any(|r| {
                    r["id"] == state["repositoryId"] && r["revision"] == state["sourceRevision"]
                })
            }),
            "business bootstrap source absent from knowledge cut",
        )?;
        for (key, table) in [
            ("maintainerSkills", "maintainer_skills"),
            ("maintainerScopeSkills", "maintainer_scope_skills"),
            ("programFacts", "program_facts"),
            (
                "maintainerSkillRefreshRounds",
                "maintainer_skill_refresh_rounds",
            ),
            ("evaluationCases", "evaluation_cases"),
        ] {
            let name = format!("{table}.jsonl");
            need(
                cut["tables"][key]
                    == json!({"path":name,"sha256":digest(&read(&base.join(&name))?)}),
                "business bootstrap table binding differs",
            )?;
        }
        json!({"schema":"agentlab.maintainer_guidance_packet.v1","guidance":[],"bootstrap":true,
            "knowledgeCutSha256":digest(&cut_bytes),"knowledgeAuthority":cut["tableGitAuthority"],
            "sources":[{"repositoryId":state["repositoryId"],"sourceRevision":state["sourceRevision"]}],
            "automaticPromotion":false,"agentConsumptionVerified":false})
    } else {
        need(
            state.get("guidanceMode").is_none() || state["guidanceMode"] == "selected",
            "business guidance mode unsupported",
        )?;
        maintainer_guidance::bind(&base, &bound(&state["guidanceSelection"])?)?
    };
    need(
        packet["sources"]
            == json!([{"repositoryId":state["repositoryId"],"sourceRevision":state["sourceRevision"]}]),
        "business source applicability differs",
    )?;
    Ok((base, cut, packet))
}
fn gap(reason: &str) -> (&'static str, Value) {
    (
        "review-required",
        json!({"gap":reason,"qualified":false,"automaticPromotion":false}),
    )
}

fn source_suite_capture(
    state: &Value,
    inputs: &Value,
) -> Result<(PathBuf, PathBuf, Value), String> {
    let stage = absolute(inputs, "stageDirectory")?;
    let suite = absolute(inputs, "suiteDirectory")?;
    need(
        inputs["stageReceiptSha256"] == digest(&read(&stage.join("stage-receipt.json"))?)
            && inputs["suiteResultSha256"] == digest(&read(&suite.join("result.json"))?),
        "business source suite original binding differs",
    )?;
    let request: Value =
        serde_json::from_slice(&read(&stage.join("request.json"))?).map_err(|e| e.to_string())?;
    need(
        request["source"]["repositoryId"] == state["repositoryId"]
            && request["source"]["revision"] == state["sourceRevision"]
            && request["scope"]["id"] == state["candidateId"]
            && request["knowledgeCutSha256"] == state["knowledge"]["cutSha256"]
            && request["authorityRevision"] == state["knowledge"]["revision"],
        "business source suite source, scope or knowledge differs",
    )?;
    let report = crate::maintainer_source_diagnostic::reconstruct_suite(&stage, &suite)?;
    Ok((stage, suite, report))
}

fn bind_source_suite_lesson(original: &Path, source: &Path) -> Result<(), String> {
    let inventory_bytes = read(&original.join("source-suite-inputs.json"))?;
    need(
        read(&source.join("source-suite-inputs.json"))? == inventory_bytes,
        "business source lesson inventory borrows another execution",
    )?;
    let inventory: Value = serde_json::from_slice(&inventory_bytes).map_err(|e| e.to_string())?;
    for entry in inventory["files"]
        .as_array()
        .ok_or("business source inventory absent")?
    {
        let name = text(entry, "path")?;
        let path = absolute(&json!({"path":source.join(name)}), "path")?;
        need(
            read(&path)? == read(&original.join(name))?,
            "business source lesson raw bytes borrow another execution",
        )?;
    }
    need(
        read(&source.join("candidate.json"))? == read(&original.join("candidate.json"))?,
        "business source lesson candidate differs",
    )
}
fn recorded_outcome(result: &Value) -> Result<bool, String> {
    let passed = result["status"] == "recorded-attempt-passed";
    need(
        passed
            || result["status"] == "attempt-budget-exhausted"
            || result["status"] == "unchanged-attempt-suppressed",
        "business loop did not produce a recorded behavior outcome",
    )?;
    let route = if passed {
        "review-agent-outcome"
    } else {
        "repair-agent-behavior"
    };
    need(
        result["attempts"].as_array().is_some_and(|a| !a.is_empty())
            && result["latestFeedback"]["nextAction"] == route,
        "business loop outcome lacks complete behavior feedback",
    )?;
    Ok(passed)
}
#[cfg(unix)]
fn persist_observations(
    config: &Value,
    packet: &Value,
    source: &Path,
    out: &Path,
) -> Result<Value, String> {
    need(
        config["reviewed"] == true
            && config["destination"]["knowledgeRepository"] == packet["knowledgeAuthority"]["repo"],
        "business observation persistence review or knowledge binding differs",
    )?;
    let request = json!({"schema":"agentlab.observation_store_request.v1","reviewed":true,"automaticPromotion":false,
        "endpoint":text(config,"endpoint")?,"destination":config["destination"],
        "sourceDirectory":source,"sourceManifestSha256":digest(&read(&source.join("export.json"))?),
        "flywheelTool":config["flywheelTool"]["path"],"flywheelToolSha256":config["flywheelTool"]["sha256"],
        "outputDirectory":out.join("persisted-observations")});
    let request_path = out.join("persistence-request.json");
    save(&request_path, &request)?;
    let command_dir = out.join("persistence-command");
    fs::create_dir(&command_dir).map_err(|e| e.to_string())?;
    let (execution, stdout) = maintainer_behavior_loop::invoke(
        &config["command"],
        &request_path,
        &command_dir,
        "adapter",
        &[],
    )?;
    let reported: Value = serde_json::from_str(&stdout).map_err(|e| e.to_string())?;
    let capture = out.join("persisted-observations");
    let mut verified = crate::maintainer_observation_store::verify(
        source,
        &read(&capture.join("plan.json"))?,
        &read(&capture.join("commit-receipt.json"))?,
        &read(&capture.join("committed.json"))?,
        &read(&capture.join("baseline.json"))?,
    )?;
    need(
        verified == reported,
        "business persistence response differs from independent readback reconstruction",
    )?;
    verified["adapterExecution"] = execution;
    verified["captureDirectory"] = json!(capture);
    Ok(verified)
}
#[cfg(not(unix))]
fn persist_observations(_: &Value, _: &Value, _: &Path, _: &Path) -> Result<Value, String> {
    Err("business observation persistence command requires Unix containment".into())
}
fn execute_operation(base: &Path, state: &Value, out: &Path) -> Result<Value, String> {
    let execution = &state["operationExecution"];
    need(
        execution["reviewed"] == true,
        "business operation execution requires review",
    )?;
    let before = bound(&execution["before"])?;
    let recipe = bound(&execution["recipe"])?;
    let parsed: Value = serde_json::from_slice(&recipe).map_err(|e| e.to_string())?;
    // Check applicability before launching even a probe. Each executor enforces
    // its own scope/capability; build recipes additionally reselect the gap plan.
    need(
        parsed["source"]["repositoryId"] == state["repositoryId"]
            && parsed["source"]["revision"] == state["sourceRevision"],
        "business operation execution source differs",
    )?;
    let capture = out.join("operation");
    if parsed["schema"] == "agentlab.maintainer_source_operation_recipe.v1" {
        crate::maintainer_source_operation::execute(
            &base.join("maintainer_scope_skills.jsonl"),
            &base.join("program_facts.jsonl"),
            &base.join("operation-evidence"),
            &before,
            &recipe,
            &absolute(execution, "sourceWorktree")?,
            &capture,
        )?;
        let receipt = read(&capture.join("execution-receipt.json"))?;
        let mut report = crate::maintainer_source_operation::qualify(&capture, &digest(&receipt))?;
        report["freshOperationExecuted"] = json!(true);
        report["executionCapture"] =
            json!({"directory":capture,"executionReceiptSha256":digest(&receipt)});
        return Ok(report);
    }
    let plan = bound(&execution["plan"])?;
    maintainer_operation_exec::execute(
        &base.join("maintainer_scope_skills.jsonl"),
        &base.join("program_facts.jsonl"),
        &base.join("operation-evidence"),
        &plan,
        &before,
        &recipe,
        &absolute(execution, "sourceWorktree")?,
        &capture,
    )?;
    let receipt = read(&capture.join("execution-receipt.json"))?;
    let mut report = maintainer_operation_qualification::qualify(
        &capture,
        &digest(&receipt),
        text(execution, "moduleRoot")?,
    )?;
    report["freshOperationExecuted"] = json!(true);
    report["executionCapture"] =
        json!({"directory":capture,"executionReceiptSha256":digest(&receipt)});
    Ok(report)
}
fn evaluate(
    stage: &str,
    state: &Value,
    out: &Path,
    round: &Value,
) -> Result<(&'static str, Value), String> {
    let (base, cut, packet) = knowledge(state)?;
    match stage {
        "repository-understanding" => Ok((
            "completed",
            json!({"schema":"agentlab.flywheel_knowledge_validation.v1",
            "knowledgeCutSha256":state["knowledge"]["cutSha256"],"knowledgeRevision":state["knowledge"]["revision"],
            "guidancePacket":packet,"existingCutValidated":true,"freshSemanticAnalysisPerformed":false,
            "remoteAuthorityReadbackPerformed":false,"qualified":false}),
        )),
        "program-analysis" => {
            let reference = maintainer_flywheel_plan::latest_assessment(&base)?;
            let original_bytes = read(&base.join(text(&reference, "assessmentRelativePath")?))?;
            let original: Value =
                serde_json::from_slice(&original_bytes).map_err(|e| e.to_string())?;
            let report = assess_with_receipts(
                &base.join("maintainer_scope_skills.jsonl"),
                Some(&base.join("program_facts.jsonl")),
                original["roundIndex"]
                    .as_u64()
                    .ok_or("business assessment round absent")?,
                original["parentAssessmentSha256"].as_str(),
                Some(&base.join("operation-evidence")),
            )?;
            save_raw(&out.join("declared-assessment.json"), &original_bytes)?;
            save(&out.join("recomputed-assessment.json"), &report)?;
            need(
                report == original,
                "business strict assessment reproduction differs",
            )?;
            Ok((
                "completed",
                json!({"schema":"agentlab.flywheel_program_reassessment.v1","durableReference":reference,
                "assessment":report,"strictReproductionVerified":true,"freshProgramGraphGenerated":false,"qualified":false}),
            ))
        }
        "maintenance-verification" => {
            need(
                ["operationCapture", "operationExecution", "operationCatalog"]
                    .iter()
                    .filter(|key| state.get(**key).is_some())
                    .count()
                    <= 1,
                "business operation capture, execution and catalog are mutually exclusive",
            )?;
            let report = if let Some(reference) = state.get("operationCatalog") {
                let bytes = bound(reference)?;
                let catalog: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
                need(
                    catalog["repositorySelector"] == state["repositoryId"],
                    "business operation catalog must select the current repository",
                )?;
                let output = out.join("selected-operation");
                let result =
                    crate::maintainer_source_operation_loop::execute(&base, &bytes, 1, &output)?;
                if result["status"] == "failed" {
                    return Err(format!(
                        "business selected source operation failed: {}",
                        result["gap"]
                    ));
                }
                if result["productiveOperationRounds"] == 0 {
                    return Ok((
                        "review-required",
                        json!({"schema":"agentlab.flywheel_operation_selection.v1",
                        "selection":result,"automaticSelectionPerformed":true,"freshOperationExecuted":false,
                        "authorityWritePerformed":false,"qualified":false}),
                    ));
                }
                need(
                    result["productiveOperationRounds"] == 1,
                    "business operation catalog exceeded one selected operation",
                )?;
                let capture = output.join("iteration-1/capture");
                let receipt_sha = digest(&read(&capture.join("execution-receipt.json"))?);
                let mut report =
                    crate::maintainer_source_operation::qualify(&capture, &receipt_sha)?;
                report["automaticSelectionPerformed"] = json!(true);
                report["freshOperationExecuted"] = json!(true);
                report["selection"] = result;
                report["executionCapture"] =
                    json!({"directory":capture,"executionReceiptSha256":receipt_sha});
                // This candidate is independently staged, not active knowledge.
                report["operationKnowledgeCandidate"] =
                    report["selection"]["finalCandidateSnapshot"].clone();
                report
            } else if state.get("operationExecution").is_some() {
                execute_operation(&base, state, out)?
            } else if let Some(operation) = state.get("operationCapture") {
                let mut report = maintainer_operation_qualification::qualify(
                    &absolute(operation, "directory")?,
                    text(operation, "executionReceiptSha256")?,
                    text(operation, "moduleRoot")?,
                )?;
                report["freshOperationExecuted"] = json!(false);
                report
            } else {
                return Ok(gap("revision-bound-maintenance-operation-capture-required"));
            };
            let source = cut["repositories"]
                .as_array()
                .ok_or("business source catalog absent")?
                .iter()
                .find(|r| r["id"] == state["repositoryId"])
                .ok_or("business source absent")?;
            need(
                report["source"]["repositoryId"] == state["repositoryId"]
                    && report["source"]["revision"] == state["sourceRevision"]
                    && report["source"]["repository"] == source["repository"],
                "business operation source differs",
            )?;
            Ok(("completed", report))
        }
        "case-execution" => {
            if let Some(inputs) = state.get("sourceSuiteCapture") {
                need(
                    state.get("behaviorExecution").is_none(),
                    "business case inputs ambiguous",
                )?;
                let (_, _, report) = source_suite_capture(state, inputs)?;
                return Ok((
                    "completed",
                    json!({
                        "schema":"agentlab.flywheel_source_suite_execution.v1","round":round,
                        "sourceSuiteCapture":inputs,"readback":report,
                        "taskPassed":report["status"]=="declarations-matched",
                        "freshExecutionPerformed":false,"caseGenerationPerformed":false,
                        "formalCaseQualified":false,"qualified":false
                    }),
                ));
            }
            let Some(inputs) = state.get("behaviorExecution") else {
                return Ok(gap(
                    "generated-candidate-and-reviewed-execution-inputs-required",
                ));
            };
            let contract = bound(&inputs["contract"])?;
            let capture = bound(&inputs["calibrationCapture"])?;
            let recipe = bound(&inputs["recipe"])?;
            let recipe_value: Value = serde_json::from_slice(&recipe).map_err(|e| e.to_string())?;
            if let Some(selection) = recipe_value.get("maintainerGuidance") {
                let selected = maintainer_behavior_loop::bind_guidance(
                    &absolute(selection, "knowledgeDirectory")?,
                    &read(&absolute(selection, "selectionPath")?)?,
                    text(selection, "repositoryId")?,
                    text(state, "sourceRevision")?,
                    text(selection, "stage")?,
                )?;
                need(
                    selected == packet,
                    "business execution guidance cut differs",
                )?;
            }
            let contract_value: Value =
                serde_json::from_slice(&contract).map_err(|e| e.to_string())?;
            need(
                contract_value["sourceRevision"] == state["sourceRevision"]
                    && contract_value["candidateId"] == state["candidateId"],
                "business behavior source or candidate differs",
            )?;
            let result = maintainer_behavior_loop::execute(
                &contract,
                &capture,
                &recipe,
                &out.join("behavior"),
            )?;
            let task_passed = recorded_outcome(&result)?;
            let number = result["attempts"]
                .as_array()
                .and_then(|a| a.last())
                .and_then(|a| a["attempt"].as_u64())
                .ok_or("business execution attempt missing")?;
            let attempt = out.join("behavior").join(format!("attempt-{number}"));
            let contract_path = attempt.join("attempt-contract.json");
            let capture_path = attempt.join("attempt-capture.json");
            let latest = json!({"contract":{"path":contract_path,"sha256":digest(&read(&contract_path)?)},
                "capture":{"path":capture_path,"sha256":digest(&read(&capture_path)?)}});
            Ok((
                "completed",
                json!({"schema":"agentlab.flywheel_behavior_execution.v1","round":round,"execution":result,"latestAttemptEvidence":latest,
                "taskPassed":task_passed,"caseGenerationPerformed":false,"formalCaseQualified":false,"qualified":false}),
            ))
        }
        "evidence-return" => {
            let case_ref = &state["stageEvidence"]["case-execution"];
            if case_ref["status"] != "completed" {
                return Ok(gap("current-completed-case-execution-evidence-required"));
            }
            let case_bytes = bound(case_ref)?;
            let case: Value = serde_json::from_slice(&case_bytes).map_err(|e| e.to_string())?;
            let mut source_observation = None;
            need(
                state.get("sourceSuiteCapture").is_some()
                    == (case["schema"] == "agentlab.flywheel_source_suite_execution.v1"),
                "business case source format differs",
            )?;
            if case["schema"] == "agentlab.flywheel_source_suite_execution.v1" {
                need(
                    case["round"] == *round
                        && state.get("behaviorExecution").is_none()
                        && case["sourceSuiteCapture"] == state["sourceSuiteCapture"],
                    "business source suite round or capture differs",
                )?;
                let (stage, suite, report) =
                    source_suite_capture(state, &case["sourceSuiteCapture"])?;
                need(
                    case["readback"] == report
                        && case["taskPassed"] == (report["status"] == "declarations-matched"),
                    "business source suite reconstructed outcome differs",
                )?;
                let destination = out.join("observations");
                let manifest = crate::maintainer_source_suite_lesson::export(
                    &stage,
                    &suite,
                    None,
                    &destination,
                )?;
                if state.get("lessonAdmission").is_none() {
                    let persistence = if let Some(config) = state.get("observationPersistence") {
                        persist_observations(config, &packet, &destination, out)?
                    } else {
                        Value::Null
                    };
                    return Ok((
                        "review-required",
                        json!({
                            "schema":"agentlab.flywheel_observation_return.v1",
                            "sourceFormat":"agentlab.source_recipe_control_suite_result.v1",
                            "export":{"directory":destination,"manifestSha256":digest(&read(&destination.join("export.json"))?)},
                            "tables":manifest["tables"],"observationExported":true,"lessonCreated":false,
                            "persistence":persistence,"taskPassed":case["taskPassed"],
                            "gap":if persistence.is_null(){"operational-persistence-and-reviewed-knowledge-delta-required"}else{"reviewed-knowledge-delta-required"},
                            "qualified":false,"authorityWritePerformed":!persistence.is_null() && persistence["noChange"]==false,
                            "automaticPromotion":false
                        }),
                    ));
                }
                source_observation = Some(destination);
            }
            if source_observation.is_none() {
                need(
                    case["schema"] == "agentlab.flywheel_behavior_execution.v1"
                        && case["round"] == *round
                        && case["taskPassed"].is_boolean(),
                    "business case evidence schema differs",
                )?;
            }
            let Some(admission) = state.get("lessonAdmission") else {
                let Some(candidate_ref) = state["behaviorExecution"].get("candidate") else {
                    return Ok(gap(
                        "bound-candidate-required-for-operational-observation-export",
                    ));
                };
                let candidate = bound(candidate_ref)?;
                let declaration: Value =
                    serde_json::from_slice(&candidate).map_err(|e| e.to_string())?;
                need(
                    declaration["repositoryId"] == state["repositoryId"]
                        && declaration["sourceRevision"] == state["sourceRevision"]
                        && declaration["id"] == state["candidateId"],
                    "business observation candidate source differs",
                )?;
                let contract = bound(&case["latestAttemptEvidence"]["contract"])?;
                let capture = bound(&case["latestAttemptEvidence"]["capture"])?;
                let feedback = crate::maintainer_behavior_checks::verify(&contract, &capture)?;
                need(
                    feedback["nextAction"]
                        == if case["taskPassed"] == true {
                            "review-agent-outcome"
                        } else {
                            "repair-agent-behavior"
                        },
                    "business observation outcome differs",
                )?;
                let destination = out.join("observations");
                let manifest = crate::maintainer_behavior_checks::export_observation(
                    &candidate,
                    &contract,
                    &capture,
                    &destination,
                )?;
                let persistence = if let Some(config) = state.get("observationPersistence") {
                    persist_observations(config, &packet, &destination, out)?
                } else {
                    Value::Null
                };
                return Ok((
                    "review-required",
                    json!({"schema":"agentlab.flywheel_observation_return.v1",
                    "export":{"directory":destination,"manifestSha256":digest(&read(&destination.join("export.json"))?)},
                    "tables":manifest["tables"],"observationExported":true,"lessonCreated":false,
                    "persistence":persistence,
                    "gap":if persistence.is_null(){"operational-persistence-and-reviewed-knowledge-delta-required"}else{"reviewed-knowledge-delta-required"},
                    "qualified":false,"authorityWritePerformed":!persistence.is_null() && persistence["noChange"]==false,"automaticPromotion":false}),
                ));
            };
            let proposal = absolute(admission, "proposalDirectory")?;
            let source = absolute(admission, "lessonSourceDirectory")?;
            if let Some(original) = source_observation {
                bind_source_suite_lesson(&original, &source)?;
                if !source.join("lesson-review.json").exists() {
                    return Ok(gap("reviewed-source-suite-lesson-required"));
                }
            } else {
                for (key, file) in [
                    ("contract", "behavior-contract.json"),
                    ("capture", "behavior-capture.json"),
                ] {
                    let original = bound(&case["latestAttemptEvidence"][key])?;
                    need(
                        read(&source.join(file))? == original,
                        "business lesson borrows another execution capture",
                    )?;
                }
            }
            // The existing gate reconstructs original raw evidence and typed
            // tables. Staging does not write or authenticate remote authority.
            let method_source = admission.get("methodSource").map(bound).transpose()?;
            let staged = maintainer_lesson_admission::stage_with_method(
                &base,
                &proposal,
                &source,
                text(admission, "lessonId")?,
                text(&state["knowledge"], "revision")?,
                &out.join("staged-admission"),
                method_source.as_deref(),
            )?;
            if let Some(returned) = admission.get("committedReturn") {
                need(
                    returned["reviewed"] == true,
                    "business knowledge return requires review",
                )?;
                let next_base = absolute(&returned["knowledge"], "directory")?;
                let verification = crate::maintainer_lesson_return::verify(
                    &out.join("staged-admission"),
                    &source,
                    &next_base,
                    &bound(&returned["readback"])?,
                );
                let verification = verification?;
                let mut next_state = state.clone();
                next_state["knowledge"] = returned["knowledge"].clone();
                next_state["guidanceSelection"] = returned["guidanceSelection"].clone();
                next_state["guidanceMode"] = json!("selected");
                next_state
                    .as_object_mut()
                    .unwrap()
                    .remove("bootstrapReview");
                let (_, _, next_packet) = knowledge(&next_state)?;
                // Force an explicit applicable selection of the newly admitted
                // lesson, not merely a new cut hash with unchanged guidance.
                let added = load_admitted_skill(&out.join("staged-admission"))?;
                need(
                    next_packet["guidance"]
                        .as_array()
                        .is_some_and(|rows| rows.iter().any(|r| r["skill"]["id"] == added)),
                    "business returned guidance omits admitted lesson",
                )?;
                return Ok((
                    "completed",
                    json!({"schema":"agentlab.flywheel_committed_lesson_return.v1",
                    "stage":staged,"verification":verification,"nextKnowledge":returned["knowledge"],
                    "nextGuidanceSelection":returned["guidanceSelection"],"guidanceBoundForNextRound":true,
                    "authorityWritePerformed":false,"formalCaseQualified":false,"qualified":false}),
                ));
            }
            Ok((
                "review-required",
                json!({"schema":"agentlab.flywheel_lesson_staging.v1","stage":staged,
                "gap":"atomic-admission-and-remote-committed-readback-required","qualified":false,"authorityWritePerformed":false}),
            ))
        }
        _ => Err("business stage unsupported".into()),
    }
}

fn load_admitted_skill(stage: &Path) -> Result<Value, String> {
    let plan: Value = serde_json::from_slice(&read(&stage.join("lesson-admission-plan.json"))?)
        .map_err(|e| e.to_string())?;
    Ok(plan["tables"]["maintainer_skills"]["key"].clone())
}

/// Run within the coordinator's already-created stage directory. Business gate
/// failures emit a rejected envelope, never a fabricated passing phase receipt.
pub fn run(request_bytes: &[u8], output: &Path) -> Result<Value, String> {
    need(
        request_bytes.len() <= 2 * 1024 * 1024,
        "business stage request excessive",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    need(
        request["schema"] == "agentlab.flywheel_stage_request.v1"
            && request["automaticPromotion"] == false
            && request["round"].as_u64().is_some_and(|n| n < 8),
        "business stage request invalid",
    )?;
    let stage = text(&request, "stage")?;
    let state_bytes = bound(&request["inputState"])?;
    let mut state: Value = serde_json::from_slice(&state_bytes).map_err(|e| e.to_string())?;
    need(
        state["schema"] == "agentlab.flywheel_business_state.v1"
            && state["automaticPromotion"] == false,
        "business state schema or promotion invalid",
    )?;
    text(&state, "repositoryId")?;
    text(&state, "sourceRevision")?;
    let root = output.canonicalize().map_err(|e| e.to_string())?;
    let out = root.join("business");
    fs::create_dir(&out).map_err(|e| e.to_string())?;
    let (status, report) = match evaluate(stage, &state, &out, &request["round"]) {
        Ok(result) => result,
        Err(error) => (
            "rejected",
            json!({"schema":"agentlab.flywheel_business_gate_rejection.v1",
            "error":error,"stage":stage,"agentBehaviorFailureInferred":false,"qualified":false}),
        ),
    };
    let report_bytes = save(&out.join("report.json"), &report)?;
    if stage == "evidence-return"
        && status == "completed"
        && report["schema"] == "agentlab.flywheel_committed_lesson_return.v1"
    {
        state["knowledge"] = report["nextKnowledge"].clone();
        state["guidanceSelection"] = report["nextGuidanceSelection"].clone();
        state["guidanceMode"] = json!("selected");
        state
            .as_object_mut()
            .ok_or("business state invalid")?
            .remove("bootstrapReview");
        state["priorRoundEvidence"] = state["stageEvidence"].clone();
        // Old executable inputs are not next-round work. Reusing them would
        // repeat the same task and let an old admission masquerade as a loop.
        for key in [
            "stageEvidence",
            "operationExecution",
            "operationCapture",
            "operationCatalog",
            "behaviorExecution",
            "sourceSuiteCapture",
            "lessonAdmission",
            "observationPersistence",
            "candidateId",
        ] {
            state
                .as_object_mut()
                .ok_or("business state invalid")?
                .remove(key);
        }
    }
    if state.get("stageEvidence").is_none() {
        state["stageEvidence"] = json!({});
    }
    need(
        state["stageEvidence"].is_object(),
        "business stage evidence invalid",
    )?;
    state["stageEvidence"][stage] =
        json!({"path":out.join("report.json"),"sha256":digest(&report_bytes),"status":status});
    let state_bytes = save(&out.join("state.json"), &state)?;
    Ok(
        json!({"schema":"agentlab.flywheel_stage_result.v1","round":request["round"],"stage":stage,
        "requestSha256":digest(request_bytes),"inputStateSha256":request["inputState"]["sha256"],"status":status,
        "outputState":{"path":"business/state.json","sha256":digest(&state_bytes)},
        "report":{"path":"business/report.json","sha256":digest(&report_bytes)},
        "qualified":false,"automaticPromotion":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[cfg(unix)]
    fn reviewed_operation_executes_and_independently_qualifies_original_capture() {
        use std::process::Command;
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "business-operation-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let source = root.join("source");
        fs::create_dir(&source).unwrap();
        fs::create_dir(source.join("src")).unwrap();
        let mut tar = tar::Builder::new(Vec::new());
        let mut header = tar::Header::new_gnu();
        header.set_size(7);
        header.set_mode(0o644);
        header.set_cksum();
        tar.append_data(&mut header, "package/member.txt", &b"fixture"[..])
            .unwrap();
        let mut gzip = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        gzip.write_all(&tar.into_inner().unwrap()).unwrap();
        fs::write(source.join("src/input.har"), gzip.finish().unwrap()).unwrap();
        fs::write(
            source.join("src/build.sh"),
            "cp src/input.har src/output.har\nprintf 'fixture-build\\n'\n",
        )
        .unwrap();
        fs::write(source.join(".gitignore"), "src/output.har\n").unwrap();
        let git = |args: &[&str]| {
            let result = Command::new("git")
                .args(args)
                .current_dir(&source)
                .output()
                .unwrap();
            assert!(
                result.status.success(),
                "{}",
                String::from_utf8_lossy(&result.stderr)
            );
            String::from_utf8(result.stdout).unwrap().trim().to_owned()
        };
        git(&["init"]);
        git(&["config", "user.name", "Fixture"]);
        git(&["config", "user.email", "fixture@example.invalid"]);
        git(&[
            "remote",
            "add",
            "origin",
            "https://example.invalid/arbitrary.git",
        ]);
        git(&["add", "src/input.har", "src/build.sh", ".gitignore"]);
        git(&["commit", "-m", "fixture"]);
        let revision = git(&["rev-parse", "HEAD"]);
        let scope = json!({"schema":"agentlab.maintainer_scope_skill.v1","id":"scope","skillLayer":"instance",
            "stage":"repository-scope","ownershipPlane":"target-operations","assetClass":"reusable-knowledge",
            "status":"source-supported","repositoryId":"arbitrary","repository":"https://example.invalid/arbitrary.git",
            "sourceRevision":revision,"sourceTreeOid":"2".repeat(40),"strategy":"generic-source-boundary",
            "kind":"source-component","pathBoundary":"src","responsibility":"Maintain the fixture.",
            "trackedFileCount":2,"sourceFileCount":1,"codeLineCount":2,"testFileCount":0,"languages":{"generic":1},
            "externalDependencyCount":0,"externalDependencies":[],"buildEntrypoints":["src/build.sh"],"testEntrypoints":[],
            "evidence":[{"path":"src/build.sh","gitBlobOid":"3".repeat(40)}],"coverage":"fixture","automaticPromotion":false});
        let fact = json!({"id":"semantic","kind":"semantic-contract","repositoryId":"arbitrary","sourceRevision":revision,
            "scopeSkillIds":["scope"],"dimensions":["responsibility","boundary","relations","behavior"],
            "evidence":[{"path":"src/build.sh","gitBlobOid":"3".repeat(40)}]});
        save_raw(
            &root.join("maintainer_scope_skills.jsonl"),
            &serde_json::to_vec(&scope).unwrap(),
        )
        .unwrap();
        save_raw(
            &root.join("program_facts.jsonl"),
            &serde_json::to_vec(&fact).unwrap(),
        )
        .unwrap();
        fs::create_dir(root.join("operation-evidence")).unwrap();
        let plan = maintainer_flywheel_plan::plan_for_capabilities(
            &root.join("maintainer_scope_skills.jsonl"),
            Some(&root.join("program_facts.jsonl")),
            &root.join("operation-evidence"),
            1,
            None,
            &["operation-verification".into()],
            1,
            80,
            Some("arbitrary"),
            Some(&["build-only".into()]),
        )
        .unwrap();
        let command = |args: Value| {
            json!({"program":"/bin/sh","programSha256":digest(&fs::read("/bin/sh").unwrap()),
            "args":args,"cwd":".","timeoutMs":3000})
        };
        let recipe = json!({"schema":"agentlab.maintainer_build_operation_recipe.v1","automaticPromotion":false,
            "source":{"repositoryId":"arbitrary","repository":"https://example.invalid/arbitrary.git","revision":revision},
            "scopeSkillId":"scope","lane":"build-only","cleanBuild":true,"probes":[command(json!(["-c","printf fixture"]))],
            "dependencyPreparation":command(json!(["-c","printf dependencies"])),
            "build":command(json!(["src/build.sh","clean","assembleHar"])),"artifact":"src/output.har"});
        let binding = |name: &str, value: &Value| {
            let path = root.join(name);
            let bytes = save(&path, value).unwrap();
            json!({"path":path,"sha256":digest(&bytes)})
        };
        let mut state = json!({"repositoryId":"arbitrary","sourceRevision":revision,
            "operationExecution":{"reviewed":true,"sourceWorktree":source,"moduleRoot":"src",
                "plan":binding("plan.json",&plan),"before":binding("before.json",&plan["assessment"]),
                "recipe":binding("recipe.json",&recipe)}});
        let out = root.join("success");
        fs::create_dir(&out).unwrap();
        let report = execute_operation(&root, &state, &out).unwrap();
        assert_eq!(report["status"], "qualified");
        assert_eq!(report["freshOperationExecuted"], true);
        assert_eq!(report["qualificationScope"]["tests"], false);
        assert_eq!(report["authorityWritePerformed"], false);
        assert!(out.join("operation/build-2.stdout").exists());
        state["operationExecution"]["reviewed"] = json!(false);
        assert!(execute_operation(&root, &state, &root)
            .unwrap_err()
            .contains("review"));
        state["operationExecution"]["reviewed"] = json!(true);
        state["sourceRevision"] = json!("0".repeat(40));
        assert!(execute_operation(&root, &state, &root)
            .unwrap_err()
            .contains("source differs"));
        assert!(!root.join("operation").exists());
        state["sourceRevision"] = json!(revision);
        let mut failed = recipe.clone();
        failed["build"]["args"] = json!(["-c", "printf 'original failure\\n' >&2; exit 7"]);
        state["operationExecution"]["recipe"] = binding("failed-recipe.json", &failed);
        let failed_out = root.join("failed");
        fs::create_dir(&failed_out).unwrap();
        assert!(execute_operation(&root, &state, &failed_out).is_err());
        let receipt: Value = serde_json::from_slice(
            &fs::read(failed_out.join("operation/execution-receipt.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(receipt["status"], "failed");
        assert_eq!(receipt["captures"][2]["exitCode"], 7);
        assert_eq!(
            fs::read(failed_out.join("operation/build-1.stderr")).unwrap(),
            b"original failure\n"
        );
        assert!(!failed_out.join("operation/attempt-2.artifact").exists());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn complete_recorded_task_failures_remain_feedback_but_infrastructure_does_not() {
        for status in ["attempt-budget-exhausted", "unchanged-attempt-suppressed"] {
            assert!(!recorded_outcome(&json!({"status":status,"attempts":[{"attempt":0}],"latestFeedback":{"nextAction":"repair-agent-behavior"}})).unwrap());
        }
        assert!(recorded_outcome(&json!({"status":"recorded-attempt-passed","attempts":[{}],"latestFeedback":{"nextAction":"review-agent-outcome"}})).unwrap());
        assert!(recorded_outcome(&json!({"status":"adapter-failed","attempts":[],"latestFeedback":{"nextAction":"repair-agent-behavior"}})).is_err());
        assert!(recorded_outcome(&json!({"status":"recorded-attempt-passed","attempts":[{}],"latestFeedback":{"nextAction":"repair-agent-behavior"}})).is_err());
    }
}

/// Prepare the built-in business adapter, requiring explicit operator review.
/// Missing operation/case/admission inputs stay missing, not synthetic passes.
pub fn prepare(
    base: &Path,
    selection: &Path,
    program: &Path,
    reviewed: bool,
    output: &Path,
) -> Result<Value, String> {
    need(
        reviewed,
        "business preparation requires explicit reviewed adapter selection",
    )?;
    need(
        base.is_absolute()
            && selection.is_absolute()
            && program.is_absolute()
            && output.is_absolute(),
        "business preparation paths must be absolute",
    )?;
    let selection_bytes = read(selection)?;
    let selected: Value = serde_json::from_slice(&selection_bytes).map_err(|e| e.to_string())?;
    let bootstrap = selected["schema"] == "agentlab.flywheel_bootstrap_selection.v1";
    let cut_bytes = read(&base.join("maintainer-knowledge-cut.json"))?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    let packet = if bootstrap {
        need(
            selected["reviewed"] == true
                && selected["automaticPromotion"] == false
                && selected["knowledgeCutSha256"] == digest(&cut_bytes)
                && selected["knowledgeRevision"] == cut["tableGitAuthority"]["revision"]
                && selected.get("skills").is_none(),
            "business bootstrap selection invalid",
        )?;
        json!({"sources":selected["sources"],"knowledgeAuthority":cut["tableGitAuthority"]})
    } else {
        maintainer_guidance::bind(base, &selection_bytes)?
    };
    let sources = packet["sources"]
        .as_array()
        .filter(|a| a.len() == 1)
        .ok_or("business adapter requires one explicitly selected source")?;
    let mut state = json!({"schema":"agentlab.flywheel_business_state.v1","automaticPromotion":false,
        "repositoryId":sources[0]["repositoryId"],"sourceRevision":sources[0]["sourceRevision"],
        "knowledge":{"directory":base,"cutSha256":digest(&cut_bytes),"revision":packet["knowledgeAuthority"]["revision"]},
        "guidanceSelection":{"path":selection,"sha256":digest(&selection_bytes)}});
    if bootstrap {
        state.as_object_mut().unwrap().remove("guidanceSelection");
        state["guidanceMode"] = json!("reviewed-bootstrap");
        state["bootstrapReview"] = json!({"reviewed":true,"knowledgeCutSha256":digest(&cut_bytes),
            "selection":{"path":selection,"sha256":digest(&selection_bytes)}});
    }
    knowledge(&state)?;
    let mut immutable = Vec::new();
    for file in [
        "maintainer-knowledge-cut.json",
        "source-set.txt",
        "maintainer_skills.jsonl",
        "maintainer_scope_skills.jsonl",
        "program_facts.jsonl",
        "maintainer_skill_refresh_rounds.jsonl",
        "evaluation_cases.jsonl",
    ] {
        let path = base.join(file);
        immutable.push(json!({"path":path,"sha256":digest(&read(&path)?)}));
    }
    immutable.push(json!({"path":selection,"sha256":digest(&selection_bytes)}));
    let program_sha = crate::maintainer_operation_exec::executable_sha(program)?;
    let stages: Vec<_> = [("repository-understanding",30_000),("program-analysis",90_000),
        ("maintenance-verification",660_000),("case-execution",720_000),("evidence-return",300_000)]
        .into_iter().map(|(stage,timeout)| json!({"stage":stage,"command":{"program":program,
            "programSha256":program_sha,"args":["--run-flywheel-business-stage","--stage-request","{request}","--output","."],
            "cwd":".","timeoutMs":timeout}})).collect();
    fs::create_dir(output).map_err(|e| e.to_string())?;
    let root = output.canonicalize().map_err(|e| e.to_string())?;
    // Preserve only fixed state and business gaps; no generated readiness rows.
    state["stageEvidence"] = json!({});
    let state_path = root.join("initial-state.json");
    let state_bytes = save(&state_path, &state)?;
    let recipe = json!({"schema":"agentlab.flywheel_cycles_recipe.v1","reviewed":true,"automaticPromotion":false,
        "maximumRounds":2,"initialState":{"path":state_path,"sha256":digest(&state_bytes)},"immutableInputs":immutable,"stages":stages});
    save(&root.join("recipe.json"), &recipe)?;
    Ok(
        json!({"schema":"agentlab.flywheel_business_preparation.v1","recipePath":root.join("recipe.json"),
        "repositoryId":state["repositoryId"],"authorityWritePerformed":false,"qualified":false}),
    )
}
