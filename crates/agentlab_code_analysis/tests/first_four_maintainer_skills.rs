use agentlab_code_analysis::digest;
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn rows(path: &Path) -> BTreeMap<String, Value> {
    let mut result = BTreeMap::new();
    for (index, line) in fs::read_to_string(path).unwrap().lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row: Value = serde_json::from_str(line)
            .unwrap_or_else(|error| panic!("{} line {}: {error}", path.display(), index + 1));
        let id = row["id"].as_str().unwrap().to_owned();
        assert!(result.insert(id.clone(), row).is_none(), "duplicate {id}");
    }
    result
}

fn ids(value: &Value, field: &str) -> Vec<String> {
    value[field]
        .as_array()
        .unwrap_or_else(|| panic!("{field} is not an array"))
        .iter()
        .map(|item| item.as_str().unwrap().to_owned())
        .collect()
}

fn json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

#[test]
fn first_four_cut_is_revision_bound_link_complete_and_tamper_evident() {
    let root = repository_root();
    let baseline = root.join("examples/maintainer-knowledge-gate/first-four");
    let cut: Value =
        serde_json::from_slice(&fs::read(baseline.join("maintainer-knowledge-cut.json")).unwrap())
            .unwrap();
    assert_eq!(cut["schema"], "agentlab.maintainer_knowledge_cut.v1");
    assert_eq!(cut["automaticPromotion"], false);

    let source_set = fs::read(baseline.join("source-set.txt")).unwrap();
    assert_eq!(cut["sourceSetSha256"], digest(&source_set));

    for table in [
        "maintainerSkills",
        "maintainerScopeSkills",
        "maintainerSkillRefreshRounds",
        "programFacts",
        "evaluationCases",
    ] {
        let relative = cut["tables"][table]["path"].as_str().unwrap();
        let bytes = fs::read(baseline.join(relative)).unwrap();
        assert_eq!(
            cut["tables"][table]["sha256"],
            digest(&bytes),
            "{table} digest differs"
        );
    }

    let repositories: BTreeMap<String, String> = cut["repositories"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            (
                row["id"].as_str().unwrap().to_owned(),
                row["revision"].as_str().unwrap().to_owned(),
            )
        })
        .collect();
    assert_eq!(repositories.len(), 4);

    let skills = rows(&baseline.join("maintainer_skills.jsonl"));
    let facts = rows(&baseline.join("program_facts.jsonl"));
    let refresh_rounds = rows(&baseline.join("maintainer_skill_refresh_rounds.jsonl"));
    let generation_rounds = rows(&baseline.join("case_generation_rounds.jsonl"));
    assert_eq!(skills.len(), 12);
    assert!(facts.len() >= 24);
    assert!(refresh_rounds.len() >= 5);
    assert_eq!(generation_rounds.len(), 1);
    assert!(
        fs::read_to_string(baseline.join("evaluation_cases.jsonl"))
            .unwrap()
            .is_empty(),
        "repository knowledge must not silently promote cases"
    );

    let mut stages_by_repository: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (skill_id, skill) in &skills {
        assert_eq!(skill["skillLayer"], "instance", "{skill_id}");
        assert_eq!(skill["ownershipPlane"], "target-operations", "{skill_id}");
        let repository_id = skill["repositoryId"].as_str().unwrap();
        let revision = repositories.get(repository_id).unwrap();
        assert_eq!(skill["sourceRevision"].as_str().unwrap(), revision);
        stages_by_repository
            .entry(repository_id.to_owned())
            .or_default()
            .insert(skill["stage"].as_str().unwrap().to_owned());

        if skill["stage"] == "seed-extraction" {
            assert_eq!(
                skill["methodDigest"],
                digest(&fs::read(root.join("skills/agentlab-seed-extraction/SKILL.md")).unwrap()),
                "{skill_id} does not bind the current iterative generation method"
            );
            assert_eq!(
                skill["methodRevision"], "59216bbc5bca6de2cb0d87bd29f8f154db9d4946",
                "{skill_id} does not bind the method-defining revision"
            );
        }
        if skill["stage"] == "repository-analysis" {
            assert_eq!(
                skill["methodDigest"],
                digest(&fs::read(root.join("skills/agentlab-codebase-analysis/SKILL.md")).unwrap()),
                "{skill_id} does not bind the current evidence-flywheel method"
            );
            assert_eq!(
                skill["methodRevision"], "f697ba31f0c6197a097e252b86ea3ed8e29ba551",
                "{skill_id} does not bind the method-defining revision"
            );
        }

        for fact_id in ids(skill, "factIds") {
            let fact = facts
                .get(&fact_id)
                .unwrap_or_else(|| panic!("{skill_id} references missing fact {fact_id}"));
            assert_eq!(fact["repositoryId"], repository_id);
            assert_eq!(fact["sourceRevision"].as_str().unwrap(), revision);
            assert_ne!(fact["kind"], "analysis");
        }
        for analysis_id in ids(skill, "analysisIds") {
            let analysis = facts
                .get(&analysis_id)
                .unwrap_or_else(|| panic!("{skill_id} references missing analysis {analysis_id}"));
            assert_eq!(analysis["repositoryId"], repository_id);
            assert_eq!(analysis["sourceRevision"].as_str().unwrap(), revision);
            assert_eq!(analysis["kind"], "analysis");
        }
    }

    let expected_stages = BTreeSet::from([
        "program-analysis".to_owned(),
        "repository-analysis".to_owned(),
        "seed-extraction".to_owned(),
    ]);
    assert_eq!(
        stages_by_repository
            .keys()
            .cloned()
            .collect::<BTreeSet<_>>(),
        repositories.keys().cloned().collect::<BTreeSet<_>>()
    );
    for (repository_id, stages) in stages_by_repository {
        assert_eq!(stages, expected_stages, "{repository_id}");
    }

    for (fact_id, fact) in &facts {
        let repository_id = fact["repositoryId"].as_str().unwrap();
        assert_eq!(
            fact["sourceRevision"].as_str().unwrap(),
            repositories.get(repository_id).unwrap(),
            "{fact_id}"
        );
        if let Some(evidence) = fact["evidence"].as_array() {
            assert!(!evidence.is_empty(), "{fact_id} has empty evidence");
            for item in evidence {
                if let Some(oid) = item["gitBlobOid"].as_str() {
                    assert_eq!(oid.len(), 40, "{fact_id} has invalid Git Blob OID");
                    assert!(oid.bytes().all(|byte| byte.is_ascii_hexdigit()));
                }
                if let (Some(path), Some(expected)) =
                    (item["path"].as_str(), item["sha256"].as_str())
                {
                    let bytes = fs::read(root.join(path)).unwrap();
                    assert_eq!(digest(&bytes), expected, "{fact_id} evidence differs");
                }
            }
        }
    }

    let first = &refresh_rounds["first-four-round-1-structural-baseline"];
    let second = &refresh_rounds["first-four-round-2-ownership-and-lineage"];
    let third = &refresh_rounds["first-four-round-3-iterative-case-generation"];
    let fourth = &refresh_rounds["first-four-round-4-evidence-flywheel-practice"];
    let fifth = &refresh_rounds["first-four-round-5-targeted-operation-evidence"];
    assert_eq!(first["roundIndex"], 1);
    assert_eq!(first["parentRoundSha256"], Value::Null);
    assert_eq!(
        second["parentRoundSha256"],
        digest(&serde_json::to_vec(first).unwrap())
    );
    assert_eq!(second["roundIndex"], 2);
    assert_eq!(second["decision"], "continue");
    assert_eq!(
        third["parentRoundSha256"],
        digest(&serde_json::to_vec(second).unwrap())
    );
    assert_eq!(third["roundIndex"], 3);
    assert_eq!(third["decision"], "continue");
    assert_eq!(
        fourth["parentRoundSha256"],
        digest(&serde_json::to_vec(third).unwrap())
    );
    assert_eq!(fourth["roundIndex"], 4);
    assert_eq!(fourth["decision"], "continue");
    assert_eq!(
        fifth["parentRoundSha256"],
        digest(&serde_json::to_vec(fourth).unwrap())
    );
    assert_eq!(fifth["roundIndex"], 5);
    assert_eq!(fifth["decision"], "continue");
    assert_eq!(
        fifth["assessment"]["sha256"],
        digest(&fs::read(baseline.join(fifth["assessment"]["path"].as_str().unwrap())).unwrap())
    );
    let mut ordered_rounds = refresh_rounds.values().collect::<Vec<_>>();
    ordered_rounds.sort_by_key(|row| row["roundIndex"].as_u64().unwrap());
    for pair in ordered_rounds.windows(2) {
        assert_eq!(
            pair[1]["parentRoundSha256"],
            digest(&serde_json::to_vec(pair[0]).unwrap()),
            "refresh-round lineage differs"
        );
        assert_eq!(
            pair[1]["roundIndex"].as_u64().unwrap(),
            pair[0]["roundIndex"].as_u64().unwrap() + 1,
            "refresh-round indices are not contiguous"
        );
    }
    let latest = ordered_rounds.last().unwrap();
    assert_eq!(
        latest["tables"]["processSkillsSha256"],
        digest(&fs::read(baseline.join("maintainer_skills.jsonl")).unwrap())
    );
    assert_eq!(
        latest["tables"]["scopeSkillsSha256"],
        digest(&fs::read(baseline.join("maintainer_scope_skills.jsonl")).unwrap())
    );
    assert_eq!(
        latest["tables"]["programFactsSha256"],
        digest(&fs::read(baseline.join("program_facts.jsonl")).unwrap())
    );
    assert_eq!(
        latest["assessment"]["sha256"],
        digest(&fs::read(baseline.join(latest["assessment"]["path"].as_str().unwrap())).unwrap())
    );

    let assessment_root = baseline.join("assessments");
    let assessment_one = json(&assessment_root.join("round-1-structural.json"));
    let assessment_two = json(&assessment_root.join("round-2-current-program-facts.json"));
    let assessment_three = json(&assessment_root.join("round-3-explicit-evidence-bindings.json"));
    let assessment_four = json(&assessment_root.join("round-4-targeted-operation-evidence.json"));
    assert_eq!(assessment_one["roundIndex"], 1);
    assert_eq!(assessment_one["parentAssessmentSha256"], Value::Null);
    assert_eq!(
        assessment_two["parentAssessmentSha256"],
        digest(&fs::read(assessment_root.join("round-1-structural.json")).unwrap())
    );
    assert_eq!(
        assessment_three["parentAssessmentSha256"],
        digest(&fs::read(assessment_root.join("round-2-current-program-facts.json")).unwrap())
    );
    assert_eq!(
        assessment_four["parentAssessmentSha256"],
        digest(&fs::read(assessment_root.join("round-3-explicit-evidence-bindings.json")).unwrap())
    );
    assert_eq!(assessment_one["totals"]["structuralReadyCount"], 480);
    assert_eq!(assessment_two["totals"]["programBoundCount"], 10);
    assert_eq!(assessment_two["totals"]["semanticReadyCount"], 0);
    assert_eq!(assessment_three["totals"]["programBoundCount"], 11);
    assert_eq!(assessment_three["totals"]["semanticReadyCount"], 4);
    assert_eq!(assessment_three["totals"]["maintenanceReadyCount"], 0);
    assert_eq!(
        assessment_three["gapCounts"]["MS-PROGRAM-EVIDENCE-UNBOUND"],
        469
    );
    assert_eq!(assessment_four["totals"]["programBoundCount"], 13);
    assert_eq!(assessment_four["totals"]["semanticReadyCount"], 6);
    assert_eq!(assessment_four["totals"]["maintenanceReadyCount"], 2);
    assert_eq!(
        assessment_four["gapCounts"]["MS-PROGRAM-EVIDENCE-UNBOUND"],
        467
    );
    assert_eq!(
        assessment_four["inputs"]["programFactsSha256"], fifth["tables"]["programFactsSha256"],
        "historical assessment must retain its own program-fact cut"
    );

    let generation = &generation_rounds["first-four-case-generation-round-1-readiness-baseline"];
    assert_eq!(generation["roundIndex"], 1);
    assert_eq!(generation["parentRoundSha256"], Value::Null);
    assert_eq!(generation["decision"], "continue");
    assert_eq!(generation["automaticPromotion"], false);
    assert_eq!(generation["maintainerSkillRefreshRoundId"], third["id"]);
    assert_eq!(
        generation["knowledgeCutSha256"],
        "2e31989f0ec07c82f57aa580dd0845bd385699429dec43bf43e838253b7b874a",
        "the historical generation baseline must retain its original knowledge cut"
    );
    assert_eq!(
        generation["coverage"]["scopeSkillCount"], 480,
        "baseline must measure the complete structural partition"
    );
    assert!(generation["candidates"]["generatedIds"]
        .as_array()
        .unwrap()
        .is_empty());
    assert!(generation["qualification"]["qualifiedCaseIds"]
        .as_array()
        .unwrap()
        .is_empty());
}
