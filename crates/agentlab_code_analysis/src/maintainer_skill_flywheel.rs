use crate::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

const SCOPE_SCHEMA: &str = "agentlab.maintainer_scope_skill.v1";
const ASSESSMENT_SCHEMA: &str = "agentlab.maintainer_skill_assessment.v1";
const DIMENSIONS: [&str; 5] = [
    "responsibility",
    "boundary",
    "relations",
    "behavior",
    "operation",
];

fn require(condition: bool, message: impl Into<String>) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(message.into())
    }
}

fn load_jsonl(path: &Path, label: &str, allow_empty: bool) -> Result<Vec<Value>, String> {
    require(
        path.is_file() && !path.is_symlink(),
        format!("{label} must be a regular file"),
    )?;
    let text = fs::read_to_string(path).map_err(|error| format!("read {label}: {error}"))?;
    let mut rows = Vec::new();
    let mut ids = BTreeSet::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row: Value = serde_json::from_str(line)
            .map_err(|error| format!("parse {label} line {}: {error}", index + 1))?;
        let id = row["id"]
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| format!("{label} line {} has no id", index + 1))?;
        require(
            ids.insert(id.to_owned()),
            format!("{label} duplicates {id}"),
        )?;
        rows.push(row);
    }
    require(allow_empty || !rows.is_empty(), format!("{label} is empty"))?;
    Ok(rows)
}

fn strings(value: &Value) -> BTreeSet<String> {
    value
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect()
}

fn valid_hex(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|value| {
        value.len() == length && value.bytes().all(|byte| byte.is_ascii_hexdigit())
    })
}

fn boundary_matches(boundary: &str, path: &str) -> bool {
    boundary == "." || path == boundary || path.starts_with(&format!("{boundary}/"))
}

fn selector_specificity(selector: &Value, path: &str) -> Option<usize> {
    match selector["type"].as_str()? {
        "prefix" => {
            let prefix = selector["path"].as_str()?;
            boundary_matches(prefix, path).then_some(prefix.len())
        }
        "files" => selector["paths"]
            .as_array()?
            .iter()
            .filter_map(Value::as_str)
            .any(|candidate| candidate == path)
            .then_some(usize::MAX),
        _ => None,
    }
}

fn valid_selector(selector: &Value) -> bool {
    match selector["type"].as_str() {
        Some("prefix") => selector["path"]
            .as_str()
            .is_some_and(|path| !path.is_empty()),
        Some("files") => selector["paths"].as_array().is_some_and(|paths| {
            !paths.is_empty()
                && paths
                    .iter()
                    .all(|path| path.as_str().is_some_and(|path| !path.is_empty()))
        }),
        _ => false,
    }
}

fn scope_specificity(skill: &Value, path: &str) -> Option<usize> {
    if let Some(selectors) = skill["ownershipSelectors"].as_array() {
        return selectors
            .iter()
            .filter_map(|selector| selector_specificity(selector, path))
            .max();
    }
    let boundary = skill["pathBoundary"].as_str()?;
    boundary_matches(boundary, path).then_some(boundary.len())
}

fn valid_scope_ownership(skill: &Value) -> bool {
    skill["ownershipSelectors"]
        .as_array()
        .map_or(true, |selectors| {
            !selectors.is_empty() && selectors.iter().all(valid_selector)
        })
}

fn evidence_path_is_owned(skill: &Value, path: &str) -> bool {
    skill["ownershipSelectors"]
        .as_array()
        .map_or(true, |_| scope_specificity(skill, path).is_some())
}

fn fact_dimensions(fact: &Value) -> BTreeSet<String> {
    let explicit = strings(&fact["dimensions"]);
    if !explicit.is_empty() {
        return explicit;
    }
    match fact["kind"].as_str().unwrap_or_default() {
        "architecture" | "dependency-relation" | "call-relation" | "data-flow" => {
            BTreeSet::from(["boundary".to_owned(), "relations".to_owned()])
        }
        "behavior-contract" | "state-transition" | "invariant" | "error-contract" => {
            BTreeSet::from(["behavior".to_owned()])
        }
        // Operation evidence is never inferred from a descriptive kind. L3
        // requires an explicit revision-bound operation dimension so a blocked
        // preflight or partial build cannot masquerade as maintenance proof.
        "build-test-entrypoint" | "runtime-verification" => BTreeSet::new(),
        _ => BTreeSet::new(),
    }
}

fn scope_fact_dimensions(fact: &Value, skill_id: &str) -> BTreeSet<String> {
    let mut dimensions = fact_dimensions(fact);
    // A dependency's successful operation does not qualify its consumers.
    // Operation coverage must name the assessed scope explicitly.
    if !strings(&fact["scopeSkillIds"]).contains(skill_id) {
        dimensions.remove("operation");
    }
    dimensions
}

fn capability_tags(skill: &Value) -> Vec<String> {
    let source_count = skill["sourceFileCount"].as_u64().unwrap_or(0);
    let test_count = skill["testFileCount"].as_u64().unwrap_or(0);
    let build_count = skill["buildEntrypoints"].as_array().map_or(0, Vec::len);
    let dependency_count = skill["externalDependencyCount"].as_u64().unwrap_or(0);
    let mut result = Vec::new();
    if source_count > 0 {
        result.push("source-maintenance".to_owned());
    }
    if test_count > 0 {
        result.push("test-maintenance".to_owned());
    }
    if build_count > 0 {
        result.push("build-maintenance".to_owned());
    }
    if dependency_count > 0 {
        result.push("external-boundary".to_owned());
    }
    if result.is_empty() {
        result.push("support-maintenance".to_owned());
    }
    result
}

fn gap(code: &str, dimension: &str, severity: &str, message: String) -> Value {
    json!({
        "code":code,
        "dimension":dimension,
        "severity":severity,
        "message":message
    })
}

pub fn assess(
    scope_path: &Path,
    program_facts_path: Option<&Path>,
    round_index: u64,
    parent_assessment_sha256: Option<&str>,
) -> Result<Value, String> {
    require(round_index >= 1, "round index must be positive")?;
    if round_index == 1 {
        require(
            parent_assessment_sha256.is_none(),
            "round 1 must not have a parent assessment",
        )?;
    } else {
        require(
            parent_assessment_sha256.is_some_and(|value| {
                value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
            }),
            "later rounds require a parent assessment SHA-256",
        )?;
    }
    let scopes = load_jsonl(scope_path, "scope Skills", false)?;
    let facts = if let Some(path) = program_facts_path {
        load_jsonl(path, "program facts", true)?
    } else {
        Vec::new()
    };
    let mut scope_index = BTreeMap::<String, usize>::new();
    let mut repository_scopes = BTreeMap::<String, Vec<usize>>::new();
    for (index, skill) in scopes.iter().enumerate() {
        let id = skill["id"].as_str().unwrap_or_default();
        require(
            skill["schema"].as_str() == Some(SCOPE_SCHEMA),
            format!("{id} uses an unsupported scope Skill schema"),
        )?;
        let repository_id = skill["repositoryId"]
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| format!("{id} has no repositoryId"))?;
        scope_index.insert(id.to_owned(), index);
        repository_scopes
            .entry(repository_id.to_owned())
            .or_default()
            .push(index);
    }

    let mut fact_bindings = BTreeMap::<String, BTreeSet<String>>::new();
    let mut binding_modes = BTreeMap::<(String, String), String>::new();
    for fact in &facts {
        let fact_id = fact["id"].as_str().unwrap_or_default().to_owned();
        let repository_id = fact["repositoryId"].as_str().unwrap_or_default();
        let mut bound = BTreeSet::new();
        for skill_id in strings(&fact["scopeSkillIds"]) {
            let index = *scope_index
                .get(&skill_id)
                .ok_or_else(|| format!("fact {fact_id} names missing scope Skill {skill_id}"))?;
            require(
                scopes[index]["repositoryId"].as_str() == Some(repository_id),
                format!("fact {fact_id} crosses repository boundary through {skill_id}"),
            )?;
            binding_modes.insert(
                (fact_id.clone(), skill_id.clone()),
                "explicit-scope-id".to_owned(),
            );
            bound.insert(skill_id);
        }
        if bound.is_empty() {
            for evidence in fact["evidence"].as_array().into_iter().flatten() {
                if !valid_hex(&evidence["gitBlobOid"], 40) {
                    continue;
                }
                let Some(path) = evidence["path"].as_str() else {
                    continue;
                };
                let mut matches = repository_scopes
                    .get(repository_id)
                    .into_iter()
                    .flatten()
                    .filter_map(|index| {
                        let skill = &scopes[*index];
                        let skill_id = skill["id"].as_str()?;
                        scope_specificity(skill, path)
                            .map(|specificity| (specificity, skill_id.to_owned()))
                    })
                    .collect::<Vec<_>>();
                matches.sort_by(|left, right| right.0.cmp(&left.0).then(left.1.cmp(&right.1)));
                if let Some((longest, _)) = matches.first() {
                    for (_, skill_id) in matches.iter().filter(|(length, _)| length == longest) {
                        binding_modes.insert(
                            (fact_id.clone(), skill_id.clone()),
                            "exact-path-boundary".to_owned(),
                        );
                        bound.insert(skill_id.clone());
                    }
                }
            }
        }
        fact_bindings.insert(fact_id, bound);
    }
    for _ in 0..facts.len() {
        let mut changed = false;
        for fact in &facts {
            let fact_id = fact["id"].as_str().unwrap_or_default().to_owned();
            let inherited = strings(&fact["evidenceFactIds"])
                .into_iter()
                .flat_map(|id| fact_bindings.get(&id).cloned().unwrap_or_default())
                .collect::<BTreeSet<_>>();
            let target = fact_bindings.entry(fact_id.clone()).or_default();
            for skill_id in inherited {
                if target.insert(skill_id.clone()) {
                    binding_modes.insert(
                        (fact_id.clone(), skill_id),
                        "inherited-evidence-fact".to_owned(),
                    );
                    changed = true;
                }
            }
        }
        if !changed {
            break;
        }
    }

    let fact_by_id = facts
        .iter()
        .map(|fact| (fact["id"].as_str().unwrap_or_default(), fact))
        .collect::<BTreeMap<_, _>>();
    let mut skill_rows = Vec::new();
    let mut repository_rows = BTreeMap::<String, Vec<Value>>::new();
    let mut gap_counts = BTreeMap::<String, usize>::new();
    for skill in &scopes {
        let skill_id = skill["id"].as_str().unwrap_or_default();
        let repository_id = skill["repositoryId"].as_str().unwrap_or_default();
        let identity_ready = valid_hex(&skill["sourceRevision"], 40)
            && valid_hex(&skill["sourceTreeOid"], 40)
            && valid_scope_ownership(skill)
            && skill["repository"]
                .as_str()
                .is_some_and(|value| !value.is_empty())
            && skill["evidence"].as_array().is_some_and(|rows| {
                !rows.is_empty()
                    && rows.iter().all(|row| {
                        valid_hex(&row["gitBlobOid"], 40)
                            && row["path"]
                                .as_str()
                                .is_some_and(|path| evidence_path_is_owned(skill, path))
                    })
            });
        let structural_ready = identity_ready
            && skill["trackedFileCount"]
                .as_u64()
                .is_some_and(|value| value > 0)
            && skill["languages"]
                .as_object()
                .is_some_and(|value| !value.is_empty())
            && skill["responsibility"]
                .as_str()
                .is_some_and(|value| !value.trim().is_empty());
        let candidate_fact_ids = fact_bindings
            .iter()
            .filter(|(_, skills)| skills.contains(skill_id))
            .map(|(id, _)| id.clone())
            .collect::<BTreeSet<_>>();
        let mut rejected_bindings = Vec::new();
        let bound_fact_ids = candidate_fact_ids
            .into_iter()
            .filter(|id| {
                let fact = fact_by_id[id.as_str()];
                let reason = if fact["repositoryId"] != skill["repositoryId"] {
                    Some("repository-mismatch")
                } else if !valid_hex(&fact["sourceRevision"], 40)
                    || fact["sourceRevision"] != skill["sourceRevision"]
                {
                    Some("source-revision-mismatch")
                } else {
                    None
                };
                if let Some(reason) = reason {
                    rejected_bindings.push(json!({
                        "factId":id,
                        "reason":reason,
                        "repositoryId":fact["repositoryId"],
                        "sourceRevision":fact["sourceRevision"]
                    }));
                    false
                } else {
                    true
                }
            })
            .collect::<BTreeSet<_>>();
        let dimensions = bound_fact_ids
            .iter()
            .flat_map(|id| {
                fact_by_id
                    .get(id.as_str())
                    .map_or_else(BTreeSet::new, |fact| scope_fact_dimensions(fact, skill_id))
            })
            .filter(|dimension| DIMENSIONS.contains(&dimension.as_str()))
            .collect::<BTreeSet<_>>();
        let capabilities = capability_tags(skill);
        let source_maintenance = capabilities
            .iter()
            .any(|value| value == "source-maintenance");
        let mut required_semantic = BTreeSet::from([
            "responsibility".to_owned(),
            "boundary".to_owned(),
            "relations".to_owned(),
        ]);
        if source_maintenance {
            required_semantic.insert("behavior".to_owned());
        }
        let missing_semantic = required_semantic
            .difference(&dimensions)
            .cloned()
            .collect::<Vec<_>>();
        let semantic_ready =
            structural_ready && !bound_fact_ids.is_empty() && missing_semantic.is_empty();
        let maintenance_ready = semantic_ready && dimensions.contains("operation");
        let level = if maintenance_ready {
            "L3-maintenance-ready"
        } else if semantic_ready {
            "L2-semantic-ready"
        } else if structural_ready {
            "L1-structural-ready"
        } else {
            "L0-discovered"
        };
        let mut gaps = Vec::new();
        if !rejected_bindings.is_empty() {
            gaps.push(gap(
                "MS-EVIDENCE-IDENTITY-MISMATCH",
                "identity",
                "P1",
                format!("{} candidate fact bindings do not match this repository and source revision; refresh or explicitly revalidate them", rejected_bindings.len()),
            ));
        }
        if !identity_ready {
            gaps.push(gap(
                "MS-IDENTITY-INVALID",
                "identity",
                "P0",
                "source identity or Git evidence is incomplete".to_owned(),
            ));
        }
        if !structural_ready {
            gaps.push(gap(
                "MS-STRUCTURE-INCOMPLETE",
                "structure",
                "P0",
                "scope structure is incomplete".to_owned(),
            ));
        }
        if bound_fact_ids.is_empty() {
            gaps.push(gap(
                "MS-PROGRAM-EVIDENCE-UNBOUND",
                "relations",
                "P1",
                "no revision-matched program fact is bound to this scope".to_owned(),
            ));
        }
        for dimension in &missing_semantic {
            let code = format!("MS-{}-EVIDENCE-MISSING", dimension.to_ascii_uppercase());
            gaps.push(gap(
                &code,
                dimension,
                "P1",
                format!("no bound program fact proves the {dimension} dimension"),
            ));
        }
        if semantic_ready && !dimensions.contains("operation") {
            gaps.push(gap(
                "MS-OPERATION-EVIDENCE-MISSING",
                "operation",
                "P1",
                "semantic scope lacks executable build, test, runtime, or maintenance evidence"
                    .to_owned(),
            ));
        }
        for item in &gaps {
            *gap_counts
                .entry(item["code"].as_str().unwrap_or_default().to_owned())
                .or_default() += 1;
        }
        let bindings = bound_fact_ids
            .iter()
            .map(|fact_id| {
                json!({
                    "factId":fact_id,
                    "bindingMode":binding_modes.get(&(fact_id.clone(), skill_id.to_owned())).cloned().unwrap_or_else(|| "unknown".to_owned()),
                    "dimensions":fact_by_id.get(fact_id.as_str()).map_or_else(Vec::new, |fact| scope_fact_dimensions(fact, skill_id).into_iter().collect())
                })
            })
            .collect::<Vec<Value>>();
        let row = json!({
            "skillId":skill_id,
            "repositoryId":repository_id,
            "sourceRevision":skill["sourceRevision"],
            "capabilities":capabilities,
            "maturity":level,
            "checks":{
                "identityReady":identity_ready,
                "structuralReady":structural_ready,
                "programEvidenceBound":!bound_fact_ids.is_empty(),
                "semanticReady":semantic_ready,
                "maintenanceReady":maintenance_ready
            },
            "evidenceBindings":bindings,
            "rejectedEvidenceBindings":rejected_bindings,
            "provenDimensions":dimensions,
            "requiredSemanticDimensions":required_semantic,
            "gaps":gaps
        });
        repository_rows
            .entry(repository_id.to_owned())
            .or_default()
            .push(row.clone());
        skill_rows.push(row);
    }

    let mut repositories = Vec::new();
    let mut totals = BTreeMap::from([
        ("scopeSkillCount", 0usize),
        ("structuralReadyCount", 0usize),
        ("programBoundCount", 0usize),
        ("semanticReadyCount", 0usize),
        ("maintenanceReadyCount", 0usize),
    ]);
    for (repository_id, rows) in repository_rows {
        let count = rows.len();
        let structural = rows
            .iter()
            .filter(|row| row["checks"]["structuralReady"] == true)
            .count();
        let program = rows
            .iter()
            .filter(|row| row["checks"]["programEvidenceBound"] == true)
            .count();
        let semantic = rows
            .iter()
            .filter(|row| row["checks"]["semanticReady"] == true)
            .count();
        let maintenance = rows
            .iter()
            .filter(|row| row["checks"]["maintenanceReady"] == true)
            .count();
        *totals.get_mut("scopeSkillCount").unwrap() += count;
        *totals.get_mut("structuralReadyCount").unwrap() += structural;
        *totals.get_mut("programBoundCount").unwrap() += program;
        *totals.get_mut("semanticReadyCount").unwrap() += semantic;
        *totals.get_mut("maintenanceReadyCount").unwrap() += maintenance;
        repositories.push(json!({
            "repositoryId":repository_id,
            "scopeSkillCount":count,
            "structuralReadyCount":structural,
            "programBoundCount":program,
            "semanticReadyCount":semantic,
            "maintenanceReadyCount":maintenance,
            "readyForCaseGeneration":maintenance == count
        }));
    }
    let ready = totals["maintenanceReadyCount"] == totals["scopeSkillCount"];
    let next_round_objectives = gap_counts
        .iter()
        .map(|(code, count)| format!("close {count} {code} gaps with revision-bound evidence"))
        .collect::<Vec<_>>();
    let scope_bytes = fs::read(scope_path).map_err(|error| error.to_string())?;
    let fact_digest = if let Some(path) = program_facts_path {
        Some(digest(&fs::read(path).map_err(|error| error.to_string())?))
    } else {
        None
    };
    let mut result = json!({
        "schema":ASSESSMENT_SCHEMA,
        "assessmentId":"pending",
        "roundIndex":round_index,
        "parentAssessmentSha256":parent_assessment_sha256,
        "inputs":{
            "scopeSkillsSha256":digest(&scope_bytes),
            "programFactsSha256":fact_digest
        },
        "standard":{
            "semanticDimensions":["responsibility","boundary","relations"],
            "sourceScopeAdditionalDimensions":["behavior"],
            "maintenanceAdditionalDimensions":["operation"],
            "repositoryReadyRule":"every scope Skill is L3-maintenance-ready"
        },
        "totals":totals,
        "repositories":repositories,
        "gapCounts":gap_counts,
        "nextRoundObjectives":next_round_objectives,
        "decision":if ready {"ready"} else {"continue"},
        "skills":skill_rows,
        "automaticPromotion":false
    });
    let id = format!(
        "maintainer-skill-assessment-{}",
        &digest(&serde_json::to_vec(&result).map_err(|error| error.to_string())?)[..20]
    );
    result["assessmentId"] = Value::String(id);
    Ok(result)
}
