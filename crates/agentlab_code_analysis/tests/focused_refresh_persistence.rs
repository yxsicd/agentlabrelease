use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[test]
fn strict_focused_refresh_stages_one_update_and_preserves_portable_operations() {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let base = repo.join("examples/maintainer-knowledge-gate/first-four");
    let root = std::env::temp_dir().join(format!(
        "focused-stage-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&root).unwrap();
    let invoke = |program: &Path, args: Vec<String>| {
        let out = Command::new(program).args(args).output().unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
    };
    let bin = Path::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"));
    invoke(
        bin,
        vec![
            "--resolve-latest-assessment".into(),
            "--base".into(),
            base.display().to_string(),
            "--output".into(),
            root.join("reference.json").display().to_string(),
        ],
    );
    let reference: Value =
        serde_json::from_slice(&fs::read(root.join("reference.json")).unwrap()).unwrap();
    let before = Path::new(reference["assessmentPath"].as_str().unwrap());
    let report: Value = serde_json::from_slice(&fs::read(before).unwrap()).unwrap();
    let scopes: Vec<_> = report["skills"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["maturity"] == "L2-semantic-ready")
        .map(|r| r["skillId"].clone())
        .collect();
    let mut facts: Vec<Value> = fs::read_to_string(base.join("program_facts.jsonl"))
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    let index = facts
        .iter()
        .position(|r| {
            r["kind"] == "analysis"
                && r["scopeSkillIds"]
                    .as_array()
                    .is_some_and(|ids| ids.len() == 1 && scopes.contains(&ids[0]))
        })
        .unwrap();
    let old = facts[index].clone();
    let scope = old["scopeSkillIds"][0].as_str().unwrap();
    facts[index]["interpretation"] = json!(format!(
        "{} Additional source-only uncertainty remains unqualified.",
        old["interpretation"].as_str().unwrap()
    ));
    let updated = facts[index].clone();
    let encoded: Vec<u8> = facts
        .iter()
        .flat_map(|value| {
            let mut bytes = serde_json::to_vec(value).unwrap();
            bytes.push(b'\n');
            bytes
        })
        .collect();
    fs::write(root.join("facts.jsonl"), &encoded).unwrap();
    invoke(
        bin,
        vec![
            "--scope-skills".into(),
            base.join("maintainer_scope_skills.jsonl")
                .display()
                .to_string(),
            "--program-facts".into(),
            root.join("facts.jsonl").display().to_string(),
            "--operation-receipts-root".into(),
            base.join("operation-evidence").display().to_string(),
            "--round-index".into(),
            (report["roundIndex"].as_u64().unwrap() + 1).to_string(),
            "--parent-assessment-sha256".into(),
            sha(&fs::read(before).unwrap()),
            "--output".into(),
            root.join("after.json").display().to_string(),
        ],
    );
    invoke(
        Path::new("python3"),
        vec![
            repo.join("examples/maintainer-knowledge-gate/focused_fact_refresh.py")
                .display()
                .to_string(),
            "compare".into(),
            "--before".into(),
            before.display().to_string(),
            "--after".into(),
            root.join("after.json").display().to_string(),
            "--scope-id".into(),
            scope.into(),
            "--output".into(),
            root.join("result.json").display().to_string(),
        ],
    );
    let receipt = json!({"acceptedFactId":old["id"], "changeKind":"updated", "scopeSkillId":scope,
        "sourceAssessmentSha256":sha(&fs::read(before).unwrap()),
        "previousFactSha256":sha(&serde_json::to_vec(&old).unwrap()),
        "acceptedFactSha256":sha(&serde_json::to_vec(&updated).unwrap()),
        "candidateProgramFactsSha256":sha(&encoded)});
    fs::write(
        root.join("receipt.json"),
        serde_json::to_vec(&receipt).unwrap(),
    )
    .unwrap();
    let stage = |label: &str| {
        Command::new("python3")
            .arg(repo.join("scripts/maintainer-skill-tablegit.py"))
            .arg("stage")
            .arg("--base")
            .arg(&base)
            .arg("--candidate-program-facts")
            .arg(root.join("facts.jsonl"))
            .arg("--candidate-assessment")
            .arg(root.join("after.json"))
            .arg("--result")
            .arg(root.join("result.json"))
            .arg("--receipt")
            .arg(root.join("receipt.json"))
            .args([
                "--run-id",
                "fixture-only",
                "--github-repository",
                "fixture/repo",
                "--output",
            ])
            .arg(root.join(label))
            .output()
            .unwrap()
    };
    let result = stage("valid");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let manifest: Value =
        serde_json::from_slice(&fs::read(root.join("valid/stage-manifest.json")).unwrap()).unwrap();
    assert_eq!(manifest["semanticMode"], "focused-refresh");
    assert_eq!(manifest["proposalReceiptCount"], 1);
    let code = "import importlib.util,sys,pathlib; s=importlib.util.spec_from_file_location('t',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); f=m.operation_evidence_files(pathlib.Path(sys.argv[2])); assert 'operation-baseline.json' in f; assert any(p.startswith('operation-evidence/') for p in f)";
    invoke(
        Path::new("python3"),
        vec![
            "-c".into(),
            code.into(),
            repo.join("scripts/maintainer-skill-tablegit.py")
                .display()
                .to_string(),
            root.join("valid").display().to_string(),
        ],
    );
    let original: Value =
        serde_json::from_slice(&fs::read(root.join("result.json")).unwrap()).unwrap();
    for label in [
        "fake-advance",
        "changed-total",
        "wrong-scope",
        "wrong-policy",
    ] {
        let mut result = original.clone();
        match label {
            "fake-advance" => result["advancedScopeIds"] = json!([scope]),
            "changed-total" => result["after"]["semanticReadyCount"] = json!(999),
            "wrong-scope" => result["selectedScopeIds"] = json!(["unrelated"]),
            "wrong-policy" => result["strictOperationEvidencePolicy"] = json!(false),
            _ => unreachable!(),
        }
        fs::write(
            root.join("result.json"),
            serde_json::to_vec(&result).unwrap(),
        )
        .unwrap();
        assert!(!stage(label).status.success(), "accepted {label}");
        assert!(!root.join(label).exists());
    }
    fs::remove_dir_all(root).unwrap();
}
