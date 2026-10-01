//! Recorded-content domain calibration consumer; no execution, admission or runtime qualification.
use crate::digest;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
const METHOD: &[u8] = include_bytes!("../../../scripts/calibrate-harmony-stage-controls.cjs");

/// Recover prior owned feedback only after reconstructing its retained capture.
/// A prior plan hash by itself is not enough to suppress new scheduling.
#[allow(clippy::too_many_arguments)]
pub fn resume(
    candidate: &[u8],
    downstream: &[u8],
    contract: &[u8],
    current: &[u8],
    current_sha: &str,
    previous_plan: &[u8],
    previous_capture: &[u8],
    previous_sha: &str,
) -> Result<Value, String> {
    let reconstructed = plan(
        candidate,
        downstream,
        contract,
        previous_capture,
        previous_sha,
        None,
    )?;
    let previous: Value = serde_json::from_slice(previous_plan).map_err(|e| e.to_string())?;
    for key in [
        "schema",
        "candidateId",
        "candidateSha256",
        "sourceRevision",
        "sourceSetSha256",
        "knowledgeCutSha256",
        "contractSha256",
        "calibrationSha256",
        "taskSha256",
        "nextAction",
        "semanticSeamCalibrationPassed",
        "acceptedControlPassed",
        "killedSemanticVariantCount",
        "qualified",
        "automaticPromotion",
        "authorityWritePerformed",
        "agentExecutionPerformed",
    ] {
        need(
            previous[key] == reconstructed[key],
            "stage previous plan contradicts retained capture",
        )?;
    }
    let mut result = plan(
        candidate,
        downstream,
        contract,
        current,
        current_sha,
        Some(&serde_json::to_vec(&reconstructed).map_err(|e| e.to_string())?),
    )?;
    result["previousCalibrationSha256"] = json!(previous_sha);
    result["previousFeedbackSha256"] = json!(digest(previous_plan));
    result["previousCaptureReconstructed"] = json!(true);
    Ok(result)
}
fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|x| !x.is_empty())
        .ok_or_else(|| format!("stage feedback {key} absent"))
}
fn rows<'a>(v: &'a Value, key: &str) -> Result<&'a Vec<Value>, String> {
    v[key]
        .as_array()
        .ok_or_else(|| format!("stage feedback {key} absent"))
}
fn index(v: &Value, key: &str, max: usize) -> Result<usize, String> {
    v[key]
        .as_u64()
        .and_then(|n| usize::try_from(n).ok())
        .filter(|n| *n <= max)
        .ok_or_else(|| format!("stage feedback {key} invalid"))
}
pub fn plan(
    candidate_bytes: &[u8],
    downstream_bytes: &[u8],
    contract_bytes: &[u8],
    receipt_bytes: &[u8],
    expected_sha: &str,
    previous: Option<&[u8]>,
) -> Result<Value, String> {
    need(
        digest(receipt_bytes) == expected_sha,
        "stage receipt digest differs",
    )?;
    let parse = |b: &[u8]| serde_json::from_slice::<Value>(b).map_err(|e| e.to_string());
    let candidate = parse(candidate_bytes)?;
    let downstream = parse(downstream_bytes)?;
    let contract = parse(contract_bytes)?;
    let receipt = parse(receipt_bytes)?;
    let candidate_sha = digest(&serde_json::to_vec(&candidate).map_err(|e| e.to_string())?);
    need(
        contract["schema"] == "agentlab.harmony_stage_control_contract.v1"
            && contract["reviewed"] == true
            && contract["candidateId"] == candidate["id"]
            && contract["candidateSha256"] == candidate_sha
            && contract["sourceRevision"] == candidate["sourceRevision"]
            && downstream["schema"] == "agentlab.maintainer_downstream_plan.v1"
            && downstream["candidateId"] == candidate["id"]
            && downstream["candidateSha256"] == candidate_sha
            && downstream["sourceRevision"] == candidate["sourceRevision"],
        "stage candidate/contract/plan binding differs",
    )?;
    for key in ["sourceSetSha256", "knowledgeCutSha256"] {
        let _ = text(&candidate, key)?;
        need(
            downstream[key] == candidate[key],
            "stage source/knowledge cut differs",
        )?;
    }
    need(
        downstream["automaticPromotion"] == false
            && rows(&downstream, "actions")?
                .iter()
                .all(|a| a["executionAuthorized"] == false),
        "stage pending actions overclaim execution",
    )?;
    need(
        ["contextPaths", "editablePaths"].iter().any(|key| {
            candidate[key]
                .as_array()
                .is_some_and(|paths| paths.contains(&contract["modulePath"]))
        }),
        "stage module outside candidate context",
    )?;
    need(
        receipt["schema"] == "agentlab.harmony_stage_control_calibration.v2"
            && receipt["contractSha256"] == digest(contract_bytes)
            && receipt["methodSha256"] == digest(METHOD)
            && receipt["sourceRevision"] == candidate["sourceRevision"]
            && receipt["qualified"] == false
            && receipt["automaticPromotion"] == false
            && receipt["authorityWritePerformed"] == false,
        "stage receipt binding or scope differs",
    )?;
    let variants = rows(&contract, "variants")?;
    let configs = rows(&contract, "configurations")?;
    need(
        variants.len() >= 2 && configs.len() >= 3,
        "stage independent controls missing",
    )?;
    let mut ids = BTreeSet::from(["baseline".to_string()]);
    let mut mutations = BTreeSet::new();
    for variant in variants {
        need(
            ids.insert(text(variant, "id")?.into())
                && mutations.insert(
                    serde_json::to_string(&json!([
                        variant["path"],
                        variant["from"],
                        variant["to"]
                    ]))
                    .map_err(|e| e.to_string())?,
                ),
            "stage duplicate variant",
        )?;
    }
    let mut checks = BTreeSet::from([
        "stage-created".to_string(),
        "application-environment-registration".to_string(),
        "stage-destroyed".to_string(),
    ]);
    let mut dimensions = BTreeSet::new();
    for (i, config) in configs.iter().enumerate() {
        need(
            checks.insert(text(config, "id")?.into())
                && config["language"].is_string()
                && config["colorMode"].is_i64(),
            "stage configuration invalid",
        )?;
        if i > 0 {
            let changed = ["language", "colorMode"]
                .into_iter()
                .filter(|key| configs[i - 1][key] != config[key])
                .collect::<Vec<_>>();
            need(
                changed.len() == 1,
                "stage configuration controls confounded",
            )?;
            dimensions.insert(changed[0]);
        }
    }
    need(
        dimensions.len() == 2,
        "stage configuration dimensions incomplete",
    )?;
    let controls = rows(&receipt, "controls")?;
    let infrastructure = !receipt["infrastructureFailure"].is_null();
    need(controls.len() <= variants.len() + 1, "stage extra controls")?;
    if infrastructure {
        need(
            controls.len() < variants.len() + 1
                && receipt["infrastructureFailure"]["id"]
                    == if controls.is_empty() {
                        json!("baseline")
                    } else {
                        variants[controls.len() - 1]["id"].clone()
                    }
                && (receipt["infrastructureFailure"]["exitCode"] != 0
                    || receipt["infrastructureFailure"]["error"].is_string()),
            "stage infrastructure failure contradicts controls",
        )?;
    } else {
        need(
            controls.len() == variants.len() + 1,
            "stage terminal controls missing",
        )?;
    }
    let mut projection = Vec::new();
    let mut accepted = false;
    let mut killed = 0;
    for (i, control) in controls.iter().enumerate() {
        let expected_id = if i == 0 {
            "baseline"
        } else {
            text(&variants[i - 1], "id")?
        };
        need(
            control["id"] == expected_id
                && control["completed"] == true
                && control["contractSha256"] == receipt["contractSha256"]
                && control["sourceRevision"] == receipt["sourceRevision"]
                && control["compilerSha256"] == receipt["compiler"]["sha256"],
            "stage control binding differs",
        )?;
        let execution = &control["workerExecution"];
        let stdout = text(execution, "stdout")?;
        let mut body = control.as_object().ok_or("stage control invalid")?.clone();
        body.remove("workerExecution");
        need(
            execution["exitCode"] == 0
                && execution["durationMs"].as_u64().is_some_and(|n| n > 0)
                && execution["stderr"].is_string()
                && execution["stdoutSha256"] == digest(stdout.as_bytes())
                && parse(stdout.as_bytes())? == Value::Object(body),
            "stage raw worker capture differs",
        )?;
        let mut sources = BTreeMap::new();
        for source in rows(control, "sources")? {
            let original = text(source, "originalSource")?;
            need(
                source["sha256"] == digest(original.as_bytes())
                    && sources.insert(text(source, "path")?, original).is_none(),
                "stage source bytes differ",
            )?;
        }
        need(
            sources.contains_key(text(&contract, "modulePath")?),
            "stage module source absent",
        )?;
        let stage_path = text(control, "executedStagePath")?;
        let original_stage = *sources
            .get(stage_path)
            .ok_or("stage executed source absent")?;
        let mut expected_source = original_stage.to_string();
        if i > 0 {
            let variant = &variants[i - 1];
            let mut observed = control["mutation"].clone();
            need(observed["applied"] == true, "stage mutation not applied")?;
            observed
                .as_object_mut()
                .ok_or("stage mutation invalid")?
                .remove("applied");
            need(observed == *variant, "stage declared mutation differs")?;
            let from = text(variant, "from")?;
            let to = variant["to"]
                .as_str()
                .ok_or("stage mutation replacement absent")?;
            need(from != to, "stage empty mutation")?;
            let original = sources
                .get(text(variant, "path")?)
                .ok_or("stage mutation source absent")?;
            need(
                original.matches(from).count() == 1,
                "stage mutation absent or ambiguous",
            )?;
            if variant["path"] == stage_path {
                expected_source = original_stage.replacen(from, to, 1);
            }
        } else {
            need(control["mutation"].is_null(), "stage baseline mutated")?;
        }
        need(
            control["executedStageSource"] == expected_source
                && control["typeErasedStageSource"].is_string(),
            "stage executed source differs",
        )?;
        let logs = rows(control, "logs")?;
        let create_end = index(control, "createLogEnd", logs.len())?;
        let destroy_start = index(control, "destroyLogStart", logs.len())?;
        let has = |slice: &[Value], marker: &str| {
            slice.iter().any(|l| {
                l["level"] == "info" && l["text"].as_str().is_some_and(|t| t.contains(marker))
            })
        };
        let registrations = rows(control, "registrations")?;
        let mut calculated = vec![
            json!({"id":"stage-created","passed":has(&logs[..create_end],text(&contract,"createMarker")?)}),
            json!({"id":"application-environment-registration","passed":registrations.len()==1 && registrations[0]["owner"]=="application" && registrations[0]["event"]==contract["eventName"] && has(&logs[..create_end],text(&contract,"registrationMarker")?)}),
        ];
        let ranges = rows(control, "configurationRanges")?;
        need(
            ranges.len() == configs.len(),
            "stage configuration ranges missing",
        )?;
        let mut cursor = create_end;
        for (config, range) in configs.iter().zip(ranges) {
            let start = index(range, "start", logs.len())?;
            let end = index(range, "end", logs.len())?;
            need(
                range["id"] == config["id"]
                    && range["input"]
                        == json!({"language":config["language"],"colorMode":config["colorMode"]})
                    && start == cursor
                    && end >= start,
                "stage configuration range differs",
            )?;
            cursor = end;
            let prefix = text(&contract, "configurationPrefix")?;
            let observations = logs[start..end]
                .iter()
                .filter(|l| {
                    l["level"] == "info"
                        && l["text"].as_str().is_some_and(|t| t.starts_with(prefix))
                })
                .collect::<Vec<_>>();
            let observed = observations
                .first()
                .and_then(|l| l["text"].as_str())
                .and_then(|t| serde_json::from_str::<Value>(&t[prefix.len()..]).ok());
            let passed = observations.len() == 1
                && observed.is_some_and(|v| {
                    v["language"] == config["language"] && v["colorMode"] == config["colorMode"]
                });
            calculated.push(json!({"id":config["id"],"passed":passed}));
        }
        need(cursor == destroy_start, "stage lifecycle range differs")?;
        calculated.push(json!({"id":"stage-destroyed","passed":has(&logs[destroy_start..],text(&contract,"destroyMarker")?)}));
        need(
            control["checks"] == json!(calculated),
            "stage checks contradict raw observations",
        )?;
        let passed = calculated.iter().all(|c| c["passed"] == true);
        need(
            control["verdict"] == if passed { "accept" } else { "reject" },
            "stage verdict contradicts checks",
        )?;
        let intended = if i == 0 {
            false
        } else {
            let required = rows(&variants[i - 1], "expectedFailedChecks")?;
            need(
                !required.is_empty()
                    && required
                        .iter()
                        .all(|id| id.as_str().is_some_and(|id| checks.contains(id))),
                "stage intended checks invalid",
            )?;
            required.iter().all(|id| {
                calculated
                    .iter()
                    .any(|c| c["id"] == *id && c["passed"] == false)
            })
        };
        need(
            if i == 0 {
                control["intendedFailureObserved"].is_null()
            } else {
                control["intendedFailureObserved"] == intended
            },
            "stage intended failure contradicts checks",
        )?;
        if i == 0 {
            accepted = passed;
        } else if !passed && intended {
            killed += 1;
        }
        projection
            .push(json!({"id":expected_id,"checks":calculated,"intendedFailureObserved":intended}));
    }
    let calibrated = !infrastructure
        && controls.len() == variants.len() + 1
        && accepted
        && killed == variants.len();
    need(
        receipt["semanticSeamCalibrationPassed"] == calibrated,
        "stage calibration summary contradicts evidence",
    )?;
    let decision = if infrastructure {
        "repair-domain-calibration-environment"
    } else if calibrated {
        "review-and-admit-scoped-domain-calibration"
    } else {
        "repair-domain-oracle-or-controls"
    };
    let task_sha=digest(&serde_json::to_vec(&json!({"candidateSha256":candidate_sha,"contractSha256":digest(contract_bytes),"methodSha256":receipt["methodSha256"],"compiler":receipt["compiler"],"controls":projection,"infrastructureFailure":receipt["infrastructureFailure"],"decision":decision})).map_err(|e|e.to_string())?);
    let mut unchanged = false;
    if let Some(bytes) = previous {
        let p = parse(bytes)?;
        need(
            p["schema"] == "agentlab.maintainer_stage_feedback_plan.v1"
                && p["candidateSha256"] == candidate_sha
                && p["qualified"] == false
                && p["automaticPromotion"] == false,
            "stage prior feedback binding differs",
        )?;
        unchanged = p["taskSha256"] == task_sha;
    }
    Ok(
        json!({"schema":"agentlab.maintainer_stage_feedback_plan.v1","candidateId":candidate["id"],"candidateSha256":candidate_sha,
        "sourceRevision":candidate["sourceRevision"],"sourceSetSha256":candidate["sourceSetSha256"],"knowledgeCutSha256":candidate["knowledgeCutSha256"],
        "contractSha256":digest(contract_bytes),"calibrationSha256":expected_sha,"taskSha256":task_sha,"nextAction":decision,
        "semanticSeamCalibrationPassed":calibrated,"acceptedControlPassed":accepted,"killedSemanticVariantCount":killed,
        "pendingFormalActions":downstream["actions"],"schedulingAllowed":!unchanged,"status":if unchanged {"awaiting-new-evidence"} else {"domain-feedback-selected-next-action"},
        "qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,"agentExecutionPerformed":false,
        "verificationBoundary":"recorded raw-observation reconstruction; no producer authentication, execution replay, admission or Harmony runtime qualification"}),
    )
}
