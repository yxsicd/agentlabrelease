use agentlab_code_analysis::maintainer_skill_flywheel::assess_with_receipts;
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
};

fn value(args: &[String], name: &str) -> Result<String, String> {
    let index = args
        .iter()
        .position(|arg| arg == name)
        .ok_or_else(|| format!("missing {name}"))?;
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("missing value for {name}"))
}

fn optional(args: &[String], name: &str) -> Option<String> {
    let index = args.iter().position(|arg| arg == name)?;
    args.get(index + 1).cloned()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let output = PathBuf::from(value(&args, "--output")?);
    if args.iter().any(|arg| arg == "--feedback-stage-calibration") {
        let selected = value(&args, "--candidate-id")?;
        let rows = fs::read_to_string(value(&args, "--candidates")?)?
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(serde_json::from_str::<serde_json::Value>)
            .collect::<Result<Vec<_>, _>>()?;
        let selected = rows
            .iter()
            .filter(|r| r["id"] == selected)
            .collect::<Vec<_>>();
        if selected.len() != 1 {
            return Err("stage candidate absent or duplicated".into());
        }
        let previous = optional(&args, "--previous-feedback-plan")
            .map(fs::read)
            .transpose()?;
        let candidate_bytes = serde_json::to_vec(selected[0])?;
        let downstream_bytes = fs::read(value(&args, "--downstream-plan")?)?;
        let contract_bytes = fs::read(value(&args, "--stage-contract")?)?;
        let calibration_bytes = fs::read(value(&args, "--stage-calibration")?)?;
        let calibration_sha = value(&args, "--calibration-sha256")?;
        let prior_capture = optional(&args, "--previous-stage-calibration");
        let report = if let Some(path) = prior_capture {
            agentlab_code_analysis::maintainer_stage_feedback::resume(
                &candidate_bytes,
                &downstream_bytes,
                &contract_bytes,
                &calibration_bytes,
                &calibration_sha,
                previous
                    .as_deref()
                    .ok_or("previous capture requires prior feedback")?,
                &fs::read(path)?,
                &value(&args, "--previous-calibration-sha256")?,
            )?
        } else {
            agentlab_code_analysis::maintainer_stage_feedback::plan(
                &candidate_bytes,
                &downstream_bytes,
                &contract_bytes,
                &calibration_bytes,
                &calibration_sha,
                previous.as_deref(),
            )?
        };
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"nextAction":report["nextAction"],"schedulingAllowed":report["schedulingAllowed"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--compare-oracle-repair") {
        let report = agentlab_code_analysis::maintainer_downstream_exec::compare_oracle_repair(
            &PathBuf::from(value(&args, "--before-execution-root")?),
            &value(&args, "--before-execution-sha256")?,
            &PathBuf::from(value(&args, "--after-execution-root")?),
            &value(&args, "--after-execution-sha256")?,
            &PathBuf::from(value(&args, "--source-worktree")?),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"controlsImproved":report["controlsImproved"],"nextAction":report["nextAction"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--prepare-downstream-probe") {
        let compiler = optional(&args, "--typescript").map(PathBuf::from);
        let report = agentlab_code_analysis::maintainer_downstream_exec::recipe(
            &fs::read(value(&args, "--downstream-plan")?)?,
            &PathBuf::from(value(&args, "--source-worktree")?),
            &PathBuf::from(value(&args, "--node")?),
            &PathBuf::from(value(&args, "--probe-script")?),
            &value(&args, "--test-path")?,
            &value(&args, "--suite-export")?,
            &value(&args, "--test-id")?,
            compiler.as_deref(),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--execute-downstream-probe") {
        let selected = value(&args, "--candidate-id")?;
        let rows = fs::read_to_string(value(&args, "--candidates")?)?
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(serde_json::from_str::<serde_json::Value>)
            .collect::<Result<Vec<_>, _>>()?;
        let candidates = rows
            .iter()
            .filter(|r| r["id"] == selected)
            .collect::<Vec<_>>();
        if candidates.len() != 1 {
            return Err("downstream candidate absent or duplicated".into());
        }
        let report = agentlab_code_analysis::maintainer_downstream_exec::execute(
            &fs::read(value(&args, "--downstream-plan")?)?,
            &serde_json::to_vec(candidates[0])?,
            &fs::read(value(&args, "--probe-recipe")?)?,
            &PathBuf::from(value(&args, "--source-worktree")?),
            &output,
        )?;
        println!(
            "{}",
            serde_json::json!({"decision":report["feedback"]["decision"],"qualified":false,"agentExecutionPerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--feedback-downstream-probe") {
        let previous = optional(&args, "--previous-feedback-plan")
            .map(fs::read)
            .transpose()?;
        let report = agentlab_code_analysis::maintainer_downstream_exec::next(
            &PathBuf::from(value(&args, "--execution-root")?),
            &value(&args, "--execution-sha256")?,
            previous.as_deref(),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"nextAction":report["nextAction"],"schedulingAllowed":report["schedulingAllowed"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--summarize-downstream") {
        let report = agentlab_code_analysis::maintainer_downstream::batch(
            &fs::read(value(&args, "--candidates")?)?,
            &fs::read(value(&args, "--plans")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--plan-downstream") {
        let previous = optional(&args, "--previous-plan")
            .map(fs::read)
            .transpose()?;
        let report = agentlab_code_analysis::maintainer_downstream::plan(
            &fs::read(value(&args, "--readiness")?)?,
            previous.as_deref(),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"candidateId":report["candidateId"],"status":report["status"],"readyActionCount":report["readyActionCount"],"agentExecutionPerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--qualify-operation-capture") {
        if output.exists() || output.is_symlink() {
            return Err("qualification output already exists".into());
        }
        let report = agentlab_code_analysis::maintainer_operation_qualification::qualify(
            &PathBuf::from(value(&args, "--execution-root")?),
            &value(&args, "--execution-receipt-sha256")?,
            &value(&args, "--module-root")?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"status":report["status"],"qualificationScope":report["qualificationScope"],"authorityWritePerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--execute-operation") {
        let report = agentlab_code_analysis::maintainer_operation_exec::execute(
            &PathBuf::from(value(&args, "--scope-skills")?),
            &PathBuf::from(value(&args, "--program-facts")?),
            &PathBuf::from(value(&args, "--operation-receipts-root")?),
            &fs::read(value(&args, "--next-round-plan")?)?,
            &fs::read(value(&args, "--before")?)?,
            &fs::read(value(&args, "--operation-recipe")?)?,
            &PathBuf::from(value(&args, "--source-worktree")?),
            &output,
        )?;
        println!(
            "{}",
            serde_json::json!({"status":report["status"],"qualified":false,"authorityWritePerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--resolve-latest-assessment") {
        let report = agentlab_code_analysis::maintainer_flywheel_plan::latest_assessment(
            &PathBuf::from(value(&args, "--base")?),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&report)?);
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--stage-operation-round") {
        let selected = args
            .iter()
            .enumerate()
            .filter(|(_, arg)| arg.as_str() == "--selected-scope")
            .map(|(i, _)| {
                args.get(i + 1)
                    .cloned()
                    .ok_or("selected scope value missing")
            })
            .collect::<Result<Vec<_>, _>>()?;
        let manifest = agentlab_code_analysis::maintainer_operation_stage::stage(
            &PathBuf::from(value(&args, "--base")?),
            &PathBuf::from(value(&args, "--program-facts")?),
            &PathBuf::from(value(&args, "--before")?),
            &PathBuf::from(value(&args, "--after")?),
            &PathBuf::from(value(&args, "--operation-receipts-root")?),
            &selected,
            &value(&args, "--run-id")?,
            args.iter()
                .any(|arg| arg == "--allow-baseline-reassessment"),
            &output,
        )?;
        println!("{}", serde_json::to_string(&manifest)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--compare-operation-round" || arg == "--compare-semantic-round")
    {
        let before = fs::read(value(&args, "--before")?)?;
        let after = fs::read(value(&args, "--after")?)?;
        let selected = args
            .iter()
            .enumerate()
            .filter(|(_, arg)| arg.as_str() == "--selected-scope")
            .map(|(i, _)| {
                args.get(i + 1)
                    .cloned()
                    .ok_or("selected scope value missing")
            })
            .collect::<Result<Vec<_>, _>>()?;
        let result = if args.iter().any(|arg| arg == "--compare-semantic-round") {
            agentlab_code_analysis::maintainer_semantic_round::compare(&before, &after, &selected)?
        } else {
            agentlab_code_analysis::maintainer_operation_evidence::compare_round(
                &before, &after, &selected,
            )?
        };
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&result)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    let scopes = PathBuf::from(value(&args, "--scope-skills")?);
    if args.iter().any(|arg| arg == "--prepare-semantic-batch") {
        let assessment_path = PathBuf::from(value(&args, "--before")?);
        let report = agentlab_code_analysis::maintainer_flywheel_plan::semantic_batch(
            &scopes,
            &PathBuf::from(value(&args, "--program-facts")?),
            &PathBuf::from(value(&args, "--operation-receipts-root")?),
            &fs::read(value(&args, "--next-round-plan")?)?,
            &fs::read(&assessment_path)?,
            &assessment_path,
            &fs::read(value(&args, "--knowledge-cut")?)?,
            &optional(&args, "--repository").unwrap_or_else(|| "auto".into()),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"selectedScopeCount":report["selectedScopeCount"],
            "selectionPolicy":report["selectionPolicy"]})
        );
        return Ok(());
    }
    let receipts = if args.iter().any(|arg| arg == "--operation-receipts-root") {
        Some(PathBuf::from(value(&args, "--operation-receipts-root")?))
    } else {
        None
    };
    if let Some(id) = optional(&args, "--prepare-operation-fact") {
        let rows = fs::read_to_string(&scopes)?;
        let mut selected = None;
        for line in rows.lines().filter(|line| !line.trim().is_empty()) {
            let row: serde_json::Value = serde_json::from_str(line)?;
            if row["id"].as_str() == Some(id.as_str()) {
                if selected.is_some() {
                    return Err("duplicate selected scope".into());
                }
                selected = Some(row);
            }
        }
        let skill = selected.ok_or("selected scope missing")?;
        let reference = serde_json::json!({
            "path":value(&args, "--operation-receipt")?,
            "sha256":value(&args, "--operation-receipt-sha256")?
        });
        let fact = agentlab_code_analysis::maintainer_operation_evidence::prepare_fact(
            &skill,
            reference,
            receipts
                .as_deref()
                .ok_or("missing --operation-receipts-root")?,
        )?;
        // A proposed cut, not a TableGit write or automatic promotion.
        let mut candidates = std::collections::BTreeMap::new();
        if let Some(path) = optional(&args, "--program-facts") {
            for line in fs::read_to_string(path)?
                .lines()
                .filter(|line| !line.trim().is_empty())
            {
                let row: serde_json::Value = serde_json::from_str(line)?;
                let id = row["id"]
                    .as_str()
                    .filter(|id| !id.is_empty())
                    .ok_or("existing fact id missing")?
                    .to_owned();
                if candidates.insert(id, row).is_some() {
                    return Err("existing fact id duplicated".into());
                }
            }
        }
        let id = fact["id"].as_str().unwrap().to_owned();
        if candidates
            .get(&id)
            .is_some_and(|existing| existing != &fact)
        {
            return Err("operation fact identity conflicts with existing row".into());
        }
        candidates.insert(id, fact.clone());
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        for row in candidates.values() {
            file.write_all(&serde_json::to_vec(row)?)?;
            file.write_all(b"\n")?;
        }
        println!(
            "{}",
            serde_json::json!({"decision":"prepared-operation-fact", "factId":fact["id"], "automaticPromotion":false})
        );
        return Ok(());
    }
    let facts = optional(&args, "--program-facts").map(PathBuf::from);
    let round_index = value(&args, "--round-index")?.parse::<u64>()?;
    let parent = optional(&args, "--parent-assessment-sha256");
    if args.iter().any(|arg| arg == "--plan-next-round") {
        let available = args
            .iter()
            .enumerate()
            .filter(|(_, arg)| arg.as_str() == "--available-lane")
            .map(|(i, _)| {
                args.get(i + 1)
                    .cloned()
                    .ok_or("available lane value missing")
            })
            .collect::<Result<Vec<_>, _>>()?;
        let operation_kinds = args
            .iter()
            .enumerate()
            .filter(|(_, arg)| arg.as_str() == "--available-operation-kind")
            .map(|(i, _)| {
                args.get(i + 1)
                    .cloned()
                    .ok_or("available operation kind missing")
            })
            .collect::<Result<Vec<_>, _>>()?;
        let report = agentlab_code_analysis::maintainer_flywheel_plan::plan_for_capabilities(
            &scopes,
            facts.as_deref(),
            receipts
                .as_deref()
                .ok_or("plan requires --operation-receipts-root")?,
            round_index,
            parent.as_deref(),
            &available,
            optional(&args, "--batch-size")
                .unwrap_or_else(|| "1".into())
                .parse()?,
            optional(&args, "--max-source-files")
                .unwrap_or_else(|| "80".into())
                .parse()?,
            optional(&args, "--repository").as_deref(),
            if operation_kinds.is_empty() {
                None
            } else {
                Some(&operation_kinds)
            },
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&report["summary"])?);
        return Ok(());
    }
    let assessment = assess_with_receipts(
        &scopes,
        facts.as_deref(),
        round_index,
        parent.as_deref(),
        receipts.as_deref(),
    )?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output)
        .map_err(|error| format!("refusing to overwrite {}: {error}", output.display()))?;
    file.write_all(&serde_json::to_vec_pretty(&assessment)?)?;
    file.write_all(b"\n")?;
    println!("{}", serde_json::to_string(&assessment["totals"])?);
    Ok(())
}
