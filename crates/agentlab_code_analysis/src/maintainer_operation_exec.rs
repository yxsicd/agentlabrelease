//! Explicitly reviewed local operations, not an execution sandbox or promotion oracle.
use crate::{
    digest,
    maintainer_flywheel_plan::{declared_operation_kinds, plan_for_capabilities},
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn string<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("operation {key} missing"))
}
fn contained(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let p = Path::new(relative);
    require(
        !relative.is_empty() && p.components().all(|c| matches!(c, Component::Normal(_))),
        "operation relative path escapes source",
    )?;
    let mut path = root.to_owned();
    for part in p.components() {
        path.push(part);
        let metadata = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        require(
            !metadata.file_type().is_symlink(),
            "operation path contains symlink",
        )?;
    }
    Ok(path)
}
fn bytes_sha(path: &Path, max: u64) -> Result<(u64, String), String> {
    let metadata = fs::metadata(path).map_err(|e| e.to_string())?;
    require(
        metadata.is_file() && metadata.len() <= max,
        "operation file exceeds capture budget",
    )?;
    let mut bytes = Vec::new();
    File::open(path)
        .map_err(|e| e.to_string())?
        .take(max + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    require(
        bytes.len() as u64 <= max,
        "operation file grew beyond capture budget",
    )?;
    Ok((bytes.len() as u64, digest(&bytes)))
}
/// Executable acquisition is not stdout/stderr capture. Monolithic Linux Node
/// can exceed 64 MiB; stream its exact bytes under a separate bounded budget.
pub(crate) fn executable_sha(path: &Path) -> Result<String, String> {
    const MAX: u64 = 256 * 1024 * 1024;
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    require(
        meta.is_file() && meta.len() <= MAX,
        "operation executable exceeds 256 MiB budget or is not a regular file",
    )?;
    let mut input = File::open(path).map_err(|e| e.to_string())?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    let mut bytes = 0u64;
    loop {
        let n = input.read(&mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        bytes += n as u64;
        require(bytes <= MAX, "operation executable grew beyond budget")?;
        hash.update(&buffer[..n]);
    }
    require(
        bytes == meta.len(),
        "operation executable changed during hashing",
    )?;
    Ok(format!("{:x}", hash.finalize()))
}

#[cfg(test)]
mod executable_budget_tests {
    use super::*;
    use std::io::{Seek, SeekFrom};
    #[test]
    fn composite_ceiling_does_not_relax_ordinary_operation_deadline() {
        let program = std::env::current_exe().unwrap();
        let command = json!({"program":program,"programSha256":executable_sha(&program).unwrap(),
            "args":[],"cwd":".","timeoutMs":240_000});
        let source = std::env::temp_dir().canonicalize().unwrap();
        assert!(validate_command(&command, &source)
            .unwrap_err()
            .contains("deadline"));
        assert!(validate_command_with_deadline(&command, &source, 900_000).is_ok());
        assert!(validate_command_with_deadline(&command, &source, 900_001).is_err());
    }
    #[test]
    fn executable_stream_hashes_beyond_log_budget_and_rejects_oversize() {
        let root = std::env::temp_dir().join(format!(
            "executable-budget-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let path = root.join("binary");
        let mut file = File::create(&path).unwrap();
        file.set_len(64 * 1024 * 1024 + 1).unwrap();
        let first = executable_sha(&path).unwrap();
        file.seek(SeekFrom::End(-1)).unwrap();
        file.write_all(b"x").unwrap();
        file.flush().unwrap();
        assert_ne!(
            first,
            executable_sha(&path).unwrap(),
            "executable tail beyond log budget was ignored"
        );
        file.set_len(256 * 1024 * 1024 + 1).unwrap();
        assert!(executable_sha(&path).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
fn write(path: &Path, value: &Value) -> Result<(), String> {
    let mut out = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    out.write_all(&serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    out.write_all(b"\n").map_err(|e| e.to_string())
}
fn git(source: &Path, args: &[&str]) -> Result<String, String> {
    // Read-only commands; disable optional Git locks and user-configured pager.
    let result = Command::new("git")
        .args(args)
        .current_dir(source)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .env("GIT_PAGER", "cat")
        .output()
        .map_err(|e| e.to_string())?;
    require(
        result.status.success(),
        "operation source identity query failed",
    )?;
    String::from_utf8(result.stdout)
        .map(|s| s.trim().to_owned())
        .map_err(|e| e.to_string())
}
pub(crate) fn clean(source: &Path, expected: &Value) -> Result<(), String> {
    require(
        git(source, &["rev-parse", "HEAD"])? == string(expected, "revision")?,
        "operation source revision drift",
    )?;
    require(
        git(source, &["remote", "get-url", "origin"])? == string(expected, "repository")?,
        "operation source remote mismatch",
    )?;
    require(
        git(
            source,
            &["status", "--porcelain=v1", "--untracked-files=all"],
        )?
        .is_empty(),
        "operation source is dirty",
    )
}
pub(crate) fn validate_command(command: &Value, source: &Path) -> Result<(), String> {
    validate_command_with_deadline(command, source, 180_000)
}
fn validate_command_with_deadline(
    command: &Value,
    source: &Path,
    limit: u64,
) -> Result<(), String> {
    require(
        (1..=900_000).contains(&limit),
        "operation deadline ceiling invalid",
    )?;
    let executable = Path::new(string(command, "program")?);
    require(
        executable.is_absolute(),
        "operation executable must be absolute",
    )?;
    require(
        executable_sha(executable)? == string(command, "programSha256")?,
        "operation executable digest mismatch",
    )?;
    require(
        command["args"].as_array().is_some_and(|a| {
            a.len() <= 64
                && a.iter()
                    .all(|s| s.as_str().is_some_and(|s| s.len() <= 4096))
        }),
        "operation argument budget invalid",
    )?;
    require(
        command["timeoutMs"]
            .as_u64()
            .is_some_and(|n| (1..=limit).contains(&n)),
        "operation deadline invalid",
    )?;
    let cwd = string(command, "cwd")?;
    require(
        cwd == "." || contained(source, cwd)?.is_dir(),
        "operation cwd missing",
    )
}

#[cfg(unix)]
pub(crate) fn capture(
    command: &Value,
    source: &Path,
    out: &Path,
    label: &str,
) -> Result<Value, String> {
    capture_with_environment(command, source, out, label, &[])
}

/// Private operator environment injection; values are never receipt fields.
#[cfg(unix)]
pub(crate) fn capture_with_environment(
    command: &Value,
    source: &Path,
    out: &Path,
    label: &str,
    environment_names: &[String],
) -> Result<Value, String> {
    capture_with_deadline_limit(command, source, out, label, environment_names, 180_000)
}

/// Composite-stage ceiling only; ordinary operation/behavior callers retain
/// their original 180-second ceiling through capture_with_environment.
#[cfg(unix)]
pub(crate) fn capture_with_deadline_limit(
    command: &Value,
    source: &Path,
    out: &Path,
    label: &str,
    environment_names: &[String],
    deadline_limit: u64,
) -> Result<Value, String> {
    use std::os::unix::process::CommandExt;
    validate_command_with_deadline(command, source, deadline_limit)?; // Revalidate immediately before spawning.
    let stdout = out.join(format!("{label}.stdout"));
    let stderr = out.join(format!("{label}.stderr"));
    let open = |p: &Path| {
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(p)
            .map_err(|e| e.to_string())
    };
    let cwd = if command["cwd"] == "." {
        source.to_owned()
    } else {
        contained(source, string(command, "cwd")?)?
    };
    let args = command["args"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap())
        .collect::<Vec<_>>();
    let start = Instant::now();
    let mut process = Command::new(string(command, "program")?);
    process
        .args(&args)
        .current_dir(&cwd)
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("HOME", std::env::var_os("HOME").unwrap_or_default())
        .env("LANG", "C.UTF-8")
        .stdin(Stdio::null())
        .stdout(open(&stdout)?)
        .stderr(open(&stderr)?)
        .process_group(0);
    for name in environment_names {
        let value =
            std::env::var_os(name).ok_or("operation selected private environment absent")?;
        process.env(name, value);
    }
    let spawn = process.spawn();
    let mut child = match spawn {
        Ok(child) => child,
        Err(error) => {
            let result = json!({"label":label,"command":command,"status":"spawn-failed","error":error.to_string(),"durationMs":start.elapsed().as_millis().max(1)});
            write(&out.join(format!("{label}.json")), &result)?;
            return Ok(result);
        }
    };
    let pid = child.id();
    let mut reason = "completed";
    let status = loop {
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
            break status;
        }
        let oversized = [&stdout, &stderr]
            .iter()
            .any(|p| fs::metadata(p).is_ok_and(|m| m.len() > 64 * 1024 * 1024));
        if oversized
            || start.elapsed().as_millis() >= command["timeoutMs"].as_u64().unwrap() as u128
        {
            reason = if oversized {
                "capture-budget-exceeded"
            } else {
                "deadline-exceeded"
            };
            // Kill only the process group created for this invocation, not a host-wide name.
            let _ = Command::new("/bin/kill")
                .args(["-KILL", "--", &format!("-{pid}")])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            let _ = child.kill();
            break child.wait().map_err(|e| e.to_string())?;
        }
        thread::sleep(Duration::from_millis(20));
    };
    // A reviewed command must not leave same-group background writers alive.
    let _ = Command::new("/bin/kill")
        .args(["-KILL", "--", &format!("-{pid}")])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    let log = |p: &Path| -> Value {
        match bytes_sha(p, 64 * 1024 * 1024) {
            Ok((bytes, sha)) => {
                json!({"path":p.file_name().unwrap().to_string_lossy(),"bytes":bytes,"sha256":sha,"complete":true})
            }
            Err(error) => {
                json!({"path":p.file_name().unwrap().to_string_lossy(),"complete":false,"error":error})
            }
        }
    };
    let stdout_log = log(&stdout);
    let stderr_log = log(&stderr);
    let complete = stdout_log["complete"] == true && stderr_log["complete"] == true;
    let result = json!({"label":label,"command":command,"pid":pid,"termination":reason,
        "status":if status.success() && reason == "completed" && complete {"successful"} else {"failed"},
        "exitCode":status.code(),"durationMs":start.elapsed().as_millis().max(1),"stdout":stdout_log,"stderr":stderr_log});
    write(&out.join(format!("{label}.json")), &result)?;
    Ok(result)
}

/// Reverify the exact scheduler selection before running one explicit recipe.
/// One selected scope is supported; larger batches fail rather than being narrowed.
#[allow(clippy::too_many_arguments)]
pub fn execute(
    scopes: &Path,
    facts: &Path,
    receipts: &Path,
    plan_bytes: &[u8],
    before_bytes: &[u8],
    recipe_bytes: &[u8],
    source: &Path,
    out: &Path,
) -> Result<Value, String> {
    #[cfg(not(unix))]
    return Err("bounded operation runner requires a Unix process-group adapter".into());
    #[cfg(unix)]
    {
        let proposed: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
        let before: Value = serde_json::from_slice(before_bytes).map_err(|e| e.to_string())?;
        let recipe: Value = serde_json::from_slice(recipe_bytes).map_err(|e| e.to_string())?;
        let policy = &proposed["policy"];
        let lanes = policy["availableLanes"]
            .as_array()
            .ok_or("operation lanes missing")?
            .iter()
            .map(|s| {
                s.as_str()
                    .map(str::to_owned)
                    .ok_or("operation lane invalid")
            })
            .collect::<Result<Vec<_>, _>>()?;
        let kinds = declared_operation_kinds(policy)?;
        require(
            kinds.as_ref().is_some_and(|kinds| kinds == &["build-only"]),
            "operation executor requires an explicit build-only capability plan",
        )?;
        let verified = plan_for_capabilities(
            scopes,
            Some(facts),
            receipts,
            before["roundIndex"]
                .as_u64()
                .ok_or("operation round missing")?,
            before["parentAssessmentSha256"].as_str(),
            &lanes,
            policy["batchSize"]
                .as_u64()
                .ok_or("operation batch missing")?
                .try_into()
                .map_err(|_| "operation batch overflow")?,
            policy["maxSourceFiles"]
                .as_u64()
                .ok_or("operation source budget missing")?,
            policy["repositorySelector"].as_str(),
            kinds.as_deref(),
        )?;
        require(
            proposed == verified && before == verified["assessment"],
            "operation plan or baseline differs from independent reassessment",
        )?;
        require(
            verified["decision"] == "propose-next-batch"
                && verified["nextLane"] == "operation-verification",
            "operation plan selected another lane",
        )?;
        let ids = verified["selectedScopeIds"]
            .as_array()
            .ok_or("operation selected scopes missing")?;
        require(
            ids.len() == 1,
            "operation executor requires exactly one selected scope; no batch narrowing",
        )?;
        let selected = verified["scopes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["skillId"] == ids[0])
            .unwrap();
        require(
            recipe["schema"] == "agentlab.maintainer_build_operation_recipe.v1"
                && recipe["automaticPromotion"] == false,
            "operation recipe contract invalid",
        )?;
        require(
            recipe["source"]["repositoryId"] == selected["repositoryId"]
                && recipe["source"]["repository"] == selected["repository"]
                && recipe["source"]["revision"] == selected["sourceRevision"]
                && recipe["scopeSkillId"] == ids[0],
            "operation recipe source or scope mismatch",
        )?;
        require(
            recipe["lane"] == "build-only" && recipe["cleanBuild"] == true,
            "operation executor supports explicit clean build recipes only",
        )?;
        let probes = recipe["probes"]
            .as_array()
            .filter(|a| !a.is_empty() && a.len() <= 4)
            .ok_or("operation toolchain probes missing")?;
        let source = source.canonicalize().map_err(|e| e.to_string())?;
        clean(&source, &recipe["source"])?;
        let commands = probes
            .iter()
            .chain([&recipe["dependencyPreparation"], &recipe["build"]])
            .collect::<Vec<_>>();
        for cmd in &commands {
            validate_command(cmd, &source)?;
        }
        let command_budget = commands
            .iter()
            .map(|cmd| cmd["timeoutMs"].as_u64().unwrap())
            .sum::<u64>()
            + recipe["build"]["timeoutMs"].as_u64().unwrap();
        require(
            command_budget <= 600_000,
            "operation total command budget exceeds ten minutes",
        )?;
        let artifact = string(&recipe, "artifact")?;
        require(
            Path::new(artifact)
                .components()
                .all(|c| matches!(c, Component::Normal(_))),
            "operation artifact path invalid",
        )?;
        let parent = out
            .parent()
            .ok_or("operation output parent missing")?
            .canonicalize()
            .map_err(|e| e.to_string())?;
        require(
            !parent.starts_with(&source),
            "operation output must be outside source",
        )?;
        fs::create_dir(out).map_err(|e| format!("operation output must be new: {e}"))?;
        for (name, bytes) in [
            ("input-plan.json", plan_bytes),
            ("input-before.json", before_bytes),
            ("input-recipe.json", recipe_bytes),
        ] {
            let mut input = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(out.join(name))
                .map_err(|e| e.to_string())?;
            input.write_all(bytes).map_err(|e| e.to_string())?;
        }
        write(
            &out.join("request.json"),
            &json!({"recipe":recipe,"recipeSha256":digest(recipe_bytes),"selectionPlanSha256":digest(plan_bytes),
            "beforeAssessmentSha256":digest(before_bytes),"sourceWorktree":source.to_string_lossy(),"qualified":false}),
        )?;
        let mut captures = Vec::new();
        let mut artifacts = Vec::new();
        let result = (|| -> Result<(), String> {
            for (i, probe) in probes.iter().enumerate() {
                let capture = capture(probe, &source, out, &format!("probe-{i}"))?;
                let success = capture["status"] == "successful";
                captures.push(capture);
                require(success, "operation toolchain probe failed")?;
            }
            let deps = capture(&recipe["dependencyPreparation"], &source, out, "dependency")?;
            let success = deps["status"] == "successful";
            captures.push(deps);
            require(success, "operation dependency preparation failed")?;
            clean(&source, &recipe["source"])?;
            for i in 1..=2 {
                let build = capture(&recipe["build"], &source, out, &format!("build-{i}"))?;
                let success = build["status"] == "successful";
                captures.push(build);
                require(success, "operation build failed")?;
                clean(&source, &recipe["source"])?;
                let path = contained(&source, artifact)?;
                let (bytes, sha) = bytes_sha(&path, 128 * 1024 * 1024)?;
                require(bytes > 0, "operation artifact is empty")?;
                let target = out.join(format!("attempt-{i}.artifact"));
                let mut retained = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(&target)
                    .map_err(|e| e.to_string())?;
                let mut original = File::open(&path)
                    .map_err(|e| e.to_string())?
                    .take(128 * 1024 * 1024 + 1);
                std::io::copy(&mut original, &mut retained).map_err(|e| e.to_string())?;
                require(
                    bytes_sha(&target, 128 * 1024 * 1024)? == (bytes, sha.clone()),
                    "operation artifact changed during capture",
                )?;
                artifacts.push(json!({"attempt":i,"sourcePath":artifact,"retainedPath":target.file_name().unwrap().to_string_lossy(),"bytes":bytes,"sha256":sha}));
            }
            Ok(())
        })();
        let clean_after = clean(&source, &recipe["source"]).is_ok();
        let succeeded = result.is_ok() && clean_after;
        let receipt = json!({"schema":"agentlab.maintainer_operation_execution.v1","status":if succeeded {"successful"} else {"failed"},
            "source":recipe["source"],"scopeSkillId":ids[0],"recipeSha256":digest(recipe_bytes),"selectionPlanSha256":digest(plan_bytes),
            "beforeAssessmentSha256":digest(before_bytes),"sourceCleanAfter":clean_after,"captures":captures,"artifacts":artifacts,
            "error":result.err(),"qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,"closedLoopQualified":false,
            "limitations":["Reviewed trusted commands only; process groups and budgets are not a sandbox.",
                "Raw artifact capture is not canonical member reproducibility or independent build qualification.",
                "No runtime, tests, performance, type-check, Skills promotion, or TableGit transaction is qualified."]});
        write(&out.join("execution-receipt.json"), &receipt)?;
        if !succeeded {
            return Err(
                "operation execution failed; retained output contains complete available evidence"
                    .into(),
            );
        }
        Ok(receipt)
    }
}
