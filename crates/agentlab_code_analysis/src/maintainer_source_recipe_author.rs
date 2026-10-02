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

/// Serialize a bounded, unreviewed proposal. No executable controls are spawned.
pub fn stage(request_bytes: &[u8], proposal_bytes: &[u8], output: &Path) -> Result<Value, String> {
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
    for control in controls {
        need(
            control.as_object().is_some_and(|o| o.len() == 3)
                && control.get("id").is_some_and(Value::is_string)
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
    let mut methods = vec![json!({"path":method,"sha256":digest(verifier.as_bytes())})];
    methods.extend(
        policy["methodDependencies"]
            .as_array()
            .unwrap()
            .iter()
            .cloned(),
    );
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
        bound_controls.push(json!({"id":control["id"],"role":control["role"],"expectedFailedCheckIds":control["expectedFailedCheckIds"],
            "command":{"program":policy["program"],"programSha256":policy["programSha256"],"args":args,"cwd":".","timeoutMs":30_000}}));
    }
    let recipe = json!({"schema":"agentlab.maintainer_source_operation_recipe.v1","reviewed":false,"automaticPromotion":false,
        "operationKind":"source-only","scopeSkillId":request["scope"]["id"],"source":request["source"],"sourceInputs":source_inputs,
        "methodInputs":methods,"checks":p["contract"]["checks"],"controls":bound_controls});
    fs::create_dir(&output).map_err(|e| e.to_string())?;
    write(&output.join("request.json"), request_bytes)?;
    write(&output.join("proposal.json"), proposal_bytes)?;
    write(&method, verifier.as_bytes())?;
    write(&output.join("unreviewed-recipe.json"), &pretty(&recipe)?)?;
    // A private copy is marked reviewed solely for the existing static gate.
    // It is never persisted or executed; successful validation does not approve it.
    let mut static_recipe = recipe.clone();
    static_recipe["reviewed"] = json!(true);
    operation::preflight(
        &static_recipe,
        &request["scope"],
        Path::new(text(&request, "sourceWorktree")?),
    )?;
    let receipt = json!({"schema":"agentlab.source_recipe_author_stage.v1","requestSha256":digest(request_bytes),"proposalSha256":digest(proposal_bytes),
        "recipeSha256":digest(&pretty(&recipe)?),"scopeSkillId":request["scope"]["id"],"reviewed":false,"executionPerformed":false,"authorityWritePerformed":false,
        "nextAction":"independently-review-verifier-semantics-and-execution-policy","automaticPromotion":false});
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
