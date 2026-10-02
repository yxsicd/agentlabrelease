#![cfg(unix)]
use agentlab_code_analysis::{
    digest,
    maintainer_operation_evidence::{compare_round, prepare_fact},
    maintainer_skill_flywheel::assess_with_receipts,
    maintainer_source_operation::{execute, qualify, recorded},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .canonicalize()
        .unwrap()
}
fn fixture() -> (PathBuf, Value, Value, Value) {
    static SEQUENCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let dir = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "source-operation-{}-{}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&dir).unwrap();
    fs::create_dir(dir.join("source")).unwrap();
    fs::create_dir(dir.join("source/src")).unwrap();
    let source = dir.join("source");
    fs::write(source.join("src/state.json"), b"{\"value\":1}").unwrap();
    fs::write(source.join("oracle.js"),"const fs=require('fs'); const original=JSON.parse(fs.readFileSync(process.argv[2])); const mode=process.argv[3]; if(mode==='error') { console.error('original-error'); process.exit(7); } console.log(JSON.stringify({value:mode==='wrong'?0:original.value,pass:mode==='wrong'}));\n").unwrap();
    let git = |a: &[&str]| {
        let r = Command::new("git")
            .args(a)
            .current_dir(&source)
            .output()
            .unwrap();
        assert!(r.status.success());
        String::from_utf8(r.stdout).unwrap().trim().to_owned()
    };
    git(&["init"]);
    git(&["config", "user.name", "Fixture"]);
    git(&["config", "user.email", "fixture@example.invalid"]);
    git(&[
        "remote",
        "add",
        "origin",
        "https://example.invalid/arbitrary.git",
    ]);
    git(&["add", "src/state.json", "oracle.js"]);
    git(&["commit", "-m", "fixture"]);
    let revision = git(&["rev-parse", "HEAD"]);
    let blob = git(&["rev-parse", "HEAD:src/state.json"]);
    let rows = fs::read_to_string(
        root().join("examples/maintainer-knowledge-gate/first-four/maintainer_scope_skills.jsonl"),
    )
    .unwrap();
    let mut skill = rows
        .lines()
        .map(|s| serde_json::from_str::<Value>(s).unwrap())
        .find(|s| s["id"] == "skill-scope-code-workshop-common-ui-state-contracts")
        .unwrap();
    skill["id"] = json!("scope-arbitrary");
    skill["repositoryId"] = json!("arbitrary");
    skill["repository"] = json!("https://example.invalid/arbitrary.git");
    skill["sourceRevision"] = json!(revision);
    skill["sourceTreeOid"] = json!(git(&["rev-parse", "HEAD^{tree}"]));
    skill["pathBoundary"] = json!("src");
    skill["ownershipSelectors"] = Value::Null;
    skill["trackedFileCount"] = json!(1);
    skill["sourceFileCount"] = json!(1);
    skill["evidence"] = json!([{"path":"src/state.json","gitBlobOid":blob}]);
    skill["responsibility"] = json!("Maintain the bounded fixture state contract.");
    let fact = json!({"id":"semantic-arbitrary","kind":"semantic-contract","repositoryId":"arbitrary","sourceRevision":revision,"scopeSkillIds":["scope-arbitrary"],
        "dimensions":["responsibility","boundary","relations","behavior"],"evidence":skill["evidence"]});
    fs::write(
        dir.join("scopes.jsonl"),
        serde_json::to_vec(&skill).unwrap(),
    )
    .unwrap();
    fs::write(dir.join("facts.jsonl"), serde_json::to_vec(&fact).unwrap()).unwrap();
    fs::create_dir(dir.join("receipts")).unwrap();
    let before = assess_with_receipts(
        &dir.join("scopes.jsonl"),
        Some(&dir.join("facts.jsonl")),
        1,
        None,
        Some(&dir.join("receipts")),
    )
    .unwrap();
    let result = Command::new("sh")
        .args(["-c", "command -v node"])
        .output()
        .unwrap();
    assert!(result.status.success());
    let node = String::from_utf8(result.stdout).unwrap().trim().to_owned();
    let command = |mode: &str| json!({"program":node,"programSha256":digest(&fs::read(&node).unwrap()),"args":[source.join("oracle.js"),"src/state.json",mode],"cwd":".","timeoutMs":30_000});
    let recipe = json!({"schema":"agentlab.maintainer_source_operation_recipe.v1","reviewed":true,"automaticPromotion":false,"operationKind":"source-only","scopeSkillId":skill["id"],
        "source":{"repositoryId":skill["repositoryId"],"repository":skill["repository"],"revision":revision},
        "sourceInputs":[{"path":"src/state.json","gitBlobOid":blob,"sha256":digest(&fs::read(source.join("src/state.json")).unwrap())}],
        "methodInputs":[{"path":source.join("oracle.js"),"sha256":digest(&fs::read(source.join("oracle.js")).unwrap())}],
        "checks":[{"id":"value","pointer":"/value","expected":1}],
        "controls":[{"id":"baseline","role":"baseline","command":command("baseline"),"expectedFailedCheckIds":[]},
            {"id":"reference","role":"reference","command":command("reference"),"expectedFailedCheckIds":[]},
            {"id":"wrong","role":"wrong","command":command("wrong"),"expectedFailedCheckIds":["value"]}]});
    (dir, skill, before, recipe)
}
fn run(dir: &Path, before: &Value, recipe: &Value, name: &str) -> Result<Value, String> {
    execute(
        &dir.join("scopes.jsonl"),
        &dir.join("facts.jsonl"),
        &dir.join("receipts"),
        &serde_json::to_vec(before).unwrap(),
        &serde_json::to_vec(recipe).unwrap(),
        &dir.join("source"),
        &dir.join(name),
    )
}
#[test]
fn real_controls_recompute_checks_and_advance_only_the_bound_scope() {
    let (dir, skill, before, recipe) = fixture();
    let execution = run(&dir, &before, &recipe, "capture").unwrap();
    assert_eq!(execution["qualified"], false);
    let execution_bytes = fs::read(dir.join("capture/execution-receipt.json")).unwrap();
    let qualification = qualify(&dir.join("capture"), &digest(&execution_bytes)).unwrap();
    let check = recorded(&qualification, &skill).unwrap();
    assert_eq!(check["status"], "verified");
    assert_eq!(check["controls"][2]["failedCheckIds"], json!(["value"]));
    assert_eq!(qualification["qualificationScope"]["runtime"], false);
    let bytes = serde_json::to_vec_pretty(&qualification).unwrap();
    fs::write(dir.join("receipts/source.json"), &bytes).unwrap();
    let operation = prepare_fact(
        &skill,
        json!({"path":"source.json","sha256":digest(&bytes)}),
        &dir.join("receipts"),
    )
    .unwrap();
    assert_eq!(operation["kind"], "source-maintenance-verification");
    assert!(operation["id"]
        .as_str()
        .unwrap()
        .starts_with("operation-source-"));
    let original = fs::read_to_string(dir.join("facts.jsonl")).unwrap();
    fs::write(
        dir.join("candidate.jsonl"),
        format!("{original}\n{}", serde_json::to_string(&operation).unwrap()),
    )
    .unwrap();
    let before_bytes = serde_json::to_vec(&before).unwrap();
    let after = assess_with_receipts(
        &dir.join("scopes.jsonl"),
        Some(&dir.join("candidate.jsonl")),
        2,
        Some(&digest(&before_bytes)),
        Some(&dir.join("receipts")),
    )
    .unwrap();
    let transition = compare_round(
        &before_bytes,
        &serde_json::to_vec(&after).unwrap(),
        &["scope-arbitrary".into()],
    )
    .unwrap();
    assert_eq!(transition["maintenanceReadyDelta"], 1);
    // Producer pass is deliberately false for accepted controls and true for wrong.
    // Tampered raw data, borrowed identity and stronger capabilities still reject.
    fs::write(dir.join("capture/reference.stdout"), b"{\"value\":0}").unwrap();
    assert!(qualify(&dir.join("capture"), &digest(&execution_bytes)).is_err());
    let mut borrowed = skill.clone();
    borrowed["id"] = json!("another");
    assert!(recorded(&qualification, &borrowed).is_err());
    borrowed = skill.clone();
    borrowed["buildEntrypoints"] = json!(["build.sh"]);
    assert!(recorded(&qualification, &borrowed).is_err());
    let mut changed = qualification.clone();
    changed["recipe"]["checks"][0]["expected"] = json!(0);
    assert!(recorded(&changed, &skill).is_err());
    fs::remove_dir_all(dir).unwrap();
}
#[test]
fn unreviewed_stale_and_failed_controls_never_qualify_or_overwrite() {
    let (dir, _, before, recipe) = fixture();
    let mut bad = recipe.clone();
    bad["reviewed"] = json!(false);
    assert!(run(&dir, &before, &bad, "unreviewed").is_err());
    assert!(!dir.join("unreviewed").exists());
    bad = recipe.clone();
    bad["sourceInputs"][0]["sha256"] = json!("0".repeat(64));
    assert!(run(&dir, &before, &bad, "stale").is_err());
    assert!(!dir.join("stale").exists());
    bad = recipe.clone();
    bad["controls"][1]["command"]["args"][2] = json!("error");
    assert!(run(&dir, &before, &bad, "failed").is_err());
    let bytes = fs::read(dir.join("failed/execution-receipt.json")).unwrap();
    let result: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(result["status"], "failed");
    assert_eq!(result["captures"][1]["exitCode"], 7);
    assert_eq!(
        fs::read(dir.join("failed/reference.stderr")).unwrap(),
        b"original-error\n"
    );
    assert!(qualify(&dir.join("failed"), &digest(&bytes)).is_err());
    assert!(run(&dir, &before, &recipe, "failed").is_err());
    assert_eq!(
        fs::read(dir.join("failed/execution-receipt.json")).unwrap(),
        bytes
    );
    fs::remove_dir_all(dir).unwrap();
}
