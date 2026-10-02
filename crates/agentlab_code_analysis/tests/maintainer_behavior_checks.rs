use agentlab_code_analysis::{digest, maintainer_behavior_checks::verify};
use serde_json::{json, Value};

fn fixture() -> (Value, Value) {
    let mut contract = json!({"schema":"agentlab.frozen_behavior_checks.v1","candidateId":"generic-task","candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),"originalSourceSha256":digest(b"baseline"),"methodSha256":"c".repeat(64),"compilerSha256":"d".repeat(64),"runtime":"test-runtime","workerDeadlineMs":1000,"checks":[{"id":"preserve","input":{"response":false},"expected":[1,"retained"]},{"id":"success","input":null,"expected":{"cleared":true}}],"controls":[],"automaticPromotion":false});
    let mut workers = Vec::new();
    let mut controls = Vec::new();
    for (id, role, failure) in [
        ("baseline", "baseline", Some("preserve")),
        ("valid-a", "accepted", None),
        ("valid-b", "accepted", None),
        ("wrong-a", "wrong", Some("preserve")),
        ("wrong-b", "wrong", Some("success")),
    ] {
        controls.push(json!({"id":id,"role":role,"submittedSourceSha256":digest(id.as_bytes()),"expectedFailedCheckIds":failure.map(|id| vec![id]).unwrap_or_default()}));
        let raw = json!({"id":id,"submittedSource":id,"submittedSourceSha256":digest(id.as_bytes()),"originalSourceSha256":digest(b"baseline"),"observations":contract["checks"].as_array().unwrap().iter().map(|check|json!({"id":check["id"],"input":check["input"],"actual":if failure==check["id"].as_str() {json!("wrong")} else {check["expected"].clone()},"expected":"producer cannot override contract","passed":true})).collect::<Vec<_>>()});
        let stdout = serde_json::to_string(&raw).unwrap();
        workers.push(json!({"id":id,"execution":{"stdoutSha256":digest(stdout.as_bytes()),"stdout":stdout,"exitCode":0,"timedOut":false,"durationMs":10}}));
    }
    contract["controls"] = json!(controls);
    let capture = json!({"schema":"agentlab.behavior_worker_capture.v1","contractSha256":digest(&serde_json::to_vec(&contract).unwrap()),"candidateId":contract["candidateId"],"candidateSha256":contract["candidateSha256"],"sourceRevision":contract["sourceRevision"],"methodSha256":contract["methodSha256"],"compilerSha256":contract["compilerSha256"],"runtime":contract["runtime"],"workers":workers});
    (contract, capture)
}
fn check(contract: &Value, capture: &Value) -> Result<Value, String> {
    verify(
        &serde_json::to_vec(contract).unwrap(),
        &serde_json::to_vec(capture).unwrap(),
    )
}
fn modify(capture: &mut Value, worker: usize, edit: impl FnOnce(&mut Value)) {
    let execution = &mut capture["workers"][worker]["execution"];
    let mut raw: Value = serde_json::from_str(execution["stdout"].as_str().unwrap()).unwrap();
    edit(&mut raw);
    let stdout = serde_json::to_string(&raw).unwrap();
    execution["stdoutSha256"] = json!(digest(stdout.as_bytes()));
    execution["stdout"] = json!(stdout);
}

#[test]
fn reconstructs_mixed_json_checks_without_trusting_producer_boolean_or_expected() {
    let (contract, capture) = fixture();
    let feedback = check(&contract, &capture).unwrap();
    assert_eq!(feedback["nextAction"], "execute-agent-attempt");
    assert_eq!(
        feedback["controls"][0]["failedCheckIds"],
        json!(["preserve"])
    );
    assert_eq!(feedback["qualified"], false);
    assert_eq!(feedback["producerAuthenticated"], false);
}

#[test]
fn distinguishes_valid_control_and_surviving_wrong_control_failures() {
    let (contract, mut capture) = fixture();
    modify(&mut capture, 1, |raw| {
        raw["observations"][0]["actual"] = json!(false)
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-valid-controls"
    );
    let (_, mut capture) = fixture();
    modify(&mut capture, 3, |raw| {
        raw["observations"][0]["actual"] = json!([1, "retained"])
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-oracle-or-wrong-controls"
    );
}

#[test]
fn infrastructure_or_incomplete_capture_never_counts_as_behavior_failure() {
    for scenario in [
        "exit",
        "timeout",
        "deadline",
        "stdout",
        "missing",
        "duplicate",
        "input",
        "source",
    ] {
        let (contract, mut capture) = fixture();
        match scenario {
            "exit" => capture["workers"][3]["execution"]["exitCode"] = json!(1),
            "timeout" => capture["workers"][3]["execution"]["timedOut"] = json!(true),
            "deadline" => capture["workers"][3]["execution"]["durationMs"] = json!(1001),
            "stdout" => capture["workers"][3]["execution"]["stdoutSha256"] = json!("0".repeat(64)),
            "missing" => modify(&mut capture, 3, |raw| {
                raw["observations"].as_array_mut().unwrap().pop();
            }),
            "duplicate" => modify(&mut capture, 3, |raw| {
                raw["observations"][1] = raw["observations"][0].clone();
            }),
            "input" => modify(&mut capture, 3, |raw| {
                raw["observations"][1]
                    .as_object_mut()
                    .unwrap()
                    .remove("input");
            }),
            _ => modify(&mut capture, 3, |raw| {
                raw["submittedSource"] = json!("swapped source")
            }),
        }
        assert!(check(&contract, &capture).is_err(), "{scenario}");
    }
}

#[test]
fn rejects_changed_contract_identity_and_duplicate_valid_sources() {
    let (mut contract, capture) = fixture();
    contract["checks"][0]["expected"] = json!("new expected after execution");
    assert!(check(&contract, &capture).is_err());
    let (contract, mut capture) = fixture();
    capture["runtime"] = json!("other-runtime");
    assert!(check(&contract, &capture).is_err());
    let (mut contract, mut capture) = fixture();
    contract["controls"][2]["submittedSourceSha256"] =
        contract["controls"][1]["submittedSourceSha256"].clone();
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&contract).unwrap()));
    assert!(check(&contract, &capture).is_err());
}

#[test]
fn agent_outcomes_retain_every_frozen_check_and_select_behavioral_repair() {
    let (mut contract, mut capture) = fixture();
    contract["controls"].as_array_mut().unwrap().push(json!({"id":"agent","role":"agent-attempt","submittedSourceSha256":digest(b"agent subject"),"expectedFailedCheckIds":[]}));
    let mut worker = capture["workers"][1].clone();
    worker["id"] = json!("agent");
    capture["workers"].as_array_mut().unwrap().push(worker);
    modify(&mut capture, 5, |raw| {
        raw["id"] = json!("agent");
        raw["submittedSource"] = json!("agent subject");
        raw["submittedSourceSha256"] = json!(digest(b"agent subject"));
    });
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&contract).unwrap()));
    let success = check(&contract, &capture).unwrap();
    assert_eq!(success["nextAction"], "review-agent-outcome");
    assert_eq!(success["qualified"], false);
    modify(&mut capture, 5, |raw| {
        raw["observations"][1]["actual"] = json!({"cleared":false})
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-agent-behavior"
    );
    modify(&mut capture, 5, |raw| {
        raw["observations"].as_array_mut().unwrap().pop();
    });
    assert!(check(&contract, &capture).is_err());
}

#[cfg(unix)]
fn loop_fixture(failing_executor: bool, repeat: bool) -> (Vec<u8>, Vec<u8>, Vec<u8>) {
    let (contract, capture) = fixture();
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    let capture_bytes = serde_json::to_vec(&capture).unwrap();
    let command = |script: String| json!({"program":"/bin/sh","programSha256":digest(&std::fs::read("/bin/sh").unwrap()),"args":["-c",script,"adapter","{request}"],"cwd":".","timeoutMs":1000});
    let raw = |number: usize, source: &str, failed: bool| {
        serde_json::to_string(&json!({"id":format!("agent-attempt-{number}"),"submittedSource":source,"submittedSourceSha256":digest(source.as_bytes()),"originalSourceSha256":contract["originalSourceSha256"],"observations":contract["checks"].as_array().unwrap().iter().map(|c| json!({"id":c["id"],"input":c["input"],"actual":if failed && c["id"]=="preserve" {json!("wrong")} else {c["expected"].clone()}})).collect::<Vec<_>>()})).unwrap()
    };
    let participant = if repeat {
        "printf '%s' '{\"submittedSource\":\"bad subject\"}'".into()
    } else {
        "case \"$1\" in *attempt-0*) printf '%s' '{\"submittedSource\":\"bad subject\"}';; *) printf '%s' '{\"submittedSource\":\"valid-a\"}';; esac".into()
    };
    let executor = if failing_executor {
        "exit 9".into()
    } else {
        format!(
            "case \"$1\" in *attempt-0*) printf '%s' '{}';; *) printf '%s' '{}';; esac",
            raw(0, "bad subject", true),
            raw(1, "valid-a", false)
        )
    };
    let recipe = json!({"schema":"agentlab.behavior_loop_recipe.v1","reviewed":true,"automaticPromotion":false,"contractSha256":digest(&contract_bytes),"captureSha256":digest(&capture_bytes),"taskDemand":"Preserve data on failure and clear on success.","maximumAttempts":2,"immutableInputs":[],"participantCommand":command(participant),"executorCommand":command(executor)});
    (
        contract_bytes,
        capture_bytes,
        serde_json::to_vec(&recipe).unwrap(),
    )
}

#[cfg(unix)]
fn loop_output(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "agentlab-behavior-loop-{label}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[test]
#[cfg(unix)]
fn real_subprocess_loop_delivers_failed_feedback_then_rechecks_repaired_subject() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let out = loop_output("repair");
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out,
    )
    .unwrap();
    assert_eq!(result["status"], "recorded-attempt-passed");
    assert_eq!(result["attempts"].as_array().unwrap().len(), 2);
    assert_eq!(result["attempts"][0]["nextAction"], "repair-agent-behavior");
    let repair: Value = serde_json::from_slice(
        &std::fs::read(out.join("attempt-1/participant-request.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(repair["submittedSource"], "bad subject");
    assert_eq!(repair["feedback"]["nextAction"], "repair-agent-behavior");
    assert_eq!(
        result["latestFeedback"]["nextAction"],
        "review-agent-outcome"
    );
    assert_eq!(result["participantAuthenticated"], false);
    assert_eq!(result["qualified"], false);
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out
    )
    .is_err());
}

#[test]
#[cfg(unix)]
fn loop_stops_infrastructure_and_suppresses_identical_failed_subject() {
    let (contract, capture, recipe) = loop_fixture(true, false);
    let out = loop_output("infrastructure");
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out
    )
    .unwrap_err()
    .contains("infrastructure"));
    assert!(!out.join("attempt-1").exists());
    assert!(out.join("attempt-0/executor.json").is_file());
    let (contract, capture, recipe) = loop_fixture(false, true);
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &recipe,
        &loop_output("repeat"),
    )
    .unwrap();
    assert_eq!(result["status"], "unchanged-attempt-suppressed");
    assert_eq!(result["attempts"].as_array().unwrap().len(), 1);
}

#[test]
#[cfg(unix)]
fn participant_cannot_rewrite_frozen_checks_before_executor_dispatch() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    recipe["participantCommand"]["args"][1] = json!(
        "printf corrupt > ../frozen-contract.json; printf '%s' '{\"submittedSource\":\"valid-a\"}'"
    );
    let out = loop_output("tamper");
    let error = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap_err();
    assert!(error.contains("immutable input changed"));
    assert!(out.join("attempt-0/participant.json").is_file());
    assert!(!out.join("attempt-0/executor.json").exists());
}
