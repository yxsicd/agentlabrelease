use crate::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path, PathBuf},
};

const CUT_SCHEMA: &str = "agentlab.maintainer_knowledge_cut.v1";
const BINDING_SCHEMA: &str = "agentlab.candidate_knowledge_binding.v1";
const SOURCE_SCHEMA: &str = "agentlab.multi_repo_manifest.v1";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GateStage {
    Candidate,
    Construction,
    Calibration,
    Freeze,
}

impl GateStage {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "candidate" => Ok(Self::Candidate),
            "construction" => Ok(Self::Construction),
            "calibration" => Ok(Self::Calibration),
            "freeze" => Ok(Self::Freeze),
            _ => Err(format!("unsupported knowledge-gate stage: {value}")),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Candidate => "candidate",
            Self::Construction => "construction",
            Self::Calibration => "calibration",
            Self::Freeze => "freeze",
        }
    }
}

fn require(condition: bool, message: impl Into<String>) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(message.into())
    }
}

fn load_json(path: &Path, label: &str) -> Result<Value, String> {
    require(
        path.is_file() && !path.is_symlink(),
        format!("{label} must be a regular file"),
    )?;
    serde_json::from_slice(&fs::read(path).map_err(|error| format!("read {label}: {error}"))?)
        .map_err(|error| format!("parse {label}: {error}"))
}

fn load_jsonl(
    path: &Path,
    label: &str,
    require_nonempty: bool,
) -> Result<BTreeMap<String, Value>, String> {
    require(
        path.is_file() && !path.is_symlink(),
        format!("{label} must be a regular file"),
    )?;
    let text = fs::read_to_string(path).map_err(|error| format!("read {label}: {error}"))?;
    let mut rows = BTreeMap::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row: Value = serde_json::from_str(line)
            .map_err(|error| format!("parse {label} line {}: {error}", index + 1))?;
        let id = row["id"]
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| format!("{label} line {} has no id", index + 1))?
            .to_owned();
        require(
            rows.insert(id.clone(), row).is_none(),
            format!("{label} duplicates id {id}"),
        )?;
    }
    if require_nonempty {
        require(!rows.is_empty(), format!("{label} is empty"))?;
    }
    Ok(rows)
}

fn file_digest(path: &Path) -> Result<String, String> {
    Ok(digest(&fs::read(path).map_err(|error| {
        format!("read {}: {error}", path.display())
    })?))
}

fn table_path(cut_path: &Path, cut: &Value, name: &str) -> Result<PathBuf, String> {
    let row = &cut["tables"][name];
    let relative = row["path"]
        .as_str()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("knowledge cut table {name} has no path"))?;
    let relative_path = Path::new(relative);
    require(
        relative_path
            .components()
            .all(|component| matches!(component, Component::Normal(_))),
        format!("knowledge cut table {name} path must be a safe relative path"),
    )?;
    let path = cut_path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(relative_path);
    let expected = row["sha256"]
        .as_str()
        .ok_or_else(|| format!("knowledge cut table {name} has no sha256"))?;
    require(
        file_digest(&path)? == expected,
        format!("knowledge cut table {name} digest differs"),
    )?;
    Ok(path)
}

fn string_set(value: &Value, label: &str) -> Result<BTreeSet<String>, String> {
    let rows = value
        .as_array()
        .ok_or_else(|| format!("{label} must be an array"))?;
    let mut result = BTreeSet::new();
    for row in rows {
        let item = row
            .as_str()
            .filter(|item| !item.is_empty())
            .ok_or_else(|| format!("{label} contains an invalid identifier"))?;
        require(
            result.insert(item.to_owned()),
            format!("{label} duplicates {item}"),
        )?;
    }
    require(!result.is_empty(), format!("{label} must not be empty"))?;
    Ok(result)
}

fn repositories(value: &Value, field: &str) -> Result<BTreeMap<String, (String, String)>, String> {
    let rows = value[field]
        .as_array()
        .ok_or_else(|| format!("{field} must be an array"))?;
    let mut result = BTreeMap::new();
    for row in rows {
        let id = row["id"]
            .as_str()
            .filter(|item| !item.is_empty())
            .ok_or_else(|| format!("{field} repository has no id"))?;
        let repository = row["repository"]
            .as_str()
            .filter(|item| !item.is_empty())
            .ok_or_else(|| format!("{field} repository {id} has no URL"))?;
        let revision = row["revision"]
            .as_str()
            .filter(|item| item.len() == 40 && item.bytes().all(|byte| byte.is_ascii_hexdigit()))
            .ok_or_else(|| format!("{field} repository {id} has an invalid revision"))?;
        require(
            result
                .insert(id.to_owned(), (repository.to_owned(), revision.to_owned()))
                .is_none(),
            format!("{field} duplicates repository {id}"),
        )?;
    }
    require(!result.is_empty(), format!("{field} has no repositories"))?;
    Ok(result)
}

fn require_text_array(value: &Value, label: &str) -> Result<(), String> {
    let rows = value
        .as_array()
        .ok_or_else(|| format!("{label} must be an array"))?;
    require(
        !rows.is_empty()
            && rows
                .iter()
                .all(|row| row.as_str().is_some_and(|text| !text.trim().is_empty())),
        format!("{label} must contain non-empty text"),
    )
}

fn candidate<'a>(difficulty: &'a Value, candidate_id: &str) -> Result<&'a Value, String> {
    let rows = difficulty["candidates"]
        .as_array()
        .ok_or_else(|| "difficulty evidence has no candidates".to_owned())?;
    let matches: Vec<_> = rows
        .iter()
        .filter(|row| row["id"].as_str() == Some(candidate_id))
        .collect();
    require(
        matches.len() == 1,
        "candidate is absent or duplicated in difficulty evidence",
    )?;
    Ok(matches[0])
}

pub fn validate_gate(
    stage: GateStage,
    source_spec_path: &Path,
    difficulty_path: &Path,
    knowledge_cut_path: &Path,
    binding_path: &Path,
    candidate_id: &str,
) -> Result<Value, String> {
    let source_spec = load_json(source_spec_path, "source specification")?;
    let difficulty = load_json(difficulty_path, "difficulty evidence")?;
    let cut = load_json(knowledge_cut_path, "maintainer knowledge cut")?;
    let binding = load_json(binding_path, "candidate knowledge binding")?;
    require(
        source_spec["schema"].as_str() == Some(SOURCE_SCHEMA),
        "unsupported source specification",
    )?;
    require(
        cut["schema"].as_str() == Some(CUT_SCHEMA),
        "unsupported maintainer knowledge cut",
    )?;
    require(
        binding["schema"].as_str() == Some(BINDING_SCHEMA),
        "unsupported candidate knowledge binding",
    )?;
    require(
        cut["automaticPromotion"].as_bool() == Some(false),
        "knowledge cut can auto-promote",
    )?;
    require(
        binding["automaticPromotion"].as_bool() == Some(false),
        "candidate binding can auto-promote",
    )?;
    require(
        binding["candidateId"].as_str() == Some(candidate_id),
        "candidate binding identity differs",
    )?;
    let candidate = candidate(&difficulty, candidate_id)?;
    let candidate_sha = digest(&serde_json::to_vec(candidate).map_err(|error| error.to_string())?);
    require(
        binding["candidateSha256"].as_str() == Some(candidate_sha.as_str()),
        "candidate binding digest differs",
    )?;
    let source_set = difficulty["sourceSetSha256"]
        .as_str()
        .ok_or_else(|| "difficulty evidence has no sourceSetSha256".to_owned())?;
    require(
        cut["sourceSetSha256"].as_str() == Some(source_set),
        "knowledge cut source set differs",
    )?;
    require(
        binding["sourceSetSha256"].as_str() == Some(source_set),
        "candidate binding source set differs",
    )?;
    require(
        binding["knowledgeCutSha256"].as_str() == Some(file_digest(knowledge_cut_path)?.as_str()),
        "candidate binding knowledge cut digest differs",
    )?;
    let source_repositories = repositories(&source_spec, "repositories")?;
    let difficulty_repositories = repositories(&difficulty, "sources")?;
    let cut_repositories = repositories(&cut, "repositories")?;
    require(
        source_repositories == difficulty_repositories,
        "difficulty repositories differ from source specification",
    )?;
    require(
        source_repositories == cut_repositories,
        "knowledge cut does not cover the exact source set",
    )?;
    let policy = &cut["policy"];
    for field in [
        "wholeRepositoryInventoryRequired",
        "semanticCoverageRequired",
        "programAnalysisBound",
        "candidateBindingsRequired",
    ] {
        require(
            policy[field].as_bool() == Some(true),
            format!("knowledge cut policy {field} is not required"),
        )?;
    }

    let skills_path = table_path(knowledge_cut_path, &cut, "maintainerSkills")?;
    let scope_skills_path = table_path(knowledge_cut_path, &cut, "maintainerScopeSkills")?;
    let refresh_rounds_path = table_path(knowledge_cut_path, &cut, "maintainerSkillRefreshRounds")?;
    let facts_path = table_path(knowledge_cut_path, &cut, "programFacts")?;
    let cases_path = table_path(knowledge_cut_path, &cut, "evaluationCases")?;
    let skills = load_jsonl(&skills_path, "maintainer skills", true)?;
    let scope_skills = load_jsonl(&scope_skills_path, "maintainer scope Skills", true)?;
    let refresh_rounds = load_jsonl(
        &refresh_rounds_path,
        "Maintainer Skill refresh rounds",
        true,
    )?;
    let facts = load_jsonl(&facts_path, "program facts", true)?;
    let cases = load_jsonl(
        &cases_path,
        "evaluation cases",
        matches!(stage, GateStage::Calibration | GateStage::Freeze),
    )?;
    for (id, row) in &skills {
        require(
            row["ownershipPlane"].as_str() == Some("target-operations"),
            format!("maintainer Skill {id} is not target-operations knowledge"),
        )?;
    }
    let mut ordered_rounds: Vec<_> = refresh_rounds.values().collect();
    ordered_rounds.sort_by_key(|row| row["roundIndex"].as_u64().unwrap_or(0));
    let mut previous_round_digest: Option<String> = None;
    for (offset, row) in ordered_rounds.iter().enumerate() {
        let expected_index = (offset + 1) as u64;
        require(
            row["roundIndex"].as_u64() == Some(expected_index),
            "Maintainer Skill refresh rounds are not contiguous",
        )?;
        require(
            row["ownershipPlane"].as_str() == Some("target-operations")
                && row["automaticPromotion"].as_bool() == Some(false),
            "Maintainer Skill refresh round crosses its ownership boundary",
        )?;
        require(
            row["parentRoundSha256"].as_str() == previous_round_digest.as_deref(),
            "Maintainer Skill refresh-round parent differs",
        )?;
        previous_round_digest = Some(digest(
            &serde_json::to_vec(row).map_err(|error| error.to_string())?,
        ));
    }
    let latest_round = ordered_rounds
        .last()
        .ok_or_else(|| "Maintainer Skill refresh history is empty".to_owned())?;
    require(
        latest_round["tables"]["processSkillsSha256"].as_str()
            == Some(file_digest(&skills_path)?.as_str())
            && latest_round["tables"]["scopeSkillsSha256"].as_str()
                == Some(file_digest(&scope_skills_path)?.as_str())
            && latest_round["tables"]["programFactsSha256"].as_str()
                == Some(file_digest(&facts_path)?.as_str()),
        "latest Maintainer Skill refresh round does not bind the current tables",
    )?;
    let mut scope_skill_repositories = BTreeSet::new();
    for (id, row) in &scope_skills {
        let repository_id = row["repositoryId"]
            .as_str()
            .ok_or_else(|| format!("maintainer scope Skill {id} has no repositoryId"))?;
        let (_, revision) = source_repositories.get(repository_id).ok_or_else(|| {
            format!("maintainer scope Skill {id} references unknown repository {repository_id}")
        })?;
        require(
            row["sourceRevision"].as_str() == Some(revision),
            format!("maintainer scope Skill {id} revision differs"),
        )?;
        require(
            row["skillLayer"].as_str() == Some("instance")
                && row["stage"].as_str() == Some("repository-scope")
                && row["ownershipPlane"].as_str() == Some("target-operations"),
            format!("maintainer scope Skill {id} is not an instance repository-scope Skill"),
        )?;
        require(
            row["trackedFileCount"]
                .as_u64()
                .is_some_and(|count| count > 0),
            format!("maintainer scope Skill {id} has no tracked-file coverage"),
        )?;
        require(
            row["automaticPromotion"].as_bool() == Some(false),
            format!("maintainer scope Skill {id} can auto-promote"),
        )?;
        scope_skill_repositories.insert(repository_id.to_owned());
    }
    require(
        scope_skill_repositories == source_repositories.keys().cloned().collect(),
        "maintainer scope Skill catalog does not cover every source repository",
    )?;
    let bindings = binding["repositoryBindings"]
        .as_array()
        .ok_or_else(|| "candidate binding has no repositoryBindings".to_owned())?;
    let mut bound_repositories = BTreeSet::new();
    let mut all_skill_ids = BTreeSet::new();
    let mut all_scope_skill_ids = BTreeSet::new();
    let mut all_fact_ids = BTreeSet::new();
    let mut all_analysis_ids = BTreeSet::new();
    for repository_binding in bindings {
        let repository_id = repository_binding["repositoryId"]
            .as_str()
            .ok_or_else(|| "repository binding has no repositoryId".to_owned())?;
        require(
            bound_repositories.insert(repository_id.to_owned()),
            format!("duplicate repository binding {repository_id}"),
        )?;
        let (_, revision) = source_repositories
            .get(repository_id)
            .ok_or_else(|| format!("binding references unknown repository {repository_id}"))?;
        require(
            repository_binding["revision"].as_str() == Some(revision),
            format!("binding revision differs for {repository_id}"),
        )?;
        let skill_ids = string_set(
            &repository_binding["skillIds"],
            &format!("{repository_id} skillIds"),
        )?;
        let sku_ids = string_set(
            &repository_binding["scopeSkillIds"],
            &format!("{repository_id} scopeSkillIds"),
        )?;
        let fact_ids = string_set(
            &repository_binding["factIds"],
            &format!("{repository_id} factIds"),
        )?;
        let analysis_ids = string_set(
            &repository_binding["analysisIds"],
            &format!("{repository_id} analysisIds"),
        )?;
        let mut stages = BTreeSet::new();
        for id in &skill_ids {
            let row = skills
                .get(id)
                .ok_or_else(|| format!("unknown maintainer Skill {id}"))?;
            require(
                row["sourceRevision"].as_str() == Some(revision),
                format!("maintainer Skill {id} revision differs"),
            )?;
            require(
                row["skillLayer"].as_str() == Some("instance"),
                format!("maintainer Skill {id} is not an instance Skill"),
            )?;
            require(
                row["ownershipPlane"].as_str() == Some("target-operations"),
                format!("maintainer Skill {id} is not target-operations knowledge"),
            )?;
            if let Some(stage) = row["stage"].as_str() {
                stages.insert(stage.to_owned());
            }
            all_skill_ids.insert(id.clone());
        }
        for id in &sku_ids {
            let row = scope_skills
                .get(id)
                .ok_or_else(|| format!("unknown maintainer scope Skill {id}"))?;
            require(
                row["repositoryId"].as_str() == Some(repository_id),
                format!("maintainer scope Skill {id} repository differs"),
            )?;
            require(
                row["sourceRevision"].as_str() == Some(revision),
                format!("maintainer scope Skill {id} revision differs"),
            )?;
            require(
                row["automaticPromotion"].as_bool() == Some(false),
                format!("maintainer scope Skill {id} can auto-promote"),
            )?;
            require(
                row["trackedFileCount"]
                    .as_u64()
                    .is_some_and(|count| count > 0),
                format!("maintainer scope Skill {id} has no tracked-file coverage"),
            )?;
            all_scope_skill_ids.insert(id.clone());
        }
        for required_stage in ["repository-analysis", "program-analysis", "seed-extraction"] {
            require(
                stages.contains(required_stage),
                format!("{repository_id} has no {required_stage} Skill"),
            )?;
        }
        for id in &fact_ids {
            let row = facts
                .get(id)
                .ok_or_else(|| format!("unknown program fact {id}"))?;
            require(
                row["sourceRevision"].as_str() == Some(revision),
                format!("program fact {id} revision differs"),
            )?;
            all_fact_ids.insert(id.clone());
        }
        for id in &analysis_ids {
            let row = facts
                .get(id)
                .ok_or_else(|| format!("unknown analysis record {id}"))?;
            require(
                row["kind"].as_str() == Some("analysis"),
                format!("program fact {id} is not an analysis record"),
            )?;
            require(
                row["sourceRevision"].as_str() == Some(revision),
                format!("analysis record {id} revision differs"),
            )?;
            all_analysis_ids.insert(id.clone());
        }
        let coverage = &repository_binding["coverage"];
        for field in [
            "architecture",
            "buildAndTestEntrypoints",
            "behaviorContracts",
            "stateTransitions",
            "crossFileResponsibilities",
            "knownGaps",
        ] {
            require_text_array(
                &coverage[field],
                &format!("{repository_id} coverage.{field}"),
            )?;
        }
    }
    require(
        bound_repositories == source_repositories.keys().cloned().collect(),
        "candidate binding does not cover every source repository exactly once",
    )?;
    let behavior = &binding["behaviorContract"];
    for field in [
        "responsibilities",
        "stateTransitions",
        "acceptanceObservables",
        "unresolvedRisks",
    ] {
        require_text_array(&behavior[field], &format!("behaviorContract.{field}"))?;
    }

    if matches!(
        stage,
        GateStage::Construction | GateStage::Calibration | GateStage::Freeze
    ) {
        let construction = &binding["construction"];
        for field in [
            "taskDemands",
            "editablePaths",
            "contextPaths",
            "oracleRequirements",
        ] {
            require_text_array(&construction[field], &format!("construction.{field}"))?;
        }
    }
    if matches!(stage, GateStage::Calibration | GateStage::Freeze) {
        let case_id = binding["caseId"]
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| "calibration requires caseId".to_owned())?;
        let row = cases
            .get(case_id)
            .ok_or_else(|| format!("unknown evaluation case {case_id}"))?;
        require(
            row["sourceSetSha256"].as_str() == Some(source_set),
            "evaluation case source set differs",
        )?;
        require(
            row["knowledgeCutSha256"].as_str() == Some(file_digest(knowledge_cut_path)?.as_str()),
            "evaluation case knowledge cut differs",
        )?;
        require(
            string_set(&row["skillIds"], "evaluation case skillIds")? == all_skill_ids,
            "evaluation case Skill binding differs",
        )?;
        require(
            string_set(&row["scopeSkillIds"], "evaluation case scopeSkillIds")?
                == all_scope_skill_ids,
            "evaluation case scope Skill binding differs",
        )?;
        require(
            string_set(&row["factIds"], "evaluation case factIds")? == all_fact_ids,
            "evaluation case fact binding differs",
        )?;
        require(
            string_set(&row["analysisIds"], "evaluation case analysisIds")? == all_analysis_ids,
            "evaluation case analysis binding differs",
        )?;
        require(
            row["oracleDigest"]
                .as_str()
                .is_some_and(|value| value.len() == 64),
            "evaluation case has no oracle digest",
        )?;
    }
    if stage == GateStage::Freeze {
        let freeze = &binding["freeze"];
        require(
            freeze["status"].as_str() == Some("frozen"),
            "freeze binding is not frozen",
        )?;
        require_text_array(&freeze["acceptedVariants"], "freeze.acceptedVariants")?;
        require_text_array(&freeze["rejectedVariants"], "freeze.rejectedVariants")?;
        require(
            freeze["independentReviewApproved"].as_bool() == Some(true),
            "freeze has no independent review approval",
        )?;
    }

    Ok(json!({
        "schema":"agentlab.maintainer_knowledge_gate_receipt.v1",
        "status":"passed",
        "stage":stage.as_str(),
        "candidateId":candidate_id,
        "candidateSha256":candidate_sha,
        "sourceSetSha256":source_set,
        "knowledgeCutSha256":file_digest(knowledge_cut_path)?,
        "bindingSha256":file_digest(binding_path)?,
        "repositoryCount":source_repositories.len(),
        "maintainerSkillCount":all_skill_ids.len(),
        "maintainerScopeSkillCount":all_scope_skill_ids.len(),
        "maintainerSkillRefreshRoundCount":ordered_rounds.len(),
        "latestMaintainerSkillRefreshRound":latest_round["id"],
        "programFactCount":all_fact_ids.len(),
        "analysisRecordCount":all_analysis_ids.len(),
        "caseBound":matches!(stage, GateStage::Calibration | GateStage::Freeze),
        "automaticPromotion":false
    }))
}
