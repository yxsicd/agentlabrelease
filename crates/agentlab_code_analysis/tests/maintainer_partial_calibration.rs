use agentlab_code_analysis::{digest, maintainer_downstream, maintainer_partial_calibration::plan};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};
static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn readiness() -> Value {
    json!({"schema":"agentlab.shadow_case_construction_readiness_receipt.v1",
      "candidateId":"arbitrary-repository-task","candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),
      "sourceSetSha256":"c".repeat(64),"knowledgeCutSha256":"d".repeat(64),"currentKnowledgeCutSha256":"e".repeat(64),"planSha256":"f".repeat(64),
      "automaticPromotion":false,"decision":"blocked-qualification","nextGate":"implement-and-calibrate-independent-oracle",
      "knowledgeBlockers":[],"qualificationBlockers":["missing oracle","missing variants","missing runtime"],
      "checks":{"oracleExecution":{"status":"unqualified","evidence":[]},
        "wrongVariantCalibration":{"status":"unqualified","evidence":[],"requiredCount":2,"executedCount":0},
        "runtimeRequirements":[{"id":"exact-platform","description":"Exact API 22; never substitute API 26","status":"unqualified","evidence":[]}]}})
}
fn fixture(pointer: bool) -> (PathBuf, Value, Value) {
    let root = std::env::temp_dir().join(format!(
        "agentlab-partial-{}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let mut observations = Vec::new();
    for (i, (text, state)) in [("good", "ready"), ("wrong", "ready"), ("good", "broken")]
        .iter()
        .enumerate()
    {
        let raw = if pointer {
            json!({"result":{"text":text,"state":state}})
        } else {
            json!({"attributes":{},"children":[{"attributes":{"application":"arbitrary-app","page":"arbitrary-page"},"children":[
              {"attributes":{"id":"text","value":text},"children":[]},{"attributes":{"id":"state","value":state},"children":[]}]}]})
        };
        let content = serde_json::to_string(&raw).unwrap();
        let envelope = json!({"ok":true,"routeDecision":"peer_direct","targetPeerId":"arbitrary-peer",
            "result":{"ok":true,"content":content,"size":content.len()}});
        let bytes = serde_json::to_vec(&envelope).unwrap();
        let file = format!("control-{i}.json");
        fs::write(root.join(&file), &bytes).unwrap();
        observations.push(json!({"phase":"after","path":file,"envelopeSha256":digest(&bytes),"rawSha256":digest(content.as_bytes()),"byteLength":content.len()}));
    }
    let selector = |id: &str| {
        if pointer {
            json!({"adapter":"json-pointer","pointer":format!("/result/{id}")})
        } else {
            json!({"adapter":"attribute-tree","owner":{"application":"arbitrary-app","page":"arbitrary-page"},"node":{"id":id},"field":"value"})
        }
    };
    let profile = json!({"schema":"agentlab.partial_calibration_profile.v1","reviewed":true,
      "candidateId":"arbitrary-repository-task","candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),"constructionPlanSha256":"f".repeat(64),
      "targetPeerId":"arbitrary-peer","runtimeIdentity":{"runtime":"API 26","architecture":"arbitrary"},
      "phases":[{"id":"after","checks":[{"id":"text","selector":selector("text"),"expected":"good"},{"id":"state","selector":selector("state"),"expected":"ready"}]}],
      "controls":[{"id":"reference","role":"accepted","expectedFailedCheckIds":[],"observations":[observations[0]]},
        {"id":"wrong-text","role":"wrong","expectedFailedCheckIds":["after/text"],"observations":[observations[1]]},
        {"id":"wrong-state","role":"wrong","expectedFailedCheckIds":["after/state"],"observations":[observations[2]]}],
      "remainingControls":[{"id":"normal-exit","description":"Complete the missing normal-exit control under the declared partial runtime"}]});
    (root, readiness(), profile)
}
fn run(root: &PathBuf, r: &Value, p: &Value, previous: Option<&Value>) -> Result<Value, String> {
    plan(
        &serde_json::to_vec(r).unwrap(),
        &serde_json::to_vec(p).unwrap(),
        root,
        previous.map(|x| serde_json::to_vec(x).unwrap()).as_deref(),
    )
}

#[test]
fn both_adapters_reconstruct_scoped_controls_without_qualifying_formal_runtime() {
    for pointer in [false, true] {
        let (root, r, p) = fixture(pointer);
        let result = run(&root, &r, &p, None).unwrap();
        assert_eq!(result["scopedControlsConsistent"], true);
        assert_eq!(result["acceptedObservationControlCount"], 1);
        assert_eq!(result["rejectedObservationControlCount"], 2);
        assert_eq!(result["scopedActions"][0]["id"], "normal-exit");
        let formal = maintainer_downstream::plan(&serde_json::to_vec(&r).unwrap(), None).unwrap();
        assert_eq!(result["formalGateActions"], formal["actions"]);
        for flag in [
            "qualified",
            "automaticPromotion",
            "agentExecutionPerformed",
            "authorityWritePerformed",
            "producerAuthenticated",
            "implementationMutationVerified",
            "runtimeIdentityAttested",
        ] {
            assert_eq!(result[flag], false);
        }
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn unchanged_observations_suppress_repetition_but_runtime_and_selectors_replan() {
    let (root, r, mut p) = fixture(false);
    let first = run(&root, &r, &p, None).unwrap();
    assert_eq!(
        run(&root, &r, &p, Some(&first)).unwrap()["schedulingAllowed"],
        false
    );
    let mut advanced = r.clone();
    advanced["currentKnowledgeCutSha256"] = json!("0".repeat(64));
    assert_eq!(
        run(&root, &advanced, &p, Some(&first)).unwrap()["schedulingAllowed"],
        false
    );
    // Transport timings/envelope bytes may change, not the original observation.
    let file = root.join("control-0.json");
    let mut envelope: Value = serde_json::from_slice(&fs::read(&file).unwrap()).unwrap();
    envelope["timings"] = json!({"durationMs":99});
    let bytes = serde_json::to_vec(&envelope).unwrap();
    fs::write(file, &bytes).unwrap();
    p["controls"][0]["observations"][0]["envelopeSha256"] = json!(digest(&bytes));
    assert_eq!(
        run(&root, &r, &p, Some(&first)).unwrap()["schedulingAllowed"],
        false
    );
    p["runtimeIdentity"]["architecture"] = json!("changed");
    assert_eq!(
        run(&root, &r, &p, Some(&first)).unwrap()["schedulingAllowed"],
        true
    );
    p["runtimeIdentity"]["architecture"] = json!("arbitrary");
    p["phases"][0]["checks"][0]["selector"]["node"]["value"] = json!("good");
    // Altered selectors that do not find wrong controls are an error, not a kill.
    assert!(run(&root, &r, &p, Some(&first)).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn contradictions_route_control_repair_and_knowledge_gaps_precede_it() {
    let (root, mut r, mut p) = fixture(true);
    p["controls"][1]["expectedFailedCheckIds"] = json!(["after/state"]);
    let result = run(&root, &r, &p, None).unwrap();
    assert_eq!(result["scopedControlsConsistent"], false);
    assert_eq!(
        result["scopedActions"][0]["kind"],
        "repair-scoped-observation-calibration"
    );
    r["decision"] = json!("blocked-knowledge-refresh");
    r["knowledgeBlockers"] = json!(["source evidence missing"]);
    assert_eq!(
        run(&root, &r, &p, None).unwrap()["scopedActions"][0]["kind"],
        "focused-knowledge-refresh"
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_borrowing_unsafe_paths_unsupported_formats_and_duplicate_controls() {
    let (root, r, p) = fixture(false);
    for (key, value) in [
        ("reviewed", json!(false)),
        ("candidateId", json!("borrowed")),
        ("sourceRevision", json!("0".repeat(40))),
        ("constructionPlanSha256", json!("0".repeat(64))),
        ("schema", json!("unknown")),
        ("unknown", json!(true)),
    ] {
        let mut bad = p.clone();
        bad[key] = value;
        assert!(run(&root, &r, &bad, None).is_err(), "{key}");
    }
    let mut bad = p.clone();
    bad["controls"][1]["observations"] = bad["controls"][0]["observations"].clone();
    assert!(run(&root, &r, &bad, None)
        .unwrap_err()
        .contains("duplicate control capture"));
    let mut bad = p.clone();
    bad["controls"][0]["observations"][0]["path"] = json!("../escape");
    assert!(run(&root, &r, &bad, None).is_err());
    let mut bad = p.clone();
    bad["phases"][0]["checks"][0]["selector"]["adapter"] = json!("execute-command");
    assert!(run(&root, &r, &bad, None).is_err());
    let mut previous = run(&root, &r, &p, None).unwrap();
    previous["scopedActions"][0]["kind"] = json!("execute-agent-now");
    assert!(run(&root, &r, &p, Some(&previous)).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejected_capture_digest_wrong_peer_and_ambiguous_nodes_are_not_negative_success() {
    let (root, r, mut p) = fixture(false);
    let file = root.join("control-0.json");
    let original = fs::read(&file).unwrap();
    let mut bytes = original.clone();
    bytes.push(b' ');
    fs::write(&file, &bytes).unwrap();
    assert!(run(&root, &r, &p, None)
        .unwrap_err()
        .contains("envelope digest"));
    let mut envelope: Value = serde_json::from_slice(&original).unwrap();
    envelope["targetPeerId"] = json!("another-peer");
    let bytes = serde_json::to_vec(&envelope).unwrap();
    fs::write(&file, &bytes).unwrap();
    p["controls"][0]["observations"][0]["envelopeSha256"] = json!(digest(&bytes));
    assert!(run(&root, &r, &p, None)
        .unwrap_err()
        .contains("capture target"));
    let mut envelope: Value = serde_json::from_slice(&original).unwrap();
    let mut raw: Value =
        serde_json::from_str(envelope["result"]["content"].as_str().unwrap()).unwrap();
    let duplicate = raw["children"][0]["children"][0].clone();
    raw["children"][0]["children"]
        .as_array_mut()
        .unwrap()
        .push(duplicate);
    let content = serde_json::to_string(&raw).unwrap();
    envelope["result"]["content"] = json!(content);
    envelope["result"]["size"] = json!(content.len());
    let bytes = serde_json::to_vec(&envelope).unwrap();
    fs::write(file, &bytes).unwrap();
    p["controls"][0]["observations"][0]["envelopeSha256"] = json!(digest(&bytes));
    p["controls"][0]["observations"][0]["rawSha256"] = json!(digest(content.as_bytes()));
    p["controls"][0]["observations"][0]["byteLength"] = json!(content.len());
    assert!(run(&root, &r, &p, None)
        .unwrap_err()
        .contains("observable absent or ambiguous"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn a_single_retained_positive_control_is_progress_not_a_complete_calibration() {
    let (root, r, mut p) = fixture(true);
    p["controls"].as_array_mut().unwrap().truncate(1);
    let result = run(&root, &r, &p, None).unwrap();
    assert_eq!(result["scopedControlsConsistent"], true);
    assert_eq!(result["rejectedObservationControlCount"], 0);
    assert!(result["scopedActions"]
        .as_array()
        .unwrap()
        .iter()
        .any(|a| a["kind"] == "complete-scoped-wrong-controls" && a["requiredCount"] == 2));
    assert_eq!(result["qualified"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn actual_downstream_wrapper_consumes_opt_in_profiles_and_suppresses_unchanged_work() {
    let (root, _r, mut p) = fixture(false);
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let invoke = |name: &str, profile: bool, previous: Option<&str>| {
        let mut cmd = std::process::Command::new("bash");
        cmd.current_dir(&repo)
            .arg("scripts/plan-maintainer-downstream.sh")
            .arg("examples/maintainer-knowledge-gate/first-four")
            .arg(".")
            .arg(root.join(name))
            .env_remove("AGENTLAB_PARTIAL_CALIBRATION_ROOT")
            .env(
                "AGENTLAB_FLYWHEEL_BIN",
                env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"),
            );
        if profile {
            cmd.env("AGENTLAB_PARTIAL_CALIBRATION_ROOT", &root);
        }
        if let Some(previous) = previous {
            cmd.arg(root.join(previous));
        }
        let result = cmd.output().unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    };
    invoke("baseline", false, None);
    let id = "shadow-case-uiability-backup-restore-state-recovery";
    let readiness: Value = serde_json::from_slice(
        &fs::read(root.join("baseline").join(id).join("readiness.json")).unwrap(),
    )
    .unwrap();
    for (key, rkey) in [
        ("candidateId", "candidateId"),
        ("candidateSha256", "candidateSha256"),
        ("sourceRevision", "sourceRevision"),
        ("constructionPlanSha256", "planSha256"),
    ] {
        p[key] = readiness[rkey].clone();
    }
    fs::create_dir(root.join("profiles")).unwrap();
    fs::write(
        root.join("profiles").join(format!("{id}.json")),
        serde_json::to_vec(&p).unwrap(),
    )
    .unwrap();
    invoke("first", true, None);
    invoke("second", true, Some("first"));
    let read = |name: &str| {
        serde_json::from_slice::<Value>(
            &fs::read(root.join(name).join(id).join("scoped-next-actions.json")).unwrap(),
        )
        .unwrap()
    };
    let first = read("first");
    let second = read("second");
    assert_eq!(first["schedulingAllowed"], true);
    assert_eq!(second["schedulingAllowed"], false);
    assert_eq!(first["formalGateActions"], second["formalGateActions"]);
    assert_eq!(second["qualified"], false);
    assert_eq!(second["scopedControlsConsistent"], true);
    let summary = |name: &str| {
        serde_json::from_slice::<Value>(
            &fs::read(root.join(name).join("partial-summary.json")).unwrap(),
        )
        .unwrap()
    };
    assert_eq!(summary("first")["activeCandidateIds"], json!([id]));
    assert_eq!(summary("second")["activeCandidateIds"], json!([]));
    fs::remove_dir_all(root).unwrap();
}
