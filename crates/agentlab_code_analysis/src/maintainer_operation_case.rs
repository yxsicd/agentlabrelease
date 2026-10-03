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

/// Additive construction handoff. Parent bytes remain historical; fresh context
/// and edit selections are independently reconstructed, never inherited grants.
pub fn successor_request(
    base: &Path,
    source: &Path,
    inputs: &[u8],
    runtime: &str,
    parent_request: &[u8],
    parent_proposal: &[u8],
    review: &[u8],
    context_bytes: &[u8],
    edit_bytes: &[u8],
) -> Result<Value, String> {
    let current = shadow_request(base, inputs, runtime)?;
    need(
        context_bytes.len() <= 1024 * 1024,
        "successor context exceeds budget",
    )?;
    crate::maintainer_construction_context::validate_edit_boundary(base, source, edit_bytes)?;
    let context: Value = serde_json::from_slice(context_bytes).map_err(|e| e.to_string())?;
    let paths = context["selectedFiles"]
        .as_array()
        .ok_or("successor context files absent")?
        .iter()
        .map(|f| {
            f["path"]
                .as_str()
                .map(str::to_owned)
                .ok_or("successor context path absent")
        })
        .collect::<Result<Vec<_>, _>>()?;
    need(
        context
            == crate::maintainer_construction_context::prepare(
                base,
                source,
                current["repository"]["id"].as_str().unwrap(),
                &paths,
            )?,
        "successor source context differs",
    )?;
    bind_successor(
        current,
        inputs,
        runtime,
        parent_request,
        parent_proposal,
        review,
        context_bytes,
        edit_bytes,
    )
}

// Called only after operation admission and source/edit reconstruction above.
fn bind_successor(
    mut current: Value,
    inputs: &[u8],
    runtime: &str,
    parent_request: &[u8],
    parent_proposal: &[u8],
    review: &[u8],
    context_bytes: &[u8],
    edit_bytes: &[u8],
) -> Result<Value, String> {
    need(
        parent_request.len() <= 1024 * 1024,
        "successor parent request exceeds lineage budget",
    )?;
    for bytes in [parent_proposal, review] {
        need(
            bytes.len() <= 64 * 1024,
            "successor parent or review exceeds budget",
        )?;
    }
    need(
        context_bytes.len() <= 1024 * 1024,
        "successor context exceeds budget",
    )?;
    let parent: Value = serde_json::from_slice(parent_request).map_err(|e| e.to_string())?;
    let proposal: Value = serde_json::from_slice(parent_proposal).map_err(|e| e.to_string())?;
    let feedback: Value = serde_json::from_slice(review).map_err(|e| e.to_string())?;
    need(
        parent["schema"] == "agentlab.operation_case_shadow_request.v1"
            && parent["repository"] == current["repository"]
            && parent["scope"]["id"] == current["scope"]["id"]
            && parent["fact"]["id"] == current["fact"]["id"],
        "successor parent source or responsibility differs",
    )?;
    need(
        proposal["schema"] == "agentlab.shadow_case_candidate.v1"
            && proposal["id"] == parent["candidateId"]
            && proposal["repositoryId"] == parent["repository"]["id"]
            && proposal["sourceRevision"] == parent["repository"]["revision"]
            && proposal["scopeSkillIds"]
                == parent
                    .get("candidateScopeSkillIds")
                    .unwrap_or(&parent["fact"]["scopeSkillIds"])
                    .clone()
            && proposal["factIds"] == json!([parent["fact"]["id"]])
            && proposal["status"] == "shadow-proposal"
            && proposal["automaticPromotion"] == false,
        "successor parent proposal identity differs",
    )?;
    need(
        feedback["schema"] == "agentlab.operator_shadow_source_review.v1"
            && feedback["verdict"] == "revision-required"
            && feedback["proposalSha256"] == digest(parent_proposal)
            && feedback["requestSha256"] == digest(parent_request)
            && feedback["sourceRevision"] == current["repository"]["revision"]
            && feedback["formalCaseQualified"] == false
            && feedback["runtimeQualified"] == false
            && feedback["automaticPromotion"] == false,
        "successor review binding differs",
    )?;
    let edit: Value = serde_json::from_slice(edit_bytes).map_err(|e| e.to_string())?;
    let context: Value = serde_json::from_slice(context_bytes).map_err(|e| e.to_string())?;
    for packet in [&edit, &context] {
        need(
            packet["repository"] == current["repository"]
                && packet["knowledgeCutSha256"] == current["knowledgeCutSha256"],
            "successor construction cut differs",
        )?;
    }
    let edits = edit["edits"].as_array().unwrap();
    let parent_paths = proposal["editablePaths"]
        .as_array()
        .ok_or("successor parent editable paths absent")?;
    need(
        !parent_paths.is_empty()
            && parent_paths
                .iter()
                .all(|p| edits.iter().any(|e| e["path"] == *p)),
        "successor selection omits parent editable path",
    )?;
    let allowed: std::collections::BTreeSet<_> = current["fact"]["evidence"]
        .as_array()
        .ok_or("parent source evidence absent")?
        .iter()
        .chain(context["selectedFiles"].as_array().unwrap())
        .chain(edit["sourceContext"]["selectedFiles"].as_array().unwrap())
        .filter_map(|f| f["path"].as_str())
        .collect();
    let findings = feedback["findings"]
        .as_array()
        .ok_or("successor review findings absent")?;
    need(
        !findings.is_empty() && findings.len() <= 8,
        "successor findings outside budget",
    )?;
    let mut ids = std::collections::BTreeSet::new();
    for finding in findings {
        need(
            finding["id"]
                .as_str()
                .is_some_and(|s| !s.is_empty() && s.len() <= 100 && ids.insert(s)),
            "successor finding id invalid",
        )?;
        for key in ["observation", "requestedRevision"] {
            need(
                finding[key]
                    .as_str()
                    .is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 2000),
                "successor finding text invalid",
            )?;
        }
        let cited = finding["sourcePaths"]
            .as_array()
            .ok_or("successor finding source paths absent")?;
        need(
            !cited.is_empty()
                && cited.len() <= 32
                && cited
                    .iter()
                    .all(|p| p.as_str().is_some_and(|s| allowed.contains(s))),
            "successor finding references unbound source",
        )?;
    }
    let mut scopes = std::collections::BTreeSet::new();
    scopes.insert(current["scope"]["id"].as_str().unwrap().to_owned());
    for entry in edits {
        scopes.insert(entry["ownerScopeSkillId"].as_str().unwrap().to_owned());
    }
    let bindings = json!({"parentRequestSha256":digest(parent_request),"parentProposalSha256":digest(parent_proposal),
        "reviewSha256":digest(review),"contextSha256":digest(context_bytes),"editBoundarySha256":digest(edit_bytes),
        "operationInputsSha256":digest(inputs),"runtimeTarget":runtime});
    current["candidateId"] = json!(format!(
        "shadow-case-successor-{}",
        digest(&serde_json::to_vec(&bindings).map_err(|e| e.to_string())?)
    ));
    current["candidateScopeSkillIds"] = json!(scopes);
    current["successorConstruction"] = json!({"schema":"agentlab.shadow_case_successor_inputs.v1",
        "bindings":bindings,"parentCandidateId":proposal["id"],
        "parentRequestUtf8":std::str::from_utf8(parent_request).map_err(|e|e.to_string())?,
        "parentProposalUtf8":std::str::from_utf8(parent_proposal).map_err(|e|e.to_string())?,
        "reviewUtf8":std::str::from_utf8(review).map_err(|e|e.to_string())?,
        "contextUtf8":std::str::from_utf8(context_bytes).map_err(|e|e.to_string())?,
        "editBoundaryUtf8":std::str::from_utf8(edit_bytes).map_err(|e|e.to_string())?,
        "sourceContext":context,"editBoundary":edit,
        "calibrationInherited":false,"formalCaseQualified":false,"automaticPromotion":false});
    Ok(current)
}

pub fn validate_successor_request(
    base: &Path,
    source: &Path,
    inputs: &[u8],
    request_bytes: &[u8],
) -> Result<Value, String> {
    need(
        request_bytes.len() <= 3 * 1024 * 1024,
        "successor request exceeds budget",
    )?;
    let request: Value = serde_json::from_slice(request_bytes).map_err(|e| e.to_string())?;
    let bound = &request["successorConstruction"];
    let text = |key: &str| {
        bound[key]
            .as_str()
            .map(str::as_bytes)
            .ok_or("successor original input absent")
    };
    let expected = successor_request(
        base,
        source,
        inputs,
        request["policy"]["runtimeTarget"]
            .as_str()
            .ok_or("successor runtime absent")?,
        text("parentRequestUtf8")?,
        text("parentProposalUtf8")?,
        text("reviewUtf8")?,
        text("contextUtf8")?,
        text("editBoundaryUtf8")?,
    )?;
    need(
        expected == request,
        "successor request differs from reconstructed inputs",
    )?;
    Ok(
        json!({"schema":"agentlab.shadow_case_successor_validation.v1","requestSha256":digest(request_bytes),
        "candidateId":request["candidateId"],"formalCaseQualified":false,"automaticPromotion":false}),
    )
}

#[cfg(test)]
mod successor_binding_tests {
    use super::*;
    #[test]
    fn arbitrary_repository_successors_bind_parent_review_and_cross_scope_inputs() {
        for repository in ["arbitrary-alpha", "independent-beta"] {
            let source = json!({"id":repository,"revision":"1".repeat(40),"repository":format!("https://example.invalid/{repository}.git")});
            let current = json!({"schema":"agentlab.operation_case_shadow_request.v1","repository":source,
                "scope":{"id":"behavior-owner"},"fact":{"id":"behavior-fact","scopeSkillIds":["behavior-owner"],
                "evidence":[{"path":"pkg/main.rs"}]},"candidateId":"shadow-case-parent-example",
                "knowledgeCutSha256":"2".repeat(64),"policy":{"runtimeTarget":"repository-test"}});
            let parent = serde_json::to_vec(&current).unwrap();
            let proposal = serde_json::to_vec(&json!({"schema":"agentlab.shadow_case_candidate.v1",
                "id":current["candidateId"],"repositoryId":repository,"sourceRevision":"1".repeat(40),
                "scopeSkillIds":["behavior-owner"],"factIds":["behavior-fact"],"editablePaths":["pkg/main.rs"],
                "status":"shadow-proposal","automaticPromotion":false})).unwrap();
            let context = json!({"repository":source,"knowledgeCutSha256":"2".repeat(64),"selectedFiles":[{"path":"tests/check.rs"}]});
            let edits = json!({"repository":source,"knowledgeCutSha256":"2".repeat(64),"sourceContext":context,
                "edits":[{"path":"pkg/main.rs","ownerScopeSkillId":"behavior-owner"},
                {"path":"tests/new.rs","ownerScopeSkillId":"verification-owner"}]});
            let review = json!({"schema":"agentlab.operator_shadow_source_review.v1","verdict":"revision-required",
                "proposalSha256":digest(&proposal),"requestSha256":digest(&parent),"sourceRevision":"1".repeat(40),
                "formalCaseQualified":false,"runtimeQualified":false,"automaticPromotion":false,
                "findings":[{"id":"test-gap","sourcePaths":["tests/check.rs"],"observation":"Template is not behavioral evidence.",
                    "requestedRevision":"Add independent source-bound behavior checks."}]});
            let invoke = |feedback: &Value, context: &Value| {
                bind_successor(
                    current.clone(),
                    b"original inputs",
                    "repository-test",
                    &parent,
                    &proposal,
                    &serde_json::to_vec(feedback).unwrap(),
                    &serde_json::to_vec(context).unwrap(),
                    &serde_json::to_vec(&edits).unwrap(),
                )
            };
            let child = invoke(&review, &context).unwrap();
            assert_eq!(child, invoke(&review, &context).unwrap());
            assert_ne!(child["candidateId"], current["candidateId"]);
            assert_eq!(
                child["candidateScopeSkillIds"],
                json!(["behavior-owner", "verification-owner"])
            );
            assert_eq!(
                child["successorConstruction"]["parentProposalUtf8"],
                std::str::from_utf8(&proposal).unwrap()
            );
            assert_eq!(
                child["successorConstruction"]["calibrationInherited"],
                false
            );
            // A multi-owner successor can itself become the next parent.
            // This proves binding, not an executed automatic business loop.
            let mut child_proposal: Value = serde_json::from_slice(&proposal).unwrap();
            child_proposal["id"] = child["candidateId"].clone();
            child_proposal["scopeSkillIds"] = child["candidateScopeSkillIds"].clone();
            let child_bytes = serde_json::to_vec(&child).unwrap();
            let child_proposal_bytes = serde_json::to_vec(&child_proposal).unwrap();
            let mut later_review = review.clone();
            later_review["requestSha256"] = json!(digest(&child_bytes));
            later_review["proposalSha256"] = json!(digest(&child_proposal_bytes));
            let grandchild = bind_successor(
                current.clone(),
                b"later inputs",
                "repository-test",
                &child_bytes,
                &child_proposal_bytes,
                &serde_json::to_vec(&later_review).unwrap(),
                &serde_json::to_vec(&context).unwrap(),
                &serde_json::to_vec(&edits).unwrap(),
            )
            .unwrap();
            assert_eq!(
                grandchild["successorConstruction"]["parentCandidateId"],
                child["candidateId"]
            );
            assert_ne!(grandchild["candidateId"], child["candidateId"]);
            let mut bad = review.clone();
            bad["findings"][0]["sourcePaths"] = json!(["unloaded.rs"]);
            assert!(invoke(&bad, &context).unwrap_err().contains("unbound"));
            bad = review.clone();
            bad["runtimeQualified"] = json!(true);
            assert!(invoke(&bad, &context).is_err());
            let mut stale = context.clone();
            stale["knowledgeCutSha256"] = json!("f".repeat(64));
            assert!(invoke(&review, &stale).unwrap_err().contains("cut differs"));
        }
    }
}

/// Bind rejected shadow bytes and source-scoped review to a reproducible request.
/// Framework-policy correction is explicit; source/knowledge identity cannot drift.
pub fn revision_request(
    base: &Path,
    inputs: &[u8],
    current: &[u8],
    parent_request: &[u8],
    parent_proposal: &[u8],
    review: &[u8],
) -> Result<Value, String> {
    for bytes in [current, parent_request, parent_proposal, review] {
        need(
            bytes.len() <= 64 * 1024,
            "shadow revision input exceeds budget",
        )?;
    }
    let decode = |bytes: &[u8]| serde_json::from_slice::<Value>(bytes).map_err(|e| e.to_string());
    let now = decode(current)?;
    let runtime = now["policy"]["runtimeTarget"]
        .as_str()
        .ok_or("revision runtime absent")?;
    need(
        now == shadow_request(base, inputs, runtime)?,
        "revision current request differs from committed evidence",
    )?;
    let parent = decode(parent_request)?;
    let mut old_projection = parent.clone();
    let mut new_projection = now.clone();
    for value in [&mut old_projection, &mut new_projection] {
        value["policy"]
            .as_object_mut()
            .ok_or("revision policy absent")?
            .remove("oracleFramework");
    }
    need(
        old_projection == new_projection,
        "revision parent source or knowledge identity differs",
    )?;
    let proposal = decode(parent_proposal)?;
    need(
        proposal.get("lineage").is_none(),
        "published shadow candidates require a successor, not draft revision",
    )?;
    need(
        proposal["schema"] == "agentlab.shadow_case_candidate.v1"
            && proposal["status"] == "shadow-proposal"
            && proposal["automaticPromotion"] == false,
        "revision parent proposal qualification differs",
    )?;
    need(
        proposal["id"] == parent["candidateId"]
            && proposal["repositoryId"] == parent["repository"]["id"]
            && proposal["sourceRevision"] == parent["repository"]["revision"]
            && proposal["scopeSkillIds"] == parent["fact"]["scopeSkillIds"]
            && proposal["factIds"] == json!([parent["fact"]["id"]]),
        "revision parent proposal identity differs",
    )?;
    let feedback = decode(review)?;
    need(
        feedback["schema"] == "agentlab.operator_shadow_source_review.v1"
            && feedback["verdict"] == "revision-required"
            && feedback["automaticPromotion"] == false
            && feedback["formalCaseQualified"] == false
            && feedback["runtimeQualified"] == false,
        "revision feedback cannot approve or qualify",
    )?;
    need(
        feedback["proposalSha256"] == digest(parent_proposal)
            && feedback["requestSha256"] == digest(parent_request)
            && feedback["sourceRevision"] == parent["repository"]["revision"],
        "revision feedback byte binding differs",
    )?;
    let findings = feedback["findings"]
        .as_array()
        .ok_or("revision findings absent")?;
    need(
        !findings.is_empty() && findings.len() <= 8,
        "revision findings outside budget",
    )?;
    let evidence = parent["fact"]["evidence"]
        .as_array()
        .ok_or("revision source evidence absent")?;
    let mut ids = std::collections::BTreeSet::new();
    for finding in findings {
        let id = finding["id"].as_str().ok_or("revision finding id absent")?;
        need(
            !id.is_empty() && id.len() <= 100 && ids.insert(id),
            "revision finding id invalid or duplicate",
        )?;
        for field in ["observation", "requestedRevision"] {
            let text = finding[field]
                .as_str()
                .ok_or("revision finding text absent")?;
            need(
                !text.trim().is_empty() && text.len() <= 2000,
                "revision finding text outside budget",
            )?;
        }
        let paths = finding["sourcePaths"]
            .as_array()
            .ok_or("revision finding source paths absent")?;
        need(
            paths.len() <= evidence.len()
                && paths.iter().all(|p| {
                    p.as_str().is_some_and(|s| !s.is_empty())
                        && evidence.iter().any(|e| e["path"] == *p)
                }),
            "revision finding borrows unbound source",
        )?;
    }
    let utf8 = |bytes: &[u8]| {
        std::str::from_utf8(bytes)
            .map(str::to_owned)
            .map_err(|e| e.to_string())
    };
    Ok(json!({"schema":"agentlab.shadow_case_revision_request.v1",
        "currentRequestSha256":digest(current),"parentRequestSha256":digest(parent_request),
        "parentProposalSha256":digest(parent_proposal),"reviewSha256":digest(review),
        "parentRequestUtf8":utf8(parent_request)?,"parentProposalUtf8":utf8(parent_proposal)?,"reviewUtf8":utf8(review)?,
        "candidateId":now["candidateId"],"sourceRevision":now["repository"]["revision"],
        "automaticPromotion":false,"formalCaseQualified":false,
        "verificationBoundary":"Binds review and retained bytes; does not authenticate reviewer, approve semantics, qualify execution or prove repair benefit."}))
}

pub fn validate_revision_request(
    base: &Path,
    inputs: &[u8],
    current: &[u8],
    packet: &[u8],
) -> Result<Value, String> {
    need(packet.len() <= 256 * 1024, "revision packet exceeds budget")?;
    let value: Value = serde_json::from_slice(packet).map_err(|e| e.to_string())?;
    let raw = |key: &str| {
        value[key]
            .as_str()
            .map(str::as_bytes)
            .ok_or("revision original bytes absent")
    };
    let expected = revision_request(
        base,
        inputs,
        current,
        raw("parentRequestUtf8")?,
        raw("parentProposalUtf8")?,
        raw("reviewUtf8")?,
    )?;
    need(
        value == expected,
        "revision packet differs from reconstructed bindings",
    )?;
    Ok(
        json!({"schema":"agentlab.shadow_case_revision_validation.v1","revisionRequestSha256":digest(packet),
        "currentRequestSha256":digest(current),"parentProposalSha256":expected["parentProposalSha256"],
        "reviewSha256":expected["reviewSha256"],"status":"bound-revision-inputs","formalCaseQualified":false,"automaticPromotion":false}),
    )
}
