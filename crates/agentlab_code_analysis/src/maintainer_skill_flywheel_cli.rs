use agentlab_code_analysis::maintainer_skill_flywheel::assess_with_receipts;
mod asset_exchange;
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
    if args.iter().any(|a| a == "--analyze-source-dependencies") {
        let bytes = fs::read(value(&args, "--author-request")?)?;
        if bytes.len() > 512 * 1024 {
            return Err("dependency request budget".into());
        }
        let request: serde_json::Value = serde_json::from_slice(&bytes)?;
        let mut result =
            agentlab_code_analysis::maintainer_source_recipe_author::source_dependency_inventory(
                &request,
            )?;
        result["authorRequestSha256"] = serde_json::json!(agentlab_code_analysis::digest(&bytes));
        result["sourceGitBindingVerified"] = serde_json::json!(false);
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?;
        file.write_all(&serde_json::to_vec_pretty(&result)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--acquire-construction-context-objects")
    {
        let report = agentlab_code_analysis::maintainer_construction_context::acquire_objects(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--source-worktree")?),
            &fs::read(value(&args, "--object-plan")?)?,
            &PathBuf::from(value(&args, "--git-program")?),
            &output,
        )?;
        println!("{}", report);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--prepare-source-verifier-interface")
    {
        let result = agentlab_code_analysis::maintainer_source_recipe_author::verifier_interface(
            &fs::read(value(&args, "--author-request")?)?,
            &fs::read(value(&args, "--design")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?;
        file.write_all(&serde_json::to_vec_pretty(&result)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args.iter().any(|a| {
        a == "--prepare-source-recipe-loop-intent" || a == "--check-source-recipe-loop-intent"
    }) {
        let request = fs::read(value(&args, "--author-request")?)?;
        let result = if args
            .iter()
            .any(|a| a == "--check-source-recipe-loop-intent")
        {
            agentlab_code_analysis::maintainer_source_repair::check_loop_intent(
                &request,
                &fs::read(value(&args, "--diagnostic-loop-intent")?)?,
            )?
        } else {
            agentlab_code_analysis::maintainer_source_repair::loop_intent(
                &request,
                value(&args, "--maximum-repairs")?.parse()?,
            )?
        };
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?;
        file.write_all(&serde_json::to_vec_pretty(&result)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--prepare-source-recipe-diagnostic-repair")
    {
        let packet = agentlab_code_analysis::maintainer_source_repair::prepare(
            &PathBuf::from(value(&args, "--stage")?),
            &PathBuf::from(value(&args, "--diagnostic-inputs")?),
            &PathBuf::from(value(&args, "--worker-capture")?),
            value(&args, "--maximum-repairs")?.parse()?,
            &output,
        )?;
        println!("{}", serde_json::to_string(&packet)?);
        return Ok(());
    }
    if args.iter().any(|a| {
        a == "--check-source-recipe-diagnostic-repair"
            || a == "--validate-source-recipe-diagnostic-repair-output"
    }) {
        let request = fs::read(value(&args, "--author-request")?)?;
        let packet = fs::read(value(&args, "--diagnostic-repair")?)?;
        let result = if args
            .iter()
            .any(|a| a == "--validate-source-recipe-diagnostic-repair-output")
        {
            agentlab_code_analysis::maintainer_source_repair::check_output(
                &request,
                &packet,
                &fs::read(value(&args, "--proposal")?)?,
                &fs::read(value(&args, "--design")?)?,
            )?
        } else {
            agentlab_code_analysis::maintainer_source_repair::check(&request, &packet)?
        };
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?;
        file.write_all(&serde_json::to_vec_pretty(&result)?)?;
        file.write_all(b"\n")?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--validate-source-recipe-control-suite")
    {
        let receipt = agentlab_code_analysis::maintainer_source_diagnostic::validate_suite(
            &PathBuf::from(value(&args, "--stage")?),
            &PathBuf::from(value(&args, "--suite")?),
            &output,
        )?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--feedback-source-recipe-diagnostic")
    {
        let receipt = agentlab_code_analysis::maintainer_source_diagnostic::feedback(
            &PathBuf::from(value(&args, "--diagnostic-inputs")?),
            &PathBuf::from(value(&args, "--worker-capture")?),
            &output,
        )?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--prepare-source-recipe-control-diagnostic")
    {
        let receipt = agentlab_code_analysis::maintainer_source_diagnostic::prepare_control(
            &PathBuf::from(value(&args, "--stage")?),
            &PathBuf::from(value(&args, "--typescript")?),
            &PathBuf::from(value(&args, "--worker")?),
            &value(&args, "--image-id")?,
            &output,
            &value(&args, "--control-id")?,
        )?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--prepare-source-recipe-diagnostic")
    {
        let receipt = agentlab_code_analysis::maintainer_source_diagnostic::prepare(
            &PathBuf::from(value(&args, "--stage")?),
            &PathBuf::from(value(&args, "--typescript")?),
            &PathBuf::from(value(&args, "--worker")?),
            &value(&args, "--image-id")?,
            &output,
        )?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args.iter().any(|a| {
        a == "--reconcile-control-declarations" || a == "--validate-control-declaration-reference"
    }) {
        let profile = fs::read(value(&args, "--profile")?)?;
        let reference = fs::read(value(&args, "--control-reference")?)?;
        let report = agentlab_code_analysis::maintainer_control_declarations::reconcile(
            &profile,
            &reference,
            &fs::read(value(&args, "--source-bytes")?)?,
        )?;
        if args
            .iter()
            .any(|a| a == "--validate-control-declaration-reference")
        {
            let parsed: serde_json::Value = serde_json::from_slice(&profile)?;
            if parsed["controlDeclarationReference"]["sha256"]
                != agentlab_code_analysis::digest(&reference)
                || !report["corrections"].as_array().unwrap().is_empty()
            {
                return Err("control declaration reference differs from profile".into());
            }
            let parent = fs::read(value(&args, "--parent-profile")?)?;
            if parsed["controlDeclarationReference"]["parentProfile"]["sha256"]
                != agentlab_code_analysis::digest(&parent)
            {
                return Err("control declaration parent profile differs".into());
            }
            let proposal = agentlab_code_analysis::maintainer_control_declarations::reconcile(
                &parent,
                &reference,
                &fs::read(value(&args, "--source-bytes")?)?,
            )?;
            let mut projection = parsed.clone();
            projection
                .as_object_mut()
                .unwrap()
                .remove("controlDeclarationReference");
            projection["reviewed"] = serde_json::json!(false);
            if projection != proposal["proposedProfile"] {
                return Err("control declaration successor changed other profile fields".into());
            }
        }
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"correctionCount":report["corrections"].as_array().unwrap().len(),"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| {
        a == "--prepare-operation-case-successor" || a == "--validate-operation-case-successor"
    }) {
        let base = PathBuf::from(value(&args, "--knowledge")?);
        let source = PathBuf::from(value(&args, "--source-worktree")?);
        let inputs = fs::read(value(&args, "--operation-inputs")?)?;
        let report = if args
            .iter()
            .any(|a| a == "--validate-operation-case-successor")
        {
            agentlab_code_analysis::maintainer_operation_case::validate_successor_request(
                &base,
                &source,
                &inputs,
                &fs::read(value(&args, "--shadow-request")?)?,
            )?
        } else {
            agentlab_code_analysis::maintainer_operation_case::successor_request(
                &base,
                &source,
                &inputs,
                &value(&args, "--runtime-target")?,
                &fs::read(value(&args, "--parent-request")?)?,
                &fs::read(value(&args, "--parent-proposal")?)?,
                &fs::read(value(&args, "--review-feedback")?)?,
                &fs::read(value(&args, "--construction-context")?)?,
                &fs::read(value(&args, "--edit-boundary")?)?,
            )?
        };
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":report["schema"],"candidateId":report["candidateId"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| {
        a == "--prepare-construction-edit-boundary" || a == "--validate-construction-edit-boundary"
    }) {
        let report = if args
            .iter()
            .any(|a| a == "--validate-construction-edit-boundary")
        {
            agentlab_code_analysis::maintainer_construction_context::validate_edit_boundary(
                &PathBuf::from(value(&args, "--knowledge")?),
                &PathBuf::from(value(&args, "--source-worktree")?),
                &fs::read(value(&args, "--edit-boundary")?)?,
            )?
        } else {
            agentlab_code_analysis::maintainer_construction_context::prepare_edit_boundary(
                &PathBuf::from(value(&args, "--knowledge")?),
                &PathBuf::from(value(&args, "--source-worktree")?),
                &value(&args, "--repository")?,
                &fs::read(value(&args, "--edit-selection")?)?,
            )?
        };
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":report["schema"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--prepare-harmony-build-plan") {
        let module = value(&args, "--build-module")?;
        let report = agentlab_code_analysis::harmony_build_plan::prepare(
            &PathBuf::from(value(&args, "--project-root")?),
            &module,
            &optional(&args, "--host-module").unwrap_or(module.clone()),
            &value(&args, "--product")?,
            &value(&args, "--build-mode")?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":report["schema"],"outputType":report["outputType"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--validate-construction-context") {
        let report = agentlab_code_analysis::maintainer_construction_context::validate_context(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--source-worktree")?),
            &fs::read(value(&args, "--context-packet")?)?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!("{}", report);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--validate-construction-context-object-plan")
    {
        let report = agentlab_code_analysis::maintainer_construction_context::validate_object_plan(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--source-worktree")?),
            &fs::read(value(&args, "--object-plan")?)?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!("{}", report);
        return Ok(());
    }
    if args.iter().any(|a| {
        a == "--prepare-construction-context" || a == "--prepare-construction-context-object-plan"
    }) {
        let paths = args
            .windows(2)
            .filter(|w| w[0] == "--context-path")
            .map(|w| w[1].clone())
            .collect::<Vec<_>>();
        let object_plan = args
            .iter()
            .any(|a| a == "--prepare-construction-context-object-plan");
        let producer = if object_plan {
            agentlab_code_analysis::maintainer_construction_context::prepare_object_plan
        } else {
            agentlab_code_analysis::maintainer_construction_context::prepare
        };
        let report = producer(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--source-worktree")?),
            &value(&args, "--repository")?,
            &paths,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":report["schema"],
            "selectedFileCount":report["selectedFiles"].as_array().unwrap().len(),
            "analysisFactCount":report["ownerKnowledge"].as_array().into_iter().flatten()
                .map(|owner| owner["analysisFacts"].as_array().unwrap().len()).sum::<usize>(),
            "ownerScopeSkillIds":report["ownerScopeSkillIds"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--bind-construction-paths") {
        let report = agentlab_code_analysis::maintainer_construction_context::bind_candidate_paths(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--source-worktree")?),
            &fs::read(value(&args, "--edit-boundary")?)?,
            &fs::read(value(&args, "--candidate")?)?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":report["schema"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--feedback-partial-calibration") {
        let previous = optional(&args, "--previous-feedback-plan")
            .map(fs::read)
            .transpose()?;
        let report = agentlab_code_analysis::maintainer_partial_calibration::plan(
            &fs::read(value(&args, "--readiness")?)?,
            &fs::read(value(&args, "--partial-profile")?)?,
            &PathBuf::from(value(&args, "--capture-root")?),
            previous.as_deref(),
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!(
            "{}",
            serde_json::json!({"status":report["status"],"schedulingAllowed":report["schedulingAllowed"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--describe-observation-archive") {
        let result = agentlab_code_analysis::maintainer_observation_store::archive_descriptor(
            &PathBuf::from(value(&args, "--source")?),
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&result)?)?;
        println!(
            "{}",
            serde_json::json!({"rowCount":result["rowCount"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--recover-observation-export") {
        let result = agentlab_code_analysis::maintainer_observation_store::recover(
            &fs::read(value(&args, "--plan")?)?,
            &fs::read(value(&args, "--remote-snapshot")?)?,
            &output,
        )?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--bind-committed-observation-export")
    {
        let result = agentlab_code_analysis::maintainer_observation_store::bind_committed_export(
            &PathBuf::from(value(&args, "--source")?),
            &fs::read(value(&args, "--plan")?)?,
            &fs::read(value(&args, "--commit-receipt")?)?,
            &fs::read(value(&args, "--remote-snapshot")?)?,
            &fs::read(value(&args, "--baseline-snapshot")?)?,
            &output,
        )?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--plan-observation-import" || a == "--verify-observation-import")
    {
        let source = PathBuf::from(value(&args, "--source")?);
        let remote = fs::read(value(&args, "--remote-snapshot")?)?;
        let result = if args.iter().any(|a| a == "--plan-observation-import") {
            agentlab_code_analysis::maintainer_observation_store::plan(
                &source,
                &remote,
                &fs::read(value(&args, "--destination")?)?,
            )?
        } else {
            agentlab_code_analysis::maintainer_observation_store::verify(
                &source,
                &fs::read(value(&args, "--plan")?)?,
                &fs::read(value(&args, "--commit-receipt")?)?,
                &remote,
                &fs::read(value(&args, "--baseline-snapshot")?)?,
            )?
        };
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&result)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":result["schema"],"insertedRows":result["insertedRows"],"qualified":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--prepare-shadow-case-revision" || a == "--validate-shadow-case-revision")
    {
        let base = PathBuf::from(value(&args, "--knowledge")?);
        let inputs = fs::read(value(&args, "--operation-inputs")?)?;
        let current = fs::read(value(&args, "--shadow-request")?)?;
        let result = if args.iter().any(|a| a == "--validate-shadow-case-revision") {
            agentlab_code_analysis::maintainer_operation_case::validate_revision_request(
                &base,
                &inputs,
                &current,
                &fs::read(value(&args, "--revision-request")?)?,
            )?
        } else {
            agentlab_code_analysis::maintainer_operation_case::revision_request(
                &base,
                &inputs,
                &current,
                &fs::read(value(&args, "--parent-request")?)?,
                &fs::read(value(&args, "--parent-proposal")?)?,
                &fs::read(value(&args, "--review-feedback")?)?,
            )?
        };
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&result)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":result["schema"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--prepare-operation-case-shadow") {
        let request = agentlab_code_analysis::maintainer_operation_case::shadow_request(
            &PathBuf::from(value(&args, "--knowledge")?),
            &fs::read(value(&args, "--operation-inputs")?)?,
            &value(&args, "--runtime-target")?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&request)?)?;
        println!(
            "{}",
            serde_json::json!({"candidateId":request["candidateId"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--prepare-operation-case-inputs") {
        let packet = agentlab_code_analysis::maintainer_operation_case::prepare(
            &PathBuf::from(value(&args, "--knowledge")?),
            &value(&args, "--scope-id")?,
            &value(&args, "--semantic-fact-id")?,
            &value(&args, "--operation-fact-id")?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&packet)?)?;
        println!(
            "{}",
            serde_json::json!({"id":packet["id"],"formalCaseQualified":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--validate-source-design-review-output")
    {
        let receipt =
            agentlab_code_analysis::maintainer_source_recipe_author::check_design_review_output(
                &fs::read(value(&args, "--author-request")?)?,
                &fs::read(value(&args, "--parent-design")?)?,
                &fs::read(value(&args, "--review-feedback")?)?,
                &fs::read(value(&args, "--design")?)?,
            )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args.iter().any(|a| a == "--validate-source-design-review") {
        let receipt = agentlab_code_analysis::maintainer_source_recipe_author::design_review(
            &fs::read(value(&args, "--author-request")?)?,
            &fs::read(value(&args, "--design")?)?,
            &fs::read(value(&args, "--review-feedback")?)?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--validate-source-recipe-revision-output")
    {
        let is_design = args.iter().any(|a| a == "--design");
        let receipt =
            agentlab_code_analysis::maintainer_source_recipe_author::check_revision_output(
                &fs::read(value(&args, "--author-request")?)?,
                &fs::read(value(&args, "--revision-request")?)?,
                &fs::read(value(
                    &args,
                    if is_design { "--design" } else { "--proposal" },
                )?)?,
                is_design,
            )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args.iter().any(|a| a == "--validate-source-recipe-design") {
        let receipt = agentlab_code_analysis::maintainer_source_recipe_author::design(
            &fs::read(value(&args, "--author-request")?)?,
            &fs::read(value(&args, "--design")?)?,
        )?;
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|a| a == "--prepare-source-recipe-revision" || a == "--check-source-recipe-revision")
    {
        let current = fs::read(value(&args, "--author-request")?)?;
        let packet = if args.iter().any(|a| a == "--check-source-recipe-revision") {
            agentlab_code_analysis::maintainer_source_recipe_author::check_revision(
                &current,
                &fs::read(value(&args, "--revision-request")?)?,
            )?
        } else {
            let parent_design = optional(&args, "--parent-design")
                .map(fs::read)
                .transpose()?;
            agentlab_code_analysis::maintainer_source_recipe_author::revision_with_design(
                &current,
                &fs::read(value(&args, "--parent-author-request")?)?,
                &fs::read(value(&args, "--proposal")?)?,
                &fs::read(value(&args, "--review-feedback")?)?,
                parent_design.as_deref(),
            )?
        };
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&packet)?)?;
        println!(
            "{}",
            serde_json::json!({"schema":packet["schema"],"revisionIndex":1,
            "executionPerformed":false,"authorityWritePerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--review-source-recipe-proposal") {
        let receipt = agentlab_code_analysis::maintainer_source_recipe_author::approve(
            &PathBuf::from(value(&args, "--proposal-stage")?),
            &value(&args, "--proposal-sha256")?,
            args.iter().any(|a| a == "--reviewed"),
            &output,
        )?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args.iter().any(|a| a == "--prepare-source-recipe-author") {
        let context = optional(&args, "--context-packet")
            .map(fs::read)
            .transpose()?;
        let request =
            agentlab_code_analysis::maintainer_source_recipe_author::prepare_with_context(
                &PathBuf::from(value(&args, "--knowledge")?),
                &PathBuf::from(value(&args, "--source-worktree")?),
                &optional(&args, "--repository").unwrap_or_else(|| "auto".into()),
                &fs::read(value(&args, "--author-policy")?)?,
                context.as_deref(),
            )?;
        let mut bytes = serde_json::to_vec_pretty(&request)?;
        bytes.push(b'\n');
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?
            .write_all(&bytes)?;
        println!(
            "{}",
            serde_json::json!({"scopeSkillId":request["scope"]["id"],"reviewed":false,"executionPerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|a| a == "--stage-source-recipe-proposal") {
        let request = fs::read(value(&args, "--author-request")?)?;
        let proposal = fs::read(value(&args, "--proposal")?)?;
        if let Some(packet_path) = optional(&args, "--source-guidance") {
            let packet = agentlab_code_analysis::maintainer_guidance::bind_source_recipe(
                &PathBuf::from(value(&args, "--source-guidance-knowledge")?),
                &request,
                &fs::read(value(&args, "--source-guidance-selection")?)?,
            )?;
            let retained: serde_json::Value = serde_json::from_slice(&fs::read(packet_path)?)?;
            if packet != retained {
                return Err("source proposal guidance binding changed".into());
            }
            agentlab_code_analysis::maintainer_guidance::source_recipe_target(&packet, &proposal)?;
        } else if optional(&args, "--source-guidance-knowledge").is_some()
            || optional(&args, "--source-guidance-selection").is_some()
        {
            return Err("source proposal requires complete guidance inputs".into());
        }
        let parent = optional(&args, "--parent-design");
        let review = optional(&args, "--design-review-feedback");
        if parent.is_some() != review.is_some() {
            return Err("design review requires paired parent and feedback".into());
        }
        let receipt = if let (Some(parent), Some(review)) = (parent, review) {
            if optional(&args, "--diagnostic-repair").is_some()
                || optional(&args, "--revision-request").is_some()
            {
                return Err("design review cannot mix repair or proposal revision".into());
            }
            let intent = optional(&args, "--diagnostic-loop-intent")
                .map(fs::read)
                .transpose()?;
            agentlab_code_analysis::maintainer_source_recipe_author::stage_with_design_review(
                &request,
                &proposal,
                &fs::read(value(&args, "--design")?)?,
                &fs::read(parent)?,
                &fs::read(review)?,
                intent.as_deref(),
                &output,
            )?
        } else if let Some(path) = optional(&args, "--diagnostic-repair") {
            if optional(&args, "--revision-request").is_some() {
                return Err("review revision cannot mix automatic repair".into());
            }
            agentlab_code_analysis::maintainer_source_recipe_author::stage_with_diagnostic_repair(
                &request,
                &proposal,
                &fs::read(value(&args, "--design")?)?,
                &fs::read(path)?,
                &output,
            )?
        } else if let Some(path) = optional(&args, "--diagnostic-loop-intent") {
            if optional(&args, "--revision-request").is_some() {
                return Err("review child cannot reset loop intent".into());
            }
            agentlab_code_analysis::maintainer_source_recipe_author::stage_with_loop_intent(
                &request,
                &proposal,
                &fs::read(value(&args, "--design")?)?,
                &fs::read(path)?,
                &output,
            )?
        } else if let Some(path) = optional(&args, "--revision-request") {
            let design = optional(&args, "--design").map(fs::read).transpose()?;
            agentlab_code_analysis::maintainer_source_recipe_author::stage_with_revision(
                &request,
                &proposal,
                design.as_deref(),
                &fs::read(path)?,
                &output,
            )?
        } else if let Some(path) = optional(&args, "--design") {
            agentlab_code_analysis::maintainer_source_recipe_author::stage_with_design(
                &request,
                &proposal,
                &fs::read(path)?,
                &output,
            )?
        } else {
            agentlab_code_analysis::maintainer_source_recipe_author::stage(
                &request, &proposal, &output,
            )?
        };
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if args.iter().any(|a| a == "--execute-source-operation-loop") {
        let report = agentlab_code_analysis::maintainer_source_operation_loop::execute(
            &PathBuf::from(value(&args, "--knowledge")?),
            &fs::read(value(&args, "--operation-catalog")?)?,
            value(&args, "--iterations")?.parse()?,
            &output,
        )?;
        println!("{}", serde_json::to_string(&report)?);
        if report["status"] == "failed" {
            return Err("source operation loop failed; original capture retained".into());
        }
        return Ok(());
    }
    if args.iter().any(|a| a == "--execute-source-operation") {
        let report = agentlab_code_analysis::maintainer_source_operation::execute(
            &PathBuf::from(value(&args, "--scope-skills")?),
            &PathBuf::from(value(&args, "--program-facts")?),
            &PathBuf::from(value(&args, "--operation-receipts-root")?),
            &fs::read(value(&args, "--before")?)?,
            &fs::read(value(&args, "--operation-recipe")?)?,
            &PathBuf::from(value(&args, "--source-worktree")?),
            &output,
        )?;
        println!("{}", serde_json::to_string(&report)?);
        return Ok(());
    }
    if args.iter().any(|a| a == "--qualify-source-operation") {
        let report = agentlab_code_analysis::maintainer_source_operation::qualify(
            &PathBuf::from(value(&args, "--execution-root")?),
            &value(&args, "--execution-receipt-sha256")?,
        )?;
        use std::io::Write;
        fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(output)?
            .write_all(&serde_json::to_vec_pretty(&report)?)?;
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--prepare-business-cycles") {
        let result = agentlab_code_analysis::maintainer_flywheel_business::prepare(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--guidance-request")?),
            &std::env::current_exe()?,
            args.iter().any(|a| a == "--reviewed"),
            &output,
        )?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--run-flywheel-business-stage")
    {
        let result = agentlab_code_analysis::maintainer_flywheel_business::run(
            &fs::read(value(&args, "--stage-request")?)?,
            &output,
        )?;
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--consume-reviewed-return") {
        let receipt = agentlab_code_analysis::maintainer_flywheel_business::consume_reviewed_return(
            &fs::read(value(&args, "--return-request")?)?,
            &output,
        )?;
        println!("{}", receipt);
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--execute-flywheel-cycles") {
        let recipe = fs::read(value(&args, "--recipe")?)?;
        let result = if args.iter().any(|arg| arg == "--cycle-checkpoint") {
            agentlab_code_analysis::maintainer_flywheel_cycles::resume(
                &recipe,
                &output,
                &PathBuf::from(value(&args, "--cycle-checkpoint")?),
                &value(&args, "--cycle-checkpoint-sha256")?,
            )?
        } else {
            if args.iter().any(|arg| arg == "--cycle-checkpoint-sha256") {
                return Err("checkpoint digest requires checkpoint path".into());
            }
            agentlab_code_analysis::maintainer_flywheel_cycles::execute(&recipe, &output)?
        };
        println!(
            "{}",
            serde_json::json!({"status":result["status"],"completedRounds":result["completedRounds"],"qualified":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--validate-source-quality-rubric")
    {
        let bytes = fs::read(value(&args, "--quality-rubric")?)?;
        let rubric = agentlab_code_analysis::maintainer_source_review::validate_rubric(&bytes)?;
        let report = serde_json::json!({
            "schema":"agentlab.source_quality_rubric_validation.v1",
            "qualityRubricSha256":agentlab_code_analysis::digest(&bytes),
            "criterionCount":rubric["criteria"].as_array().unwrap().len(),
            "structureValidated":true,"semanticQualityVerified":false,
            "reviewerExecuted":false,"authorityWritePerformed":false,"qualified":false
        });
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        println!("{}", report);
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--export-source-suite-review-feedback"
            || arg == "--verify-source-suite-review-feedback"
    }) {
        let checkout = if args.iter().any(|a| a == "--source-git-checkout") {
            Some(PathBuf::from(value(&args, "--source-git-checkout")?))
        } else {
            None
        };
        if args
            .iter()
            .any(|arg| arg == "--verify-source-suite-review-feedback")
        {
            if args
                .iter()
                .any(|arg| arg == "--export-source-suite-review-feedback")
            {
                return Err("feedback reception and export are mutually exclusive".into());
            }
            let report = agentlab_code_analysis::maintainer_source_review::verify_feedback_export(
                &PathBuf::from(value(&args, "--source")?),
                &fs::read(value(&args, "--quality-rubric")?)?,
                &PathBuf::from(value(&args, "--participant-evidence")?),
                &fs::read(value(&args, "--review-response")?)?,
                checkout.as_deref(),
                &PathBuf::from(value(&args, "--feedback")?),
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
        let report = agentlab_code_analysis::maintainer_source_review::export_accepted_feedback(
            &PathBuf::from(value(&args, "--source")?),
            &fs::read(value(&args, "--quality-rubric")?)?,
            &PathBuf::from(value(&args, "--participant-evidence")?),
            &fs::read(value(&args, "--review-response")?)?,
            checkout.as_deref(),
            &output,
        )?;
        println!("{}", serde_json::to_string(&report)?);
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--validate-source-suite-review-response"
            || arg == "--verify-source-suite-review-completion"
            || arg == "--diagnose-source-suite-review-citations"
    }) {
        let source = PathBuf::from(value(&args, "--source")?);
        let rubric = fs::read(value(&args, "--quality-rubric")?)?;
        let response = fs::read(value(&args, "--review-response")?)?;
        let checkout = if args.iter().any(|a| a == "--source-git-checkout") {
            Some(PathBuf::from(value(&args, "--source-git-checkout")?))
        } else {
            None
        };
        let report = if args
            .iter()
            .any(|arg| arg == "--verify-source-suite-review-completion")
        {
            agentlab_code_analysis::maintainer_source_review::verify_completion_with_git(
                &source,
                &rubric,
                &PathBuf::from(value(&args, "--participant-evidence")?),
                &response,
                checkout.as_deref(),
            )?
        } else if args
            .iter()
            .any(|arg| arg == "--diagnose-source-suite-review-citations")
        {
            agentlab_code_analysis::maintainer_source_review::diagnose_citations_with_git(
                &source,
                &rubric,
                &response,
                checkout.as_deref(),
            )?
        } else {
            agentlab_code_analysis::maintainer_source_review::validate_response_with_git(
                &source,
                &rubric,
                &response,
                checkout.as_deref(),
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
            serde_json::json!({"verdict":report["verdict"],"responseContentVerified":report["responseContentVerified"] == true,"diagnosticOnly":report["diagnosticOnly"] == true,"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--prepare-source-suite-review"
            || arg == "--prepare-source-suite-review-prompt"
            || arg == "--prepare-source-suite-review-attempt-prompt"
    }) {
        let checkout = if args.iter().any(|a| a == "--source-git-checkout") {
            Some(PathBuf::from(value(&args, "--source-git-checkout")?))
        } else {
            None
        };
        if args.iter().any(|arg| {
            arg == "--prepare-source-suite-review-prompt"
                || arg == "--prepare-source-suite-review-attempt-prompt"
        }) {
            let prompt = if args
                .iter()
                .any(|arg| arg == "--prepare-source-suite-review-attempt-prompt")
            {
                agentlab_code_analysis::maintainer_source_review::prompt_for_review_attempt(
                    &PathBuf::from(value(&args, "--source")?),
                    &fs::read(value(&args, "--quality-rubric")?)?,
                    &PathBuf::from(value(&args, "--participant-evidence")?),
                    checkout.as_deref(),
                )?
            } else {
                agentlab_code_analysis::maintainer_source_review::prompt_with_git(
                    &PathBuf::from(value(&args, "--source")?),
                    &fs::read(value(&args, "--quality-rubric")?)?,
                    checkout.as_deref(),
                )?
            };
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&output)?;
            file.write_all(&prompt)?;
            println!(
                "{}",
                serde_json::json!({"promptPreparedOnly":true,"reviewerExecuted":false,"qualified":false})
            );
            return Ok(());
        }
        let report = agentlab_code_analysis::maintainer_source_review::prepare_with_git(
            &PathBuf::from(value(&args, "--source")?),
            &fs::read(value(&args, "--quality-rubric")?)?,
            checkout.as_deref(),
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&report)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"reviewPreparedOnly":true,"reviewerExecuted":false,"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--export-source-suite-lesson" || arg == "--export-source-suite-observation"
    }) {
        let observation = args
            .iter()
            .any(|a| a == "--export-source-suite-observation");
        if observation
            && args
                .iter()
                .any(|a| a == "--lesson-review" || a == "--export-source-suite-lesson")
        {
            return Err("source suite observation cannot include lesson review".into());
        }
        let review = if observation {
            None
        } else {
            Some(fs::read(value(&args, "--lesson-review")?)?)
        };
        let manifest = agentlab_code_analysis::maintainer_source_suite_lesson::export(
            &PathBuf::from(value(&args, "--stage")?),
            &PathBuf::from(value(&args, "--suite")?),
            review.as_deref(),
            &output,
        )?;
        println!(
            "{}",
            serde_json::json!({"assetClass":manifest["assetClass"],"lessonCreated":!observation,
            "authorityWritePerformed":false,"qualified":false,"automaticPromotion":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--export-behavior-lesson" || arg == "--export-behavior-observation")
    {
        let observation = args
            .iter()
            .any(|arg| arg == "--export-behavior-observation");
        if observation
            && args
                .iter()
                .any(|arg| arg == "--export-behavior-lesson" || arg == "--lesson-review")
        {
            return Err("observation export cannot include lesson review or promotion".into());
        }
        let id = value(&args, "--candidate-id")?;
        let candidates = fs::read_to_string(value(&args, "--candidates")?)?;
        let rows = candidates
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(serde_json::from_str::<serde_json::Value>)
            .collect::<Result<Vec<_>, _>>()?;
        let selected = rows.iter().filter(|r| r["id"] == id).collect::<Vec<_>>();
        if selected.len() != 1 {
            return Err("behavior lesson candidate absent or duplicated".into());
        }
        let candidate = serde_json::to_vec(selected[0])?;
        let contract = fs::read(value(&args, "--contract")?)?;
        let capture = fs::read(value(&args, "--capture")?)?;
        if observation {
            let manifest = agentlab_code_analysis::maintainer_behavior_checks::export_observation(
                &candidate, &contract, &capture, &output,
            )?;
            println!(
                "{}",
                serde_json::json!({"assetClass":manifest["assetClass"],"authorityWritePerformed":false,"lessonCreated":false,"qualified":false})
            );
            return Ok(());
        }
        let review = fs::read(value(&args, "--lesson-review")?)?;
        let tables = agentlab_code_analysis::maintainer_behavior_checks::lesson_assets(
            &candidate, &contract, &capture, &review,
        )?;
        fs::create_dir(&output)?;
        for (name, bytes) in [
            ("candidate.json", candidate),
            ("behavior-contract.json", contract),
            ("behavior-capture.json", capture),
            ("lesson-review.json", review),
        ] {
            fs::write(output.join(name), bytes)?;
        }
        let manifest = asset_exchange::export(&output, "evaluation-instance", &tables);
        println!(
            "{}",
            serde_json::json!({"assetClass":manifest["assetClass"],"authorityWritePerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--execute-behavior-calibration" || arg == "--execute-calibrated-behavior-loop"
    }) {
        let contract = fs::read(value(&args, "--contract")?)?;
        let recipe = fs::read(value(&args, "--calibration-recipe")?)?;
        let result = if args
            .iter()
            .any(|arg| arg == "--execute-calibrated-behavior-loop")
        {
            agentlab_code_analysis::maintainer_behavior_calibration::execute_cycle(
                &contract,
                &recipe,
                &fs::read(value(&args, "--loop-template")?)?,
                &output,
            )?
        } else {
            agentlab_code_analysis::maintainer_behavior_calibration::execute(
                &contract, &recipe, &output,
            )?
        };
        println!(
            "{}",
            serde_json::json!({"status":result["status"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--execute-behavior-loop") {
        let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
            &fs::read(value(&args, "--contract")?)?,
            &fs::read(value(&args, "--capture")?)?,
            &fs::read(value(&args, "--recipe")?)?,
            &output,
        )?;
        println!(
            "{}",
            serde_json::json!({"status":result["status"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--verify-behavior-checks") {
        let feedback = agentlab_code_analysis::maintainer_behavior_checks::verify(
            &fs::read(value(&args, "--contract")?)?,
            &fs::read(value(&args, "--capture")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&feedback)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"nextAction":feedback["nextAction"],"qualified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--verify-author-completion") {
        let receipt = agentlab_code_analysis::maintainer_guidance::completion(
            &PathBuf::from(value(&args, "--participant-evidence")?),
            &fs::read(value(&args, "--author-request")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"authorCompletionVerified":true,"learningBenefitVerified":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--validate-stage-author-proposal")
    {
        let receipt = agentlab_code_analysis::maintainer_guidance::stage_proposal(
            &PathBuf::from(value(&args, "--source-workspace")?),
            &fs::read(value(&args, "--author-request")?)?,
            &fs::read(value(&args, "--proposal")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"proposalContentValid":true,"semanticExecutionVerified":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--verify-guidance-consumption")
    {
        let receipt = agentlab_code_analysis::maintainer_guidance::consumption(
            &PathBuf::from(value(&args, "--participant-evidence")?),
            &fs::read(value(&args, "--guidance-packet")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"agentConsumptionVerified":true,"learningBenefitVerified":false})
        );
        return Ok(());
    }
    if args
        .iter()
        .any(|arg| arg == "--bind-source-recipe-guidance")
    {
        let packet = agentlab_code_analysis::maintainer_guidance::bind_source_recipe(
            &PathBuf::from(value(&args, "--knowledge")?),
            &fs::read(value(&args, "--author-request")?)?,
            &fs::read(value(&args, "--guidance-request")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&packet)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"sourceGuidanceBound":true,"agentConsumptionVerified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--verify-source-recipe-guidance-consumption"
            || arg == "--verify-source-recipe-completion"
    }) {
        let receipt = agentlab_code_analysis::maintainer_guidance::source_recipe_completion(
            &PathBuf::from(value(&args, "--participant-evidence")?),
            &fs::read(value(&args, "--guidance-packet")?)?,
        )?;
        if args
            .iter()
            .any(|arg| arg == "--verify-source-recipe-guidance-consumption")
            && receipt["agentConsumptionVerified"] != true
        {
            return Err("source consumption requires guided treatment".into());
        }
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"authorCompletionVerified":true,"agentConsumptionVerified":receipt["agentConsumptionVerified"],"learningBenefitVerified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--bind-maintainer-guidance") {
        let packet = agentlab_code_analysis::maintainer_guidance::bind(
            &PathBuf::from(value(&args, "--knowledge")?),
            &fs::read(value(&args, "--guidance-request")?)?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&packet)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"guidanceCount":packet["guidance"].as_array().unwrap().len(),"agentConsumptionVerified":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| {
        arg == "--verify-lesson-source-readback" || arg == "--verify-committed-lesson-return"
    }) {
        let base = PathBuf::from(value(&args, "--knowledge")?);
        let proposal = PathBuf::from(value(&args, "--proposal")?);
        let source = PathBuf::from(value(&args, "--lesson-source")?);
        let lesson_id = value(&args, "--lesson-id")?;
        let expected_revision = value(&args, "--expected-knowledge-revision")?;
        let method = optional(&args, "--method-source")
            .map(fs::read)
            .transpose()?;
        if method
            .as_ref()
            .is_some_and(|bytes| bytes.len() > 1024 * 1024)
        {
            return Err("historical method budget".into());
        }
        let inputs = agentlab_code_analysis::maintainer_lesson_admission::ReviewedReturnInputs {
            base: &base,
            proposal: &proposal,
            source: &source,
            lesson_id: &lesson_id,
            expected_revision: &expected_revision,
            method_source: method.as_deref(),
        };
        let capture = fs::read(value(&args, "--readback")?)?;
        let guidance_intent = optional(&args, "--next-guidance-intent")
            .map(fs::read)
            .transpose()?;
        let receipt = if args
            .iter()
            .any(|arg| arg == "--verify-lesson-source-readback")
        {
            inputs.verify_source_readback_with_guidance(
                &capture,
                guidance_intent.as_deref(),
                &output,
            )?
        } else {
            inputs.verify_committed_return_with_guidance(
                &PathBuf::from(value(&args, "--committed-knowledge")?),
                &capture,
                guidance_intent.as_deref(),
                &output,
            )?
        };
        if let Some(guidance) = receipt.get("nextGuidance") {
            for (key, filename) in [
                ("selection", "guidance-selection.json"),
                ("packet", "guidance-packet.json"),
            ] {
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(output.join(filename))?;
                file.write_all(&serde_json::to_vec(&guidance[key])?)?;
            }
        }
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output.join("return-verification.json"))?;
        file.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
        file.write_all(b"\n")?;
        println!("{}", receipt);
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--stage-lesson-admission") {
        let manifest = agentlab_code_analysis::maintainer_lesson_admission::stage(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--proposal")?),
            &PathBuf::from(value(&args, "--lesson-source")?),
            &value(&args, "--lesson-id")?,
            &value(&args, "--expected-knowledge-revision")?,
            &output,
        )?;
        println!(
            "{}",
            serde_json::json!({"stageKind":manifest["stageKind"],"authorityWritePerformed":false})
        );
        return Ok(());
    }
    if args.iter().any(|arg| arg == "--prepare-lesson-admission") {
        let plan = agentlab_code_analysis::maintainer_lesson_admission::prepare(
            &PathBuf::from(value(&args, "--knowledge")?),
            &PathBuf::from(value(&args, "--proposal")?),
            &PathBuf::from(value(&args, "--lesson-source")?),
            &value(&args, "--lesson-id")?,
            &value(&args, "--expected-knowledge-revision")?,
        )?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&output)?;
        file.write_all(&serde_json::to_vec_pretty(&plan)?)?;
        file.write_all(b"\n")?;
        println!(
            "{}",
            serde_json::json!({"decision":plan["decision"],"authorityWritePerformed":false})
        );
        return Ok(());
    }
    let export_lesson = args.iter().any(|arg| arg == "--export-stage-lesson");
    let export_stage = export_lesson || args.iter().any(|arg| arg == "--export-stage-calibration");
    if export_stage || args.iter().any(|arg| arg == "--feedback-stage-calibration") {
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
        if export_stage {
            if previous.is_some() || optional(&args, "--previous-stage-calibration").is_some() {
                return Err(
                    "operational export reconstructs its own capture, not prior scheduling".into(),
                );
            }
            let review = if export_lesson {
                Some(fs::read(value(&args, "--lesson-review")?)?)
            } else {
                None
            };
            let tables = if let Some(review) = &review {
                agentlab_code_analysis::maintainer_stage_feedback::lesson_assets(
                    &candidate_bytes,
                    &downstream_bytes,
                    &contract_bytes,
                    &calibration_bytes,
                    &calibration_sha,
                    review,
                )?
            } else {
                agentlab_code_analysis::maintainer_stage_feedback::assets(
                    &candidate_bytes,
                    &downstream_bytes,
                    &contract_bytes,
                    &calibration_bytes,
                    &calibration_sha,
                )?
            };
            let feedback = agentlab_code_analysis::maintainer_stage_feedback::plan(
                &candidate_bytes,
                &downstream_bytes,
                &contract_bytes,
                &calibration_bytes,
                &calibration_sha,
                None,
            )?;
            let mut feedback_bytes = serde_json::to_vec_pretty(&feedback)?;
            feedback_bytes.push(b'\n');
            fs::create_dir(&output)?;
            if let Some(review) = &review {
                fs::write(output.join("lesson-review.json"), review)?;
            }
            for (name, bytes) in [
                ("candidate.json", candidate_bytes.as_slice()),
                ("downstream-plan.json", downstream_bytes.as_slice()),
                ("stage-contract.json", contract_bytes.as_slice()),
                ("stage-calibration.json", calibration_bytes.as_slice()),
                ("feedback.json", feedback_bytes.as_slice()),
            ] {
                fs::write(output.join(name), bytes)?;
            }
            let manifest = asset_exchange::export(&output, "evaluation-instance", &tables);
            println!(
                "{}",
                serde_json::json!({"assetClass":manifest["assetClass"],
                "tableCount":tables.len(),"qualified":false})
            );
            return Ok(());
        }
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
