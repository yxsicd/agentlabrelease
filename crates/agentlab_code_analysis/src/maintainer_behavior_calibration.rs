//! Reviewed control execution using the existing behavior executor protocol.
//! This is trusted diagnostic orchestration, not runtime/producer attestation.
use crate::{digest, maintainer_behavior_checks as checks, maintainer_behavior_loop as runner};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, io::Write, path::Path};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn save(path: &Path, bytes: &[u8]) -> Result<(), String> {
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(bytes)
        .map_err(|e| e.to_string())
}
fn record(path: &Path, value: &Value) -> Result<Vec<u8>, String> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    save(path, &bytes)?;
    Ok(bytes)
}

#[cfg(unix)]
pub fn execute(contract_bytes: &[u8], recipe_bytes: &[u8], out: &Path) -> Result<Value, String> {
    let contract = checks::validate_contract(contract_bytes)?;
    need(
        recipe_bytes.len() <= 4 * 1024 * 1024,
        "calibration recipe budget",
    )?;
    let recipe: Value = serde_json::from_slice(recipe_bytes).map_err(|e| e.to_string())?;
    need(
        recipe["schema"] == "agentlab.behavior_calibration_recipe.v1"
            && recipe["reviewed"] == true
            && recipe["automaticPromotion"] == false
            && recipe["contractSha256"] == digest(contract_bytes),
        "calibration recipe binding",
    )?;
    let controls = contract["controls"].as_array().unwrap();
    need(
        controls.iter().all(|c| c["role"] != "agent-attempt"),
        "calibration cannot enroll Agent attempts",
    )?;
    let rows = recipe["sources"]
        .as_array()
        .filter(|a| a.len() == controls.len())
        .ok_or("calibration source inventory incomplete")?;
    let mut sources = BTreeMap::new();
    for row in rows {
        let id = row["id"].as_str().ok_or("calibration source id")?;
        let source = row["submittedSource"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 256 * 1024)
            .ok_or("calibration source bytes")?;
        need(
            sources.insert(id, source).is_none(),
            "calibration duplicate source id",
        )?;
    }
    for control in controls {
        let source = sources
            .get(control["id"].as_str().unwrap())
            .ok_or("calibration missing declared source")?;
        need(
            control["submittedSourceSha256"] == digest(source.as_bytes()),
            "calibration source differs",
        )?;
    }
    let recovery = recipe["recoveryControlId"]
        .as_str()
        .ok_or("calibration recovery missing")?;
    need(
        controls
            .iter()
            .any(|c| c["id"] == recovery && c["role"] == "accepted"),
        "calibration recovery must be accepted source",
    )?;
    let command = &recipe["executorCommand"];
    need(
        command["cwd"] == "."
            && command["args"]
                .as_array()
                .is_some_and(|a| a.iter().filter(|v| v.as_str() == Some("{request}")).count() == 1)
            && command["timeoutMs"]
                .as_u64()
                .is_some_and(|n| n > 0 && n <= contract["workerDeadlineMs"].as_u64().unwrap()),
        "calibration executor request/deadline",
    )?;
    crate::maintainer_operation_exec::validate_command(
        command,
        out.parent().ok_or("calibration output parent")?,
    )?;
    let mut immutable = runner::pinned_inputs(&recipe)?;
    fs::create_dir(out).map_err(|e| e.to_string())?;
    let out = out.canonicalize().map_err(|e| e.to_string())?;
    save(&out.join("contract.json"), contract_bytes)?;
    save(&out.join("recipe.json"), recipe_bytes)?;
    immutable.push((out.join("contract.json"), digest(contract_bytes)));
    immutable.push((out.join("recipe.json"), digest(recipe_bytes)));
    let mut capture = json!({"schema":"agentlab.behavior_worker_capture.v1","contractSha256":digest(contract_bytes),"workers":[]});
    for key in [
        "candidateId",
        "candidateSha256",
        "sourceRevision",
        "methodSha256",
        "compilerSha256",
        "runtime",
    ] {
        capture[key] = contract[key].clone();
    }
    let result = (|| -> Result<Value, String> {
        // Index-based directories avoid interpreting arbitrary business IDs as paths.
        for index in 0..=controls.len() {
            runner::recheck(&immutable)?;
            let id = if index == controls.len() {
                recovery
            } else {
                controls[index]["id"].as_str().unwrap()
            };
            let source = sources[id];
            let dir = out.join(format!("control-{index}"));
            fs::create_dir(&dir).map_err(|e| e.to_string())?;
            let request = json!({"schema":"agentlab.behavior_executor_request.v1","id":id,
                "originalSourceSha256":contract["originalSourceSha256"],"submittedSourceSha256":digest(source.as_bytes()),
                "submittedSource":source,"checks":contract["checks"].as_array().unwrap().iter()
                    .map(|c| json!({"id":c["id"],"input":c["input"]})).collect::<Vec<_>>()});
            let request_path = dir.join("executor-request.json");
            let bytes = record(&request_path, &request)?;
            immutable.push((request_path.clone(), digest(&bytes)));
            let (process, stdout) = runner::invoke(command, &request_path, &dir, "executor", &[])?;
            runner::recheck(&immutable)?;
            let worker = json!({"id":id,"execution":{"exitCode":process["exitCode"],"timedOut":false,
                "durationMs":process["durationMs"],"stdoutSha256":digest(stdout.as_bytes()),"stdout":stdout}});
            record(&dir.join("worker.json"), &worker)?;
            if index < controls.len() {
                capture["workers"].as_array_mut().unwrap().push(worker);
            } else {
                // Recovery is an additional run of the SAME accepted source, not
                // a second distinct positive implementation or stronger coverage.
                let bytes = record(&out.join("capture.json"), &capture)?;
                let feedback = checks::verify(contract_bytes, &bytes)?;
                record(&out.join("feedback.json"), &feedback)?;
                let mut recovered = capture.clone();
                let position = controls.iter().position(|c| c["id"] == recovery).unwrap();
                recovered["workers"][position] = worker;
                let recovered_bytes = record(&out.join("recovery-capture.json"), &recovered)?;
                let recovery_feedback = checks::verify(contract_bytes, &recovered_bytes)?;
                record(&out.join("recovery-feedback.json"), &recovery_feedback)?;
                runner::freeze_tree(&dir, &mut immutable, 0)?;
                runner::recheck(&immutable)?;
                return Ok(
                    json!({"feedback":feedback,"recoveryFeedback":recovery_feedback,
                    "captureSha256":digest(&bytes),"recoveryCaptureSha256":digest(&recovered_bytes)}),
                );
            }
            runner::freeze_tree(&dir, &mut immutable, 0)?;
        }
        Err("calibration missing recovery".into())
    })();
    let passed = result.as_ref().is_ok_and(|v| {
        v["feedback"]["nextAction"] == "execute-agent-attempt"
            && v["recoveryFeedback"]["nextAction"] == "execute-agent-attempt"
    });
    let receipt = json!({"schema":"agentlab.behavior_calibration_execution.v1",
        "status":if result.is_err() {"infrastructure-failed"} else if passed {"calibration-passed"} else {"review-required"},
        "contractSha256":digest(contract_bytes),"recipeSha256":digest(recipe_bytes),
        "result":result.as_ref().ok(),"error":result.as_ref().err(),"qualified":false,"automaticPromotion":false,
        "producerAuthenticated":false,"securitySandboxed":false,"authorityWritePerformed":false});
    record(&out.join("calibration-result.json"), &receipt)?;
    result?;
    Ok(receipt)
}

/// One reviewed dispatch connects fresh calibration to the EXISTING bounded
/// repair loop. Template capture binding is explicitly deferred, never forged.
#[cfg(unix)]
pub fn execute_cycle(
    contract: &[u8],
    calibration_recipe: &[u8],
    template_bytes: &[u8],
    out: &Path,
) -> Result<Value, String> {
    let existed = out.exists();
    let result = execute_cycle_inner(contract, calibration_recipe, template_bytes, out);
    if let Err(error) = &result {
        // Never add a failure receipt to a prior run when output reuse rejects.
        if !existed && out.is_dir() && !out.join("cycle-result.json").exists() {
            record(
                &out.join("cycle-result.json"),
                &json!({
                    "schema":"agentlab.calibrated_behavior_cycle.v1","status":"execution-failed",
                    "error":error,"dispatchState":"inspect-retained-process-captures",
                    "qualified":false,"automaticPromotion":false,"authorityWritePerformed":false
                }),
            )?;
        }
    }
    result
}

#[cfg(unix)]
fn execute_cycle_inner(
    contract: &[u8],
    calibration_recipe: &[u8],
    template_bytes: &[u8],
    out: &Path,
) -> Result<Value, String> {
    checks::validate_contract(contract)?;
    need(
        template_bytes.len() <= 256 * 1024 && calibration_recipe.len() <= 4 * 1024 * 1024,
        "calibration loop template budget",
    )?;
    let template: Value = serde_json::from_slice(template_bytes).map_err(|e| e.to_string())?;
    need(
        template["schema"] == "agentlab.calibrated_behavior_loop_template.v1"
            && template["reviewed"] == true
            && template["automaticPromotion"] == false
            && template["contractSha256"] == digest(contract)
            && template["calibrationRecipeSha256"] == digest(calibration_recipe)
            && template.get("captureSha256").is_none(),
        "calibration loop template binding",
    )?;
    let calibration: Value =
        serde_json::from_slice(calibration_recipe).map_err(|e| e.to_string())?;
    need(
        template["executorCommand"] == calibration["executorCommand"],
        "calibration and attempt executor differ",
    )?;
    let mut immutable = runner::pinned_inputs(&template)?;
    fs::create_dir(out).map_err(|e| e.to_string())?;
    let out = out.canonicalize().map_err(|e| e.to_string())?;
    save(&out.join("loop-template.json"), template_bytes)?;
    immutable.push((out.join("loop-template.json"), digest(template_bytes)));
    let calibration_root = out.join("calibration");
    let receipt = execute(contract, calibration_recipe, &calibration_root)?;
    runner::recheck(&immutable)?;
    if receipt["status"] != "calibration-passed" {
        let result = json!({"schema":"agentlab.calibrated_behavior_cycle.v1","status":"calibration-review-required",
            "calibration":receipt,"agentDispatched":false,"qualified":false,"automaticPromotion":false,
            "participantAuthenticated":false,"authorityWritePerformed":false});
        record(&out.join("cycle-result.json"), &result)?;
        return Ok(result);
    }
    let capture = fs::read(calibration_root.join("capture.json")).map_err(|e| e.to_string())?;
    let mut pinned_calibration = Vec::new();
    runner::freeze_tree(&calibration_root, &mut pinned_calibration, 0)?;
    let mut recipe = template.clone();
    recipe["schema"] = json!("agentlab.behavior_loop_recipe.v1");
    recipe["captureSha256"] = json!(digest(&capture));
    recipe
        .as_object_mut()
        .unwrap()
        .remove("calibrationRecipeSha256");
    for input in calibration["immutableInputs"]
        .as_array()
        .ok_or("calibration immutable inputs")?
    {
        let inputs = recipe["immutableInputs"]
            .as_array_mut()
            .ok_or("calibration template immutable inputs")?;
        if !inputs.contains(input) {
            inputs.push(input.clone());
        }
    }
    for (path, sha) in &pinned_calibration {
        if path.is_file() {
            recipe["immutableInputs"]
                .as_array_mut()
                .ok_or("calibration template immutable inputs")?
                .push(json!({"path":path,"sha256":sha}));
        }
    }
    // Pin original authorization separately from the generated capture binding.
    recipe["immutableInputs"]
        .as_array_mut()
        .unwrap()
        .push(json!({"path":out.join("loop-template.json"),"sha256":digest(template_bytes)}));
    let recipe_bytes = record(&out.join("bound-loop-recipe.json"), &recipe)?;
    let loop_result = runner::execute(contract, &capture, &recipe_bytes, &out.join("attempts"))?;
    runner::recheck(&pinned_calibration)?;
    runner::recheck(&immutable)?;
    let result = json!({"schema":"agentlab.calibrated_behavior_cycle.v1","status":loop_result["status"],
        "calibration":receipt,"loop":loop_result,"agentDispatched":true,"qualified":false,"automaticPromotion":false,
        "participantAuthenticated":false,"authorityWritePerformed":false});
    record(&out.join("cycle-result.json"), &result)?;
    Ok(result)
}

#[cfg(not(unix))]
pub fn execute(_: &[u8], _: &[u8], _: &Path) -> Result<Value, String> {
    Err("calibration requires Unix process-group capture".into())
}
#[cfg(not(unix))]
pub fn execute_cycle(_: &[u8], _: &[u8], _: &[u8], _: &Path) -> Result<Value, String> {
    Err("calibration requires Unix process-group capture".into())
}
