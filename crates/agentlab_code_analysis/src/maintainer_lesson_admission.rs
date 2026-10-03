//! Explicit, source-bound lesson admission planning. No authority writes.
use crate::{digest, maintainer_skill_flywheel::assess_with_receipts, maintainer_stage_feedback};
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

/// Assemble an independently reassessed snapshot for the existing writer.
/// Declared source commits still require separate remote readback verification.
pub fn stage(
    base: &Path,
    proposal: &Path,
    source: &Path,
    lesson_id: &str,
    expected_revision: &str,
    output: &Path,
) -> Result<Value, String> {
    stage_with_method(
        base,
        proposal,
        source,
        lesson_id,
        expected_revision,
        output,
        None,
    )
}

/// A historical method body remains an explicit frozen input. Its bytes bind
/// the proposed methodDigest; its declared Git revision is not authenticated.
pub(crate) fn stage_with_method(
    base: &Path,
    proposal: &Path,
    source: &Path,
    lesson_id: &str,
    expected_revision: &str,
    output: &Path,
    method_source: Option<&[u8]>,
) -> Result<Value, String> {
    let plan = prepare_with_method(
        base,
        proposal,
        source,
        lesson_id,
        expected_revision,
        method_source,
    )?;
    let durable = crate::maintainer_flywheel_plan::latest_assessment(base)?;
    let prior_bytes = read(
        base,
        durable["assessmentRelativePath"]
            .as_str()
            .ok_or("lesson assessment path absent")?,
    )?;
    let prior: Value = serde_json::from_slice(&prior_bytes).map_err(|e| e.to_string())?;
    let receipt_root = base.join("operation-evidence");
    let prior_index = prior["roundIndex"]
        .as_u64()
        .ok_or("lesson assessment round absent")?;
    let before = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        prior_index,
        prior["parentAssessmentSha256"].as_str(),
        Some(&receipt_root),
    )?;
    need(
        before == prior,
        "lesson baseline strict reassessment differs",
    )?;
    let after = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&proposal.join("program_facts.jsonl")),
        prior_index
            .checked_add(1)
            .ok_or("lesson assessment round overflow")?,
        Some(&digest(&prior_bytes)),
        Some(&receipt_root),
    )?;
    need(
        after["totals"] == before["totals"]
            && after["standard"] == before["standard"]
            && after["skills"] == before["skills"],
        "lesson admission unexpectedly changes scope readiness",
    )?;
    let mut files = BTreeMap::new();
    fn collect(
        root: &Path,
        at: &Path,
        files: &mut BTreeMap<String, Vec<u8>>,
    ) -> Result<(), String> {
        need(
            fs::symlink_metadata(at)
                .map_err(|e| e.to_string())?
                .is_dir(),
            "lesson stage directory is not a real directory",
        )?;
        for entry in fs::read_dir(at).map_err(|e| e.to_string())? {
            let path = entry.map_err(|e| e.to_string())?.path();
            let metadata = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
            if metadata.is_dir() {
                collect(root, &path, files)?;
            } else {
                need(
                    metadata.is_file(),
                    "lesson stage contains a symlink or special file",
                )?;
                let relative = path
                    .strip_prefix(root)
                    .map_err(|e| e.to_string())?
                    .to_str()
                    .ok_or("lesson stage filename not UTF8")?;
                files.insert(relative.into(), read(root, relative)?);
            }
        }
        Ok(())
    }
    collect(base, base, &mut files)?;
    if let Some(bytes) = method_source {
        files.insert("reviewed-method-source.md".into(), bytes.to_vec());
    }
    need(
        files.values().map(Vec::len).sum::<usize>() <= 64 * 1024 * 1024,
        "lesson stage snapshot budget exceeded",
    )?;
    for table in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        files.insert(
            format!("{table}.jsonl"),
            jsonl(&rows(&read(proposal, &format!("{table}.jsonl"))?)?)?,
        );
    }
    let after_bytes = serde_json::to_vec_pretty(&after).map_err(|e| e.to_string())?;
    let mut round = plan["tables"]["maintainer_skill_refresh_rounds"]["row"].clone();
    let assessment_path = format!(
        "assessments/lesson-{}.json",
        round["id"].as_str().ok_or("lesson round identity absent")?
    );
    need(
        !files.contains_key(&assessment_path),
        "lesson assessment path already exists",
    )?;
    round["assessment"] = json!({"path":assessment_path,"sha256":digest(&after_bytes)});
    round["assessmentReused"] = json!(false);
    round["priorAssessmentSha256"] = json!(digest(&prior_bytes));
    round["residualGaps"] = after["nextRoundObjectives"].clone();
    let mut history = rows(&files["maintainer_skill_refresh_rounds.jsonl"])?;
    need(
        history
            .insert(round["id"].as_str().unwrap().into(), round)
            .is_none(),
        "lesson round already exists",
    )?;
    files.insert(
        "maintainer_skill_refresh_rounds.jsonl".into(),
        jsonl(&history)?,
    );
    files.insert(assessment_path.clone(), after_bytes.clone());
    let mut inherited = BTreeMap::new();
    let facts = rows(&files["program_facts.jsonl"])?;
    for skill in after["skills"]
        .as_array()
        .ok_or("lesson assessment skills absent")?
    {
        for (id, check) in skill["operationEvidenceChecks"]
            .as_object()
            .into_iter()
            .flatten()
        {
            if check["status"] != "verified" {
                continue;
            }
            let reference =
                &facts.get(id).ok_or("lesson operation fact absent")?["operationEvidence"];
            let path = format!(
                "operation-evidence/{}",
                reference["path"]
                    .as_str()
                    .ok_or("lesson operation path absent")?
            );
            need(
                files
                    .get(&path)
                    .is_some_and(|bytes| reference["sha256"] == digest(bytes)),
                "lesson inherited operation receipt absent or changed",
            )?;
            inherited.insert(
                id.clone(),
                json!({"factId":id,"path":path,"sha256":reference["sha256"]}),
            );
        }
    }
    let result = json!({"schema":"agentlab.maintainer_lesson_stage_result.v1","decision":"review-proposed-lesson-knowledge",
        "strictOperationEvidencePolicy":true,"beforeAssessmentSha256":digest(&prior_bytes),"assessmentSha256":digest(&after_bytes),
        "before":before["totals"],"after":after["totals"],"advancedScopeIds":[],"countsAsMaturityGain":false});
    files.insert("operation-baseline.json".into(), prior_bytes);
    files.insert(
        "operation-result.json".into(),
        serde_json::to_vec_pretty(&result).map_err(|e| e.to_string())?,
    );
    files.insert(
        "lesson-admission-plan.json".into(),
        serde_json::to_vec_pretty(&plan).map_err(|e| e.to_string())?,
    );
    let table_names = [
        ("maintainerSkills", "maintainer_skills"),
        ("programFacts", "program_facts"),
        ("maintainerScopeSkills", "maintainer_scope_skills"),
        (
            "maintainerSkillRefreshRounds",
            "maintainer_skill_refresh_rounds",
        ),
        ("evaluationCases", "evaluation_cases"),
    ];
    let mut cut: Value = serde_json::from_slice(&files["maintainer-knowledge-cut.json"])
        .map_err(|e| e.to_string())?;
    for (key, table) in table_names {
        cut["tables"][key]["sha256"] = json!(digest(&files[&format!("{table}.jsonl")]));
    }
    cut["staging"] = json!({"authorityWritePerformed":false,"baselineRevision":expected_revision,"mode":"reviewed-lesson-admission"});
    files.insert(
        "maintainer-knowledge-cut.json".into(),
        serde_json::to_vec_pretty(&cut).map_err(|e| e.to_string())?,
    );
    let manifest = json!({"schema":"agentlab.maintainer_skill_tablegit_stage.v1","stageKind":"reviewed-lesson","automaticPromotion":false,
        "authorityWritePerformed":false,"assessment":assessment_path,"acceptedFactIds":[plan["tables"]["program_facts"]["key"]],
        "operationEvidence":{"receiptRoot":"operation-evidence","coverage":"verified-child-operation-facts-only","receipts":[],
            "inheritedReceipts":inherited.values().collect::<Vec<_>>()},
        "tables":table_names.iter().map(|(_,table)| { let path=format!("{table}.jsonl");
            ((*table).to_owned(),json!({"path":path,"sha256":digest(&files[&path])})) }).collect::<BTreeMap<_,_>>()});
    files.insert(
        "stage-manifest.json".into(),
        serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?,
    );
    // Every evidence check precedes destination creation; partial I/O remains
    // visible on failure, never represented as a valid published snapshot.
    fs::create_dir(output).map_err(|e| format!("refusing lesson stage output reuse: {e}"))?;
    for (relative, bytes) in files {
        let path = output.join(relative);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        fs::write(path, bytes).map_err(|e| e.to_string())?;
    }
    Ok(manifest)
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
    prepare_with_method(base, proposal, source, lesson_id, expected_revision, None)
}

fn prepare_with_method(
    base: &Path,
    proposal: &Path,
    source: &Path,
    lesson_id: &str,
    expected_revision: &str,
    method_source: Option<&[u8]>,
) -> Result<Value, String> {
    let method = method_source.unwrap_or(include_bytes!(
        "../../../skills/agentlab-experiment-learning/SKILL.md"
    ));
    need(
        !method.is_empty() && method.len() <= 256 * 1024,
        "admission method source budget",
    )?;
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
    let review_bytes = read(source, "lesson-review.json")?;
    let review: Value = serde_json::from_slice(&review_bytes).map_err(|e| e.to_string())?;
    let mut projection = Value::Null;
    let expected = if review["schema"] == "agentlab.behavior_lesson_review.v1" {
        let original_analysis = rows(&read(source, "analysis_records.jsonl")?)?;
        need(
            original_analysis.len() == 1,
            "admission original analysis ambiguous",
        )?;
        let analysis = original_analysis.values().next().unwrap();
        need(
            analysis["kind"] == "raw-behavior-reconstruction"
                && analysis["code"] == "maintainer_behavior_checks::verify",
            "admission original analyzer unsupported",
        )?;
        let original_consumer = analysis["consumerSourceSha256"]
            .as_str()
            .ok_or("admission projection identity absent")?;
        projection = json!({"declaredOriginalConsumerSha256":original_consumer,
            "currentConsumerSha256":digest(include_bytes!("maintainer_behavior_checks.rs")),
            "originalProducerAuthenticated":false,"currentSemanticReconstructionRequired":true});
        crate::maintainer_behavior_checks::lesson_assets_for_projection(
            &candidate_bytes,
            &read(source, "behavior-contract.json")?,
            &read(source, "behavior-capture.json")?,
            &review_bytes,
            original_consumer,
        )?
    } else {
        let capture = read(source, "stage-calibration.json")?;
        maintainer_stage_feedback::lesson_assets(
            &candidate_bytes,
            &read(source, "downstream-plan.json")?,
            &read(source, "stage-contract.json")?,
            &capture,
            &digest(&capture),
            &review_bytes,
        )?
    };
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
                    && row["methodDigest"] == digest(method),
                "admission proposed lesson lineage differs",
            )?;
            if table == "maintainer_skills" {
                need(
                    row["body"] == review["body"]
                        && row["factIds"] == json!([review["factId"]])
                        && row["skillLayer"] == "method"
                        && row["role"] == "maintenance"
                        && row["stage"]
                            == lesson["promotionContract"]
                                .get("skillStage")
                                .unwrap_or(&json!("calibration"))
                                .clone()
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
        "assessmentReused":true,"sourceCommitAuthenticated":false,"projectionRevalidation":projection,
        "methodSourceSha256":digest(method),"historicalMethodSourceProvided":method_source.is_some(),"methodCommitAuthenticated":false,
        "tables":additions,"requiredFollowUp":["verify declared source cut through committed remote readback","validate staged full knowledge cut before authority transaction","atomic committed readback",
        "export and independently validate new knowledge cut","verify downstream guidance consumption","measure next-round benefit"]}),
    )
}
