use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn retained_diagnostic_is_byte_bound_and_never_runtime_qualification() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let receipts =
        root.join("examples/maintainer-knowledge-gate/first-four/qualification-receipts");
    let finding: Value = serde_json::from_slice(
        &fs::read(receipts.join("abilitystage-oracle-finding.json")).unwrap(),
    )
    .unwrap();
    let bytes = fs::read(receipts.join(finding["probe"]["path"].as_str().unwrap())).unwrap();
    assert_eq!(
        finding["probe"]["sha256"],
        format!("{:x}", Sha256::digest(&bytes))
    );
    let probe: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(
        probe["methodSha256"],
        format!(
            "{:x}",
            Sha256::digest(
                fs::read(root.join("scripts/probe-hypium-failure-controls.cjs")).unwrap()
            )
        )
    );
    assert_eq!(probe["source"]["revision"], finding["sourceRevision"]);
    assert_eq!(probe["decision"], finding["decision"]);
    assert_eq!(probe["failureSensitive"], false);
    for control in probe["controls"].as_array().unwrap() {
        assert_eq!(control["source"], probe["source"]);
        assert_eq!(control["verdict"], "accept");
        assert_eq!(control["startCalls"], 1);
        assert_eq!(control["doneCalls"], 1);
    }
    assert_eq!(finding["historicalCandidateRewritten"], false);
    assert_eq!(finding["knowledgeAuthorityWritten"], false);
    assert_eq!(finding["qualified"], false);
    assert_eq!(probe["qualified"], false);
}

#[test]
fn failure_controls_reject_vacuous_success_and_preserve_infrastructure_failure() {
    let root = std::env::temp_dir().join(format!(
        "hypium-controls-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&root).unwrap();
    let git = |args: &[&str]| {
        let output = Command::new("git")
            .arg("-C")
            .arg(&root)
            .args(args)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8(output.stdout).unwrap().trim().to_owned()
    };
    git(&["init"]);
    git(&["config", "user.name", "Fixture"]);
    git(&["config", "user.email", "fixture@example.invalid"]);
    let prefix = "const {describe,it}=require('@ohos/hypium');const {default:registry}=require('@ohos.app.ability.abilityDelegatorRegistry');exports.suite=()=>describe('arbitrary',()=>";
    for (name, body) in [
        ("vacuous", "it('probe',0,async(done)=>{try{await registry.getAbilityDelegator().startAbility({});done();}catch(e){done();}})"),
        ("sensitive", "it('probe',0,async()=>{await registry.getAbilityDelegator().startAbility({});})"),
        ("unsupported", "it('probe',0,async()=>{await registry.getAbilityDelegator().startAbility({});require('unmodeled-platform');})"),
        ("ambiguous", "it('probe',0,async()=>{});it('probe',0,async()=>{})"),
    ] {
        let closure = if name == "ambiguous" {format!("{{{body}}}")} else {body.into()};
        fs::write(root.join(format!("{name}.js")), format!("{prefix}{closure});")).unwrap();
    }
    git(&["add", "."]);
    git(&["commit", "-m", "arbitrary source controls"]);
    let revision = git(&["rev-parse", "HEAD"]);
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/probe-hypium-failure-controls.cjs");
    for (name, success, expected) in [
        ("vacuous", true, "repair-oracle-before-runtime-calibration"),
        ("sensitive", true, "continue-runtime-calibration"),
        ("unsupported", false, "probe-infrastructure-failed"),
        ("ambiguous", false, "probe-infrastructure-failed"),
    ] {
        let output = root.join(format!("{name}.json"));
        let run = || {
            Command::new("node")
                .arg(&script)
                .args([
                    "--source-repo",
                    root.to_str().unwrap(),
                    "--revision",
                    &revision,
                    "--test-path",
                    &format!("{name}.js"),
                    "--suite-export",
                    "suite",
                    "--test-id",
                    "probe",
                    "--output",
                    output.to_str().unwrap(),
                ])
                .output()
                .unwrap()
        };
        let result = run();
        assert_eq!(
            result.status.success(),
            success,
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let bytes = fs::read(&output).unwrap();
        let receipt: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(receipt["decision"], expected);
        assert_eq!(receipt["qualified"], false);
        assert_eq!(receipt["authorityWritePerformed"], false);
        assert_eq!(receipt["source"]["revision"], revision);
        assert!(!run().status.success(), "receipt overwrite accepted");
        assert_eq!(fs::read(&output).unwrap(), bytes);
    }
    fs::remove_dir_all(root).unwrap();
}
