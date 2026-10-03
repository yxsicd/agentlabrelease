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
    let request = json!({"schema":"agentlab.source_recipe_author_request.v1","knowledgeCutSha256":digest(&cut_bytes),
        "knowledgeDirectory":knowledge.canonicalize().map_err(|e|e.to_string())?,"repositorySelector":repository,
        "authorityRevision":cut["tableGitAuthority"]["revision"],"source":source_identity,"sourceWorktree":source.canonicalize().map_err(|e|e.to_string())?,
        "scope":skill,"sourceFiles":files,"semanticFacts":facts,"policy":policy,"selectedGap":gap,
        "planSha256":digest(&pretty(&plan)?),"planSummary":plan["summary"],
        "reviewed":false,"automaticPromotion":false,"closedLoopQualified":false});
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
    need(
        current_bytes.len() <= 512 * 1024
            && parent_bytes.len() <= 512 * 1024
            && proposal_bytes.len() <= 256 * 1024
            && review_bytes.len() <= 16 * 1024,
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
        review.as_object().is_some_and(|o| o.len() == 8)
            && review["schema"] == "agentlab.source_recipe_review_feedback.v1"
            && review["parentRequestSha256"] == digest(parent_bytes)
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
    Ok(
        json!({"schema":"agentlab.source_recipe_revision_request.v1", "revisionIndex":1,
        "currentRequestSha256":digest(current_bytes),
        "parentRequestOriginal":std::str::from_utf8(parent_bytes).map_err(|e|e.to_string())?,
        "parentProposalOriginal":std::str::from_utf8(proposal_bytes).map_err(|e|e.to_string())?,
        "reviewOriginal":std::str::from_utf8(review_bytes).map_err(|e|e.to_string())?,
        "reviewSha256":digest(review_bytes), "reviewed":false,
        "automaticPromotion":false,"executionPerformed":false,"authorityWritePerformed":false}),
    )
}

pub fn check_revision(current_bytes: &[u8], packet_bytes: &[u8]) -> Result<Value, String> {
    need(
        packet_bytes.len() <= 2 * 1024 * 1024,
        "recipe revision packet budget",
    )?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    need(
        revision(
            current_bytes,
            text(&packet, "parentRequestOriginal")?.as_bytes(),
            text(&packet, "parentProposalOriginal")?.as_bytes(),
            text(&packet, "reviewOriginal")?.as_bytes(),
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
    let review: Value = serde_json::from_slice(review_bytes).map_err(|e| e.to_string())?;
    need(
        review.as_object().is_some_and(|o| o.len() == 8)
            && review["schema"] == "agentlab.source_recipe_design_review.v1"
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
    Ok(
        json!({"schema":"agentlab.source_recipe_design_review_admission.v1",
        "authorRequestSha256":digest(request_bytes),"parentDesignSha256":digest(design_bytes),
        "reviewSha256":digest(review_bytes),"revisionRequested":true,"semanticQualified":false,
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
    for check in checks {
        need(
            check.as_object().is_some_and(|o| o.len() == 3)
                && check_ids.insert(text(check, "id")?)
                && check.get("expected").is_some()
                && expected
                    .pointer(text(check, "pointer")?)
                    .is_some_and(|v| v == &check["expected"]),
            "recipe design checks differ from scenario observations",
        )?;
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
    )
}

/// Serialize a bounded, unreviewed proposal. No executable controls are spawned.
pub fn stage(request_bytes: &[u8], proposal_bytes: &[u8], output: &Path) -> Result<Value, String> {
    stage_inner(request_bytes, proposal_bytes, output, None)
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
    let mut bytes = format!(
        "const manifest = {};\n",
        serde_json::to_string(&manifest).map_err(|e| e.to_string())?
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
) -> Result<Value, String> {
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
    for path in paths {
        let path = path.as_str().ok_or("recipe author source path")?;
        need(seen.insert(path), "recipe author duplicate source")?;
        let file = request["sourceFiles"]
            .as_array()
            .ok_or("recipe author inventory")?
            .iter()
            .find(|f| f["path"] == path)
            .ok_or("recipe author unowned source")?;
        need(
            file["content"].is_string(),
            "recipe author requested source needs explicit context expansion",
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
