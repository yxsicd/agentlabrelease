#![cfg(unix)]
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn git(root: &Path, args: &[&str]) -> String {
    let r = Command::new("git")
        .current_dir(root)
        .args(args)
        .output()
        .unwrap();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    String::from_utf8(r.stdout).unwrap().trim().into()
}
fn run(root: &Path, contract: &Value, label: &str) -> (bool, Value) {
    let input = root.join(format!("{label}.contract.json"));
    let output = root.join(format!("{label}.result.json"));
    fs::write(&input, serde_json::to_vec(contract).unwrap()).unwrap();
    let r = Command::new("node")
        .arg(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../scripts/calibrate-harmony-stage-controls.cjs"),
        )
        .arg("--contract")
        .arg(input)
        .arg("--source-repo")
        .arg(root)
        .arg("--output")
        .arg(&output)
        .output()
        .unwrap();
    let result = fs::read(&output)
        .ok()
        .map(|b| serde_json::from_slice(&b).unwrap())
        .unwrap_or(Value::Null);
    (r.status.success(), result)
}
#[test]
fn actual_stage_methods_discriminate_semantic_mutations_without_repository_constants() {
    for repository in ["arbitrary-owner-one", "different-owner-two"] {
        let root = std::env::temp_dir().join(format!(
            "{repository}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(root.join("src/owner")).unwrap();
        fs::write(
            root.join("src/module.json5"),
            r#"{"module":{"srcEntry":"./owner/Owner.js"}}"#,
        )
        .unwrap();
        let code = r#"const {AbilityStage}=require('@kit.AbilityKit');exports.default=class Owner extends AbilityStage {
          onCreate(){console.info('created');let envCallback={onConfigurationUpdated(config){console.info('config: '+JSON.stringify(config));}};
          let app=this.context.getApplicationContext();let id=app.on('environment', envCallback);console.info('id: '+id);}
          onDestroy(){console.info('destroyed');}}
        "#;
        fs::write(root.join("src/owner/Owner.js"), code).unwrap();
        fs::write(root.join("src/owner/Alternate.js"), "const {AbilityStage}=require('@kit.AbilityKit');exports.default=class Alternate extends AbilityStage {};").unwrap();
        git(&root, &["init"]);
        git(&root, &["config", "user.name", "Fixture"]);
        git(&root, &["config", "user.email", "fixture@example.invalid"]);
        git(&root, &["add", "src"]);
        git(&root, &["commit", "-m", "stage fixture"]);
        let mut c = json!({"schema":"agentlab.harmony_stage_control_contract.v1","reviewed":true,
            "sourceRevision":git(&root,&["rev-parse","HEAD"]),"modulePath":"src/module.json5",
            "createMarker":"created","destroyMarker":"destroyed","registrationMarker":"id: ","configurationPrefix":"config: ","eventName":"environment",
            "configurations":[{"id":"initial","language":"en-US","colorMode":0},{"id":"language","language":"zh-CN","colorMode":0},{"id":"color","language":"zh-CN","colorMode":1}],
            "variants":[{"id":"entry","path":"src/module.json5","from":"./owner/Owner.js","to":"./owner/Alternate.js","expectedFailedChecks":["stage-created","language","color"]},
                {"id":"event","path":"src/owner/Owner.js","from":".on('environment', envCallback)","to":".on('typo', envCallback)","expectedFailedChecks":["application-environment-registration","language","color"]}]});
        let candidate = json!({"id":repository,"sourceRevision":c["sourceRevision"],
            "contextPaths":["src/module.json5"],"editablePaths":["src/owner/Owner.js"],
            "sourceSetSha256":"a".repeat(64),"knowledgeCutSha256":"b".repeat(64)});
        let candidate_sha =
            agentlab_code_analysis::digest(&serde_json::to_vec(&candidate).unwrap());
        c["candidateId"] = candidate["id"].clone();
        c["candidateSha256"] = json!(candidate_sha);
        let downstream = json!({"schema":"agentlab.maintainer_downstream_plan.v1","candidateId":repository,
            "candidateSha256":candidate_sha,"sourceRevision":candidate["sourceRevision"],"automaticPromotion":false,
            "sourceSetSha256":candidate["sourceSetSha256"],"knowledgeCutSha256":candidate["knowledgeCutSha256"],
            "actions":[{"id":"exact-runtime","kind":"qualify-exact-runtime-requirement","executionAuthorized":false}]});
        let consume = |contract: &Value, receipt: &Value, previous: Option<&[u8]>| {
            let bytes = serde_json::to_vec(receipt).unwrap();
            agentlab_code_analysis::maintainer_stage_feedback::plan(
                &serde_json::to_vec(&candidate).unwrap(),
                &serde_json::to_vec(&downstream).unwrap(),
                &serde_json::to_vec(contract).unwrap(),
                &bytes,
                &agentlab_code_analysis::digest(&bytes),
                previous,
            )
        };
        let (ok, r) = run(&root, &c, "actual");
        assert!(ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], true);
        assert_eq!(r["qualified"], false);
        assert_eq!(r["controls"][0]["verdict"], "accept");
        for control in r["controls"].as_array().unwrap().iter().skip(1) {
            assert_eq!(control["verdict"], "reject");
            assert_eq!(control["intendedFailureObserved"], true);
        }
        let first = consume(&c, &r, None).unwrap();
        assert_eq!(
            first["nextAction"],
            "review-and-admit-scoped-domain-calibration"
        );
        assert_eq!(first["killedSemanticVariantCount"], 2);
        assert_eq!(first["pendingFormalActions"], downstream["actions"]);
        let repeat = consume(&c, &r, Some(&serde_json::to_vec(&first).unwrap())).unwrap();
        assert_eq!(repeat["schedulingAllowed"], false);
        // Recorded runtime identity participates in scheduling even with equal checks.
        let mut runtime_changed = r.clone();
        runtime_changed["runtime"] = json!("v1.2.3");
        let replan = consume(
            &c,
            &runtime_changed,
            Some(&serde_json::to_vec(&first).unwrap()),
        )
        .unwrap();
        assert_eq!(replan["schedulingAllowed"], true);
        assert_ne!(replan["taskSha256"], first["taskSha256"]);
        let mut runtime_missing = r.clone();
        runtime_missing.as_object_mut().unwrap().remove("runtime");
        assert!(consume(&c, &runtime_missing, None)
            .unwrap_err()
            .contains("runtime absent"));
        let (ok, fresh) = run(&root, &c, "fresh");
        assert!(ok);
        let resume = |previous: &Value, capture: &Value| {
            let current = serde_json::to_vec(&fresh).unwrap();
            let prior = serde_json::to_vec(capture).unwrap();
            agentlab_code_analysis::maintainer_stage_feedback::resume(
                &serde_json::to_vec(&candidate).unwrap(),
                &serde_json::to_vec(&downstream).unwrap(),
                &serde_json::to_vec(&c).unwrap(),
                &current,
                &agentlab_code_analysis::digest(&current),
                &serde_json::to_vec(previous).unwrap(),
                &prior,
                &agentlab_code_analysis::digest(&prior),
            )
        };
        let resumed = resume(&first, &r).unwrap();
        assert_eq!(resumed["previousCaptureReconstructed"], true);
        assert_eq!(resumed["schedulingAllowed"], false);
        assert_eq!(resumed["pendingFormalActions"], downstream["actions"]);
        assert_eq!(resumed["qualified"], false);
        // History owns semantic scheduling, not today's formal requirement queue.
        let mut current_downstream = downstream.clone();
        current_downstream["actions"].as_array_mut().unwrap().push(json!({
            "id":"new-formal-demand","kind":"qualify-independent-oracle","executionAuthorized":false
        }));
        let fresh_bytes = serde_json::to_vec(&fresh).unwrap();
        let prior_bytes = serde_json::to_vec(&r).unwrap();
        let current_plan = agentlab_code_analysis::maintainer_stage_feedback::resume(
            &serde_json::to_vec(&candidate).unwrap(),
            &serde_json::to_vec(&current_downstream).unwrap(),
            &serde_json::to_vec(&c).unwrap(),
            &fresh_bytes,
            &agentlab_code_analysis::digest(&fresh_bytes),
            &serde_json::to_vec(&first).unwrap(),
            &prior_bytes,
            &agentlab_code_analysis::digest(&prior_bytes),
        )
        .unwrap();
        assert_eq!(
            current_plan["pendingFormalActions"],
            current_downstream["actions"]
        );
        assert_eq!(current_plan["schedulingAllowed"], false);
        let mut fabricated_plan = first.clone();
        fabricated_plan["taskSha256"] = json!("d".repeat(64));
        assert!(resume(&fabricated_plan, &r)
            .unwrap_err()
            .contains("contradicts retained capture"));
        let mut historical_plan = first.clone();
        historical_plan.as_object_mut().unwrap().remove("runtime");
        assert!(resume(&historical_plan, &r).is_err());
        let mut tampered = r.clone();
        tampered["controls"][1]["checks"][0]["passed"] = json!(true);
        let mut body = tampered["controls"][1].as_object().unwrap().clone();
        body.remove("workerExecution");
        let raw = serde_json::to_string(&Value::Object(body)).unwrap();
        tampered["controls"][1]["workerExecution"]["stdout"] = json!(raw);
        tampered["controls"][1]["workerExecution"]["stdoutSha256"] =
            json!(agentlab_code_analysis::digest(raw.as_bytes()));
        assert!(consume(&c, &tampered, None)
            .unwrap_err()
            .contains("raw observations"));
        assert!(resume(&first, &tampered)
            .unwrap_err()
            .contains("raw observations"));
        let mut missing = r.clone();
        missing["controls"].as_array_mut().unwrap().pop();
        assert!(consume(&c, &missing, None).is_err());
        let mut duplicate = r.clone();
        let extra = duplicate["controls"][1].clone();
        duplicate["controls"].as_array_mut().unwrap().push(extra);
        assert!(consume(&c, &duplicate, None).is_err());
        let mut borrowed = c.clone();
        borrowed["candidateSha256"] = json!("c".repeat(64));
        assert!(consume(&borrowed, &r, None).is_err());
        // Renaming an internal class while retaining its default export is not a semantic defect.
        let mut cosmetic = c.clone();
        cosmetic["variants"][1]["from"] = json!("class Owner");
        cosmetic["variants"][1]["to"] = json!("class Renamed");
        let (ok, r) = run(&root, &cosmetic, "cosmetic");
        assert!(ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        assert_eq!(r["controls"][2]["verdict"], "accept");
        assert_eq!(
            consume(&cosmetic, &r, None).unwrap()["nextAction"],
            "repair-domain-oracle-or-controls"
        );
        // Missing loader support is infrastructure failure, not a killed implementation.
        let mut unsupported = c.clone();
        unsupported["variants"][1]["from"] = json!("require('@kit.AbilityKit')");
        unsupported["variants"][1]["to"] = json!("require('unsupported-platform')");
        let (ok, r) = run(&root, &unsupported, "unsupported");
        assert!(!ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        assert_eq!(r["infrastructureFailure"]["id"], "event");
        assert_eq!(
            consume(&unsupported, &r, None).unwrap()["nextAction"],
            "repair-domain-calibration-environment"
        );
        let mut ambiguous = c.clone();
        ambiguous["variants"][1]["from"] = json!("not-in-source");
        let (ok, r) = run(&root, &ambiguous, "absent");
        assert!(!ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        let mut confounded = c.clone();
        confounded["configurations"][1]["colorMode"] = json!(1);
        let (ok, r) = run(&root, &confounded, "confounded");
        assert!(!ok);
        assert!(r.is_null());
        assert!(git(&root, &["diff", "--name-only", "HEAD", "--", "src"]).is_empty());
        fs::remove_dir_all(root).unwrap();
    }
}
