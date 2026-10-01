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
fn oracle_only_successor_preserves_demand_and_proves_changed_controls() {
    use agentlab_code_analysis::maintainer_downstream_exec::{
        compare_oracle_repair, recipe as prepare,
    };
    for (name, body, improved) in [
        ("repair-sensitive", "async()=>{await registry.getAbilityDelegator().startAbility({});}", true),
        ("repair-still-vacuous", "async(done)=>{try{await registry.getAbilityDelegator().startAbility({});done();}catch(error){done();}}", false),
    ] {
        let (root, old, mut plan, recipe) = fixture(name,
            "async(done)=>{try{await registry.getAbilityDelegator().startAbility({});done();}catch(e){done();}}");
        let before = run(&root, &old, &plan, &recipe, "before").unwrap();
        let before_sha = digest(&fs::read(root.join("before/execution.json")).unwrap());
        fs::write(root.join("source/startup.js"), format!("const {{describe,it}}=require('@ohos/hypium');const {{default:registry}}=require('@ohos.app.ability.abilityDelegatorRegistry');exports.suite=()=>describe('arbitrary',()=>it('probe',0,{body}));")).unwrap();
        git(&root.join("source"), &["add", "startup.js"]);
        git(&root.join("source"), &["commit", "-m", "Oracle-only repair"]);
        let mut child = old.clone();
        child["id"] = json!(format!("{name}-child"));
        child["sourceRevision"] = json!(git(&root.join("source"), &["rev-parse", "HEAD"]));
        child["oracleRepairParent"] = json!({"candidateId":old["id"],"candidateSha256":before["candidateSha256"],"executionSha256":before_sha});
        plan["candidateId"] = child["id"].clone();
        plan["sourceRevision"] = child["sourceRevision"].clone();
        plan["candidateSha256"] = json!(digest(&serde_json::to_vec(&child).unwrap()));
        let make_recipe = |plan: &Value| prepare(&serde_json::to_vec(plan).unwrap(), &root.join("source"),
            Path::new(recipe["node"].as_str().unwrap()), Path::new(recipe["probeScript"].as_str().unwrap()),
            "startup.js", "suite", "probe", None).unwrap();
        let mut new_recipe = make_recipe(&plan);
        new_recipe["timeoutMs"] = recipe["timeoutMs"].clone();
        run(&root, &child, &plan, &new_recipe, "after").unwrap();
        let after_sha = digest(&fs::read(root.join("after/execution.json")).unwrap());
        let compare = || compare_oracle_repair(&root.join("before"), &before_sha,
            &root.join("after"), &after_sha, &root.join("source"));
        let report = compare().unwrap();
        assert_eq!(report["controlsImproved"], improved);
        assert_eq!(report["implementationUnchanged"], true);
        assert_eq!(report["qualified"], false);
        // Valid capture but changed demand must never count as Oracle repair.
        let mut changed = child.clone();
        changed["demand"] = json!("different contract");
        let mut changed_plan = plan.clone();
        changed_plan["candidateSha256"] = json!(digest(&serde_json::to_vec(&changed).unwrap()));
        let mut changed_recipe = make_recipe(&changed_plan);
        changed_recipe["timeoutMs"] = recipe["timeoutMs"].clone();
        run(&root, &changed, &changed_plan, &changed_recipe, "changed-demand").unwrap();
        let changed_sha = digest(&fs::read(root.join("changed-demand/execution.json")).unwrap());
        assert!(compare_oracle_repair(&root.join("before"), &before_sha, &root.join("changed-demand"),
            &changed_sha, &root.join("source")).unwrap_err().contains("demand"));
        let mut budget_recipe = new_recipe.clone();
        budget_recipe["timeoutMs"] = json!(10_001);
        run(&root, &child, &plan, &budget_recipe, "changed-budget").unwrap();
        let budget_sha = digest(&fs::read(root.join("changed-budget/execution.json")).unwrap());
        assert!(compare_oracle_repair(&root.join("before"), &before_sha,
            &root.join("changed-budget"), &budget_sha, &root.join("source"))
            .unwrap_err().contains("runtime"));
        fs::write(root.join("source/unrelated"), "dirty").unwrap();
        assert!(compare().unwrap_err().contains("dirty"));
        // Even successful controls cannot hide implementation changes.
        git(&root.join("source"), &["add", "unrelated"]);
        git(&root.join("source"), &["commit", "--amend", "--no-edit"]);
        let mut extra = child.clone();
        extra["sourceRevision"] = json!(git(&root.join("source"), &["rev-parse", "HEAD"]));
        let mut extra_plan = plan.clone();
        extra_plan["sourceRevision"] = extra["sourceRevision"].clone();
        extra_plan["candidateSha256"] = json!(digest(&serde_json::to_vec(&extra).unwrap()));
        let mut extra_recipe = make_recipe(&extra_plan);
        extra_recipe["timeoutMs"] = recipe["timeoutMs"].clone();
        run(&root, &extra, &extra_plan, &extra_recipe, "extra-source").unwrap();
        let extra_sha = digest(&fs::read(root.join("extra-source/execution.json")).unwrap());
        assert!(compare_oracle_repair(&root.join("before"), &before_sha,
            &root.join("extra-source"), &extra_sha, &root.join("source"))
            .unwrap_err().contains("implementation"));
        fs::remove_dir_all(root).unwrap();
    }
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
