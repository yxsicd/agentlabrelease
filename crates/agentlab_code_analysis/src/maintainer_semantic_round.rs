//! Scope-exact semantic gain gate for the existing construction Agent loop.
use crate::digest;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn sha(value: &Value) -> bool {
    value
        .as_str()
        .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
}
fn rows(report: &Value) -> Result<BTreeMap<String, Value>, String> {
    let mut result = BTreeMap::new();
    for row in report["skills"]
        .as_array()
        .ok_or("semantic scope rows missing")?
    {
        let id = row["skillId"]
            .as_str()
            .filter(|id| !id.is_empty())
            .ok_or("semantic scope id missing")?;
        require(
            result.insert(id.to_owned(), row.clone()).is_none(),
            "semantic scope id duplicated",
        )?;
    }
    for (key, check) in [
        ("structuralReadyCount", "structuralReady"),
        ("programBoundCount", "programEvidenceBound"),
        ("semanticReadyCount", "semanticReady"),
        ("maintenanceReadyCount", "maintenanceReady"),
    ] {
        require(
            result.values().all(|row| row["checks"][check].is_boolean()),
            "semantic scope check missing",
        )?;
        require(
            report["totals"][key].as_u64()
                == Some(
                    result
                        .values()
                        .filter(|row| row["checks"][check] == true)
                        .count() as u64,
                ),
            "semantic totals differ from scope rows",
        )?;
    }
    require(
        report["totals"]["scopeSkillCount"].as_u64() == Some(result.len() as u64),
        "semantic scope total differs",
    )?;
    Ok(result)
}

pub fn compare(
    before_bytes: &[u8],
    after_bytes: &[u8],
    selected: &[String],
) -> Result<Value, String> {
    let before: Value = serde_json::from_slice(before_bytes).map_err(|e| e.to_string())?;
    let after: Value = serde_json::from_slice(after_bytes).map_err(|e| e.to_string())?;
    let ids = selected.iter().collect::<BTreeSet<_>>();
    require(
        !ids.is_empty() && ids.len() <= 4 && ids.len() == selected.len(),
        "select one to four unique semantic scopes",
    )?;
    for report in [&before, &after] {
        require(
            report["schema"] == "agentlab.maintainer_skill_assessment.v1"
                && report["automaticPromotion"] == false,
            "semantic assessment contract invalid",
        )?;
        require(
            report["roundIndex"].as_u64().is_some_and(|n| n > 0)
                && sha(&report["inputs"]["scopeSkillsSha256"])
                && sha(&report["inputs"]["programFactsSha256"]),
            "semantic assessment input identity missing",
        )?;
    }
    require(
        before["standard"] == after["standard"],
        "semantic assessment policy changed",
    )?;
    let policy = before["standard"]["operationEvidencePolicy"]
        .as_str()
        .ok_or("semantic operation policy missing")?;
    require(
        matches!(policy, "verified-receipt-content" | "legacy-explicit-claim"),
        "semantic operation policy unsupported",
    )?;
    require(
        after["parentAssessmentSha256"].as_str() == Some(digest(before_bytes).as_str()),
        "semantic parent digest mismatch",
    )?;
    require(
        before["roundIndex"].as_u64().and_then(|n| n.checked_add(1))
            == after["roundIndex"].as_u64(),
        "semantic round is not contiguous",
    )?;
    require(
        before["inputs"]["scopeSkillsSha256"] == after["inputs"]["scopeSkillsSha256"],
        "semantic round changed scope catalog",
    )?;
    let old = rows(&before)?;
    let new = rows(&after)?;
    require(
        old.keys().eq(new.keys()) && ids.iter().all(|id| old.contains_key(id.as_str())),
        "semantic scope cut differs or selected scope missing",
    )?;
    let mut advanced = Vec::new();
    let mut batch_identity = None;
    for (id, original) in &old {
        let updated = &new[id];
        if !ids.contains(id) {
            require(
                original == updated,
                "semantic round changed an unselected scope",
            )?;
            continue;
        }
        let identity = (
            original["repositoryId"].clone(),
            original["sourceRevision"].clone(),
        );
        require(
            identity.0.as_str().is_some_and(|s| !s.is_empty())
                && identity
                    .1
                    .as_str()
                    .is_some_and(|s| s.len() == 40 && s.bytes().all(|b| b.is_ascii_hexdigit())),
            "semantic source identity invalid",
        )?;
        if let Some(expected) = &batch_identity {
            require(
                &identity == expected,
                "semantic batch mixed source identities",
            )?;
        }
        batch_identity = Some(identity);
        for key in [
            "repositoryId",
            "sourceRevision",
            "capabilities",
            "requiredSemanticDimensions",
            "operationEvidenceChecks",
        ] {
            require(
                original[key] == updated[key],
                "semantic round changed identity or operation evidence",
            )?;
        }
        for key in ["identityReady", "structuralReady"] {
            require(
                original["checks"][key] == true && updated["checks"][key] == true,
                "semantic structural prerequisite missing",
            )?;
        }
        if original == updated {
            continue;
        }
        require(
            original["maturity"] == "L1-structural-ready"
                && original["checks"]["semanticReady"] == false
                && original["checks"]["maintenanceReady"] == false
                && updated["checks"]["semanticReady"] == true
                && updated["checks"]["programEvidenceBound"] == true
                && matches!(
                    updated["maturity"].as_str(),
                    Some("L2-semantic-ready" | "L3-maintenance-ready")
                ),
            "semantic selected scope did not close L1 to L2 prerequisites",
        )?;
        let dimensions = |row: &Value| -> BTreeSet<String> {
            row["provenDimensions"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect()
        };
        let prior_dimensions = dimensions(original);
        let next_dimensions = dimensions(updated);
        let required = updated["requiredSemanticDimensions"]
            .as_array()
            .filter(|rows| !rows.is_empty())
            .ok_or("semantic required dimensions missing")?;
        require(
            required.iter().all(|dim| {
                dim.as_str()
                    .is_some_and(|dim| next_dimensions.contains(dim))
            }),
            "semantic selected scope lacks a required dimension",
        )?;
        require(
            prior_dimensions.is_subset(&next_dimensions),
            "semantic round removed a proven dimension",
        )?;
        require(
            prior_dimensions.contains("operation") == next_dimensions.contains("operation"),
            "semantic round introduced operation evidence",
        )?;
        require(
            updated["checks"]["maintenanceReady"] == json!(next_dimensions.contains("operation")),
            "semantic maintenance verdict inconsistent",
        )?;
        require(
            updated["maturity"]
                == if next_dimensions.contains("operation") {
                    "L3-maintenance-ready"
                } else {
                    "L2-semantic-ready"
                },
            "semantic maturity label differs from evidence",
        )?;
        advanced.push(id.clone());
    }
    let semantic_delta = after["totals"]["semanticReadyCount"]
        .as_u64()
        .unwrap()
        .checked_sub(before["totals"]["semanticReadyCount"].as_u64().unwrap())
        .ok_or("semantic readiness regressed")?;
    let maintenance_delta = after["totals"]["maintenanceReadyCount"]
        .as_u64()
        .unwrap()
        .checked_sub(before["totals"]["maintenanceReadyCount"].as_u64().unwrap())
        .ok_or("semantic operation readiness regressed")?;
    let bound_delta = after["totals"]["programBoundCount"]
        .as_u64()
        .unwrap()
        .checked_sub(before["totals"]["programBoundCount"].as_u64().unwrap())
        .ok_or("semantic binding regressed")?;
    require(
        semantic_delta == advanced.len() as u64
            && maintenance_delta <= semantic_delta
            && bound_delta <= semantic_delta,
        "semantic aggregate delta differs from selected scope gains",
    )?;
    require(
        before["totals"]["structuralReadyCount"] == after["totals"]["structuralReadyCount"],
        "semantic structural total changed",
    )?;
    if advanced.is_empty() {
        require(
            before["inputs"]["programFactsSha256"] == after["inputs"]["programFactsSha256"],
            "semantic no-change changed fact cut",
        )?;
    } else {
        require(advanced.len() == ids.len(), "semantic batch is partial")?;
        require(
            before["inputs"]["programFactsSha256"] != after["inputs"]["programFactsSha256"],
            "semantic gain has unchanged fact cut",
        )?;
    }
    Ok(
        json!({"schema":"agentlab.maintainer_skill_agent_flywheel_result.v1","automaticPromotion":false,
        "authorityWritePerformed":false,"decision":if advanced.is_empty(){"no-change"}else{"review-proposed-knowledge"},
        "before":before["totals"],"after":after["totals"],"batchScopeCount":ids.len(),
        "selectedScopeIds":selected,"advancedScopeIds":advanced,"semanticReadyDelta":semantic_delta,
        "maintenanceReadyDelta":maintenance_delta,"operationEvidencePolicy":policy,
        "strictOperationEvidencePolicy":policy=="verified-receipt-content",
        "beforeAssessmentSha256":digest(before_bytes),"assessmentSha256":digest(after_bytes),
        "nextRoundObjectives":after["nextRoundObjectives"]}),
    )
}
