use agentlab_code_analysis::{digest, maintainer_downstream::plan};
use serde_json::{json, Value};
use std::{fs, path::PathBuf, process::Command};

fn fixture(candidate: &str) -> Value {
    json!({"schema":"agentlab.shadow_case_construction_readiness_receipt.v1",
        "candidateId":candidate,"candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),
        "sourceSetSha256":"c".repeat(64),"knowledgeCutSha256":"d".repeat(64),
        "currentKnowledgeCutSha256":"e".repeat(64),"planSha256":"f".repeat(64),
        "automaticPromotion":false,"decision":"blocked-qualification","nextGate":"implement-and-calibrate-independent-oracle",
        "knowledgeBlockers":[],"qualificationBlockers":["oracle missing","runtime missing","variants missing"],
        "checks":{"oracleExecution":{"status":"unqualified","evidence":[]},
            "wrongVariantCalibration":{"status":"unqualified","evidence":[],"requiredCount":2,"executedCount":0},
            "runtimeRequirements":[{"id":"exact-platform-test","description":"An arbitrary pinned target; never substitute a different API.","status":"unqualified","evidence":[]}]}})
}
fn route(r: &Value) -> Value {
    plan(&serde_json::to_vec(r).unwrap(), None).unwrap()
}
fn kinds(p: &Value) -> Vec<&str> {
    p["actions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|a| a["kind"].as_str().unwrap())
        .collect()
}

#[test]
fn qualification_routes_to_oracle_variants_and_exact_runtime_not_more_semantics() {
    let p = route(&fixture("arbitrary-first-repo"));
    assert_eq!(
        kinds(&p),
        [
            "implement-and-calibrate-oracle",
            "calibrate-wrong-variants",
            "qualify-exact-runtime-requirement"
        ]
    );
    assert_eq!(p["actions"][1]["dependsOn"][0], p["actions"][0]["id"]);
    assert_eq!(p["actions"][1]["readyForScheduling"], false);
    assert_eq!(p["actions"][2]["requirement"]["id"], "exact-platform-test");
    assert_eq!(p["agentExecutionPerformed"], false);
}

#[test]
fn knowledge_blockers_precede_expensive_downstream_work() {
    let mut r = fixture("arbitrary-first-repo");
    r["knowledgeBlockers"] = json!(["missing exact Oracle Blob"]);
    r["decision"] = json!("blocked-knowledge-refresh");
    let p = route(&r);
    assert_eq!(kinds(&p), ["focused-knowledge-refresh"]);
}

#[test]
fn calibrated_oracle_skips_repeated_oracle_work_but_not_runtime() {
    let mut r = fixture("arbitrary-second-repo");
    for key in ["oracleExecution", "wrongVariantCalibration"] {
        r["checks"][key]["status"] = json!("qualified");
        r["checks"][key]["evidence"] = json!([{"path":"verified.json","sha256":"a".repeat(64)}]);
    }
    r["checks"]["wrongVariantCalibration"]["executedCount"] = json!(2);
    r["qualificationBlockers"] = json!(["runtime missing"]);
    let p = route(&r);
    assert_eq!(kinds(&p), ["qualify-exact-runtime-requirement"]);
    // This is a repository-independent protocol control, not real cross-repo execution.
    r["candidateId"] = json!("renamed-repo");
    assert_eq!(route(&r)["actions"], p["actions"]);
}

#[test]
fn ready_construction_is_not_assessed_agent_dispatch() {
    let mut r = fixture("ready-fixture");
    for key in ["oracleExecution", "wrongVariantCalibration"] {
        r["checks"][key]["status"] = json!("qualified");
        r["checks"][key]["evidence"] = json!([{"path":"verified.json"}]);
    }
    r["checks"]["wrongVariantCalibration"]["executedCount"] = json!(2);
    r["checks"]["runtimeRequirements"][0]["status"] = json!("qualified");
    r["checks"]["runtimeRequirements"][0]["evidence"] = json!([{"path":"verified.json"}]);
    r["qualificationBlockers"] = json!([]);
    r["decision"] = json!("ready-for-construction");
    r["nextGate"] = json!("maintainer-knowledge-gate-construction");
    let p = route(&r);
    assert_eq!(kinds(&p), ["construct-and-freeze-operational-case"]);
    assert_eq!(p["actions"][0]["executionAuthorized"], false);
}

#[test]
fn identical_evidence_stops_loop_and_changed_receipt_replans() {
    let r = fixture("unchanged");
    let raw = serde_json::to_vec(&r).unwrap();
    let first = plan(&raw, None).unwrap();
    let second = plan(&raw, Some(&serde_json::to_vec(&first).unwrap())).unwrap();
    assert_eq!(second["status"], "awaiting-new-evidence");
    assert_eq!(second["schedulingAllowed"], false);
    assert_eq!(second["readinessSha256"], digest(&raw));
    assert_eq!(second["actions"], first["actions"]);
    let mut changed = r.clone();
    changed["currentKnowledgeCutSha256"] = json!("0".repeat(64));
    assert_eq!(
        plan(
            &serde_json::to_vec(&changed).unwrap(),
            Some(&serde_json::to_vec(&second).unwrap())
        )
        .unwrap()["schedulingAllowed"],
        false
    );
    changed["planSha256"] = json!("1".repeat(64));
    assert_eq!(
        plan(
            &serde_json::to_vec(&changed).unwrap(),
            Some(&serde_json::to_vec(&second).unwrap())
        )
        .unwrap()["schedulingAllowed"],
        true
    );
    assert_eq!(
        plan(
            &serde_json::to_vec_pretty(&r).unwrap(),
            Some(&serde_json::to_vec(&first).unwrap())
        )
        .unwrap()["schedulingAllowed"],
        false
    );
}

#[test]
fn contradictory_malformed_borrowed_and_tampered_inputs_fail_closed() {
    let r = fixture("original");
    for (field, value) in [
        ("automaticPromotion", json!(true)),
        ("decision", json!("ready-for-construction")),
        ("sourceRevision", json!("latest")),
        ("candidateSha256", json!("not-a-digest")),
        ("qualificationBlockers", json!([])),
    ] {
        let mut broken = r.clone();
        broken[field] = value;
        assert!(plan(&serde_json::to_vec(&broken).unwrap(), None).is_err());
    }
    let mut previous = route(&r);
    previous["candidateId"] = json!("borrowed");
    assert!(plan(
        &serde_json::to_vec(&r).unwrap(),
        Some(&serde_json::to_vec(&previous).unwrap())
    )
    .is_err());
    previous = route(&r);
    previous["actions"][0]["kind"] = json!("execute-agent-now");
    assert!(plan(
        &serde_json::to_vec(&r).unwrap(),
        Some(&serde_json::to_vec(&previous).unwrap())
    )
    .is_err());
}

#[test]
fn actual_first_four_assessor_to_rust_controller_and_repeated_batch() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let out = std::env::temp_dir().join(format!(
        "agentlab-downstream-regression-{}",
        std::process::id()
    ));
    fs::create_dir(&out).unwrap();
    let run = |name: &str, previous: Option<&str>| {
        let mut command = Command::new("bash");
        command
            .current_dir(&root)
            .arg("scripts/plan-maintainer-downstream.sh")
            .arg("examples/maintainer-knowledge-gate/first-four")
            .arg(".")
            .arg(out.join(name))
            .env(
                "AGENTLAB_FLYWHEEL_BIN",
                env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"),
            );
        if let Some(p) = previous {
            command.arg(out.join(p));
        }
        let captured = command.output().unwrap();
        assert!(
            captured.status.success(),
            "{}",
            String::from_utf8_lossy(&captured.stderr)
        );
        serde_json::from_slice::<Value>(&fs::read(out.join(name).join("summary.json")).unwrap())
            .unwrap()
    };
    let first = run("first", None);
    assert_eq!(first["planCount"], 3);
    assert_eq!(
        first["missingConstructionPlanCandidateIds"]
            .as_array()
            .unwrap()
            .len(),
        7
    );
    assert_eq!(first["schedulingAllowedPlanCount"], 2);
    assert_eq!(
        first["retainedHistoricalCandidateIds"],
        json!(["shadow-case-abilitystage-environment-callback-binding"])
    );
    let second = run("repeat", Some("first"));
    assert_eq!(second["schedulingAllowedPlanCount"], 0);
    assert_eq!(second["agentExecutionPerformed"], false);
    fs::remove_dir_all(out).unwrap();
}

#[test]
fn batch_rejects_parent_drift_instead_of_suppressing_unverified_history() {
    let parent = json!({"id":"parent"});
    let child = json!({"id":"child","lineage":{"parentCandidateId":"parent","parentCandidateSha256":"a".repeat(64)}});
    let rows = format!("{}\n{}\n", parent, child);
    assert!(
        agentlab_code_analysis::maintainer_downstream::batch(rows.as_bytes(), b"[]")
            .unwrap_err()
            .contains("parent digest differs")
    );
}
