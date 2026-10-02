use agentlab_code_analysis::digest;
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
    process::Command,
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

fn canonical_table_digest(path: &Path) -> String {
    let mut bytes = Vec::new();
    for row in rows(path).values() {
        bytes.extend(serde_json::to_vec(row).unwrap());
        bytes.push(b'\n');
    }
    digest(&bytes)
}

fn json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn method_at_revision(root: &Path, revision: &str, path: &str) -> Vec<u8> {
    assert_eq!(revision.len(), 40, "method revision must be exact");
    assert!(revision.bytes().all(|byte| byte.is_ascii_hexdigit()));
    let output = Command::new("git")
        .args([
            "-C",
            root.to_str().unwrap(),
            "show",
            &format!("{revision}:{path}"),
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "method revision must resolve its Skill bytes"
    );
    output.stdout
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
    assert_eq!(
        skills
            .values()
            .filter(|skill| skill["skillLayer"] == "instance")
            .count(),
        12
    );
    assert_eq!(
        skills
            .values()
            .filter(|skill| skill["skillLayer"] == "method")
            .count(),
        1
    );
    assert!(facts.len() >= 24);
    assert!(refresh_rounds.len() >= 5);
    assert!(!generation_rounds.is_empty());
    assert!(
        fs::read_to_string(baseline.join("evaluation_cases.jsonl"))
            .unwrap()
            .is_empty(),
        "repository knowledge must not silently promote cases"
    );

    let mut stages_by_repository: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (skill_id, skill) in &skills {
        assert_eq!(skill["ownershipPlane"], "target-operations", "{skill_id}");
        let repository_id = skill["repositoryId"].as_str().unwrap();
        let revision = repositories.get(repository_id).unwrap();
        assert_eq!(skill["sourceRevision"].as_str().unwrap(), revision);
        if skill["skillLayer"] == "method" {
            assert_eq!(skill["stage"], "calibration");
            assert_eq!(skill["automaticPromotion"], false);
            assert_eq!(skill["methodSkillId"], "agentlab-experiment-learning");
            assert_eq!(
                skill["methodDigest"],
                digest(&method_at_revision(
                    &root,
                    skill["methodRevision"].as_str().unwrap(),
                    "skills/agentlab-experiment-learning/SKILL.md"
                ))
            );
            let bound = ids(skill, "factIds");
            assert_eq!(bound.len(), 1);
            let fact = &facts[&bound[0]];
            assert_eq!(fact["kind"], "verified-lesson");
            assert_eq!(fact["repositoryId"], repository_id);
            assert_eq!(fact["sourceRevision"].as_str().unwrap(), revision);
            assert_eq!(fact["lessonSource"], skill["lessonSource"]);
            assert_eq!(
                fact["sourceLessonExportDigest"],
                skill["sourceLessonExportDigest"]
            );
            for key in [
                "caseQualified",
                "harmonyBuildQualified",
                "harmonyRuntimeQualified",
                "uiQualified",
                "producerAuthenticated",
            ] {
                assert_eq!(fact["qualification"][key], false);
            }
            continue;
        }
        assert_eq!(skill["skillLayer"], "instance", "{skill_id}");
        stages_by_repository
            .entry(repository_id.to_owned())
            .or_default()
            .insert(skill["stage"].as_str().unwrap().to_owned());

        if skill["stage"] == "seed-extraction" {
            let revision = skill["methodRevision"].as_str().unwrap();
            assert_eq!(
                skill["methodDigest"],
                digest(&method_at_revision(
                    &root,
                    revision,
                    "skills/agentlab-seed-extraction/SKILL.md",
                )),
                "{skill_id} does not bind its exact iterative generation method revision"
            );
        }
        if skill["stage"] == "repository-analysis" {
            let revision = skill["methodRevision"].as_str().unwrap();
            assert_eq!(
                skill["methodDigest"],
                digest(&method_at_revision(
                    &root,
                    revision,
                    "skills/agentlab-codebase-analysis/SKILL.md",
                )),
                "{skill_id} does not bind its exact evidence-flywheel method revision"
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
                    let evidence_path = match item["root"].as_str() {
                        None => root.join(path), // Historical publication-relative links.
                        Some("operation-receipts") => {
                            assert_eq!(item["path"], fact["operationEvidence"]["path"]);
                            assert_eq!(item["sha256"], fact["operationEvidence"]["sha256"]);
                            assert!(Path::new(path)
                                .components()
                                .all(|part| matches!(part, std::path::Component::Normal(_))));
                            let receipts = baseline.join("operation-evidence");
                            let target = receipts.join(path);
                            assert!(target
                                .canonicalize()
                                .unwrap()
                                .starts_with(receipts.canonicalize().unwrap()));
                            target
                        }
                        Some(other) => panic!("unsupported evidence root {other}"),
                    };
                    let bytes = fs::read(evidence_path).unwrap();
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
        canonical_table_digest(&baseline.join("maintainer_skills.jsonl"))
    );
    assert_eq!(
        latest["tables"]["scopeSkillsSha256"],
        canonical_table_digest(&baseline.join("maintainer_scope_skills.jsonl"))
    );
    assert_eq!(
        latest["tables"]["programFactsSha256"],
        canonical_table_digest(&baseline.join("program_facts.jsonl"))
    );
    assert_eq!(
        latest["assessment"]["sha256"],
        digest(&fs::read(baseline.join(latest["assessment"]["path"].as_str().unwrap())).unwrap())
    );
    // TableGit tables bind canonical row values; strict assessments separately
    // bind original raw input bytes. Neither identity substitutes for the other.
    let latest_report = json(&baseline.join(latest["assessment"]["path"].as_str().unwrap()));
    for (key, name) in [
        ("scopeSkillsSha256", "maintainer_scope_skills.jsonl"),
        ("programFactsSha256", "program_facts.jsonl"),
    ] {
        assert_eq!(
            latest_report["inputs"][key],
            digest(&fs::read(baseline.join(name)).unwrap())
        );
    }

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

    let mut ordered_generation_rounds = generation_rounds.values().collect::<Vec<_>>();
    ordered_generation_rounds.sort_by_key(|row| row["roundIndex"].as_u64().unwrap());
    assert_eq!(ordered_generation_rounds[0]["roundIndex"], 1);
    assert_eq!(
        ordered_generation_rounds[0]["parentRoundSha256"],
        Value::Null
    );
    for row in &ordered_generation_rounds {
        assert_eq!(
            row["automaticPromotion"], false,
            "case-generation rounds must never promote candidates automatically"
        );
    }
    for pair in ordered_generation_rounds.windows(2) {
        assert_eq!(
            pair[1]["parentRoundSha256"],
            digest(&serde_json::to_vec(pair[0]).unwrap()),
            "case-generation round lineage differs"
        );
        assert_eq!(
            pair[1]["roundIndex"].as_u64().unwrap(),
            pair[0]["roundIndex"].as_u64().unwrap() + 1,
            "case-generation round indices are not contiguous"
        );
    }
}
