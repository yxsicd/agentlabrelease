#![cfg(unix)]
use agentlab_code_analysis::{digest, maintainer_flywheel_cycles::execute};
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
 let state=if args[1]=="repeat" {input} else {serde_json::to_vec(&json!({"round":r["round"],"stage":stage})).unwrap()};
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
    let command = json!({"program":binary,"programSha256":digest(&fs::read(&binary).unwrap()),"cwd":".","timeoutMs":3000,"args":["advance","{request}"]});
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
