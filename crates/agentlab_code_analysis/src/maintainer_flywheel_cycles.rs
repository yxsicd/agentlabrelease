//! Trusted, bounded multi-round transport across existing business gates.
//! Adapter completion is not independent semantic qualification or admission.
use crate::{
    digest,
    maintainer_behavior_loop::{freeze_tree, invoke, pinned_inputs, recheck},
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
    let stages = recipe["stages"]
        .as_array()
        .filter(|s| s.len() == STAGES.len())
        .ok_or("cycle stages incomplete")?;
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
                .is_some_and(|n| (1..=180_000).contains(&n)),
            "cycle adapter deadline invalid",
        )?;
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
    fs::create_dir(out).map_err(|e| e.to_string())?;
    save(&out.join("recipe.json"), recipe_bytes)?;
    frozen.push((out.join("recipe.json"), digest(recipe_bytes)));
    let mut state = initial;
    let mut state_sha = initial_sha;
    let mut history = Vec::new();
    let mut status = "round-budget-exhausted";
    let mut completed = 0;
    let mut seen_states = BTreeSet::from([state_sha.clone()]);
    'rounds: for round in 0..rounds {
        for (stage_index, stage) in stages.iter().enumerate() {
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
            // Do not inject credentials into every stage. Trusted adapters may
            // obtain their own scoped private credentials; never put them in recipes.
            let outcome = invoke(
                &stage["command"],
                &dir.join("request.json"),
                &dir,
                "adapter",
                &[],
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
        }
        completed += 1;
    }
    recheck(&frozen)?;
    let result = json!({"schema":"agentlab.flywheel_cycles_capture.v1", "recipeSha256":digest(recipe_bytes),
        "status":status,"completedRounds":completed,"stages":history,"latestState":{"path":state,"sha256":state_sha},
        "adapterClaimsIndependentlyQualified":false,"qualified":false,"automaticPromotion":false,
        "authorityWritesIndependentlyVerified":false,"securitySandboxed":false});
    json_save(&out.join("cycles-result.json"), &result)?;
    Ok(result)
}

#[cfg(not(unix))]
pub fn execute(_: &[u8], _: &Path) -> Result<Value, String> {
    Err("cycle capture requires Unix process containment".into())
}
