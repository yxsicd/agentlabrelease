//! Repository-independent routing after shadow construction assessment.
//! This consumes the independently validated readiness receipt; it does not
//! execute commands, authenticate producers, freeze cases or promote knowledge.
use crate::digest;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// Keep historical parents inspectable, but never spend a new turn refreshing
/// them when an exact digest-bound successor already exists.
pub fn batch(candidates_bytes: &[u8], plans_bytes: &[u8]) -> Result<Value, String> {
    let mut candidates = BTreeMap::new();
    for line in std::str::from_utf8(candidates_bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|l| !l.trim().is_empty())
    {
        let row: Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        let id = text(&row, "id")?.to_owned();
        require(
            candidates.insert(id, row).is_none(),
            "downstream candidate duplicated",
        )?;
    }
    let mut parents = BTreeSet::new();
    for row in candidates.values() {
        if let Some(id) = row["lineage"]["parentCandidateId"].as_str() {
            let parent = candidates.get(id).ok_or("downstream parent absent")?;
            require(
                row["lineage"]["parentCandidateSha256"]
                    == digest(&serde_json::to_vec(parent).map_err(|e| e.to_string())?),
                "downstream parent digest differs",
            )?;
            let mut seen = BTreeSet::new();
            let mut cursor = row;
            while let Some(id) = cursor["lineage"]["parentCandidateId"].as_str() {
                require(seen.insert(id), "downstream lineage cycle")?;
                cursor = candidates.get(id).ok_or("downstream ancestor absent")?;
            }
            parents.insert(id.to_owned());
        }
    }
    let plans: Vec<Value> = serde_json::from_slice(plans_bytes).map_err(|e| e.to_string())?;
    let mut planned = BTreeSet::new();
    let mut active = Vec::new();
    let mut counts = BTreeMap::<String, usize>::new();
    for p in &plans {
        let id = text(p, "candidateId")?;
        require(planned.insert(id.to_owned()), "downstream plan duplicated")?;
        let c = candidates
            .get(id)
            .ok_or("downstream planned candidate absent")?;
        require(
            p["schema"] == "agentlab.maintainer_downstream_plan.v1"
                && p["candidateSha256"]
                    == digest(&serde_json::to_vec(c).map_err(|e| e.to_string())?)
                && p["automaticPromotion"] == false,
            "downstream batch plan identity differs",
        )?;
        if !parents.contains(id) && p["schedulingAllowed"] == true {
            active.push(id.to_owned());
            for action in p["actions"]
                .as_array()
                .ok_or("downstream batch actions missing")?
            {
                *counts.entry(text(action, "kind")?.to_owned()).or_default() += 1;
            }
        }
    }
    Ok(
        json!({"schema":"agentlab.maintainer_downstream_batch.v1","planCount":plans.len(),
        "activeCandidateIds":active,"retainedHistoricalCandidateIds":parents,
        "schedulingAllowedPlanCount":active.len(),
        "missingConstructionPlanCandidateIds":candidates.keys().filter(|id| !planned.contains(*id)).collect::<Vec<_>>(),
        "actionCounts":counts.into_iter().map(|(kind,count)|json!({"kind":kind,"count":count})).collect::<Vec<_>>(),
        "agentExecutionPerformed":false,"authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("downstream {key} missing"))
}
fn sha(v: &Value, key: &str) -> Result<(), String> {
    let s = text(v, key)?;
    require(
        s.len() == 64
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "downstream digest invalid",
    )
}
fn status(v: &Value) -> Result<bool, String> {
    match text(v, "status")? {
        "qualified" => {
            require(
                v["evidence"].as_array().is_some_and(|a| !a.is_empty()),
                "downstream qualification evidence missing",
            )?;
            Ok(true)
        }
        "unqualified" => {
            require(
                v["evidence"].is_array(),
                "downstream evidence array missing",
            )?;
            Ok(false)
        }
        _ => Err("downstream qualification status unknown".into()),
    }
}

/// An unchanged input must not spend another Agent turn on the same task.
/// A new receipt is evidence of changed input, not evidence of successful work.
pub fn plan(readiness_bytes: &[u8], previous_bytes: Option<&[u8]>) -> Result<Value, String> {
    let r: Value = serde_json::from_slice(readiness_bytes).map_err(|e| e.to_string())?;
    require(
        r["schema"] == "agentlab.shadow_case_construction_readiness_receipt.v1"
            && r["automaticPromotion"] == false,
        "downstream readiness schema or promotion differs",
    )?;
    let candidate = text(&r, "candidateId")?;
    let revision = text(&r, "sourceRevision")?;
    require(
        revision.len() == 40
            && revision
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "downstream source revision invalid",
    )?;
    for key in [
        "candidateSha256",
        "sourceSetSha256",
        "knowledgeCutSha256",
        "currentKnowledgeCutSha256",
        "planSha256",
    ] {
        sha(&r, key)?;
    }
    let knowledge = r["knowledgeBlockers"]
        .as_array()
        .ok_or("downstream knowledge blockers missing")?;
    let qualification = r["qualificationBlockers"]
        .as_array()
        .ok_or("downstream qualification blockers missing")?;
    require(
        knowledge
            .iter()
            .chain(qualification)
            .all(|s| s.as_str().is_some_and(|s| !s.is_empty())),
        "downstream blockers invalid",
    )?;
    let checks = &r["checks"];
    let oracle = status(&checks["oracleExecution"])?;
    let variants = &checks["wrongVariantCalibration"];
    let calibrated = status(variants)?;
    let required = variants["requiredCount"]
        .as_u64()
        .filter(|n| *n >= 2)
        .ok_or("downstream required variants invalid")?;
    let executed = variants["executedCount"]
        .as_u64()
        .ok_or("downstream executed variants invalid")?;
    require(
        !calibrated || executed >= required,
        "downstream calibration below required count",
    )?;
    let runtime = checks["runtimeRequirements"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or("downstream runtime requirements missing")?;
    let mut ids = BTreeSet::new();
    let mut missing_runtime = Vec::new();
    for requirement in runtime {
        let id = text(requirement, "id")?;
        require(ids.insert(id), "downstream runtime requirement duplicated")?;
        if !status(requirement)? {
            missing_runtime.push(requirement);
        }
    }
    let blocked = !oracle || !calibrated || !missing_runtime.is_empty();
    let expected = if !knowledge.is_empty() {
        "blocked-knowledge-refresh"
    } else if blocked {
        "blocked-qualification"
    } else {
        "ready-for-construction"
    };
    require(
        r["decision"] == expected,
        "downstream readiness decision contradicts checks",
    )?;
    require(
        blocked == !qualification.is_empty(),
        "downstream qualification blockers contradict checks",
    )?;
    let mut actions = Vec::new();
    let mut add = |kind: &str, requirement: Value, depends: Vec<String>| {
        let seed =
            json!({"candidateSha256":r["candidateSha256"],"kind":kind,"requirement":requirement});
        let id = format!(
            "downstream-{}",
            &digest(&serde_json::to_vec(&seed).unwrap())[..24]
        );
        actions.push(
            json!({"id":id,"kind":kind,"requirement":requirement,"dependsOn":depends,
            "readyForScheduling":depends.is_empty(),"executionAuthorized":false}),
        );
        id
    };
    if !knowledge.is_empty() {
        add(
            "focused-knowledge-refresh",
            json!({"blockers":knowledge}),
            vec![],
        );
    } else if blocked {
        let oracle_action = if !oracle {
            Some(add(
                "implement-and-calibrate-oracle",
                json!({"acceptedReferenceRequired":true,"independentBehaviorChecksRequired":true}),
                vec![],
            ))
        } else {
            None
        };
        if !calibrated {
            add(
                "calibrate-wrong-variants",
                json!({"requiredCount":required,"observedCount":executed}),
                oracle_action.into_iter().collect(),
            );
        }
        for requirement in missing_runtime {
            // The exact requirement text is retained; API/hardware substitutions
            // are never inferred from a generic runner being available.
            add(
                "qualify-exact-runtime-requirement",
                json!({"id":requirement["id"],"description":requirement["description"]}),
                vec![],
            );
        }
    } else {
        // Construction readiness is not frozen operational dispatch authority.
        add(
            "construct-and-freeze-operational-case",
            json!({"nextGate":r["nextGate"]}),
            vec![],
        );
    }
    let readiness_sha = digest(readiness_bytes);
    // Unrelated cut advancement or JSON formatting is not new evidence for
    // this candidate. Bind only the owned, independently assessed gate state.
    let gate_state_sha = digest(
        &serde_json::to_vec(&json!({
            "candidateSha256":r["candidateSha256"],"sourceRevision":r["sourceRevision"],
            "sourceSetSha256":r["sourceSetSha256"],"constructionPlanSha256":r["planSha256"],
            "knowledgeBlockers":knowledge,"qualificationBlockers":qualification,"checks":checks,
            "actions":actions
        }))
        .map_err(|e| e.to_string())?,
    );
    let mut unchanged = false;
    if let Some(bytes) = previous_bytes {
        let previous: Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
        require(
            previous["schema"] == "agentlab.maintainer_downstream_plan.v1"
                && previous["automaticPromotion"] == false
                && previous["authorityWritePerformed"] == false,
            "downstream previous plan invalid",
        )?;
        require(
            previous["candidateId"] == candidate
                && previous["candidateSha256"] == r["candidateSha256"],
            "downstream previous candidate differs",
        )?;
        sha(&previous, "readinessSha256")?;
        sha(&previous, "gateStateSha256")?;
        unchanged = previous["gateStateSha256"] == gate_state_sha;
        if unchanged {
            require(
                previous["actions"] == Value::Array(actions.clone()),
                "downstream unchanged plan actions differ",
            )?;
        }
    }
    let ready_count = actions
        .iter()
        .filter(|a| a["readyForScheduling"] == true)
        .count();
    Ok(
        json!({"schema":"agentlab.maintainer_downstream_plan.v1","candidateId":candidate,
        "candidateSha256":r["candidateSha256"],"sourceRevision":revision,
        "sourceSetSha256":r["sourceSetSha256"],"knowledgeCutSha256":r["knowledgeCutSha256"],
        "currentKnowledgeCutSha256":r["currentKnowledgeCutSha256"],"constructionPlanSha256":r["planSha256"],
        "readinessSha256":readiness_sha,"gateStateSha256":gate_state_sha,"previousPlanSha256":previous_bytes.map(digest),
        "status":if unchanged {"awaiting-new-evidence"} else {"next-actions-planned"},
        "schedulingAllowed":!unchanged,"readyActionCount":ready_count,"actions":actions,
        "automaticPromotion":false,"authorityWritePerformed":false,"agentExecutionPerformed":false,
        "verificationBoundary":"validated readiness consumer only; no producer authentication, execution, case freeze or qualification"}),
    )
}
