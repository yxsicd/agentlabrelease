//! Independent receipt-content checks, not an execution or authenticity oracle.
use crate::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path},
};

/// Check a pure operation round. No source execution, case promotion or writes.
pub fn compare_round(
    before_bytes: &[u8],
    after_bytes: &[u8],
    selected: &[String],
) -> Result<Value, String> {
    let before: Value = serde_json::from_slice(before_bytes).map_err(|e| e.to_string())?;
    let after: Value = serde_json::from_slice(after_bytes).map_err(|e| e.to_string())?;
    let ids = selected.iter().collect::<BTreeSet<_>>();
    require(
        !ids.is_empty() && ids.len() <= 4 && ids.len() == selected.len(),
        "select one to four unique operation scopes",
    )?;
    for report in [&before, &after] {
        require(
            report["schema"] == "agentlab.maintainer_skill_assessment.v1"
                && report["automaticPromotion"] == false,
            "operation round assessment contract invalid",
        )?;
        require(
            report["standard"]["operationEvidencePolicy"] == "verified-receipt-content",
            "operation round requires strict same-policy assessments",
        )?;
        require(
            positive(&report["roundIndex"])
                && sha(&report["inputs"]["scopeSkillsSha256"])
                && sha(&report["inputs"]["programFactsSha256"]),
            "operation round input identity missing",
        )?;
    }
    require(
        after["parentAssessmentSha256"].as_str() == Some(digest(before_bytes).as_str()),
        "operation round parent digest mismatch",
    )?;
    require(
        before["roundIndex"].as_u64().and_then(|n| n.checked_add(1))
            == after["roundIndex"].as_u64(),
        "operation round is not contiguous",
    )?;
    require(
        before["inputs"]["scopeSkillsSha256"] == after["inputs"]["scopeSkillsSha256"],
        "operation round changed scope catalog",
    )?;
    for key in [
        "scopeSkillCount",
        "structuralReadyCount",
        "programBoundCount",
        "semanticReadyCount",
    ] {
        require(
            before["totals"][key].as_u64().is_some()
                && before["totals"][key] == after["totals"][key],
            "operation round changed non-operation totals",
        )?;
    }
    let index = |report: &Value| -> Result<BTreeMap<String, Value>, String> {
        let rows = report["skills"]
            .as_array()
            .ok_or("operation round scope rows missing")?;
        let mut result = BTreeMap::new();
        for row in rows {
            let id = row["skillId"]
                .as_str()
                .ok_or("operation round scope identity missing")?;
            require(
                result.insert(id.to_owned(), row.clone()).is_none(),
                "operation round duplicate scope",
            )?;
        }
        Ok(result)
    };
    let old = index(&before)?;
    let new = index(&after)?;
    require(
        before["totals"]["scopeSkillCount"].as_u64() == Some(old.len() as u64),
        "operation round scope count differs from rows",
    )?;
    require(
        old.keys().eq(new.keys()),
        "operation round changed scope identities",
    )?;
    require(
        ids.iter().all(|id| old.contains_key(id.as_str())),
        "selected operation scope missing",
    )?;
    let mut advanced = Vec::new();
    for (id, original) in &old {
        let updated = &new[id];
        if !ids.contains(id) {
            require(
                original == updated,
                "operation round changed an unselected scope",
            )?;
            continue;
        }
        for key in [
            "repositoryId",
            "sourceRevision",
            "capabilities",
            "requiredSemanticDimensions",
            "rejectedEvidenceBindings",
        ] {
            require(
                original[key] == updated[key],
                "operation round changed selected scope identity or semantic contract",
            )?;
        }
        require(
            original["checks"]["semanticReady"] == true
                && updated["checks"]["semanticReady"] == true,
            "operation scope is not semantic-ready",
        )?;
        for key in [
            "identityReady",
            "structuralReady",
            "programEvidenceBound",
            "semanticReady",
        ] {
            require(
                original["checks"][key] == true && updated["checks"][key] == true,
                "operation round changed prerequisite readiness",
            )?;
        }
        let semantic_bindings = |row: &Value| -> BTreeMap<String, Value> {
            row["evidenceBindings"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|binding| {
                    let dimensions = binding["dimensions"]
                        .as_array()?
                        .iter()
                        .filter(|dim| *dim != "operation")
                        .cloned()
                        .collect::<Vec<_>>();
                    if dimensions.is_empty() {
                        return None;
                    }
                    Some((
                        binding["factId"].as_str()?.to_owned(),
                        json!({"bindingMode":binding["bindingMode"], "dimensions":dimensions}),
                    ))
                })
                .collect()
        };
        require(
            semantic_bindings(original) == semantic_bindings(updated),
            "operation round changed semantic evidence",
        )?;
        if original == updated {
            continue;
        }
        require(
            original["maturity"] == "L2-semantic-ready"
                && updated["maturity"] == "L3-maintenance-ready",
            "operation round requires L2 to L3 transition",
        )?;
        require(
            original["checks"]["maintenanceReady"] == false
                && updated["checks"]["maintenanceReady"] == true,
            "operation round readiness transition invalid",
        )?;
        require(
            updated["operationEvidenceChecks"]
                .as_object()
                .is_some_and(|checks| checks.values().any(|check| check["status"] == "verified")),
            "operation round lacks verified receipt",
        )?;
        advanced.push(id.clone());
    }
    let old_count = before["totals"]["maintenanceReadyCount"]
        .as_u64()
        .ok_or("operation baseline maintenance count missing")?;
    require(
        old_count.checked_add(advanced.len() as u64)
            == after["totals"]["maintenanceReadyCount"].as_u64(),
        "operation round aggregate delta differs",
    )?;
    if advanced.is_empty() {
        require(
            before["inputs"]["programFactsSha256"] == after["inputs"]["programFactsSha256"],
            "no-change round changed fact cut",
        )?;
    } else {
        require(advanced.len() == ids.len(), "operation batch is partial")?;
        require(
            before["inputs"]["programFactsSha256"] != after["inputs"]["programFactsSha256"],
            "operation gain has unchanged fact cut",
        )?;
    }
    Ok(json!({
        "schema":"agentlab.maintainer_operation_round_result.v1", "automaticPromotion":false,
        "decision":if advanced.is_empty() {"no-change"} else {"review-proposed-operation-knowledge"},
        "beforeAssessmentSha256":digest(before_bytes), "afterAssessmentSha256":digest(after_bytes),
        "selectedScopeIds":selected, "advancedScopeIds":advanced, "maintenanceReadyDelta":advanced.len(),
        "nextRoundObjectives":after["nextRoundObjectives"], "authorityWritePerformed":false
    }))
}

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.to_owned())
    }
}
fn text(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.trim().is_empty())
}
fn sha(value: &Value) -> bool {
    value
        .as_str()
        .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
}
fn positive(value: &Value) -> bool {
    value.as_u64().is_some_and(|n| n > 0)
}

pub fn prepare_fact(skill: &Value, reference: Value, root: &Path) -> Result<Value, String> {
    let mut fact = json!({
        "id":format!("operation-build-{}", digest(&serde_json::to_vec(&json!([skill["id"], reference])).map_err(|e| e.to_string())?)),
        "kind":"build-verification", "repositoryId":skill["repositoryId"],
        "sourceRevision":skill["sourceRevision"], "scopeSkillIds":[skill["id"]],
        "dimensions":["operation"], "operationEvidence":reference,
        "evidence":[reference], "automaticPromotion":false
    });
    fact["operationEvidenceCheck"] = verify(&fact, skill, root)?;
    fact["interpretation"] = json!("Receipt-content-qualified module build only; runtime, tests, performance and type checking are not independently qualified.");
    Ok(fact)
}

pub fn verify(fact: &Value, skill: &Value, root: &Path) -> Result<Value, String> {
    let reference = &fact["operationEvidence"];
    let relative = reference["path"]
        .as_str()
        .ok_or("operation receipt reference missing")?;
    require(
        sha(&reference["sha256"]),
        "operation receipt digest missing",
    )?;
    let path = Path::new(relative);
    require(
        !relative.is_empty() && path.components().all(|c| matches!(c, Component::Normal(_))),
        "operation receipt path must be contained and relative",
    )?;
    let mut resolved = root.to_path_buf();
    require(root.is_dir(), "operation receipt root missing")?;
    for component in path.components() {
        resolved.push(component.as_os_str());
        require(
            !fs::symlink_metadata(&resolved)
                .map_err(|e| format!("operation receipt missing: {e}"))?
                .file_type()
                .is_symlink(),
            "operation receipt symlink rejected",
        )?;
    }
    require(
        resolved.is_file(),
        "operation receipt must be a regular file",
    )?;
    require(
        fs::metadata(&resolved).map_err(|e| e.to_string())?.len() <= 2 * 1024 * 1024,
        "operation receipt exceeds size budget",
    )?;
    let bytes = fs::read(resolved).map_err(|e| e.to_string())?;
    require(
        reference["sha256"].as_str() == Some(digest(&bytes).as_str()),
        "operation receipt digest mismatch",
    )?;
    let receipt: Value = serde_json::from_slice(&bytes)
        .map_err(|e| format!("operation receipt JSON invalid: {e}"))?;
    require(
        receipt["schema"] == "agentlab.maintainer_scope_build_qualification.v1",
        "operation receipt adapter unavailable",
    )?;
    require(
        receipt["status"] == "qualified" && receipt["automaticPromotion"] == false,
        "operation receipt is not qualified",
    )?;
    let source = &receipt["source"];
    require(
        text(&skill["id"])
            && text(&skill["repositoryId"])
            && text(&skill["repository"])
            && skill["sourceRevision"]
                .as_str()
                .is_some_and(|s| s.len() == 40 && s.bytes().all(|b| b.is_ascii_hexdigit())),
        "operation scope source identity invalid",
    )?;
    require(
        source["repositoryId"] == skill["repositoryId"]
            && source["revision"] == skill["sourceRevision"]
            && source["repository"] == skill["repository"],
        "operation receipt source identity mismatch",
    )?;
    require(
        source["cleanBefore"] == true && source["cleanAfter"] == true,
        "operation source is not clean",
    )?;
    let scope = &receipt["scope"];
    require(
        scope["scopeSkillIds"] == json!([skill["id"]]) && scope["scopeSpecificBinding"] == true,
        "operation receipt scope mismatch",
    )?;
    require(
        scope["lane"] == "build-only" && text(&scope["module"]) && text(&scope["target"]),
        "operation receipt lane invalid",
    )?;
    let toolchain = &receipt["toolchain"];
    require(
        ["sdkRelease", "hvigorVersion", "ohpmVersion"]
            .iter()
            .all(|key| text(&toolchain[*key])),
        "operation toolchain identity missing",
    )?;
    let deps = &receipt["dependencyPreparation"];
    require(
        deps["status"] == "successful"
            && deps["exitCode"].as_u64() == Some(0)
            && positive(&deps["durationMs"])
            && sha(&deps["lockSha256"]),
        "operation dependencies unqualified",
    )?;
    let build = &receipt["build"];
    require(
        build["status"] == "successful"
            && build["task"] == "assembleHar"
            && build["canonicalContentReproducible"] == true,
        "operation build unqualified",
    )?;
    let command = build["command"]
        .as_array()
        .filter(|rows| !rows.is_empty() && rows.iter().all(text))
        .ok_or("operation build command missing")?;
    let attempts = build["attempts"]
        .as_array()
        .filter(|rows| rows.len() == 2)
        .ok_or("operation requires two clean attempts")?;
    let mut operations = BTreeSet::new();
    let mut raw = BTreeSet::new();
    for attempt in attempts {
        require(
            attempt["cleanBuild"] == true
                && attempt["exitCode"].as_u64() == Some(0)
                && positive(&attempt["durationMs"]),
            "operation attempt failed or partial",
        )?;
        require(
            text(&attempt["artifact"])
                && positive(&attempt["artifactBytes"])
                && positive(&attempt["memberCount"])
                && ["artifactSha256", "canonicalMemberSha256", "buildLogSha256"]
                    .iter()
                    .all(|key| sha(&attempt[*key])),
            "operation artifact evidence incomplete",
        )?;
        let authority = &attempt["executionAuthority"];
        require(
            matches!(
                authority["routeDecision"].as_str(),
                Some("peer_direct" | "upstream_local_peer")
            ) && text(&authority["targetPeerId"])
                && text(&authority["operationId"]),
            "operation execution authority missing",
        )?;
        require(
            operations.insert(authority["operationId"].as_str().unwrap()),
            "operation attempts duplicate execution identity",
        )?;
        raw.insert(attempt["artifactSha256"].as_str().unwrap());
    }
    require(
        attempts[0]["canonicalMemberSha256"] == attempts[1]["canonicalMemberSha256"]
            && attempts[0]["memberCount"] == attempts[1]["memberCount"],
        "operation canonical content mismatch",
    )?;
    require(
        build["rawArchiveReproducible"].as_bool() == Some(raw.len() == 1),
        "operation raw reproducibility claim inconsistent",
    )?;
    let coverage = &receipt["qualificationScope"];
    require(
        coverage["moduleBuild"] == true
            && ["runtime", "tests", "performance"]
                .iter()
                .all(|key| coverage[*key] == false),
        "build-only operation overclaims qualification",
    )?;
    require(
        receipt["limitations"]
            .as_array()
            .is_some_and(|rows| !rows.is_empty() && rows.iter().all(text)),
        "operation limitations missing",
    )?;
    Ok(json!({
        "status":"verified", "receiptPath":relative, "receiptSha256":digest(&bytes),
        "lane":"build-only", "qualificationScope":coverage,
        "typeChecking":if command.iter().any(|arg| arg == "--no-type-check") {"not-qualified"} else {"not-independently-qualified"},
        "limitations":receipt["limitations"],
        "verificationBoundary":"receipt bytes and recorded assertions; no build replay or raw artifact/log readback"
    }))
}
