//! Generic recorded behavior comparison. No repository, framework or predicate
//! is selected by this consumer. It does not authenticate or execute producers.
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
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("behavior {key} missing"))
}
fn hex(value: &Value, key: &str, length: usize) -> Result<(), String> {
    let s = text(value, key)?;
    require(
        s.len() == length
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "behavior digest invalid",
    )
}

pub fn verify(contract_bytes: &[u8], capture_bytes: &[u8]) -> Result<Value, String> {
    require(
        contract_bytes.len() <= 256 * 1024 && capture_bytes.len() <= 4 * 1024 * 1024,
        "behavior input budget exceeded",
    )?;
    let contract: Value = serde_json::from_slice(contract_bytes).map_err(|e| e.to_string())?;
    let capture: Value = serde_json::from_slice(capture_bytes).map_err(|e| e.to_string())?;
    require(
        contract["schema"] == "agentlab.frozen_behavior_checks.v1"
            && contract["automaticPromotion"] == false,
        "behavior contract schema or promotion differs",
    )?;
    require(
        capture["schema"] == "agentlab.behavior_worker_capture.v1"
            && capture["contractSha256"] == digest(contract_bytes),
        "behavior capture contract differs",
    )?;
    text(&contract, "candidateId")?;
    for key in [
        "candidateSha256",
        "originalSourceSha256",
        "methodSha256",
        "compilerSha256",
    ] {
        hex(&contract, key, 64)?;
    }
    hex(&contract, "sourceRevision", 40)?;
    text(&contract, "runtime")?;
    for key in [
        "candidateId",
        "candidateSha256",
        "sourceRevision",
        "methodSha256",
        "compilerSha256",
        "runtime",
    ] {
        require(
            capture[key] == contract[key],
            "behavior execution identity differs",
        )?;
    }
    let deadline = contract["workerDeadlineMs"]
        .as_u64()
        .filter(|n| *n > 0 && *n <= 60_000)
        .ok_or("behavior deadline invalid")?;
    let checks = contract["checks"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 128)
        .ok_or("behavior checks absent or excessive")?;
    let mut expected = BTreeMap::new();
    for check in checks {
        let id = text(check, "id")?;
        require(
            check.get("input").is_some() && check.get("expected").is_some(),
            "behavior frozen input or expectation missing",
        )?;
        require(
            expected.insert(id, check).is_none(),
            "behavior frozen check duplicated",
        )?;
    }
    let manifests = contract["controls"]
        .as_array()
        .filter(|a| a.len() >= 5 && a.len() <= 32)
        .ok_or("behavior controls absent or excessive")?;
    let workers = capture["workers"]
        .as_array()
        .ok_or("behavior workers absent")?;
    require(
        workers.len() == manifests.len(),
        "behavior workers incomplete",
    )?;
    let mut declarations = BTreeMap::new();
    let mut roles = BTreeMap::<String, usize>::new();
    let mut source_digests = BTreeSet::new();
    for control in manifests {
        let id = text(control, "id")?;
        let role = text(control, "role")?;
        require(
            ["baseline", "accepted", "wrong", "agent-attempt"].contains(&role),
            "behavior role unknown",
        )?;
        hex(control, "submittedSourceSha256", 64)?;
        require(
            source_digests.insert(text(control, "submittedSourceSha256")?),
            "behavior control sources duplicate",
        )?;
        let intended = control["expectedFailedCheckIds"]
            .as_array()
            .ok_or("behavior intended failures absent")?;
        let mut seen = BTreeSet::new();
        for item in intended {
            let id = item.as_str().ok_or("behavior failure ID invalid")?;
            require(
                expected.contains_key(id) && seen.insert(id),
                "behavior intended check unknown or duplicate",
            )?;
        }
        require(
            match role {
                "accepted" => intended.is_empty(),
                "baseline" | "wrong" => !intended.is_empty(),
                _ => true,
            },
            "behavior failure declaration differs from role",
        )?;
        if role == "baseline" {
            require(
                control["submittedSourceSha256"] == contract["originalSourceSha256"],
                "behavior baseline source differs",
            )?;
        }
        require(
            declarations.insert(id, control).is_none(),
            "behavior control duplicated",
        )?;
        *roles.entry(role.into()).or_default() += 1;
    }
    require(
        roles.get("baseline") == Some(&1)
            && roles.get("accepted").copied().unwrap_or(0) >= 2
            && roles.get("wrong").copied().unwrap_or(0) >= 2,
        "behavior calibration roles incomplete",
    )?;
    let mut seen = BTreeSet::new();
    let mut results = Vec::new();
    let mut baseline_matches = false;
    let mut accepted_pass = true;
    let mut wrong_discriminate = true;
    let mut agent_passed = None;
    for worker in workers {
        let id = text(worker, "id")?;
        require(seen.insert(id), "behavior worker duplicated")?;
        let control = declarations.get(id).ok_or("behavior worker undeclared")?;
        let execution = &worker["execution"];
        require(
            execution["exitCode"].as_i64() == Some(0)
                && execution["timedOut"] == false
                && execution["durationMs"]
                    .as_u64()
                    .is_some_and(|n| n > 0 && n <= deadline),
            "behavior worker infrastructure failure",
        )?;
        let stdout = text(execution, "stdout")?;
        require(
            execution["stdoutSha256"] == digest(stdout.as_bytes()),
            "behavior worker stdout differs",
        )?;
        let raw: Value = serde_json::from_str(stdout).map_err(|e| e.to_string())?;
        require(
            raw["id"] == id
                && raw["submittedSourceSha256"] == control["submittedSourceSha256"]
                && raw["originalSourceSha256"] == contract["originalSourceSha256"],
            "behavior worker source binding differs",
        )?;
        require(
            digest(text(&raw, "submittedSource")?.as_bytes())
                == text(control, "submittedSourceSha256")?,
            "behavior submitted bytes differ",
        )?;
        let observations = raw["observations"]
            .as_array()
            .ok_or("behavior observations absent")?;
        require(
            observations.len() == expected.len(),
            "behavior observations incomplete",
        )?;
        let mut observed_ids = BTreeSet::new();
        let mut failures = BTreeSet::new();
        let mut reconstructed = Vec::new();
        for observed in observations {
            let check_id = text(observed, "id")?;
            require(
                observed_ids.insert(check_id),
                "behavior observation duplicated",
            )?;
            let frozen = expected
                .get(check_id)
                .ok_or("behavior observed check undeclared")?;
            require(
                observed.get("input").is_some()
                    && observed["input"] == frozen["input"]
                    && observed.get("actual").is_some(),
                "behavior observed input or actual missing",
            )?;
            let passed = observed["actual"] == frozen["expected"];
            if !passed {
                failures.insert(check_id.to_owned());
            }
            reconstructed.push(json!({"id":check_id,"expected":frozen["expected"],"actual":observed["actual"],"passed":passed}));
        }
        let intended: BTreeSet<String> = control["expectedFailedCheckIds"]
            .as_array()
            .unwrap()
            .iter()
            .map(|id| id.as_str().unwrap().into())
            .collect();
        match text(control, "role")? {
            "baseline" => baseline_matches = failures == intended,
            "accepted" => accepted_pass &= failures.is_empty(),
            "wrong" => wrong_discriminate &= intended.is_subset(&failures),
            _ => agent_passed = Some(agent_passed.unwrap_or(true) && failures.is_empty()),
        }
        results.push(json!({"id":id,"role":control["role"],"failedCheckIds":failures,"checks":reconstructed,"stdoutSha256":execution["stdoutSha256"]}));
    }
    let calibrated = baseline_matches && accepted_pass && wrong_discriminate;
    let next_action = if !baseline_matches {
        "review-task-baseline"
    } else if !accepted_pass {
        "repair-valid-controls"
    } else if !wrong_discriminate {
        "repair-oracle-or-wrong-controls"
    } else {
        match agent_passed {
            None => "execute-agent-attempt",
            Some(false) => "repair-agent-behavior",
            Some(true) => "review-agent-outcome",
        }
    };
    Ok(
        json!({"schema":"agentlab.behavior_check_feedback.v1","contractSha256":digest(contract_bytes),"captureSha256":digest(capture_bytes),"candidateId":contract["candidateId"],"candidateSha256":contract["candidateSha256"],"sourceRevision":contract["sourceRevision"],"controls":results,"calibrationRecordedContentPassed":calibrated,"nextAction":next_action,"producerAuthenticated":false,"executionReplayed":false,"qualified":false,"automaticPromotion":false,"authorityWritePerformed":false}),
    )
}
