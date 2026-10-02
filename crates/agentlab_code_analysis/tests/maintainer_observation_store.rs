use agentlab_code_analysis::{
    digest,
    maintainer_behavior_checks::export_observation,
    maintainer_observation_store::{plan, verify},
};
use serde_json::{json, Value};
use std::{fs, path::PathBuf};
fn bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).unwrap()
}
fn fixture() -> (PathBuf, Value, Value) {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "observation-store-{}-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let candidate = json!({"id":"independent-task","repositoryId":"replaceable-target","sourceRevision":"b".repeat(40)});
    let mut contract = json!({"schema":"agentlab.frozen_behavior_checks.v1","candidateId":candidate["id"],"candidateSha256":digest(&bytes(&candidate)),"sourceRevision":candidate["sourceRevision"],"originalSourceSha256":digest(b"baseline"),"methodSha256":"c".repeat(64),"compilerSha256":"d".repeat(64),"runtime":"fixture-only","workerDeadlineMs":1000,"automaticPromotion":false,"checks":[{"id":"outcome","input":null,"expected":true}],"controls":[]});
    let mut controls = Vec::new();
    let mut workers = Vec::new();
    for (id, role, actual) in [
        ("baseline", "baseline", false),
        ("valid-a", "accepted", true),
        ("valid-b", "accepted", true),
        ("wrong-a", "wrong", false),
        ("wrong-b", "wrong", false),
        ("attempt", "agent-attempt", false),
    ] {
        controls.push(json!({"id":id,"role":role,"submittedSourceSha256":digest(id.as_bytes()),"expectedFailedCheckIds":if role=="baseline"||role=="wrong" {vec!["outcome"]} else {vec![]}}));
        let stdout=serde_json::to_string(&json!({"id":id,"submittedSource":id,"submittedSourceSha256":digest(id.as_bytes()),"originalSourceSha256":digest(b"baseline"),"observations":[{"id":"outcome","input":null,"actual":actual}]})).unwrap();
        workers.push(json!({"id":id,"execution":{"stdoutSha256":digest(stdout.as_bytes()),"stdout":stdout,"exitCode":0,"timedOut":false,"durationMs":1}}));
    }
    contract["controls"] = json!(controls);
    let capture = json!({"schema":"agentlab.behavior_worker_capture.v1","contractSha256":digest(&bytes(&contract)),"candidateId":contract["candidateId"],"candidateSha256":contract["candidateSha256"],"sourceRevision":contract["sourceRevision"],"methodSha256":contract["methodSha256"],"compilerSha256":contract["compilerSha256"],"runtime":contract["runtime"],"workers":workers});
    let manifest = export_observation(
        &bytes(&candidate),
        &bytes(&contract),
        &bytes(&capture),
        &root,
    )
    .unwrap();
    let mut tables = serde_json::Map::new();
    for name in manifest["tables"].as_object().unwrap().keys() {
        tables.insert(
            name.clone(),
            json!({"revision":"a".repeat(40),"dirty":false,"truncated":false,"rows":[]}),
        );
    }
    tables.get_mut("runs").unwrap()["rows"] =
        json!([{"key":"older-run","row":{"id":"older-run","unchanged":"foreign producer"}}]);
    let remote = json!({"schema":"agentlab.observation_store_snapshot.v1","repository":"operational-store","revision":"a".repeat(40),"tablePrefix":"data/","tables":tables});
    let destination = json!({"schema":"agentlab.observation_store_destination.v1","reviewed":true,"automaticPromotion":false,"repository":"operational-store","knowledgeRepository":"independent-knowledge","expectedRevision":"a".repeat(40),"tablePrefix":"data/","transactionId":"a1122026-1003-4a11-8811-221190128101"});
    (root, remote, destination)
}
fn committed(plan: &Value, revision: &str) -> Value {
    let mut tables = serde_json::Map::new();
    for (name, rows) in plan["expectedTables"].as_object().unwrap() {
        tables.insert(name.clone(),json!({"revision":revision,"dirty":false,"truncated":false,
            "rows":rows.as_object().unwrap().iter().map(|(key,row)|json!({"key":key,"row":row})).collect::<Vec<_>>()}));
    }
    json!({"schema":"agentlab.observation_store_snapshot.v1","repository":plan["destination"]["repository"],"revision":revision,"tablePrefix":plan["destination"]["tablePrefix"],"tables":tables})
}
#[test]
fn exact_insert_readback_preserves_old_rows_and_reimport_has_no_transaction() {
    let (root, remote, destination) = fixture();
    let planned = plan(&root, &bytes(&remote), &bytes(&destination)).unwrap();
    assert_eq!(
        planned,
        plan(&root, &bytes(&remote), &bytes(&destination)).unwrap()
    );
    assert_eq!(
        planned["transaction"]["tables"].as_array().unwrap().len(),
        6
    );
    let receipt = json!({"repo":"operational-store","revision":"e".repeat(40),"previous_revision":"a".repeat(40),"outcome":"applied","conflicts":[]});
    let after = committed(&planned, &"e".repeat(40));
    let result = verify(
        &root,
        &bytes(&planned),
        &bytes(&receipt),
        &bytes(&after),
        &bytes(&remote),
    )
    .unwrap();
    assert_eq!(result["allRowsExact"], true);
    assert_eq!(result["qualified"], false);
    let mut next = destination.clone();
    next["expectedRevision"] = receipt["revision"].clone();
    let repeated = plan(&root, &bytes(&after), &bytes(&next)).unwrap();
    assert!(repeated["transaction"].is_null());
    assert_eq!(repeated["insertedRows"], 0);
    let unchanged = json!({"revision":receipt["revision"],"conflicts":[]});
    assert_eq!(
        verify(
            &root,
            &bytes(&repeated),
            &bytes(&unchanged),
            &bytes(&after),
            &bytes(&after)
        )
        .unwrap()["noChange"],
        true
    );
    fs::remove_dir_all(root).unwrap();
}
#[test]
fn dirty_truncated_alias_destinations_and_conflicting_rows_are_rejected() {
    let (root, remote, destination) = fixture();
    for key in ["dirty", "truncated"] {
        let mut changed = remote.clone();
        changed["tables"]["checks"][key] = json!(true);
        assert!(plan(&root, &bytes(&changed), &bytes(&destination)).is_err());
    }
    let mut alias = destination.clone();
    alias["knowledgeRepository"] = alias["repository"].clone();
    assert!(plan(&root, &bytes(&remote), &bytes(&alias)).is_err());
    let planned = plan(&root, &bytes(&remote), &bytes(&destination)).unwrap();
    let mut conflict = committed(&planned, &"a".repeat(40));
    conflict["tables"]["attempts"]["rows"][0]["row"]["behaviorPassed"] = json!(true);
    assert!(plan(&root, &bytes(&conflict), &bytes(&destination))
        .unwrap_err()
        .contains("overwrite forbidden"));
    fs::remove_dir_all(root).unwrap();
}
#[test]
fn missing_old_rows_wrong_receipts_and_altered_plans_never_verify() {
    let (root, remote, destination) = fixture();
    let planned = plan(&root, &bytes(&remote), &bytes(&destination)).unwrap();
    let receipt = json!({"repo":"operational-store","revision":"e".repeat(40),"previous_revision":"a".repeat(40),"outcome":"applied","conflicts":[]});
    let mut after = committed(&planned, &"e".repeat(40));
    after["tables"]["runs"]["rows"]
        .as_array_mut()
        .unwrap()
        .retain(|r| r["key"] != "older-run");
    assert!(verify(
        &root,
        &bytes(&planned),
        &bytes(&receipt),
        &bytes(&after),
        &bytes(&remote)
    )
    .is_err());
    let mut forged = planned.clone();
    forged["expectedTables"]["runs"]
        .as_object_mut()
        .unwrap()
        .remove("older-run");
    assert!(verify(
        &root,
        &bytes(&forged),
        &bytes(&receipt),
        &bytes(&after),
        &bytes(&remote)
    )
    .unwrap_err()
    .contains("baseline reconstruction"));
    let mut wrong = receipt.clone();
    wrong["repo"] = json!("another-repository");
    assert!(verify(
        &root,
        &bytes(&planned),
        &bytes(&wrong),
        &bytes(&committed(&planned, &"e".repeat(40))),
        &bytes(&remote)
    )
    .is_err());
    fs::write(root.join("checks.jsonl"), b"{}\n").unwrap();
    assert!(plan(&root, &bytes(&remote), &bytes(&destination)).is_err());
    fs::remove_dir_all(root).unwrap();
}
