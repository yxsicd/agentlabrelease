//! Trusted, bounded multi-round transport across existing business gates.
//! Adapter completion is not independent semantic qualification or admission.
use crate::{
    digest,
    maintainer_behavior_loop::{freeze_tree, invoke_with_deadline_limit, pinned_inputs, recheck},
};
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    fs::{self, OpenOptions},
    io::Write,
    path::{Component, Path, PathBuf},
};

const STAGES: [&str; 5] = [
    "repository-understanding",
    "program-analysis",
    "maintenance-verification",
    "case-execution",
    "evidence-return",
];
fn environment_names(stage: &Value) -> Result<Vec<String>, String> {
    let Some(value) = stage.get("environmentNames") else {
        return Ok(Vec::new());
    };
    let names = value
        .as_array()
        .filter(|a| a.len() <= 12)
        .ok_or("cycle environment names invalid")?;
    let mut seen = BTreeSet::new();
    names
        .iter()
        .map(|value| {
            let name = value.as_str().ok_or("cycle environment name invalid")?;
            require(
                [
                    "AGENTLAB_LM_GATEWAY_URL",
                    "AGENTLAB_LM_GATEWAY_KEY",
                    "AGENTLAB_PI_BINARY",
                    "AGENTLAB_MODEL",
                    "AGENTLAB_PROVIDER_ROUTE",
                    "AGENTLAB_REASONING_EFFORT",
                    "AGENTLAB_PARTICIPANT_RUNTIME_CONFIG",
                    "DOCKER_CONFIG",
                    "AGENTLAB_TABLEGIT_MCP_URL",
                    "AGENTLAB_TABLEGIT_PERSON_ID",
                ]
                .contains(&name)
                    && seen.insert(name),
                "cycle environment name forbidden or duplicate",
            )?;
            require(
                std::env::var_os(name).is_some(),
                "cycle selected private environment absent",
            )?;
            Ok(name.to_owned())
        })
        .collect()
}
fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn save(path: &Path, bytes: &[u8]) -> Result<(), String> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(bytes)
        .map_err(|e| e.to_string())
}
fn json_save(path: &Path, value: &Value) -> Result<(), String> {
    save(
        path,
        &serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?,
    )
}
fn regular(path: &Path) -> Result<Vec<u8>, String> {
    for ancestor in path.ancestors() {
        require(
            !fs::symlink_metadata(ancestor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "cycle artifact symlink",
        )?;
    }
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    require(
        meta.is_file() && meta.len() <= 16 * 1024 * 1024,
        "cycle state must be bounded regular file",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    require(
        bytes.len() <= 16 * 1024 * 1024,
        "cycle state grew beyond budget",
    )?;
    Ok(bytes)
}
fn output_state(dir: &Path, result: &Value) -> Result<(PathBuf, String), String> {
    let relative = result["outputState"]["path"]
        .as_str()
        .ok_or("cycle output state path missing")?;
    require(
        !relative.is_empty()
            && Path::new(relative)
                .components()
                .all(|c| matches!(c, Component::Normal(_))),
        "cycle output state escapes stage",
    )?;
    let path = dir.join(relative);
    let sha = digest(&regular(&path)?);
    require(
        result["outputState"]["sha256"] == sha,
        "cycle output state digest mismatch",
    )?;
    Ok((path, sha))
}

/// Each adapter must run its own existing independent business gates. The
/// coordinator binds transport and preserves stopping boundaries; it never
/// converts an adapter claim into qualified knowledge, a case, or a release.
#[cfg(unix)]
pub fn execute(recipe_bytes: &[u8], out: &Path) -> Result<Value, String> {
    execute_from(recipe_bytes, out, None)
}

/// Continue only an explicitly selected, byte-bound completed boundary. An
/// uncertain dispatch is never retried and a checkpoint may be claimed once.
#[cfg(unix)]
pub fn resume(
    recipe_bytes: &[u8],
    out: &Path,
    checkpoint: &Path,
    sha: &str,
) -> Result<Value, String> {
    execute_from(recipe_bytes, out, Some((checkpoint, sha)))
}

#[cfg(unix)]
fn execute_from(
    recipe_bytes: &[u8],
    out: &Path,
    checkpoint: Option<(&Path, &str)>,
) -> Result<Value, String> {
    require(recipe_bytes.len() <= 1024 * 1024, "cycle recipe excessive")?;
    let recipe: Value = serde_json::from_slice(recipe_bytes).map_err(|e| e.to_string())?;
    require(
        recipe["schema"] == "agentlab.flywheel_cycles_recipe.v1"
            && recipe["reviewed"] == true
            && recipe["automaticPromotion"] == false,
        "cycle recipe unreviewed or invalid",
    )?;
    let rounds = recipe["maximumRounds"]
        .as_u64()
        .filter(|n| (1..=8).contains(n))
        .ok_or("cycle round budget invalid")?;
    let invocation_limit = match recipe.get("maximumStagesPerInvocation") {
        Some(value) => value
            .as_u64()
            .filter(|n| (1..=40).contains(n))
            .ok_or("cycle invocation stage budget invalid")?,
        None => 40,
    };
    let stages = recipe["stages"]
        .as_array()
        .filter(|s| s.len() == STAGES.len())
        .ok_or("cycle stages incomplete")?;
    let environments = stages
        .iter()
        .map(environment_names)
        .collect::<Result<Vec<_>, _>>()?;
    let mut round_budget_ms = 0;
    for (stage, name) in stages.iter().zip(STAGES) {
        require(
            stage["stage"] == name && stage["command"]["cwd"] == ".",
            "cycle stage order or cwd invalid",
        )?;
        require(
            stage["command"]["args"]
                .as_array()
                .is_some_and(|a| a.iter().filter(|v| **v == "{request}").count() == 1),
            "cycle adapter requires request argument",
        )?;
        require(
            stage["command"]["timeoutMs"]
                .as_u64()
                .is_some_and(|n| (1..=900_000).contains(&n)),
            "cycle adapter deadline invalid",
        )?;
        round_budget_ms += stage["command"]["timeoutMs"].as_u64().unwrap();
        let program = Path::new(
            stage["command"]["program"]
                .as_str()
                .ok_or("cycle program missing")?,
        );
        require(program.is_absolute(), "cycle program must be absolute")?;
        require(
            stage["command"]["programSha256"]
                == crate::maintainer_operation_exec::executable_sha(program)?,
            "cycle executable digest mismatch",
        )?;
    }
    let total_command_budget_ms = round_budget_ms * rounds;
    require(
        total_command_budget_ms <= 3_600_000,
        "cycle total command budget exceeds one hour",
    )?;
    let mut frozen = pinned_inputs(&recipe)?;
    let initial = PathBuf::from(
        recipe["initialState"]["path"]
            .as_str()
            .ok_or("cycle initial state missing")?,
    );
    require(
        initial.is_absolute(),
        "cycle initial state must be absolute",
    )?;
    let initial_sha = digest(&regular(&initial)?);
    require(
        recipe["initialState"]["sha256"] == initial_sha,
        "cycle initial state digest mismatch",
    )?;
    frozen.push((initial.clone(), initial_sha.clone()));
    require(out.is_absolute(), "cycle output must be absolute")?;
    for parent in out
        .parent()
        .ok_or("cycle output parent missing")?
        .ancestors()
    {
        require(
            !fs::symlink_metadata(parent)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "cycle output ancestor symlink",
        )?;
    }
    let mut state = initial;
    let mut state_sha = initial_sha;
    let mut history: Vec<Value> = Vec::new();
    let mut completed = 0;
    let mut seen_states = BTreeSet::from([state_sha.clone()]);
    let mut start_step = 0usize;
    if let Some((path, sha)) = checkpoint {
        require(path.is_absolute(), "cycle checkpoint must be absolute")?;
        let bytes = regular(path)?;
        require(digest(&bytes) == sha, "cycle checkpoint digest mismatch")?;
        let cut: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        require(
            cut["schema"] == "agentlab.flywheel_cycle_checkpoint.v1"
                && cut["recipeSha256"] == digest(recipe_bytes)
                && cut["automaticPromotion"] == false,
            "cycle checkpoint identity differs",
        )?;
        start_step = cut["nextStep"]
            .as_u64()
            .filter(|n| *n > 0 && *n < rounds * 5)
            .ok_or("cycle checkpoint has no remaining step")? as usize;
        history = cut["stages"]
            .as_array()
            .filter(|h| h.len() == start_step)
            .ok_or("cycle checkpoint history invalid")?
            .clone();
        for (index, item) in history.iter().enumerate() {
            require(
                item["round"] == index / 5
                    && item["stage"] == STAGES[index % 5]
                    && item["result"]["status"] == "completed",
                "cycle checkpoint history order invalid",
            )?;
        }
        let retained: Vec<(PathBuf, String)> =
            serde_json::from_value(cut["frozen"].clone()).map_err(|e| e.to_string())?;
        require(
            !retained.is_empty() && retained.len() <= 4096,
            "cycle checkpoint inventory invalid",
        )?;
        recheck(&retained)?;
        frozen.extend(retained);
        state = PathBuf::from(
            cut["latestState"]["path"]
                .as_str()
                .ok_or("cycle checkpoint state missing")?,
        );
        state_sha = digest(&regular(&state)?);
        require(
            cut["latestState"]["sha256"] == state_sha,
            "cycle checkpoint state differs",
        )?;
        seen_states =
            serde_json::from_value(cut["seenStates"].clone()).map_err(|e| e.to_string())?;
        completed = start_step / 5;
        // A later stage directory proves dispatch may have begun. Never infer
        // absence of an external effect from missing stdout or result files.
        let prior = path.parent().ok_or("cycle checkpoint parent missing")?;
        for entry in fs::read_dir(prior).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if name.starts_with("round-") {
                require(
                    (0..start_step).any(|i| name == format!("round-{}-{}", i / 5, STAGES[i % 5])),
                    "cycle checkpoint has uncertain subsequent dispatch",
                )?;
            }
        }
        let terminal_bytes = regular(&prior.join("cycles-result.json"))
            .map_err(|_| "cycle continuation requires terminal checkpoint-ready capture")?;
        let terminal: Value = serde_json::from_slice(&terminal_bytes).map_err(|e| e.to_string())?;
        require(
            terminal["status"] == "checkpoint-ready"
                && terminal["recipeSha256"] == digest(recipe_bytes)
                && terminal["latestCheckpoint"]["path"] == path.to_string_lossy().as_ref()
                && terminal["latestCheckpoint"]["sha256"] == sha
                && terminal["stages"] == cut["stages"],
            "cycle continuation requires matching terminal checkpoint-ready capture",
        )?;
        frozen.push((prior.join("cycles-result.json"), digest(&terminal_bytes)));
        require(
            !prior.join("continuation-claim.json").exists(),
            "cycle checkpoint already claimed",
        )?;
    }
    fs::create_dir(out).map_err(|e| e.to_string())?;
    if let Some((path, sha)) = checkpoint {
        json_save(
            &path.parent().unwrap().join("continuation-claim.json"),
            &json!({"checkpoint":path,"sha256":sha,"destination":out}),
        )?;
        frozen.push((path.to_owned(), sha.to_owned()));
    }
    save(&out.join("recipe.json"), recipe_bytes)?;
    frozen.push((out.join("recipe.json"), digest(recipe_bytes)));
    let mut status = "round-budget-exhausted";
    let mut dispatched = 0u64;
    let mut latest_checkpoint = Value::Null;
    'rounds: for round in (start_step as u64 / 5)..rounds {
        for (stage_index, stage) in stages.iter().enumerate() {
            if (round as usize * 5 + stage_index) < start_step {
                continue;
            }
            recheck(&frozen)?;
            let name = STAGES[stage_index];
            let dir = out.join(format!("round-{round}-{name}"));
            fs::create_dir(&dir).map_err(|e| e.to_string())?;
            let request = json!({"schema":"agentlab.flywheel_stage_request.v1", "round":round, "stage":name,
                "recipeSha256":digest(recipe_bytes), "inputState":{"path":state,"sha256":state_sha},
                "previousStage":history.last(), "automaticPromotion":false});
            let bytes = serde_json::to_vec_pretty(&request).map_err(|e| e.to_string())?;
            let request_path = dir.join("request.json");
            save(&request_path, &bytes)?;
            let request_sha = digest(&bytes);
            frozen.push((request_path, request_sha.clone()));
            // Forward only this stage's explicit selection. Values are not
            // recipe/request/receipt fields and never inherit into other stages.
            dispatched += 1;
            let outcome = invoke_with_deadline_limit(
                &stage["command"],
                &dir.join("request.json"),
                &dir,
                "adapter",
                &environments[stage_index],
                900_000,
            );
            recheck(&frozen)?;
            let (execution, stdout) = match outcome {
                Ok(value) => value,
                Err(error) => {
                    json_save(
                        &dir.join("failure.json"),
                        &json!({"kind":"infrastructure-or-capture", "error":error}),
                    )?;
                    status = "adapter-failed";
                    break 'rounds;
                }
            };
            let result: Value = serde_json::from_str(&stdout)
                .map_err(|e| format!("cycle adapter invalid response: {e}"))?;
            require(
                result["schema"] == "agentlab.flywheel_stage_result.v1"
                    && result["stage"] == name
                    && result["round"] == round
                    && result["requestSha256"] == request_sha
                    && result["inputStateSha256"] == state_sha
                    && result["automaticPromotion"] == false,
                "cycle result identity or input binding differs",
            )?;
            let decision = result["status"]
                .as_str()
                .ok_or("cycle stage status missing")?;
            require(
                ["completed", "review-required", "rejected", "no-change"].contains(&decision),
                "cycle result status invalid",
            )?;
            json_save(&dir.join("result.json"), &result)?;
            history.push(
                json!({"round":round,"stage":name,"requestSha256":request_sha,
                "resultSha256":digest(stdout.as_bytes()),"execution":execution,"result":result}),
            );
            if decision != "completed" {
                status = match decision {
                    "review-required" => "review-required",
                    "rejected" => "stage-rejected",
                    _ => "no-change",
                };
                freeze_tree(&dir, &mut frozen, 0)?;
                break 'rounds;
            }
            let (next_state, next_sha) = output_state(&dir, &result)?;
            // A fresh receipt alone is not knowledge gain. Evidence-return
            // must supply different next-round state bytes, or stop scheduling.
            if stage_index == STAGES.len() - 1 && !seen_states.insert(next_sha.clone()) {
                status = "no-change";
                freeze_tree(&dir, &mut frozen, 0)?;
                break 'rounds;
            }
            state = next_state;
            state_sha = next_sha;
            freeze_tree(&dir, &mut frozen, 0)?;
            recheck(&frozen)?;
            let next_step = round * 5 + stage_index as u64 + 1;
            if stage_index == 4 {
                completed += 1;
            }
            let cut_path = out.join(format!("checkpoint-{next_step}.json"));
            json_save(
                &cut_path,
                &json!({"schema":"agentlab.flywheel_cycle_checkpoint.v1",
                "recipeSha256":digest(recipe_bytes),"nextStep":next_step,"stages":history,
                "latestState":{"path":state,"sha256":state_sha},"seenStates":seen_states,
                "frozen":frozen,"automaticPromotion":false}),
            )?;
            latest_checkpoint = json!({"path":cut_path,"sha256":digest(&regular(&cut_path)?)});
            if dispatched >= invocation_limit && next_step < rounds * 5 {
                status = "checkpoint-ready";
                break 'rounds;
            }
        }
    }
    recheck(&frozen)?;
    let result = json!({"schema":"agentlab.flywheel_cycles_capture.v1", "recipeSha256":digest(recipe_bytes),
        "status":status,"completedRounds":completed,"totalCommandBudgetMs":total_command_budget_ms,"stages":history,"latestState":{"path":state,"sha256":state_sha},
        "stagesDispatchedThisInvocation":dispatched,"latestCheckpoint":latest_checkpoint,
        "resumedFrom":checkpoint.map(|(path,sha)| json!({"path":path,"sha256":sha})),
        "adapterClaimsIndependentlyQualified":false,"qualified":false,"automaticPromotion":false,
        "authorityWritesIndependentlyVerified":false,"securitySandboxed":false});
    json_save(&out.join("cycles-result.json"), &result)?;
    Ok(result)
}

#[cfg(not(unix))]
pub fn execute(_: &[u8], _: &Path) -> Result<Value, String> {
    Err("cycle capture requires Unix process containment".into())
}

#[cfg(not(unix))]
pub fn resume(_: &[u8], _: &Path, _: &Path, _: &str) -> Result<Value, String> {
    Err("cycle capture requires Unix process containment".into())
}
