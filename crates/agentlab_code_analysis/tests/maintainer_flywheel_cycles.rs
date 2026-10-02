#![cfg(unix)]
use agentlab_code_analysis::{
    digest,
    maintainer_flywheel_cycles::{execute, resume},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

// A compiled Rust transport fixture, not an Agent or semantic qualification.
const ADAPTER: &str = r#"
use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::{fs,path::Path};
fn sha(b:&[u8])->String {format!("{:x}",Sha256::digest(b))}
fn main() {
 let args:Vec<String>=std::env::args().collect();
 let bytes=fs::read(&args[2]).unwrap(); let r:Value=serde_json::from_slice(&bytes).unwrap();
 let dir=Path::new(&args[2]).parent().unwrap();
 let stage=r["stage"].as_str().unwrap();
 let status=if args[1]=="review" && stage=="evidence-return" {"review-required"} else if args[1]=="reject" {"rejected"} else {"completed"};
 if args[1]=="exit" {std::process::exit(7);}
 let input=fs::read(r["inputState"]["path"].as_str().unwrap()).unwrap();
 if args[1]=="tamper" {fs::write(r["inputState"]["path"].as_str().unwrap(),b"changed").unwrap();}
 let state=if args[1]=="repeat" {input} else {serde_json::to_vec(&json!({"round":r["round"],"stage":stage,"hasModelEnvironment":std::env::var_os("AGENTLAB_MODEL").is_some()})).unwrap()};
 fs::write(dir.join("state.json"),&state).unwrap();
 let request_sha=if args[1]=="borrowed" {"wrong".into()} else {sha(&bytes)};
 println!("{}",json!({"schema":"agentlab.flywheel_stage_result.v1","round":r["round"],"stage":stage,
 "requestSha256":request_sha,"inputStateSha256":r["inputState"]["sha256"],"status":status,
 "outputState":{"path":"state.json","sha256":sha(&state)},"automaticPromotion":false}));
}
"#;

fn library(name: &str) -> PathBuf {
    let deps = std::env::current_exe()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    fs::read_dir(deps)
        .unwrap()
        .map(|p| p.unwrap().path())
        .filter(|p| {
            p.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with(&format!("lib{name}-"))
                && p.extension().is_some_and(|e| e == "rlib")
        })
        .max_by_key(|p| fs::metadata(p).unwrap().modified().unwrap())
        .unwrap()
}
fn fixture() -> (PathBuf, Value) {
    static SEQUENCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "flywheel-cycles-{}-{}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    fs::write(root.join("adapter.rs"), ADAPTER).unwrap();
    let binary = root.join("adapter");
    let deps = std::env::current_exe()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    let compile = Command::new("rustc")
        .args(["--edition=2021", "--crate-name", "cycle_adapter"])
        .arg(root.join("adapter.rs"))
        .arg("--extern")
        .arg(format!("serde_json={}", library("serde_json").display()))
        .arg("--extern")
        .arg(format!("sha2={}", library("sha2").display()))
        .arg("-L")
        .arg(format!("dependency={}", deps.display()))
        .arg("-o")
        .arg(&binary)
        .output()
        .unwrap();
    assert!(
        compile.status.success(),
        "{}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let initial = root.join("initial.json");
    fs::write(&initial, b"{}").unwrap();
    // Freshly linked native test adapters can incur cold-launch latency under
    // parallel regression load. This fixture allowance is not an Agent budget.
    let command = json!({"program":binary,"programSha256":digest(&fs::read(&binary).unwrap()),"cwd":".","timeoutMs":30_000,"args":["advance","{request}"]});
    let stages = [
        "repository-understanding",
        "program-analysis",
        "maintenance-verification",
        "case-execution",
        "evidence-return",
    ]
    .map(|s| json!({"stage":s,"command":command}));
    let recipe = json!({"schema":"agentlab.flywheel_cycles_recipe.v1","reviewed":true,"automaticPromotion":false,"maximumRounds":2,
        "immutableInputs":[{"path":root.join("adapter.rs"),"sha256":digest(ADAPTER.as_bytes())}],
        "initialState":{"path":initial,"sha256":digest(b"{}")},"stages":stages});
    (root, recipe)
}
fn run(root: &Path, recipe: &Value, name: &str) -> Result<Value, String> {
    execute(&serde_json::to_vec(recipe).unwrap(), &root.join(name))
}

#[test]
fn bounded_chunks_continue_without_reexecuting_completed_stages() {
    let (root, mut recipe) = fixture();
    recipe["maximumStagesPerInvocation"] = json!(3);
    let bytes = serde_json::to_vec(&recipe).unwrap();
    let mut previous = run(&root, &recipe, "chunk-0").unwrap();
    assert_eq!(previous["status"], "checkpoint-ready");
    for chunk in 1..=3 {
        let step = previous["stages"].as_array().unwrap().len();
        let checkpoint = root.join(format!("chunk-{}/checkpoint-{step}.json", chunk - 1));
        let sha = digest(&fs::read(&checkpoint).unwrap());
        let out = root.join(format!("chunk-{chunk}"));
        previous = resume(&bytes, &out, &checkpoint, &sha).unwrap();
        let dirs = fs::read_dir(&out)
            .unwrap()
            .filter(|e| {
                e.as_ref()
                    .unwrap()
                    .file_name()
                    .to_string_lossy()
                    .starts_with("round-")
            })
            .count();
        assert_eq!(dirs, if chunk == 3 { 1 } else { 3 });
        assert!(resume(
            &bytes,
            &root.join(format!("duplicate-{chunk}")),
            &checkpoint,
            &sha
        )
        .unwrap_err()
        .contains("claimed"));
    }
    assert_eq!(previous["completedRounds"], 2);
    assert_eq!(previous["stages"].as_array().unwrap().len(), 10);
    assert_eq!(previous["status"], "round-budget-exhausted");
    assert_eq!(previous["qualified"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn resume_rejects_drift_and_uncertain_dispatch_before_new_commands() {
    let (root, mut recipe) = fixture();
    recipe["maximumStagesPerInvocation"] = json!(1);
    run(&root, &recipe, "first").unwrap();
    let checkpoint = root.join("first/checkpoint-1.json");
    let sha = digest(&fs::read(&checkpoint).unwrap());
    let bytes = serde_json::to_vec(&recipe).unwrap();
    assert!(resume(&bytes, &root.join("bad-sha"), &checkpoint, "wrong")
        .unwrap_err()
        .contains("digest mismatch"));
    let mut other = recipe.clone();
    other["maximumRounds"] = json!(3);
    assert!(resume(
        &serde_json::to_vec(&other).unwrap(),
        &root.join("bad-recipe"),
        &checkpoint,
        &sha
    )
    .unwrap_err()
    .contains("identity"));
    let uncertain = root.join("first/round-0-program-analysis");
    fs::create_dir(&uncertain).unwrap();
    assert!(resume(&bytes, &root.join("uncertain"), &checkpoint, &sha)
        .unwrap_err()
        .contains("uncertain"));
    assert!(!root.join("uncertain").exists());
    fs::remove_dir(&uncertain).unwrap();
    let terminal = root.join("first/cycles-result.json");
    fs::rename(&terminal, root.join("first/terminal-retained.json")).unwrap();
    assert!(
        resume(&bytes, &root.join("unterminated"), &checkpoint, &sha)
            .unwrap_err()
            .contains("terminal")
    );
    assert!(!root.join("unterminated").exists());
    fs::rename(root.join("first/terminal-retained.json"), terminal).unwrap();
    fs::write(
        root.join("first/round-0-repository-understanding/state.json"),
        b"changed",
    )
    .unwrap();
    assert!(resume(&bytes, &root.join("changed"), &checkpoint, &sha)
        .unwrap_err()
        .contains("changed"));
    assert!(!root.join("changed").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn cli_continuation_requires_explicit_checkpoint_digest() {
    let (root, mut recipe) = fixture();
    recipe["maximumStagesPerInvocation"] = json!(1);
    run(&root, &recipe, "first").unwrap();
    let checkpoint = root.join("first/checkpoint-1.json");
    let recipe_path = root.join("recipe.json");
    fs::write(&recipe_path, serde_json::to_vec(&recipe).unwrap()).unwrap();
    let command = |name: &str, sha: Option<String>| {
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"));
        cmd.arg("--execute-flywheel-cycles")
            .arg("--recipe")
            .arg(&recipe_path)
            .arg("--output")
            .arg(root.join(name))
            .arg("--cycle-checkpoint")
            .arg(&checkpoint);
        if let Some(sha) = sha {
            cmd.arg("--cycle-checkpoint-sha256").arg(sha);
        }
        cmd.output().unwrap()
    };
    assert!(!command("missing", None).status.success());
    assert!(!root.join("missing").exists());
    let result = command("continued", Some(digest(&fs::read(&checkpoint).unwrap())));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(root.join("continued/round-0-program-analysis").exists());
    assert!(!root
        .join("continued/round-0-repository-understanding")
        .exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn failed_dispatch_preserves_checkpoint_but_cannot_automatically_resume_it() {
    let (root, mut recipe) = fixture();
    recipe["stages"][1]["command"]["args"][0] = json!("exit");
    let result = run(&root, &recipe, "failed").unwrap();
    assert_eq!(result["status"], "adapter-failed");
    let checkpoint = root.join("failed/checkpoint-1.json");
    let sha = digest(&fs::read(&checkpoint).unwrap());
    assert!(resume(
        &serde_json::to_vec(&recipe).unwrap(),
        &root.join("retry"),
        &checkpoint,
        &sha
    )
    .unwrap_err()
    .contains("uncertain"));
    assert!(!root.join("retry").exists());
    assert!(root
        .join("failed/round-0-program-analysis/failure.json")
        .exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn two_rounds_retain_exact_stage_lineage_without_claiming_qualification() {
    let (root, recipe) = fixture();
    let result = run(&root, &recipe, "capture").unwrap();
    assert_eq!(result["completedRounds"], 2);
    assert_eq!(result["stages"].as_array().unwrap().len(), 10);
    assert_eq!(result["qualified"], false);
    assert_eq!(result["authorityWritesIndependentlyVerified"], false);
    let request: Value = serde_json::from_slice(
        &fs::read(root.join("capture/round-1-repository-understanding/request.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(request["previousStage"]["stage"], "evidence-return");
    assert_eq!(
        request["inputState"]["sha256"],
        request["previousStage"]["result"]["outputState"]["sha256"]
    );
    assert!(
        run(&root, &recipe, "capture").is_err(),
        "must not overwrite captures"
    );
    let recipe_path = root.join("recipe.json");
    fs::write(&recipe_path, serde_json::to_vec(&recipe).unwrap()).unwrap();
    let cli = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .arg("--execute-flywheel-cycles")
        .arg("--recipe")
        .arg(&recipe_path)
        .arg("--output")
        .arg(root.join("cli-capture"))
        .output()
        .unwrap();
    assert!(
        cli.status.success(),
        "{}",
        String::from_utf8_lossy(&cli.stderr)
    );
    let receipt: Value = serde_json::from_slice(&cli.stdout).unwrap();
    assert_eq!(receipt["completedRounds"], 2);
    assert_eq!(receipt["qualified"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn review_rejection_infrastructure_and_no_change_stop_before_next_round() {
    let (root, recipe) = fixture();
    for (mode, status, count) in [
        ("review", "review-required", 5),
        ("reject", "stage-rejected", 1),
        ("repeat", "no-change", 5),
        ("exit", "adapter-failed", 0),
    ] {
        let mut r = recipe.clone();
        for s in r["stages"].as_array_mut().unwrap() {
            s["command"]["args"][0] = json!(mode);
        }
        let capture = run(&root, &r, mode).unwrap();
        assert_eq!(capture["status"], status);
        assert_eq!(capture["completedRounds"], 0);
        assert_eq!(capture["stages"].as_array().unwrap().len(), count);
        assert!(!root
            .join(mode)
            .join("round-1-repository-understanding")
            .exists());
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn mutation_of_prior_state_is_terminal_not_a_new_round() {
    let (root, mut recipe) = fixture();
    recipe["stages"][1]["command"]["args"][0] = json!("tamper");
    assert!(run(&root, &recipe, "tamper")
        .unwrap_err()
        .contains("changed"));
    assert!(!root
        .join("tamper/round-0-maintenance-verification")
        .exists());
    assert!(root
        .join("tamper/round-0-program-analysis/adapter.stdout")
        .exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn private_environment_is_stage_scoped_and_names_are_checked_before_execution() {
    let (root, mut recipe) = fixture();
    let old = std::env::var_os("AGENTLAB_MODEL");
    std::env::set_var("AGENTLAB_MODEL", "private-model-transport-fixture");
    recipe["stages"][3]["environmentNames"] = json!(["AGENTLAB_MODEL"]);
    let result = run(&root, &recipe, "environment").unwrap();
    for stage in result["stages"].as_array().unwrap() {
        let path = root
            .join("environment")
            .join(format!(
                "round-{}-{}",
                stage["round"],
                stage["stage"].as_str().unwrap()
            ))
            .join("state.json");
        let state: Value = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
        assert_eq!(
            state["hasModelEnvironment"],
            stage["stage"] == "case-execution"
        );
    }
    assert!(!serde_json::to_string(&result)
        .unwrap()
        .contains("private-model-transport-fixture"));
    recipe["stages"][0]["environmentNames"] = json!(["PATH"]);
    assert!(run(&root, &recipe, "forbidden")
        .unwrap_err()
        .contains("forbidden"));
    assert!(!root.join("forbidden").exists());
    if let Some(value) = old {
        std::env::set_var("AGENTLAB_MODEL", value);
    } else {
        std::env::remove_var("AGENTLAB_MODEL");
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn composite_stage_budget_is_explicit_and_total_is_bounded() {
    let (root, mut recipe) = fixture();
    recipe["stages"][3]["command"]["timeoutMs"] = json!(240_000);
    let result = run(&root, &recipe, "composite").unwrap();
    assert_eq!(result["totalCommandBudgetMs"], 720_000);
    assert_eq!(
        result["stages"][3]["execution"]["command"]["timeoutMs"],
        240_000
    );
    for stage in recipe["stages"].as_array_mut().unwrap() {
        stage["command"]["timeoutMs"] = json!(900_000);
    }
    assert!(run(&root, &recipe, "excessive")
        .unwrap_err()
        .contains("one hour"));
    assert!(!root.join("excessive").exists());
    recipe["stages"][0]["command"]["timeoutMs"] = json!(900_001);
    assert!(run(&root, &recipe, "deadline")
        .unwrap_err()
        .contains("deadline"));
    assert!(!root.join("deadline").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn reject_borrowed_response_and_incomplete_recipe_without_relabeling_success() {
    let (root, recipe) = fixture();
    let mut r = recipe.clone();
    r["stages"][0]["command"]["args"][0] = json!("borrowed");
    assert!(run(&root, &r, "borrowed").unwrap_err().contains("binding"));
    assert!(root
        .join("borrowed/round-0-repository-understanding/adapter.stdout")
        .exists());
    assert!(!root.join("borrowed/round-0-program-analysis").exists());
    r = recipe.clone();
    r["stages"].as_array_mut().unwrap().pop();
    assert!(run(&root, &r, "incomplete").is_err());
    assert!(!root.join("incomplete").exists());
    fs::remove_dir_all(root).unwrap();
}
