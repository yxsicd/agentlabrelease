#![cfg(unix)]
use agentlab_code_analysis::{
    digest,
    maintainer_downstream_exec::{execute, next, readback},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn git(root: &Path, args: &[&str]) -> String {
    let result = Command::new("git")
        .current_dir(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    String::from_utf8(result.stdout).unwrap().trim().to_owned()
}
fn fixture(name: &str, body: &str) -> (PathBuf, Value, Value, Value) {
    let root = std::env::temp_dir().join(format!(
        "downstream-exec-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        name
    ));
    fs::create_dir(&root).unwrap();
    let source = root.join("source");
    fs::create_dir(&source).unwrap();
    let code=format!("const {{describe,it}}=require('@ohos/hypium');const {{default:registry}}=require('@ohos.app.ability.abilityDelegatorRegistry');exports.suite=()=>describe('arbitrary',()=>it('probe',0,{body}));");
    fs::write(source.join("startup.js"), code).unwrap();
    git(&source, &["init"]);
    git(&source, &["config", "user.name", "Fixture"]);
    git(
        &source,
        &["config", "user.email", "fixture@example.invalid"],
    );
    git(&source, &["add", "startup.js"]);
    git(&source, &["commit", "-m", "controlled source"]);
    let revision = git(&source, &["rev-parse", "HEAD"]);
    let candidate = json!({"id":name,"sourceRevision":revision,"sourceSetSha256":"a".repeat(64),"knowledgeCutSha256":"b".repeat(64),"contextPaths":["startup.js"],"editablePaths":[]});
    let plan = json!({"schema":"agentlab.maintainer_downstream_plan.v1","status":"next-actions-planned","schedulingAllowed":true,"automaticPromotion":false,
        "candidateId":name,"candidateSha256":digest(&serde_json::to_vec(&candidate).unwrap()),"sourceRevision":revision,
        "sourceSetSha256":candidate["sourceSetSha256"],"knowledgeCutSha256":candidate["knowledgeCutSha256"],
        "actions":[{"id":"selected-oracle-action","kind":"implement-and-calibrate-oracle","readyForScheduling":true}]});
    let node = Command::new("node")
        .args(["-p", "process.execPath"])
        .output()
        .unwrap();
    assert!(node.status.success());
    let node = fs::canonicalize(String::from_utf8(node.stdout).unwrap().trim()).unwrap();
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/probe-hypium-failure-controls.cjs")
        .canonicalize()
        .unwrap();
    let recipe = json!({"schema":"agentlab.maintainer_downstream_probe_recipe.v1","reviewed":true,"adapter":"hypium-startability-controls",
        "planSha256":digest(&serde_json::to_vec(&plan).unwrap()),"actionId":"selected-oracle-action",
        "testPath":"startup.js","testBlobOid":git(&source,&["rev-parse",&format!("{revision}:startup.js")]),
        "testSourceSha256":digest(&fs::read(source.join("startup.js")).unwrap()),"suiteExport":"suite","testId":"probe",
        "node":node,"nodeSha256":digest(&fs::read(node).unwrap()),"probeScript":script,"timeoutMs":10_000,"typescript":null});
    (root, candidate, plan, recipe)
}
fn run(
    root: &Path,
    candidate: &Value,
    plan: &Value,
    recipe: &Value,
    out: &str,
) -> Result<Value, String> {
    execute(
        &serde_json::to_vec(plan).unwrap(),
        &serde_json::to_vec(candidate).unwrap(),
        &serde_json::to_vec(recipe).unwrap(),
        &root.join("source"),
        &root.join(out),
    )
}

#[test]
fn actual_execution_feedback_and_unchanged_repeat_across_arbitrary_sources() {
    for (name,body,expected,sensitive) in [
        ("first-repository","async(done)=>{try{await registry.getAbilityDelegator().startAbility({});done();}catch(e){done();}}","repair-independent-oracle",false),
        ("second-repository","async()=>{await registry.getAbilityDelegator().startAbility({});}","continue-runtime-calibration",true),
    ]{
        let (root,candidate,plan,recipe)=fixture(name,body);
        let result=run(&root,&candidate,&plan,&recipe,"execution").unwrap();
        assert_eq!(result["feedback"]["decision"],expected);assert_eq!(result["feedback"]["failureSensitive"],sensitive);
        assert_eq!(result["process"]["exitCode"],0);assert_eq!(result["sourceUnchanged"],true);assert_eq!(result["qualified"],false);
        let execution=root.join("execution");let sha=digest(&fs::read(execution.join("execution.json")).unwrap());
        assert_eq!(readback(&execution,&sha).unwrap()["feedback"],result["feedback"]);
        let portable=root.join("portable");fs::create_dir(&portable).unwrap();
        for entry in fs::read_dir(&execution).unwrap(){let p=entry.unwrap().path();fs::copy(&p,portable.join(p.file_name().unwrap())).unwrap();}
        assert_eq!(readback(&portable,&sha).unwrap()["feedback"],result["feedback"]);
        let first=next(&execution,&sha,None).unwrap();assert_eq!(first["nextAction"],expected);assert_eq!(first["schedulingAllowed"],true);
        let second=next(&execution,&sha,Some(&serde_json::to_vec(&first).unwrap())).unwrap();
        assert_eq!(second["schedulingAllowed"],false);assert_eq!(second["status"],"awaiting-new-evidence");
        assert!(run(&root,&candidate,&plan,&recipe,"execution").is_err(),"receipt overwrite accepted");
        fs::write(execution.join("process.stdout"),"tampered").unwrap();assert!(readback(&execution,&sha).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn unsupported_import_and_deadline_are_environment_failures_not_failed_cases() {
    for (name,body,timeout) in [
        ("unsupported","async()=>{await registry.getAbilityDelegator().startAbility({});require('unmodeled-platform');}",10_000),
        ("deadline","async()=>{await registry.getAbilityDelegator().startAbility({});}",1),
    ]{
        let (root,candidate,plan,mut recipe)=fixture(name,body);recipe["timeoutMs"]=json!(timeout);
        let result=run(&root,&candidate,&plan,&recipe,"execution").unwrap();
        assert_eq!(result["feedback"]["decision"],"repair-calibration-environment");
        assert_eq!(result["feedback"]["failureSensitive"],Value::Null);assert_eq!(result["qualified"],false);
        let sha=digest(&fs::read(root.join("execution/execution.json")).unwrap());
        assert_eq!(readback(&root.join("execution"),&sha).unwrap()["feedback"],result["feedback"]);
        assert!(root.join("execution/process.stderr").is_file());fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn changed_source_plan_path_runtime_and_review_fail_before_execution() {
    let (root, candidate, plan, recipe) = fixture(
        "guard",
        "async()=>{await registry.getAbilityDelegator().startAbility({});}",
    );
    for (field, value) in [
        ("reviewed", json!(false)),
        ("planSha256", json!("c".repeat(64))),
        ("testPath", json!("../startup.js")),
        ("nodeSha256", json!("d".repeat(64))),
        ("testSourceSha256", json!("e".repeat(64))),
    ] {
        let mut broken = recipe.clone();
        broken[field] = value;
        assert!(run(&root, &candidate, &plan, &broken, "rejected").is_err());
        assert!(!root.join("rejected").exists());
    }
    let mut blocked = plan.clone();
    blocked["schedulingAllowed"] = json!(false);
    assert!(run(&root, &candidate, &blocked, &recipe, "rejected").is_err());
    fs::write(root.join("source/startup.js"), "changed").unwrap();
    assert!(run(&root, &candidate, &plan, &recipe, "rejected").is_err());
    assert!(!root.join("rejected").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn recipe_preparation_and_failed_spawn_preserve_terminal_feedback() {
    let (root, candidate, plan, original) = fixture(
        "spawn-failure",
        "async()=>{await registry.getAbilityDelegator().startAbility({});}",
    );
    let source = root.join("source");
    let mut recipe = agentlab_code_analysis::maintainer_downstream_exec::recipe(
        &serde_json::to_vec(&plan).unwrap(),
        &source,
        Path::new(original["node"].as_str().unwrap()),
        Path::new(original["probeScript"].as_str().unwrap()),
        "startup.js",
        "suite",
        "probe",
        None,
    )
    .unwrap();
    // A pinned regular file without execute permission models a launcher error.
    recipe["node"] = json!(source.join("startup.js"));
    recipe["nodeSha256"] = json!(digest(&fs::read(source.join("startup.js")).unwrap()));
    let result = run(&root, &candidate, &plan, &recipe, "execution").unwrap();
    assert_eq!(result["process"]["status"], "spawn-failed");
    assert_eq!(
        result["feedback"]["decision"],
        "repair-calibration-environment"
    );
    let sha = digest(&fs::read(root.join("execution/execution.json")).unwrap());
    assert_eq!(
        readback(&root.join("execution"), &sha).unwrap()["feedback"],
        result["feedback"]
    );
    fs::remove_dir_all(root).unwrap();
}
