//! Reconcile declarations with a byte-bound prior source-operation contract.
//! Does not infer intended failures from a new run or authenticate a producer.
use crate::{digest, maintainer_source_operation};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}

pub fn reconcile(
    profile_bytes: &[u8],
    reference_bytes: &[u8],
    source_bytes: &[u8],
) -> Result<Value, String> {
    need(
        profile_bytes.len() <= 256 * 1024
            && reference_bytes.len() <= 4 * 1024 * 1024
            && source_bytes.len() <= 256 * 1024,
        "control declaration input budget",
    )?;
    let profile: Value = serde_json::from_slice(profile_bytes).map_err(|e| e.to_string())?;
    let reference: Value = serde_json::from_slice(reference_bytes).map_err(|e| e.to_string())?;
    let scope: Value = serde_json::from_str(
        reference["scopeOriginal"]
            .as_str()
            .ok_or("control reference scope")?,
    )
    .map_err(|e| e.to_string())?;
    let reconstructed = maintainer_source_operation::recorded(&reference, &scope)?;
    let recipe = &reference["recipe"];
    need(
        profile["schema"] == "agentlab.reviewed_behavior_profile.v1"
            && profile["reviewed"] == true
            && profile["automaticPromotion"] == false
            && profile["repository"] == recipe["source"]["repository"]
            && profile["sourceRevision"] == recipe["source"]["revision"],
        "control declaration profile/source differs",
    )?;
    let path = profile["originalSourcePath"]
        .as_str()
        .ok_or("control declaration original path")?;
    let source_sha = digest(source_bytes);
    for inventory in [&profile["sources"], &recipe["sourceInputs"]] {
        let rows = inventory
            .as_array()
            .ok_or("control declaration source inventory")?;
        let found = rows
            .iter()
            .filter(|r| r["path"] == path)
            .collect::<Vec<_>>();
        need(
            found.len() == 1 && found[0]["sha256"] == source_sha,
            "control declaration original source binding",
        )?;
    }
    let source = std::str::from_utf8(source_bytes).map_err(|e| e.to_string())?;
    let checks = profile["checks"]
        .as_array()
        .ok_or("control declaration checks")?;
    let prior_checks = recipe["checks"].as_array().unwrap();
    need(
        checks.len() == prior_checks.len(),
        "control declaration check inventory differs",
    )?;
    let mut seen = BTreeSet::new();
    for check in checks {
        let id = check["id"].as_str().ok_or("control declaration check id")?;
        let found = prior_checks
            .iter()
            .filter(|c| c["id"] == id)
            .collect::<Vec<_>>();
        need(
            seen.insert(id)
                && found.len() == 1
                && check.get("input").is_some()
                && check.get("expected").is_some()
                && check["expected"] == found[0]["expected"],
            "control declaration predicates differ",
        )?;
    }
    let controls = profile["controls"]
        .as_array()
        .ok_or("control declaration controls")?;
    let prior = recipe["controls"].as_array().unwrap();
    need(
        controls.len() == prior.len(),
        "control declaration control inventory differs",
    )?;
    let mut declared = BTreeMap::new();
    for (control, stream) in prior.iter().zip(reference["streams"].as_array().unwrap()) {
        let raw: Value =
            serde_json::from_str(stream["stdout"].as_str().unwrap()).map_err(|e| e.to_string())?;
        need(
            raw["id"] == control["id"] && raw["sourceSha256"] == source_sha,
            "control declaration recorded source identity",
        )?;
        declared.insert(control["id"].as_str().unwrap(), (control, raw));
    }
    let mut successor = profile.clone();
    successor["reviewed"] = json!(false);
    let mut corrections = Vec::new();
    let mut seen = BTreeSet::new();
    for (index, control) in controls.iter().enumerate() {
        let id = control["id"]
            .as_str()
            .ok_or("control declaration control id")?;
        need(seen.insert(id), "control declaration duplicate control")?;
        let (previous, raw) = declared
            .get(id)
            .ok_or("control declaration missing reference control")?;
        let role = if previous["role"] == "reference" {
            json!("accepted")
        } else {
            previous["role"].clone()
        };
        need(
            control["role"] == role,
            "control declaration control role differs",
        )?;
        let edits = control["edits"]
            .as_array()
            .filter(|a| a.len() <= 16)
            .ok_or("control declaration edits")?;
        let mut variant = source.to_owned();
        for edit in edits {
            let from = edit["from"]
                .as_str()
                .filter(|s| !s.is_empty())
                .ok_or("control declaration edit from")?;
            let to = edit["to"].as_str().ok_or("control declaration edit to")?;
            need(
                from != to && variant.matches(from).count() == 1,
                "control declaration edit ambiguous",
            )?;
            variant = variant.replacen(from, to, 1);
            need(
                variant.len() <= 256 * 1024,
                "control declaration variant budget",
            )?;
        }
        need(
            raw["submittedSourceSha256"] == digest(variant.as_bytes()),
            "control declaration variant source differs",
        )?;
        let current = control["expectedFailedCheckIds"]
            .as_array()
            .ok_or("control declaration failure list")?;
        let current_set = current
            .iter()
            .map(|v| v.as_str().ok_or("control declaration failure id"))
            .collect::<Result<BTreeSet<_>, _>>()?;
        need(
            current_set.len() == current.len()
                && current_set.iter().all(|id| seen_check(checks, id)),
            "control declaration invalid failure id",
        )?;
        let previous_set = previous["expectedFailedCheckIds"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect::<BTreeSet<_>>();
        if current_set != previous_set {
            corrections.push(json!({"id":id,"previousDeclaration":control["expectedFailedCheckIds"],
                "priorSourceContractDeclaration":previous["expectedFailedCheckIds"],"submittedSourceSha256":raw["submittedSourceSha256"]}));
        }
        successor["controls"][index]["expectedFailedCheckIds"] =
            previous["expectedFailedCheckIds"].clone();
    }
    Ok(
        json!({"schema":"agentlab.control_declaration_reconciliation.v1","parentProfileSha256":digest(profile_bytes),
        "referenceSha256":digest(reference_bytes),"originalSourceSha256":source_sha,
        "corrections":corrections,"proposedProfile":successor,"referenceReadback":reconstructed,
        "reviewRequired":true,"qualified":false,"producerAuthenticated":false,"executionPerformed":false,
        "automaticPromotion":false,"authorityWritePerformed":false,
        "verificationBoundary":"Preserved prior declared failures, check values and exact variant bytes; input semantics, intent, commit ancestry and producer authenticity require separate review."}),
    )
}
fn seen_check(checks: &[Value], id: &str) -> bool {
    checks.iter().any(|c| c["id"] == id)
}
