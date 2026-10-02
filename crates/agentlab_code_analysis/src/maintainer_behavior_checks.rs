//! Generic recorded behavior comparison. No repository, framework or predicate
//! is selected by this consumer. It does not authenticate or execute producers.
use crate::digest;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// Explicit reviewed interpretation of reconstructed behavior controls, not admission or learning.
pub fn lesson_assets(
    candidate_bytes: &[u8],
    contract_bytes: &[u8],
    capture_bytes: &[u8],
    review_bytes: &[u8],
) -> Result<BTreeMap<String, BTreeMap<String, Value>>, String> {
    require(
        candidate_bytes.len() <= 256 * 1024 && review_bytes.len() <= 128 * 1024,
        "behavior lesson input budget exceeded",
    )?;
    let feedback = verify(contract_bytes, capture_bytes)?;
    let candidate: Value = serde_json::from_slice(candidate_bytes).map_err(|e| e.to_string())?;
    let contract: Value = serde_json::from_slice(contract_bytes).map_err(|e| e.to_string())?;
    let review: Value = serde_json::from_slice(review_bytes).map_err(|e| e.to_string())?;
    require(
        candidate["id"] == contract["candidateId"]
            && candidate["sourceRevision"] == contract["sourceRevision"]
            && digest(&serde_json::to_vec(&candidate).map_err(|e| e.to_string())?)
                == contract["candidateSha256"],
        "behavior lesson candidate binding differs",
    )?;
    let repository = text(&candidate, "repositoryId")?;
    require(
        review["schema"] == "agentlab.behavior_lesson_review.v1"
            && review["reviewed"] == true
            && review["automaticPromotion"] == false
            && feedback["calibrationRecordedContentPassed"] == true,
        "behavior lesson requires reviewed calibrated evidence",
    )?;
    for (key, actual) in [
        ("candidateSha256", feedback["candidateSha256"].clone()),
        ("sourceRevision", feedback["sourceRevision"].clone()),
        ("contractSha256", json!(digest(contract_bytes))),
        ("captureSha256", json!(digest(capture_bytes))),
    ] {
        require(
            review[key] == actual,
            "behavior lesson review binding differs",
        )?;
    }
    for key in [
        "id",
        "scope",
        "reviewerId",
        "phenomenon",
        "cause",
        "change",
        "factId",
        "skillId",
        "body",
    ] {
        require(
            !text(&review, key)?.trim().is_empty(),
            "behavior lesson review text empty",
        )?;
    }
    require(
        review["factId"] != review["skillId"],
        "behavior lesson target identities collide",
    )?;
    require(
        review["skillStage"] == "calibration" || review["skillStage"] == "evaluation",
        "behavior lesson stage unsupported",
    )?;
    let controls = feedback["controls"].as_array().unwrap();
    require(
        controls
            .iter()
            .filter(|c| {
                c["role"] == "accepted" && c["failedCheckIds"].as_array().unwrap().is_empty()
            })
            .count()
            >= 2
            && controls
                .iter()
                .filter(|c| {
                    c["role"] == "wrong" && !c["failedCheckIds"].as_array().unwrap().is_empty()
                })
                .count()
                >= 2,
        "behavior lesson requires two accepted and two rejected controls",
    )?;
    let consumer = digest(include_bytes!("maintainer_behavior_checks.rs"));
    let run = format!(
        "behavior-{}",
        digest(
            &serde_json::to_vec(&json!([
                feedback["candidateSha256"],
                digest(contract_bytes),
                digest(capture_bytes),
                consumer
            ]))
            .map_err(|e| e.to_string())?
        )
    );
    let evidence = format!("{run}-lesson-{}", digest(review_bytes));
    let validation = format!("{evidence}-validation");
    let qualification = json!({"boundary":"independently reconstructed recorded behavior checks","harmonyBuildQualified":false,
        "harmonyRuntimeQualified":false,"uiQualified":false,"caseQualified":false,"producerAuthenticated":false,"learningBenefitVerified":false});
    let mut expected = serde_json::Map::new();
    for control in controls.iter().filter(|c| c["role"] != "agent-attempt") {
        expected.insert(
            text(control, "id")?.into(),
            json!(control["failedCheckIds"].as_array().unwrap().is_empty()),
        );
    }
    let promotion = json!({"id":review["id"],"scope":review["scope"],"phenomenon":review["phenomenon"],"cause":review["cause"],
        "change":review["change"],"factId":review["factId"],"skillId":review["skillId"],"body":review["body"],
        "skillStage":review["skillStage"],"expected":expected,"qualification":qualification});
    let mut tables: BTreeMap<String, BTreeMap<String, Value>> = BTreeMap::new();
    let mut put = |table: &str, mut row: Value| {
        row["assetClass"] = json!("evaluation-instance");
        row["runId"] = json!(run);
        tables
            .entry(table.into())
            .or_default()
            .insert(row["id"].as_str().unwrap().into(), row);
    };
    put(
        "runs",
        json!({"id":run,"kind":"recorded-behavior-calibration","candidateId":candidate["id"],"repositoryId":repository,
        "sourceRevision":candidate["sourceRevision"],"contractSha256":digest(contract_bytes),"captureSha256":digest(capture_bytes),
        "calibrationRecordedContentPassed":true,"qualified":false,"automaticPromotion":false}),
    );
    put(
        "analysis_records",
        json!({"id":format!("{run}-feedback"),"kind":"raw-behavior-reconstruction","consumerSourceSha256":consumer,
        "code":"maintainer_behavior_checks::verify","inputSha256":digest(capture_bytes),"result":feedback}),
    );
    let mut control_ids = Vec::new();
    let mut attempt_ids = Vec::new();
    for control in controls {
        let is_attempt = control["role"] == "agent-attempt";
        let id = format!(
            "{run}-{}-{}",
            if is_attempt { "attempt" } else { "control" },
            digest(text(control, "id")?.as_bytes())
        );
        if is_attempt {
            attempt_ids.push(id.clone());
            let declaration = contract["controls"]
                .as_array()
                .unwrap()
                .iter()
                .find(|row| row["id"] == control["id"])
                .unwrap();
            put(
                "attempts",
                json!({"id":id,"kind":"recorded-behavior-attempt","variant":control["id"],
                "candidateId":candidate["id"],"repositoryId":repository,"sourceRevision":candidate["sourceRevision"],
                "submittedSourceSha256":declaration["submittedSourceSha256"],
                "behaviorPassed":control["failedCheckIds"].as_array().unwrap().is_empty(),
                "failedCheckIds":control["failedCheckIds"],"capturePath":"behavior-capture.json",
                "captureSha256":digest(capture_bytes),"contractSha256":digest(contract_bytes),
                "stdoutSha256":control["stdoutSha256"],"participantCompletionVerified":false,
                "producerAuthenticated":false,"qualified":false}),
            );
        } else {
            control_ids.push(id.clone());
            put(
                "calibration_controls",
                json!({"id":id,"variant":control["id"],"role":control["role"],"completed":true,
            "observedVerdict":if control["failedCheckIds"].as_array().unwrap().is_empty(){"accept"}else{"reject"},
            "capturePath":"behavior-capture.json","captureSha256":digest(capture_bytes),"stdoutSha256":control["stdoutSha256"]}),
            );
        }
        for check in control["checks"].as_array().unwrap() {
            put(
                "checks",
                json!({"id":format!("{id}-check-{}",digest(text(check,"id")?.as_bytes())),
                "controlId":if is_attempt {Value::Null}else{json!(id)},
                "attemptId":if is_attempt {json!(id)}else{Value::Null},
                "variant":control["id"],"check":check["id"],"passed":check["passed"],"capturePath":"behavior-capture.json",
                "captureSha256":digest(capture_bytes),"authority":"independently-reconstructed-frozen-check"}),
            );
        }
    }
    put(
        "experiment_lessons",
        json!({"id":review["id"],"kind":"calibrated-method-lesson","status":"verified","scope":review["scope"],
        "phenomenon":review["phenomenon"],"cause":review["cause"],"change":review["change"],"repositoryId":repository,
        "sourceRevision":candidate["sourceRevision"],"analysisId":format!("{run}-feedback"),"evidenceIds":[evidence],
        "validationIds":[validation],"targetIds":[review["factId"],review["skillId"]],"promotionContract":promotion,
        "attribution":"explicit-reviewed-interpretation-of-reconstructed-controls","reviewerId":review["reviewerId"],
        "reviewSha256":digest(review_bytes),"automaticPromotion":false,"qualified":false}),
    );
    put(
        "lesson_evidence",
        json!({"id":evidence,"lessonId":review["id"],"kind":"reconstructed-behavior-controls",
        "capturePath":"behavior-capture.json","captureSha256":digest(capture_bytes),"reviewPath":"lesson-review.json",
        "reviewSha256":digest(review_bytes),"controlIds":control_ids,"attemptIds":attempt_ids}),
    );
    put(
        "lesson_validations",
        json!({"id":validation,"lessonId":review["id"],"kind":"positive-negative-calibration","passed":true,
        "scope":review["scope"],"evidenceId":evidence,"expected":expected,"qualification":qualification,"reviewSha256":digest(review_bytes)}),
    );
    for (name, bytes) in [
        ("candidate.json", candidate_bytes),
        ("behavior-contract.json", contract_bytes),
        ("behavior-capture.json", capture_bytes),
        ("lesson-review.json", review_bytes),
    ] {
        put(
            "evidence_files",
            json!({"id":format!("{run}-file-{}-{}",digest(name.as_bytes()),digest(bytes)),"path":name,"sha256":digest(bytes),"bytes":bytes.len()}),
        );
    }
    Ok(tables)
}

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
            role == "agent-attempt"
                || source_digests.insert(text(control, "submittedSourceSha256")?),
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
