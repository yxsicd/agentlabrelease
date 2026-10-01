//! Explicit, source-bound lesson admission planning. No authority writes.
use crate::{digest, maintainer_stage_feedback};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::Path};

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
        "admission input must be a regular non-symlink file",
    )?;
    fs::read(path).map_err(|e| e.to_string())
}
fn load(root: &Path, name: &str) -> Result<Value, String> {
    serde_json::from_slice(&read(root, name)?).map_err(|e| e.to_string())
}
fn rows(bytes: &[u8]) -> Result<BTreeMap<String, Value>, String> {
    let mut result = BTreeMap::new();
    for line in std::str::from_utf8(bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|l| !l.trim().is_empty())
    {
        let row: Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        let id = row["id"]
            .as_str()
            .filter(|id| !id.trim().is_empty())
            .ok_or("admission row identity absent")?
            .to_owned();
        need(
            result.insert(id, row).is_none(),
            "admission duplicate row identity",
        )?;
    }
    Ok(result)
}
fn jsonl(rows: &BTreeMap<String, Value>) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    for row in rows.values() {
        bytes.extend(serde_json::to_vec(row).map_err(|e| e.to_string())?);
        bytes.push(b'\n');
    }
    Ok(bytes)
}
fn oid(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        s.len() == 40
            && s.bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    })
}

/// Propose exactly one Skill, one fact and one refresh row. The result is not a
/// published knowledge cut or a qualification receipt.
pub fn prepare(
    base: &Path,
    proposal: &Path,
    source: &Path,
    lesson_id: &str,
    expected_revision: &str,
) -> Result<Value, String> {
    let cut_bytes = read(base, "maintainer-knowledge-cut.json")?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    need(
        cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && oid(&json!(expected_revision))
            && cut["tableGitAuthority"]["revision"] == expected_revision,
        "admission knowledge revision fence differs",
    )?;
    need(
        cut["tableGitAuthority"]["repo"]
            .as_str()
            .is_some_and(|s| !s.trim().is_empty()),
        "admission knowledge repository absent",
    )?;
    let mut baseline = BTreeMap::new();
    let mut hashes = BTreeMap::new();
    for (key, table) in [
        ("maintainerSkills", "maintainer_skills"),
        ("programFacts", "program_facts"),
        ("maintainerScopeSkills", "maintainer_scope_skills"),
        (
            "maintainerSkillRefreshRounds",
            "maintainer_skill_refresh_rounds",
        ),
        ("evaluationCases", "evaluation_cases"),
    ] {
        let name = format!("{table}.jsonl");
        let bytes = read(base, &name)?;
        need(
            cut["tables"][key]["path"] == name && cut["tables"][key]["sha256"] == digest(&bytes),
            "admission baseline table binding differs",
        )?;
        hashes.insert(table, digest(&bytes));
        baseline.insert(table, rows(&bytes)?);
    }
    let mut history = baseline["maintainer_skill_refresh_rounds"]
        .values()
        .collect::<Vec<_>>();
    history.sort_by_key(|r| r["roundIndex"].as_u64().unwrap_or(0));
    for (i, row) in history.iter().enumerate() {
        need(
            row["roundIndex"] == (i + 1) as u64
                && row["ownershipPlane"] == "target-operations"
                && row["automaticPromotion"] == false,
            "admission refresh history invalid",
        )?;
        if i > 0 {
            need(
                row["parentRoundSha256"]
                    == digest(&serde_json::to_vec(history[i - 1]).map_err(|e| e.to_string())?),
                "admission refresh parent binding differs",
            )?;
        }
    }
    let previous = *history.last().ok_or("admission parent refresh absent")?;
    need(
        previous["coverage"]["processSkillCount"] == baseline["maintainer_skills"].len(),
        "admission parent process Skill count differs",
    )?;
    for (key, table) in [
        ("processSkillsSha256", "maintainer_skills"),
        ("programFactsSha256", "program_facts"),
        ("scopeSkillsSha256", "maintainer_scope_skills"),
    ] {
        need(
            previous["tables"][key] == hashes[table],
            "admission latest refresh table binding differs",
        )?;
    }
    // Reconstruct all analytical lesson entities from retained raw evidence,
    // rather than trusting a verified status or a rehashed proposal.
    let candidate_bytes = read(source, "candidate.json")?;
    let candidate: Value = serde_json::from_slice(&candidate_bytes).map_err(|e| e.to_string())?;
    let capture = read(source, "stage-calibration.json")?;
    let review_bytes = read(source, "lesson-review.json")?;
    let expected = maintainer_stage_feedback::lesson_assets(
        &candidate_bytes,
        &read(source, "downstream-plan.json")?,
        &read(source, "stage-contract.json")?,
        &capture,
        &digest(&capture),
        &review_bytes,
    )?;
    let export = load(source, "export.json")?;
    need(
        export["assetClass"] == "evaluation-instance"
            && oid(&export["revision"])
            && export["repository"].as_str().is_some_and(|s| !s.is_empty())
            && export["tablePrefix"].as_str().is_some(),
        "admission committed lesson source absent",
    )?;
    for (table, reconstructed) in &expected {
        let bytes = read(source, &format!("{table}.jsonl"))?;
        need(
            export["tables"][table]["sha256"] == digest(&bytes) && rows(&bytes)? == *reconstructed,
            "admission committed lesson reconstruction differs",
        )?;
    }
    let lesson = expected["experiment_lessons"]
        .get(lesson_id)
        .ok_or("admission selected lesson absent")?;
    let review: Value = serde_json::from_slice(&review_bytes).map_err(|e| e.to_string())?;
    need(
        review["id"] == lesson_id,
        "admission selected review differs",
    )?;
    need(
        baseline["maintainer_scope_skills"].values().any(|scope| {
            scope["repositoryId"] == candidate["repositoryId"]
                && scope["sourceRevision"] == candidate["sourceRevision"]
        }),
        "admission source outside baseline repositories",
    )?;
    let lesson_digest = digest(&read(source, "experiment_lessons.jsonl")?);
    let lineage = json!({"repository":export["repository"],"revision":export["revision"],"tablePrefix":export["tablePrefix"],
        "lessonId":lesson_id,"lessonFileDigest":lesson_digest});
    let mut new_tables = BTreeMap::new();
    let mut additions = BTreeMap::new();
    for (table, target) in [
        ("maintainer_skills", "skillId"),
        ("program_facts", "factId"),
        ("evaluation_cases", ""),
    ] {
        let proposed = rows(&read(proposal, &format!("{table}.jsonl"))?)?;
        need(
            baseline[table]
                .iter()
                .all(|(id, row)| proposed.get(id) == Some(row)),
            "admission changed or retired baseline knowledge",
        )?;
        let added = proposed
            .iter()
            .filter(|(id, _)| !baseline[table].contains_key(*id))
            .collect::<Vec<_>>();
        need(
            added.len() == usize::from(table != "evaluation_cases"),
            "admission unexpected knowledge delta",
        )?;
        if let Some((id, row)) = added.first() {
            need(
                row["id"] == review[target]
                    && row["assetClass"] == "reusable-knowledge"
                    && row["ownershipPlane"] == "target-operations"
                    && row["automaticPromotion"] == false
                    && row["repositoryId"] == candidate["repositoryId"]
                    && row["sourceRevision"] == candidate["sourceRevision"]
                    && row["sourceLessonId"] == lesson_id
                    && row["sourceLessonExportDigest"] == lesson_digest
                    && row["lessonSource"] == lineage
                    && row["methodSkillId"] == "agentlab-experiment-learning"
                    && oid(&row["methodRevision"])
                    && row["methodDigest"]
                        == digest(include_bytes!(
                            "../../../skills/agentlab-experiment-learning/SKILL.md"
                        )),
                "admission proposed lesson lineage differs",
            )?;
            if table == "maintainer_skills" {
                need(
                    row["body"] == review["body"]
                        && row["factIds"] == json!([review["factId"]])
                        && row["skillLayer"] == "method"
                        && row["role"] == "maintenance"
                        && row["stage"] == "calibration"
                        && row["objectId"] == lesson_id
                        && row["title"] == lesson["phenomenon"]
                        && row.as_object().map(|o| o.len()) == Some(19),
                    "admission guidance differs from reviewed lesson",
                )?;
            } else {
                need(
                    row["qualification"] == lesson["promotionContract"]["qualification"]
                        && row["validationIds"] == lesson["validationIds"]
                        && row["kind"] == "verified-lesson"
                        && ["scope", "phenomenon", "cause", "change"]
                            .iter()
                            .all(|key| row[key] == lesson[key])
                        && row.as_object().map(|o| o.len()) == Some(19),
                    "admission fact differs from verified lesson",
                )?;
            }
            additions.insert(table, json!({"key":id,"row":row}));
        }
        new_tables.insert(table, proposed);
    }
    let skills_hash = digest(&jsonl(&new_tables["maintainer_skills"])?);
    need(
        additions["maintainer_skills"]["row"]["methodRevision"]
            == additions["program_facts"]["row"]["methodRevision"],
        "admission mixed method revisions",
    )?;
    let facts_hash = digest(&jsonl(&new_tables["program_facts"])?);
    let mut coverage = previous["coverage"].clone();
    coverage["processSkillCount"] = json!(new_tables["maintainer_skills"].len());
    let identity = digest(
        &serde_json::to_vec(&json!({"cut":digest(&cut_bytes),"lessonSource":lineage,
        "skills":skills_hash,"facts":facts_hash}))
        .map_err(|e| e.to_string())?,
    );
    let round = json!({"id":format!("lesson-admission-{identity}"),"schema":"agentlab.maintainer_skill_refresh_round.v1",
        "ownershipPlane":"target-operations","automaticPromotion":false,"roundIndex":history.len()+1,
        "parentRoundSha256":digest(&serde_json::to_vec(previous).map_err(|e| e.to_string())?),
        "knowledgeChangeMode":"reviewed-lesson-admission","decision":"continue",
        "coverage":coverage,"assessment":previous["assessment"],"assessmentReused":true,
        "changes":{"added":[review["skillId"],review["factId"]],"updated":[],"retired":[]},
        "tables":{"processSkillsSha256":skills_hash,"programFactsSha256":facts_hash,"scopeSkillsSha256":hashes["maintainer_scope_skills"]},
        "lessonSource":lineage,"reviewSha256":digest(&review_bytes),
        "producer":{"kind":"reviewed-lesson-admission-planner"},"countsAsMaturityGain":false});
    additions.insert(
        "maintainer_skill_refresh_rounds",
        json!({"key":round["id"],"row":round}),
    );
    Ok(
        json!({"schema":"agentlab.maintainer_lesson_admission_plan.v1","decision":"prepared-reviewed-lesson-admission",
        "repository":cut["tableGitAuthority"]["repo"],"expectedRevision":expected_revision,
        "baselineKnowledgeCutSha256":digest(&cut_bytes),"sourceExportSha256":digest(&read(source,"export.json")?),
        "automaticPromotion":false,"authorityWritePerformed":false,"qualified":false,
        "assessmentReused":true,"sourceCommitAuthenticated":false,"tables":additions,"requiredFollowUp":["verify declared source cut through committed remote readback","validate staged full knowledge cut before authority transaction","atomic committed readback",
        "export and independently validate new knowledge cut","verify downstream guidance consumption","measure next-round benefit"]}),
    )
}
