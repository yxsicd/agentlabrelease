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
    let lifecycle_bytes = read(evidence, "author-calibration-lifecycle.json")?;
    let lifecycle: Value = serde_json::from_slice(&lifecycle_bytes).map_err(|e| e.to_string())?;
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
                && wire["providerId"] == intent["participantIdentity"]["providerRoute"],
            "consumption model or route differs",
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
            "model":wire["model"],"providerRoute":wire["providerId"]}));
    }
    need(
        !completed.is_empty(),
        "consumption has no completed full-prompt exchange",
    )?;
    completed.sort_by_key(|r| r["exchangeId"].as_str().unwrap().to_owned());
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
