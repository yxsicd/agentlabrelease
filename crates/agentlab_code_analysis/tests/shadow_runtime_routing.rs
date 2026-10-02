use serde_json::{json, Value};
use std::{
    io::Write,
    process::{Command, Stdio},
};

#[test]
fn shadow_runtime_policy_is_explicit_generic_and_cannot_downgrade_ohostest() {
    let adapter = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples/maintainer-knowledge-gate/case_generation_shadow.py");
    let request = json!({"schema":"agentlab.case_generation_shadow_request.v1",
        "candidateId":"shadow-case-arbitrary-behavior",
        "sourceSetSha256":"1".repeat(64),"knowledgeCutSha256":"2".repeat(64),
        "maintainerSkillRefreshRoundId":"arbitrary-round", "loopReceiptSha256":"3".repeat(64),
        "scope":{"id":"arbitrary-scope", "pathBoundary":"lib", "testEntrypoints":["tests/contract.rs"]},
        "fact":{"id":"arbitrary-fact", "repositoryId":"unfamiliar-repository", "sourceRevision":"4".repeat(40),
            "scopeSkillIds":["arbitrary-scope"], "evidence":[{"path":"lib/state.rs"}]},
        "policy":{"runtimeTarget":"repository-test", "externalHardwareAllowed":false, "physicalDeviceFallbackAllowed":false}});
    let proposal = json!({"schema":"agentlab.shadow_case_candidate.v1", "id":request["candidateId"],
        "repositoryId":request["fact"]["repositoryId"], "sourceRevision":request["fact"]["sourceRevision"],
        "scopeSkillIds":["arbitrary-scope"],"factIds":["arbitrary-fact"],
        "title":"Preserve a bounded state contract", "mechanism":"Preserve the owned state across two staged changes and reject lost-state or wrong-boundary shortcuts through observable repository tests.",
        "stagedDemands":["Retain pending state", "Retain pending state across a later retry"],
        "editablePaths":["lib/state.rs"], "contextPaths":[],
        "oracleHypothesis":{"framework":"repository-test", "status":"hypothesis-unqualified",
            "observables":["pending state remains", "retry result is correct"],
            "requiredEnvironment":["pinned Rust repository test runner in an isolated Linux container"],
            "wrongVariants":["discard pending state", "reset retry too early"]},
        "limitations":["Oracle is not yet executed", "Wrong variants are not yet calibrated"],
        "status":"shadow-proposal", "automaticPromotion":false});
    let invoke = |request: &Value, proposal: &Value| {
        let mut child = Command::new("python3").args(["-c",
            "import importlib.util,json,sys\ns=importlib.util.spec_from_file_location('gate',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\np=json.load(sys.stdin);print(json.dumps(m.validate_proposal(p['request'],p['proposal'])))",
            adapter.to_str().unwrap()]).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(
                &serde_json::to_vec(&json!({"request":request,"proposal":proposal})).unwrap(),
            )
            .unwrap();
        child.wait_with_output().unwrap()
    };
    let valid = invoke(&request, &proposal);
    assert!(
        valid.status.success(),
        "{}",
        String::from_utf8_lossy(&valid.stderr)
    );
    let candidate: Value = serde_json::from_slice(&valid.stdout).unwrap();
    assert_eq!(candidate["lineage"]["runtimeTarget"], "repository-test");
    assert_eq!(
        candidate["lineage"]["shadowRequestValueSha256"]
            .as_str()
            .unwrap()
            .len(),
        64
    );
    for (pointer, value) in [
        ("/policy/runtimeTarget", json!("unknown-runtime")),
        ("/policy/externalHardwareAllowed", json!(true)),
        ("/policy/physicalDeviceFallbackAllowed", json!(true)),
    ] {
        let mut bad = request.clone();
        *bad.pointer_mut(pointer).unwrap() = value;
        assert!(!invoke(&bad, &proposal).status.success(), "{pointer}");
    }
    let mut external = proposal.clone();
    external["oracleHypothesis"]["requiredEnvironment"] =
        json!(["USB attached external hardware is required"]);
    assert!(!invoke(&request, &external).status.success());
    let mut harmony = request.clone();
    harmony["scope"]["testEntrypoints"] = json!(["entry/src/ohosTest/Test.ets"]);
    let mut harmony_proposal = proposal.clone();
    harmony_proposal["oracleHypothesis"]["framework"] = json!("ohosTest");
    assert!(!invoke(&harmony, &harmony_proposal).status.success());
    harmony["policy"]["runtimeTarget"] = json!("harmony-emulator");
    assert!(!invoke(&harmony, &harmony_proposal).status.success());
    harmony_proposal["oracleHypothesis"]["requiredEnvironment"] =
        json!(["pinned HarmonyOS emulator image"]);
    assert!(invoke(&harmony, &harmony_proposal).status.success());
}
