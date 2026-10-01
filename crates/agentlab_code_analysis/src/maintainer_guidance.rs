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
