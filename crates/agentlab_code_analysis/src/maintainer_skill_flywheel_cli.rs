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
        let report = agentlab_code_analysis::maintainer_flywheel_plan::plan(
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
