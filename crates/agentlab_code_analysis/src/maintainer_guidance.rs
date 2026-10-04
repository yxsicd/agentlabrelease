//! Explicit fixed-cut guidance selection, not automatic applicability or learning.
use crate::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn read(root: &Path, name: &str) -> Result<Vec<u8>, String> {
    let path = root.join(name);
    need(
        fs::symlink_metadata(&path)
            .map_err(|e| e.to_string())?
            .is_file(),
        "guidance input must be a regular non-symlink file",
    )?;
    fs::read(path).map_err(|e| e.to_string())
}
fn rows(bytes: &[u8]) -> Result<BTreeMap<String, Value>, String> {
    let mut result = BTreeMap::new();
    for line in std::str::from_utf8(bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|s| !s.trim().is_empty())
    {
        let row: Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        let id = text(&row, "id")?.to_owned();
        need(
            result.insert(id, row).is_none(),
            "guidance duplicate table row",
        )?;
    }
    Ok(result)
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| format!("guidance {key} absent"))
}
fn hex(s: &str, n: usize) -> bool {
    s.len() == n
        && s.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

/// Bind explicitly reviewed rows to one exported cut and exact target sources.
/// This authenticates bytes, not the export's claimed remote commit or reviewer.
pub fn bind(knowledge: &Path, request_bytes: &[u8]) -> Result<Value, String> {
    bind_inner(knowledge, request_bytes, false)
}

fn bind_inner(knowledge: &Path, request_bytes: &[u8], staged: bool) -> Result<Value, String> {
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    need(
        request["schema"] == "agentlab.maintainer_guidance_selection.v1"
            && request["automaticPromotion"] == false,
        "guidance selection schema or promotion differs",
    )?;
    let cut_bytes = read(knowledge, "maintainer-knowledge-cut.json")?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    need(
        cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && request["knowledgeCutSha256"] == digest(&cut_bytes)
            && request["knowledgeRevision"] == cut["tableGitAuthority"]["revision"]
            && hex(text(&request, "knowledgeRevision")?, 40)
            && if staged {
                cut["staging"]["mode"] == "reviewed-lesson-admission"
            } else {
                cut.get("staging").is_none()
            },
        "guidance requires the selected committed knowledge cut",
    )?;
    let mut tables = BTreeMap::new();
    for (name, file) in [
        ("maintainerSkills", "maintainer_skills.jsonl"),
        ("programFacts", "program_facts.jsonl"),
        ("maintainerScopeSkills", "maintainer_scope_skills.jsonl"),
        (
            "maintainerSkillRefreshRounds",
            "maintainer_skill_refresh_rounds.jsonl",
        ),
        ("evaluationCases", "evaluation_cases.jsonl"),
    ] {
        let bytes = read(knowledge, file)?;
        need(
            cut["tables"][name]["path"] == file && cut["tables"][name]["sha256"] == digest(&bytes),
            "guidance table binding differs",
        )?;
        tables.insert(name, rows(&bytes)?);
    }
    let stage = text(&request, "stage")?;
    let sources = request["sources"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or("guidance sources absent")?;
    let mut identities = BTreeSet::new();
    for source in sources {
        let id = text(source, "repositoryId")?;
        let revision = text(source, "sourceRevision")?;
        need(
            hex(revision, 40) && identities.insert((id, revision)),
            "guidance source duplicate or invalid",
        )?;
        need(
            cut["repositories"].as_array().is_some_and(|repos| {
                repos
                    .iter()
                    .any(|r| r["id"] == id && r["revision"] == revision)
            }),
            "guidance target not present at the knowledge source cut",
        )?;
    }
    let selected = request["skills"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or("guidance explicit selection absent")?;
    let mut used = BTreeSet::new();
    let mut guidance = Vec::new();
    for choice in selected {
        let id = text(choice, "id")?;
        need(used.insert(id), "guidance selection duplicated")?;
        text(choice, "applicabilityReason")?;
        let skill = tables["maintainerSkills"]
            .get(id)
            .ok_or("guidance selected Skill absent")?;
        let row_sha = digest(&serde_json::to_vec(skill).map_err(|e| e.to_string())?);
        need(
            choice["rowSha256"] == row_sha && choice["objectId"] == skill["objectId"],
            "guidance selected row or object binding differs",
        )?;
        text(skill, "objectId")?;
        need(
            skill["stage"] == stage
                && skill["role"] == "maintenance"
                && skill["ownershipPlane"] == "target-operations"
                && skill["automaticPromotion"] == false,
            "guidance stage, role or ownership differs",
        )?;
        need(
            identities.contains(&(text(skill, "repositoryId")?, text(skill, "sourceRevision")?)),
            "guidance source revision or repository differs",
        )?;
        need(
            hex(text(skill, "methodRevision")?, 40) && hex(text(skill, "methodDigest")?, 64),
            "guidance method identity invalid",
        )?;
        text(skill, "body")?;
        let fact_ids = skill["factIds"]
            .as_array()
            .filter(|a| !a.is_empty())
            .ok_or("guidance facts absent")?;
        let mut facts = Vec::new();
        let mut fact_seen = BTreeSet::new();
        for fact_id in fact_ids {
            let fact_id = fact_id.as_str().ok_or("guidance fact id invalid")?;
            need(
                fact_seen.insert(fact_id),
                "guidance fact reference duplicated",
            )?;
            let fact = tables["programFacts"]
                .get(fact_id)
                .ok_or("guidance referenced fact absent")?;
            for key in [
                "repositoryId",
                "sourceRevision",
                "methodRevision",
                "methodDigest",
                "lessonSource",
                "sourceLessonId",
                "sourceLessonExportDigest",
            ] {
                need(
                    skill.get(key).is_some() && skill[key] == fact[key],
                    "guidance fact provenance differs",
                )?;
            }
            facts.push(json!({"id":fact_id,"rowSha256":digest(&serde_json::to_vec(fact).map_err(|e| e.to_string())?),"qualification":fact["qualification"]}));
        }
        guidance.push(json!({"skill":skill,"rowSha256":row_sha,
            "bodySha256":digest(text(skill,"body")?.as_bytes()),"facts":facts,
            "applicabilityReason":choice["applicabilityReason"]}));
    }
    Ok(json!({"schema":"agentlab.maintainer_guidance_packet.v1",
        "selectionSha256":digest(request_bytes),"knowledgeCutSha256":digest(&cut_bytes),
        "knowledgeAuthority":cut["tableGitAuthority"],"stage":stage,"sources":sources,
        "guidance":guidance,"automaticPromotion":false,"authorityWritePerformed":false,
        "remoteCommitAuthenticated":false,"reviewerAuthenticated":false,
        "agentConsumptionVerified":false,"learningBenefitVerified":false}))
}

/// Called only after original lesson reconstruction. Staged validation is a
/// pre-write applicability check; its packet must never escape as committed input.
pub(crate) fn continuation(
    knowledge: &Path,
    baseline: &Path,
    stage: &Path,
    intent_bytes: &[u8],
    staged: bool,
) -> Result<Value, String> {
    need(
        intent_bytes.len() <= 1024 * 1024,
        "guidance continuation budget",
    )?;
    let intent: Value = serde_json::from_slice(intent_bytes).map_err(|e| e.to_string())?;
    let fields = [
        "schema",
        "reviewed",
        "automaticPromotion",
        "baselineKnowledgeCutSha256",
        "baselineKnowledgeRevision",
        "stage",
        "sources",
        "skills",
        "sourceRecipeTarget",
    ];
    need(
        intent.as_object().is_some_and(|object| {
            (object.len() == 8 || object.len() == 9)
                && object.keys().all(|key| fields.contains(&key.as_str()))
                && fields[..8].iter().all(|key| object.contains_key(*key))
        }) && intent["schema"] == "agentlab.reviewed_guidance_continuation.v1"
            && intent["reviewed"] == true
            && intent["automaticPromotion"] == false,
        "guidance continuation reviewed intent differs",
    )?;
    let baseline_bytes = read(baseline, "maintainer-knowledge-cut.json")?;
    let baseline_cut: Value = serde_json::from_slice(&baseline_bytes).map_err(|e| e.to_string())?;
    let cut_bytes = read(knowledge, "maintainer-knowledge-cut.json")?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    need(
        intent["baselineKnowledgeCutSha256"] == digest(&baseline_bytes)
            && intent["baselineKnowledgeRevision"] == baseline_cut["tableGitAuthority"]["revision"]
            && cut["tableGitAuthority"]["repo"] == baseline_cut["tableGitAuthority"]["repo"],
        "guidance continuation baseline differs",
    )?;
    let plan: Value = serde_json::from_slice(&read(stage, "lesson-admission-plan.json")?)
        .map_err(|e| e.to_string())?;
    let admitted_id = text(&plan["tables"]["maintainer_skills"], "key")?;
    need(
        intent["skills"]
            .as_array()
            .is_some_and(|choices| choices.iter().any(|choice| choice["id"] == admitted_id)),
        "guidance continuation omits admitted Skill",
    )?;
    let mut selection = json!({"schema":"agentlab.maintainer_guidance_selection.v1",
        "automaticPromotion":false,"knowledgeCutSha256":digest(&cut_bytes),
        "knowledgeRevision":cut["tableGitAuthority"]["revision"],
        "stage":intent["stage"],"sources":intent["sources"],"skills":intent["skills"]});
    if let Some(target) = intent.get("sourceRecipeTarget") {
        selection["sourceRecipeTarget"] = target.clone();
    }
    let packet = bind_inner(
        knowledge,
        &serde_json::to_vec(&selection).map_err(|e| e.to_string())?,
        staged,
    )?;
    Ok(json!({"selection":selection,"packet":packet}))
}

/// Bind selected calibration knowledge to a source-recipe author's exact cut
/// and an explicit construction target. This is applicability review, not
/// semantic approval, model transmission or automatic task selection.
pub fn bind_source_recipe(
    knowledge: &Path,
    request_bytes: &[u8],
    selection_bytes: &[u8],
) -> Result<Value, String> {
    need(
        request_bytes.len() <= 512 * 1024,
        "source guidance request budget",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let selection: Value = serde_json::from_slice(selection_bytes).map_err(|e| e.to_string())?;
    let mut packet = bind(knowledge, selection_bytes)?;
    need(
        request["schema"] == "agentlab.source_recipe_author_request.v1"
            && request["reviewed"] == false
            && request["automaticPromotion"] == false
            && packet["stage"] == "calibration"
            && packet["knowledgeCutSha256"] == request["knowledgeCutSha256"]
            && packet["knowledgeAuthority"]["revision"] == request["authorityRevision"]
            && packet["sources"]
                == json!([{"repositoryId":request["source"]["repositoryId"],
                "sourceRevision":request["source"]["revision"]}])
            && request["scope"]["repositoryId"] == request["source"]["repositoryId"]
            && request["scope"]["sourceRevision"] == request["source"]["revision"],
        "source guidance author cut, stage or source differs",
    )?;
    let target = &selection["sourceRecipeTarget"];
    let scope_id = text(&request["scope"], "id")?;
    need(
        target.as_object().is_some_and(|o| o.len() == 3)
            && !scope_id.trim().is_empty()
            && text(target, "scopeSkillId")? == scope_id
            && !text(target, "demand")?.trim().is_empty()
            && text(target, "demand")?.len() <= 2048,
        "source guidance construction target differs",
    )?;
    let paths = target["sourcePaths"]
        .as_array()
        .filter(|p| !p.is_empty() && p.len() <= 16)
        .ok_or("source guidance target paths absent")?;
    let files = request["sourceFiles"]
        .as_array()
        .ok_or("source guidance files absent")?;
    let mut seen = BTreeSet::new();
    for path in paths {
        let path = path.as_str().ok_or("source guidance target path invalid")?;
        need(
            !path.is_empty()
                && !path.starts_with('/')
                && !path.contains('\\')
                && path
                    .split('/')
                    .all(|p| !p.is_empty() && p != "." && p != "..")
                && seen.insert(path),
            "source guidance target path duplicate or unsafe",
        )?;
        let matches: Vec<_> = files.iter().filter(|f| f["path"] == path).collect();
        need(
            matches.len() == 1,
            "source guidance target is not uniquely loaded",
        )?;
        let content = matches[0]["content"]
            .as_str()
            .ok_or("source guidance target not loaded")?;
        need(
            matches[0]["sha256"] == digest(content.as_bytes()),
            "source guidance target bytes differ",
        )?;
    }
    packet["sourceRecipeBinding"] = json!({"authorRequestSha256":digest(request_bytes),
        "target":target,"reviewerAuthenticated":false,"semanticQualified":false});
    Ok(packet)
}

/// A named target must survive generated-proposal staging. Path inclusion is
/// not proof of actual source execution or of a correct semantic invariant.
pub fn source_recipe_target(packet: &Value, proposal_bytes: &[u8]) -> Result<(), String> {
    let proposal: Value = serde_json::from_slice(proposal_bytes).map_err(|e| e.to_string())?;
    let target = &packet["sourceRecipeBinding"]["target"];
    need(
        text(&proposal, "scopeSkillId")? == text(target, "scopeSkillId")?,
        "source guidance proposal changed scope",
    )?;
    let paths = proposal["sourcePaths"]
        .as_array()
        .ok_or("source guidance proposal paths absent")?;
    let expected = target["sourcePaths"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or("source guidance target absent")?;
    need(
        expected.iter().all(|p| paths.contains(p)),
        "source guidance proposal omitted target source",
    )
}

/// Validate an unreviewed author's source-bound proposal without executing it.
pub fn stage_proposal(
    workspace: &Path,
    request_bytes: &[u8],
    proposal_bytes: &[u8],
) -> Result<Value, String> {
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let proposal: Value = serde_json::from_slice(proposal_bytes).map_err(|e| e.to_string())?;
    need(
        request["schema"] == "agentlab.stage_calibration_authoring_request.v1"
            && request["automaticPromotion"] == false,
        "stage proposal request differs",
    )?;
    let keys: BTreeSet<&str> = [
        "schema",
        "reviewed",
        "candidateId",
        "candidateSha256",
        "sourceRevision",
        "modulePath",
        "createMarker",
        "destroyMarker",
        "registrationMarker",
        "configurationPrefix",
        "eventName",
        "configurations",
        "variants",
    ]
    .into_iter()
    .collect();
    need(
        proposal["schema"] == "agentlab.harmony_stage_control_contract.v1"
            && proposal["reviewed"] == false,
        "stage proposal schema or review boundary differs",
    )?;
    for key in [
        "candidateId",
        "candidateSha256",
        "sourceRevision",
        "modulePath",
    ] {
        text(&proposal, key)?;
        need(
            proposal[key] == request["stageContext"][key],
            "stage proposal identity differs",
        )?;
    }
    need(
        proposal
            .as_object()
            .is_some_and(|o| o.keys().map(String::as_str).collect::<BTreeSet<_>>() == keys),
        "stage proposal fields differ",
    )?;
    need(
        hex(text(&proposal, "sourceRevision")?, 40) && hex(text(&proposal, "candidateSha256")?, 64),
        "stage proposal revision invalid",
    )?;
    for key in [
        "createMarker",
        "destroyMarker",
        "registrationMarker",
        "configurationPrefix",
        "eventName",
    ] {
        text(&proposal, key)?;
    }
    let configs = proposal["configurations"]
        .as_array()
        .filter(|a| a.len() >= 3)
        .ok_or("stage proposal configurations absent")?;
    let mut checks: BTreeSet<String> = [
        "stage-created",
        "stage-destroyed",
        "application-environment-registration",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    let mut dimensions = BTreeSet::new();
    for (i, config) in configs.iter().enumerate() {
        need(
            config.as_object().is_some_and(|o| o.len() == 3) && config["colorMode"].is_i64(),
            "stage proposal colorMode must be integer",
        )?;
        text(config, "language")?;
        need(
            checks.insert(text(config, "id")?.to_owned()),
            "stage proposal check IDs collide",
        )?;
        if i > 0 {
            let changed: Vec<_> = ["language", "colorMode"]
                .into_iter()
                .filter(|k| config[*k] != configs[i - 1][*k])
                .collect();
            need(
                changed.len() == 1,
                "stage proposal transitions must change one dimension",
            )?;
            dimensions.insert(changed[0]);
        }
    }
    need(
        dimensions.len() == 2,
        "stage proposal must vary both configuration dimensions",
    )?;
    let sources = request["sources"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or("stage proposal source inventory absent")?;
    let mut originals = BTreeMap::new();
    let safe = |s: &str| {
        !s.contains('\\')
            && !s.is_empty()
            && Path::new(s)
                .components()
                .all(|c| matches!(c, std::path::Component::Normal(_)))
            && s.split('/').all(|c| !c.is_empty() && c != "." && c != "..")
    };
    for source in sources {
        let path = text(source, "path")?;
        let file = text(source, "workspacePath")?;
        need(
            safe(path) && safe(file) && source["revision"] == proposal["sourceRevision"],
            "stage proposal source path or revision differs",
        )?;
        let mut current = workspace.to_path_buf();
        for component in Path::new(file).components() {
            current.push(component);
            need(
                !fs::symlink_metadata(&current)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink(),
                "stage proposal source symlink",
            )?;
        }
        let bytes = read(workspace, file)?;
        need(
            source["sha256"] == digest(&bytes)
                && source["bytes"].as_u64() == Some(bytes.len() as u64),
            "stage proposal source bytes changed",
        )?;
        let original = String::from_utf8(bytes).map_err(|e| e.to_string())?;
        need(
            originals.insert(path.to_owned(), original).is_none(),
            "stage proposal duplicate source path",
        )?;
    }
    need(
        originals.contains_key(text(&proposal, "modulePath")?),
        "stage proposal module not supplied",
    )?;
    let variants = proposal["variants"]
        .as_array()
        .filter(|a| a.len() >= 2)
        .ok_or("stage proposal requires two wrong variants")?;
    let mut ids = BTreeSet::from(["baseline".to_owned()]);
    let mut edits = BTreeSet::new();
    for variant in variants {
        need(
            variant.as_object().is_some_and(|o| o.len() == 5)
                && ids.insert(text(variant, "id")?.to_owned()),
            "stage proposal variant ID or shape invalid",
        )?;
        let path = text(variant, "path")?;
        let from = text(variant, "from")?;
        let to = variant["to"]
            .as_str()
            .ok_or("stage proposal replacement absent")?;
        need(
            from != to && edits.insert((path, from, to)),
            "stage proposal empty or duplicate mutation",
        )?;
        let original = originals
            .get(path)
            .ok_or("stage proposal mutation path not supplied")?;
        need(
            original.match_indices(from).count() == 1,
            "stage proposal replacement must match source exactly once",
        )?;
        let failed = variant["expectedFailedChecks"]
            .as_array()
            .filter(|a| !a.is_empty())
            .ok_or("stage proposal intended failures absent")?;
        let mut seen = BTreeSet::new();
        for check in failed {
            let id = check
                .as_str()
                .ok_or("stage proposal failure check invalid")?;
            need(
                checks.contains(id) && seen.insert(id),
                "stage proposal failure check unknown or duplicate",
            )?;
        }
    }
    Ok(
        json!({"schema":"agentlab.stage_author_proposal_validation.v1","requestSha256":digest(request_bytes),
        "proposalSha256":digest(proposal_bytes),"candidateId":proposal["candidateId"],"sourceRevision":proposal["sourceRevision"],
        "sourceFilesVerified":originals.len(),"wrongVariantsBound":variants.len(),"proposalContentValid":true,
        "reviewed":false,"semanticExecutionVerified":false,"caseQualified":false,"learningBenefitVerified":false,"automaticPromotion":false}),
    )
}

/// Independently check the complete guidance-bearing operator proxy exchange.
/// This proves recorded transmission/completion, not producer authenticity or benefit.
pub fn consumption(evidence: &Path, packet_bytes: &[u8]) -> Result<Value, String> {
    consumption_for_turn(evidence, packet_bytes, "author-calibration")
}

/// Source construction keeps its original label and capture files. Never rename
/// source evidence into the stage-author layout to obtain a passing receipt.
pub fn source_recipe_consumption(evidence: &Path, packet_bytes: &[u8]) -> Result<Value, String> {
    let receipt = source_recipe_completion(evidence, packet_bytes)?;
    need(
        receipt["agentConsumptionVerified"] == true,
        "source consumption requires guided treatment",
    )?;
    Ok(receipt)
}

/// Both treatments must complete the original source-author lifecycle and
/// transmit the same explicitly selected task. Unguided is not consumption.
pub fn source_recipe_completion(evidence: &Path, packet_bytes: &[u8]) -> Result<Value, String> {
    let revision_label = "source-recipe-author-format-revision-1";
    let revision_present = fs::read_dir(evidence)
        .map_err(|e| e.to_string())?
        .try_fold(false, |present, entry| {
            let entry = entry.map_err(|e| e.to_string())?;
            Ok::<_, String>(
                present
                    || entry
                        .file_name()
                        .to_string_lossy()
                        .starts_with(revision_label),
            )
        })?;
    // Any partial revision capture is terminal until independently completed;
    // never borrow the earlier turn's passing lifecycle after a correction.
    let label = if revision_present {
        revision_label
    } else {
        "source-recipe-author"
    };
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    let rebound = bind_source_recipe(
        &evidence.join("source-guidance-knowledge"),
        &read(evidence, "source-guidance-author-request.json")?,
        &read(evidence, "source-guidance-selection.json")?,
    )?;
    need(
        packet == rebound,
        "source consumption retained guidance binding differs",
    )?;
    let final_message: Value = serde_json::from_slice(&read(
        evidence,
        &format!("{label}-final-assistant-message.json"),
    )?)
    .map_err(|e| e.to_string())?;
    need(
        final_message["stopReason"] == "stop",
        "source construction generation did not complete normally",
    )?;
    let intent = serde_json::from_slice::<Value>(&read(
        evidence,
        &format!("{label}-guidance-consumption-intent.json"),
    )?)
    .map_err(|e| e.to_string())?;
    need(
        intent["participantBudgetSeconds"]
            .as_u64()
            .is_some_and(|n| n > 0)
            && intent["transportRetryLimit"] == 0,
        "source consumption complete budget and retry policy required",
    )?;
    need(
        packet["sourceRecipeBinding"]["authorRequestSha256"]
            .as_str()
            .is_some_and(|s| hex(s, 64)),
        "source consumption author binding absent",
    )?;
    let mut receipt = consumption_for_turn(evidence, packet_bytes, label)?;
    receipt["schema"] = json!("agentlab.source_recipe_guidance_completion.v1");
    receipt["authorCompletionVerified"] = json!(true);
    receipt["completedTurnLabel"] = json!(label);
    receipt["guidanceMode"] = intent["guidanceMode"].clone();
    receipt["authorRequestSha256"] = packet["sourceRecipeBinding"]["authorRequestSha256"].clone();
    Ok(receipt)
}

/// Independently replay a one-shot source constructor without manufacturing guidance.
/// Fresh frozen-design continuations own one isolated exchange and no format repair.
pub fn source_recipe_unguided_completion(
    evidence: &Path,
    request_bytes: &[u8],
    proposal_bytes: &[u8],
) -> Result<Value, String> {
    let label = "source-recipe-author";
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    need(
        request["schema"] == "agentlab.source_recipe_author_request.v1"
            && request["automaticPromotion"] == false
            && read(evidence, "source-completion-author-request.json")? == request_bytes,
        "source completion retained author request differs",
    )?;
    for entry in fs::read_dir(evidence).map_err(|e| e.to_string())? {
        let name = entry.map_err(|e| e.to_string())?.file_name();
        need(
            !name
                .to_string_lossy()
                .starts_with("source-recipe-author-format-revision-"),
            "one-shot source completion cannot borrow a format repair",
        )?;
    }
    let prompt = read(evidence, &format!("{label}-prompt.txt"))?;
    let original_prompt = read(evidence, &format!("{label}-completion-prompt-original.txt"))?;
    let normalized = std::str::from_utf8(&original_prompt)
        .map_err(|e| e.to_string())?
        .trim_matches([' ', '\t', '\r', '\n']);
    let intent_bytes = read(evidence, &format!("{label}-completion-intent.json"))?;
    let intent: Value = serde_json::from_slice(&intent_bytes).map_err(|e| e.to_string())?;
    need(
        intent["schema"] == "agentlab.source_recipe_completion_intent.v1"
            && intent["authorRequestSha256"] == digest(request_bytes)
            && intent["promptSha256"] == digest(&prompt)
            && intent["promptOriginalSha256"] == digest(&original_prompt)
            && normalized.as_bytes() == prompt
            && intent["participantBudgetSeconds"] == 420
            && intent["transportRetryLimit"] == 0
            && intent["guidanceProvided"] == false,
        "one-shot source completion intent or budget differs",
    )?;
    let (exchanges, lifecycle_bytes) =
        recorded_exchanges_for_turn(evidence, &prompt, &intent, label, &[])?;
    let request_count = fs::read_dir(evidence.join("gateway"))
        .map_err(|e| e.to_string())?
        .map(|entry| {
            entry.map(|entry| {
                entry
                    .file_name()
                    .to_string_lossy()
                    .ends_with(".upstream-request.json")
            })
        })
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?
        .into_iter()
        .filter(|present| *present)
        .count();
    need(
        exchanges.len() == 1 && request_count == 1,
        "source completion requires one isolated original exchange",
    )?;
    let id = exchanges[0]["exchangeId"].as_str().unwrap();
    let wire: Value = serde_json::from_slice(&read(
        evidence,
        &format!("gateway/{id}.upstream-request.json"),
    )?)
    .map_err(|e| e.to_string())?;
    let messages = wire["messages"]
        .as_array()
        .ok_or("source completion messages absent")?;
    need(
        messages
            .iter()
            .all(|m| m["role"] == "system" || m["role"] == "user")
            && messages.iter().filter(|m| m["role"] == "user").count() == 1,
        "source completion history is not a fresh isolated constructor",
    )?;
    let status: Value =
        serde_json::from_slice(&read(evidence, &format!("gateway/{id}.status.json"))?)
            .map_err(|e| e.to_string())?;
    need(
        status["upstreamDeadlineExceeded"] != true && status["clientDisconnected"] != true,
        "source completion transport deadline or disconnect",
    )?;
    let raw = read(evidence, &format!("gateway/{id}.response"))?;
    let final_bytes = read(evidence, &format!("{label}-final-assistant-message.json"))?;
    let final_message: Value = serde_json::from_slice(&final_bytes).map_err(|e| e.to_string())?;
    let text =
        crate::maintainer_source_review::recorded_completion_text(&wire, &raw, &final_message)?;
    let proposal: Value = serde_json::from_slice(proposal_bytes).map_err(|e| e.to_string())?;
    need(
        proposal.is_object()
            && serde_json::from_str::<Value>(&text).map_err(|e| e.to_string())? == proposal,
        "source completion proposal differs from original upstream text",
    )?;
    Ok(
        json!({"schema":"agentlab.source_recipe_unguided_completion.v1",
        "authorRequestSha256":digest(request_bytes),"proposalSha256":digest(proposal_bytes),
        "promptSha256":digest(&prompt),"intentSha256":digest(&intent_bytes),
        "lifecycleSha256":digest(&lifecycle_bytes),"finalAssistantMessageSha256":digest(&final_bytes),
        "completedExchanges":exchanges,"participantBudgetSeconds":420,"transportRetryLimit":0,
        "authorCompletionVerified":true,"proposalOriginalWireVerified":true,
        "guidanceProvided":false,"guidanceAbsenceVerified":false,"agentConsumptionVerified":false,
        "producerAuthenticated":false,"learningBenefitVerified":false,"caseQualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

fn consumption_for_turn(
    evidence: &Path,
    packet_bytes: &[u8],
    label: &str,
) -> Result<Value, String> {
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    need(
        packet["schema"] == "agentlab.maintainer_guidance_packet.v1"
            && packet["automaticPromotion"] == false,
        "consumption packet invalid",
    )?;
    let prefix = if label == "author-calibration" {
        "guidance"
    } else {
        label
    };
    let prompt_bytes = read(evidence, &format!("{prefix}-prompt.txt"))?;
    let intent_name = if label == "author-calibration" {
        "guidance-consumption-intent.json".to_owned()
    } else {
        format!("{label}-guidance-consumption-intent.json")
    };
    let intent_bytes = read(evidence, &intent_name)?;
    let intent: Value = serde_json::from_slice(&intent_bytes).map_err(|e| e.to_string())?;
    let unguided = label != "author-calibration" && intent["guidanceMode"] == "unguided";
    let prompt = std::str::from_utf8(&prompt_bytes).map_err(|e| e.to_string())?;
    let last = prompt
        .lines()
        .rev()
        .find(|l| !l.trim().is_empty())
        .ok_or("consumption prompt empty")?;
    let included: Value =
        serde_json::from_str(last).map_err(|_| "consumption prompt packet absent")?;
    need(
        included
            == if unguided {
                packet["sourceRecipeBinding"]["target"].clone()
            } else {
                packet.clone()
            },
        "consumption prompt omitted or changed the selected packet",
    )?;
    need(
        read(evidence, &format!("{label}-prompt.txt"))? == prompt_bytes,
        "consumption actual turn prompt differs",
    )?;
    need(
        intent["schema"] == "agentlab.maintainer_guidance_prompt_intent.v1"
            && intent["promptSha256"] == digest(&prompt_bytes)
            && intent["knowledgeAuthority"] == packet["knowledgeAuthority"]
            && (label == "author-calibration"
                || (intent["authorRequestSha256"]
                    == packet["sourceRecipeBinding"]["authorRequestSha256"]
                    && (intent["guidanceMode"] == "guided" || unguided))),
        "consumption intent binding differs",
    )?;
    let expected_skills = packet["guidance"]
        .as_array()
        .filter(|a| !a.is_empty())
        .ok_or("consumption selected guidance absent")?;
    let mut selected = Vec::new();
    for row in expected_skills {
        let skill = &row["skill"];
        need(
            row["rowSha256"] == digest(&serde_json::to_vec(skill).map_err(|e| e.to_string())?)
                && row["bodySha256"] == digest(text(skill, "body")?.as_bytes()),
            "consumption guidance bytes differ",
        )?;
        selected.push(
            json!({"id":skill["id"],"rowSha256":row["rowSha256"],"bodySha256":row["bodySha256"]}),
        );
    }
    if unguided {
        selected.clear();
    }
    need(
        intent["selectedSkills"] == json!(selected),
        "consumption selection differs",
    )?;
    let excluded_bodies = if unguided {
        expected_skills
            .iter()
            .map(|r| text(&r["skill"], "body").map(str::to_owned))
            .collect::<Result<Vec<_>, _>>()?
    } else {
        Vec::new()
    };
    let (completed, lifecycle_bytes) =
        recorded_exchanges_for_turn(evidence, &prompt_bytes, &intent, label, &excluded_bodies)?;
    Ok(
        json!({"schema":"agentlab.maintainer_guidance_consumption.v1",
        "packetSha256":digest(packet_bytes),"promptSha256":digest(&prompt_bytes),
        "intentSha256":digest(&intent_bytes),"lifecycleSha256":digest(&lifecycle_bytes),
        "knowledgeAuthority":packet["knowledgeAuthority"],"selectedSkills":selected,
        "participantBudgetSeconds":intent["participantBudgetSeconds"],
        "transportRetryLimit":intent["transportRetryLimit"],
        "implicitTransportRetryDisabledVerified":intent["transportRetryLimit"] == 0,
        "completedGuidanceExchanges":completed,"agentConsumptionVerified":!unguided,
        "producerAuthenticated":false,"learningBenefitVerified":false,"caseQualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

/// Bind recorded guidance consumption to the exact assessed attempt request.
pub fn guided_completion(evidence: &Path, request_bytes: &[u8]) -> Result<Value, String> {
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    need(
        request["guidanceMode"] == "guided",
        "guided request mode differs",
    )?;
    let packet = request
        .get("maintainerGuidance")
        .ok_or("guided request packet absent")?;
    let intent: Value =
        serde_json::from_slice(&read(evidence, "guidance-consumption-intent.json")?)
            .map_err(|e| e.to_string())?;
    need(
        intent["requestSha256"] == digest(request_bytes),
        "guided request identity differs",
    )?;
    need(
        intent["participantBudgetSeconds"]
            .as_u64()
            .is_some_and(|n| n > 0)
            && intent["transportRetryLimit"] == 0,
        "guided completion budget policy absent",
    )?;
    let mut result = consumption(
        evidence,
        &serde_json::to_vec(packet).map_err(|e| e.to_string())?,
    )?;
    result["requestSha256"] = json!(digest(request_bytes));
    Ok(result)
}

/// Completion of a recorded unguided author, not proof of guidance absence in all context.
pub fn completion(evidence: &Path, request_bytes: &[u8]) -> Result<Value, String> {
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    need(
        request["guidanceMode"] == "unguided" && request.get("maintainerGuidance").is_none(),
        "unguided author request contains guidance or differs",
    )?;
    let prompt_bytes = read(evidence, "author-calibration-prompt.txt")?;
    let intent_bytes = read(evidence, "author-completion-intent.json")?;
    let intent: Value = serde_json::from_slice(&intent_bytes).map_err(|e| e.to_string())?;
    need(
        intent["schema"] == "agentlab.author_completion_intent.v1"
            && intent["requestSha256"] == digest(request_bytes)
            && intent["promptSha256"] == digest(&prompt_bytes)
            && intent["participantBudgetSeconds"]
                .as_u64()
                .is_some_and(|n| n > 0)
            && intent["guidanceProvided"] == false,
        "author completion intent differs",
    )?;
    text(&intent["participantIdentity"], "model")?;
    text(&intent["participantIdentity"], "providerRoute")?;
    let (completed, lifecycle_bytes) = recorded_exchanges(evidence, &prompt_bytes, &intent)?;
    Ok(
        json!({"schema":"agentlab.author_completion.v1","requestSha256":digest(request_bytes),
        "promptSha256":digest(&prompt_bytes),"intentSha256":digest(&intent_bytes),
        "lifecycleSha256":digest(&lifecycle_bytes),"completedExchanges":completed,
        "participantBudgetSeconds":intent["participantBudgetSeconds"],
        "transportRetryLimit":intent["transportRetryLimit"],
        "implicitTransportRetryDisabledVerified":intent["transportRetryLimit"] == 0,
        "authorCompletionVerified":true,"guidanceProvided":false,"guidanceAbsenceVerified":false,
        "producerAuthenticated":false,"learningBenefitVerified":false,"caseQualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

fn recorded_exchanges(
    evidence: &Path,
    prompt_bytes: &[u8],
    intent: &Value,
) -> Result<(Vec<Value>, Vec<u8>), String> {
    recorded_exchanges_for_turn(evidence, prompt_bytes, intent, "author-calibration", &[])
}

pub(crate) fn recorded_exchanges_for_turn(
    evidence: &Path,
    prompt_bytes: &[u8],
    intent: &Value,
    label: &str,
    excluded_bodies: &[String],
) -> Result<(Vec<Value>, Vec<u8>), String> {
    text(&intent["participantIdentity"], "model")?;
    text(&intent["participantIdentity"], "providerRoute")?;
    let prompt = std::str::from_utf8(prompt_bytes).map_err(|e| e.to_string())?;
    need(
        !prompt.trim().is_empty()
            && read(evidence, &format!("{label}-prompt.txt"))? == prompt_bytes,
        "consumption actual turn prompt differs",
    )?;
    let lifecycle_bytes = read(evidence, &format!("{label}-lifecycle.json"))?;
    let lifecycle: Value = serde_json::from_slice(&lifecycle_bytes).map_err(|e| e.to_string())?;
    if let Some(budget) = intent.get("participantBudgetSeconds") {
        need(
            budget.as_u64().is_some_and(|n| n > 0)
                && lifecycle["participantBudgetSeconds"] == *budget
                && lifecycle["participantBudgetScope"] == "native-process-watchdog",
            "consumption participant budget differs",
        )?;
    }
    if let Some(limit) = intent.get("transportRetryLimit") {
        let retry_absent = matches!(
            fs::symlink_metadata(evidence.join(format!("{label}-transport-retry.json"))),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound
        );
        need(
            *limit == 0 && lifecycle["transportRetryLimit"] == *limit && retry_absent,
            "consumption implicit transport retry violates total author budget",
        )?;
    }
    need(
        lifecycle["label"] == label
            && lifecycle["captureAuthority"] == "operator"
            && lifecycle["exitCode"] == 0
            && lifecycle["timedOut"] == false
            && lifecycle["finalAssistantMessagePresent"] == true,
        "consumption participant did not complete",
    )?;
    let final_bytes = read(evidence, &format!("{label}-final-assistant-message.json"))?;
    let final_message: Value = serde_json::from_slice(&final_bytes).map_err(|e| e.to_string())?;
    need(
        lifecycle["finalAssistantMessageSha256"] == digest(&final_bytes)
            && final_message["role"] == "assistant"
            && final_message["stopReason"] != "error",
        "consumption final assistant observation differs",
    )?;
    let gateway = evidence.join("gateway");
    need(
        fs::symlink_metadata(&gateway)
            .map_err(|e| e.to_string())?
            .is_dir(),
        "consumption gateway directory invalid",
    )?;
    let mut completed = Vec::new();
    let mut last_exchange: Option<(u64, String)> = None;
    for entry in fs::read_dir(&gateway).map_err(|e| e.to_string())? {
        let name = entry
            .map_err(|e| e.to_string())?
            .file_name()
            .to_string_lossy()
            .into_owned();
        let Some(id) = name.strip_suffix(".upstream-request.json") else {
            continue;
        };
        need(
            !id.is_empty() && id.bytes().all(|b| b.is_ascii_digit()),
            "consumption exchange identity invalid",
        )?;
        let sequence = id
            .parse::<u64>()
            .map_err(|_| "consumption exchange sequence invalid")?;
        if last_exchange.as_ref().is_none_or(|(n, _)| sequence > *n) {
            last_exchange = Some((sequence, id.to_owned()));
        }
        let wire_bytes = read(&gateway, &name)?;
        let wire: Value = serde_json::from_slice(&wire_bytes).map_err(|e| e.to_string())?;
        if !excluded_bodies.is_empty() {
            for message in wire["messages"]
                .as_array()
                .ok_or("unguided wire messages absent")?
            {
                let mut contents = Vec::new();
                if let Some(text) = message["content"].as_str() {
                    contents.push(text);
                }
                if let Some(parts) = message["content"].as_array() {
                    contents.extend(parts.iter().filter_map(|p| p["text"].as_str()));
                }
                for body in excluded_bodies {
                    let encoded = serde_json::to_string(body).map_err(|e| e.to_string())?;
                    need(
                        !contents.iter().any(|text| {
                            text.contains(body.as_str()) || text.contains(encoded.as_str())
                        }),
                        "unguided wire carries selected guidance body",
                    )?;
                }
            }
        }
        let carries_prompt = wire["messages"].as_array().is_some_and(|messages| {
            messages.iter().any(|m| {
                m["role"] == "user"
                    && (m["content"].as_str() == Some(prompt)
                        || m["content"].as_array().is_some_and(|parts| {
                            parts.iter().any(|part| {
                                part["type"] == "text" && part["text"].as_str() == Some(prompt)
                            })
                        }))
            })
        });
        if !carries_prompt {
            continue;
        }
        need(
            wire["model"] == intent["participantIdentity"]["model"]
                && wire["providerId"] == intent["participantIdentity"]["providerRoute"]
                && wire["reasoning_effort"]
                    == intent["participantIdentity"]["providerReasoningEffort"],
            "consumption model, route or provider reasoning differs",
        )?;
        let status_bytes = read(&gateway, &format!("{id}.status.json"))?;
        let status: Value = serde_json::from_slice(&status_bytes).map_err(|e| e.to_string())?;
        let response = read(&gateway, &format!("{id}.response"))?;
        if status["exchangeId"] != id
            || status["durationMs"].as_u64().unwrap_or(0) == 0
            || status["status"] != 200
            || status["upstreamEof"] != true
            || status["semanticComplete"] != true
            || status["outcome"] != "completed"
            || !status["streamError"].is_null()
            || status["responseBytes"].as_u64() != Some(response.len() as u64)
        {
            continue;
        }
        let mut terminal = false;
        let mut error = false;
        if wire["stream"] == true {
            for line in std::str::from_utf8(&response)
                .map_err(|e| e.to_string())?
                .lines()
            {
                let Some(data) = line.strip_prefix("data:") else {
                    continue;
                };
                let data = data.trim();
                if data == "[DONE]" {
                    terminal = true;
                    continue;
                }
                let frame: Value = serde_json::from_str(data).map_err(|e| e.to_string())?;
                error |= frame.get("error").is_some_and(|e| !e.is_null());
                terminal |= frame["choices"].as_array().is_some_and(|a| {
                    a.iter()
                        .any(|c| c["finish_reason"].as_str().is_some_and(|s| !s.is_empty()))
                });
            }
        } else {
            let frame: Value = serde_json::from_slice(&response).map_err(|e| e.to_string())?;
            error = frame.get("error").is_some_and(|e| !e.is_null());
            terminal = frame["choices"].as_array().is_some_and(|a| {
                a.iter()
                    .any(|c| c["finish_reason"].as_str().is_some_and(|s| !s.is_empty()))
            });
        }
        need(
            terminal && !error,
            "consumption raw response does not establish semantic completion",
        )?;
        completed.push(json!({"exchangeId":id,"requestSha256":digest(&wire_bytes),
            "statusSha256":digest(&status_bytes),"responseSha256":digest(&response),"responseBytes":response.len(),
            "model":wire["model"],"providerRoute":wire["providerId"],"providerReasoningEffort":wire["reasoning_effort"]}));
    }
    need(
        !completed.is_empty(),
        "consumption has no completed full-prompt exchange",
    )?;
    let last_id = &last_exchange.ok_or("consumption exchanges absent")?.1;
    need(
        completed
            .iter()
            .any(|r| r["exchangeId"] == last_id.as_str()),
        "consumption final exchange incomplete or no longer bound to the full guidance prompt",
    )?;
    completed.sort_by_key(|r| r["exchangeId"].as_str().unwrap().to_owned());
    Ok((completed, lifecycle_bytes))
}
