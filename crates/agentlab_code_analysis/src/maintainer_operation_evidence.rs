//! Independent receipt-content checks, not an execution or authenticity oracle.
use crate::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    fs,
    path::{Component, Path},
};

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
