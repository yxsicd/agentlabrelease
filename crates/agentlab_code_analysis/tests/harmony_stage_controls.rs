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
        let c = json!({"schema":"agentlab.harmony_stage_control_contract.v1","reviewed":true,
            "sourceRevision":git(&root,&["rev-parse","HEAD"]),"modulePath":"src/module.json5",
            "createMarker":"created","destroyMarker":"destroyed","registrationMarker":"id: ","configurationPrefix":"config: ","eventName":"environment",
            "configurations":[{"id":"initial","language":"en-US","colorMode":0},{"id":"language","language":"zh-CN","colorMode":0},{"id":"color","language":"zh-CN","colorMode":1}],
            "variants":[{"id":"entry","path":"src/module.json5","from":"./owner/Owner.js","to":"./owner/Alternate.js","expectedFailedChecks":["stage-created","language","color"]},
                {"id":"event","path":"src/owner/Owner.js","from":".on('environment', envCallback)","to":".on('typo', envCallback)","expectedFailedChecks":["application-environment-registration","language","color"]}]});
        let (ok, r) = run(&root, &c, "actual");
        assert!(ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], true);
        assert_eq!(r["qualified"], false);
        assert_eq!(r["controls"][0]["verdict"], "accept");
        for control in r["controls"].as_array().unwrap().iter().skip(1) {
            assert_eq!(control["verdict"], "reject");
            assert_eq!(control["intendedFailureObserved"], true);
        }
        // Renaming an internal class while retaining its default export is not a semantic defect.
        let mut cosmetic = c.clone();
        cosmetic["variants"][1]["from"] = json!("class Owner");
        cosmetic["variants"][1]["to"] = json!("class Renamed");
        let (ok, r) = run(&root, &cosmetic, "cosmetic");
        assert!(ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        assert_eq!(r["controls"][2]["verdict"], "accept");
        // Missing loader support is infrastructure failure, not a killed implementation.
        let mut unsupported = c.clone();
        unsupported["variants"][1]["from"] = json!("require('@kit.AbilityKit')");
        unsupported["variants"][1]["to"] = json!("require('unsupported-platform')");
        let (ok, r) = run(&root, &unsupported, "unsupported");
        assert!(!ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        assert_eq!(r["infrastructureFailure"]["id"], "event");
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
