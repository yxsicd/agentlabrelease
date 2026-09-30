//! Local snapshot preparation for the existing revision-fenced TableGit writer.
//! This module has no network client and never promotes knowledge automatically.
use crate::{
    digest, maintainer_operation_evidence, maintainer_skill_flywheel::assess_with_receipts,
};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::Path};

const TABLES: [&str; 5] = [
    "maintainer_skills",
    "maintainer_scope_skills",
    "program_facts",
    "maintainer_skill_refresh_rounds",
    "evaluation_cases",
];

fn regular(path: &Path) -> Result<Vec<u8>, String> {
    let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    if !meta.is_file() {
        return Err("stage input must be a regular file".into());
    }
    fs::read(path).map_err(|e| e.to_string())
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
            .filter(|s| !s.is_empty())
            .ok_or("stage row id missing")?
            .to_owned();
        if result.insert(id, row).is_some() {
            return Err("stage duplicate row id".into());
        }
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
fn pretty(value: &Value) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}

#[allow(clippy::too_many_arguments)]
pub fn stage(
    base: &Path,
    candidate: &Path,
    before_path: &Path,
    after_path: &Path,
    receipt_root: &Path,
    selected: &[String],
    run_id: &str,
    allow_baseline_reassessment: bool,
    output: &Path,
) -> Result<Value, String> {
    if run_id.is_empty()
        || run_id.len() > 100
        || !run_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err("stage run id must be a safe identifier".into());
    }
    if !fs::symlink_metadata(base)
        .map_err(|e| e.to_string())?
        .is_dir()
    {
        return Err("stage base must be a real directory".into());
    }
    let before_bytes = regular(before_path)?;
    let after_bytes = regular(after_path)?;
    let before: Value = serde_json::from_slice(&before_bytes).map_err(|e| e.to_string())?;
    let after: Value = serde_json::from_slice(&after_bytes).map_err(|e| e.to_string())?;
    let result =
        maintainer_operation_evidence::compare_round(&before_bytes, &after_bytes, selected)?;
    if result["decision"] != "review-proposed-operation-knowledge" {
        return Err("no-change cannot stage an authority round".into());
    }
    let mut files = BTreeMap::new();
    for table in TABLES {
        files.insert(
            format!("{table}.jsonl"),
            regular(&base.join(format!("{table}.jsonl")))?,
        );
    }
    let scope_bytes = &files["maintainer_scope_skills.jsonl"];
    let scopes = rows(scope_bytes)?;
    let old_facts = rows(&files["program_facts.jsonl"])?;
    let candidate_bytes = regular(candidate)?;
    let new_facts = rows(&candidate_bytes)?;
    if digest(scope_bytes) != before["inputs"]["scopeSkillsSha256"].as_str().unwrap_or("")
        || digest(&files["program_facts.jsonl"])
            != before["inputs"]["programFactsSha256"]
                .as_str()
                .unwrap_or("")
        || digest(&candidate_bytes) != after["inputs"]["programFactsSha256"].as_str().unwrap_or("")
    {
        return Err("stage assessment input digest mismatch".into());
    }
    for (facts, report) in [
        (base.join("program_facts.jsonl"), &before),
        (candidate.to_path_buf(), &after),
    ] {
        let computed = assess_with_receipts(
            &base.join("maintainer_scope_skills.jsonl"),
            Some(&facts),
            report["roundIndex"]
                .as_u64()
                .ok_or("stage assessment round missing")?,
            report["parentAssessmentSha256"].as_str(),
            Some(receipt_root),
        )?;
        if &computed != report {
            return Err("stage independent reassessment differs".into());
        }
    }
    if old_facts
        .iter()
        .any(|(id, row)| new_facts.get(id) != Some(row))
    {
        return Err("operation stage changed or retired an existing fact".into());
    }
    let added = new_facts
        .iter()
        .filter(|(id, _)| !old_facts.contains_key(*id))
        .collect::<Vec<_>>();
    if added.len() != selected.len() {
        return Err("operation stage requires one new fact per selected scope".into());
    }
    let mut accepted = BTreeMap::new();
    let mut portable_receipts = Vec::new();
    for (id, fact) in added {
        let ids = fact["scopeSkillIds"]
            .as_array()
            .ok_or("stage operation binding missing")?;
        if ids.len() != 1 {
            return Err("stage operation must bind one scope".into());
        }
        let scope_id = ids[0].as_str().ok_or("stage scope id invalid")?;
        if !selected.iter().any(|s| s == scope_id)
            || accepted.insert(scope_id.to_owned(), id.clone()).is_some()
        {
            return Err("stage operation scope outside selected batch or duplicated".into());
        }
        let expected = maintainer_operation_evidence::prepare_fact(
            scopes.get(scope_id).ok_or("stage scope missing")?,
            fact["operationEvidence"].clone(),
            receipt_root,
        )?;
        if &expected != fact {
            return Err("stage fact differs from verified operation candidate".into());
        }
        let relative = fact["operationEvidence"]["path"]
            .as_str()
            .ok_or("stage receipt path missing")?;
        let bytes = regular(&receipt_root.join(relative))?;
        if fact["operationEvidence"]["sha256"].as_str() != Some(digest(&bytes).as_str()) {
            return Err("stage receipt changed during capture".into());
        }
        let path = format!("operation-evidence/{relative}");
        portable_receipts.push(json!({"factId":id,"path":path,"sha256":digest(&bytes)}));
        if let Some(existing) = files.insert(path, bytes.clone()) {
            if existing != bytes {
                return Err("stage portable receipt path collision".into());
            }
        }
    }
    let mut rounds = rows(&files["maintainer_skill_refresh_rounds.jsonl"])?;
    let previous = rounds
        .values()
        .max_by_key(|row| row["roundIndex"].as_u64().unwrap_or(0))
        .ok_or("stage parent round missing")?;
    let round_index = previous["roundIndex"]
        .as_u64()
        .ok_or("stage parent index missing")?
        .checked_add(1)
        .ok_or("stage round overflow")?;
    // Durable refresh rounds and assessment rounds are independent counters.
    let prior_path = previous["assessment"]["path"]
        .as_str()
        .ok_or("stage parent assessment missing")?;
    if !Path::new(prior_path)
        .components()
        .all(|c| matches!(c, std::path::Component::Normal(_)))
    {
        return Err("stage parent assessment path escapes base".into());
    }
    let prior_bytes = regular(&base.join(prior_path))?;
    let prior: Value = serde_json::from_slice(&prior_bytes).map_err(|e| e.to_string())?;
    if previous["assessment"]["sha256"].as_str() != Some(digest(&prior_bytes).as_str())
        || prior["roundIndex"] != before["roundIndex"]
        || prior["inputs"]["scopeSkillsSha256"] != before["inputs"]["scopeSkillsSha256"]
    {
        return Err("stage baseline does not bind latest durable assessment".into());
    }
    let baseline_reassessed = prior != before;
    if baseline_reassessed && !allow_baseline_reassessment {
        return Err(
            "stage baseline changed; explicit baseline reassessment approval required".into(),
        );
    }
    let assessment_index = after["roundIndex"]
        .as_u64()
        .ok_or("stage assessment index missing")?;
    let assessment_path = format!("assessments/round-{assessment_index}-operation-{run_id}.json");
    let mut coverage = previous["coverage"].clone();
    for (key, total) in [
        ("programBoundScopeCount", "programBoundCount"),
        ("semanticReadyScopeCount", "semanticReadyCount"),
        ("maintenanceReadyScopeCount", "maintenanceReadyCount"),
    ] {
        if coverage.get(key).is_some() {
            coverage[key] = after["totals"][total].clone();
        }
    }
    let round = json!({
        "id":format!("operation-round-{round_index}-{run_id}"), "schema":"agentlab.maintainer_operation_refresh_round.v1",
        "roundIndex":round_index, "parentRoundSha256":digest(&serde_json::to_vec(previous).map_err(|e|e.to_string())?),
        "automaticPromotion":false, "ownershipPlane":"target-operations", "decision":"continue",
        "changes":{"added":accepted.values().map(|id|format!("verified operation fact {id}")).collect::<Vec<_>>(),"updated":[],"retired":[]},
        "coverage":coverage, "focus":["consume exact-source operation receipts without changing semantic knowledge"],
        "residualGaps":after["nextRoundObjectives"],
        "tables":{"processSkillsSha256":digest(&jsonl(&rows(&files["maintainer_skills.jsonl"])?)?),
            "scopeSkillsSha256":digest(&jsonl(&scopes)?),"programFactsSha256":digest(&jsonl(&new_facts)?)},
        "assessment":{"path":assessment_path,"sha256":digest(&after_bytes)},
        "producer":{"kind":"operation-receipt-stager","runId":run_id},
        "operationRoundResultSha256":digest(&serde_json::to_vec(&result).map_err(|e|e.to_string())?)
        ,"baselineReassessment":{"performed":baseline_reassessed,"priorAssessmentSha256":digest(&prior_bytes),
            "strictBaselineSha256":digest(&before_bytes),"countsAsMaturityGain":false}
    });
    let round_id = round["id"].as_str().unwrap().to_owned();
    if rounds.insert(round_id, round).is_some() {
        return Err("stage round id conflict".into());
    }
    files.insert("program_facts.jsonl".into(), candidate_bytes);
    files.insert(
        "maintainer_skill_refresh_rounds.jsonl".into(),
        jsonl(&rounds)?,
    );
    files.insert(
        "maintainer-knowledge-cut.json".into(),
        regular(&base.join("maintainer-knowledge-cut.json"))?,
    );
    let assessments = base.join("assessments");
    if !fs::symlink_metadata(&assessments)
        .map_err(|e| e.to_string())?
        .is_dir()
    {
        return Err("stage assessments must be a real directory".into());
    }
    for entry in fs::read_dir(assessments).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        if path.extension().is_some_and(|ext| ext == "json") {
            files.insert(
                format!(
                    "assessments/{}",
                    path.file_name()
                        .unwrap()
                        .to_str()
                        .ok_or("stage non-UTF8 filename")?
                ),
                regular(&path)?,
            );
        }
    }
    if files.contains_key(&assessment_path) {
        return Err("stage assessment path already exists".into());
    }
    files.insert(assessment_path.clone(), after_bytes);
    files.insert("operation-baseline.json".into(), before_bytes);
    files.insert("operation-result.json".into(), pretty(&result)?);
    let manifest = json!({"schema":"agentlab.maintainer_skill_tablegit_stage.v1","automaticPromotion":false,
        "runId":run_id,"proposalReceiptCount":0,"acceptedFactIds":accepted.values().collect::<Vec<_>>(),
        "assessment":assessment_path,"stageKind":"verified-operation","authorityWritePerformed":false,
        "operationEvidence":{"receiptRoot":"operation-evidence","coverage":"accepted-operation-facts-only","receipts":portable_receipts},
        "tables":TABLES.iter().map(|table|{let path=format!("{table}.jsonl");((*table).to_owned(),json!({"path":path,"sha256":digest(&files[&path])}))}).collect::<BTreeMap<_,_>>()});
    files.insert("stage-manifest.json".into(), pretty(&manifest)?);
    // All semantic and receipt checks precede filesystem mutation. Refuse reuse.
    fs::create_dir(output).map_err(|e| format!("refusing stage output reuse: {e}"))?;
    let written = (|| -> Result<(), String> {
        fs::create_dir(output.join("assessments")).map_err(|e| e.to_string())?;
        for (path, bytes) in files {
            let path = output.join(path);
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            fs::write(path, bytes).map_err(|e| e.to_string())?;
        }
        Ok(())
    })();
    if written.is_err() {
        let _ = fs::remove_dir_all(output);
    }
    written?;
    Ok(manifest)
}
