//! Bounded unreviewed verifier repair. Frozen design and source are never revised here.
use crate::{digest, maintainer_source_diagnostic as diagnostic};
use serde_json::{json, Value};
use std::{fs, io::Write, path::Path};

pub const PACKET_LIMIT: usize = 16 * 1024 * 1024;
pub fn loop_intent(request_bytes: &[u8], maximum: u64) -> Result<Value, String> {
    need(
        maximum <= 2 && request_bytes.len() <= 512 * 1024,
        "construction loop intent budget",
    )?;
    Ok(
        json!({"schema":"agentlab.source_recipe_diagnostic_loop_intent.v1","authorRequestSha256":digest(request_bytes),
        "maximumRepairs":maximum,"reviewed":false,"qualified":false,"automaticPromotion":false,"authorityWritePerformed":false}),
    )
}
pub fn check_loop_intent(request_bytes: &[u8], intent_bytes: &[u8]) -> Result<Value, String> {
    let intent = parsed(intent_bytes)?;
    let maximum = intent["maximumRepairs"]
        .as_u64()
        .ok_or("construction loop intent maximum missing")?;
    need(
        intent == loop_intent(request_bytes, maximum)?,
        "construction loop intent differs",
    )?;
    Ok(intent)
}
fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn raw<'a>(v: &'a Value, key: &str, limit: usize) -> Result<&'a [u8], String> {
    v[key]
        .as_str()
        .filter(|s| s.len() <= limit)
        .map(str::as_bytes)
        .ok_or_else(|| format!("construction repair {key} budget/type"))
}
fn parsed(bytes: &[u8]) -> Result<Value, String> {
    serde_json::from_slice(bytes).map_err(|e| e.to_string())
}
fn write(path: &Path, value: &Value) -> Result<(), String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    need(
        bytes.len() <= PACKET_LIMIT,
        "construction repair packet budget",
    )?;
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(&bytes)
        .map_err(|e| e.to_string())
}

/// Preserve complete original UTF-8 evidence. Non-UTF8 logs stop this adapter.
pub fn prepare(
    stage: &Path,
    inputs: &Path,
    capture: &Path,
    maximum: u64,
    output: &Path,
) -> Result<Value, String> {
    prepare_inner(stage, inputs, capture, maximum, None, output)
}

/// A separately reviewed, prospective enrollment; never retrofit the parent's budget.
pub fn prepare_continuation(
    stage: &Path,
    inputs: &Path,
    capture: &Path,
    enrollment: &[u8],
    output: &Path,
) -> Result<Value, String> {
    prepare_inner(stage, inputs, capture, 1, Some(enrollment), output)
}

fn prepare_inner(
    stage: &Path,
    inputs: &Path,
    capture: &Path,
    maximum: u64,
    enrollment: Option<&[u8]>,
    output: &Path,
) -> Result<Value, String> {
    need(
        (1..=2).contains(&maximum),
        "construction repair budget must be 1..2",
    )?;
    need(
        !stage.join("revision-request.json").exists(),
        "review child cannot reset into automatic repair",
    )?;
    let mut packet = json!({"schema":"agentlab.source_recipe_diagnostic_repair.v1",
        "maximumRepairs":maximum,"repairIndex":1,"previousRepairOriginal":null,
        "reviewed":false,"semanticQualified":false,"automaticPromotion":false,"authorityWritePerformed":false});
    if let Some(bytes) = enrollment {
        need(bytes.len() <= 65536, "continuation enrollment budget")?;
        packet["schema"] = json!("agentlab.source_recipe_diagnostic_repair.v2");
        packet["continuationEnrollmentOriginal"] =
            json!(std::str::from_utf8(bytes).map_err(|e| e.to_string())?);
        packet["loopIntentOriginal"] = Value::Null;
    }
    for (key, name, limit) in [
        ("parentRequestOriginal", "request.json", 512 * 1024),
        ("parentProposalOriginal", "proposal.json", 256 * 1024),
        ("parentDesignOriginal", "design.json", 64 * 1024),
        (
            "loopIntentOriginal",
            "diagnostic-loop-intent.json",
            64 * 1024,
        ),
        (
            "parentStageReceiptOriginal",
            "stage-receipt.json",
            64 * 1024,
        ),
    ] {
        if enrollment.is_some() && key == "loopIntentOriginal" {
            continue;
        }
        let bytes = diagnostic::read(&stage.join(name), limit)?;
        packet[key] = json!(std::str::from_utf8(&bytes).map_err(|e| e.to_string())?);
    }
    for (key, root, name, limit) in [
        ("intentOriginal", inputs, "intent.json", 128 * 1024),
        (
            "executionRequestOriginal",
            inputs,
            "request.json",
            256 * 1024,
        ),
        ("descriptorOriginal", inputs, "descriptor.json", 64 * 1024),
        ("supportOriginal", inputs, "support.json", 4 * 1024 * 1024),
        ("processOriginal", capture, "process.json", 64 * 1024),
        ("stdoutOriginal", capture, "worker-stdout.log", 1024 * 1024),
        ("stderrOriginal", capture, "worker-stderr.log", 1024 * 1024),
    ] {
        let bytes = diagnostic::read(&root.join(name), limit)?;
        packet[key] = json!(std::str::from_utf8(&bytes).map_err(|e| e.to_string())?);
    }
    need(
        diagnostic::read(&capture.join("request.json"), 256 * 1024)?
            == raw(&packet, "executionRequestOriginal", 256 * 1024)?,
        "construction repair captured request differs",
    )?;
    let stage_receipt = parsed(raw(&packet, "parentStageReceiptOriginal", 65536)?)?;
    if stage_receipt.get("diagnosticRepairPacketSha256").is_some()
        || stage.join("diagnostic-repair.json").exists()
    {
        need(enrollment.is_none(), "continuation cannot reset a repair lineage")?;
        let previous = diagnostic::read(&stage.join("diagnostic-repair.json"), PACKET_LIMIT)?;
        need(
            stage_receipt["diagnosticRepairPacketSha256"] == digest(&previous),
            "construction repair prior packet differs",
        )?;
        let prior = parsed(&previous)?;
        packet["repairIndex"] = json!(
            prior["repairIndex"]
                .as_u64()
                .ok_or("construction repair prior index")?
                + 1
        );
        packet["previousRepairOriginal"] =
            json!(std::str::from_utf8(&previous).map_err(|e| e.to_string())?);
    }
    let bytes = serde_json::to_vec(&packet).map_err(|e| e.to_string())?;
    check(raw(&packet, "parentRequestOriginal", 512 * 1024)?, &bytes)?;
    write(output, &packet)?;
    Ok(packet)
}

/// Reconstruct the whole parent failure; the packet is not an authenticated attestation.
pub fn check(request_bytes: &[u8], packet_bytes: &[u8]) -> Result<Value, String> {
    check_depth(request_bytes, packet_bytes, 0)
}
fn check_depth(request_bytes: &[u8], packet_bytes: &[u8], depth: usize) -> Result<Value, String> {
    need(
        depth < 2 && packet_bytes.len() <= PACKET_LIMIT,
        "construction repair lineage/packet budget",
    )?;
    let p = parsed(packet_bytes)?;
    let continuation = p["schema"] == "agentlab.source_recipe_diagnostic_repair.v2";
    need(
        p.as_object().is_some_and(|o| o.len() == if continuation { 21 } else { 20 })
            && (continuation || p["schema"] == "agentlab.source_recipe_diagnostic_repair.v1")
            && p["reviewed"] == false
            && p["semanticQualified"] == false
            && p["automaticPromotion"] == false
            && p["authorityWritePerformed"] == false,
        "construction repair packet identity",
    )?;
    let maximum = p["maximumRepairs"]
        .as_u64()
        .filter(|n| (1..=2).contains(n))
        .ok_or("construction repair budget")?;
    let index = p["repairIndex"]
        .as_u64()
        .filter(|n| *n > 0 && *n <= maximum)
        .ok_or("construction repair exhausted")?;
    let parent_request = raw(&p, "parentRequestOriginal", 512 * 1024)?;
    need(
        request_bytes == parent_request,
        "construction repair source/knowledge request changed",
    )?;
    let proposal_bytes = raw(&p, "parentProposalOriginal", 256 * 1024)?;
    let design_bytes = raw(&p, "parentDesignOriginal", 64 * 1024)?;
    let parent = parsed(proposal_bytes)?;
    let design = parsed(design_bytes)?;
    let request = parsed(parent_request)?;
    let stage = parsed(raw(&p, "parentStageReceiptOriginal", 65536)?)?;
    if continuation {
        need(
            depth == 0 && maximum == 1 && index == 1 && p["loopIntentOriginal"].is_null(),
            "continuation cannot extend or reopen a repair budget",
        )?;
        let enrollment = parsed(raw(&p, "continuationEnrollmentOriginal", 65536)?)?;
        let id = enrollment["enrollmentId"]
            .as_str()
            .filter(|s| !s.trim().is_empty() && s.len() <= 96)
            .ok_or("continuation enrollment id")?;
        let mut expected = json!({"schema":"agentlab.source_recipe_diagnostic_continuation_enrollment.v1",
            "enrollmentId":id,"maximumSuccessors":1,"participantBudgetSeconds":420,
            "transportRetryLimit":0,"designRevisionLimit":0,"codeRevisionLimit":0,
            "reviewed":true,"automaticPromotion":false});
        for (field, original) in [
            ("authorRequestSha256", "parentRequestOriginal"),
            ("parentStageReceiptSha256", "parentStageReceiptOriginal"),
            ("parentDesignSha256", "parentDesignOriginal"),
            ("parentProposalSha256", "parentProposalOriginal"),
            ("diagnosticIntentSha256", "intentOriginal"),
            ("diagnosticProcessSha256", "processOriginal"),
            ("diagnosticStdoutSha256", "stdoutOriginal"),
            ("diagnosticStderrSha256", "stderrOriginal"),
        ] {
            expected[field] = json!(digest(raw(&p, original, PACKET_LIMIT)?));
        }
        need(enrollment == expected, "continuation enrollment differs from original failure")?;
    } else {
        let loop_bytes = raw(&p, "loopIntentOriginal", 65536)?;
        let frozen_budget = check_loop_intent(parent_request, loop_bytes)?;
        need(
            frozen_budget["maximumRepairs"] == maximum
                && stage["diagnosticLoopIntentSha256"] == digest(loop_bytes),
            "construction repair budget differs from pre-generation intent",
        )?;
    }
    need(
        stage["schema"] == "agentlab.source_recipe_author_stage.v1"
            && stage["reviewed"] == false
            && stage["automaticPromotion"] == false
            && stage["executionPerformed"] == false
            && stage["requestSha256"] == digest(parent_request)
            && stage["proposalSha256"] == digest(proposal_bytes)
            && stage["designSha256"] == digest(design_bytes)
            && stage.get("revisionPacketSha256").is_none()
            && stage.get("designReviewSha256").is_none()
            && request["schema"] == "agentlab.source_recipe_author_request.v1"
            && request["reviewed"] == false
            && request["automaticPromotion"] == false
            && parent["schema"] == "agentlab.source_recipe_author_proposal.v1"
            && design["schema"] == "agentlab.source_recipe_design.v2"
            && parent["scopeSkillId"] == request["scope"]["id"]
            && parent["scopeSkillId"] == design["scopeSkillId"]
            && parent["contract"]["checks"] == design["checks"],
        "construction repair parent binding differs",
    )?;
    if index == 1 {
        need(
            p["previousRepairOriginal"].is_null()
                && stage.get("diagnosticRepairPacketSha256").is_none(),
            "construction repair cannot reset lineage",
        )?;
    } else {
        let previous = raw(&p, "previousRepairOriginal", PACKET_LIMIT)?;
        let prior = parsed(previous)?;
        need(
            prior["maximumRepairs"] == maximum
                && prior["repairIndex"] == index - 1
                && stage["diagnosticRepairPacketSha256"] == digest(previous),
            "construction repair prior budget/index differs",
        )?;
        check_depth(request_bytes, previous, depth + 1)?;
        check_output_inner(&prior, proposal_bytes, design_bytes)?;
    }
    let intent_bytes = raw(&p, "intentOriginal", 128 * 1024)?;
    let execution_bytes = raw(&p, "executionRequestOriginal", 256 * 1024)?;
    let descriptor_bytes = raw(&p, "descriptorOriginal", 65536)?;
    let process_bytes = raw(&p, "processOriginal", 65536)?;
    let stdout = raw(&p, "stdoutOriginal", 1024 * 1024)?;
    let stderr = raw(&p, "stderrOriginal", 1024 * 1024)?;
    let feedback = diagnostic::reconstruct(
        intent_bytes,
        execution_bytes,
        descriptor_bytes,
        process_bytes,
        stdout,
        stderr,
    )?;
    if continuation {
        need(
            feedback["classification"] == "baseline-observations-rejected",
            "continuation requires completed baseline observations, not infrastructure failure",
        )?;
    }
    let intent = parsed(intent_bytes)?;
    let execution = parsed(execution_bytes)?;
    let descriptor = parsed(descriptor_bytes)?;
    let process = parsed(process_bytes)?;
    let support_bytes = raw(&p, "supportOriginal", 4 * 1024 * 1024)?;
    let support = parsed(support_bytes)?;
    need(
        intent["originalStageReceipt"] == stage
            && intent["checks"] == design["checks"]
            && intent["source"] == request["source"]
            && execution["schema"] == "agentlab.behavior_executor_request.v1"
            && execution["submittedSource"] == parent["verifierSource"]
            && execution["submittedSourceSha256"]
                == digest(
                    parent["verifierSource"]
                        .as_str()
                        .ok_or("construction repair verifier missing")?
                        .as_bytes(),
                )
            && descriptor["workerSha256"]
                == digest(include_bytes!(
                    "../../../scripts/source-recipe-diagnostic-worker.cjs"
                ))
            && descriptor["supportSha256"] == digest(support_bytes)
            && support["schema"] == "agentlab.source_recipe_diagnostic_support.v1"
            && support["controlId"] == intent["controlId"]
            && support["runtimeSha256"] == stage["designRuntimeSha256"]
            && support["runtimeSha256"]
                == digest(
                    support["runtimeSource"]
                        .as_str()
                        .ok_or("construction repair runtime missing")?
                        .as_bytes(),
                )
            && support["compilerSha256"] == descriptor["compilerSha256"]
            && support["compilerSha256"] == request["policy"]["methodDependencies"][0]["sha256"],
        "construction repair execution/source binding differs",
    )?;
    let manifest = crate::maintainer_source_recipe_author::runtime_manifest(
        support["runtimeSource"].as_str().unwrap(),
    )?;
    let paths = parent["sourcePaths"]
        .as_array()
        .ok_or("construction repair selected paths missing")?;
    let inventory = request["sourceFiles"]
        .as_array()
        .ok_or("construction repair inventory missing")?;
    let files = support["files"]
        .as_array()
        .ok_or("construction repair retained files missing")?;
    need(
        manifest["scenarios"] == design["scenarios"]
            && manifest["controls"] == design["controls"]
            && manifest["files"] == support["files"]
            && paths.len() == files.len()
            && files
                .iter()
                .all(|file| paths.contains(&file["path"]) && inventory.contains(file)),
        "construction repair runtime manifest/source differs",
    )?;
    let baselines = design["controls"]
        .as_array()
        .ok_or("construction repair controls missing")?
        .iter()
        .filter(|c| c["role"] == "baseline")
        .collect::<Vec<_>>();
    need(
        baselines.len() == 1
            && baselines[0]["id"] == support["controlId"]
            && baselines[0]["edits"] == json!([])
            && baselines[0]["expectedFailedCheckIds"] == json!([]),
        "construction repair baseline differs",
    )?;
    let code = process["exitCode"]
        .as_i64()
        .ok_or("construction repair exit missing")?;
    need(feedback["baselinePassed"]==false && process["timedOut"]==false && process["logBudgetExceeded"]==false
        && process["cleanupExitCode"]==0 && process["network"]=="none" && process["rootFilesystemReadOnly"]==true
        && process["capabilitiesDropped"]==true && process["durationMs"].as_u64().is_some_and(|n|n>0)
        && (0..125).contains(&code) && (code==0 || !stderr.is_empty()),"construction repair requires bounded completed diagnostic failure; transport/timeout/cleanup failure stops")?;
    Ok(
        json!({"schema":"agentlab.source_recipe_diagnostic_repair_admission.v1","packetSha256":digest(packet_bytes),
        "parentProposalSha256":digest(proposal_bytes),"parentDesignSha256":digest(design_bytes),"repairIndex":index,"maximumRepairs":maximum,
        "feedback":feedback,"producerAuthenticated":false,"reviewed":false,"semanticQualified":false,"automaticPromotion":false,"authorityWritePerformed":false}),
    )
}

fn check_output_inner(
    packet: &Value,
    proposal_bytes: &[u8],
    design_bytes: &[u8],
) -> Result<(), String> {
    need(
        proposal_bytes.len() <= 256 * 1024
            && design_bytes == raw(packet, "parentDesignOriginal", 64 * 1024)?,
        "construction repair changed frozen design",
    )?;
    let parent = parsed(raw(packet, "parentProposalOriginal", 256 * 1024)?)?;
    let proposal = parsed(proposal_bytes)?;
    need(
        proposal["schema"] == parent["schema"]
            && proposal["scopeSkillId"] == parent["scopeSkillId"]
            && proposal["contract"] == parent["contract"]
            && proposal["sourcePaths"] == parent["sourcePaths"],
        "construction repair changed frozen checks/controls/source paths",
    )?;
    need(
        proposal["verifierSource"]
            .as_str()
            .is_some_and(|s| !s.is_empty() && s.len() <= 128 * 1024)
            && proposal["verifierSource"] != parent["verifierSource"],
        "construction repair unchanged/missing verifier",
    )?;
    Ok(())
}
pub fn check_output(
    request_bytes: &[u8],
    packet_bytes: &[u8],
    proposal_bytes: &[u8],
    design_bytes: &[u8],
) -> Result<Value, String> {
    let admission = check(request_bytes, packet_bytes)?;
    check_output_inner(&parsed(packet_bytes)?, proposal_bytes, design_bytes)?;
    Ok(
        json!({"schema":"agentlab.source_recipe_diagnostic_repair_output.v1","packetSha256":admission["packetSha256"],
        "repairIndex":admission["repairIndex"],"proposalSha256":digest(proposal_bytes),"designSha256":digest(design_bytes),
        "reviewed":false,"semanticQualified":false,"automaticPromotion":false,"authorityWritePerformed":false}),
    )
}
