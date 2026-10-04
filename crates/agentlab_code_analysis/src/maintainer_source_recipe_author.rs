//! Gap-selected verifier authorship. Model output is untrusted and never executed here.
use crate::{
    digest, maintainer_flywheel_plan as planner, maintainer_operation_exec as exec,
    maintainer_source_operation as operation,
};
use serde_json::{json, Value};
use std::{collections::BTreeSet, fs, io::Write, path::Path, process::Command};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("recipe author {key} absent"))
}
fn read(p: &Path, limit: usize) -> Result<Vec<u8>, String> {
    for ancestor in p.ancestors() {
        need(
            !fs::symlink_metadata(ancestor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "recipe author symlink",
        )?;
    }
    let m = fs::metadata(p).map_err(|e| e.to_string())?;
    need(
        m.is_file() && m.len() <= limit as u64,
        "recipe author input budget",
    )?;
    let bytes = fs::read(p).map_err(|e| e.to_string())?;
    need(bytes.len() <= limit, "recipe author growing input")?;
    Ok(bytes)
}
fn write(p: &Path, bytes: &[u8]) -> Result<(), String> {
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(p)
        .map_err(|e| e.to_string())?
        .write_all(bytes)
        .map_err(|e| e.to_string())
}
fn pretty(v: &Value) -> Result<Vec<u8>, String> {
    let mut b = serde_json::to_vec_pretty(v).map_err(|e| e.to_string())?;
    b.push(b'\n');
    Ok(b)
}
fn rows(p: &Path) -> Result<Vec<Value>, String> {
    String::from_utf8(read(p, 16 * 1024 * 1024)?)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|l| !l.is_empty())
        .map(|l| serde_json::from_str(l).map_err(|e| e.to_string()))
        .collect()
}
fn policy_gate(policy: &Value) -> Result<(), String> {
    need(
        policy["schema"] == "agentlab.source_recipe_author_policy.v1"
            && policy["automaticPromotion"] == false,
        "recipe author policy differs",
    )?;
    let program = Path::new(text(policy, "program")?);
    need(
        program.is_absolute()
            && program.canonicalize().map_err(|e| e.to_string())? == program
            && policy["programSha256"] == exec::executable_sha(program)?,
        "recipe author executable drift",
    )?;
    let deps = policy["methodDependencies"]
        .as_array()
        .filter(|a| a.len() <= 7)
        .ok_or("recipe author dependencies invalid")?;
    let mut remaining = 31 * 1024 * 1024;
    let mut seen = BTreeSet::new();
    for dep in deps {
        let p = text(dep, "path")?;
        need(
            Path::new(p).is_absolute() && seen.insert(p),
            "recipe author dependency path",
        )?;
        let bytes = read(Path::new(p), (16 * 1024 * 1024).min(remaining))?;
        remaining = remaining
            .checked_sub(bytes.len())
            .ok_or("recipe author dependency budget")?;
        need(
            dep["sha256"] == digest(&bytes),
            "recipe author dependency drift",
        )?;
    }
    Ok(())
}

pub fn prepare(
    knowledge: &Path,
    source: &Path,
    repository: &str,
    policy_bytes: &[u8],
) -> Result<Value, String> {
    need(
        policy_bytes.len() <= 64 * 1024,
        "recipe author policy budget",
    )?;
    let policy: Value = serde_json::from_slice(policy_bytes).map_err(|e| e.to_string())?;
    policy_gate(&policy)?;
    let cut_bytes = read(
        &knowledge.join("maintainer-knowledge-cut.json"),
        1024 * 1024,
    )?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    need(
        cut["schema"] == "agentlab.maintainer_knowledge_cut.v1" && cut.get("staging").is_none(),
        "recipe author requires committed cut",
    )?;
    for (key, name) in [
        ("maintainerSkills", "maintainer_skills"),
        ("maintainerScopeSkills", "maintainer_scope_skills"),
        ("programFacts", "program_facts"),
        (
            "maintainerSkillRefreshRounds",
            "maintainer_skill_refresh_rounds",
        ),
        ("evaluationCases", "evaluation_cases"),
    ] {
        let file = format!("{name}.jsonl");
        need(
            cut["tables"][key]["path"] == file
                && cut["tables"][key]["sha256"]
                    == digest(&read(&knowledge.join(file), 16 * 1024 * 1024)?),
            "recipe author table drift",
        )?;
    }
    let reference = planner::latest_assessment(knowledge)?;
    let baseline: Value = serde_json::from_slice(&read(
        Path::new(text(&reference, "assessmentPath")?),
        2 * 1024 * 1024,
    )?)
    .map_err(|e| e.to_string())?;
    let plan = planner::plan_for_capabilities(
        &knowledge.join("maintainer_scope_skills.jsonl"),
        Some(&knowledge.join("program_facts.jsonl")),
        &knowledge.join("operation-evidence"),
        baseline["roundIndex"]
            .as_u64()
            .ok_or("recipe author round")?,
        baseline["parentAssessmentSha256"].as_str(),
        &["operation-verification".into()],
        1,
        80,
        Some(repository),
        Some(&["source-only".into()]),
    )?;
    need(
        plan["assessment"] == baseline,
        "recipe author baseline differs",
    )?;
    let selected = plan["selectedScopeIds"]
        .as_array()
        .filter(|a| a.len() == 1)
        .ok_or("recipe author selected source-only gap required")?;
    let skill = rows(&knowledge.join("maintainer_scope_skills.jsonl"))?
        .into_iter()
        .find(|s| s["id"] == selected[0])
        .ok_or("recipe author selected scope absent")?;
    let source_identity = json!({"repositoryId":skill["repositoryId"],"repository":skill["repository"],"revision":skill["sourceRevision"]});
    exec::clean(source, &source_identity)?;
    let mut pathspecs = Vec::new();
    if let Some(selectors) = skill["ownershipSelectors"].as_array() {
        for selector in selectors {
            match selector["type"].as_str() {
                Some("prefix") => pathspecs.push(text(selector, "path")?.to_owned()),
                Some("files") => {
                    for path in selector["paths"]
                        .as_array()
                        .ok_or("recipe author file selectors")?
                    {
                        pathspecs.push(path.as_str().ok_or("recipe author path")?.into());
                    }
                }
                _ => return Err("recipe author ownership selectors".into()),
            }
        }
    } else {
        pathspecs.push(text(&skill, "pathBoundary")?.into());
    }
    let result = Command::new("git")
        .args(["ls-tree", "-r", "-z", "--full-tree", "HEAD", "--"])
        .args(&pathspecs)
        .current_dir(source)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .output()
        .map_err(|e| e.to_string())?;
    need(result.status.success(), "recipe author inventory failed")?;
    let facts = rows(&knowledge.join("program_facts.jsonl"))?
        .into_iter()
        .filter(|f| {
            f["repositoryId"] == skill["repositoryId"]
                && f["sourceRevision"] == skill["sourceRevision"]
                && f["scopeSkillIds"]
                    .as_array()
                    .is_some_and(|ids| ids.contains(&skill["id"]))
        })
        .collect::<Vec<_>>();
    let anchors = skill["evidence"]
        .as_array()
        .into_iter()
        .flatten()
        .chain(
            facts
                .iter()
                .flat_map(|f| f["evidence"].as_array().into_iter().flatten()),
        )
        .filter_map(|e| e["path"].as_str())
        .filter(|p| operation::owned(&skill, p))
        .collect::<BTreeSet<_>>();
    need(
        !anchors.is_empty(),
        "recipe author owned evidence anchors required",
    )?;
    let mut files = Vec::new();
    let mut remaining: usize = 128 * 1024;
    let mut text_bytes: usize = 0;
    for entry in result.stdout.split(|b| *b == 0).filter(|b| !b.is_empty()) {
        let entry = std::str::from_utf8(entry).map_err(|e| e.to_string())?;
        let (meta, path) = entry.split_once('\t').ok_or("recipe author tree entry")?;
        let parts = meta.split_whitespace().collect::<Vec<_>>();
        need(
            parts.len() == 3
                && matches!(parts[0], "100644" | "100755")
                && parts[1] == "blob"
                && operation::owned(&skill, path),
            "recipe author unsupported owned file",
        )?;
        let bytes = read(&source.join(path), 4 * 1024 * 1024)?;
        if std::str::from_utf8(&bytes).is_ok() {
            text_bytes = text_bytes
                .checked_add(bytes.len())
                .ok_or("recipe author text context size overflow")?;
        }
        let content = if anchors.contains(path) {
            remaining = remaining
                .checked_sub(bytes.len())
                .ok_or("recipe author evidence context requires decomposition")?;
            json!(std::str::from_utf8(&bytes).map_err(|e| e.to_string())?)
        } else {
            Value::Null
        };
        files.push(json!({"path":path,"gitBlobOid":parts[2],"sha256":digest(&bytes),"byteCount":bytes.len(),"content":content}));
    }
    // Small responsibilities can supply actual dependency implementations, not
    // just anchor bodies and filenames. Larger ones retain the bounded anchor
    // cut rather than silently providing a partial arbitrary dependency set.
    if text_bytes <= 128 * 1024 {
        for file in &mut files {
            if file["content"].is_null() {
                let bytes = read(&source.join(text(file, "path")?), 4 * 1024 * 1024)?;
                need(
                    file["sha256"] == digest(&bytes),
                    "recipe author context changed during preparation",
                )?;
                if let Ok(content) = std::str::from_utf8(&bytes) {
                    file["content"] = json!(content);
                }
            }
        }
    }
    need(
        files.len() <= 80 && skill["trackedFileCount"] == files.len(),
        "recipe author inventory incomplete",
    )?;
    exec::clean(source, &source_identity)?;
    let gap = plan["scopes"]
        .as_array()
        .ok_or("recipe author plan scopes")?
        .iter()
        .find(|s| s["selected"] == true)
        .ok_or("recipe author selected gap")?;
    let mut request = json!({"schema":"agentlab.source_recipe_author_request.v1","knowledgeCutSha256":digest(&cut_bytes),
        "knowledgeDirectory":knowledge.canonicalize().map_err(|e|e.to_string())?,"repositorySelector":repository,
        "authorityRevision":cut["tableGitAuthority"]["revision"],"source":source_identity,"sourceWorktree":source.canonicalize().map_err(|e|e.to_string())?,
        "scope":skill,"sourceFiles":files,"semanticFacts":facts,"policy":policy,"selectedGap":gap,
        "planSha256":digest(&pretty(&plan)?),"planSummary":plan["summary"],
        "reviewed":false,"automaticPromotion":false,"closedLoopQualified":false});
    request["sourceDependencyInventory"] = source_dependency_inventory(&request)?;
    need(
        serde_json::to_vec(&request)
            .map_err(|e| e.to_string())?
            .len()
            <= 512 * 1024,
        "recipe author request budget",
    )?;
    Ok(request)
}

/// One explicit source-grounded revision, not automatic approval or a transport retry.
pub fn revision(
    current_bytes: &[u8],
    parent_bytes: &[u8],
    proposal_bytes: &[u8],
    review_bytes: &[u8],
) -> Result<Value, String> {
    revision_with_design(
        current_bytes,
        parent_bytes,
        proposal_bytes,
        review_bytes,
        None,
    )
}

pub fn revision_with_design(
    current_bytes: &[u8],
    parent_bytes: &[u8],
    proposal_bytes: &[u8],
    review_bytes: &[u8],
    parent_design_bytes: Option<&[u8]>,
) -> Result<Value, String> {
    need(
        current_bytes.len() <= 512 * 1024
            && parent_bytes.len() <= 512 * 1024
            && proposal_bytes.len() <= 256 * 1024
            && review_bytes.len() <= 16 * 1024
            && parent_design_bytes.is_none_or(|bytes| bytes.len() <= 64 * 1024),
        "recipe revision input budget",
    )?;
    let current: Value = serde_json::from_slice(current_bytes).map_err(|e| e.to_string())?;
    let parent: Value = serde_json::from_slice(parent_bytes).map_err(|e| e.to_string())?;
    let proposal: Value = serde_json::from_slice(proposal_bytes).map_err(|e| e.to_string())?;
    let review: Value = serde_json::from_slice(review_bytes).map_err(|e| e.to_string())?;
    need(
        current["schema"] == "agentlab.source_recipe_author_request.v1"
            && parent["schema"] == current["schema"]
            && current["reviewed"] == false
            && parent["reviewed"] == false
            && current["automaticPromotion"] == false
            && parent["automaticPromotion"] == false,
        "recipe revision request identity",
    )?;
    need(
        prepare(
            Path::new(text(&current, "knowledgeDirectory")?),
            Path::new(text(&current, "sourceWorktree")?),
            text(&current, "repositorySelector")?,
            &serde_json::to_vec(&current["policy"]).map_err(|e| e.to_string())?,
        )? == current,
        "recipe revision current request no longer reproduces",
    )?;
    for key in [
        "authorityRevision",
        "knowledgeCutSha256",
        "source",
        "scope",
        "sourceFiles",
        "sourceDependencyInventory",
        "semanticFacts",
        "selectedGap",
        "planSha256",
        "planSummary",
        "repositorySelector",
    ] {
        need(
            current.get(key).is_some() && current[key] == parent[key],
            "recipe revision source/knowledge context drift",
        )?;
    }
    need(
        proposal["schema"] == "agentlab.source_recipe_author_proposal.v1"
            && proposal["scopeSkillId"] == current["scope"]["id"],
        "recipe revision parent proposal scope",
    )?;
    need(
        review.as_object().is_some_and(|o| {
            (review["schema"] == "agentlab.source_recipe_review_feedback.v1" && o.len() == 8)
                || (review["schema"] == "agentlab.source_recipe_review_feedback.v2" && o.len() == 9)
                || (review["schema"] == "agentlab.source_recipe_review_feedback.v3"
                    && o.len() == 11)
        }) && review["parentRequestSha256"] == digest(parent_bytes)
            && review["parentProposalSha256"] == digest(proposal_bytes)
            && review["reviewed"] == true
            && review["verdict"] == "revise"
            && review["automaticPromotion"] == false
            && text(&review, "reviewer")?.len() <= 128,
        "recipe revision reviewed feedback binding",
    )?;
    let findings = review["findings"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 8)
        .ok_or("recipe revision findings budget")?;
    let mut ids = BTreeSet::new();
    for finding in findings {
        need(
            finding.as_object().is_some_and(|o| o.len() == 4)
                && ids.insert(text(finding, "id")?)
                && text(finding, "id")?.len() <= 64
                && text(finding, "observed")?.len() <= 1024
                && text(finding, "requiredChange")?.len() <= 1024,
            "recipe revision finding contract",
        )?;
        let paths = finding["sourcePaths"]
            .as_array()
            .filter(|a| !a.is_empty() && a.len() <= 4)
            .ok_or("recipe revision finding source paths")?;
        need(
            paths.iter().all(|path| {
                current["sourceFiles"].as_array().is_some_and(|files| {
                    files
                        .iter()
                        .any(|f| path.is_string() && f["path"] == *path && f["content"].is_string())
                })
            }),
            "recipe revision finding requires loaded owned source",
        )?;
    }
    reviewed_checks(&proposal, &review)?;
    let mut packet = json!({"schema":"agentlab.source_recipe_revision_request.v1", "revisionIndex":1,
        "currentRequestSha256":digest(current_bytes),
        "parentRequestOriginal":std::str::from_utf8(parent_bytes).map_err(|e|e.to_string())?,
        "parentProposalOriginal":std::str::from_utf8(proposal_bytes).map_err(|e|e.to_string())?,
        "reviewOriginal":std::str::from_utf8(review_bytes).map_err(|e|e.to_string())?,
        "reviewSha256":digest(review_bytes), "reviewed":false,
        "automaticPromotion":false,"executionPerformed":false,"authorityWritePerformed":false});
    if let Some(bytes) = parent_design_bytes {
        need(
            review["schema"] == "agentlab.source_recipe_review_feedback.v3"
                && review["parentDesignSha256"] == digest(bytes),
            "recipe revision parent design review binding",
        )?;
        check_design_proposal(current_bytes, proposal_bytes, bytes)?;
        let parent_design: Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
        reviewed_scenarios(&parent_design, &review)?;
        packet["schema"] = json!("agentlab.source_recipe_revision_request.v2");
        packet["parentDesignOriginal"] =
            json!(std::str::from_utf8(bytes).map_err(|e| e.to_string())?);
        packet["parentDesignSha256"] = json!(digest(bytes));
    } else {
        need(
            review["schema"] != "agentlab.source_recipe_review_feedback.v3",
            "recipe revision v3 review requires original parent design",
        )?;
    }
    Ok(packet)
}

fn check_map(checks: &Value) -> Result<std::collections::BTreeMap<String, Value>, String> {
    let rows = checks
        .as_array()
        .filter(|a| (1..=64).contains(&a.len()))
        .ok_or("recipe revision protected checks budget")?;
    let mut map = std::collections::BTreeMap::new();
    for check in rows {
        let id = text(check, "id")?;
        need(
            check.as_object().is_some_and(|o| o.len() == 3)
                && check.get("expected").is_some()
                && text(check, "pointer")?.starts_with('/')
                && map.insert(id.to_owned(), check.clone()).is_none(),
            "recipe revision protected check shape/duplicate",
        )?;
    }
    Ok(map)
}

/// Review assertions authorize exact check edits, not their semantic truth.
fn reviewed_checks(proposal: &Value, review: &Value) -> Result<Value, String> {
    let mut checks = check_map(&proposal["contract"]["checks"])?;
    if matches!(
        review["schema"].as_str(),
        Some(
            "agentlab.source_recipe_review_feedback.v2"
                | "agentlab.source_recipe_review_feedback.v3"
                | "agentlab.source_recipe_design_review.v2"
        )
    ) {
        let changes = review["checkChanges"]
            .as_array()
            .filter(|a| {
                a.len() <= 64
                    && (review["schema"] == "agentlab.source_recipe_review_feedback.v3"
                        || review["schema"] == "agentlab.source_recipe_design_review.v2"
                        || !a.is_empty())
            })
            .ok_or("recipe revision explicit check changes budget")?;
        let mut seen = BTreeSet::new();
        for change in changes {
            let id = text(change, "id")?;
            need(
                change.as_object().is_some_and(|o| o.len() == 4)
                    && seen.insert(id)
                    && change.get("before").is_some()
                    && change.get("after").is_some()
                    && change["before"] != change["after"]
                    && review["findings"].as_array().is_some_and(|findings| {
                        findings.iter().any(|f| {
                            f["id"] == change["findingId"] && change["findingId"].is_string()
                        })
                    }),
                "recipe revision explicit check change/finding",
            )?;
            need(
                checks.get(id).cloned().unwrap_or(Value::Null) == change["before"],
                "recipe revision check change before differs from parent",
            )?;
            if change["after"].is_null() {
                checks.remove(id);
            } else {
                let replacement = check_map(&json!([change["after"]]))?;
                need(
                    replacement.contains_key(id),
                    "recipe revision check change id differs",
                )?;
                checks.insert(id.to_owned(), change["after"].clone());
            }
        }
    }
    let result = Value::Array(checks.into_values().collect());
    check_map(&result)?;
    Ok(result)
}

fn scenario_map(scenarios: &Value) -> Result<std::collections::BTreeMap<String, Value>, String> {
    let rows = scenarios
        .as_array()
        .filter(|a| (1..=8).contains(&a.len()))
        .ok_or("recipe revision protected scenarios budget")?;
    let mut map = std::collections::BTreeMap::new();
    for scenario in rows {
        let id = text(scenario, "id")?;
        need(
            scenario.as_object().is_some_and(|o| o.len() == 4)
                && id.len() <= 64
                && !id.contains(['/', '~'])
                && scenario["initialState"].is_object()
                && scenario["inputs"].is_object()
                && scenario["expectedObservations"].is_object()
                && map.insert(id.to_owned(), scenario.clone()).is_none(),
            "recipe revision protected scenario shape/duplicate",
        )?;
    }
    Ok(map)
}

fn reviewed_scenarios(parent_design: &Value, review: &Value) -> Result<Value, String> {
    let mut scenarios = scenario_map(&parent_design["scenarios"])?;
    let mut ordered = parent_design["scenarios"].as_array().unwrap().clone();
    let changes = review["scenarioChanges"]
        .as_array()
        .filter(|a| a.len() <= 8)
        .ok_or("recipe revision explicit scenario changes budget")?;
    let mut seen = BTreeSet::new();
    for change in changes {
        let id = text(change, "id")?;
        need(
            change.as_object().is_some_and(|o| o.len() == 4)
                && seen.insert(id)
                && change.get("before").is_some()
                && change.get("after").is_some()
                && change["before"] != change["after"]
                && review["findings"].as_array().is_some_and(|findings| {
                    findings
                        .iter()
                        .any(|f| f["id"] == change["findingId"] && change["findingId"].is_string())
                }),
            "recipe revision explicit scenario change/finding",
        )?;
        need(
            scenarios.get(id).cloned().unwrap_or(Value::Null) == change["before"],
            "recipe revision scenario change before differs from parent",
        )?;
        if change["after"].is_null() {
            scenarios.remove(id);
            ordered.retain(|scenario| scenario["id"] != id);
        } else {
            let replacement = scenario_map(&json!([change["after"]]))?;
            need(
                replacement.contains_key(id),
                "recipe revision scenario change id differs",
            )?;
            scenarios.insert(id.to_owned(), change["after"].clone());
            if let Some(index) = ordered.iter().position(|scenario| scenario["id"] == id) {
                ordered[index] = change["after"].clone();
            } else {
                ordered.push(change["after"].clone());
            }
        }
    }
    let result = Value::Array(ordered);
    scenario_map(&result)?;
    Ok(result)
}

pub fn check_revision_output(
    current_bytes: &[u8],
    packet_bytes: &[u8],
    output_bytes: &[u8],
    is_design: bool,
) -> Result<Value, String> {
    need(
        output_bytes.len() <= if is_design { 64 * 1024 } else { 256 * 1024 },
        "recipe revision output budget",
    )?;
    let admission = check_revision(current_bytes, packet_bytes)?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    let proposal: Value = serde_json::from_str(text(&packet, "parentProposalOriginal")?)
        .map_err(|e| e.to_string())?;
    let review: Value =
        serde_json::from_str(text(&packet, "reviewOriginal")?).map_err(|e| e.to_string())?;
    let output: Value = serde_json::from_slice(output_bytes).map_err(|e| e.to_string())?;
    let expected = check_map(&reviewed_checks(&proposal, &review)?)?;
    let actual = check_map(if is_design {
        &output["checks"]
    } else {
        &output["contract"]["checks"]
    })
    .map_err(|e| format!("recipe design checks parent-protection output: {e}"))?;
    let ids: BTreeSet<_> = expected.keys().chain(actual.keys()).collect();
    for id in ids {
        need(expected.get(id) == actual.get(id),
            &format!("recipe design checks differ from reviewed parent contract at check {id}; retain exact id/pointer/expected unless an exact v2/v3 checkChanges entry authorizes the change"))?;
    }
    let mut receipt = json!({"schema":"agentlab.source_recipe_revision_output_admission.v1",
        "revisionPacketSha256":admission["revisionPacketSha256"],"outputSha256":digest(output_bytes),
        "protectedChecksSha256":digest(&serde_json::to_vec(&expected).map_err(|e|e.to_string())?),
        "checkCount":expected.len(),"outputKind":if is_design {"design"} else {"proposal"},
        "reviewerIdentityAuthenticated":false,"semanticQualified":false,"executionPerformed":false,
        "authorityWritePerformed":false,"automaticPromotion":false});
    if packet["schema"] == "agentlab.source_recipe_revision_request.v2" {
        let parent_design: Value = serde_json::from_str(text(&packet, "parentDesignOriginal")?)
            .map_err(|e| e.to_string())?;
        let ordered_scenarios = reviewed_scenarios(&parent_design, &review)?;
        let expected_scenarios = scenario_map(&ordered_scenarios)?;
        if is_design {
            need(
                output["schema"] == parent_design["schema"],
                "recipe design schema differs from reviewed parent design",
            )?;
            let actual_scenarios = scenario_map(&output["scenarios"])
                .map_err(|e| format!("recipe design scenario parent-protection output: {e}"))?;
            let ids: BTreeSet<_> = expected_scenarios
                .keys()
                .chain(actual_scenarios.keys())
                .collect();
            for id in ids {
                need(expected_scenarios.get(id) == actual_scenarios.get(id),
                    &format!("recipe design scenario differs from reviewed parent at scenario {id}; retain exact initialState/inputs/expectedObservations unless an exact v3 scenarioChanges entry authorizes the change"))?;
            }
            need(output["scenarios"] == ordered_scenarios,
                "recipe design scenario sequence differs from reviewed parent; preserve existing scenario order, append reviewed additions and remove only reviewed scenarios")?;
        }
        receipt["parentDesignSha256"] = packet["parentDesignSha256"].clone();
        receipt["protectedScenariosSha256"] = json!(digest(
            &serde_json::to_vec(&ordered_scenarios).map_err(|e| e.to_string())?
        ));
        receipt["scenarioCount"] = json!(expected_scenarios.len());
        receipt["scenarioInputsValidated"] = json!(is_design);
    }
    Ok(receipt)
}

pub fn check_revision(current_bytes: &[u8], packet_bytes: &[u8]) -> Result<Value, String> {
    need(
        packet_bytes.len() <= 2 * 1024 * 1024,
        "recipe revision packet budget",
    )?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    need(
        revision_with_design(
            current_bytes,
            text(&packet, "parentRequestOriginal")?.as_bytes(),
            text(&packet, "parentProposalOriginal")?.as_bytes(),
            text(&packet, "reviewOriginal")?.as_bytes(),
            if packet["schema"] == "agentlab.source_recipe_revision_request.v2" {
                Some(text(&packet, "parentDesignOriginal")?.as_bytes())
            } else {
                None
            },
        )? == packet,
        "recipe revision packet differs",
    )?;
    Ok(
        json!({"schema":"agentlab.source_recipe_revision_admission.v1",
        "revisionPacketSha256":digest(packet_bytes),"currentRequestSha256":digest(current_bytes),
        "reviewSha256":packet["reviewSha256"],"revisionIndex":1,
        "automaticPromotion":false,"executionPerformed":false,"authorityWritePerformed":false}),
    )
}

/// Bind independent semantic findings to a reproducible draft before new inference.
/// A reviewed request to revise is not approval of either design or executable code.
pub fn design_review(
    request_bytes: &[u8],
    design_bytes: &[u8],
    review_bytes: &[u8],
) -> Result<Value, String> {
    need(
        request_bytes.len() <= 512 * 1024
            && design_bytes.len() <= 64 * 1024
            && review_bytes.len() <= 16 * 1024,
        "design review input budget",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    need(
        prepare(
            Path::new(text(&request, "knowledgeDirectory")?),
            Path::new(text(&request, "sourceWorktree")?),
            text(&request, "repositorySelector")?,
            &serde_json::to_vec(&request["policy"]).map_err(|e| e.to_string())?,
        )? == request,
        "design review request no longer reproduces",
    )?;
    design(request_bytes, design_bytes)?;
    design_review_contract(request_bytes, design_bytes, review_bytes)
}

// Portable byte-bound review validation: no historical runner paths are opened.
fn design_review_contract(
    request_bytes: &[u8],
    design_bytes: &[u8],
    review_bytes: &[u8],
) -> Result<Value, String> {
    need(
        request_bytes.len() <= 512 * 1024
            && design_bytes.len() <= 64 * 1024
            && review_bytes.len() <= 16 * 1024,
        "design review input budget",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let parent: Value = serde_json::from_slice(design_bytes).map_err(|e| e.to_string())?;
    let review: Value = serde_json::from_slice(review_bytes).map_err(|e| e.to_string())?;
    let exact = review["schema"] == "agentlab.source_recipe_design_review.v2";
    need(
        review
            .as_object()
            .is_some_and(|o| o.len() == if exact { 10 } else { 8 })
            && (exact || review["schema"] == "agentlab.source_recipe_design_review.v1")
            && request["schema"] == "agentlab.source_recipe_author_request.v1"
            && parent["scopeSkillId"] == request["scope"]["id"]
            && review["parentRequestSha256"] == digest(request_bytes)
            && review["parentDesignSha256"] == digest(design_bytes)
            && review["reviewed"] == true
            && review["verdict"] == "revise"
            && review["automaticPromotion"] == false
            && text(&review, "reviewer")?.len() <= 128,
        "design review feedback binding",
    )?;
    let findings = review["findings"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 8)
        .ok_or("design review findings budget")?;
    let mut ids = BTreeSet::new();
    for finding in findings {
        need(
            finding.as_object().is_some_and(|o| o.len() == 4)
                && ids.insert(text(finding, "id")?)
                && text(finding, "id")?.len() <= 64
                && text(finding, "observed")?.len() <= 1024
                && text(finding, "requiredChange")?.len() <= 1024,
            "design review finding contract",
        )?;
        let paths = finding["sourcePaths"]
            .as_array()
            .filter(|a| !a.is_empty() && a.len() <= 4)
            .ok_or("design review finding paths")?;
        need(
            paths.iter().all(|path| {
                request["sourceFiles"].as_array().is_some_and(|files| {
                    files
                        .iter()
                        .any(|f| path.is_string() && f["path"] == *path && f["content"].is_string())
                })
            }),
            "design review finding requires loaded owned source",
        )?;
    }
    if exact {
        reviewed_checks(&json!({"contract":{"checks":parent["checks"]}}), &review)?;
        reviewed_scenarios(&parent, &review)?;
    }
    Ok(
        json!({"schema":if exact {"agentlab.source_recipe_design_review_admission.v2"} else {"agentlab.source_recipe_design_review_admission.v1"},
        "authorRequestSha256":digest(request_bytes),"parentDesignSha256":digest(design_bytes),
        "reviewSha256":digest(review_bytes),"revisionRequested":true,"semanticQualified":false,
        "executionPerformed":false,"authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

/// Exact successor protection, shared by authoring, approval and portable readback.
/// It proves declared changes only, not semantic truth or actual verifier consumption.
pub fn check_design_review_output(
    request: &[u8],
    parent: &[u8],
    review: &[u8],
    successor: &[u8],
) -> Result<Value, String> {
    let admission = design_review_contract(request, parent, review)?;
    need(
        successor.len() <= 64 * 1024,
        "design review successor budget",
    )?;
    let p: Value = serde_json::from_slice(parent).map_err(|e| e.to_string())?;
    let r: Value = serde_json::from_slice(review).map_err(|e| e.to_string())?;
    let s: Value = serde_json::from_slice(successor).map_err(|e| e.to_string())?;
    let exact = r["schema"] == "agentlab.source_recipe_design_review.v2";
    if exact {
        need(
            s["schema"] == p["schema"] && s["scopeSkillId"] == p["scopeSkillId"],
            "recipe design schema/scope differs from reviewed parent",
        )?;
        let expected = check_map(&reviewed_checks(
            &json!({"contract":{"checks":p["checks"]}}),
            &r,
        )?)?;
        let actual = check_map(&s["checks"])?;
        for id in expected
            .keys()
            .chain(actual.keys())
            .collect::<BTreeSet<_>>()
        {
            need(expected.get(id) == actual.get(id), &format!("recipe design checks differ from exact design review at check {id}; require checkChanges before/after/findingId"))?;
        }
        let scenarios = reviewed_scenarios(&p, &r)?;
        let expected = scenario_map(&scenarios)?;
        let actual = scenario_map(&s["scenarios"])?;
        for id in expected
            .keys()
            .chain(actual.keys())
            .collect::<BTreeSet<_>>()
        {
            need(expected.get(id) == actual.get(id), &format!("recipe design scenario differs from exact design review at scenario {id}; require scenarioChanges before/after/findingId"))?;
        }
        need(
            s["scenarios"] == scenarios,
            "recipe design scenario sequence differs from exact design review",
        )?;
    }
    Ok(
        json!({"schema":"agentlab.source_recipe_design_review_output.v1",
        "authorRequestSha256":admission["authorRequestSha256"],
        "parentDesignSha256":admission["parentDesignSha256"],"reviewSha256":admission["reviewSha256"],
        "successorDesignSha256":digest(successor),"exactContractProtected":exact,
        "semanticQualified":false,"reviewerIdentityAuthenticated":false,
        "executionPerformed":false,"authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

/// Static source correction before code generation; this does not establish semantic truth.
fn frozen_seams(inputs: &Value, scenario_index: usize) -> Result<(), String> {
    let root = format!("/scenarios/{scenario_index}/inputs/seams");
    let seams = inputs["seams"]
        .as_object()
        .filter(|s| s.len() <= 32)
        .ok_or_else(|| format!("recipe design scenario seam inventory at {root}: required object with 0..32 entries"))?;
    for (id, seam) in seams {
        let pointer = format!("{root}/{}", id.replace('~', "~0").replace('/', "~1"));
        need(
            !id.is_empty() && id.len() <= 128,
            &format!("recipe design scenario seam id at {pointer}: required nonempty ID within 128 bytes"),
        )?;
        need(
            seam.as_object().is_some_and(|s| s.len() == 2) && seam["repeatLast"].is_boolean(),
            &format!("recipe design scenario seam fields at {pointer}: required exactly outcomes and repeatLast; repeatLast must be boolean. Seams describe controlled external dependencies, not the tested method or its expected result. If no external seams are needed, use inputs.seams={{}} instead of an empty named seam."),
        )?;
        let outcomes = seam["outcomes"]
            .as_array()
            .filter(|s| (1..=16).contains(&s.len()))
            .ok_or_else(|| format!("recipe design scenario seam outcomes at {pointer}/outcomes: required array with 1..16 entries"))?;
        for (index, outcome) in outcomes.iter().enumerate() {
            let location = format!("{pointer}/outcomes/{index}");
            let fields = outcome.as_object().ok_or_else(|| {
                format!("recipe design scenario seam outcome object at {location}: required object")
            })?;
            let kind = outcome["kind"].as_str().ok_or_else(|| {
                format!(
                    "recipe design scenario seam outcome kind at {location}/kind: required string"
                )
            })?;
            let undefined = matches!(kind, "return-undefined" | "resolve-undefined");
            need(
                matches!(
                    kind,
                    "return"
                        | "resolve"
                        | "throw"
                        | "reject"
                        | "return-undefined"
                        | "resolve-undefined"
                ) && fields.len() == if undefined { 1 } else { 2 }
                    && (undefined || fields.contains_key("value")),
                &format!("recipe design scenario seam outcome kind/value at {location}: required exactly kind and value for return/resolve/throw/reject, or only kind for return-undefined/resolve-undefined"),
            )?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod seam_feedback_tests {
    use super::*;

    #[test]
    fn empty_named_seam_retains_rejection_and_locates_repair() {
        // Structure retained from real Action 37111329948; no source-specific oracle.
        let error = frozen_seams(&json!({"seams":{"tested-method":{}}}), 3).unwrap_err();
        assert!(error.starts_with("recipe design scenario seam fields"));
        assert!(error.contains("/scenarios/3/inputs/seams/tested-method"));
        assert!(error.contains("exactly outcomes and repeatLast"));
        assert!(error.contains("inputs.seams={}"));
        assert!(frozen_seams(&json!({"seams":{}}), 3).is_ok());
    }

    #[test]
    fn dependency_sequences_keep_exact_contract() {
        for kind in ["return", "resolve", "throw", "reject"] {
            let valid = json!({"seams":{"dependency":{"repeatLast":false,"outcomes":[{"kind":kind,"value":null}]}}});
            assert!(frozen_seams(&valid, 0).is_ok());
            let mut invalid = valid.clone();
            invalid["seams"]["dependency"]["repeatLast"] = json!("false");
            assert!(frozen_seams(&invalid, 0).is_err());
            invalid = valid.clone();
            invalid["seams"]["dependency"]["outcomes"][0] = json!({"kind":kind});
            assert!(frozen_seams(&invalid, 0)
                .unwrap_err()
                .contains("/outcomes/0"));
        }
        for kind in ["return-undefined", "resolve-undefined"] {
            let mut input =
                json!({"seams":{"dependency":{"repeatLast":true,"outcomes":[{"kind":kind}]}}});
            assert!(frozen_seams(&input, 0).is_ok());
            input["seams"]["dependency"]["outcomes"][0]["value"] = Value::Null;
            assert!(frozen_seams(&input, 0).is_err());
        }
    }

    #[test]
    fn feedback_escapes_json_pointer_and_rejects_extra_fields() {
        let input = json!({"seams":{"dep/~":{"repeatLast":false,"outcomes":[],"extra":true}}});
        let error = frozen_seams(&input, 2).unwrap_err();
        assert!(error.contains("/scenarios/2/inputs/seams/dep~1~0"));
        let input = json!({"seams":{"dep":{"repeatLast":false,"outcomes":[]}}});
        assert!(frozen_seams(&input, 2).unwrap_err().contains("1..16"));
    }
}

pub fn design(request_bytes: &[u8], design_bytes: &[u8]) -> Result<Value, String> {
    need(
        request_bytes.len() <= 512 * 1024 && design_bytes.len() <= 64 * 1024,
        "recipe design input budget",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let design: Value = serde_json::from_slice(design_bytes).map_err(|e| e.to_string())?;
    need(
        request["schema"] == "agentlab.source_recipe_author_request.v1"
            && request["reviewed"] == false
            && request["automaticPromotion"] == false,
        "recipe design request identity",
    )?;
    need(
        prepare(
            Path::new(text(&request, "knowledgeDirectory")?),
            Path::new(text(&request, "sourceWorktree")?),
            text(&request, "repositorySelector")?,
            &serde_json::to_vec(&request["policy"]).map_err(|e| e.to_string())?,
        )? == request,
        "recipe design request no longer reproduces",
    )?;
    need(
        design.as_object().is_some_and(|o| o.len() == 7)
            && matches!(
                design["schema"].as_str(),
                Some("agentlab.source_recipe_design.v1" | "agentlab.source_recipe_design.v2")
            )
            && design["scopeSkillId"] == request["scope"]["id"],
        "recipe design schema/scope",
    )?;
    let invariant = design["invariant"]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or("recipe design invariant must be nonempty text")?;
    need(
        invariant.len() <= 2048,
        &format!(
            "recipe design invariant byte budget 2048; observed {}",
            invariant.len()
        ),
    )?;
    let limitations = design["limitations"]
        .as_array()
        .ok_or("recipe design limitations must be an array")?;
    need(
        (2..=8).contains(&limitations.len()),
        &format!(
            "recipe design limitations count must be 2..8; observed {}",
            limitations.len()
        ),
    )?;
    for (index, limitation) in limitations.iter().enumerate() {
        need(
            limitation
                .as_str()
                .is_some_and(|s| !s.is_empty() && s.len() <= 1024),
            &format!(
                "recipe design limitations item {index} must be nonempty text within 1024 bytes"
            ),
        )?;
    }
    let scenarios = design["scenarios"]
        .as_array()
        .filter(|a| (1..=8).contains(&a.len()))
        .ok_or("recipe design scenario budget")?;
    let mut expected = serde_json::Map::new();
    for (scenario_index, scenario) in scenarios.iter().enumerate() {
        let id = text(scenario, "id")?;
        need(
            scenario.as_object().is_some_and(|o| o.len() == 4)
                && id.len() <= 64
                && !id.contains(['/', '~'])
                && !expected.contains_key(id)
                && scenario["initialState"].is_object()
                && scenario["inputs"].is_object()
                && scenario["expectedObservations"].is_object(),
            "recipe design scenario contract",
        )?;
        if design["schema"] == "agentlab.source_recipe_design.v2" {
            frozen_seams(&scenario["inputs"], scenario_index)?;
        }
        expected.insert(id.into(), scenario["expectedObservations"].clone());
    }
    let expected = Value::Object(expected);
    let checks = design["checks"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 64)
        .ok_or("recipe design check budget")?;
    let mut check_ids = BTreeSet::new();
    let diagnostic_value = |value: &Value| {
        let rendered = value.to_string();
        if rendered.chars().count() > 256 {
            format!(
                "{}...[truncated]",
                rendered.chars().take(256).collect::<String>()
            )
        } else {
            rendered
        }
    };
    for (check_index, check) in checks.iter().enumerate() {
        need(
            check.as_object().is_some_and(|o| o.len() == 3)
                && check_ids.insert(text(check, "id")?)
                && check.get("expected").is_some(),
            &format!("recipe design check fields at /checks/{check_index}: required exactly unique id, pointer and expected"),
        )?;
        let pointer = text(check, "pointer")?;
        let actual = expected.pointer(pointer).ok_or_else(|| {
            format!("recipe design check pointer at /checks/{check_index}/pointer: check {} pointer {} does not resolve into scenario expectedObservations; available scenario IDs {}; use exact scenario IDs, not abbreviations. This is a pointer failure, not permission to change expected values.",
                diagnostic_value(&check["id"]), diagnostic_value(&check["pointer"]),
                serde_json::to_string(&expected.as_object().unwrap().keys().collect::<Vec<_>>()).unwrap())
        })?;
        need(actual == &check["expected"], &format!(
            "recipe design check expected at /checks/{check_index}/expected: check {} pointer {} has check expected {} but scenario expectedObservations declares {}; retain originals and review consistency, not semantic approval",
            diagnostic_value(&check["id"]), diagnostic_value(&check["pointer"]),
            diagnostic_value(&check["expected"]), diagnostic_value(actual)))?;
    }
    let files = request["sourceFiles"]
        .as_array()
        .ok_or("recipe design inventory")?;
    let original = files
        .iter()
        .filter_map(|f| {
            Some((
                f["path"].as_str()?.to_string(),
                f["content"].as_str()?.to_string(),
            ))
        })
        .collect::<std::collections::BTreeMap<_, _>>();
    let controls = design["controls"]
        .as_array()
        .filter(|a| (4..=8).contains(&a.len()))
        .ok_or("recipe design control budget")?;
    let original_sha = digest(&serde_json::to_vec(&original).map_err(|e| e.to_string())?);
    let mut names = BTreeSet::new();
    let mut variants = BTreeSet::new();
    let (mut baselines, mut references, mut wrongs) = (0, 0, 0);
    let mut results = Vec::new();
    for control in controls {
        let id = text(control, "id")?;
        need(
            control.as_object().is_some_and(|o| o.len() == 4)
                && operation::valid_control_id(id)
                && names.insert(id),
            "recipe design control contract",
        )?;
        let failures = control["expectedFailedCheckIds"]
            .as_array()
            .ok_or("recipe design failure array")?;
        let mut failed_ids = BTreeSet::new();
        need(
            failures.iter().all(|v| {
                v.as_str()
                    .is_some_and(|s| check_ids.contains(s) && failed_ids.insert(s))
            }),
            "recipe design unknown/duplicate failed check",
        )?;
        let edits = control["edits"]
            .as_array()
            .filter(|a| a.len() <= 4)
            .ok_or("recipe design edit budget")?;
        match control["role"].as_str() {
            Some("baseline") => {
                baselines += 1;
                need(edits.is_empty(), "recipe design baseline edits")?;
            }
            Some("reference") => {
                references += 1;
                need(
                    !edits.is_empty() && failures.is_empty(),
                    "recipe design invalid reference",
                )?;
            }
            Some("wrong") => {
                wrongs += 1;
                need(
                    !edits.is_empty() && !failures.is_empty(),
                    "recipe design vacuous wrong",
                )?;
            }
            _ => return Err("recipe design unknown role".into()),
        }
        let mut transformed = original.clone();
        let mut edit_receipts = Vec::new();
        for edit in edits {
            need(
                edit.as_object().is_some_and(|o| o.len() == 3),
                "recipe design edit fields",
            )?;
            let path = text(edit, "path")?;
            let before = text(edit, "before")?;
            let after = edit["after"].as_str().ok_or("recipe design replacement")?;
            need(
                before.len() <= 16384 && after.len() <= 16384 && before != after,
                "recipe design edit size/no-change",
            )?;
            let body = transformed
                .get_mut(path)
                .ok_or("recipe design edit requires loaded owned source")?;
            let count = body.matches(before).count();
            need(count==1,&format!("recipe design edit in control {id} at {path} must match exactly once; observed {count}"))?;
            *body = body.replacen(before, after, 1);
            edit_receipts
                .push(json!({"path":path,"matchCount":1,"resultSha256":digest(body.as_bytes())}));
        }
        let variant = digest(&serde_json::to_vec(&transformed).map_err(|e| e.to_string())?);
        need(
            control["role"] == "baseline"
                || (variant != original_sha && variants.insert(variant.clone())),
            "recipe design unchanged or duplicate variant",
        )?;
        results.push(json!({"id":id,"sourceVariantSha256":variant,"edits":edit_receipts}));
    }
    need(
        baselines == 1 && references >= 2 && wrongs >= 1,
        "recipe design control roles",
    )?;
    Ok(
        json!({"schema":"agentlab.source_recipe_design_validation.v1",
        "requestSha256":digest(request_bytes),"designSha256":digest(design_bytes),"controls":results,
        "staticSourceCorrection":true,"semanticQualified":false,"reviewed":false,
        "executionPerformed":false,"authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

/// Reuse native syntactic analysis over the exact bounded source cut.
/// Existing-file candidates do not grant imports, edits or semantic approval.
pub fn source_dependency_inventory(request: &Value) -> Result<Value, String> {
    let files = request["sourceFiles"]
        .as_array()
        .ok_or("dependency source inventory missing")?;
    let mut imports = Vec::new();
    let mut syntax_errors = Vec::new();
    for file in files {
        let path = text(file, "path")?;
        let Some(content) = file["content"].as_str() else {
            continue;
        };
        if ![".ts", ".ets", ".tsx", ".js"]
            .iter()
            .any(|extension| path.ends_with(extension))
        {
            continue;
        }
        let analysis = crate::analyze(
            path,
            content.as_bytes(),
            text(&request["source"], "revision")?,
        )?;
        if analysis.has_errors {
            syntax_errors.push(path);
        }
        for row in analysis
            .rows
            .iter()
            .filter(|row| row["kind"] == "module-reference" && row["referenceType"] == "import")
        {
            let specifier = text(row, "specifier")?;
            let mut candidates = Vec::new();
            if specifier.starts_with('.') {
                let mut parts = path.split('/').collect::<Vec<_>>();
                parts.pop();
                let mut valid = true;
                for part in specifier.split('/') {
                    match part {
                        "" | "." => {}
                        ".." => {
                            if parts.pop().is_none() {
                                valid = false;
                                break;
                            }
                        }
                        other => parts.push(other),
                    }
                }
                if valid {
                    let base = parts.join("/");
                    let possible = [
                        base.clone(),
                        format!("{base}.ts"),
                        format!("{base}.ets"),
                        format!("{base}.tsx"),
                        format!("{base}.js"),
                        format!("{base}/index.ts"),
                        format!("{base}/index.ets"),
                        format!("{base}/index.js"),
                    ];
                    for target in files
                        .iter()
                        .filter(|target| possible.iter().any(|p| target["path"] == *p))
                    {
                        candidates.push(json!({"path":target["path"],"gitBlobOid":target["gitBlobOid"],
                            "sha256":target["sha256"],"contentLoaded":target["content"].is_string()}));
                    }
                }
            }
            candidates.sort_by_key(|target| target["path"].as_str().unwrap().to_owned());
            imports.push(json!({"sourcePath":path,"sourceSha256":digest(content.as_bytes()),
                "specifier":specifier,"importedBindings":row["importedBindings"],"statement":row["statement"],
                "candidateSourceFiles":candidates,
                "resolution":if !specifier.starts_with('.') {"external-or-alias-requires-explicit-binding"}
                    else if candidates.is_empty() {"outside-loaded-scope-context-required"}
                    else if candidates.len()!=1 {"ambiguous-source-candidates"}
                    else if candidates[0]["contentLoaded"]!=true {"scoped-source-not-loaded"}
                    else {"single-loaded-source-candidate-not-runtime-resolution"}}));
        }
    }
    imports.sort_by_key(|row| {
        (
            row["sourcePath"].as_str().unwrap().to_owned(),
            row["specifier"].as_str().unwrap().to_owned(),
        )
    });
    syntax_errors.sort();
    let result = json!({"schema":"agentlab.source_dependency_inventory.v1","imports":imports,
        "syntaxErrorPaths":syntax_errors,"resolutionPolicy":"syntactic-imports-and-bounded-existing-file-candidates",
        "runtimeResolutionVerified":false,"semanticQualified":false,"executionPerformed":false,"authorityWritePerformed":false});
    need(
        serde_json::to_vec(&result)
            .map_err(|e| e.to_string())?
            .len()
            <= 128 * 1024,
        "dependency inventory budget; decompose scope",
    )?;
    Ok(result)
}

/// Bind mechanical verifier interfaces to an independently validated design.
/// This supplies no expected observations and grants no execution or approval.
pub fn verifier_interface(request_bytes: &[u8], design_bytes: &[u8]) -> Result<Value, String> {
    design(request_bytes, design_bytes)?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let plan: Value = serde_json::from_slice(design_bytes).map_err(|e| e.to_string())?;
    let loaded: BTreeSet<_> = request["sourceFiles"]
        .as_array()
        .ok_or("verifier interface source inventory")?
        .iter()
        .filter(|file| file["content"].is_string())
        .map(|file| text(file, "path").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    let dependencies = request["policy"]["methodDependencies"]
        .as_array()
        .ok_or("verifier interface method dependencies")?
        .len();
    let pointer = |key: &str| format!("/{}", key.replace('~', "~0").replace('/', "~1"));
    let scenarios: Vec<_> = plan["scenarios"].as_array().unwrap().iter().map(|scenario| {
        let mut pointers = vec![String::new()];
        pointers.extend(scenario["initialState"].as_object().unwrap().keys().map(|key| pointer(key)));
        json!({"id":scenario["id"],"initialStateTopLevelPointers":pointers,
            "inputTopLevelPointers":scenario["inputs"].as_object().unwrap().keys().map(|key|pointer(key)).collect::<Vec<_>>()})
    }).collect();
    let result = json!({
        "schema":"agentlab.source_verifier_interface.v1",
        "requestSha256":digest(request_bytes),"designSha256":digest(design_bytes),
        "runtimeSourceSha256":digest(include_bytes!("source_design_runtime.cjs")),
        "scopeSkillId":request["scope"]["id"],
        "allowedLoadedSourcePaths":loaded,
        "sourceDependencyInventory":source_dependency_inventory(&request)?,
        "sourcePathSelection":"only loaded paths actually read; import seams do not load implementation files",
        "invocation":{"sourceRootArgvIndex":2,"controlIdArgvIndex":3,
            "runtimeArgvIndex":4+dependencies,"methodDependencyArgvStart":4,
            "compilerInvocationRequired":dependencies>0},
        "runtime":{"controlTransformationOwner":"operator-frozen-runtime",
            "sourceReturns":"already transformed source; do not reapply edits",
            "loadModuleReturns":"CommonJS exports; explicitly construct exported classes",
            "initialStatePointerBase":"scenario.initialState, not scenarioInputs packet",
            "initialStateObservation":"actual source state; mismatch must stop before tested operation",
            "initialFieldsObservation":"assertInitialFields(scenarioId, actualInstance, '/fields') reads selected own data properties; never pass expected state as actual",
            "initialStateValueShape":"assertInitialState actual is the selected subtree value, not a wrapper object; setup metadata is not observed state",
            "initialStatePointerInventory":"root and top-level only; nested RFC6901 pointers remain supported"},
        "scenarios":scenarios,
        "semanticQualified":false,"executionPerformed":false,
        "automaticPromotion":false,"authorityWritePerformed":false
    });
    need(
        serde_json::to_vec(&result)
            .map_err(|e| e.to_string())?
            .len()
            <= 64 * 1024,
        "verifier interface packet budget",
    )?;
    Ok(result)
}

fn check_design_proposal(
    request_bytes: &[u8],
    proposal_bytes: &[u8],
    design_bytes: &[u8],
) -> Result<Value, String> {
    need(
        proposal_bytes.len() <= 256 * 1024,
        "recipe author proposal budget",
    )?;
    let validation = design(request_bytes, design_bytes)?;
    let d: Value = serde_json::from_slice(design_bytes).map_err(|e| e.to_string())?;
    let p: Value = serde_json::from_slice(proposal_bytes).map_err(|e| e.to_string())?;
    let controls=d["controls"].as_array().unwrap().iter().map(|c|
        json!({"id":c["id"],"role":c["role"],"expectedFailedCheckIds":c["expectedFailedCheckIds"]})).collect::<Vec<_>>();
    need(
        p["contract"]["checks"] == d["checks"] && p["contract"]["controls"] == json!(controls),
        "recipe proposal changed frozen design contract",
    )?;
    need(
        d["controls"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|c| c["edits"].as_array().unwrap())
            .all(|edit| {
                p["sourcePaths"]
                    .as_array()
                    .is_some_and(|paths| paths.contains(&edit["path"]))
            }),
        "recipe proposal omitted designed source",
    )?;
    Ok(validation)
}

pub fn stage_with_design(
    request_bytes: &[u8],
    proposal_bytes: &[u8],
    design_bytes: &[u8],
    output: &Path,
) -> Result<Value, String> {
    let validation = check_design_proposal(request_bytes, proposal_bytes, design_bytes)?;
    stage_inner(
        request_bytes,
        proposal_bytes,
        output,
        Some((design_bytes, &validation)),
        None,
        None,
        None,
        None,
    )
}

pub fn stage_with_design_review(
    request: &[u8],
    proposal: &[u8],
    design: &[u8],
    parent: &[u8],
    review: &[u8],
    intent: Option<&[u8]>,
    output: &Path,
) -> Result<Value, String> {
    design_review(request, parent, review)?;
    let validation = check_design_proposal(request, proposal, design)?;
    if let Some(intent) = intent {
        crate::maintainer_source_repair::check_loop_intent(request, intent)?;
    }
    stage_inner(
        request,
        proposal,
        output,
        Some((design, &validation)),
        None,
        None,
        intent,
        Some((parent, review)),
    )
}

/// Serialize a bounded, unreviewed proposal. No executable controls are spawned.
pub fn stage(request_bytes: &[u8], proposal_bytes: &[u8], output: &Path) -> Result<Value, String> {
    stage_inner(
        request_bytes,
        proposal_bytes,
        output,
        None,
        None,
        None,
        None,
        None,
    )
}

pub fn stage_with_revision(
    request_bytes: &[u8],
    proposal_bytes: &[u8],
    design_bytes: Option<&[u8]>,
    packet_bytes: &[u8],
    output: &Path,
) -> Result<Value, String> {
    let validation = design_bytes
        .map(|d| check_design_proposal(request_bytes, proposal_bytes, d))
        .transpose()?;
    stage_inner(
        request_bytes,
        proposal_bytes,
        output,
        design_bytes.zip(validation.as_ref()),
        Some(packet_bytes),
        None,
        None,
        None,
    )
}

/// Code-only diagnostic correction never grants independent review.
pub fn stage_with_diagnostic_repair(
    request_bytes: &[u8],
    proposal_bytes: &[u8],
    design_bytes: &[u8],
    packet_bytes: &[u8],
    output: &Path,
) -> Result<Value, String> {
    crate::maintainer_source_repair::check_output(
        request_bytes,
        packet_bytes,
        proposal_bytes,
        design_bytes,
    )?;
    let validation = check_design_proposal(request_bytes, proposal_bytes, design_bytes)?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    let loop_intent = packet["loopIntentOriginal"]
        .as_str()
        .ok_or("construction repair loop intent missing")?
        .as_bytes();
    stage_inner(
        request_bytes,
        proposal_bytes,
        output,
        Some((design_bytes, &validation)),
        None,
        Some(packet_bytes),
        Some(loop_intent),
        None,
    )
}

pub fn stage_with_loop_intent(
    request_bytes: &[u8],
    proposal_bytes: &[u8],
    design_bytes: &[u8],
    intent: &[u8],
    output: &Path,
) -> Result<Value, String> {
    crate::maintainer_source_repair::check_loop_intent(request_bytes, intent)?;
    let validation = check_design_proposal(request_bytes, proposal_bytes, design_bytes)?;
    stage_inner(
        request_bytes,
        proposal_bytes,
        output,
        Some((design_bytes, &validation)),
        None,
        None,
        Some(intent),
        None,
    )
}

/// Decode only the generated manifest header, without evaluating JavaScript.
/// Retain old literal captures as historical data; new headers preserve JSON keys.
pub(crate) fn runtime_manifest(runtime: &str) -> Result<Value, String> {
    let literal = runtime
        .lines()
        .next()
        .and_then(|s| s.strip_prefix("const manifest = "))
        .and_then(|s| s.strip_suffix(';'))
        .ok_or("runtime manifest header missing")?;
    if let Some(encoded) = literal
        .strip_prefix("JSON.parse(")
        .and_then(|s| s.strip_suffix(')'))
    {
        let json: String = serde_json::from_str(encoded).map_err(|e| e.to_string())?;
        serde_json::from_str(&json).map_err(|e| e.to_string())
    } else {
        serde_json::from_str(literal).map_err(|e| e.to_string())
    }
}

fn design_runtime(
    request: &Value,
    proposal: &Value,
    design_bytes: &[u8],
) -> Result<Vec<u8>, String> {
    let design: Value = serde_json::from_slice(design_bytes).map_err(|e| e.to_string())?;
    let files: Vec<Value> = proposal["sourcePaths"]
        .as_array()
        .ok_or("runtime source paths")?
        .iter()
        .map(|path| {
            request["sourceFiles"]
                .as_array()
                .unwrap()
                .iter()
                .find(|file| file["path"] == *path)
                .cloned()
                .ok_or("runtime unowned source".to_string())
        })
        .collect::<Result<_, _>>()?;
    let manifest = json!({"files":files,"controls":design["controls"],
        "scenarios":if design["schema"] == "agentlab.source_recipe_design.v2" { design["scenarios"].clone() } else { json!([]) }});
    // Preserve JSON keys such as __proto__; an object literal has different semantics.
    let encoded = serde_json::to_string(&manifest).map_err(|e| e.to_string())?;
    let mut bytes = format!(
        "const manifest = JSON.parse({});\n",
        serde_json::to_string(&encoded).map_err(|e| e.to_string())?
    )
    .into_bytes();
    bytes.extend_from_slice(include_bytes!("source_design_runtime.cjs"));
    Ok(bytes)
}

fn stage_inner(
    request_bytes: &[u8],
    proposal_bytes: &[u8],
    output: &Path,
    design: Option<(&[u8], &Value)>,
    revision: Option<&[u8]>,
    diagnostic_repair: Option<&[u8]>,
    loop_intent: Option<&[u8]>,
    design_review: Option<(&[u8], &[u8])>,
) -> Result<Value, String> {
    let review_validation = design_review
        .map(|(parent, review)| {
            check_design_review_output(
                request_bytes,
                parent,
                review,
                design.ok_or("design review requires successor design")?.0,
            )
        })
        .transpose()?;
    let revision_validation = revision
        .map(|packet| {
            need(
                packet.len() <= 2 * 1024 * 1024,
                "recipe revision packet budget",
            )?;
            let value: Value = serde_json::from_slice(packet).map_err(|e| e.to_string())?;
            need(
                value["schema"] != "agentlab.source_recipe_revision_request.v2" || design.is_some(),
                "recipe revision parent scenario protection requires successor design",
            )?;
            if let Some((bytes, _)) = design {
                check_revision_output(request_bytes, packet, bytes, true)?;
            }
            check_revision_output(request_bytes, packet, proposal_bytes, false)
        })
        .transpose()?;
    need(
        request_bytes.len() <= 512 * 1024 && proposal_bytes.len() <= 256 * 1024,
        "recipe author proposal budget",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let p: Value = serde_json::from_slice(proposal_bytes).map_err(|e| e.to_string())?;
    need(
        request["schema"] == "agentlab.source_recipe_author_request.v1"
            && request["reviewed"] == false
            && request["automaticPromotion"] == false,
        "recipe author request schema",
    )?;
    need(
        prepare(
            Path::new(text(&request, "knowledgeDirectory")?),
            Path::new(text(&request, "sourceWorktree")?),
            text(&request, "repositorySelector")?,
            &serde_json::to_vec(&request["policy"]).map_err(|e| e.to_string())?,
        )? == request,
        "recipe author request no longer reproduces",
    )?;
    need(
        p.as_object().is_some_and(|o| o.len() == 7)
            && p["schema"] == "agentlab.source_recipe_author_proposal.v1"
            && p["scopeSkillId"] == request["scope"]["id"],
        "recipe author proposal schema/scope",
    )?;
    let verifier = text(&p, "verifierSource")?;
    need(
        verifier.len() <= 128 * 1024,
        "recipe author verifier budget",
    )?;
    need(
        text(&p, "rationale")?.len() <= 4096
            && p["limitations"].as_array().is_some_and(|a| {
                a.len() >= 2
                    && a.len() <= 8
                    && a.iter()
                        .all(|v| v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 1024))
            }),
        "recipe author explanation budget",
    )?;
    let paths = p["sourcePaths"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 16)
        .ok_or("recipe author selected source paths")?;
    let mut seen = BTreeSet::new();
    let mut source_inputs = Vec::new();
    for (index, path) in paths.iter().enumerate() {
        let path = path.as_str().ok_or("recipe author source path")?;
        need(seen.insert(path), "recipe author duplicate source")?;
        let file = request["sourceFiles"]
            .as_array()
            .ok_or("recipe author inventory")?
            .iter()
            .find(|f| f["path"] == path)
            .ok_or_else(|| format!(
                "recipe author unowned source at sourcePaths[{index}]: {}; select only paths present in sourceFiles; an import seam does not load its implementation",
                serde_json::to_string(&path.chars().take(256).collect::<String>()).unwrap()
            ))?;
        need(
            file["content"].is_string(),
            &format!("recipe author requested source needs explicit context expansion at sourcePaths[{index}]: {}", serde_json::to_string(&path.chars().take(256).collect::<String>()).unwrap()),
        )?;
        source_inputs
            .push(json!({"path":path,"sha256":file["sha256"],"gitBlobOid":file["gitBlobOid"]}));
    }
    let spec = p["contract"]
        .as_object()
        .filter(|o| o.len() == 2)
        .ok_or("recipe author contract")?;
    let _ = spec;
    let checks = p["contract"]["checks"]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= 64)
        .ok_or("recipe author checks must be 1..64 id/pointer/expected objects")?;
    for check in checks {
        need(
            check.as_object().is_some_and(|o| o.len() == 3)
                && check.get("id").is_some_and(Value::is_string)
                && check.get("pointer").is_some_and(Value::is_string)
                && check.get("expected").is_some(),
            "recipe author check must contain exactly id, pointer and expected; check names or computed pass flags are not an oracle",
        )?;
    }
    let controls = p["contract"]["controls"]
        .as_array()
        .filter(|a| (4..=8).contains(&a.len()))
        .ok_or("recipe author controls")?;
    let mut control_ids = BTreeSet::new();
    for control in controls {
        need(
            control.as_object().is_some_and(|o| o.len() == 3)
                && control["id"].as_str().is_some_and(|id| operation::valid_control_id(id) && control_ids.insert(id))
                && matches!(control["role"].as_str(), Some("baseline" | "reference" | "wrong"))
                && control["expectedFailedCheckIds"]
                    .as_array()
                    .is_some_and(|ids| ids.iter().all(Value::is_string)),
            "recipe author control must contain exactly id, role (baseline/reference/wrong) and expectedFailedCheckIds string array",
        )?;
    }
    need(
        controls.iter().filter(|c| c["role"] == "reference").count() >= 2,
        "recipe author alternative-valid control required",
    )?;
    need(
        output.is_absolute() && !output.exists(),
        "recipe author fresh absolute output required",
    )?;
    let parent = output
        .parent()
        .ok_or("recipe author parent")?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    need(
        !parent.starts_with(Path::new(text(&request, "sourceWorktree")?)),
        "recipe author output inside source",
    )?;
    let output = parent.join(output.file_name().ok_or("recipe author output name")?);
    let policy = &request["policy"];
    policy_gate(policy)?;
    let method = output.join("controls.cjs");
    let runtime = design
        .map(|(bytes, _)| design_runtime(&request, &p, bytes))
        .transpose()?;
    need(
        runtime.is_none() || policy["methodDependencies"].as_array().unwrap().len() <= 6,
        "recipe author design runtime needs one method dependency slot",
    )?;
    let runtime_path = output.join("design-runtime.cjs");
    let mut methods = vec![json!({"path":method,"sha256":digest(verifier.as_bytes())})];
    methods.extend(
        policy["methodDependencies"]
            .as_array()
            .unwrap()
            .iter()
            .cloned(),
    );
    if let Some(bytes) = &runtime {
        methods.push(json!({"path":runtime_path,"sha256":digest(bytes)}));
    }
    let mut bound_controls = Vec::new();
    for control in controls {
        need(
            control.as_object().is_some_and(|o| o.len() == 3),
            "recipe author control fields",
        )?;
        let mut args = vec![
            json!(method),
            request["sourceWorktree"].clone(),
            control["id"].clone(),
        ];
        args.extend(
            policy["methodDependencies"]
                .as_array()
                .unwrap()
                .iter()
                .map(|d| d["path"].clone()),
        );
        if runtime.is_some() {
            args.push(json!(runtime_path));
        }
        bound_controls.push(json!({"id":control["id"],"role":control["role"],"expectedFailedCheckIds":control["expectedFailedCheckIds"],
            "command":{"program":policy["program"],"programSha256":policy["programSha256"],"args":args,"cwd":".","timeoutMs":30_000}}));
    }
    let recipe = json!({"schema":"agentlab.maintainer_source_operation_recipe.v1","reviewed":false,"automaticPromotion":false,
        "operationKind":"source-only","scopeSkillId":request["scope"]["id"],"source":request["source"],"sourceInputs":source_inputs,
        "methodInputs":methods,"checks":p["contract"]["checks"],"controls":bound_controls});
    // Validate the bound structure before creating any staging files. This private
    // reviewed flag only selects the existing static contract; it is not approval.
    let mut static_recipe = recipe.clone();
    static_recipe["reviewed"] = json!(true);
    operation::recipe_gate(&static_recipe, &request["scope"])?;
    fs::create_dir(&output).map_err(|e| e.to_string())?;
    write(&output.join("request.json"), request_bytes)?;
    write(&output.join("proposal.json"), proposal_bytes)?;
    write(&method, verifier.as_bytes())?;
    if let Some(bytes) = &runtime {
        write(&runtime_path, bytes)?;
    }
    write(&output.join("unreviewed-recipe.json"), &pretty(&recipe)?)?;
    // A private copy is marked reviewed solely for the existing static gate.
    // It is never persisted or executed; successful validation does not approve it.
    operation::preflight(
        &static_recipe,
        &request["scope"],
        Path::new(text(&request, "sourceWorktree")?),
    )?;
    let mut receipt = json!({"schema":"agentlab.source_recipe_author_stage.v1","requestSha256":digest(request_bytes),"proposalSha256":digest(proposal_bytes),
        "recipeSha256":digest(&pretty(&recipe)?),"scopeSkillId":request["scope"]["id"],"reviewed":false,"executionPerformed":false,"authorityWritePerformed":false,
        "nextAction":"independently-review-verifier-semantics-and-execution-policy","automaticPromotion":false});
    if let Some((bytes, validation)) = design {
        let validation_bytes = pretty(validation)?;
        write(&output.join("design.json"), bytes)?;
        write(&output.join("design-validation.json"), &validation_bytes)?;
        receipt["designSha256"] = json!(digest(bytes));
        receipt["designValidationSha256"] = json!(digest(&validation_bytes));
        receipt["designRuntimeSha256"] = json!(digest(runtime.as_ref().unwrap()));
    }
    if let Some(packet) = revision {
        let validation = pretty(revision_validation.as_ref().unwrap())?;
        write(&output.join("revision-request.json"), packet)?;
        write(
            &output.join("revision-contract-validation.json"),
            &validation,
        )?;
        receipt["revisionPacketSha256"] = json!(digest(packet));
        receipt["revisionContractValidationSha256"] = json!(digest(&validation));
    }
    if let Some(packet) = diagnostic_repair {
        let validation = crate::maintainer_source_repair::check_output(
            request_bytes,
            packet,
            proposal_bytes,
            design.unwrap().0,
        )?;
        let bytes = pretty(&validation)?;
        write(&output.join("diagnostic-repair.json"), packet)?;
        write(&output.join("diagnostic-repair-output.json"), &bytes)?;
        receipt["diagnosticRepairPacketSha256"] = json!(digest(packet));
        receipt["diagnosticRepairOutputSha256"] = json!(digest(&bytes));
    }
    if let Some(intent) = loop_intent {
        crate::maintainer_source_repair::check_loop_intent(request_bytes, intent)?;
        write(&output.join("diagnostic-loop-intent.json"), intent)?;
        receipt["diagnosticLoopIntentSha256"] = json!(digest(intent));
    }
    if let Some((parent, review)) = design_review {
        let validation = pretty(review_validation.as_ref().unwrap())?;
        write(&output.join("parent-design.json"), parent)?;
        write(&output.join("design-review-feedback.json"), review)?;
        write(&output.join("design-review-output.json"), &validation)?;
        receipt["reviewParentDesignSha256"] = json!(digest(parent));
        receipt["designReviewSha256"] = json!(digest(review));
        receipt["designReviewOutputSha256"] = json!(digest(&validation));
    }
    write(&output.join("stage-receipt.json"), &pretty(&receipt)?)?;
    Ok(receipt)
}

/// Explicit operator review of the exact proposal; review is not behavior qualification.
pub fn approve(
    stage: &Path,
    proposal_sha: &str,
    reviewed: bool,
    output: &Path,
) -> Result<Value, String> {
    need(reviewed, "recipe author independent review required")?;
    let request_bytes = read(&stage.join("request.json"), 512 * 1024)?;
    let proposal_bytes = read(&stage.join("proposal.json"), 256 * 1024)?;
    let receipt: Value =
        serde_json::from_slice(&read(&stage.join("stage-receipt.json"), 64 * 1024)?)
            .map_err(|e| e.to_string())?;
    let request: Value = serde_json::from_slice(&request_bytes).map_err(|e| e.to_string())?;
    let recipe_bytes = read(&stage.join("unreviewed-recipe.json"), 256 * 1024)?;
    need(
        receipt["schema"] == "agentlab.source_recipe_author_stage.v1"
            && receipt["requestSha256"] == digest(&request_bytes)
            && receipt["proposalSha256"] == digest(&proposal_bytes)
            && digest(&proposal_bytes) == proposal_sha
            && receipt["recipeSha256"] == digest(&recipe_bytes),
        "recipe author reviewed bytes differ",
    )?;
    need(
        prepare(
            Path::new(text(&request, "knowledgeDirectory")?),
            Path::new(text(&request, "sourceWorktree")?),
            text(&request, "repositorySelector")?,
            &serde_json::to_vec(&request["policy"]).map_err(|e| e.to_string())?,
        )? == request,
        "recipe author stale review request",
    )?;
    if receipt.get("revisionPacketSha256").is_some() || stage.join("revision-request.json").exists()
    {
        let packet = read(&stage.join("revision-request.json"), 2 * 1024 * 1024)?;
        let packet_value: Value = serde_json::from_slice(&packet).map_err(|e| e.to_string())?;
        need(
            packet_value["schema"] != "agentlab.source_recipe_revision_request.v2"
                || receipt.get("designSha256").is_some(),
            "recipe revision parent scenario protection requires retained successor design",
        )?;
        let validation = check_revision_output(&request_bytes, &packet, &proposal_bytes, false)?;
        let stored = read(&stage.join("revision-contract-validation.json"), 128 * 1024)?;
        need(
            receipt["revisionPacketSha256"] == digest(&packet)
                && receipt["revisionContractValidationSha256"] == digest(&stored)
                && stored == pretty(&validation)?,
            "recipe author reviewed parent contract bytes differ",
        )?;
        if receipt.get("designSha256").is_some() {
            check_revision_output(
                &request_bytes,
                &packet,
                &read(&stage.join("design.json"), 64 * 1024)?,
                true,
            )?;
        }
    }
    if receipt.get("designSha256").is_some() {
        let bytes = read(&stage.join("design.json"), 64 * 1024)?;
        let validation = check_design_proposal(&request_bytes, &proposal_bytes, &bytes)?;
        let stored = read(&stage.join("design-validation.json"), 128 * 1024)?;
        need(
            receipt["designSha256"] == digest(&bytes)
                && receipt["designValidationSha256"] == digest(&stored)
                && stored == pretty(&validation)?,
            "recipe author reviewed design bytes differ",
        )?;
        if receipt.get("designRuntimeSha256").is_some() || stage.join("design-runtime.cjs").exists()
        {
            let proposal: Value =
                serde_json::from_slice(&proposal_bytes).map_err(|e| e.to_string())?;
            let expected = design_runtime(&request, &proposal, &bytes)?;
            let actual = read(&stage.join("design-runtime.cjs"), 1024 * 1024)?;
            need(
                actual == expected && receipt["designRuntimeSha256"] == digest(&expected),
                "recipe author reviewed runtime bytes differ",
            )?;
        }
    }
    check_staged_design_review(stage, &receipt, &request_bytes, &[])?;
    if receipt.get("diagnosticRepairPacketSha256").is_some()
        || stage.join("diagnostic-repair.json").exists()
    {
        let packet = read(
            &stage.join("diagnostic-repair.json"),
            crate::maintainer_source_repair::PACKET_LIMIT,
        )?;
        let design = read(&stage.join("design.json"), 64 * 1024)?;
        let validation = crate::maintainer_source_repair::check_output(
            &request_bytes,
            &packet,
            &proposal_bytes,
            &design,
        )?;
        let stored = read(&stage.join("diagnostic-repair-output.json"), 64 * 1024)?;
        need(
            receipt["diagnosticRepairPacketSha256"] == digest(&packet)
                && receipt["diagnosticRepairOutputSha256"] == digest(&stored)
                && stored == pretty(&validation)?,
            "recipe author reviewed diagnostic repair lineage differs",
        )?;
    }
    let mut recipe: Value = serde_json::from_slice(&recipe_bytes).map_err(|e| e.to_string())?;
    need(
        recipe["reviewed"] == false,
        "recipe author input already reviewed",
    )?;
    recipe["reviewed"] = json!(true);
    operation::preflight(
        &recipe,
        &request["scope"],
        Path::new(text(&request, "sourceWorktree")?),
    )?;
    write(output, &pretty(&recipe)?)?;
    Ok(
        json!({"schema":"agentlab.source_recipe_author_review.v1","proposalSha256":proposal_sha,"recipeSha256":digest(&pretty(&recipe)?),
        "reviewed":true,"reviewerIdentityAuthenticated":false,"executionPerformed":false,"authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

/// Reconsume retained review originals without dereferencing source/knowledge paths.
pub fn check_staged_design_review(
    stage: &Path,
    receipt: &Value,
    request: &[u8],
    design: &[u8],
) -> Result<(), String> {
    let names = [
        "parent-design.json",
        "design-review-feedback.json",
        "design-review-output.json",
    ];
    if receipt.get("designReviewSha256").is_none()
        && receipt.get("reviewParentDesignSha256").is_none()
        && receipt.get("designReviewOutputSha256").is_none()
        && !names.iter().any(|name| stage.join(name).exists())
    {
        return Ok(());
    }
    let parent = read(&stage.join(names[0]), 64 * 1024)?;
    let review = read(&stage.join(names[1]), 16 * 1024)?;
    let stored = read(&stage.join(names[2]), 64 * 1024)?;
    let retained;
    let design = if design.is_empty() {
        retained = read(&stage.join("design.json"), 64 * 1024)?;
        retained.as_slice()
    } else {
        design
    };
    let validation = check_design_review_output(request, &parent, &review, design)?;
    need(
        receipt["reviewParentDesignSha256"] == digest(&parent)
            && receipt["designReviewSha256"] == digest(&review)
            && receipt["designReviewOutputSha256"] == digest(&stored)
            && stored == pretty(&validation)?,
        "recipe design review retained bytes differ",
    )
}
