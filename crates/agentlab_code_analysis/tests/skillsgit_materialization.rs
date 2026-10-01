use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn write(path: &Path, value: &Value) {
    fs::write(path, serde_json::to_vec(value).unwrap()).unwrap();
}

#[test]
fn materialization_consumes_durable_assessed_bindings_and_capability_dimensions() {
    let base = std::env::temp_dir().join(format!(
        "al-skill-tree-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(base.join("assessments")).unwrap();
    let scope = json!({"id":"scope-unfamiliar-config", "repositoryId":"unfamiliar",
        "sourceRevision":"a".repeat(40), "pathBoundary":"config"});
    write(&base.join("maintainer_scope_skills.jsonl"), &scope);
    let good = json!({"id":"contract", "repositoryId":"unfamiliar",
        "sourceRevision":"a".repeat(40), "scopeSkillIds":[scope["id"]],
        "dimensions":["responsibility","boundary","relations"], "interpretation":"Grounded configuration contract"});
    let mut stale = good.clone();
    stale["id"] = json!("stale");
    stale["sourceRevision"] = json!("b".repeat(40));
    stale["interpretation"] = json!("STALE contract must not appear");
    let structural = json!({"id":"architecture", "repositoryId":"unfamiliar",
        "sourceRevision":"a".repeat(40), "kind":"architecture"});
    let fact_bytes = format!("{}\n{}\n{}\n", good, stale, structural);
    fs::write(base.join("program_facts.jsonl"), &fact_bytes).unwrap();
    let cut = json!({"repositories":[{"id":"unfamiliar", "revision":"a".repeat(40)}]});
    write(&base.join("maintainer-knowledge-cut.json"), &cut);
    let mut report = json!({"schema":"agentlab.maintainer_skill_assessment.v1",
        "automaticPromotion":false, "roundIndex":7,
        "inputs":{"scopeSkillsSha256":digest(&fs::read(base.join("maintainer_scope_skills.jsonl")).unwrap()),
            "programFactsSha256":digest(fact_bytes.as_bytes())},
        "skills":[{"skillId":scope["id"], "repositoryId":"unfamiliar", "sourceRevision":"a".repeat(40),
            "maturity":"L2-semantic-ready", "checks":{"semanticReady":true},
            "requiredSemanticDimensions":["responsibility","boundary","relations"],
            "evidenceBindings":[{"factId":"contract", "dimensions":["responsibility","boundary","relations"]},
                {"factId":"architecture", "dimensions":["boundary","relations"]}]}]});
    let assessment = base.join("assessments/pinned.json");
    let bind = |report: &Value| {
        write(&assessment, report);
        write(
            &base.join("maintainer_skill_refresh_rounds.jsonl"),
            &json!({"id":"durable-second", "roundIndex":2,
            "assessment":{"path":"assessments/pinned.json", "sha256":digest(&fs::read(&assessment).unwrap())}}),
        );
    };
    bind(&report);
    write(
        &base.join("assessments/orphan-999.json"),
        &json!({"roundIndex":999,"skills":[]}),
    );
    let adapter = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/materialize-skillsgit-maintainer-tree.py");
    let invoke = || {
        Command::new("python3").args(["-c",
        "import importlib.util,json,pathlib,sys\ns=importlib.util.spec_from_file_location('material',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nr,scopes=m.semantic_scope_material(pathlib.Path(sys.argv[2]),'unfamiliar');print(json.dumps({'round':r['roundIndex'],'facts':[[f['id'] for f in x[2]] for x in scopes]}))",
        adapter.to_str().unwrap(), base.to_str().unwrap()]).output().unwrap()
    };
    let result = invoke();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&result.stdout).unwrap(),
        json!({"round":7,"facts":[["contract"]]})
    );
    fs::write(&assessment, b"{}").unwrap();
    assert!(!invoke().status.success(), "changed report bytes");
    bind(&report);
    fs::write(base.join("program_facts.jsonl"), format!("{fact_bytes}\n")).unwrap();
    assert!(!invoke().status.success(), "changed assessed fact bytes");
    fs::write(base.join("program_facts.jsonl"), &fact_bytes).unwrap();
    let mut wrong_cut = cut.clone();
    wrong_cut["repositories"][0]["revision"] = json!("b".repeat(40));
    write(&base.join("maintainer-knowledge-cut.json"), &wrong_cut);
    assert!(!invoke().status.success(), "borrowed source identity");
    write(&base.join("maintainer-knowledge-cut.json"), &cut);
    report["skills"][0]["evidenceBindings"][0]["factId"] = json!("stale");
    bind(&report);
    assert!(!invoke().status.success(), "stale assessment binding");
    report["skills"][0]["evidenceBindings"][0]["factId"] = json!("contract");
    report["skills"][0]["requiredSemanticDimensions"] =
        json!(["responsibility", "boundary", "relations", "behavior"]);
    bind(&report);
    assert!(!invoke().status.success(), "missing required behavior");
    fs::remove_dir_all(base).unwrap();
}

#[test]
fn strict_table_export_preserves_original_assessed_unicode_bytes() {
    let base = std::env::temp_dir().join(format!(
        "al-strict-export-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(base.join("output")).unwrap();
    // A historical assessed cut may retain append order, unlike a TableGit
    // readback. Preserve both ordering and Unicode bytes after value checking.
    let original = b"{\"id\":\"z\",\"value\":\"\\u4e2d\"}\n{\"id\":\"a\",\"value\":\"first\"}\n";
    fs::write(base.join("program_facts.jsonl"), original).unwrap();
    let adapter =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../scripts/maintainer-skill-tablegit.py");
    let result = Command::new("python3").args(["-c",
        "import importlib.util,pathlib,sys\ns=importlib.util.spec_from_file_location('writer',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\np=pathlib.Path(sys.argv[2]);rows=sorted(m.load_jsonl(p/'program_facts.jsonl'),key=lambda r:r['id']);m.write_exact_export_table(p/'output',p,'program_facts',rows,True)\ntry:\n m.write_exact_export_table(p/'output',p,'program_facts',[{'id':'x','value':'wrong'}],True)\nexcept RuntimeError:\n pass\nelse:\n raise AssertionError('authority value mismatch accepted')",
        adapter.to_str().unwrap(), base.to_str().unwrap()]).output().unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        fs::read(base.join("output/program_facts.jsonl")).unwrap(),
        original
    );
    fs::remove_dir_all(base).unwrap();
}
