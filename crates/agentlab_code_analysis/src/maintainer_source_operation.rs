//! Reviewed source-maintenance controls. Never HAR/runtime/Agent qualification.
use crate::{
    digest, maintainer_operation_exec as exec, maintainer_skill_flywheel::assess_with_receipts,
};
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    fs,
    io::Write,
    path::{Component, Path},
    process::Command,
};

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
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("source operation {key} missing"))
}
fn sha(v: &Value, len: usize) -> bool {
    v.as_str()
        .is_some_and(|s| s.len() == len && s.bytes().all(|b| b.is_ascii_hexdigit()))
}
fn relative(p: &str) -> bool {
    !p.is_empty()
        && Path::new(p)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
fn owned(skill: &Value, p: &str) -> bool {
    if !relative(p) {
        return false;
    }
    let prefix = |base: &str| p == base || p.starts_with(&format!("{base}/"));
    if let Some(selectors) = skill["ownershipSelectors"].as_array() {
        selectors.iter().any(|s| match s["type"].as_str() {
            Some("prefix") => s["path"].as_str().is_some_and(prefix),
            Some("files") => s["paths"]
                .as_array()
                .is_some_and(|a| a.iter().any(|v| v == p)),
            _ => false,
        })
    } else {
        skill["pathBoundary"].as_str().is_some_and(prefix)
    }
}
fn read(path: &Path, limit: usize) -> Result<Vec<u8>, String> {
    for p in path.ancestors() {
        need(
            !fs::symlink_metadata(p)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "source operation symlink",
        )?;
    }
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    need(
        meta.is_file() && meta.len() <= limit as u64,
        "source operation file budget",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    need(bytes.len() <= limit, "source operation file grew")?;
    Ok(bytes)
}
fn save(out: &Path, name: &str, bytes: &[u8]) -> Result<(), String> {
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(out.join(name))
        .map_err(|e| e.to_string())?
        .write_all(bytes)
        .map_err(|e| e.to_string())
}
fn recipe_gate(recipe: &Value, skill: &Value) -> Result<(), String> {
    need(
        skill["ownershipSelectors"].is_null()
            || skill["ownershipSelectors"]
                .as_array()
                .is_some_and(|a| !a.is_empty()),
        "source operation ownership contract",
    )?;
    need(
        recipe["schema"] == "agentlab.maintainer_source_operation_recipe.v1"
            && recipe["reviewed"] == true
            && recipe["automaticPromotion"] == false
            && recipe["operationKind"] == "source-only",
        "source operation review/schema/kind",
    )?;
    need(
        recipe["scopeSkillId"] == skill["id"]
            && recipe["source"]["repositoryId"] == skill["repositoryId"]
            && recipe["source"]["repository"] == skill["repository"]
            && recipe["source"]["revision"] == skill["sourceRevision"],
        "source operation source/scope differs",
    )?;
    need(
        skill["sourceFileCount"].as_u64().is_some_and(|n| n > 0)
            && skill["buildEntrypoints"]
                .as_array()
                .is_some_and(|a| a.is_empty())
            && skill["testFileCount"] == 0
            && skill["testEntrypoints"]
                .as_array()
                .is_some_and(|a| a.is_empty()),
        "source operation adapter does not cover build/test capability",
    )?;
    let inputs = recipe["sourceInputs"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 16)
        .ok_or("source operation source inputs")?;
    let mut paths = BTreeSet::new();
    for input in inputs {
        let path = text(input, "path")?;
        need(
            owned(skill, path)
                && paths.insert(path)
                && sha(&input["sha256"], 64)
                && sha(&input["gitBlobOid"], 40),
            "source operation unowned/duplicate/unbound source",
        )?;
    }
    let methods = recipe["methodInputs"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 8)
        .ok_or("source operation method inputs")?;
    let mut method_paths = BTreeSet::new();
    for method in methods {
        let path = text(method, "path")?;
        need(
            Path::new(path).is_absolute()
                && method_paths.insert(path)
                && sha(&method["sha256"], 64),
            "source operation method binding",
        )?;
    }
    let checks = recipe["checks"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 64)
        .ok_or("source operation checks")?;
    let mut ids = BTreeSet::new();
    for check in checks {
        need(
            ids.insert(text(check, "id")?)
                && text(check, "pointer")?.starts_with('/')
                && check.get("expected").is_some(),
            "source operation duplicate/unbound check",
        )?;
    }
    let controls = recipe["controls"]
        .as_array()
        .filter(|a| (3..=8).contains(&a.len()))
        .ok_or("source operation controls")?;
    let mut names = BTreeSet::new();
    let mut baseline = 0;
    let mut reference = 0;
    let mut wrong = 0;
    let mut budget = 0u64;
    for control in controls {
        let id = text(control, "id")?;
        need(
            id.len() <= 64
                && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
                && names.insert(id),
            "source operation control id",
        )?;
        let failures = control["expectedFailedCheckIds"]
            .as_array()
            .ok_or("source operation expected failures")?;
        let mut failed_ids = BTreeSet::new();
        need(
            failures.iter().all(|v| {
                v.as_str()
                    .is_some_and(|s| ids.contains(s) && failed_ids.insert(s))
            }),
            "source operation invalid expected failure",
        )?;
        match control["role"].as_str() {
            Some("baseline") => baseline += 1,
            Some("reference") => {
                reference += 1;
                need(
                    failures.is_empty(),
                    "source operation reference expects failure",
                )?;
            }
            Some("wrong") => {
                wrong += 1;
                need(!failures.is_empty(), "source operation vacuous negative")?;
            }
            _ => return Err("source operation unknown role".into()),
        }
        budget = budget
            .checked_add(
                control["command"]["timeoutMs"]
                    .as_u64()
                    .ok_or("source operation command budget")?,
            )
            .ok_or("source operation budget overflow")?;
        let command = &control["command"];
        need(
            Path::new(text(command, "program")?).is_absolute()
                && sha(&command["programSha256"], 64)
                && command["args"].as_array().is_some_and(|a| {
                    a.len() <= 64
                        && a.iter()
                            .all(|v| v.as_str().is_some_and(|s| s.len() <= 4096))
                })
                && (command["cwd"] == "." || command["cwd"].as_str().is_some_and(relative))
                && command["timeoutMs"]
                    .as_u64()
                    .is_some_and(|n| (1..=180_000).contains(&n)),
            "source operation command contract",
        )?;
    }
    need(
        baseline == 1 && reference > 0 && wrong > 0 && budget <= 600_000,
        "source operation role/total budget",
    )?;
    Ok(())
}
fn verify_inputs(recipe: &Value, source: &Path) -> Result<(), String> {
    exec::clean(source, &recipe["source"])?;
    for input in recipe["sourceInputs"].as_array().unwrap() {
        let p = text(input, "path")?;
        let bytes = read(&source.join(p), 4 * 1024 * 1024)?;
        need(
            input["sha256"] == digest(&bytes),
            "source operation source bytes drift",
        )?;
        let git = Command::new("git")
            .args([
                "rev-parse",
                &format!("{}:{p}", text(&recipe["source"], "revision")?),
            ])
            .current_dir(source)
            .env("GIT_OPTIONAL_LOCKS", "0")
            .output()
            .map_err(|e| e.to_string())?;
        need(
            git.status.success()
                && String::from_utf8(git.stdout)
                    .map_err(|e| e.to_string())?
                    .trim()
                    == text(input, "gitBlobOid")?,
            "source operation Git Blob differs",
        )?;
    }
    for method in recipe["methodInputs"].as_array().unwrap() {
        need(
            method["sha256"] == digest(&read(Path::new(text(method, "path")?), 4 * 1024 * 1024)?),
            "source operation method bytes drift",
        )?;
    }
    Ok(())
}

/// Every command and original source is reviewed and pinned. This is not a sandbox.
#[cfg(not(unix))]
pub fn execute(
    _scopes: &Path,
    _facts: &Path,
    _receipts: &Path,
    _before_bytes: &[u8],
    _recipe_bytes: &[u8],
    _source: &Path,
    _out: &Path,
) -> Result<Value, String> {
    Err("source operation requires a Unix process-group adapter".into())
}
#[cfg(unix)]
pub fn execute(
    scopes: &Path,
    facts: &Path,
    receipts: &Path,
    before_bytes: &[u8],
    recipe_bytes: &[u8],
    source: &Path,
    out: &Path,
) -> Result<Value, String> {
    need(
        before_bytes.len() <= 2 * 1024 * 1024 && recipe_bytes.len() <= 256 * 1024,
        "source operation input budget",
    )?;
    let before: Value = serde_json::from_slice(before_bytes).map_err(|e| e.to_string())?;
    let recipe: Value = serde_json::from_slice(recipe_bytes).map_err(|e| e.to_string())?;
    let computed = assess_with_receipts(
        scopes,
        Some(facts),
        before["roundIndex"]
            .as_u64()
            .ok_or("source operation round")?,
        before["parentAssessmentSha256"].as_str(),
        Some(receipts),
    )?;
    need(
        computed == before,
        "source operation baseline reproduction differs",
    )?;
    let skills = read(scopes, 4 * 1024 * 1024)?;
    let rows = String::from_utf8(skills)
        .map_err(|e| e.to_string())?
        .lines()
        .map(|s| serde_json::from_str::<Value>(s).map_err(|e| e.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    let skill = rows
        .iter()
        .find(|s| s["id"] == recipe["scopeSkillId"])
        .ok_or("source operation scope absent")?;
    recipe_gate(&recipe, skill)?;
    let verdict = before["skills"]
        .as_array()
        .unwrap()
        .iter()
        .find(|s| s["skillId"] == skill["id"])
        .ok_or("source operation assessment scope absent")?;
    need(
        verdict["checks"]["semanticReady"] == true
            && crate::maintainer_flywheel_plan::operation_kind(&verdict["capabilities"])
                == "source-only",
        "source operation prerequisite/capability not ready",
    )?;
    let source = source.canonicalize().map_err(|e| e.to_string())?;
    verify_inputs(&recipe, &source)?;
    for c in recipe["controls"].as_array().unwrap() {
        exec::validate_command(&c["command"], &source)?;
    }
    need(
        !out.parent()
            .ok_or("source operation output parent")?
            .canonicalize()
            .map_err(|e| e.to_string())?
            .starts_with(&source),
        "source operation output inside source",
    )?;
    fs::create_dir(out).map_err(|e| e.to_string())?;
    save(out, "input-recipe.json", recipe_bytes)?;
    save(out, "input-before.json", before_bytes)?;
    save(
        out,
        "input-scope.json",
        &serde_json::to_vec(skill).map_err(|e| e.to_string())?,
    )?;
    for (i, input) in recipe["sourceInputs"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
    {
        save(
            out,
            &format!("source-{i}.original"),
            &read(&source.join(text(input, "path")?), 4 * 1024 * 1024)?,
        )?;
    }
    let mut captures = Vec::new();
    for (i, method) in recipe["methodInputs"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
    {
        save(
            out,
            &format!("method-{i}.original"),
            &read(Path::new(text(method, "path")?), 4 * 1024 * 1024)?,
        )?;
    }
    let result = (|| -> Result<(), String> {
        for control in recipe["controls"].as_array().unwrap() {
            verify_inputs(&recipe, &source)?;
            let capture = exec::capture_with_deadline_limit(
                &control["command"],
                &source,
                out,
                text(control, "id")?,
                &[],
                180_000,
            )?;
            let ok = capture["status"] == "successful";
            captures.push(capture);
            need(ok, "source operation control execution failed")?;
        }
        verify_inputs(&recipe, &source)
    })();
    let receipt = json!({"schema":"agentlab.maintainer_source_operation_execution.v1","status":if result.is_ok(){"successful"}else{"failed"},
        "source":recipe["source"],"scopeSkillId":recipe["scopeSkillId"],"recipeSha256":digest(recipe_bytes),"beforeAssessmentSha256":digest(before_bytes),
        "scopeSha256":digest(&serde_json::to_vec(skill).map_err(|e|e.to_string())?),
        "captures":captures,"error":result.err(),"qualified":false,"authorityWritePerformed":false,"automaticPromotion":false});
    save(
        out,
        "execution-receipt.json",
        &serde_json::to_vec_pretty(&receipt).map_err(|e| e.to_string())?,
    )?;
    need(
        receipt["status"] == "successful",
        "source operation failed; raw capture retained",
    )?;
    Ok(receipt)
}

/// Recompute declared checks from exact original stdout, never producer pass fields.
pub fn qualify(root: &Path, execution_sha: &str) -> Result<Value, String> {
    let bytes = read(&root.join("execution-receipt.json"), 2 * 1024 * 1024)?;
    need(
        digest(&bytes) == execution_sha,
        "source operation execution digest differs",
    )?;
    let execution: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    let recipe_bytes = read(&root.join("input-recipe.json"), 256 * 1024)?;
    need(
        execution["recipeSha256"] == digest(&recipe_bytes),
        "source operation recipe digest differs",
    )?;
    let recipe: Value = serde_json::from_slice(&recipe_bytes).map_err(|e| e.to_string())?;
    let scope_bytes = read(&root.join("input-scope.json"), 256 * 1024)?;
    need(
        execution["scopeSha256"] == digest(&scope_bytes),
        "source operation captured scope differs",
    )?;
    let skill: Value = serde_json::from_slice(&scope_bytes).map_err(|e| e.to_string())?;
    recipe_gate(&recipe, &skill)?;
    need(
        execution["beforeAssessmentSha256"]
            == digest(&read(&root.join("input-before.json"), 2 * 1024 * 1024)?),
        "source operation baseline digest differs",
    )?;
    for (i, input) in recipe["sourceInputs"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
    {
        need(
            input["sha256"]
                == digest(&read(
                    &root.join(format!("source-{i}.original")),
                    4 * 1024 * 1024,
                )?),
            "source operation original source differs",
        )?;
    }
    for (i, method) in recipe["methodInputs"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
    {
        need(
            method["sha256"]
                == digest(&read(
                    &root.join(format!("method-{i}.original")),
                    4 * 1024 * 1024,
                )?),
            "source operation original method differs",
        )?;
    }
    let mut streams = Vec::new();
    for c in execution["captures"]
        .as_array()
        .ok_or("source operation captures absent")?
    {
        let label = text(c, "label")?;
        need(relative(label), "source operation label escapes")?;
        let mut entry = json!({});
        for stream in ["stdout", "stderr"] {
            let p = format!("{label}.{stream}");
            let bytes = read(&root.join(&p), 256 * 1024)?;
            need(
                c[stream]["path"] == p
                    && c[stream]["complete"] == true
                    && c[stream]["sha256"] == digest(&bytes)
                    && c[stream]["bytes"] == bytes.len(),
                "source operation incomplete/changed stream",
            )?;
            entry[stream] = json!(String::from_utf8(bytes).map_err(|e| e.to_string())?);
        }
        streams.push(entry);
    }
    let receipt = json!({"schema":"agentlab.maintainer_scope_source_qualification.v1","status":"qualified",
        "recipeOriginal":String::from_utf8(recipe_bytes).map_err(|e|e.to_string())?,
        "executionOriginal":String::from_utf8(bytes).map_err(|e|e.to_string())?,
        "scopeOriginal":String::from_utf8(scope_bytes).map_err(|e|e.to_string())?,
        "recipe":recipe,"execution":execution,"streams":streams,"executionReceiptSha256":execution_sha,
        "source":recipe["source"],"scopeSkillId":recipe["scopeSkillId"],"automaticPromotion":false,"authorityWritePerformed":false,
        "qualificationScope":{"sourceMaintenance":true,"build":false,"runtime":false,"tests":false,"performance":false},
        "verificationBoundary":"Reviewed source-maintenance controls and retained bytes; no authenticated producer, full scope coverage, formal tests, framework runtime or Agent qualification."});
    recorded(&receipt, &skill)?;
    need(
        serde_json::to_vec(&receipt)
            .map_err(|e| e.to_string())?
            .len()
            <= 2 * 1024 * 1024,
        "source operation portable receipt budget",
    )?;
    Ok(receipt)
}

/// Portable strict assessment independently repeats the same content checks.
pub fn recorded(receipt: &Value, skill: &Value) -> Result<Value, String> {
    let recipe = &receipt["recipe"];
    recipe_gate(recipe, skill)?;
    let execution = &receipt["execution"];
    let original_recipe = text(receipt, "recipeOriginal")?.as_bytes();
    let original_execution = text(receipt, "executionOriginal")?.as_bytes();
    let original_scope = text(receipt, "scopeOriginal")?.as_bytes();
    need(
        serde_json::from_slice::<Value>(original_recipe).map_err(|e| e.to_string())? == *recipe
            && serde_json::from_slice::<Value>(original_execution).map_err(|e| e.to_string())?
                == *execution
            && execution["recipeSha256"] == digest(original_recipe)
            && receipt["executionReceiptSha256"] == digest(original_execution)
            && execution["scopeSha256"] == digest(original_scope)
            && serde_json::from_slice::<Value>(original_scope).map_err(|e| e.to_string())?
                == *skill,
        "source operation original byte lineage differs",
    )?;
    need(
        receipt["schema"] == "agentlab.maintainer_scope_source_qualification.v1"
            && receipt["status"] == "qualified"
            && receipt["automaticPromotion"] == false
            && receipt["authorityWritePerformed"] == false
            && receipt["source"] == recipe["source"]
            && receipt["scopeSkillId"] == recipe["scopeSkillId"]
            && sha(&receipt["executionReceiptSha256"], 64),
        "source operation qualification identity",
    )?;
    need(
        execution["schema"] == "agentlab.maintainer_source_operation_execution.v1"
            && execution["status"] == "successful"
            && execution["qualified"] == false
            && execution["automaticPromotion"] == false
            && execution["authorityWritePerformed"] == false
            && execution["source"] == recipe["source"]
            && execution["scopeSkillId"] == recipe["scopeSkillId"]
            && sha(&execution["recipeSha256"], 64)
            && sha(&execution["beforeAssessmentSha256"], 64),
        "source operation execution identity",
    )?;
    let controls = recipe["controls"].as_array().unwrap();
    let captures = execution["captures"]
        .as_array()
        .ok_or("source operation captures")?;
    let streams = receipt["streams"]
        .as_array()
        .ok_or("source operation streams")?;
    need(
        controls.len() == captures.len() && controls.len() == streams.len(),
        "source operation partial capture",
    )?;
    let mut pids = BTreeSet::new();
    let mut outcomes = Vec::new();
    for ((control, capture), streams) in controls.iter().zip(captures).zip(streams) {
        let label = text(control, "id")?;
        need(
            capture["label"] == label
                && capture["command"] == control["command"]
                && capture["status"] == "successful"
                && capture["termination"] == "completed"
                && capture["exitCode"] == 0
                && capture["durationMs"].as_u64().is_some_and(|n| n > 0)
                && capture["pid"]
                    .as_u64()
                    .is_some_and(|n| n > 0 && pids.insert(n)),
            "source operation failed/reused process",
        )?;
        for stream in ["stdout", "stderr"] {
            let bytes = text(streams, stream)
                .or_else(|_| {
                    streams[stream]
                        .as_str()
                        .ok_or("source operation missing stream")
                })?
                .as_bytes();
            need(
                bytes.len() <= 256 * 1024
                    && capture[stream]["path"] == format!("{label}.{stream}")
                    && capture[stream]["complete"] == true
                    && capture[stream]["sha256"] == digest(bytes)
                    && capture[stream]["bytes"] == bytes.len(),
                "source operation portable stream differs",
            )?;
        }
        let observed: Value = serde_json::from_str(streams["stdout"].as_str().unwrap())
            .map_err(|e| format!("source operation stdout is not JSON: {e}"))?;
        let mut failures = BTreeSet::new();
        for check in recipe["checks"].as_array().unwrap() {
            let actual = observed
                .pointer(text(check, "pointer")?)
                .ok_or("source operation observation missing check")?;
            if actual != &check["expected"] {
                failures.insert(text(check, "id")?);
            }
        }
        let expected = control["expectedFailedCheckIds"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s.as_str().unwrap())
            .collect::<BTreeSet<_>>();
        need(
            failures == expected,
            "source operation control outcome differs",
        )?;
        outcomes.push(json!({"id":label,"role":control["role"],"failedCheckIds":failures}));
    }
    need(
        receipt["qualificationScope"]
            == json!({"sourceMaintenance":true,"build":false,"runtime":false,"tests":false,"performance":false})
            && !text(receipt, "verificationBoundary")?.is_empty(),
        "source operation overclaimed qualification",
    )?;
    Ok(
        json!({"status":"verified","adapter":"recorded-source-maintenance-controls-v1","lane":"source-only",
        "qualificationScope":receipt["qualificationScope"],"controls":outcomes,"verificationBoundary":receipt["verificationBoundary"]}),
    )
}
