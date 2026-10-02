use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn sha(value: &Value) -> String {
    format!("{:x}", Sha256::digest(serde_json::to_vec(value).unwrap()))
}

#[test]
fn original_shadow_history_prepares_feedback_without_rebinding_or_authority_mutation() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let knowledge = root.join("examples/maintainer-knowledge-gate/first-four");
    let rows = |name: &str| -> Vec<Value> {
        fs::read_to_string(knowledge.join(name))
            .unwrap()
            .lines()
            .filter(|s| !s.is_empty())
            .map(|s| serde_json::from_str(s).unwrap())
            .collect()
    };
    let candidates = rows("case_generation_candidates.jsonl");
    let candidate = candidates
        .iter()
        .find(|r| r["id"] == "shadow-case-abilitystage-environment-callback-binding")
        .unwrap();
    assert_eq!(
        sha(candidate),
        "67525cc61d7d22f3eae2f66df5dbfded19ac1864e6f3f0dc0069e048c0abb23e"
    );
    assert_eq!(
        candidate["knowledgeCutSha256"],
        "ccd9d953b926b5647de7572dcdc7065cbbc9fd91ba46c5c01a3278ddd170e70e"
    );
    let rounds = rows("case_generation_rounds.jsonl");
    let round = rounds
        .iter()
        .find(|r| r["id"] == "first-four-case-generation-round-16-shadow-36857619983")
        .unwrap();
    assert_eq!(
        sha(round),
        "17500e53aee385d9a6f729b4e9564d532024879d1934d1f49a4b86c3562a5522"
    );
    let parent = rounds.iter().find(|r| r["roundIndex"] == 15).unwrap();
    assert_eq!(round["parentRoundSha256"], sha(parent));
    assert_eq!(round["knowledgeCutSha256"], candidate["knowledgeCutSha256"]);
    assert_eq!(
        round["qualification"]["qualifiedCaseIds"],
        serde_json::json!([])
    );
    let original: Vec<_> = [
        "maintainer_skills.jsonl",
        "maintainer_scope_skills.jsonl",
        "program_facts.jsonl",
        "maintainer_skill_refresh_rounds.jsonl",
        "evaluation_cases.jsonl",
        "maintainer-knowledge-cut.json",
        "case_generation_candidates.jsonl",
        "case_generation_rounds.jsonl",
    ]
    .iter()
    .map(|name| (*name, fs::read(knowledge.join(name)).unwrap()))
    .collect();
    let temp = std::env::temp_dir().join(format!(
        "restored-feedback-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&temp).unwrap();
    let reference = temp.join("reference.json");
    let result = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .arg("--resolve-latest-assessment")
        .arg("--base")
        .arg(&knowledge)
        .arg("--output")
        .arg(&reference)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let reference: Value = serde_json::from_slice(&fs::read(reference).unwrap()).unwrap();
    let output = temp.join("request.json");
    let result = Command::new("python3")
        .arg(root.join("examples/maintainer-knowledge-gate/focused_fact_refresh.py"))
        .arg("prepare")
        .arg("--knowledge")
        .arg(&knowledge)
        .arg("--assessment")
        .arg(reference["assessmentPath"].as_str().unwrap())
        .arg("--candidate-id")
        .arg(candidate["id"].as_str().unwrap())
        .arg("--plan")
        .arg(knowledge.join("construction-plans/abilitystage-environment-callback.json"))
        .arg("--evidence-root")
        .arg(&root)
        .arg("--output")
        .arg(&output)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let request: Value = serde_json::from_slice(&fs::read(output).unwrap()).unwrap();
    assert_eq!(request["readinessDecision"], "blocked-knowledge-refresh");
    assert_eq!(request["candidateSha256"], sha(candidate));
    assert_eq!(
        request["knowledgeCutSha256"],
        candidate["knowledgeCutSha256"]
    );
    assert_eq!(
        request["requiredDimensions"],
        request["existingFact"]["dimensions"]
    );
    assert_eq!(request["requiredOraclePaths"].as_array().unwrap().len(), 2);
    assert_eq!(request["automaticPromotion"], false);
    for (name, bytes) in original {
        assert_eq!(
            fs::read(knowledge.join(name)).unwrap(),
            bytes,
            "mutated {name}"
        );
    }
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn current_authority_cut_prepares_telemetry_refresh_without_borrowing_runtime_evidence() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let knowledge = root.join("examples/maintainer-knowledge-gate/first-four");
    let original: Vec<_> = [
        "maintainer_skills.jsonl",
        "maintainer_scope_skills.jsonl",
        "program_facts.jsonl",
        "maintainer_skill_refresh_rounds.jsonl",
        "evaluation_cases.jsonl",
        "maintainer-knowledge-cut.json",
        "case_generation_candidates.jsonl",
        "case_generation_rounds.jsonl",
    ]
    .iter()
    .map(|name| (*name, fs::read(knowledge.join(name)).unwrap()))
    .collect();
    let cut: Value = serde_json::from_slice(&original[5].1).unwrap();
    assert_eq!(
        cut["tableGitAuthority"]["revision"],
        "1aef65558cbbc66b3bfe63b719cfc171b33a28f9"
    );
    let temp = std::env::temp_dir().join(format!(
        "telemetry-feedback-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&temp).unwrap();
    let reference = temp.join("reference.json");
    let resolved = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .args(["--resolve-latest-assessment", "--base"])
        .arg(&knowledge)
        .arg("--output")
        .arg(&reference)
        .output()
        .unwrap();
    assert!(
        resolved.status.success(),
        "{}",
        String::from_utf8_lossy(&resolved.stderr)
    );
    let reference: Value = serde_json::from_slice(&fs::read(reference).unwrap()).unwrap();
    assert_eq!(reference["refreshRoundIndex"], 40);
    let output = temp.join("request.json");
    let prepared = Command::new("python3")
        .arg(root.join("examples/maintainer-knowledge-gate/focused_fact_refresh.py"))
        .args(["prepare", "--knowledge"])
        .arg(&knowledge)
        .arg("--assessment")
        .arg(reference["assessmentPath"].as_str().unwrap())
        .args([
            "--candidate-id",
            "shadow-case-rdb-preference-telemetry-pipeline",
            "--plan",
        ])
        .arg(knowledge.join("construction-plans/telemetry-persistence.json"))
        .arg("--evidence-root")
        .arg(&root)
        .arg("--output")
        .arg(&output)
        .output()
        .unwrap();
    assert!(
        prepared.status.success(),
        "{}",
        String::from_utf8_lossy(&prepared.stderr)
    );
    let request: Value = serde_json::from_slice(&fs::read(output).unwrap()).unwrap();
    assert_eq!(request["readinessDecision"], "blocked-knowledge-refresh");
    assert_eq!(
        request["sourceAssessment"]["sha256"],
        reference["assessmentSha256"]
    );
    assert_eq!(
        request["existingFact"]["evidence"]
            .as_array()
            .unwrap()
            .len(),
        5
    );
    assert_eq!(
        request["requiredImplementationPaths"]
            .as_array()
            .unwrap()
            .len(),
        3
    );
    assert_eq!(request["requiredOraclePaths"].as_array().unwrap().len(), 2);
    assert_eq!(
        request["requiredDimensions"],
        request["existingFact"]["dimensions"]
    );
    assert_eq!(request["automaticPromotion"], false);
    let candidate: Value = fs::read_to_string(knowledge.join("case_generation_candidates.jsonl"))
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .find(|row| row["id"] == request["candidateId"])
        .unwrap();
    assert_eq!(sha(&candidate), request["candidateSha256"]);
    assert_eq!(
        candidate["oracleHypothesis"]["status"],
        "hypothesis-unqualified"
    );
    for (name, bytes) in original {
        assert_eq!(
            fs::read(knowledge.join(name)).unwrap(),
            bytes,
            "mutated {name}"
        );
    }
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn recovered_telemetry_successor_preserves_parent_and_requires_independent_qualification() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let knowledge = root.join("examples/maintainer-knowledge-gate/first-four");
    let candidates: Vec<Value> =
        fs::read_to_string(knowledge.join("case_generation_candidates.jsonl"))
            .unwrap()
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
    let parent = candidates
        .iter()
        .find(|row| row["id"] == "shadow-case-rdb-preference-telemetry-pipeline")
        .unwrap();
    assert_eq!(
        sha(parent),
        "bc676978abcfb563f8d12616075ba05a8cd727a4cc25f24c2d8271002eef3dd9"
    );
    let successor = candidates
        .iter()
        .find(|row| row["id"] == "shadow-case-refresh-a864ecaec7c67603cab0e114743c5421")
        .unwrap();
    assert_eq!(
        sha(successor),
        "3a2f2e8bdd6901776fe4686112528bb3140dc9e1262a91fdd426b65d92d81bd7"
    );
    assert_eq!(successor["lineage"]["parentCandidateSha256"], sha(parent));
    assert_eq!(successor["oracleHypothesis"], parent["oracleHypothesis"]);
    assert_eq!(successor["automaticPromotion"], false);
    assert_eq!(
        successor["maintainerSkillRefreshRoundId"],
        "first-four-round-40-agent-36960519495"
    );
    let temp = std::env::temp_dir().join(format!(
        "telemetry-successor-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&temp).unwrap();
    let output = temp.join("readiness.json");
    let result =
        Command::new("python3")
            .arg(root.join("examples/maintainer-knowledge-gate/shadow_construction_readiness.py"))
            .arg("--knowledge")
            .arg(&knowledge)
            .arg("--candidate-id")
            .arg(successor["id"].as_str().unwrap())
            .arg("--plan")
            .arg(knowledge.join(
                "construction-plans/shadow-case-refresh-a864ecaec7c67603cab0e114743c5421.json",
            ))
            .arg("--evidence-root")
            .arg(&root)
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let receipt: Value = serde_json::from_slice(&fs::read(output).unwrap()).unwrap();
    assert_eq!(receipt["decision"], "blocked-qualification");
    assert!(receipt["knowledgeBlockers"].as_array().unwrap().is_empty());
    assert_eq!(
        receipt["qualificationBlockers"].as_array().unwrap().len(),
        4
    );
    assert_eq!(receipt["automaticPromotion"], false);
    let outside_context = receipt["checks"]["oraclePaths"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["inCandidateScope"] == false)
        .unwrap();
    assert_eq!(outside_context["readOnlyContextBound"], true);
    assert_eq!(
        outside_context["contextOwnerScopeSkillIds"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(!successor["editablePaths"]
        .as_array()
        .unwrap()
        .contains(&outside_context["path"]));
    fs::remove_dir_all(temp).unwrap();
}
