use agentlab_code_analysis::{
    digest,
    knowledge_gate::{validate_gate, GateStage},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    source: PathBuf,
    difficulty: PathBuf,
    cut: PathBuf,
    binding: PathBuf,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn write_json(path: &PathBuf, value: &Value) {
    fs::write(path, serde_json::to_vec(value).unwrap()).unwrap();
}

fn fixture() -> Fixture {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let sequence = FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "agentlab-knowledge-gate-{}-{unique}-{sequence}",
        std::process::id()
    ));
    fs::create_dir_all(&root).unwrap();
    let revision = "1".repeat(40);
    let source_set = "a".repeat(64);
    let repositories = json!([{"id":"repo-a","repository":"https://example.invalid/repo-a.git","revision":revision}]);
    let source = root.join("source.json");
    write_json(
        &source,
        &json!({"schema":"agentlab.multi_repo_manifest.v1","repositories":repositories}),
    );
    let candidate = json!({
        "id":"difficulty-a",
        "relationType":"shared-domain-identifier-contract",
        "evidenceIds":["source-fact-a"],
        "verificationContract":{"caseReady":false},
        "automaticPromotion":false
    });
    let difficulty = root.join("difficulty.json");
    write_json(
        &difficulty,
        &json!({
            "schema":"agentlab.difficulty_candidates.v2",
            "sourceSetSha256":source_set,
            "sources":repositories,
            "candidates":[candidate],
            "automaticPromotion":false
        }),
    );
    let skills = root.join("maintainer_skills.jsonl");
    let skill_rows = [
        json!({"id":"skill-repository","skillLayer":"instance","stage":"repository-analysis","sourceRevision":revision}),
        json!({"id":"skill-program","skillLayer":"instance","stage":"program-analysis","sourceRevision":revision}),
        json!({"id":"skill-seed","skillLayer":"instance","stage":"seed-extraction","sourceRevision":revision}),
    ];
    fs::write(
        &skills,
        skill_rows
            .iter()
            .map(|row| serde_json::to_string(row).unwrap() + "\n")
            .collect::<String>(),
    )
    .unwrap();
    let facts = root.join("program_facts.jsonl");
    fs::write(
        &facts,
        format!(
            "{}\n{}\n",
            json!({"id":"fact-a","kind":"symbol","sourceRevision":revision}),
            json!({"id":"analysis-a","kind":"analysis","sourceRevision":revision})
        ),
    )
    .unwrap();
    let skus = root.join("maintainer_skus.jsonl");
    fs::write(
        &skus,
        format!(
            "{}\n",
            json!({
                "id":"sku-a",
                "repositoryId":"repo-a",
                "sourceRevision":revision,
                "trackedFileCount":1,
                "automaticPromotion":false
            })
        ),
    )
    .unwrap();
    let cases = root.join("evaluation_cases.jsonl");
    fs::write(&cases, "").unwrap();
    let cut = root.join("knowledge-cut.json");
    write_json(
        &cut,
        &json!({
            "schema":"agentlab.maintainer_knowledge_cut.v1",
            "sourceSetSha256":source_set,
            "repositories":repositories,
            "tables":{
                "maintainerSkills":{"path":"maintainer_skills.jsonl","sha256":digest(&fs::read(&skills).unwrap())},
                "maintainerSkus":{"path":"maintainer_skus.jsonl","sha256":digest(&fs::read(&skus).unwrap())},
                "programFacts":{"path":"program_facts.jsonl","sha256":digest(&fs::read(&facts).unwrap())},
                "evaluationCases":{"path":"evaluation_cases.jsonl","sha256":digest(&fs::read(&cases).unwrap())}
            },
            "policy":{
                "wholeRepositoryInventoryRequired":true,
                "semanticCoverageRequired":true,
                "programAnalysisBound":true,
                "candidateBindingsRequired":true
            },
            "automaticPromotion":false
        }),
    );
    let difficulty_value: Value = serde_json::from_slice(&fs::read(&difficulty).unwrap()).unwrap();
    let candidate_sha = digest(&serde_json::to_vec(&difficulty_value["candidates"][0]).unwrap());
    let binding = root.join("binding.json");
    write_json(
        &binding,
        &json!({
            "schema":"agentlab.candidate_knowledge_binding.v1",
            "candidateId":"difficulty-a",
            "candidateSha256":candidate_sha,
            "sourceSetSha256":source_set,
            "knowledgeCutSha256":digest(&fs::read(&cut).unwrap()),
            "repositoryBindings":[{
                "repositoryId":"repo-a",
                "revision":revision,
                "skuIds":["sku-a"],
                "skillIds":["skill-program","skill-repository","skill-seed"],
                "factIds":["fact-a"],
                "analysisIds":["analysis-a"],
                "coverage":{
                    "architecture":["module boundary"],
                    "buildAndTestEntrypoints":["locked build"],
                    "behaviorContracts":["observable behavior"],
                    "stateTransitions":["before to after"],
                    "crossFileResponsibilities":["caller and callee"],
                    "knownGaps":["dynamic dispatch unresolved"]
                }
            }],
            "behaviorContract":{
                "responsibilities":["owner responsibility"],
                "stateTransitions":["idle to complete"],
                "acceptanceObservables":["independent result"],
                "unresolvedRisks":["runtime provider unavailable"]
            },
            "automaticPromotion":false
        }),
    );
    Fixture {
        root,
        source,
        difficulty,
        cut,
        binding,
    }
}

#[test]
fn candidate_gate_accepts_exact_revision_bound_knowledge() {
    let fixture = fixture();
    let receipt = validate_gate(
        GateStage::Candidate,
        &fixture.source,
        &fixture.difficulty,
        &fixture.cut,
        &fixture.binding,
        "difficulty-a",
    )
    .unwrap();
    assert_eq!(receipt["status"], "passed");
    assert_eq!(receipt["repositoryCount"], 1);
    assert_eq!(receipt["maintainerSkillCount"], 3);
    assert_eq!(receipt["maintainerSkuCount"], 1);
    assert_eq!(receipt["programFactCount"], 1);
    assert_eq!(receipt["analysisRecordCount"], 1);
}

#[test]
fn candidate_gate_rejects_missing_program_analysis_skill() {
    let fixture = fixture();
    let mut binding: Value = serde_json::from_slice(&fs::read(&fixture.binding).unwrap()).unwrap();
    binding["repositoryBindings"][0]["skillIds"] = json!(["skill-repository", "skill-seed"]);
    write_json(&fixture.binding, &binding);
    let error = validate_gate(
        GateStage::Candidate,
        &fixture.source,
        &fixture.difficulty,
        &fixture.cut,
        &fixture.binding,
        "difficulty-a",
    )
    .unwrap_err();
    assert!(error.contains("program-analysis"), "{error}");
}

#[test]
fn candidate_gate_rejects_unknown_maintainer_sku() {
    let fixture = fixture();
    let mut binding: Value = serde_json::from_slice(&fs::read(&fixture.binding).unwrap()).unwrap();
    binding["repositoryBindings"][0]["skuIds"] = json!(["sku-not-in-cut"]);
    write_json(&fixture.binding, &binding);
    let error = validate_gate(
        GateStage::Candidate,
        &fixture.source,
        &fixture.difficulty,
        &fixture.cut,
        &fixture.binding,
        "difficulty-a",
    )
    .unwrap_err();
    assert!(error.contains("unknown maintainer SKU"), "{error}");
}

#[test]
fn construction_gate_rejects_candidate_only_binding() {
    let fixture = fixture();
    let error = validate_gate(
        GateStage::Construction,
        &fixture.source,
        &fixture.difficulty,
        &fixture.cut,
        &fixture.binding,
        "difficulty-a",
    )
    .unwrap_err();
    assert!(error.contains("construction.taskDemands"), "{error}");
}

#[test]
fn candidate_gate_rejects_table_paths_outside_the_knowledge_cut() {
    let fixture = fixture();
    let mut cut: Value = serde_json::from_slice(&fs::read(&fixture.cut).unwrap()).unwrap();
    cut["tables"]["programFacts"]["path"] = json!("../program_facts.jsonl");
    write_json(&fixture.cut, &cut);
    let mut binding: Value = serde_json::from_slice(&fs::read(&fixture.binding).unwrap()).unwrap();
    binding["knowledgeCutSha256"] = json!(digest(&fs::read(&fixture.cut).unwrap()));
    write_json(&fixture.binding, &binding);
    let error = validate_gate(
        GateStage::Candidate,
        &fixture.source,
        &fixture.difficulty,
        &fixture.cut,
        &fixture.binding,
        "difficulty-a",
    )
    .unwrap_err();
    assert!(error.contains("safe relative path"), "{error}");
}
