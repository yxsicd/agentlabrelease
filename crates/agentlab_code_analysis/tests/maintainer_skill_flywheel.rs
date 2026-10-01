use agentlab_code_analysis::{
    digest,
    maintainer_skill_flywheel::{assess, assess_with_receipts},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-maintainer-skill-flywheel-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}

#[test]
#[cfg(unix)]
fn operation_executor_runs_exact_plan_and_retains_failures_without_promotion() {
    use agentlab_code_analysis::{
        maintainer_flywheel_plan::plan_for_capabilities, maintainer_operation_exec::execute,
    };
    use std::process::Command;
    let root = temp_root();
    let source = root.join("source");
    fs::create_dir(&source).unwrap();
    fs::write(
        source.join("build.sh"),
        "printf 'artifact\\n' > result.bin\nprintf 'built\\n'\nprintf 'warning\\n' >&2\n",
    )
    .unwrap();
    fs::write(source.join(".gitignore"), "result.bin\n").unwrap();
    let git = |args: &[&str]| {
        let output = Command::new("git")
            .args(args)
            .current_dir(&source)
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
    git(&[
        "remote",
        "add",
        "origin",
        "https://example.invalid/arbitrary.git",
    ]);
    git(&["add", "build.sh", ".gitignore"]);
    git(&["commit", "-m", "fixture"]);
    let revision = git(&["rev-parse", "HEAD"]);
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let mut skill = scope("bounded-scope", "arbitrary");
    skill["sourceRevision"] = json!(revision);
    skill["buildEntrypoints"] = json!(["build.sh"]);
    let mut semantic = complete_fact("semantic", "arbitrary", "bounded-scope");
    semantic["sourceRevision"] = json!(revision);
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&scopes, &[skill]);
    jsonl(&facts, &[semantic]);
    let next = plan_for_capabilities(
        &scopes,
        Some(&facts),
        &root,
        1,
        None,
        &["operation-verification".into()],
        1,
        80,
        None,
        Some(&["build-only".into()]),
    )
    .unwrap();
    let plan_bytes = serde_json::to_vec(&next).unwrap();
    let before_bytes = serde_json::to_vec(&next["assessment"]).unwrap();
    let command = |args: Value| {
        json!({"program":"/bin/sh", "programSha256":digest(&fs::read("/bin/sh").unwrap()),
        "args":args, "cwd":".", "timeoutMs":1000})
    };
    let recipe = json!({"schema":"agentlab.maintainer_build_operation_recipe.v1", "automaticPromotion":false,
        "source":{"repositoryId":"arbitrary", "repository":"https://example.invalid/arbitrary.git", "revision":revision},
        "scopeSkillId":"bounded-scope", "lane":"build-only", "cleanBuild":true,
        "probes":[command(json!(["-c", "printf 'toolchain-version\\n'"]))],
        "dependencyPreparation":command(json!(["-c", "printf 'dependencies\\n'"])),
        "build":command(json!(["./build.sh"])), "artifact":"result.bin"});
    let run = |recipe: &Value, bytes: &[u8], name: &str| {
        execute(
            &scopes,
            &facts,
            &root,
            bytes,
            &before_bytes,
            &serde_json::to_vec(recipe).unwrap(),
            &source,
            &root.join(name),
        )
    };
    let result = run(&recipe, &plan_bytes, "successful").unwrap();
    assert_eq!(result["status"], "successful");
    assert_eq!(result["qualified"], false);
    assert_eq!(result["authorityWritePerformed"], false);
    assert_eq!(result["captures"].as_array().unwrap().len(), 4);
    assert_eq!(result["artifacts"].as_array().unwrap().len(), 2);
    assert_eq!(
        result["artifacts"][0]["sha256"],
        result["artifacts"][1]["sha256"]
    );
    assert_eq!(
        fs::read(root.join("successful/attempt-1.artifact")).unwrap(),
        b"artifact\n"
    );
    assert_eq!(
        fs::read_to_string(root.join("successful/build-1.stderr")).unwrap(),
        "warning\n"
    );
    assert!(run(&recipe, &plan_bytes, "successful").is_err());
    let mut forged = next.clone();
    forged["selectedScopeIds"] = json!(["another-scope"]);
    assert!(run(&recipe, &serde_json::to_vec(&forged).unwrap(), "forged").is_err());
    assert!(!root.join("forged").exists());
    for (key, value) in [
        ("scopeSkillId", json!("another-scope")),
        ("artifact", json!("../escape")),
    ] {
        let mut invalid = recipe.clone();
        invalid[key] = value;
        assert!(run(&invalid, &plan_bytes, key).is_err());
        assert!(!root.join(key).exists());
    }
    let mut invalid = recipe.clone();
    invalid["build"]["programSha256"] = json!("0".repeat(64));
    assert!(run(&invalid, &plan_bytes, "executable-drift").is_err());
    assert!(!root.join("executable-drift").exists());
    for (name, args, timeout) in [
        (
            "build-failed",
            json!(["-c", "printf 'failed\\n' >&2; exit 7"]),
            1000,
        ),
        (
            "timeout",
            json!([
                "-c",
                "(sleep 0.3; printf late > \"$1\") & wait",
                "fixture",
                root.join("late-marker")
            ]),
            40,
        ),
    ] {
        let mut invalid = recipe.clone();
        invalid["build"]["args"] = args;
        invalid["build"]["timeoutMs"] = json!(timeout);
        assert!(run(&invalid, &plan_bytes, name).is_err());
        let receipt: Value = serde_json::from_slice(
            &fs::read(root.join(name).join("execution-receipt.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(receipt["status"], "failed");
        assert_eq!(receipt["qualified"], false);
        assert_eq!(receipt["captures"].as_array().unwrap().len(), 3);
        assert!(receipt["artifacts"].as_array().unwrap().is_empty());
        if name == "timeout" {
            assert_eq!(receipt["captures"][2]["termination"], "deadline-exceeded");
            assert!(receipt["captures"][2]["durationMs"].as_u64().unwrap() < 2000);
            std::thread::sleep(std::time::Duration::from_millis(400));
            assert!(
                !root.join("late-marker").exists(),
                "timed-out descendant remained alive"
            );
        } else {
            assert_eq!(receipt["captures"][2]["exitCode"], 7);
            assert_eq!(
                fs::read_to_string(root.join(name).join("build-1.stderr")).unwrap(),
                "failed\n"
            );
        }
    }
    let denied_program = root.join("denied-program");
    fs::copy("/bin/sh", &denied_program).unwrap();
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(&denied_program, fs::Permissions::from_mode(0o600)).unwrap();
    let mut denied = recipe.clone();
    denied["dependencyPreparation"]["program"] = json!(denied_program);
    denied["dependencyPreparation"]["programSha256"] =
        json!(digest(&fs::read(&denied_program).unwrap()));
    assert!(run(&denied, &plan_bytes, "spawn-failed").is_err());
    let spawn: Value =
        serde_json::from_slice(&fs::read(root.join("spawn-failed/dependency.json")).unwrap())
            .unwrap();
    assert_eq!(spawn["status"], "spawn-failed");
    assert!(root.join("spawn-failed/execution-receipt.json").is_file());
    for (name, bytes) in [
        ("next.json", plan_bytes.as_slice()),
        ("before.json", before_bytes.as_slice()),
        (
            "recipe.json",
            serde_json::to_vec(&recipe).unwrap().as_slice(),
        ),
    ] {
        fs::write(root.join(name), bytes).unwrap();
    }
    let cli = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .arg("--execute-operation")
        .arg("--scope-skills")
        .arg(&scopes)
        .arg("--program-facts")
        .arg(&facts)
        .arg("--operation-receipts-root")
        .arg(&root)
        .arg("--next-round-plan")
        .arg(root.join("next.json"))
        .arg("--before")
        .arg(root.join("before.json"))
        .arg("--operation-recipe")
        .arg(root.join("recipe.json"))
        .arg("--source-worktree")
        .arg(&source)
        .arg("--output")
        .arg(root.join("cli-run"))
        .output()
        .unwrap();
    assert!(
        cli.status.success(),
        "{}",
        String::from_utf8_lossy(&cli.stderr)
    );
    let cli_receipt: Value =
        serde_json::from_slice(&fs::read(root.join("cli-run/execution-receipt.json")).unwrap())
            .unwrap();
    assert_eq!(cli_receipt["status"], "successful");
    assert_eq!(cli_receipt["qualified"], false);
    fs::write(source.join("dirty.txt"), "user-owned").unwrap();
    assert!(run(&recipe, &plan_bytes, "dirty").is_err());
    assert!(!root.join("dirty").exists());
    assert_eq!(
        fs::read_to_string(source.join("dirty.txt")).unwrap(),
        "user-owned"
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn operation_capabilities_route_without_hiding_other_scope_gaps() {
    use agentlab_code_analysis::maintainer_flywheel_plan::{operation_kind, plan_for_capabilities};
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let mut support = scope("a-config", "arbitrary");
    support["sourceFileCount"] = json!(0);
    support["kind"] = json!("configuration");
    let mut build = scope("b-build", "arbitrary");
    build["buildEntrypoints"] = json!(["build.sh"]);
    let mut build_test = scope("c-build-test", "arbitrary");
    build_test["buildEntrypoints"] = json!(["build.sh"]);
    build_test["testEntrypoints"] = json!(["test.sh"]);
    build_test["testFileCount"] = json!(1);
    jsonl(&scopes, &[support, build, build_test]);
    let semantic = ["a-config", "b-build", "c-build-test"]
        .iter()
        .map(|id| {
            let mut fact = complete_fact(&format!("fact-{id}"), "arbitrary", id);
            fact["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
            fact
        })
        .collect::<Vec<_>>();
    jsonl(&facts, &semantic);
    let run = |kinds: Option<&[String]>| {
        plan_for_capabilities(
            &scopes,
            Some(&facts),
            &root,
            1,
            None,
            &["operation-verification".into()],
            4,
            80,
            None,
            kinds,
        )
    };
    let legacy = run(None).unwrap();
    assert_eq!(legacy["selectedScopeIds"][0], "a-config");
    let bounded = run(Some(&["build-only".into()])).unwrap();
    assert_eq!(bounded["selectedScopeIds"], json!(["b-build"]));
    assert_eq!(bounded["summary"]["scopeCount"], 3);
    assert_eq!(bounded["summary"]["capabilityBlocked"], 2);
    assert_eq!(bounded["summary"]["eligible"], 1);
    let config = bounded["scopes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["skillId"] == "a-config")
        .unwrap();
    assert_eq!(config["capabilityGap"]["operationKind"], "support-config");
    let tests = bounded["scopes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["skillId"] == "c-build-test")
        .unwrap();
    assert_eq!(tests["capabilityGap"]["operationKind"], "build-test");
    assert_eq!(bounded["assessment"], legacy["assessment"]);
    assert_eq!(bounded["closedLoopQualified"], false);
    assert!(run(Some(&["build-only".into(), "build-only".into()])).is_err());
    assert!(run(Some(&["made-up".into()])).is_err());
    assert_eq!(run(Some(&[])).unwrap()["decision"], "capability-blocked");
    for (caps, kind) in [
        (json!(["build-maintenance"]), "build-only"),
        (
            json!(["build-maintenance", "test-maintenance"]),
            "build-test",
        ),
        (json!(["test-maintenance"]), "test-only"),
        (json!(["source-maintenance"]), "source-only"),
        (json!(["support-maintenance"]), "support-config"),
    ] {
        assert_eq!(operation_kind(&caps), kind);
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn durable_assessment_resolution_ignores_orphans_and_rejects_broken_lineage() {
    use agentlab_code_analysis::maintainer_flywheel_plan::latest_assessment;
    let root = temp_root();
    fs::create_dir(root.join("assessments")).unwrap();
    let scopes = root.join("scopes.jsonl");
    jsonl(&scopes, &[scope("scope-alpha", "alpha")]);
    let baseline = serde_json::to_vec_pretty(&assess(&scopes, None, 1, None).unwrap()).unwrap();
    let relative = "assessments/current.json";
    fs::write(root.join(relative), &baseline).unwrap();
    fs::write(
        root.join("assessments/orphan.json"),
        b"{\"roundIndex\":999}",
    )
    .unwrap();
    let table = root.join("maintainer_skill_refresh_rounds.jsonl");
    let round = json!({"id":"durable-seven","roundIndex":7,
        "assessment":{"path":relative,"sha256":digest(&baseline)}});
    jsonl(&table, &[round.clone()]);
    let resolved = latest_assessment(&root).unwrap();
    assert_eq!(resolved["refreshRoundIndex"], 7);
    assert_eq!(resolved["assessmentRoundIndex"], 1);
    assert_eq!(resolved["assessmentSha256"], digest(&baseline));
    let project = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let python = |expect_ok: bool| {
        let result = std::process::Command::new("python3").args(["-c",
            "import importlib.util, pathlib, sys; s=importlib.util.spec_from_file_location('writer',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.latest_assessment_path(pathlib.Path(sys.argv[2])))"])
            .arg(project.join("scripts/maintainer-skill-tablegit.py")).arg(&root).output().unwrap();
        assert_eq!(
            result.status.success(),
            expect_ok,
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        if expect_ok {
            assert_eq!(
                String::from_utf8(result.stdout).unwrap().trim(),
                root.join(relative).to_str().unwrap()
            );
        }
    };
    python(true);
    #[cfg(unix)]
    {
        fs::write(root.join("original.json"), &baseline).unwrap();
        fs::remove_file(root.join(relative)).unwrap();
        std::os::unix::fs::symlink(root.join("original.json"), root.join(relative)).unwrap();
        assert!(latest_assessment(&root).is_err());
        python(false);
        fs::remove_file(root.join(relative)).unwrap();
        fs::write(root.join(relative), &baseline).unwrap();
    }
    let pointer = root.join("resolved.json");
    let invoke = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args(["--resolve-latest-assessment", "--base"])
            .arg(&root)
            .arg("--output")
            .arg(&pointer)
            .output()
            .unwrap()
    };
    assert!(invoke().status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&pointer).unwrap()).unwrap(),
        resolved
    );
    assert!(!invoke().status.success());
    fs::remove_file(&pointer).unwrap();
    jsonl(
        &table,
        &[
            round.clone(),
            json!({"id":"conflict","roundIndex":7,"assessment":round["assessment"]}),
        ],
    );
    assert!(latest_assessment(&root).is_err());
    python(false);
    jsonl(&table, &[round.clone()]);
    fs::write(root.join(relative), b"tampered").unwrap();
    assert!(latest_assessment(&root).is_err());
    python(false);
    assert!(!invoke().status.success());
    assert!(!pointer.exists());
    fs::write(root.join(relative), &baseline).unwrap();
    for path in [
        "../outside.json",
        "assessments/../scopes.jsonl",
        "/absolute.json",
    ] {
        let mut invalid = round.clone();
        invalid["assessment"]["path"] = json!(path);
        jsonl(&table, &[invalid]);
        assert!(latest_assessment(&root).is_err());
        python(false);
    }
    jsonl(&table, &[round]);
    fs::remove_file(root.join(relative)).unwrap();
    assert!(latest_assessment(&root).is_err());
    python(false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_semantic_dispatch_uses_exact_plan_and_rejects_drift() {
    use agentlab_code_analysis::maintainer_flywheel_plan::{plan_for_repository, semantic_batch};
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let baseline_path = root.join("baseline.json");
    jsonl(
        &scopes,
        &[scope("scope-alpha", "alpha"), scope("scope-beta", "beta")],
    );
    jsonl(&facts, &[]);
    let next = plan_for_repository(
        &scopes,
        Some(&facts),
        &root,
        1,
        None,
        &["semantic-refresh".into()],
        4,
        80,
        Some("beta"),
    )
    .unwrap();
    assert_eq!(next["summary"]["scopeCount"], 2);
    assert_eq!(next["selectedScopeIds"], json!(["scope-beta"]));
    let baseline = serde_json::to_vec_pretty(&next["assessment"]).unwrap();
    let plan_bytes = serde_json::to_vec_pretty(&next).unwrap();
    let cut = serde_json::to_vec(&json!({"repositories":[
        {"id":"alpha","repository":"https://example.invalid/alpha.git","revision":"1".repeat(40)},
        {"id":"beta","repository":"https://example.invalid/beta.git","revision":"1".repeat(40)}
    ]}))
    .unwrap();
    let batch = semantic_batch(
        &scopes,
        &facts,
        &root,
        &plan_bytes,
        &baseline,
        &baseline_path,
        &cut,
        "beta",
    )
    .unwrap();
    assert_eq!(batch["requests"][0]["scope"]["id"], "scope-beta");
    assert_eq!(
        batch["requests"][0]["requiredDimensions"],
        json!(["behavior", "boundary", "relations", "responsibility"])
    );
    assert_eq!(batch["sourceAssessment"]["sha256"], digest(&baseline));
    assert_eq!(batch["selectionPlanSha256"], digest(&plan_bytes));
    assert_eq!(batch["authorityWritePerformed"], false);
    assert!(semantic_batch(
        &scopes,
        &facts,
        &root,
        &plan_bytes,
        &baseline,
        &baseline_path,
        &cut,
        "alpha"
    )
    .is_err());
    let mut forged = next.clone();
    forged["selectedScopeIds"] = json!(["scope-alpha"]);
    assert!(semantic_batch(
        &scopes,
        &facts,
        &root,
        &serde_json::to_vec(&forged).unwrap(),
        &baseline,
        &baseline_path,
        &cut,
        "auto"
    )
    .is_err());
    let mut forged_baseline = next["assessment"].clone();
    forged_baseline["totals"]["semanticReadyCount"] = json!(2);
    assert!(semantic_batch(
        &scopes,
        &facts,
        &root,
        &plan_bytes,
        &serde_json::to_vec(&forged_baseline).unwrap(),
        &baseline_path,
        &cut,
        "auto"
    )
    .is_err());
    let mut bad_cut: Value = serde_json::from_slice(&cut).unwrap();
    bad_cut["repositories"][1]["revision"] = json!("9".repeat(40));
    assert!(semantic_batch(
        &scopes,
        &facts,
        &root,
        &plan_bytes,
        &baseline,
        &baseline_path,
        &serde_json::to_vec(&bad_cut).unwrap(),
        "auto"
    )
    .is_err());
    fs::write(&baseline_path, &baseline).unwrap();
    fs::write(root.join("plan.json"), &plan_bytes).unwrap();
    fs::write(root.join("cut.json"), &cut).unwrap();
    let output = root.join("batch.json");
    let invoke = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args(["--prepare-semantic-batch", "--scope-skills"])
            .arg(&scopes)
            .arg("--program-facts")
            .arg(&facts)
            .arg("--operation-receipts-root")
            .arg(&root)
            .arg("--before")
            .arg(&baseline_path)
            .arg("--next-round-plan")
            .arg(root.join("plan.json"))
            .arg("--knowledge-cut")
            .arg(root.join("cut.json"))
            .args(["--repository", "beta", "--output"])
            .arg(&output)
            .output()
            .unwrap()
    };
    assert!(invoke().status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&output).unwrap()).unwrap(),
        batch
    );
    assert!(!invoke().status.success()); // no overwrite
    fs::remove_file(&output).unwrap();
    jsonl(&facts, &[complete_fact("drift", "beta", "scope-beta")]);
    assert!(!invoke().status.success());
    assert!(!output.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn semantic_dispatch_refuses_nonsemantic_or_unavailable_lanes() {
    use agentlab_code_analysis::maintainer_flywheel_plan::{plan, semantic_batch};
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope-alpha", "alpha")]);
    jsonl(&facts, &[]);
    let cut = serde_json::to_vec(&json!({"repositories":[
        {"id":"alpha","repository":"https://example.invalid/alpha.git","revision":"1".repeat(40)}
    ]}))
    .unwrap();
    let check = |next: Value| {
        semantic_batch(
            &scopes,
            &facts,
            &root,
            &serde_json::to_vec(&next).unwrap(),
            &serde_json::to_vec(&next["assessment"]).unwrap(),
            &root.join("baseline.json"),
            &cut,
            "auto",
        )
    };
    assert!(check(plan(&scopes, Some(&facts), &root, 1, None, &[], 1, 80).unwrap()).is_err());
    jsonl(&facts, &[complete_fact("semantic", "alpha", "scope-alpha")]);
    let operation = plan(
        &scopes,
        Some(&facts),
        &root,
        1,
        None,
        &["operation-verification".into()],
        1,
        80,
    )
    .unwrap();
    assert_eq!(operation["nextLane"], "operation-verification");
    assert!(check(operation).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_execution_loop_stops_before_agent_when_source_cut_drifted() {
    let root = temp_root();
    let knowledge = root.join("knowledge");
    fs::create_dir_all(knowledge.join("assessments")).unwrap();
    fs::create_dir_all(knowledge.join("operation-evidence")).unwrap();
    let scopes = knowledge.join("maintainer_scope_skills.jsonl");
    let facts = knowledge.join("program_facts.jsonl");
    jsonl(&scopes, &[scope("scope-alpha", "alpha")]);
    jsonl(&facts, &[]);
    let baseline = assess_with_receipts(
        &scopes,
        Some(&facts),
        1,
        None,
        Some(&knowledge.join("operation-evidence")),
    )
    .unwrap();
    fs::write(
        knowledge.join("assessments/baseline.json"),
        serde_json::to_vec(&baseline).unwrap(),
    )
    .unwrap();
    jsonl(
        &knowledge.join("maintainer_skill_refresh_rounds.jsonl"),
        &[json!({
            "id":"round-one","roundIndex":1,"assessment":{"path":"assessments/baseline.json",
            "sha256":digest(&serde_json::to_vec(&baseline).unwrap())}
        })],
    );
    fs::write(knowledge.join("maintainer-knowledge-cut.json"), serde_json::to_vec(&json!({
        "repositories":[{"id":"alpha","repository":"https://example.invalid/alpha.git","revision":"9".repeat(40)}]
    })).unwrap()).unwrap();
    let run = root.join("run");
    let project = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let output = std::process::Command::new("bash")
        .arg(project.join("scripts/run-maintainer-skill-agent-loop.sh"))
        .arg(&knowledge)
        .arg(&run)
        .args(["auto", "1", "/absent/participant"])
        .env(
            "AGENTLAB_FLYWHEEL_GATE",
            env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"),
        )
        .current_dir(project)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(
        String::from_utf8_lossy(&output.stderr)
            .contains("dispatch repository cut identity differs"),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(run
        .join("loop/iteration-1/strict-next-round-plan.json")
        .exists());
    assert!(!run
        .join("loop/iteration-1/flywheel-batch-request.json")
        .exists());
    assert!(!run.join("loop/iteration-1/agents").exists());
    assert!(!run.join("loop/knowledge-1").exists());
    fs::remove_dir_all(root).unwrap();
}

fn jsonl(path: &Path, rows: &[Value]) {
    let text = rows
        .iter()
        .map(|row| serde_json::to_string(row).unwrap() + "\n")
        .collect::<String>();
    fs::write(path, text).unwrap();
}

fn rows_from_file(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

fn scope(id: &str, repository_id: &str) -> Value {
    json!({
        "schema":"agentlab.maintainer_scope_skill.v1",
        "id":id,
        "skillLayer":"instance",
        "stage":"repository-scope",
        "ownershipPlane":"target-operations",
        "assetClass":"reusable-knowledge",
        "status":"source-supported",
        "repositoryId":repository_id,
        "repository":format!("https://example.invalid/{repository_id}.git"),
        "sourceRevision":"1".repeat(40),
        "sourceTreeOid":"2".repeat(40),
        "strategy":"generic-source-boundary",
        "kind":"source-component",
        "pathBoundary":"src",
        "responsibility":"Maintain the source component and its external contract.",
        "documentedTitle":null,
        "documentedPurpose":null,
        "trackedFileCount":1,
        "sourceFileCount":1,
        "codeLineCount":10,
        "testFileCount":0,
        "languages":{"generic":1},
        "externalDependencyCount":0,
        "externalDependencies":[],
        "buildEntrypoints":[],
        "testEntrypoints":[],
        "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}],
        "coverage":"all tracked files under this leaf boundary are assigned exactly once",
        "automaticPromotion":false
    })
}

fn complete_fact(id: &str, repository_id: &str, skill_id: &str) -> Value {
    json!({
        "id":id,
        "kind":"semantic-contract",
        "repositoryId":repository_id,
        "sourceRevision":"1".repeat(40),
        "scopeSkillIds":[skill_id],
        "dimensions":["responsibility","boundary","relations","behavior","operation"],
        "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}]
    })
}

fn build_receipt() -> Value {
    let attempt = |id: &str| {
        json!({
            "cleanBuild":true,"exitCode":0,"durationMs":100,"artifact":"out/library.har",
            "artifactBytes":123,"artifactSha256":"a".repeat(64),
            "canonicalMemberSha256":"b".repeat(64),"memberCount":3,"buildLogSha256":"c".repeat(64),
            "executionAuthority":{"routeDecision":"peer_direct","targetPeerId":"generic-peer","operationId":id}
        })
    };
    json!({
        "schema":"agentlab.maintainer_scope_build_qualification.v1", "status":"qualified", "automaticPromotion":false,
        "source":{"repositoryId":"arbitrary","repository":"https://example.invalid/arbitrary.git","revision":"1".repeat(40),"cleanBefore":true,"cleanAfter":true},
        "scope":{"scopeSkillIds":["scope"],"lane":"build-only","module":"library","target":"default","scopeSpecificBinding":true},
        "toolchain":{"sdkRelease":"fixture-sdk","hvigorVersion":"fixture-build","ohpmVersion":"fixture-deps"},
        "dependencyPreparation":{"status":"successful","exitCode":0,"durationMs":100,"lockSha256":"d".repeat(64)},
        "build":{"status":"successful","task":"assembleHar","command":["builder","--no-type-check","assembleHar"],"canonicalContentReproducible":true,"rawArchiveReproducible":true,"attempts":[attempt("run-one"),attempt("run-two")]},
        "qualificationScope":{"moduleBuild":true,"runtime":false,"tests":false,"performance":false},
        "limitations":["Controlled fixture; no real execution or runtime qualification."]
    })
}

#[test]
fn semantic_round_gate_rejects_borrowed_gains_and_partial_batches() {
    use agentlab_code_analysis::maintainer_semantic_round::compare;
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(
        &scopes,
        &[
            scope("selected", "arbitrary"),
            scope("sibling", "arbitrary"),
        ],
    );
    jsonl(&facts, &[]);
    let before = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    let before_bytes = serde_json::to_vec(&before).unwrap();
    let semantic = |id: &str| {
        let mut fact = complete_fact(&format!("semantic-{id}"), "arbitrary", id);
        fact["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
        fact
    };
    let evaluate = || {
        assess_with_receipts(
            &scopes,
            Some(&facts),
            2,
            Some(&digest(&before_bytes)),
            Some(&root),
        )
        .unwrap()
    };
    jsonl(&facts, &[semantic("sibling")]);
    let borrowed = evaluate();
    assert_eq!(borrowed["totals"]["semanticReadyCount"], 1);
    assert!(compare(
        &before_bytes,
        &serde_json::to_vec(&borrowed).unwrap(),
        &["selected".into()]
    )
    .unwrap_err()
    .contains("unselected"));
    jsonl(&facts, &[semantic("selected")]);
    let after = evaluate();
    let after_bytes = serde_json::to_vec(&after).unwrap();
    let result = compare(&before_bytes, &after_bytes, &["selected".into()]).unwrap();
    assert_eq!(result["decision"], "review-proposed-knowledge");
    assert_eq!(result["advancedScopeIds"], json!(["selected"]));
    assert_eq!(result["semanticReadyDelta"], 1);
    assert_eq!(result["maintenanceReadyDelta"], 0);
    assert!(compare(
        &before_bytes,
        &after_bytes,
        &["selected".into(), "sibling".into()]
    )
    .unwrap_err()
    .contains("partial"));
    for (pointer, value) in [
        ("/roundIndex", json!(3)),
        ("/parentAssessmentSha256", json!("a".repeat(64))),
        ("/inputs/scopeSkillsSha256", json!("b".repeat(64))),
        ("/totals/semanticReadyCount", json!(2)),
        (
            "/standard/operationEvidencePolicy",
            json!("legacy-explicit-claim"),
        ),
    ] {
        let mut forged = after.clone();
        *forged.pointer_mut(pointer).unwrap() = value;
        assert!(
            compare(
                &before_bytes,
                &serde_json::to_vec(&forged).unwrap(),
                &["selected".into()]
            )
            .is_err(),
            "{pointer}"
        );
    }
    let replay = assess_with_receipts(
        &scopes,
        Some(&facts),
        3,
        Some(&digest(&after_bytes)),
        Some(&root),
    )
    .unwrap();
    let replay_result = compare(
        &after_bytes,
        &serde_json::to_vec(&replay).unwrap(),
        &["selected".into()],
    )
    .unwrap();
    assert_eq!(replay_result["decision"], "no-change");
    assert_eq!(replay_result["semanticReadyDelta"], 0);
    let before_path = root.join("before.json");
    let after_path = root.join("after.json");
    fs::write(&before_path, before_bytes).unwrap();
    fs::write(&after_path, after_bytes).unwrap();
    let output = root.join("result.json");
    let command = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--compare-semantic-round",
                "--before",
                before_path.to_str().unwrap(),
                "--after",
                after_path.to_str().unwrap(),
                "--selected-scope",
                "selected",
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    assert!(command().status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&fs::read(&output).unwrap()).unwrap(),
        result
    );
    fs::write(&after_path, serde_json::to_vec(&borrowed).unwrap()).unwrap();
    fs::remove_file(&output).unwrap();
    assert!(!command().status.success());
    assert!(!output.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn semantic_closure_preserves_preverified_operation_evidence() {
    use agentlab_code_analysis::maintainer_semantic_round::compare;
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary")]);
    let bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &bytes).unwrap();
    let mut operation = complete_fact("operation", "arbitrary", "scope");
    operation["dimensions"] = json!(["operation"]);
    operation["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
    jsonl(&facts, &[operation.clone()]);
    let before = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    let before_bytes = serde_json::to_vec(&before).unwrap();
    let mut semantic = complete_fact("semantic", "arbitrary", "scope");
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&facts, &[operation, semantic]);
    let after = assess_with_receipts(
        &scopes,
        Some(&facts),
        2,
        Some(&digest(&before_bytes)),
        Some(&root),
    )
    .unwrap();
    let result = compare(
        &before_bytes,
        &serde_json::to_vec(&after).unwrap(),
        &["scope".into()],
    )
    .unwrap();
    assert_eq!(result["semanticReadyDelta"], 1);
    assert_eq!(result["maintenanceReadyDelta"], 1);
    assert_eq!(result["strictOperationEvidencePolicy"], true);
    fs::write(root.join("build.json"), b"tampered").unwrap();
    let invalid = assess_with_receipts(
        &scopes,
        Some(&facts),
        2,
        Some(&digest(&before_bytes)),
        Some(&root),
    )
    .unwrap();
    assert!(compare(
        &before_bytes,
        &serde_json::to_vec(&invalid).unwrap(),
        &["scope".into()]
    )
    .unwrap_err()
    .contains("operation evidence"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn next_round_planner_routes_gaps_without_claiming_closed_loop() {
    use agentlab_code_analysis::maintainer_flywheel_plan::plan;
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let skill = scope("scope", "arbitrary");
    jsonl(&scopes, &[skill.clone()]);
    jsonl(&facts, &[]);
    let run = |lanes: &[&str]| {
        plan(
            &scopes,
            Some(&facts),
            &root,
            1,
            None,
            &lanes.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            4,
            80,
        )
        .unwrap()
    };
    let blocked = run(&[]);
    assert_eq!(blocked["decision"], "capability-blocked");
    assert_eq!(blocked["summary"]["capabilityBlocked"], 1);
    assert_eq!(blocked["scopes"][0]["capabilityGap"], "semantic-refresh");
    let semantic = run(&["semantic-refresh"]);
    assert_eq!(semantic["nextLane"], "semantic-refresh");
    assert_eq!(semantic["selectedScopeIds"], json!(["scope"]));
    let mut fact = complete_fact("semantic", "arbitrary", "scope");
    fact["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&facts, &[fact.clone()]);
    let operation = run(&["semantic-refresh", "operation-verification"]);
    assert_eq!(operation["nextLane"], "operation-verification");
    assert_eq!(operation["scopes"][0]["maturity"], "L2-semantic-ready");
    // A legacy operation claim or a missing receipt cannot skip this lane.
    fact["dimensions"] = json!([
        "responsibility",
        "boundary",
        "relations",
        "behavior",
        "operation"
    ]);
    jsonl(&facts, &[fact.clone()]);
    assert_eq!(
        run(&["operation-verification"])["nextLane"],
        "operation-verification"
    );
    let bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &bytes).unwrap();
    fact["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
    jsonl(&facts, &[fact]);
    let ready = run(&["operation-verification"]);
    assert_eq!(ready["summary"]["knowledgeReady"], 1);
    assert_eq!(ready["decision"], "downstream-validation-required");
    assert_eq!(ready["closedLoopQualified"], false);
    assert_eq!(ready["automaticPromotion"], false);
    assert_eq!(ready["authorityWritePerformed"], false);
    assert_eq!(ready, run(&["operation-verification"]));
    let output = root.join("next-plan.json");
    let command = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--plan-next-round",
                "--scope-skills",
                scopes.to_str().unwrap(),
                "--program-facts",
                facts.to_str().unwrap(),
                "--operation-receipts-root",
                root.to_str().unwrap(),
                "--round-index",
                "1",
                "--available-lane",
                "operation-verification",
                "--batch-size",
                "4",
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    assert!(command().status.success());
    let bytes = fs::read(&output).unwrap();
    assert_eq!(serde_json::from_slice::<Value>(&bytes).unwrap(), ready);
    assert!(!command().status.success());
    assert_eq!(fs::read(&output).unwrap(), bytes);
    fs::write(root.join("build.json"), b"tampered").unwrap();
    assert_eq!(
        run(&["operation-verification"])["nextLane"],
        "operation-verification"
    );
    for lanes in [
        vec!["unknown".into()],
        vec!["semantic-refresh".into(), "semantic-refresh".into()],
    ] {
        assert!(plan(&scopes, Some(&facts), &root, 1, None, &lanes, 1, 80).is_err());
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn next_round_plan_accounts_for_every_scope_and_isolates_batches() {
    use agentlab_code_analysis::maintainer_flywheel_plan::plan;
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let mut rows = vec![
        scope("zeta", "arbitrary"),
        scope("alpha", "arbitrary"),
        scope("foreign", "other"),
    ];
    let mut large = scope("large", "arbitrary");
    large["sourceFileCount"] = json!(81);
    large["trackedFileCount"] = json!(81);
    rows.push(large);
    let mut root_scope = scope("root", "arbitrary");
    root_scope["pathBoundary"] = json!(".");
    rows.push(root_scope);
    let mut stale = scope("repair", "arbitrary");
    stale["sourceRevision"] = Value::Null;
    rows.push(stale);
    jsonl(&scopes, &rows);
    let available = vec!["semantic-refresh".into()];
    let report = plan(&scopes, None, &root, 1, None, &available, 4, 80).unwrap();
    assert_eq!(report["summary"]["scopeCount"], 6);
    assert_eq!(report["summary"]["capabilityBlocked"], 2);
    assert_eq!(report["selectedScopeIds"], json!(["alpha", "zeta"]));
    assert_eq!(report["nextLane"], "semantic-refresh");
    let items = report["scopes"].as_array().unwrap();
    assert_eq!(
        items.iter().find(|row| row["skillId"] == "large").unwrap()["nextLane"],
        "scope-decomposition"
    );
    assert_eq!(
        items.iter().find(|row| row["skillId"] == "repair").unwrap()["nextLane"],
        "inventory-repair"
    );
    rows.reverse();
    jsonl(&scopes, &rows);
    let reordered = plan(&scopes, None, &root, 1, None, &available, 4, 80).unwrap();
    assert_eq!(reordered["scopes"], report["scopes"]);
    assert_eq!(reordered["selectedScopeIds"], report["selectedScopeIds"]);
    // Even same repository/lane cannot batch a different source revision.
    rows.iter_mut().find(|row| row["id"] == "zeta").unwrap()["sourceRevision"] =
        json!("9".repeat(40));
    jsonl(&scopes, &rows);
    let different = plan(&scopes, None, &root, 1, None, &available, 4, 80).unwrap();
    assert_eq!(different["selectedScopeIds"], json!(["alpha"]));
    assert!(plan(&scopes, None, &root, 1, None, &available, 0, 80).is_err());
    assert!(plan(&scopes, None, &root, 1, None, &available, 4, 0).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn mixed_semantic_and_operation_rounds_preserve_portable_cut() {
    use agentlab_code_analysis::{
        maintainer_operation_evidence::prepare_fact, maintainer_operation_stage::stage,
        maintainer_semantic_round::compare,
    };
    let root = temp_root();
    let base = root.join("base");
    fs::create_dir_all(base.join("assessments")).unwrap();
    jsonl(
        &base.join("maintainer_scope_skills.jsonl"),
        &[scope("alpha", "arbitrary"), scope("beta", "arbitrary")],
    );
    let mut semantic_alpha = complete_fact("semantic-alpha", "arbitrary", "alpha");
    semantic_alpha["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&base.join("program_facts.jsonl"), &[semantic_alpha.clone()]);
    jsonl(&base.join("maintainer_skills.jsonl"), &[]);
    jsonl(&base.join("evaluation_cases.jsonl"), &[]);
    fs::write(base.join("maintainer-knowledge-cut.json"), b"{}\n").unwrap();
    let original = root.join("original-machine");
    fs::create_dir(&original).unwrap();
    let mut receipt = build_receipt();
    receipt["scope"]["scopeSkillIds"] = json!(["alpha"]);
    let receipt_bytes = serde_json::to_vec(&receipt).unwrap();
    fs::write(original.join("alpha.json"), &receipt_bytes).unwrap();
    let before = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        1,
        None,
        Some(&original),
    )
    .unwrap();
    let before_bytes = serde_json::to_vec(&before).unwrap();
    fs::write(base.join("assessments/parent.json"), &before_bytes).unwrap();
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &[json!({
            "id":"parent", "roundIndex":1, "coverage":{"trackedFileCount":2},
            "assessment":{"path":"assessments/parent.json","sha256":digest(&before_bytes)}
        })],
    );
    let operation_alpha = prepare_fact(
        &scope("alpha", "arbitrary"),
        json!({"path":"alpha.json","sha256":digest(&receipt_bytes)}),
        &original,
    )
    .unwrap();
    let candidate = root.join("candidate.jsonl");
    jsonl(&candidate, &[semantic_alpha, operation_alpha]);
    let after = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&candidate),
        2,
        Some(&digest(&before_bytes)),
        Some(&original),
    )
    .unwrap();
    let after_bytes = serde_json::to_vec(&after).unwrap();
    let before_path = root.join("before.json");
    let after_path = root.join("after.json");
    fs::write(&before_path, &before_bytes).unwrap();
    fs::write(&after_path, &after_bytes).unwrap();
    let operation_cut = root.join("operation-cut");
    stage(
        &base,
        &candidate,
        &before_path,
        &after_path,
        &original,
        &["alpha".into()],
        "alpha",
        false,
        &operation_cut,
    )
    .unwrap();
    fs::remove_dir_all(&original).unwrap();
    let mut semantic_beta = complete_fact("semantic-beta", "arbitrary", "beta");
    semantic_beta["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    let mut facts = rows_from_file(&operation_cut.join("program_facts.jsonl"));
    facts.push(semantic_beta);
    jsonl(&candidate, &facts);
    let child = assess_with_receipts(
        &operation_cut.join("maintainer_scope_skills.jsonl"),
        Some(&candidate),
        3,
        Some(&digest(&after_bytes)),
        Some(&operation_cut.join("operation-evidence")),
    )
    .unwrap();
    let child_bytes = serde_json::to_vec(&child).unwrap();
    fs::write(&after_path, &child_bytes).unwrap();
    let result = compare(&after_bytes, &child_bytes, &["beta".into()]).unwrap();
    let result_path = root.join("semantic-result.json");
    fs::write(&result_path, serde_json::to_vec(&result).unwrap()).unwrap();
    let proposal_receipt = root.join("proposal-receipt.json");
    fs::write(&proposal_receipt, serde_json::to_vec(&json!({"acceptedFactId":"semantic-beta","scopeSkillId":"beta","sourceAssessmentSha256":digest(&after_bytes)})).unwrap()).unwrap();
    let semantic_cut = root.join("semantic-cut");
    let repo_root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let response = std::process::Command::new("python3")
        .current_dir(repo_root)
        .args([
            "scripts/maintainer-skill-tablegit.py",
            "stage",
            "--base",
            operation_cut.to_str().unwrap(),
            "--candidate-program-facts",
            candidate.to_str().unwrap(),
            "--candidate-assessment",
            after_path.to_str().unwrap(),
            "--result",
            result_path.to_str().unwrap(),
            "--receipt",
            proposal_receipt.to_str().unwrap(),
            "--run-id",
            "beta",
            "--github-repository",
            "example/arbitrary",
            "--output",
            semantic_cut.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(
        response.status.success(),
        "{}",
        String::from_utf8_lossy(&response.stderr)
    );
    let portable = assess_with_receipts(
        &semantic_cut.join("maintainer_scope_skills.jsonl"),
        Some(&semantic_cut.join("program_facts.jsonl")),
        3,
        Some(&digest(&after_bytes)),
        Some(&semantic_cut.join("operation-evidence")),
    )
    .unwrap();
    assert_eq!(portable, child);
    // Exercise the real writer preflight without creating any network client.
    let preflight = std::process::Command::new("python3").current_dir(repo_root)
        .args(["-c", "import importlib.util,sys; from pathlib import Path; s=importlib.util.spec_from_file_location('writer','scripts/maintainer-skill-tablegit.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); files=m.operation_evidence_files(Path(sys.argv[1])); assert 'operation-evidence/alpha.json' in files", semantic_cut.to_str().unwrap()])
        .output().unwrap();
    assert!(
        preflight.status.success(),
        "{}",
        String::from_utf8_lossy(&preflight.stderr)
    );
    receipt["scope"]["scopeSkillIds"] = json!(["beta"]);
    let beta_bytes = serde_json::to_vec(&receipt).unwrap();
    let receipt_root = semantic_cut.join("operation-evidence");
    fs::write(receipt_root.join("beta.json"), &beta_bytes).unwrap();
    facts = rows_from_file(&semantic_cut.join("program_facts.jsonl"));
    facts.push(
        prepare_fact(
            &scope("beta", "arbitrary"),
            json!({"path":"beta.json","sha256":digest(&beta_bytes)}),
            &receipt_root,
        )
        .unwrap(),
    );
    jsonl(&candidate, &facts);
    let final_report = assess_with_receipts(
        &semantic_cut.join("maintainer_scope_skills.jsonl"),
        Some(&candidate),
        4,
        Some(&digest(&child_bytes)),
        Some(&receipt_root),
    )
    .unwrap();
    fs::write(&before_path, &child_bytes).unwrap();
    fs::write(&after_path, serde_json::to_vec(&final_report).unwrap()).unwrap();
    let final_cut = root.join("final-cut");
    stage(
        &semantic_cut,
        &candidate,
        &before_path,
        &after_path,
        &receipt_root,
        &["beta".into()],
        "beta-operation",
        false,
        &final_cut,
    )
    .unwrap();
    fs::remove_dir_all(&operation_cut).unwrap();
    fs::remove_dir_all(&semantic_cut).unwrap();
    let final_portable = assess_with_receipts(
        &final_cut.join("maintainer_scope_skills.jsonl"),
        Some(&final_cut.join("program_facts.jsonl")),
        4,
        Some(&digest(&child_bytes)),
        Some(&final_cut.join("operation-evidence")),
    )
    .unwrap();
    assert_eq!(final_portable, final_report);
    assert_eq!(final_portable["totals"]["maintenanceReadyCount"], 2);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn productive_rounds_retain_inherited_receipts_without_original_machine() {
    use agentlab_code_analysis::{
        maintainer_operation_evidence::prepare_fact, maintainer_operation_stage::stage,
    };
    let root = temp_root();
    let mut base = root.join("base");
    fs::create_dir_all(base.join("assessments")).unwrap();
    let scope_rows = [
        scope("alpha", "arbitrary"),
        scope("beta", "arbitrary"),
        scope("gamma", "arbitrary"),
    ];
    jsonl(&base.join("maintainer_scope_skills.jsonl"), &scope_rows);
    let mut facts = scope_rows
        .iter()
        .map(|skill| {
            let id = skill["id"].as_str().unwrap();
            let mut fact = complete_fact(&format!("semantic-{id}"), "arbitrary", id);
            fact["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
            fact
        })
        .collect::<Vec<_>>();
    jsonl(&base.join("program_facts.jsonl"), &facts);
    jsonl(&base.join("maintainer_skills.jsonl"), &[]);
    jsonl(&base.join("evaluation_cases.jsonl"), &[]);
    fs::write(base.join("maintainer-knowledge-cut.json"), b"{}\n").unwrap();
    let mut receipts = root.join("original-machine");
    fs::create_dir(&receipts).unwrap();
    let mut before = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        1,
        None,
        Some(&receipts),
    )
    .unwrap();
    let bytes = serde_json::to_vec(&before).unwrap();
    fs::write(base.join("assessments/parent.json"), &bytes).unwrap();
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &[json!({
            "id":"parent", "roundIndex":1, "coverage":{},
            "assessment":{"path":"assessments/parent.json","sha256":digest(&bytes)}
        })],
    );
    for (index, skill) in scope_rows.iter().enumerate() {
        let id = skill["id"].as_str().unwrap();
        let mut receipt = build_receipt();
        receipt["scope"]["scopeSkillIds"] = json!([id]);
        let receipt_bytes = serde_json::to_vec(&receipt).unwrap();
        let name = format!("{id}.json");
        fs::write(receipts.join(&name), &receipt_bytes).unwrap();
        facts.push(
            prepare_fact(
                skill,
                json!({"path":name,"sha256":digest(&receipt_bytes)}),
                &receipts,
            )
            .unwrap(),
        );
        let candidate = root.join(format!("candidate-{index}.jsonl"));
        jsonl(&candidate, &facts);
        let before_bytes = serde_json::to_vec(&before).unwrap();
        let after = assess_with_receipts(
            &base.join("maintainer_scope_skills.jsonl"),
            Some(&candidate),
            index as u64 + 2,
            Some(&digest(&before_bytes)),
            Some(&receipts),
        )
        .unwrap();
        let before_path = root.join("before.json");
        let after_path = root.join("after.json");
        fs::write(&before_path, &before_bytes).unwrap();
        fs::write(&after_path, serde_json::to_vec(&after).unwrap()).unwrap();
        let output = root.join(format!("stage-{index}"));
        let manifest = stage(
            &base,
            &candidate,
            &before_path,
            &after_path,
            &receipts,
            &[id.to_owned()],
            &format!("round-{index}"),
            false,
            &output,
        )
        .unwrap();
        assert_eq!(
            manifest["operationEvidence"]["receipts"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            manifest["operationEvidence"]["inheritedReceipts"]
                .as_array()
                .unwrap()
                .len(),
            index
        );
        assert_eq!(manifest["automaticPromotion"], false);
        let portable = assess_with_receipts(
            &output.join("maintainer_scope_skills.jsonl"),
            Some(&output.join("program_facts.jsonl")),
            index as u64 + 2,
            Some(&digest(&before_bytes)),
            Some(&output.join("operation-evidence")),
        )
        .unwrap();
        assert_eq!(portable, after);
        assert_eq!(portable["totals"]["maintenanceReadyCount"], index + 1);
        if index > 0 {
            let saved = fs::read(receipts.join("alpha.json")).unwrap();
            fs::write(receipts.join("alpha.json"), b"tampered").unwrap();
            let rejected = root.join(format!("rejected-{index}"));
            assert!(stage(
                &base,
                &candidate,
                &before_path,
                &after_path,
                &receipts,
                &[id.to_owned()],
                &format!("bad-{index}"),
                false,
                &rejected
            )
            .is_err());
            assert!(!rejected.exists());
            fs::write(receipts.join("alpha.json"), saved).unwrap();
        }
        // The next worker receives only the portable bundle plus its new
        // receipt; the previous worker's receipt directory no longer exists.
        let next_receipts = root.join(format!("worker-{}", index + 1));
        fs::create_dir(&next_receipts).unwrap();
        for row in manifest["operationEvidence"]["receipts"]
            .as_array()
            .unwrap()
            .iter()
            .chain(
                manifest["operationEvidence"]["inheritedReceipts"]
                    .as_array()
                    .unwrap(),
            )
        {
            let path = row["path"].as_str().unwrap();
            fs::copy(
                output.join(path),
                next_receipts.join(path.strip_prefix("operation-evidence/").unwrap()),
            )
            .unwrap();
        }
        fs::remove_dir_all(&receipts).unwrap();
        receipts = next_receipts;
        base = output;
        before = after;
    }
    fs::remove_dir_all(&receipts).unwrap();
    let report = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        4,
        before["parentAssessmentSha256"].as_str(),
        Some(&base.join("operation-evidence")),
    )
    .unwrap();
    assert_eq!(report, before);
    assert_eq!(report["totals"]["maintenanceReadyCount"], 3);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_cli_prepares_repeatable_candidate_cut_and_advances_one_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(
        &scopes,
        &[
            scope("scope", "arbitrary"),
            scope("unselected", "arbitrary"),
        ],
    );
    let mut semantic = complete_fact("semantic", "arbitrary", "scope");
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&facts, &[semantic]);
    let original = fs::read(&facts).unwrap();
    let receipt_bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &receipt_bytes).unwrap();
    let before = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(before["totals"]["maintenanceReadyCount"], 0);
    let prepare = |output: &Path, receipt_sha: &str| {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--scope-skills",
                scopes.to_str().unwrap(),
                "--program-facts",
                facts.to_str().unwrap(),
                "--prepare-operation-fact",
                "scope",
                "--operation-receipts-root",
                root.to_str().unwrap(),
                "--operation-receipt",
                "build.json",
                "--operation-receipt-sha256",
                receipt_sha,
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    let candidate = root.join("candidate.jsonl");
    let success = prepare(&candidate, &digest(&receipt_bytes));
    assert!(
        success.status.success(),
        "{}",
        String::from_utf8_lossy(&success.stderr)
    );
    assert_eq!(fs::read(&facts).unwrap(), original);
    assert_eq!(rows_from_file(&candidate).len(), 2);
    let parent = digest(&serde_json::to_vec(&before).unwrap());
    let after =
        assess_with_receipts(&scopes, Some(&candidate), 2, Some(&parent), Some(&root)).unwrap();
    assert_eq!(after["totals"]["semanticReadyCount"], 1);
    assert_eq!(after["totals"]["maintenanceReadyCount"], 1);
    assert_eq!(after["automaticPromotion"], false);
    let selected = vec!["scope".to_owned()];
    let before_bytes = serde_json::to_vec(&before).unwrap();
    let after_bytes = serde_json::to_vec(&after).unwrap();
    let result = agentlab_code_analysis::maintainer_operation_evidence::compare_round(
        &before_bytes,
        &after_bytes,
        &selected,
    )
    .unwrap();
    assert_eq!(result["decision"], "review-proposed-operation-knowledge");
    assert_eq!(result["maintenanceReadyDelta"], 1);
    let base = root.join("base");
    fs::create_dir(&base).unwrap();
    fs::create_dir(base.join("assessments")).unwrap();
    fs::copy(&scopes, base.join("maintainer_scope_skills.jsonl")).unwrap();
    fs::copy(&facts, base.join("program_facts.jsonl")).unwrap();
    jsonl(
        &base.join("maintainer_skills.jsonl"),
        &[json!({"id":"process"})],
    );
    jsonl(&base.join("evaluation_cases.jsonl"), &[]);
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &[json!({
            "id":"parent", "roundIndex":4, "coverage":{"trackedFileCount":2},
            "assessment":{"path":"assessments/parent.json","sha256":digest(&before_bytes)}
        })],
    );
    fs::write(base.join("maintainer-knowledge-cut.json"), b"{}\n").unwrap();
    fs::write(base.join("assessments/parent.json"), &before_bytes).unwrap();
    let before_file = root.join("before.json");
    let after_file = root.join("after.json");
    fs::write(&before_file, &before_bytes).unwrap();
    fs::write(&after_file, &after_bytes).unwrap();
    let stage = |output: &Path, candidate: &Path, after: &Path| {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--stage-operation-round",
                "--base",
                base.to_str().unwrap(),
                "--program-facts",
                candidate.to_str().unwrap(),
                "--before",
                before_file.to_str().unwrap(),
                "--after",
                after.to_str().unwrap(),
                "--operation-receipts-root",
                root.to_str().unwrap(),
                "--selected-scope",
                "scope",
                "--run-id",
                "generic-run",
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    let staged = root.join("stage");
    let response = stage(&staged, &candidate, &after_file);
    assert!(
        response.status.success(),
        "{}",
        String::from_utf8_lossy(&response.stderr)
    );
    assert_eq!(
        fs::read(staged.join("program_facts.jsonl")).unwrap(),
        fs::read(&candidate).unwrap()
    );
    for table in [
        "maintainer_skills",
        "maintainer_scope_skills",
        "evaluation_cases",
    ] {
        assert_eq!(
            fs::read(staged.join(format!("{table}.jsonl"))).unwrap(),
            fs::read(base.join(format!("{table}.jsonl"))).unwrap()
        );
    }
    let rounds = rows_from_file(&staged.join("maintainer_skill_refresh_rounds.jsonl"));
    assert_eq!(rounds.len(), 2);
    assert_eq!(
        rounds.iter().find(|r| r["roundIndex"] == 5).unwrap()["automaticPromotion"],
        false
    );
    assert!(!stage(&staged, &candidate, &after_file).status.success());
    let operation = rows_from_file(&candidate)
        .into_iter()
        .find(|row| row["dimensions"] == json!(["operation"]))
        .unwrap();
    let portable_root = staged.join("operation-evidence");
    assert_eq!(
        fs::read(portable_root.join("build.json")).unwrap(),
        receipt_bytes
    );
    fs::remove_file(root.join("build.json")).unwrap();
    assert!(
        agentlab_code_analysis::maintainer_operation_evidence::verify(
            &operation,
            &scope("scope", "arbitrary"),
            &portable_root
        )
        .is_ok()
    );
    fs::write(portable_root.join("build.json"), b"tampered").unwrap();
    assert!(
        agentlab_code_analysis::maintainer_operation_evidence::verify(
            &operation,
            &scope("scope", "arbitrary"),
            &portable_root
        )
        .is_err()
    );
    fs::write(portable_root.join("build.json"), &receipt_bytes).unwrap();
    fs::write(root.join("build.json"), &receipt_bytes).unwrap();
    let forged = root.join("forged.json");
    let mut forged_report = after.clone();
    forged_report["nextRoundObjectives"] = json!([]);
    fs::write(&forged, serde_json::to_vec(&forged_report).unwrap()).unwrap();
    let rejected_stage = root.join("rejected-stage");
    assert!(!stage(&rejected_stage, &candidate, &forged).status.success());
    assert!(!rejected_stage.exists());
    let mut legacy_parent = before.clone();
    legacy_parent["standard"]["operationEvidencePolicy"] = json!("legacy-explicit-claim");
    let legacy_bytes = serde_json::to_vec(&legacy_parent).unwrap();
    fs::write(base.join("assessments/parent.json"), &legacy_bytes).unwrap();
    let mut parent_rows = rows_from_file(&base.join("maintainer_skill_refresh_rounds.jsonl"));
    parent_rows[0]["assessment"]["sha256"] = json!(digest(&legacy_bytes));
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &parent_rows,
    );
    assert!(!stage(&rejected_stage, &candidate, &after_file)
        .status
        .success());
    assert!(!rejected_stage.exists());
    agentlab_code_analysis::maintainer_operation_stage::stage(
        &base,
        &candidate,
        &before_file,
        &after_file,
        &root,
        &selected,
        "explicit-rebaseline",
        true,
        &rejected_stage,
    )
    .unwrap();
    let migrated = rows_from_file(&rejected_stage.join("maintainer_skill_refresh_rounds.jsonl"));
    let latest = migrated.iter().find(|row| row["roundIndex"] == 5).unwrap();
    assert_eq!(latest["baselineReassessment"]["performed"], true);
    assert_eq!(
        latest["baselineReassessment"]["countsAsMaturityGain"],
        false
    );
    let changed_facts = root.join("changed-facts.jsonl");
    let mut changed = rows_from_file(&candidate);
    let semantic = changed.iter_mut().find(|r| r["id"] == "semantic").unwrap();
    semantic["interpretation"] = json!("unrelated semantic mutation");
    jsonl(&changed_facts, &changed);
    assert!(!stage(&rejected_stage, &changed_facts, &after_file)
        .status
        .success());
    assert_eq!(fs::read(&facts).unwrap(), original);
    for (pointer, value) in [
        ("/parentAssessmentSha256", json!("0".repeat(64))),
        ("/roundIndex", json!(7)),
        (
            "/standard/operationEvidencePolicy",
            json!("legacy-explicit-claim"),
        ),
        ("/totals/semanticReadyCount", json!(2)),
        ("/totals/maintenanceReadyCount", json!(2)),
        ("/inputs/scopeSkillsSha256", json!("0".repeat(64))),
        ("/skills/0/sourceRevision", json!("9".repeat(40))),
        ("/skills/1/maturity", json!("L3-maintenance-ready")),
    ] {
        let mut invalid = after.clone();
        *invalid.pointer_mut(pointer).unwrap() = value;
        assert!(
            agentlab_code_analysis::maintainer_operation_evidence::compare_round(
                &before_bytes,
                &serde_json::to_vec(&invalid).unwrap(),
                &selected
            )
            .is_err(),
            "{pointer}"
        );
    }
    let no_change = assess_with_receipts(
        &scopes,
        Some(&candidate),
        3,
        Some(&digest(&after_bytes)),
        Some(&root),
    )
    .unwrap();
    let replay_result = agentlab_code_analysis::maintainer_operation_evidence::compare_round(
        &after_bytes,
        &serde_json::to_vec(&no_change).unwrap(),
        &selected,
    )
    .unwrap();
    assert_eq!(replay_result["decision"], "no-change");
    assert_eq!(replay_result["maintenanceReadyDelta"], 0);
    let replay = root.join("replay.jsonl");
    assert!(prepare(&replay, &digest(&receipt_bytes)).status.success());
    assert_eq!(fs::read(&candidate).unwrap(), fs::read(&replay).unwrap());
    assert!(!prepare(&candidate, &digest(&receipt_bytes))
        .status
        .success());
    let rejected = root.join("rejected.jsonl");
    assert!(!prepare(&rejected, &"0".repeat(64)).status.success());
    assert!(!rejected.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_operation_receipts_close_only_content_verified_build_gaps() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary")]);
    let mut fact = complete_fact("fact", "arbitrary", "scope");
    jsonl(&facts, &[fact.clone()]);
    let unverified = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(unverified["skills"][0]["maturity"], "L2-semantic-ready");
    assert_eq!(
        unverified["gapCounts"]["MS-OPERATION-RECEIPT-UNVERIFIED"],
        1
    );
    let bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &bytes).unwrap();
    fact["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
    jsonl(&facts, &[fact.clone()]);
    let verified = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(verified["skills"][0]["maturity"], "L3-maintenance-ready");
    assert_eq!(
        verified["standard"]["operationEvidencePolicy"],
        "verified-receipt-content"
    );
    assert_eq!(
        verified["skills"][0]["operationEvidenceChecks"]["fact"]["typeChecking"],
        "not-qualified"
    );
    assert_eq!(
        verified["skills"][0]["operationEvidenceChecks"]["fact"]["qualificationScope"]["runtime"],
        false
    );
    assert_eq!(
        verified,
        assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap()
    );
    fact["operationEvidence"]["sha256"] = json!("e".repeat(64));
    jsonl(&facts, &[fact]);
    let tampered = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(tampered["skills"][0]["maturity"], "L2-semantic-ready");
    assert_eq!(
        tampered["skills"][0]["operationEvidenceChecks"]["fact"]["reason"],
        "operation receipt digest mismatch"
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_receipt_rejects_failed_stale_borrowed_and_overclaimed_operations() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary")]);
    for (pointer, value) in [
        ("/status", json!("blocked")),
        ("/schema", json!("unsupported-runtime-schema")),
        ("/source/revision", json!("9".repeat(40))),
        ("/source/repositoryId", json!("another-repository")),
        ("/source/cleanAfter", json!(false)),
        ("/scope/scopeSkillIds", json!(["sibling"])),
        ("/scope/lane", json!("runtime")),
        ("/toolchain/sdkRelease", Value::Null),
        ("/dependencyPreparation/exitCode", json!(1)),
        ("/build/attempts/1/exitCode", json!(1)),
        (
            "/build/attempts/1/executionAuthority/operationId",
            json!("run-one"),
        ),
        (
            "/build/attempts/1/canonicalMemberSha256",
            json!("f".repeat(64)),
        ),
        ("/build/rawArchiveReproducible", json!(false)),
        ("/qualificationScope/runtime", json!(true)),
        ("/qualificationScope/tests", json!(true)),
        ("/qualificationScope/performance", json!(true)),
        ("/limitations", json!([])),
    ] {
        let mut receipt = build_receipt();
        *receipt.pointer_mut(pointer).unwrap() = value;
        let bytes = serde_json::to_vec(&receipt).unwrap();
        fs::write(root.join("build.json"), &bytes).unwrap();
        let mut fact = complete_fact("fact", "arbitrary", "scope");
        fact["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
        jsonl(&facts, &[fact]);
        let report = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
        assert_eq!(
            report["skills"][0]["maturity"], "L2-semantic-ready",
            "{pointer}"
        );
        assert_eq!(
            report["skills"][0]["operationEvidenceChecks"]["fact"]["status"], "rejected",
            "{pointer}"
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_receipt_rejects_traversal_missing_files_and_symlinks() {
    let root = temp_root();
    let skill = scope("scope", "arbitrary");
    for path in ["../outside.json", "/absolute.json", "missing.json"] {
        let mut fact = complete_fact("fact", "arbitrary", "scope");
        fact["operationEvidence"] = json!({"path":path,"sha256":"a".repeat(64)});
        assert!(
            agentlab_code_analysis::maintainer_operation_evidence::verify(&fact, &skill, &root)
                .is_err()
        );
    }
    #[cfg(unix)]
    {
        fs::write(
            root.join("real.json"),
            serde_json::to_vec(&build_receipt()).unwrap(),
        )
        .unwrap();
        std::os::unix::fs::symlink(root.join("real.json"), root.join("link.json")).unwrap();
        let mut fact = complete_fact("fact", "arbitrary", "scope");
        fact["operationEvidence"] = json!({"path":"link.json","sha256":"a".repeat(64)});
        assert!(
            agentlab_code_analysis::maintainer_operation_evidence::verify(&fact, &skill, &root)
                .unwrap_err()
                .contains("symlink")
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn stale_or_missing_source_identity_cannot_advance_any_dimension() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    for revision in [json!("9".repeat(40)), Value::Null, json!("main")] {
        let mut fact = complete_fact("fact", "arbitrary-repository", "scope");
        fact["sourceRevision"] = revision;
        jsonl(&facts, &[fact]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["totals"]["programBoundCount"], 0);
        assert_eq!(report["totals"]["semanticReadyCount"], 0);
        assert_eq!(report["totals"]["maintenanceReadyCount"], 0);
        assert_eq!(report["skills"][0]["provenDimensions"], json!([]));
        assert_eq!(
            report["skills"][0]["rejectedEvidenceBindings"][0]["reason"],
            "source-revision-mismatch"
        );
        assert_eq!(report["gapCounts"]["MS-EVIDENCE-IDENTITY-MISMATCH"], 1);
    }
    jsonl(
        &facts,
        &[complete_fact("fact", "arbitrary-repository", "scope")],
    );
    let refreshed = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(refreshed["decision"], "ready");
    assert_eq!(
        refreshed["skills"][0]["rejectedEvidenceBindings"],
        json!([])
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn inherited_cross_repository_or_stale_facts_are_not_semantic_proof() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    let mut anchor = complete_fact("anchor", "arbitrary-repository", "scope");
    anchor["dimensions"] = json!(["boundary"]);
    for (repository, revision) in [
        ("different-repository", "1".repeat(40)),
        ("arbitrary-repository", "9".repeat(40)),
    ] {
        let mut inherited = complete_fact("inherited", repository, "scope");
        inherited["sourceRevision"] = json!(revision);
        inherited["scopeSkillIds"] = json!([]);
        inherited["evidence"] = json!([]);
        inherited["evidenceFactIds"] = json!(["anchor"]);
        jsonl(&facts, &[anchor.clone(), inherited]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["totals"]["semanticReadyCount"], 0);
        assert_eq!(
            report["skills"][0]["evidenceBindings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            report["skills"][0]["rejectedEvidenceBindings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn implicit_operation_binding_never_qualifies_a_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    let mut semantic = complete_fact("semantic", "arbitrary-repository", "scope");
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    for inherit in [false, true] {
        let mut operation = complete_fact("operation", "arbitrary-repository", "scope");
        operation["dimensions"] = json!(["operation"]);
        operation["scopeSkillIds"] = json!([]);
        if inherit {
            operation["evidence"] = json!([]);
            operation["evidenceFactIds"] = json!(["semantic"]);
        }
        jsonl(&facts, &[semantic.clone(), operation.clone()]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["skills"][0]["maturity"], "L2-semantic-ready");
        let binding = report["skills"][0]["evidenceBindings"]
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["factId"] == "operation")
            .unwrap();
        assert_eq!(binding["dimensions"], json!([]));
        operation["scopeSkillIds"] = json!(["scope"]);
        jsonl(&facts, &[semantic.clone(), operation]);
        let qualified = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(qualified["skills"][0]["maturity"], "L3-maintenance-ready");
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn generic_evidence_rounds_advance_arbitrary_repositories_without_name_rules() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(
        &scopes,
        &[
            scope("skill-scope-alpha-src", "alpha-library"),
            scope("skill-scope-beta-src", "beta-service"),
        ],
    );

    let first = assess(&scopes, None, 1, None).unwrap();
    assert_eq!(first["decision"], "continue");
    assert_eq!(first["totals"]["structuralReadyCount"], 2);
    assert_eq!(first["totals"]["programBoundCount"], 0);
    assert_eq!(first["totals"]["semanticReadyCount"], 0);
    assert_eq!(first["totals"]["maintenanceReadyCount"], 0);

    jsonl(
        &facts,
        &[
            complete_fact(
                "fact-alpha-contract",
                "alpha-library",
                "skill-scope-alpha-src",
            ),
            complete_fact("fact-beta-contract", "beta-service", "skill-scope-beta-src"),
        ],
    );
    let first_bytes = serde_json::to_vec_pretty(&first).unwrap();
    let parent = digest(&first_bytes);
    let second = assess(&scopes, Some(&facts), 2, Some(&parent)).unwrap();
    assert_eq!(second["decision"], "ready");
    assert_eq!(second["totals"]["programBoundCount"], 2);
    assert_eq!(second["totals"]["semanticReadyCount"], 2);
    assert_eq!(second["totals"]["maintenanceReadyCount"], 2);
    assert!(second["repositories"]
        .as_array()
        .unwrap()
        .iter()
        .all(|repository| repository["readyForCaseGeneration"] == true));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn operation_maturity_requires_explicit_revision_bound_dimension() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("skill-scope-alpha-src", "alpha-library")]);
    jsonl(
        &facts,
        &[
            json!({
                "id":"fact-alpha-semantic",
                "kind":"semantic-contract",
                "repositoryId":"alpha-library",
                "sourceRevision":"1".repeat(40),
                "scopeSkillIds":["skill-scope-alpha-src"],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}]
            }),
            json!({
                "id":"fact-alpha-blocked-build-preflight",
                "kind":"build-test-entrypoint",
                "repositoryId":"alpha-library",
                "sourceRevision":"1".repeat(40),
                "scopeSkillIds":["skill-scope-alpha-src"],
                "evidence":[{"path":"qualification.json","sha256":"4".repeat(64)}]
            }),
        ],
    );
    let blocked = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(blocked["totals"]["semanticReadyCount"], 1);
    assert_eq!(blocked["totals"]["maintenanceReadyCount"], 0);
    assert_eq!(blocked["skills"][0]["maturity"], "L2-semantic-ready");
    assert!(blocked["skills"][0]["gaps"]
        .as_array()
        .unwrap()
        .iter()
        .any(|gap| gap["code"] == "MS-OPERATION-EVIDENCE-MISSING"));

    let mut rows = rows_from_file(&facts);
    rows.push(json!({
        "id":"verification-alpha-runtime",
        "kind":"runtime-verification",
        "repositoryId":"alpha-library",
        "sourceRevision":"1".repeat(40),
        "scopeSkillIds":["skill-scope-alpha-src"],
        "dimensions":["operation"],
        "evidence":[{"path":"qualified-runtime.json","sha256":"5".repeat(64)}]
    }));
    jsonl(&facts, &rows);
    let qualified = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(qualified["totals"]["maintenanceReadyCount"], 1);
    assert_eq!(qualified["skills"][0]["maturity"], "L3-maintenance-ready");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn composite_selectors_bind_exact_owned_paths_and_reject_shared_anchor_siblings() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let mut one = scope("skill-scope-arbitrary-one", "arbitrary");
    one["ownershipSelectors"] = json!([
        {"type":"prefix","path":"src/one"},
        {"type":"files","paths":["src/root.generic"]}
    ]);
    one["evidence"] = json!([{"path":"src/one/main.generic","gitBlobOid":"3".repeat(40)}]);
    let mut two = scope("skill-scope-arbitrary-two", "arbitrary");
    two["ownershipSelectors"] = json!([{"type":"prefix","path":"src/two"}]);
    two["evidence"] = json!([{"path":"src/two/main.generic","gitBlobOid":"4".repeat(40)}]);
    jsonl(&scopes, &[one, two]);
    jsonl(
        &facts,
        &[
            json!({
                "id":"fact-one", "kind":"semantic-contract", "repositoryId":"arbitrary",
                "sourceRevision":"1".repeat(40), "scopeSkillIds":[],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/root.generic","gitBlobOid":"5".repeat(40)}]
            }),
            json!({
                "id":"fact-two", "kind":"semantic-contract", "repositoryId":"arbitrary",
                "sourceRevision":"1".repeat(40), "scopeSkillIds":[],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/two/main.generic","gitBlobOid":"4".repeat(40)}]
            }),
        ],
    );
    let assessment = assess(&scopes, Some(&facts), 1, None).unwrap();
    let rows = assessment["skills"].as_array().unwrap();
    let first = rows
        .iter()
        .find(|row| row["skillId"] == "skill-scope-arbitrary-one")
        .unwrap();
    let second = rows
        .iter()
        .find(|row| row["skillId"] == "skill-scope-arbitrary-two")
        .unwrap();
    assert_eq!(first["checks"]["programEvidenceBound"], true);
    assert_eq!(second["checks"]["programEvidenceBound"], true);
    assert_eq!(first["evidenceBindings"][0]["factId"], "fact-one");
    assert_eq!(second["evidenceBindings"][0]["factId"], "fact-two");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn legacy_virtual_boundaries_retain_v1_identity_compatibility() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let mut legacy = scope("skill-scope-arbitrary-support", "arbitrary");
    legacy["pathBoundary"] = json!("src/_support");
    legacy["evidence"] = json!([{
        "path":"src/build-profile.json5", "gitBlobOid":"3".repeat(40)
    }]);
    jsonl(&scopes, &[legacy]);
    let assessment = assess(&scopes, None, 1, None).unwrap();
    assert_eq!(assessment["totals"]["structuralReadyCount"], 1);
    assert_eq!(assessment["skills"][0]["checks"]["identityReady"], true);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn explicit_fact_binding_cannot_name_a_missing_or_cross_repository_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("skill-scope-alpha-src", "alpha-library")]);
    jsonl(
        &facts,
        &[complete_fact(
            "fact-beta-contract",
            "beta-service",
            "skill-scope-alpha-src",
        )],
    );
    let error = assess(&scopes, Some(&facts), 1, None).unwrap_err();
    assert!(error.contains("crosses repository boundary"));
    fs::remove_dir_all(root).unwrap();
}
