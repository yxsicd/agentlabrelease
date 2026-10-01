use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn legacy_shadow_adapter_rejects_empty_borrowed_and_nondiscriminating_receipts() {
    let root = std::env::temp_dir().join(format!(
        "agentlab-shadow-content-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    let adapter = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples/maintainer-knowledge-gate/shadow_construction_readiness.py");
    let candidate = json!({"id":"arbitrary-case", "sourceRevision":"1".repeat(40),
        "sourceSetSha256":"2".repeat(64), "knowledgeCutSha256":"3".repeat(64),
        "oracleHypothesis":{"observables":["state"], "wrongVariants":["lost-state", "wrong-boundary"]}});
    let mut receipt = json!({"schema":"agentlab.shadow_case_qualification.v1", "kind":"wrong-variant-calibration",
    "status":"qualified", "automaticPromotion":false, "candidateId":"arbitrary-case",
    "sourceRevision":candidate["sourceRevision"], "sourceSetSha256":candidate["sourceSetSha256"],
    "knowledgeCutSha256":candidate["knowledgeCutSha256"],
    "execution":{"status":"completed", "exitCode":0, "durationMs":1},
    "checks":[{"id":"calibration-run", "passed":true}],
    "variants":[
        {"id":"reference", "role":"accepted", "completed":true, "expectedVerdict":"accept", "observedVerdict":"accept", "checks":[{"id":"state", "observable":"state", "passed":true}]},
        {"id":"lost-state", "role":"wrong", "completed":true, "expectedVerdict":"reject", "observedVerdict":"reject", "checks":[{"id":"state", "observable":"state", "passed":false}]},
        {"id":"wrong-boundary", "role":"wrong", "completed":true, "expectedVerdict":"reject", "observedVerdict":"reject", "checks":[{"id":"state", "observable":"state", "passed":false}]}
    ]});
    let invoke = |value: &Value| {
        let bytes = serde_json::to_vec(value).unwrap();
        fs::write(root.join("receipt.json"), &bytes).unwrap();
        let payload = json!({"candidate":candidate, "receipt":value,
            "qualification":{"status":"qualified", "executedCount":2, "evidence":[{"path":"receipt.json", "sha256":digest(&bytes)}]}});
        let mut child = Command::new("python3").args(["-c", 
            "import importlib.util,json,sys\nfrom pathlib import Path\ns=importlib.util.spec_from_file_location('gate',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\np=json.load(sys.stdin)\nm.validate_qualification(Path(sys.argv[2]),p['qualification'],'calibration',p['candidate'],'wrong-variant-calibration')",
            adapter.to_str().unwrap(), root.to_str().unwrap()]).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(&serde_json::to_vec(&payload).unwrap())
            .unwrap();
        child.wait_with_output().unwrap()
    };
    // Use the adapter's canonical JSON digest, not Rust serialization ordering.
    let output = Command::new("python3").args(["-c", "import json,hashlib,sys;print(hashlib.sha256(json.dumps(json.loads(sys.argv[1]),ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()).hexdigest())", &candidate.to_string()]).output().unwrap();
    assert!(output.status.success());
    receipt["candidateSha256"] = json!(String::from_utf8(output.stdout).unwrap().trim());
    let positive = invoke(&receipt);
    assert!(
        positive.status.success(),
        "{}",
        String::from_utf8_lossy(&positive.stderr)
    );
    assert!(!invoke(&json!({})).status.success());
    for (pointer, value) in [
        ("/candidateId", json!("borrowed")),
        ("/candidateSha256", json!("0".repeat(64))),
        ("/sourceRevision", json!("9".repeat(40))),
        ("/execution/exitCode", json!(1)),
        ("/execution/status", json!("timeout")),
        ("/checks/0/passed", json!(false)),
        ("/variants/0/checks/0/passed", json!(false)),
        ("/variants/1/completed", json!(false)),
        ("/variants/1/checks/0/passed", json!(true)),
        ("/variants/1/id", json!("undeclared")),
        ("/variants/1/checks/0/observable", json!("unrelated")),
        ("/variants/2/id", json!("lost-state")),
        ("/variants/2/observedVerdict", json!("accept")),
    ] {
        let mut bad = receipt.clone();
        *bad.pointer_mut(pointer).unwrap() = value;
        assert!(!invoke(&bad).status.success(), "{pointer}");
    }
    fs::remove_dir_all(root).unwrap();
}
