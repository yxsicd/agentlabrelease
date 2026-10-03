#![cfg(unix)]
use agentlab_code_analysis::{digest, maintainer_behavior_calibration as calibration};
use serde_json::{json, Value};
use std::{fs, path::PathBuf, process::Command};

struct Fixture {
    root: PathBuf,
    contract: Vec<u8>,
    recipe: Value,
    template: Value,
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}
fn bytes(v: &Value) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}
fn fixture(mode: &str) -> Fixture {
    static SEQUENCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "agentlab-calibration-{}-{}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    let output = Command::new("node")
        .args(["-p", "process.execPath"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let node = fs::canonicalize(String::from_utf8(output.stdout).unwrap().trim()).unwrap();
    let worker = root.join("worker.cjs");
    fs::write(&worker, r#"const fs=require('fs'),crypto=require('crypto');
const p=process.argv[2],mode=process.argv[3],r=JSON.parse(fs.readFileSync(p));
if(r.checks.some(c=>Object.hasOwn(c,'expected')) || r.controls) throw Error('evaluator answers leaked');
if(mode==='infrastructure' && p.includes('control-3')) process.exit(17);
const actual=new Function(r.submittedSource)();
if(mode==='recovery-failed' && p.includes('control-5')) actual.a=0;
if(mode==='tamper' && p.includes('control-1')) fs.writeFileSync(require('path').join(p,'../../control-0/executor.stdout'),'changed');
console.log(JSON.stringify({id:r.id,submittedSource:r.submittedSource,
submittedSourceSha256:crypto.createHash('sha256').update(r.submittedSource).digest('hex'),
originalSourceSha256:r.originalSourceSha256,observations:r.checks.map(c=>({id:c.id,input:c.input,actual:actual[c.id]}))}));
"#).unwrap();
    let participant = root.join("participant.cjs");
    fs::write(
        &participant,
        r#"const fs=require('fs'),r=JSON.parse(fs.readFileSync(process.argv[2]));
if(r.attempt===0) console.log(JSON.stringify({submittedSource:'return {a:0,b:1}; // submitted'}));
else {if(r.feedback.nextAction!=='repair-agent-behavior') throw Error('missing failed feedback');
console.log(JSON.stringify({submittedSource:'const n=1; return {a:n,b:n}; // repaired'}));}
"#,
    )
    .unwrap();
    let definitions = [
        ("original", "baseline", "return {a:0,b:1};", vec!["a"]),
        ("valid/one", "accepted", "return {a:1,b:1};", vec![]),
        (
            "valid-two",
            "accepted",
            "const n=1; return {a:n,b:n};",
            vec![],
        ),
        (
            "wrong-one",
            "wrong",
            if mode == "surviving" {
                "return {a:1,b:1}; // survives"
            } else if mode == "cascade" {
                "return {a:0,b:0}; // cascade"
            } else {
                "return {a:0,b:1}; // mutation"
            },
            vec!["a"],
        ),
        ("wrong-two", "wrong", "return {a:1,b:0};", vec!["b"]),
    ];
    let contract = bytes(
        &json!({"schema":"agentlab.frozen_behavior_checks.v1","candidateId":"unrelated-task",
        "candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),"originalSourceSha256":digest(definitions[0].2.as_bytes()),
        "methodSha256":digest(&fs::read(&worker).unwrap()),"compilerSha256":digest(&fs::read(&node).unwrap()),
        "runtime":"reviewed-node-fixture","workerDeadlineMs":1000,"automaticPromotion":false,
        "checks":[{"id":"a","input":null,"expected":1},{"id":"b","input":null,"expected":1}],
        "controls":definitions.iter().map(|(id,role,source,failed)| json!({"id":id,"role":role,
            "submittedSourceSha256":digest(source.as_bytes()),"expectedFailedCheckIds":failed})).collect::<Vec<_>>()}),
    );
    let command = |path: &PathBuf| {
        json!({"program":node,"programSha256":digest(&fs::read(&node).unwrap()),
        "args":[path,"{request}",mode],"cwd":".","timeoutMs":1000})
    };
    let inputs = json!([{"path":worker,"sha256":digest(&fs::read(&worker).unwrap())},
        {"path":participant,"sha256":digest(&fs::read(&participant).unwrap())}]);
    let recipe = json!({"schema":"agentlab.behavior_calibration_recipe.v1","reviewed":true,"automaticPromotion":false,
        "contractSha256":digest(&contract),"sources":definitions.iter().map(|(id,_,source,_)|json!({"id":id,"submittedSource":source})).collect::<Vec<_>>(),
        "recoveryControlId":"valid/one","executorCommand":command(&worker),"immutableInputs":inputs});
    let template = json!({"schema":"agentlab.calibrated_behavior_loop_template.v1","reviewed":true,"automaticPromotion":false,
        "contractSha256":digest(&contract),"calibrationRecipeSha256":digest(&bytes(&recipe)),
        "taskDemand":"Return one for each independent observation.","maximumAttempts":2,"immutableInputs":inputs,
        "participantCommand":command(&participant),"executorCommand":command(&worker)});
    Fixture {
        root,
        contract,
        recipe,
        template,
    }
}

#[test]
fn one_cli_dispatch_calibrates_recovers_and_delivers_feedback_to_existing_repair_loop() {
    let f = fixture("normal");
    for (name, value) in [
        ("recipe.json", bytes(&f.recipe)),
        ("template.json", bytes(&f.template)),
        ("contract.json", f.contract.clone()),
    ] {
        fs::write(f.root.join(name), value).unwrap();
    }
    let out = f.root.join("cycle");
    let output = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .arg("--execute-calibrated-behavior-loop")
        .args(["--contract", f.root.join("contract.json").to_str().unwrap()])
        .args([
            "--calibration-recipe",
            f.root.join("recipe.json").to_str().unwrap(),
        ])
        .args([
            "--loop-template",
            f.root.join("template.json").to_str().unwrap(),
        ])
        .args(["--output", out.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result: Value =
        serde_json::from_slice(&fs::read(out.join("cycle-result.json")).unwrap()).unwrap();
    assert_eq!(result["status"], "recorded-attempt-passed");
    assert_eq!(result["loop"]["attempts"].as_array().unwrap().len(), 2);
    assert_eq!(
        result["loop"]["attempts"][0]["nextAction"],
        "repair-agent-behavior"
    );
    assert_eq!(
        result["calibration"]["result"]["recoveryFeedback"]["nextAction"],
        "execute-agent-attempt"
    );
    assert_eq!(result["qualified"], false);
    assert_eq!(
        fs::read(out.join("calibration/contract.json")).unwrap(),
        f.contract
    );
    assert_eq!(
        fs::read(out.join("loop-template.json")).unwrap(),
        bytes(&f.template)
    );
    assert!(
        calibration::execute_cycle(&f.contract, &bytes(&f.recipe), &bytes(&f.template), &out)
            .is_err()
    );
}

#[test]
fn survived_contaminated_and_failed_recovery_controls_stop_before_participant() {
    for mode in ["surviving", "cascade", "recovery-failed"] {
        let f = fixture(mode);
        let out = f.root.join("cycle");
        let result =
            calibration::execute_cycle(&f.contract, &bytes(&f.recipe), &bytes(&f.template), &out)
                .unwrap();
        assert_eq!(result["status"], "calibration-review-required");
        assert_eq!(result["agentDispatched"], false);
        assert!(!out.join("attempts").exists());
        assert!(out.join("calibration/control-5/executor.stdout").is_file());
    }
}

#[test]
fn invalid_frozen_inputs_and_source_bindings_fail_before_execution() {
    let f = fixture("normal");
    let mut recipe = f.recipe.clone();
    recipe["sources"][1]["submittedSource"] = json!("changed");
    let out = f.root.join("invalid");
    assert!(calibration::execute(&f.contract, &bytes(&recipe), &out).is_err());
    assert!(!out.exists());
    let mut contract: Value = serde_json::from_slice(&f.contract).unwrap();
    contract["checks"][1]["id"] = json!("a");
    let contract = bytes(&contract);
    recipe["contractSha256"] = json!(digest(&contract));
    assert!(calibration::execute(&contract, &bytes(&recipe), &out).is_err());
    assert!(!out.exists());
    let mut template = f.template.clone();
    template["executorCommand"]["timeoutMs"] = json!(999);
    assert!(
        calibration::execute_cycle(&f.contract, &bytes(&f.recipe), &bytes(&template), &out)
            .is_err()
    );
    assert!(!out.exists());
}

#[test]
fn infrastructure_and_prior_capture_mutation_preserve_terminal_failure_without_negative_credit() {
    for mode in ["infrastructure", "tamper"] {
        let f = fixture(mode);
        let out = f.root.join("calibration");
        assert!(calibration::execute(&f.contract, &bytes(&f.recipe), &out).is_err());
        let result: Value =
            serde_json::from_slice(&fs::read(out.join("calibration-result.json")).unwrap())
                .unwrap();
        assert_eq!(result["status"], "infrastructure-failed");
        assert!(out.join("control-0/executor.stdout").is_file());
        assert!(!out.join("feedback.json").exists());
        assert!(!out.join("control-5").exists());
    }
}

#[test]
fn failed_cycle_has_terminal_receipt_and_does_not_overwrite_a_previous_run() {
    let f = fixture("infrastructure");
    let out = f.root.join("cycle");
    assert!(
        calibration::execute_cycle(&f.contract, &bytes(&f.recipe), &bytes(&f.template), &out)
            .is_err()
    );
    let path = out.join("cycle-result.json");
    let receipt = fs::read(&path).unwrap();
    let value: Value = serde_json::from_slice(&receipt).unwrap();
    assert_eq!(value["status"], "execution-failed");
    assert!(!out.join("attempts").exists());
    assert!(
        calibration::execute_cycle(&f.contract, &bytes(&f.recipe), &bytes(&f.template), &out)
            .is_err()
    );
    assert_eq!(fs::read(path).unwrap(), receipt);
}
