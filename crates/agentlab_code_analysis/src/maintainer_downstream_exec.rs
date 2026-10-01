//! Explicit bounded diagnostic execution and portable feedback, not runtime
//! calibration qualification, assessed-Agent execution or a security sandbox.
use crate::digest;
#[cfg(unix)]
use crate::maintainer_operation_exec::capture;
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Component, Path, PathBuf},
    process::Command,
};

const PROBE: &[u8] = include_bytes!("../../../scripts/probe-hypium-failure-controls.cjs");
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
        .ok_or_else(|| format!("downstream execution {key} missing"))
}
fn read(path: &Path) -> Result<Vec<u8>, String> {
    let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    require(
        meta.is_file() && !meta.file_type().is_symlink() && meta.len() <= 64 * 1024 * 1024,
        "downstream file invalid or exceeds budget",
    )?;
    fs::read(path).map_err(|e| e.to_string())
}
fn write(path: &Path, v: &Value) -> Result<(), String> {
    let mut out = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    out.write_all(&serde_json::to_vec_pretty(v).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    out.write_all(b"\n").map_err(|e| e.to_string())
}
fn git(root: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let r = Command::new("git")
        .current_dir(root)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    require(r.status.success(), "downstream source query failed")?;
    Ok(r.stdout)
}
fn clean(root: &Path, revision: &str) -> Result<(), String> {
    require(
        String::from_utf8(git(root, &["rev-parse", "HEAD"])?)
            .map_err(|e| e.to_string())?
            .trim()
            == revision,
        "downstream source revision drift",
    )?;
    require(
        git(root, &["status", "--porcelain=v1", "--untracked-files=all"])?.is_empty(),
        "downstream source worktree dirty",
    )
}
fn binding(root: &Path, name: &str) -> Result<Value, String> {
    let b = read(&root.join(name))?;
    Ok(json!({"path":name,"sha256":digest(&b),"bytes":b.len()}))
}
fn verified(root: &Path, r: &Value) -> Result<Vec<u8>, String> {
    let p = Path::new(text(r, "path")?);
    require(
        p.components().all(|c| matches!(c, Component::Normal(_))),
        "downstream evidence path escapes root",
    )?;
    let mut cursor = root.to_owned();
    for c in p.components() {
        cursor.push(c);
        require(
            !fs::symlink_metadata(&cursor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "downstream evidence symlink rejected",
        )?;
    }
    let b = read(&cursor)?;
    require(
        r["sha256"] == digest(&b) && r["bytes"] == b.len(),
        "downstream evidence digest or bytes differ",
    )?;
    Ok(b)
}

fn classify_checked(
    plan: &Value,
    recipe: &Value,
    process: &Value,
    probe: Option<&Value>,
    unchanged: bool,
) -> Result<Value, String> {
    let mut sensitive = None;
    let mut decision = "repair-calibration-environment";
    if process["status"] == "successful"
        && process["termination"] == "completed"
        && process["exitCode"] == 0
        && process["durationMs"].as_u64().is_some_and(|n| n > 0)
        && unchanged
    {
        if let Some(p) = probe {
            require(
                p["schema"] == "agentlab.hypium_failure_control_probe.v1"
                    && p["qualified"] == false
                    && p["automaticPromotion"] == false
                    && p["authorityWritePerformed"] == false,
                "downstream probe overclaims or schema differs",
            )?;
            require(
                p["source"]["revision"] == plan["sourceRevision"]
                    && p["source"]["path"] == recipe["testPath"]
                    && p["source"]["sha256"] == recipe["testSourceSha256"]
                    && p["source"]["gitBlobOid"] == recipe["testBlobOid"]
                    && p["methodSha256"] == digest(PROBE)
                    && p["testId"] == recipe["testId"]
                    && p["suiteExport"] == recipe["suiteExport"],
                "downstream probe identity differs",
            )?;
            let controls = p["controls"]
                .as_array()
                .ok_or("downstream controls missing")?;
            require(controls.len() == 2, "downstream control count differs")?;
            for (i, c) in controls.iter().enumerate() {
                require(
                    c["control"] == if i == 0 { "resolve" } else { "reject" }
                        && c["source"] == p["source"]
                        && c["startCalls"] == 1
                        && matches!(c["verdict"].as_str(), Some("accept" | "reject")),
                    "downstream controls incomplete or duplicated",
                )?;
                if !recipe["typescript"].is_null() {
                    require(
                        c["compiler"]["kind"] == "typescript-type-erasure-only"
                            && c["compiler"]["sha256"] == recipe["typescript"]["sha256"],
                        "downstream compiler evidence differs",
                    )?;
                } else {
                    require(
                        c["compiler"]["kind"] == "javascript-pass-through",
                        "downstream unexpected compiler",
                    )?;
                }
            }
            let observed = controls[0]["verdict"] == "accept" && controls[1]["verdict"] == "reject";
            require(
                p["failureSensitive"] == observed
                    && p["decision"]
                        == if observed {
                            "continue-runtime-calibration"
                        } else {
                            "repair-oracle-before-runtime-calibration"
                        },
                "downstream probe decision contradicts controls",
            )?;
            sensitive = Some(observed);
            decision = if observed {
                "continue-runtime-calibration"
            } else {
                "repair-independent-oracle"
            };
        }
    }
    Ok(
        json!({"schema":"agentlab.maintainer_downstream_feedback.v1","candidateId":plan["candidateId"],
        "candidateSha256":plan["candidateSha256"],"sourceRevision":plan["sourceRevision"],
        "sourceSetSha256":plan["sourceSetSha256"],"knowledgeCutSha256":plan["knowledgeCutSha256"],
        "actionId":recipe["actionId"],"decision":decision,"failureSensitive":sensitive,
        "sourceUnchanged":unchanged,"qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,
        "agentExecutionPerformed":false,"verificationBoundary":"controlled startup seam only; no wrong-implementation, emulator, HAP, case freeze or Agent qualification"}),
    )
}

fn classify(
    plan: &Value,
    recipe: &Value,
    process: &Value,
    probe: Option<&Value>,
    unchanged: bool,
) -> Result<Value, String> {
    match classify_checked(plan, recipe, process, probe, unchanged) {
        Ok(v) => Ok(v),
        Err(error) => {
            // A malformed successful-looking result is an adapter failure, not
            // a negative implementation verdict. Retain it and a terminal record.
            let mut fallback = classify_checked(plan, recipe, process, None, unchanged)?;
            fallback["admissionError"] = json!(error);
            Ok(fallback)
        }
    }
}

/// Caller explicitly selects a reviewed adapter recipe. No shell, provider
/// credentials, generic Agent-generated command or physical-device fallback.
pub fn recipe(
    plan_bytes: &[u8],
    source: &Path,
    node: &Path,
    script: &Path,
    test: &str,
    suite: &str,
    test_id: &str,
    compiler: Option<&Path>,
) -> Result<Value, String> {
    let plan: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
    let actions = plan["actions"]
        .as_array()
        .ok_or("downstream recipe actions absent")?
        .iter()
        .filter(|a| {
            a["kind"] == "implement-and-calibrate-oracle" && a["readyForScheduling"] == true
        })
        .collect::<Vec<_>>();
    require(
        actions.len() == 1,
        "downstream recipe has no unique ready Oracle action",
    )?;
    require(
        Path::new(test)
            .components()
            .all(|c| matches!(c, Component::Normal(_))),
        "downstream recipe test path unsafe",
    )?;
    clean(source, text(&plan, "sourceRevision")?)?;
    let spec = format!("{}:{test}", text(&plan, "sourceRevision")?);
    let blob = String::from_utf8(git(source, &["rev-parse", &spec])?)
        .map_err(|e| e.to_string())?
        .trim()
        .to_owned();
    let node = fs::canonicalize(node).map_err(|e| e.to_string())?;
    let script = fs::canonicalize(script).map_err(|e| e.to_string())?;
    require(
        digest(&read(&script)?) == digest(PROBE),
        "downstream recipe method differs",
    )?;
    let compiler = compiler
        .map(|p| -> Result<Value, String> {
            let p = fs::canonicalize(p).map_err(|e| e.to_string())?;
            Ok(json!({"path":p,"sha256":digest(&read(&p)?)}))
        })
        .transpose()?;
    Ok(
        json!({"schema":"agentlab.maintainer_downstream_probe_recipe.v1","reviewed":true,"adapter":"hypium-startability-controls",
        "planSha256":digest(plan_bytes),"actionId":actions[0]["id"],"testPath":test,"testBlobOid":blob,
        "testSourceSha256":digest(&git(source,&["cat-file","blob",&blob])?),"suiteExport":suite,"testId":test_id,
        "nodeSha256":digest(&read(&node)?),"node":node,"probeScript":script,"timeoutMs":15_000,"typescript":compiler}),
    )
}

#[cfg(unix)]
pub fn execute(
    plan_bytes: &[u8],
    candidate_bytes: &[u8],
    recipe_bytes: &[u8],
    source: &Path,
    out: &Path,
) -> Result<Value, String> {
    let plan: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
    let candidate: Value = serde_json::from_slice(candidate_bytes).map_err(|e| e.to_string())?;
    let recipe: Value = serde_json::from_slice(recipe_bytes).map_err(|e| e.to_string())?;
    require(
        plan["schema"] == "agentlab.maintainer_downstream_plan.v1"
            && plan["status"] == "next-actions-planned"
            && plan["schedulingAllowed"] == true
            && plan["automaticPromotion"] == false,
        "downstream plan not schedulable",
    )?;
    require(
        plan["candidateId"] == candidate["id"]
            && plan["candidateSha256"]
                == digest(&serde_json::to_vec(&candidate).map_err(|e| e.to_string())?),
        "downstream candidate binding differs",
    )?;
    for key in ["sourceRevision", "sourceSetSha256", "knowledgeCutSha256"] {
        require(
            plan[key] == candidate[key],
            "downstream candidate source cut differs",
        )?;
    }
    require(
        recipe["schema"] == "agentlab.maintainer_downstream_probe_recipe.v1"
            && recipe["reviewed"] == true
            && recipe["adapter"] == "hypium-startability-controls"
            && recipe["planSha256"] == digest(plan_bytes),
        "downstream recipe unreviewed or plan differs",
    )?;
    let actions = plan["actions"]
        .as_array()
        .ok_or("downstream actions missing")?;
    let selected = actions
        .iter()
        .filter(|a| a["id"] == recipe["actionId"])
        .collect::<Vec<_>>();
    require(
        selected.len() == 1
            && selected[0]["kind"] == "implement-and-calibrate-oracle"
            && selected[0]["readyForScheduling"] == true,
        "downstream action cannot run diagnostic",
    )?;
    let test = text(&recipe, "testPath")?;
    require(
        Path::new(test)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
            && ["contextPaths", "editablePaths"].iter().any(|k| {
                candidate[*k]
                    .as_array()
                    .is_some_and(|a| a.iter().any(|p| p == test))
            }),
        "downstream test escapes candidate source boundary",
    )?;
    let source = fs::canonicalize(source).map_err(|e| e.to_string())?;
    clean(&source, text(&plan, "sourceRevision")?)?;
    let spec = format!("{}:{test}", text(&plan, "sourceRevision")?);
    let blob = String::from_utf8(git(&source, &["rev-parse", &spec])?)
        .map_err(|e| e.to_string())?
        .trim()
        .to_owned();
    require(
        recipe["testBlobOid"] == blob
            && recipe["testSourceSha256"] == digest(&git(&source, &["cat-file", "blob", &blob])?),
        "downstream test Blob differs",
    )?;
    let script = PathBuf::from(text(&recipe, "probeScript")?);
    require(
        script.is_absolute() && digest(&read(&script)?) == digest(PROBE),
        "downstream probe adapter is not compiled method",
    )?;
    let node = PathBuf::from(text(&recipe, "node")?);
    require(
        node.is_absolute() && digest(&read(&node)?) == recipe["nodeSha256"],
        "downstream Node digest differs",
    )?;
    require(
        recipe["timeoutMs"]
            .as_u64()
            .is_some_and(|n| (1..=30_000).contains(&n)),
        "downstream deadline invalid",
    )?;
    require(
        !out.exists() && !out.is_symlink(),
        "downstream output already exists",
    )?;
    let parent = fs::canonicalize(out.parent().ok_or("downstream output parent missing")?)
        .map_err(|e| e.to_string())?;
    require(
        !parent.starts_with(&source),
        "downstream evidence must be outside source",
    )?;
    let out = parent.join(out.file_name().ok_or("downstream output name missing")?);
    let mut args = vec![
        script.to_string_lossy().into_owned(),
        "--source-repo".into(),
        source.to_string_lossy().into_owned(),
        "--revision".into(),
        text(&plan, "sourceRevision")?.into(),
        "--test-path".into(),
        test.into(),
        "--suite-export".into(),
        text(&recipe, "suiteExport")?.into(),
        "--test-id".into(),
        text(&recipe, "testId")?.into(),
        "--output".into(),
        out.join("probe.json").to_string_lossy().into_owned(),
    ];
    if !recipe["typescript"].is_null() {
        let compiler = PathBuf::from(text(&recipe["typescript"], "path")?);
        require(
            compiler.is_absolute() && digest(&read(&compiler)?) == recipe["typescript"]["sha256"],
            "downstream compiler digest differs",
        )?;
        args.extend([
            "--typescript".into(),
            compiler.to_string_lossy().into_owned(),
            "--typescript-sha256".into(),
            text(&recipe["typescript"], "sha256")?.into(),
        ]);
    }
    fs::create_dir(&out).map_err(|e| e.to_string())?;
    for (name, bytes) in [
        ("plan.json", plan_bytes),
        ("candidate.json", candidate_bytes),
        ("recipe.json", recipe_bytes),
    ] {
        let mut f = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(out.join(name))
            .map_err(|e| e.to_string())?;
        f.write_all(bytes).map_err(|e| e.to_string())?;
    }
    let command = json!({"program":node,"programSha256":recipe["nodeSha256"],"args":args,"cwd":".","timeoutMs":recipe["timeoutMs"]});
    let process = capture(&command, &source, &out, "process")?;
    let unchanged = clean(&source, text(&plan, "sourceRevision")?).is_ok();
    let probe = read(&out.join("probe.json"))
        .ok()
        .and_then(|b| serde_json::from_slice::<Value>(&b).ok());
    let feedback = classify(&plan, &recipe, &process, probe.as_ref(), unchanged)?;
    write(&out.join("feedback.json"), &feedback)?;
    let names = [
        "plan.json",
        "candidate.json",
        "recipe.json",
        "process.json",
        "process.stdout",
        "process.stderr",
        "feedback.json",
    ];
    let mut evidence = names
        .iter()
        .map(|name| binding(&out, name))
        .collect::<Result<Vec<_>, _>>()?;
    if out.join("probe.json").is_file() {
        evidence.push(binding(&out, "probe.json")?);
    }
    let receipt = json!({"schema":"agentlab.maintainer_downstream_execution.v1","candidateId":plan["candidateId"],
        "candidateSha256":plan["candidateSha256"],"actionId":recipe["actionId"],"sourceRevision":plan["sourceRevision"],
        "process":process,"sourceUnchanged":unchanged,"feedback":feedback,"evidence":evidence,
        "qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,"agentExecutionPerformed":false});
    write(&out.join("execution.json"), &receipt)?;
    Ok(receipt)
}

/// Reconstruct the feedback from byte-bound raw inputs and stdout/stderr.
/// No subprocess, Agent or source checkout is reexecuted by this readback.
pub fn readback(root: &Path, expected_sha: &str) -> Result<Value, String> {
    require(
        root.is_dir() && !root.is_symlink(),
        "downstream evidence root invalid",
    )?;
    let bytes = read(&root.join("execution.json"))?;
    require(
        digest(&bytes) == expected_sha,
        "downstream execution digest differs",
    )?;
    let receipt: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    require(
        receipt["schema"] == "agentlab.maintainer_downstream_execution.v1"
            && receipt["qualified"] == false
            && receipt["automaticPromotion"] == false
            && receipt["authorityWritePerformed"] == false
            && receipt["agentExecutionPerformed"] == false,
        "downstream execution overclaimed",
    )?;
    let mut files = std::collections::BTreeMap::new();
    for r in receipt["evidence"]
        .as_array()
        .ok_or("downstream evidence missing")?
    {
        let path = text(r, "path")?.to_owned();
        require(
            files.insert(path, verified(root, r)?).is_none(),
            "downstream evidence duplicated",
        )?;
    }
    let parse = |name: &str| -> Result<Value, String> {
        serde_json::from_slice(
            files
                .get(name)
                .ok_or_else(|| format!("downstream {name} absent"))?,
        )
        .map_err(|e| e.to_string())
    };
    let plan = parse("plan.json")?;
    let candidate = parse("candidate.json")?;
    let recipe = parse("recipe.json")?;
    let process = parse("process.json")?;
    require(
        recipe["planSha256"] == digest(files.get("plan.json").unwrap())
            && plan["candidateId"] == candidate["id"]
            && plan["candidateSha256"]
                == digest(&serde_json::to_vec(&candidate).map_err(|e| e.to_string())?)
            && receipt["candidateSha256"] == plan["candidateSha256"]
            && receipt["candidateId"] == plan["candidateId"]
            && receipt["sourceRevision"] == plan["sourceRevision"]
            && receipt["actionId"] == recipe["actionId"]
            && receipt["process"] == process,
        "downstream readback input binding differs",
    )?;
    for key in ["stdout", "stderr"] {
        if process["status"] == "spawn-failed" {
            require(
                files
                    .get(&format!("process.{key}"))
                    .is_some_and(|b| b.is_empty()),
                "downstream failed spawn log differs",
            )?;
            continue;
        }
        let log = files
            .get(text(&process[key], "path")?)
            .ok_or("downstream process log missing")?;
        require(
            process[key]["sha256"] == digest(log)
                && process[key]["bytes"] == log.len()
                && process[key]["complete"] == true,
            "downstream process log differs",
        )?;
    }
    let probe = files
        .get("probe.json")
        .and_then(|b| serde_json::from_slice::<Value>(b).ok());
    let feedback = classify(
        &plan,
        &recipe,
        &process,
        probe.as_ref(),
        receipt["sourceUnchanged"] == true,
    )?;
    require(
        feedback == parse("feedback.json")? && feedback == receipt["feedback"],
        "downstream replay feedback differs",
    )?;
    Ok(
        json!({"schema":"agentlab.maintainer_downstream_readback.v1","executionSha256":expected_sha,
        "feedback":feedback,"verifiedEvidenceCount":files.len(),"executionReplayed":false,
        "qualified":false,"automaticPromotion":false,"authorityWritePerformed":false}),
    )
}

pub fn next(
    root: &Path,
    expected_sha: &str,
    previous_bytes: Option<&[u8]>,
) -> Result<Value, String> {
    let readback = readback(root, expected_sha)?;
    let feedback = &readback["feedback"];
    let task_sha = digest(&serde_json::to_vec(feedback).map_err(|e| e.to_string())?);
    let mut unchanged = false;
    if let Some(bytes) = previous_bytes {
        let previous: Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
        require(
            previous["schema"] == "agentlab.maintainer_downstream_feedback_plan.v1"
                && previous["automaticPromotion"] == false
                && previous["candidateId"] == feedback["candidateId"]
                && previous["candidateSha256"] == feedback["candidateSha256"],
            "downstream previous feedback plan differs",
        )?;
        unchanged = previous["taskSha256"] == task_sha;
    }
    Ok(
        json!({"schema":"agentlab.maintainer_downstream_feedback_plan.v1","candidateId":feedback["candidateId"],
        "candidateSha256":feedback["candidateSha256"],"executionSha256":expected_sha,"sourceRevision":feedback["sourceRevision"],
        "taskSha256":task_sha,"nextAction":feedback["decision"],"schedulingAllowed":!unchanged,
        "status":if unchanged {"awaiting-new-evidence"}else{"feedback-selected-next-action"},
        "feedback":feedback,"qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,
        "agentExecutionPerformed":false}),
    )
}

#[cfg(not(unix))]
pub fn execute(
    _plan: &[u8],
    _candidate: &[u8],
    _recipe: &[u8],
    _source: &Path,
    _out: &Path,
) -> Result<Value, String> {
    Err("downstream probe execution requires Unix process-group capture".into())
}
