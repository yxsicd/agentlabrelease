//! Bounded productive operation rounds over explicitly reviewed recipes.
//! Candidate staging only: no model, remote write, case promotion or full cycle.
use crate::{
    digest, maintainer_flywheel_plan as planner, maintainer_operation_evidence as evidence,
    maintainer_operation_stage, maintainer_skill_flywheel::assess_with_receipts,
    maintainer_source_operation as operation,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Write,
    path::{Path, PathBuf},
};

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn read(path: &Path, limit: usize) -> Result<Vec<u8>, String> {
    for ancestor in path.ancestors() {
        require(
            !fs::symlink_metadata(ancestor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "operation loop input contains symlink",
        )?;
    }
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    require(
        meta.is_file() && meta.len() <= limit as u64,
        "operation loop input exceeds budget",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    require(bytes.len() <= limit, "operation loop input grew")?;
    Ok(bytes)
}
fn save(path: &Path, bytes: &[u8]) -> Result<(), String> {
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?
        .write_all(bytes)
        .map_err(|e| e.to_string())
}
fn pretty(v: &Value) -> Result<Vec<u8>, String> {
    let mut bytes = serde_json::to_vec_pretty(v).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("operation loop {key} absent"))
}
fn rows(path: &Path) -> Result<BTreeMap<String, Value>, String> {
    let bytes = read(path, 16 * 1024 * 1024)?;
    let mut rows = BTreeMap::new();
    for line in std::str::from_utf8(&bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|l| !l.is_empty())
    {
        let row: Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
        require(
            rows.insert(text(&row, "id")?.to_owned(), row).is_none(),
            "operation loop duplicate row",
        )?;
    }
    Ok(rows)
}
fn copy_receipts(from: &Path, to: &Path, remaining: &mut usize) -> Result<(), String> {
    require(
        fs::symlink_metadata(from)
            .map_err(|e| e.to_string())?
            .is_dir(),
        "operation loop receipts directory invalid",
    )?;
    fs::create_dir(to).map_err(|e| e.to_string())?;
    for entry in fs::read_dir(from).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let target = to.join(entry.file_name());
        let meta = entry.file_type().map_err(|e| e.to_string())?;
        if meta.is_dir() {
            copy_receipts(&entry.path(), &target, remaining)?;
        } else {
            require(
                meta.is_file(),
                "operation loop receipt contains symlink or special file",
            )?;
            let bytes = read(&entry.path(), *remaining)?;
            *remaining = remaining
                .checked_sub(bytes.len())
                .ok_or("operation loop receipt budget")?;
            save(&target, &bytes)?;
        }
    }
    Ok(())
}

/// Each subsequent plan consumes the previous staged cut's durable assessment.
/// Missing reviewed recipes stop selection, rather than borrowing another scope.
pub fn execute(
    knowledge: &Path,
    catalog_bytes: &[u8],
    iterations: u64,
    output: &Path,
) -> Result<Value, String> {
    require(
        (1..=3).contains(&iterations),
        "operation loop requires one to three iterations",
    )?;
    require(
        catalog_bytes.len() <= 256 * 1024,
        "operation catalog budget",
    )?;
    let catalog: Value = serde_json::from_slice(catalog_bytes).map_err(|e| e.to_string())?;
    require(
        catalog["schema"] == "agentlab.reviewed_source_operation_catalog.v1"
            && catalog["reviewed"] == true
            && catalog["automaticPromotion"] == false,
        "operation catalog review/schema differs",
    )?;
    let knowledge = knowledge.canonicalize().map_err(|e| e.to_string())?;
    let cut_bytes = read(
        &knowledge.join("maintainer-knowledge-cut.json"),
        1024 * 1024,
    )?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    require(
        catalog["knowledgeCutSha256"] == digest(&cut_bytes)
            && cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && cut.get("staging").is_none(),
        "operation catalog knowledge cut differs",
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
        let filename = format!("{name}.jsonl");
        require(
            cut["tables"][key]["path"] == filename
                && cut["tables"][key]["sha256"]
                    == digest(&read(&knowledge.join(filename), 16 * 1024 * 1024)?),
            "operation loop initial table differs from selected cut",
        )?;
    }
    let selector = text(&catalog, "repositorySelector")?;
    let entries = catalog["entries"]
        .as_array()
        .filter(|a| a.len() <= 64)
        .ok_or("operation catalog entries invalid")?;
    let mut recipes = BTreeMap::new();
    let mut ids = BTreeSet::new();
    for entry in entries {
        let id = text(entry, "scopeSkillId")?;
        require(ids.insert(id), "operation catalog duplicate scope")?;
        let recipe_path = PathBuf::from(text(&entry["recipe"], "path")?);
        let source = PathBuf::from(text(entry, "sourceWorktree")?);
        require(
            recipe_path.is_absolute() && source.is_absolute(),
            "operation catalog paths must be absolute",
        )?;
        let bytes = read(&recipe_path, 256 * 1024)?;
        require(
            entry["recipe"]["sha256"] == digest(&bytes),
            "operation catalog recipe digest differs",
        )?;
        let recipe: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        require(
            recipe["scopeSkillId"] == id
                && recipe["schema"] == "agentlab.maintainer_source_operation_recipe.v1"
                && recipe["reviewed"] == true
                && recipe["automaticPromotion"] == false
                && recipe["operationKind"] == "source-only",
            "operation catalog recipe review/scope/kind differs",
        )?;
        recipes.insert(id.to_owned(), (recipe_path, bytes, source));
    }
    require(
        output.is_absolute(),
        "operation loop output must be absolute",
    )?;
    let parent = output
        .parent()
        .ok_or("operation loop output parent absent")?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let resolved_output = parent.join(
        output
            .file_name()
            .ok_or("operation loop output name absent")?,
    );
    require(
        !resolved_output.starts_with(&knowledge),
        "operation loop output inside knowledge",
    )?;
    for (_, _, source) in recipes.values() {
        let source = source.canonicalize().map_err(|e| e.to_string())?;
        require(
            !resolved_output.starts_with(source),
            "operation loop output inside source",
        )?;
    }
    planner::latest_assessment(&knowledge)?;
    fs::create_dir(output).map_err(|e| format!("refusing operation loop output reuse: {e}"))?;
    save(&output.join("catalog.json"), catalog_bytes)?;
    let mut current = knowledge;
    let mut rounds = Vec::new();
    let mut terminal = "bounded-round-limit".to_owned();
    let mut gap = Value::Null;
    let execution = (|| -> Result<(), String> {
        for index in 1..=iterations {
            let dir = output.join(format!("iteration-{index}"));
            fs::create_dir(&dir).map_err(|e| e.to_string())?;
            let durable = planner::latest_assessment(&current)?;
            save(&dir.join("durable-reference.json"), &pretty(&durable)?)?;
            let before_path = PathBuf::from(text(&durable, "assessmentPath")?);
            let before_bytes = read(&before_path, 16 * 1024 * 1024)?;
            let before: Value = serde_json::from_slice(&before_bytes).map_err(|e| e.to_string())?;
            let scopes = current.join("maintainer_scope_skills.jsonl");
            let facts = current.join("program_facts.jsonl");
            let receipts = current.join("operation-evidence");
            let round = before["roundIndex"]
                .as_u64()
                .ok_or("operation loop baseline round absent")?;
            let plan = planner::plan_for_capabilities(
                &scopes,
                Some(&facts),
                &receipts,
                round,
                before["parentAssessmentSha256"].as_str(),
                &["operation-verification".into()],
                1,
                80,
                Some(selector),
                Some(&["source-only".into()]),
            )?;
            require(
                before == plan["assessment"],
                "operation loop baseline differs from independent plan",
            )?;
            save(&dir.join("plan.json"), &pretty(&plan)?)?;
            if plan["decision"] != "propose-next-batch" {
                terminal = "review-required".into();
                gap = json!({"code":"no-executable-source-operation-selection","planDecision":plan["decision"]});
                break;
            }
            require(
                plan["nextLane"] == "operation-verification"
                    && plan["selectedScopeIds"]
                        .as_array()
                        .is_some_and(|a| a.len() == 1),
                "operation loop selected lane/batch differs",
            )?;
            let id = plan["selectedScopeIds"][0]
                .as_str()
                .ok_or("operation loop selected id invalid")?;
            let Some((recipe_path, recipe_bytes, source)) = recipes.get(id) else {
                terminal = "review-required".into();
                gap = json!({"code":"selected-source-operation-recipe-required","scopeSkillId":id});
                break;
            };
            require(
                read(recipe_path, 256 * 1024)? == *recipe_bytes,
                "operation loop reviewed recipe changed",
            )?;
            save(&dir.join("before.json"), &before_bytes)?;
            save(&dir.join("recipe.json"), recipe_bytes)?;
            operation::execute(
                &scopes,
                &facts,
                &receipts,
                &before_bytes,
                recipe_bytes,
                source,
                &dir.join("capture"),
            )?;
            let capture_sha = digest(&read(
                &dir.join("capture/execution-receipt.json"),
                2 * 1024 * 1024,
            )?);
            let qualification = operation::qualify(&dir.join("capture"), &capture_sha)?;
            let bytes = pretty(&qualification)?;
            let qualification_sha = digest(&bytes);
            let receipt_name = format!("source-{qualification_sha}.json");
            let next_receipts = dir.join("receipts");
            copy_receipts(&receipts, &next_receipts, &mut (16 * 1024 * 1024))?;
            save(&next_receipts.join(&receipt_name), &bytes)?;
            let scope_rows = rows(&scopes)?;
            let fact = evidence::prepare_fact(
                scope_rows.get(id).ok_or("operation loop scope absent")?,
                json!({"path":receipt_name,"sha256":qualification_sha}),
                &next_receipts,
            )?;
            let mut fact_rows = rows(&facts)?;
            require(
                fact_rows
                    .insert(text(&fact, "id")?.to_owned(), fact.clone())
                    .is_none(),
                "operation loop would replay existing fact",
            )?;
            let mut candidate_bytes = Vec::new();
            for row in fact_rows.values() {
                candidate_bytes.extend(serde_json::to_vec(row).map_err(|e| e.to_string())?);
                candidate_bytes.push(b'\n');
            }
            let candidate = dir.join("candidate-facts.jsonl");
            save(&candidate, &candidate_bytes)?;
            let after = assess_with_receipts(
                &scopes,
                Some(&candidate),
                round
                    .checked_add(1)
                    .ok_or("operation loop round overflow")?,
                Some(&digest(&before_bytes)),
                Some(&next_receipts),
            )?;
            let after_path = dir.join("after.json");
            let after_bytes = pretty(&after)?;
            save(&after_path, &after_bytes)?;
            let result = evidence::compare_round(&before_bytes, &after_bytes, &[id.to_owned()])?;
            require(
                result["maintenanceReadyDelta"] == 1,
                "operation loop nonproductive transition",
            )?;
            save(&dir.join("result.json"), &pretty(&result)?)?;
            let next = dir.join("stage");
            maintainer_operation_stage::stage(
                &current,
                &candidate,
                &dir.join("before.json"),
                &after_path,
                &next_receipts,
                &[id.to_owned()],
                &format!("source-loop-{index}"),
                false,
                &next,
            )?;
            rounds.push(json!({"iteration":index,"scopeSkillId":id,"acceptedFactId":fact["id"],
                "beforeAssessmentSha256":digest(&before_bytes),"afterAssessmentSha256":digest(&after_bytes),
                "executionReceiptSha256":capture_sha,"qualificationSha256":qualification_sha,
                "maintenanceReadyDelta":1,"before":before["totals"],"after":after["totals"],
                "snapshot":next,"candidateOnly":true}));
            current = next;
        }
        Ok(())
    })();
    if let Err(error) = execution {
        terminal = "failed".into();
        gap = json!({"code":"operation-loop-stage-failed","error":error});
    }
    let report = json!({"schema":"agentlab.reviewed_source_operation_loop.v1","status":terminal,"gap":gap,
        "requestedIterations":iterations,"productiveOperationRounds":rounds.len(),"rounds":rounds,
        "finalCandidateSnapshot":if rounds.is_empty(){Value::Null}else{json!(current)},
        "catalogSha256":digest(catalog_bytes),"initialKnowledgeCutSha256":digest(&cut_bytes),
        "authorityWritePerformed":false,"automaticPromotion":false,"closedLoopQualified":false,
        "recipeGenerationPerformed":false,"agentExecutionPerformed":false});
    save(&output.join("loop-receipt.json"), &pretty(&report)?)?;
    Ok(report)
}
