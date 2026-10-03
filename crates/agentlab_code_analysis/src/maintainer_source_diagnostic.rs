//! Portable retained-byte diagnostic, never approval, historical restore or calibration.
use crate::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, fs, io::Write, path::Path};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
pub(crate) fn read(path: &Path, limit: usize) -> Result<Vec<u8>, String> {
    let path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| e.to_string())?
            .join(path)
    };
    for ancestor in path.ancestors() {
        need(
            !fs::symlink_metadata(ancestor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "diagnostic symlink",
        )?;
    }
    let metadata = fs::metadata(&path).map_err(|e| e.to_string())?;
    need(
        metadata.is_file() && metadata.len() <= limit as u64,
        "diagnostic input budget",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    need(bytes.len() <= limit, "diagnostic growing input")?;
    Ok(bytes)
}
fn write(path: &Path, value: &Value) -> Result<(), String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(&bytes)
        .map_err(|e| e.to_string())
}
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("diagnostic {key} missing"))
}

/// No original runner paths are dereferenced. Compiler and worker are explicit new dependencies.
pub fn prepare(
    stage: &Path,
    compiler: &Path,
    worker: &Path,
    image: &str,
    output: &Path,
) -> Result<Value, String> {
    prepare_selected(stage, compiler, worker, image, output, None)
}

/// Diagnostic execution of one frozen control. Never a code-repair input or approval.
pub fn prepare_control(
    stage: &Path,
    compiler: &Path,
    worker: &Path,
    image: &str,
    output: &Path,
    control_id: &str,
) -> Result<Value, String> {
    prepare_selected(stage, compiler, worker, image, output, Some(control_id))
}

fn prepare_selected(
    stage: &Path,
    compiler: &Path,
    worker: &Path,
    image: &str,
    output: &Path,
    control_id: Option<&str>,
) -> Result<Value, String> {
    need(!output.exists(), "diagnostic output exists")?;
    need(
        image.starts_with("sha256:")
            && image.len() == 71
            && image[7..]
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
        "diagnostic exact image ID required",
    )?;
    let receipt: Value = serde_json::from_slice(&read(&stage.join("stage-receipt.json"), 65536)?)
        .map_err(|e| e.to_string())?;
    need(
        receipt["schema"] == "agentlab.source_recipe_author_stage.v1"
            && receipt["reviewed"] == false
            && receipt["automaticPromotion"] == false
            && receipt["executionPerformed"] == false,
        "diagnostic stage identity",
    )?;
    let mut originals = Vec::new();
    for (name, field, limit) in [
        ("request.json", "requestSha256", 512 * 1024),
        ("proposal.json", "proposalSha256", 256 * 1024),
        ("design.json", "designSha256", 64 * 1024),
        ("design-runtime.cjs", "designRuntimeSha256", 1024 * 1024),
    ] {
        let bytes = read(&stage.join(name), limit)?;
        need(
            receipt[field] == digest(&bytes),
            "diagnostic original digest differs",
        )?;
        originals.push(bytes);
    }
    let request: Value = serde_json::from_slice(&originals[0]).map_err(|e| e.to_string())?;
    let proposal: Value = serde_json::from_slice(&originals[1]).map_err(|e| e.to_string())?;
    let design: Value = serde_json::from_slice(&originals[2]).map_err(|e| e.to_string())?;
    crate::maintainer_source_recipe_author::check_staged_design_review(
        stage,
        &receipt,
        &originals[0],
        &originals[2],
    )?;
    if receipt.get("diagnosticRepairPacketSha256").is_some()
        || stage.join("diagnostic-repair.json").exists()
    {
        let packet = read(
            &stage.join("diagnostic-repair.json"),
            crate::maintainer_source_repair::PACKET_LIMIT,
        )?;
        let validation = crate::maintainer_source_repair::check_output(
            &originals[0],
            &packet,
            &originals[1],
            &originals[2],
        )?;
        let stored = read(&stage.join("diagnostic-repair-output.json"), 65536)?;
        need(
            receipt["diagnosticRepairPacketSha256"] == digest(&packet)
                && receipt["diagnosticRepairOutputSha256"] == digest(&stored)
                && serde_json::from_slice::<Value>(&stored).map_err(|e| e.to_string())?
                    == validation,
            "diagnostic repair lineage differs",
        )?;
    }
    need(
        request["schema"] == "agentlab.source_recipe_author_request.v1"
            && request["reviewed"] == false
            && request["automaticPromotion"] == false
            && proposal["schema"] == "agentlab.source_recipe_author_proposal.v1"
            && design["schema"] == "agentlab.source_recipe_design.v2"
            && proposal["scopeSkillId"] == request["scope"]["id"]
            && design["scopeSkillId"] == proposal["scopeSkillId"],
        "diagnostic source identity",
    )?;
    let verifier = text(&proposal, "verifierSource")?;
    need(
        verifier.len() <= 128 * 1024
            && read(&stage.join("controls.cjs"), 128 * 1024)? == verifier.as_bytes(),
        "diagnostic verifier differs",
    )?;
    need(
        proposal["contract"]["checks"] == design["checks"],
        "diagnostic checks differ",
    )?;
    let checks = design["checks"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 64)
        .ok_or("diagnostic checks invalid")?;
    let mut ids = BTreeSet::new();
    for check in checks {
        need(
            check.as_object().is_some_and(|o| o.len() == 3)
                && ids.insert(text(check, "id")?)
                && text(check, "pointer")?.starts_with('/')
                && check.get("expected").is_some(),
            "diagnostic check malformed",
        )?;
    }
    let runtime = std::str::from_utf8(&originals[3]).map_err(|e| e.to_string())?;
    let manifest = crate::maintainer_source_recipe_author::runtime_manifest(runtime)?;
    need(
        manifest["scenarios"] == design["scenarios"] && manifest["controls"] == design["controls"],
        "diagnostic runtime design differs",
    )?;
    let files = manifest["files"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 16)
        .ok_or("diagnostic files invalid")?;
    let source_files = request["sourceFiles"]
        .as_array()
        .ok_or("diagnostic source inventory missing")?;
    let paths = proposal["sourcePaths"]
        .as_array()
        .ok_or("diagnostic source paths missing")?;
    need(
        paths.len() == files.len(),
        "diagnostic source path set differs",
    )?;
    let mut seen = BTreeSet::new();
    for file in files {
        let name = text(file, "path")?;
        need(
            !name.contains('\\')
                && !Path::new(name).is_absolute()
                && name
                    .split('/')
                    .all(|s| !s.is_empty() && s != "." && s != "..")
                && seen.insert(name)
                && paths.contains(&file["path"]),
            "diagnostic unsafe or duplicate source path",
        )?;
        let bytes = text(file, "content")?.as_bytes();
        need(
            file["byteCount"] == bytes.len()
                && file["sha256"] == digest(bytes)
                && source_files
                    .iter()
                    .filter(|f| f["path"] == file["path"])
                    .count()
                    == 1
                && source_files.contains(file),
            "diagnostic recorded source differs",
        )?;
    }
    let controls = manifest["controls"]
        .as_array()
        .ok_or("diagnostic controls missing")?;
    let baselines: Vec<_> = controls
        .iter()
        .filter(|c| c["role"] == "baseline")
        .collect();
    need(
        baselines.len() == 1
            && baselines[0]["edits"] == json!([])
            && baselines[0]["expectedFailedCheckIds"] == json!([]),
        "diagnostic baseline invalid",
    )?;
    text(baselines[0], "id")?;
    let selected = if let Some(id) = control_id {
        let matches: Vec<_> = controls.iter().filter(|c| c["id"] == id).collect();
        need(matches.len() == 1, "diagnostic control absent or ambiguous")?;
        matches[0]
    } else {
        baselines[0]
    };
    let role = text(selected, "role")?;
    need(
        crate::maintainer_source_operation::valid_control_id(text(selected, "id")?),
        "diagnostic control id invalid",
    )?;
    let failures = selected["expectedFailedCheckIds"]
        .as_array()
        .ok_or("diagnostic expected failures missing")?;
    let mut declared = BTreeSet::new();
    for failure in failures {
        let id = failure.as_str().ok_or("diagnostic failure id invalid")?;
        need(
            ids.contains(id) && declared.insert(id),
            "diagnostic failure id unknown or duplicate",
        )?;
    }
    need(
        match role {
            "baseline" => failures.is_empty() && selected["edits"] == json!([]),
            "reference" => {
                failures.is_empty() && selected["edits"].as_array().is_some_and(|e| !e.is_empty())
            }
            "wrong" => {
                !failures.is_empty() && selected["edits"].as_array().is_some_and(|e| !e.is_empty())
            }
            _ => false,
        },
        "diagnostic control declaration invalid",
    )?;
    let compiler_bytes = read(compiler, 16 * 1024 * 1024)?;
    let dependencies = request["policy"]["methodDependencies"]
        .as_array()
        .ok_or("diagnostic compiler binding missing")?;
    need(
        dependencies.len() == 1 && dependencies[0]["sha256"] == digest(&compiler_bytes),
        "diagnostic requires one original compiler dependency",
    )?;
    let worker_bytes = read(worker, 4 * 1024 * 1024)?;
    need(
        worker_bytes == include_bytes!("../../../scripts/source-recipe-diagnostic-worker.cjs"),
        "diagnostic worker differs from reviewed method",
    )?;
    let execution_request = json!({"schema":"agentlab.behavior_executor_request.v1","id":if control_id.is_some() {format!("source-recipe-control-{}-{}",text(selected,"id")?,digest(&originals[1]))} else {format!("source-recipe-baseline-{}",digest(&originals[1]))},"submittedSource":verifier,"submittedSourceSha256":digest(verifier.as_bytes())});
    let mut support = json!({"schema":"agentlab.source_recipe_diagnostic_support.v1","compilerSha256":digest(&compiler_bytes),"runtimeSource":runtime,"runtimeSha256":digest(&originals[3]),"files":files,"controlId":selected["id"]});
    if control_id.is_some() {
        support["selectedControl"] = selected.clone();
    }
    fs::create_dir(output).map_err(|e| e.to_string())?;
    let output = output.canonicalize().map_err(|e| e.to_string())?;
    write(&output.join("request.json"), &execution_request)?;
    write(&output.join("support.json"), &support)?;
    let descriptor = json!({"schema":"agentlab.contained_behavior_executor.v1","reviewed":true,"automaticPromotion":false,"imageId":image,"timeoutMs":30000,
        "diagnosticOracleSha256":digest(&serde_json::to_vec(&design["checks"]).map_err(|e|e.to_string())?),
        "workerPath":worker.canonicalize().map_err(|e|e.to_string())?,"workerSha256":digest(&worker_bytes),"compilerPath":compiler.canonicalize().map_err(|e|e.to_string())?,"compilerSha256":digest(&compiler_bytes),
        "supportPath":output.join("support.json"),"supportSha256":digest(&read(&output.join("support.json"),4*1024*1024)?)});
    write(&output.join("descriptor.json"), &descriptor)?;
    let mut intent = json!({"schema":"agentlab.source_recipe_diagnostic_intent.v1","originalStageReceipt":receipt,"source":request["source"],"controlId":selected["id"],"checks":design["checks"],
        "requestSha256":digest(&read(&output.join("request.json"),256*1024)?),"descriptorSha256":digest(&read(&output.join("descriptor.json"),65536)?),
        "diagnosticOnly":true,"verifierReviewed":false,"qualified":false,"revisionAuthenticated":false,"runtimeEquivalentToOriginal":false,"automaticPromotion":false,"authorityWritePerformed":false,"executionPerformed":false});
    if control_id.is_some() {
        intent["schema"] = json!("agentlab.source_recipe_control_diagnostic_intent.v1");
        intent["controlRole"] = selected["role"].clone();
        intent["expectedFailedCheckIds"] = selected["expectedFailedCheckIds"].clone();
        intent["supportSha256"] = descriptor["supportSha256"].clone();
    }
    write(&output.join("intent.json"), &intent)?;
    Ok(intent)
}

/// Reconstruct actual output without treating launcher exit zero as a behavior verdict.
pub fn feedback(inputs: &Path, capture: &Path, output: &Path) -> Result<Value, String> {
    let report = reconstruct_capture(inputs, capture)?;
    write(output, &report)?;
    Ok(report)
}

fn reconstruct_capture(inputs: &Path, capture: &Path) -> Result<Value, String> {
    let intent_bytes = read(&inputs.join("intent.json"), 128 * 1024)?;
    let request_bytes = read(&inputs.join("request.json"), 256 * 1024)?;
    need(
        read(&capture.join("request.json"), 256 * 1024)? == request_bytes,
        "diagnostic capture request differs",
    )?;
    let intent: Value = serde_json::from_slice(&intent_bytes).map_err(|e| e.to_string())?;
    let control = intent["schema"] == "agentlab.source_recipe_control_diagnostic_intent.v1";
    if control {
        let support: Value =
            serde_json::from_slice(&read(&inputs.join("support.json"), 4 * 1024 * 1024)?)
                .map_err(|e| e.to_string())?;
        need(
            intent["supportSha256"]
                == digest(&read(&inputs.join("support.json"), 4 * 1024 * 1024)?)
                && support["controlId"] == intent["controlId"]
                && support["selectedControl"]["id"] == intent["controlId"]
                && support["selectedControl"]["role"] == intent["controlRole"]
                && support["selectedControl"]["expectedFailedCheckIds"]
                    == intent["expectedFailedCheckIds"],
            "diagnostic selected control binding differs",
        )?;
    }
    let report = reconstruct_selected(
        &intent_bytes,
        &request_bytes,
        &read(&inputs.join("descriptor.json"), 65536)?,
        &read(&capture.join("process.json"), 65536)?,
        &read(&capture.join("worker-stdout.log"), 1024 * 1024)?,
        &read(&capture.join("worker-stderr.log"), 1024 * 1024)?,
        control,
    )?;
    Ok(report)
}

/// Independently reconstruct the entire portable diagnostic suite, not authority admission.
pub fn validate_suite(stage: &Path, suite: &Path, output: &Path) -> Result<Value, String> {
    let reconstructed = reconstruct_suite(stage, suite)?;
    write(output, &reconstructed)?;
    Ok(reconstructed)
}

/// Side-effect-free consumer shared by readback and reviewed lesson admission.
pub fn reconstruct_suite(stage: &Path, suite: &Path) -> Result<Value, String> {
    let original = read(&suite.join("result.json"), 128 * 1024)?;
    let result: Value = serde_json::from_slice(&original).map_err(|e| e.to_string())?;
    need(
        result["schema"] == "agentlab.source_recipe_control_suite_result.v1"
            && result["diagnosticOnly"] == true
            && result["qualified"] == false
            && result["semanticQualified"] == false
            && result["automaticPromotion"] == false
            && result["authorityWritePerformed"] == false,
        "suite diagnostic boundary differs",
    )?;
    let receipt: Value = serde_json::from_slice(&read(&stage.join("stage-receipt.json"), 65536)?)
        .map_err(|e| e.to_string())?;
    let mut originals = Vec::new();
    for (name, field, limit) in [
        ("request.json", "requestSha256", 512 * 1024),
        ("proposal.json", "proposalSha256", 256 * 1024),
        ("design.json", "designSha256", 64 * 1024),
        ("design-runtime.cjs", "designRuntimeSha256", 1024 * 1024),
    ] {
        let bytes = read(&stage.join(name), limit)?;
        need(
            receipt[field] == digest(&bytes),
            "suite original stage digest differs",
        )?;
        originals.push(bytes);
    }
    let design: Value = serde_json::from_slice(&originals[2]).map_err(|e| e.to_string())?;
    let proposal: Value = serde_json::from_slice(&originals[1]).map_err(|e| e.to_string())?;
    let author_request: Value = serde_json::from_slice(&originals[0]).map_err(|e| e.to_string())?;
    crate::maintainer_source_recipe_author::check_staged_design_review(
        stage,
        &receipt,
        &originals[0],
        &originals[2],
    )?;
    let runtime = std::str::from_utf8(&originals[3]).map_err(|e| e.to_string())?;
    let manifest = crate::maintainer_source_recipe_author::runtime_manifest(runtime)?;
    need(
        result["designSha256"] == digest(&originals[2])
            && proposal["contract"]["checks"] == design["checks"]
            && manifest["controls"] == design["controls"]
            && manifest["scenarios"] == design["scenarios"]
            && read(&stage.join("controls.cjs"), 128 * 1024)?
                == text(&proposal, "verifierSource")?.as_bytes(),
        "suite frozen design or verifier differs",
    )?;
    let controls = design["controls"]
        .as_array()
        .filter(|a| (4..=16).contains(&a.len()))
        .ok_or("suite controls missing")?;
    let mut ids = BTreeSet::new();
    need(
        controls.iter().all(|c| {
            c["id"].as_str().is_some_and(|id| ids.insert(id))
                && matches!(c["role"].as_str(), Some("baseline" | "reference" | "wrong"))
        }) && controls.iter().filter(|c| c["role"] == "baseline").count() == 1
            && controls.iter().filter(|c| c["role"] == "reference").count() >= 2
            && controls.iter().any(|c| c["role"] == "wrong"),
        "suite complete control inventory differs",
    )?;
    let reference = controls.iter().find(|c| c["role"] == "reference").unwrap();
    let rows = result["attempts"]
        .as_array()
        .ok_or("suite attempts missing")?;
    need(
        rows.len() == controls.len() + 1,
        "suite incomplete or duplicate recovery",
    )?;
    let directories: BTreeSet<_> = fs::read_dir(suite)
        .map_err(|e| e.to_string())?
        .map(|e| e.map(|e| e.file_name().to_string_lossy().into_owned()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?
        .into_iter()
        .filter(|n| n.starts_with("control-"))
        .collect();
    need(
        directories == (0..rows.len()).map(|i| format!("control-{i}")).collect(),
        "suite control directories differ",
    )?;
    let mut reports = Vec::new();
    let mut observed_captures = BTreeSet::new();
    for (index, row) in rows.iter().enumerate() {
        let selected = controls.get(index).unwrap_or(reference);
        let recovery = index == controls.len();
        need(
            row["controlId"] == selected["id"]
                && row["role"] == selected["role"]
                && row["recovery"] == recovery,
            "suite schedule or accepted-reference recovery differs",
        )?;
        let directory = suite.join(format!("control-{index}"));
        let captures: Vec<_> = fs::read_dir(&directory)
            .map_err(|e| e.to_string())?
            .filter_map(|e| e.ok())
            .filter(|e| {
                e.file_name()
                    .to_string_lossy()
                    .starts_with("contained-input-")
            })
            .map(|e| e.path())
            .collect();
        need(
            captures.len() == 1,
            "suite owned capture absent or ambiguous",
        )?;
        let intent: Value =
            serde_json::from_slice(&read(&directory.join("intent.json"), 128 * 1024)?)
                .map_err(|e| e.to_string())?;
        let support: Value =
            serde_json::from_slice(&read(&directory.join("support.json"), 4 * 1024 * 1024)?)
                .map_err(|e| e.to_string())?;
        let execution_request: Value =
            serde_json::from_slice(&read(&directory.join("request.json"), 256 * 1024)?)
                .map_err(|e| e.to_string())?;
        need(
            intent["originalStageReceipt"] == receipt
                && intent["checks"] == design["checks"]
                && intent["controlId"] == selected["id"]
                && support["selectedControl"] == *selected
                && support["runtimeSource"] == runtime
                && support["files"] == manifest["files"]
                && intent["source"] == author_request["source"]
                && execution_request["submittedSource"] == proposal["verifierSource"]
                && execution_request["submittedSourceSha256"]
                    == digest(text(&proposal, "verifierSource")?.as_bytes()),
            "suite control borrowed from different stage",
        )?;
        let report = reconstruct_capture(&directory, &captures[0])?;
        need(
            report["executionCompleted"] == true,
            "suite incomplete infrastructure execution",
        )?;
        let stored = read(&directory.join("feedback.json"), 128 * 1024)?;
        need(
            row["feedbackSha256"] == digest(&stored)
                && serde_json::from_slice::<Value>(&stored).map_err(|e| e.to_string())? == report
                && row["classification"] == report["classification"]
                && row["declarationMatched"] == report["declarationMatched"],
            "suite stored feedback differs from raw capture",
        )?;
        // Fresh executions must have different raw process receipts, not copied prior captures.
        need(
            observed_captures.insert(text(&report, "processSha256")?.to_owned()),
            "suite duplicate execution capture",
        )?;
        reports.push(report);
    }
    let matched = reports
        .iter()
        .all(|r| r["executionCompleted"] == true && r["declarationMatched"] == true);
    need(
        result["status"]
            == if matched {
                "declarations-matched"
            } else {
                "review-declaration-mismatch"
            },
        "suite aggregate verdict differs",
    )?;
    let reconstructed = json!({"schema":"agentlab.source_recipe_control_suite_readback.v1",
        "suiteResultSha256":digest(&original),"designSha256":digest(&originals[2]),
        "proposalSha256":digest(&originals[1]),"status":result["status"],"completeInventoryReconstructed":true,
        "controlCount":controls.len(),"acceptedReferenceRecoveryReconstructed":true,"controls":reports,
        "diagnosticOnly":true,"qualified":false,"semanticQualified":false,"producerAuthenticated":false,
        "authorityWritePerformed":false,"automaticPromotion":false,
        "nextAction":if matched {"independent-semantic-review-and-knowledge-admission"} else {"review-frozen-declaration-disagreement"}});
    Ok(reconstructed)
}

/// Shared retained-byte reconstruction for diagnostics and bounded construction repair.
pub(crate) fn reconstruct(
    intent_bytes: &[u8],
    request_bytes: &[u8],
    descriptor_bytes: &[u8],
    process_bytes: &[u8],
    stdout: &[u8],
    stderr: &[u8],
) -> Result<Value, String> {
    reconstruct_selected(
        intent_bytes,
        request_bytes,
        descriptor_bytes,
        process_bytes,
        stdout,
        stderr,
        false,
    )
}

fn reconstruct_selected(
    intent_bytes: &[u8],
    request_bytes: &[u8],
    descriptor_bytes: &[u8],
    process_bytes: &[u8],
    stdout: &[u8],
    stderr: &[u8],
    control: bool,
) -> Result<Value, String> {
    let intent: Value = serde_json::from_slice(&intent_bytes).map_err(|e| e.to_string())?;
    need(
        intent["schema"]
            == if control {
                "agentlab.source_recipe_control_diagnostic_intent.v1"
            } else {
                "agentlab.source_recipe_diagnostic_intent.v1"
            }
            && intent["diagnosticOnly"] == true
            && intent["qualified"] == false
            && intent["verifierReviewed"] == false,
        "diagnostic intent differs",
    )?;
    need(
        intent["requestSha256"] == digest(&request_bytes)
            && intent["descriptorSha256"] == digest(&descriptor_bytes),
        "diagnostic input changed",
    )?;
    let request: Value = serde_json::from_slice(&request_bytes).map_err(|e| e.to_string())?;
    let descriptor: Value = serde_json::from_slice(&descriptor_bytes).map_err(|e| e.to_string())?;
    need(
        descriptor["diagnosticOracleSha256"]
            == digest(&serde_json::to_vec(&intent["checks"]).map_err(|e| e.to_string())?),
        "diagnostic frozen oracle changed",
    )?;
    let process: Value = serde_json::from_slice(&process_bytes).map_err(|e| e.to_string())?;
    need(
        process["schema"] == "agentlab.contained_behavior_process.v1"
            && process["requestSha256"] == intent["requestSha256"]
            && process["descriptorSha256"] == intent["descriptorSha256"]
            && process["imageId"] == descriptor["imageId"],
        "diagnostic capture binding differs",
    )?;
    need(
        process["stdoutSha256"] == digest(&stdout) && process["stderrSha256"] == digest(&stderr),
        "diagnostic raw logs differ",
    )?;
    let normal = process["exitCode"] == 0
        && process["timedOut"] == false
        && process["logBudgetExceeded"] == false;
    let mut checks = Vec::new();
    if normal {
        let observed: Value = serde_json::from_slice(&stdout).map_err(|e| e.to_string())?;
        let verifier_stdout = text(&observed, "verifierStdout")?;
        need(
            observed["verifierStdoutSha256"] == digest(verifier_stdout.as_bytes())
                && serde_json::from_str::<Value>(verifier_stdout).map_err(|e| e.to_string())?
                    == observed["observations"],
            "diagnostic original verifier output differs",
        )?;
        need(
            observed["id"] == request["id"]
                && observed["submittedSource"] == request["submittedSource"]
                && observed["submittedSourceSha256"] == request["submittedSourceSha256"],
            "diagnostic worker identity differs",
        )?;
        let frozen = intent["checks"]
            .as_array()
            .filter(|a| !a.is_empty() && a.len() <= 64)
            .ok_or("diagnostic frozen checks missing")?;
        for check in frozen {
            let pointer = text(check, "pointer")?;
            let actual = observed["observations"].pointer(pointer);
            checks.push(json!({"id":text(check,"id")?,"pointer":pointer,"expected":check["expected"],"present":actual.is_some(),"actual":actual,"passed":actual == check.get("expected")}));
        }
    }
    let baseline_passed = normal && checks.iter().all(|c| c["passed"] == true);
    if control {
        need(
            intent["supportSha256"] == descriptor["supportSha256"],
            "diagnostic control support differs",
        )?;
        let expected = intent["expectedFailedCheckIds"]
            .as_array()
            .ok_or("diagnostic control failure set missing")?;
        let expected_set: BTreeSet<_> = expected
            .iter()
            .map(|v| v.as_str().ok_or("diagnostic failure id invalid"))
            .collect::<Result<_, _>>()?;
        let failed: BTreeSet<_> = checks
            .iter()
            .filter(|c| c["passed"] != true)
            .map(|c| c["id"].as_str().unwrap())
            .collect();
        let matches = normal && failed == expected_set;
        return Ok(
            json!({"schema":"agentlab.source_recipe_control_diagnostic_feedback.v1",
            "intentSha256":digest(intent_bytes),"processSha256":digest(process_bytes),"stdoutSha256":digest(stdout),"stderrSha256":digest(stderr),
            "controlId":intent["controlId"],"controlRole":intent["controlRole"],"expectedFailedCheckIds":expected,
            "observedFailedCheckIds":if normal {json!(failed)} else {Value::Null},"missingExpectedFailureIds":if normal {json!(expected_set.difference(&failed).collect::<Vec<_>>())} else {Value::Null},
            "unexpectedFailedCheckIds":if normal {json!(failed.difference(&expected_set).collect::<Vec<_>>())} else {Value::Null},
            "classification":if !normal {"verifier-execution-infrastructure-failure"} else if matches {"control-declaration-matched"} else {"control-declaration-mismatch"},
            "executionCompleted":normal,"declarationMatched":matches,"checks":checks,
            "exitCode":process["exitCode"],"timedOut":process["timedOut"],"logBudgetExceeded":process["logBudgetExceeded"],
            "diagnosticOnly":true,"qualified":false,"semanticQualified":false,"formalIsolationQualified":false,
            "automaticPromotion":false,"authorityWritePerformed":false,
            "nextAction":if !normal {"review-verifier-execution-failure"} else if matches {"independent-semantic-review-and-reference-recovery"} else {"review-control-failure-attribution-without-changing-expectations"}}),
        );
    }
    let report = json!({"schema":"agentlab.source_recipe_diagnostic_feedback.v1","intentSha256":digest(&intent_bytes),"processSha256":digest(&process_bytes),"stdoutSha256":digest(&stdout),"stderrSha256":digest(&stderr),
        "classification":if !normal {"verifier-execution-infrastructure-failure"} else if baseline_passed {"baseline-observations-passed"} else {"baseline-observations-rejected"},
        "exitCode":process["exitCode"],"timedOut":process["timedOut"],"logBudgetExceeded":process["logBudgetExceeded"],"baselinePassed":baseline_passed,"checks":checks,
        "diagnosticOnly":true,"qualified":false,"wrongControlsExecuted":0,"formalIsolationQualified":false,"automaticPromotion":false,"authorityWritePerformed":false,
        "nextAction":if !normal {"review-verifier-execution-failure"} else if baseline_passed {"independent-semantic-review-and-complete-control-calibration"} else {"Agent-owned-baseline-observation-repair"}});
    Ok(report)
}
