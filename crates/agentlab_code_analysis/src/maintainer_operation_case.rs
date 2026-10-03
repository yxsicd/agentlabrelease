//! Bridge admitted maintenance evidence into case construction inputs, not a case.
use crate::{digest, maintainer_flywheel_plan, maintainer_skill_flywheel::assess_with_receipts};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::Path};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn read(path: &Path) -> Result<Vec<u8>, String> {
    need(path.is_absolute(), "case input root must be absolute")?;
    for parent in path.ancestors() {
        need(
            !fs::symlink_metadata(parent)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "case input symlink rejected",
        )?;
    }
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    need(
        meta.is_file() && meta.len() <= 16 * 1024 * 1024,
        "case input must be a bounded file",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    need(
        bytes.len() <= 16 * 1024 * 1024,
        "case input grew beyond budget",
    )?;
    Ok(bytes)
}
fn rows(bytes: &[u8]) -> Result<BTreeMap<String, Value>, String> {
    let mut result = BTreeMap::new();
    for line in std::str::from_utf8(bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|s| !s.trim().is_empty())
    {
        let row: Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        let id = row["id"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("case row id missing")?
            .to_owned();
        need(result.insert(id, row).is_none(), "case duplicate row")?;
    }
    Ok(result)
}

/// Select an explicitly named semantic fact and verified operation from one cut.
/// Recomputes maintenance readiness; never relabels its controls as case calibration.
pub fn prepare(
    base: &Path,
    scope_id: &str,
    semantic_id: &str,
    operation_id: &str,
) -> Result<Value, String> {
    let cut_bytes = read(&base.join("maintainer-knowledge-cut.json"))?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    let revision = cut["tableGitAuthority"]["revision"].as_str().unwrap_or("");
    need(
        cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && cut["automaticPromotion"] == false
            && cut.get("staging").is_none()
            && revision.len() == 40
            && revision
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "case construction requires a committed fixed cut",
    )?;
    let mut tables = BTreeMap::new();
    for (key, file) in [
        ("maintainerSkills", "maintainer_skills.jsonl"),
        ("maintainerScopeSkills", "maintainer_scope_skills.jsonl"),
        ("programFacts", "program_facts.jsonl"),
        (
            "maintainerSkillRefreshRounds",
            "maintainer_skill_refresh_rounds.jsonl",
        ),
        ("evaluationCases", "evaluation_cases.jsonl"),
    ] {
        let bytes = read(&base.join(file))?;
        need(
            cut["tables"][key]["path"] == file && cut["tables"][key]["sha256"] == digest(&bytes),
            "case table digest differs",
        )?;
        tables.insert(key, rows(&bytes)?);
    }
    let scope = tables["maintainerScopeSkills"]
        .get(scope_id)
        .ok_or("case scope absent")?;
    let semantic = tables["programFacts"]
        .get(semantic_id)
        .ok_or("case semantic fact absent")?;
    let operation = tables["programFacts"]
        .get(operation_id)
        .ok_or("case operation fact absent")?;
    need(
        semantic_id != operation_id && semantic["kind"] == "analysis",
        "case semantic fact is not analysis",
    )?;
    let repositories = cut["repositories"]
        .as_array()
        .ok_or("case repositories absent")?;
    let matches = repositories
        .iter()
        .filter(|r| r["id"] == scope["repositoryId"])
        .collect::<Vec<_>>();
    need(matches.len() == 1, "case repository absent or duplicated")?;
    let repository = matches[0];
    for fact in [semantic, operation] {
        need(
            fact["repositoryId"] == repository["id"]
                && fact["sourceRevision"] == repository["revision"]
                && scope["sourceRevision"] == repository["revision"]
                && fact["scopeSkillIds"] == json!([scope_id]),
            "case source or scope binding differs",
        )?;
    }
    let dimensions = semantic["dimensions"]
        .as_array()
        .ok_or("case semantic dimensions absent")?;
    need(
        ["behavior", "boundary", "relations", "responsibility"]
            .iter()
            .all(|d| dimensions.iter().any(|v| v == d)),
        "case semantic fact lacks behavioral dimensions",
    )?;
    need(
        semantic["evidence"].as_array().is_some_and(|e| {
            !e.is_empty()
                && e.iter().all(|v| {
                    v["gitBlobOid"].as_str().is_some_and(|s| s.len() == 40)
                        && v["path"].as_str().is_some_and(|s| !s.is_empty())
                })
        }),
        "case semantic source evidence absent",
    )?;
    let evidence = semantic["evidence"].as_array().unwrap();
    let matches_blob = |owner: &Value, item: &Value| {
        owner["evidence"].as_array().is_some_and(|inventory| {
            inventory
                .iter()
                .any(|v| v["path"] == item["path"] && v["gitBlobOid"] == item["gitBlobOid"])
        })
    };
    need(
        evidence.iter().any(|item| matches_blob(scope, item)),
        "case semantic evidence lacks a matching scope Blob anchor",
    )?;
    let durable = maintainer_flywheel_plan::latest_assessment(base)?;
    let retained: Value = serde_json::from_slice(&read(Path::new(
        durable["assessmentPath"]
            .as_str()
            .ok_or("case assessment absent")?,
    ))?)
    .map_err(|e| e.to_string())?;
    let assessed = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        retained["roundIndex"]
            .as_u64()
            .ok_or("case assessment round absent")?,
        retained["parentAssessmentSha256"].as_str(),
        Some(&base.join("operation-evidence")),
    )?;
    need(
        assessed == retained,
        "case independent maintenance assessment differs",
    )?;
    let selected = assessed["skills"]
        .as_array()
        .ok_or("case assessed scopes absent")?
        .iter()
        .find(|s| s["skillId"] == scope_id)
        .ok_or("case assessed scope absent")?;
    need(
        selected["checks"]["maintenanceReady"] == true
            && selected["operationEvidenceChecks"][operation_id]["status"] == "verified",
        "case selected maintenance evidence unverified",
    )?;
    let identity = json!({"knowledgeCutSha256":digest(&cut_bytes), "scopeSkillId":scope_id,
        "semanticFactId":semantic_id,"operationFactId":operation_id});
    Ok(
        json!({"schema":"agentlab.maintainer_operation_case_inputs.v1",
        "id":format!("operation-case-inputs-{}",digest(&serde_json::to_vec(&identity).map_err(|e| e.to_string())?)),
        "knowledgeCutSha256":digest(&cut_bytes),"knowledgeRevision":revision,
        "sourceSetSha256":cut["sourceSetSha256"],"maintainerSkillRefreshRoundId":durable["refreshRoundId"],
        "assessmentSha256":durable["assessmentSha256"],"repository":repository,"scope":scope,
        "semanticFact":semantic,"operationFact":operation,
        "operationVerification":selected["operationEvidenceChecks"][operation_id],
        "status":"construction-inputs-only","automaticPromotion":false,"authorityWritePerformed":false,
        "semanticBlobVerification":"matching-scope-anchor-only; complete source inventory must be verified during construction",
        "formalCaseQualified":false,"caseCalibrationInherited":false,
        "nextRequirements":["derive concrete staged task demands from semantic source evidence",
            "bind candidate to repository Skills, program analyses and this exact cut",
            "retain diverse cohort or explicit insufficiency result","construct independent Oracle under frozen task checks",
            "calibrate accepted and meaningful wrong task implementations","satisfy declared runtime and freeze gates",
            "execute assessed attempts and return new evidence to a later knowledge cut"],
        "verificationBoundary":"Verifies fixed exported bytes and maintenance receipt content, not remote commit authenticity, reviewer identity, formal case calibration or runtime qualification."}),
    )
}

/// Reverify an input packet before translating it into the shadow constructor's
/// semantic fields. Maintenance proof retains its own lineage, not a fake loop.
pub fn shadow_request(base: &Path, inputs: &[u8], runtime: &str) -> Result<Value, String> {
    let packet: Value = serde_json::from_slice(inputs).map_err(|e| e.to_string())?;
    need(
        packet["schema"] == "agentlab.maintainer_operation_case_inputs.v1",
        "operation case input schema differs",
    )?;
    let id = |v: &Value| {
        v["id"]
            .as_str()
            .map(str::to_owned)
            .ok_or("operation case input id absent")
    };
    let checked = prepare(
        base,
        &id(&packet["scope"])?,
        &id(&packet["semanticFact"])?,
        &id(&packet["operationFact"])?,
    )?;
    need(
        packet == checked,
        "operation case inputs differ from current committed evidence",
    )?;
    need(
        matches!(runtime, "harmony-emulator" | "repository-test"),
        "operation case runtime unsupported",
    )?;
    need(
        runtime == "harmony-emulator"
            || !packet["scope"]["testEntrypoints"]
                .as_array()
                .is_some_and(|a| {
                    a.iter()
                        .any(|p| p.as_str().is_some_and(|s| s.contains("ohosTest")))
                }),
        "ohosTest requires Harmony emulator",
    )?;
    let durable = maintainer_flywheel_plan::latest_assessment(base)?;
    let assessment: Value = serde_json::from_slice(&read(Path::new(
        durable["assessmentPath"]
            .as_str()
            .ok_or("case assessment absent")?,
    ))?)
    .map_err(|e| e.to_string())?;
    Ok(json!({"schema":"agentlab.operation_case_shadow_request.v1",
        "automaticPromotion":false,"sourceSetSha256":packet["sourceSetSha256"],
        "knowledgeCutSha256":packet["knowledgeCutSha256"],"maintainerSkillRefreshRoundId":packet["maintainerSkillRefreshRoundId"],
        "operationInputsSha256":digest(inputs),"maintenanceEvidence":packet["operationVerification"],
        "knowledgeCoverage":assessment["totals"],"repository":packet["repository"],
        "scope":packet["scope"],"fact":packet["semanticFact"],
        "candidateId":format!("shadow-case-operation-{}",digest(inputs)),
        "policy":{"candidateLimit":1,"constructionMode":"shadow","candidateGateRequired":true,
            "independentOracleRequired":true,"wrongVariantCalibrationRequired":true,
            "runtimeTarget":runtime,"oracleFramework":if runtime == "harmony-emulator" {"ohosTest"} else {"repository-test"},
            "externalHardwareAllowed":false,"physicalDeviceFallbackAllowed":false,
            "shadowEligible":true,"blockers":[],"caseCalibrationInherited":false},
        "output":"shadow-case-proposal.json"}))
}
