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
            && cut.get("staging").is_none(),
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
        proposal
            .as_object()
            .is_some_and(|o| o.keys().map(String::as_str).collect::<BTreeSet<_>>() == keys)
            && proposal["schema"] == "agentlab.harmony_stage_control_contract.v1"
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
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    need(
        packet["schema"] == "agentlab.maintainer_guidance_packet.v1"
            && packet["automaticPromotion"] == false,
        "consumption packet invalid",
    )?;
    let prompt_bytes = read(evidence, "guidance-prompt.txt")?;
    let prompt = std::str::from_utf8(&prompt_bytes).map_err(|e| e.to_string())?;
    let last = prompt
        .lines()
        .rev()
        .find(|l| !l.trim().is_empty())
        .ok_or("consumption prompt empty")?;
    let included: Value =
        serde_json::from_str(last).map_err(|_| "consumption prompt packet absent")?;
    need(
        included == packet,
        "consumption prompt omitted or changed the selected packet",
    )?;
    need(
        read(evidence, "author-calibration-prompt.txt")? == prompt_bytes,
        "consumption actual turn prompt differs",
    )?;
    let intent_bytes = read(evidence, "guidance-consumption-intent.json")?;
    let intent: Value = serde_json::from_slice(&intent_bytes).map_err(|e| e.to_string())?;
    need(
        intent["schema"] == "agentlab.maintainer_guidance_prompt_intent.v1"
            && intent["promptSha256"] == digest(&prompt_bytes)
            && intent["knowledgeAuthority"] == packet["knowledgeAuthority"],
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
    need(
        intent["selectedSkills"] == json!(selected),
        "consumption selection differs",
    )?;
    let (completed, lifecycle_bytes) = recorded_exchanges(evidence, &prompt_bytes, &intent)?;
    Ok(
        json!({"schema":"agentlab.maintainer_guidance_consumption.v1",
        "packetSha256":digest(packet_bytes),"promptSha256":digest(&prompt_bytes),
        "intentSha256":digest(&intent_bytes),"lifecycleSha256":digest(&lifecycle_bytes),
        "knowledgeAuthority":packet["knowledgeAuthority"],"selectedSkills":selected,
        "completedGuidanceExchanges":completed,"agentConsumptionVerified":true,
        "producerAuthenticated":false,"learningBenefitVerified":false,"caseQualified":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    )
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
    text(&intent["participantIdentity"], "model")?;
    text(&intent["participantIdentity"], "providerRoute")?;
    let prompt = std::str::from_utf8(prompt_bytes).map_err(|e| e.to_string())?;
    need(
        !prompt.trim().is_empty()
            && read(evidence, "author-calibration-prompt.txt")? == prompt_bytes,
        "consumption actual turn prompt differs",
    )?;
    let lifecycle_bytes = read(evidence, "author-calibration-lifecycle.json")?;
    let lifecycle: Value = serde_json::from_slice(&lifecycle_bytes).map_err(|e| e.to_string())?;
    if let Some(budget) = intent.get("participantBudgetSeconds") {
        need(
            budget.as_u64().is_some_and(|n| n > 0)
                && lifecycle["participantBudgetSeconds"] == *budget
                && lifecycle["participantBudgetScope"] == "native-process-watchdog",
            "consumption participant budget differs",
        )?;
    }
    need(
        lifecycle["label"] == "author-calibration"
            && lifecycle["captureAuthority"] == "operator"
            && lifecycle["exitCode"] == 0
            && lifecycle["timedOut"] == false
            && lifecycle["finalAssistantMessagePresent"] == true,
        "consumption participant did not complete",
    )?;
    let final_bytes = read(evidence, "author-calibration-final-assistant-message.json")?;
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
