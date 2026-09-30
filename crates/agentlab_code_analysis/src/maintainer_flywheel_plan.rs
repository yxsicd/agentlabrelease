//! Gap-driven scheduling proposals, never execution or authority promotion.
use crate::{digest, maintainer_skill_flywheel::assess_with_receipts};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

const LANES: [&str; 4] = [
    "inventory-repair",
    "scope-decomposition",
    "semantic-refresh",
    "operation-verification",
];

#[allow(clippy::too_many_arguments)]
pub fn plan(
    scopes: &Path,
    facts: Option<&Path>,
    receipts: &Path,
    round: u64,
    parent: Option<&str>,
    available: &[String],
    batch_size: usize,
    max_source_files: u64,
) -> Result<Value, String> {
    if !(1..=4).contains(&batch_size) || max_source_files == 0 {
        return Err("plan requires batch size 1..4 and positive source budget".into());
    }
    let lanes = available
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if lanes.len() != available.len() || lanes.iter().any(|lane| !LANES.contains(lane)) {
        return Err("plan lane duplicated or unsupported".into());
    }
    // Never accept a caller-written ready report or legacy operation claims.
    let assessment = assess_with_receipts(scopes, facts, round, parent, Some(receipts))?;
    let catalog_bytes = fs::read(scopes).map_err(|e| e.to_string())?;
    if assessment["inputs"]["scopeSkillsSha256"].as_str() != Some(digest(&catalog_bytes).as_str()) {
        return Err("plan scope cut changed during assessment".into());
    }
    if let Some(facts) = facts {
        let bytes = fs::read(facts).map_err(|e| e.to_string())?;
        if assessment["inputs"]["programFactsSha256"].as_str() != Some(digest(&bytes).as_str()) {
            return Err("plan fact cut changed during assessment".into());
        }
    }
    let catalog = std::str::from_utf8(&catalog_bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str::<Value>(line).map_err(|e| e.to_string()))
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|row| (row["id"].as_str().unwrap().to_owned(), row))
        .collect::<BTreeMap<_, _>>();
    let mut items = Vec::new();
    for state in assessment["skills"]
        .as_array()
        .ok_or("assessment skills missing")?
    {
        let id = state["skillId"]
            .as_str()
            .ok_or("assessment skill id missing")?;
        let scope = &catalog[id];
        let (lane, priority, reason) = if state["checks"]["structuralReady"] != true {
            (
                Some("inventory-repair"),
                0,
                "structural-evidence-incomplete",
            )
        } else if state["checks"]["semanticReady"] != true {
            if scope["sourceFileCount"].as_u64().is_none() {
                (Some("inventory-repair"), 0, "source-count-invalid")
            } else if scope["sourceFileCount"].as_u64().unwrap() > max_source_files {
                (
                    Some("scope-decomposition"),
                    1,
                    "scope-exceeds-analysis-budget",
                )
            } else {
                (Some("semantic-refresh"), 2, "semantic-evidence-incomplete")
            }
        } else if state["checks"]["maintenanceReady"] != true {
            (
                Some("operation-verification"),
                3,
                "operation-evidence-incomplete-or-unverified",
            )
        } else {
            (None, 4, "knowledge-ready-not-closed-loop")
        };
        let eligible = lane.is_some_and(|lane| lanes.contains(lane));
        let disposition = if lane.is_none() {
            "knowledge-ready"
        } else if eligible {
            "eligible"
        } else {
            "capability-blocked"
        };
        let source = scope["sourceFileCount"].as_u64().unwrap_or(0);
        let mode = if scope["pathBoundary"] == "." {
            "repository-contract"
        } else if source == 0 {
            "configuration-asset"
        } else {
            "source-behavior"
        };
        items.push(json!({"skillId":id,"repositoryId":scope["repositoryId"],
            "repository":scope["repository"],"sourceRevision":scope["sourceRevision"],
            "pathBoundary":scope["pathBoundary"],"ownershipSelectors":scope["ownershipSelectors"],
            "maturity":state["maturity"],"analysisMode":mode,
            "nextLane":lane,"priority":priority,"reason":reason,
            "disposition":disposition,"selected":false,"gaps":state["gaps"],
            "capabilityGap":if disposition == "capability-blocked" {lane} else {None}}));
    }
    items.sort_by_key(|item| {
        (
            item["priority"].as_u64().unwrap(),
            item["repositoryId"].as_str().unwrap().to_owned(),
            item["sourceRevision"].as_str().unwrap_or("").to_owned(),
            item["skillId"].as_str().unwrap().to_owned(),
        )
    });
    let first = items
        .iter()
        .find(|row| row["disposition"] == "eligible")
        .cloned();
    let mut selected = Vec::new();
    if let Some(first) = &first {
        for item in &mut items {
            // No cross-repository/source/lane batch, or root+child projection.
            if selected.len() < batch_size
                && item["disposition"] == "eligible"
                && item["repositoryId"] == first["repositoryId"]
                && item["repository"] == first["repository"]
                && item["sourceRevision"] == first["sourceRevision"]
                && item["nextLane"] == first["nextLane"]
                && item["analysisMode"] == first["analysisMode"]
            {
                item["selected"] = json!(true);
                selected.push(item["skillId"].clone());
            }
        }
    }
    let count = |status: &str| {
        items
            .iter()
            .filter(|row| row["disposition"] == status)
            .count()
    };
    let decision = if !selected.is_empty() {
        "propose-next-batch"
    } else if count("capability-blocked") > 0 {
        "capability-blocked"
    } else {
        "downstream-validation-required"
    };
    Ok(json!({"schema":"agentlab.maintainer_flywheel_next_plan.v1",
        "assessment":assessment,"assessmentValueSha256":digest(&serde_json::to_vec(&assessment).map_err(|e|e.to_string())?),
        "policy":{"batchSize":batch_size,"maxSourceFiles":max_source_files,
            "availableLanes":lanes,"operationEvidencePolicy":"verified-receipt-content"},
        "summary":{"scopeCount":items.len(),"eligible":count("eligible"),
            "capabilityBlocked":count("capability-blocked"),"knowledgeReady":count("knowledge-ready"),
            "selected":selected.len()},
        "decision":decision,"selectedScopeIds":selected,"nextLane":first.map(|row|row["nextLane"].clone()),
        "scopes":items,"closedLoopQualified":false,"automaticPromotion":false,
        "authorityWritePerformed":false,
        "downstreamRequirements":["calibrated-case-generation","case-execution",
            "evidence-feedback-into-next-cut","cross-repository-transfer"]}))
}
