use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "agentlab-multi-repo-case-{}-{stamp}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        Self(root)
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

fn copy_tree(source: &Path, target: &Path) {
    fs::create_dir_all(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let destination = target.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&entry.path(), &destination);
        } else {
            fs::copy(entry.path(), destination).unwrap();
        }
    }
}

fn git(root: &Path, args: &[&str]) -> String {
    let result = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    String::from_utf8(result.stdout).unwrap().trim().to_owned()
}

fn run(command: &mut Command) -> std::process::Output {
    command.output().unwrap()
}

#[test]
fn recursive_candidate_becomes_a_calibrated_case_without_exposing_reference_source() {
    let fixture = Fixture::new();
    let repository_root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let example = repository_root.join("examples/multi-repo-case");
    let mut sources = Vec::new();
    for name in ["app", "contracts", "service"] {
        let root = fixture.0.join(name);
        copy_tree(&example.join("baseline").join(name), &root);
        git(&root, &["init", "-q"]);
        git(&root, &["add", "."]);
        git(
            &root,
            &[
                "-c",
                "user.name=Case pipeline",
                "-c",
                "user.email=case@example.invalid",
                "commit",
                "-qm",
                "baseline",
            ],
        );
        let revision = git(&root, &["rev-parse", "HEAD"]);
        sources.push(json!({
            "id":name,
            "repository":format!("fixture://{name}"),
            "root":root,
            "revision":revision
        }));
    }
    let manifest = json!({
        "schema":"agentlab.multi_repo_manifest.v1",
        "repositories":sources,
        "moduleBindings":{
            "@demo/contracts":{"repositoryId":"contracts","path":"src/policy.ts"},
            "@demo/service":{"repositoryId":"service","path":"src/reservation.ts"}
        }
    });
    let manifest_path = fixture.0.join("manifest.json");
    fs::write(
        &manifest_path,
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    let analysis_root = fixture.0.join("analysis");
    let analysis = run(
        Command::new(env!("CARGO_BIN_EXE_agentlab-multi-repo-analysis"))
            .arg(&manifest_path)
            .arg(&analysis_root),
    );
    assert!(
        analysis.status.success(),
        "{}",
        String::from_utf8_lossy(&analysis.stderr)
    );
    let difficulty_path = analysis_root.join("difficulty_candidates.json");
    let difficulty: Value = serde_json::from_slice(&fs::read(&difficulty_path).unwrap()).unwrap();
    let candidate = difficulty["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| {
            row["dimensionId"] == "multi-repository-change-impact"
                && row["seed"]["repositoryId"] == "contracts"
        })
        .unwrap();
    assert_eq!(candidate["affectedRepositoryCount"], 3);
    assert_eq!(candidate["maxDependencyDepth"], 2);
    let candidate_id = candidate["id"].as_str().unwrap();
    let source_set = difficulty["sourceSetSha256"].as_str().unwrap();

    let calibration_root = fixture.0.join("calibration");
    let calibration = run(Command::new("python3")
        .arg(example.join("calibrate.py"))
        .arg("--baseline")
        .arg(example.join("baseline"))
        .arg("--reference")
        .arg(example.join("reference"))
        .arg("--source-set-sha256")
        .arg(source_set)
        .arg("--candidate-id")
        .arg(candidate_id)
        .arg("--output")
        .arg(&calibration_root));
    assert!(
        calibration.status.success(),
        "{}",
        String::from_utf8_lossy(&calibration.stderr)
    );
    let repeated_calibration_root = fixture.0.join("repeated-calibration");
    let repeated_calibration = run(Command::new("python3")
        .arg(example.join("calibrate.py"))
        .arg("--baseline")
        .arg(example.join("baseline"))
        .arg("--reference")
        .arg(example.join("reference"))
        .arg("--source-set-sha256")
        .arg(source_set)
        .arg("--candidate-id")
        .arg(candidate_id)
        .arg("--output")
        .arg(&repeated_calibration_root));
    assert!(repeated_calibration.status.success());
    assert_eq!(
        fs::read(calibration_root.join("summary.json")).unwrap(),
        fs::read(repeated_calibration_root.join("summary.json")).unwrap()
    );
    let oracle_contract_path = example.join("oracle-contract.json");
    let oracle_contract: Value =
        serde_json::from_slice(&fs::read(&oracle_contract_path).unwrap()).unwrap();
    assert_eq!(
        oracle_contract["oracleSha256"],
        digest(&fs::read(example.join("oracle.mjs")).unwrap())
    );
    let construction_root = fixture.0.join("construction");
    let construct = |output: &Path| {
        run(Command::new("python3")
            .arg(repository_root.join("scripts/run-multi-repo-intent-construction.py"))
            .arg("--manifest")
            .arg(&manifest_path)
            .arg("--difficulty")
            .arg(&difficulty_path)
            .arg("--facts")
            .arg(analysis_root.join("workspace_facts.jsonl"))
            .arg("--candidate-id")
            .arg(candidate_id)
            .arg("--oracle-contract")
            .arg(&oracle_contract_path)
            .arg("--participant")
            .arg(example.join("mock-construction-agent.py"))
            .arg("--participant-id")
            .arg("deterministic-construction-fixture-v1")
            .arg("--output")
            .arg(output))
    };
    let constructed = construct(&construction_root);
    assert!(
        constructed.status.success(),
        "{}",
        String::from_utf8_lossy(&constructed.stderr)
    );
    let repeated_construction_root = fixture.0.join("repeated-construction");
    assert!(construct(&repeated_construction_root).status.success());
    assert_eq!(
        fs::read(construction_root.join("intent.json")).unwrap(),
        fs::read(repeated_construction_root.join("intent.json")).unwrap()
    );
    assert_eq!(
        fs::read(construction_root.join("construction-receipt.json")).unwrap(),
        fs::read(repeated_construction_root.join("construction-receipt.json")).unwrap()
    );
    let construction_receipt: Value = serde_json::from_slice(
        &fs::read(construction_root.join("construction-receipt.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(construction_receipt["status"], "candidate-unverified");
    assert_eq!(construction_receipt["semanticKnowledgeVerified"], false);
    assert_eq!(
        construction_receipt["sourceFiles"]
            .as_array()
            .unwrap()
            .len(),
        3
    );
    let request_text =
        fs::read_to_string(construction_root.join("workspace/construction-request.json")).unwrap();
    assert!(!request_text.contains("calibrationExpectations"));
    assert!(!request_text.contains("policyFor(tier)"));
    let intent_path = construction_root.join("intent.json");
    let quality_path = construction_root.join("intent-quality.json");
    let quality = run(Command::new("python3")
        .arg(repository_root.join("scripts/score-multi-repo-intent.py"))
        .arg("--intent")
        .arg(&intent_path)
        .arg("--construction-receipt")
        .arg(construction_root.join("construction-receipt.json"))
        .arg("--oracle-contract")
        .arg(&oracle_contract_path)
        .arg("--output")
        .arg(&quality_path));
    assert!(
        quality.status.success(),
        "{}",
        String::from_utf8_lossy(&quality.stderr)
    );
    let quality_report: Value = serde_json::from_slice(&fs::read(&quality_path).unwrap()).unwrap();
    assert_eq!(quality_report["qualifiedForReview"], true);
    assert_eq!(quality_report["policy"]["automaticPromotion"], false);
    let mut generic_intent: Value =
        serde_json::from_slice(&fs::read(&intent_path).unwrap()).unwrap();
    generic_intent["stages"][0]["demand"] = json!("Update the behavior.");
    let generic_intent_path = fixture.0.join("generic-intent.json");
    fs::write(
        &generic_intent_path,
        serde_json::to_vec_pretty(&generic_intent).unwrap(),
    )
    .unwrap();
    let generic_quality_path = fixture.0.join("generic-quality.json");
    let generic_quality = run(Command::new("python3")
        .arg(repository_root.join("scripts/score-multi-repo-intent.py"))
        .arg("--intent")
        .arg(&generic_intent_path)
        .arg("--construction-receipt")
        .arg(construction_root.join("construction-receipt.json"))
        .arg("--oracle-contract")
        .arg(&oracle_contract_path)
        .arg("--output")
        .arg(&generic_quality_path));
    assert_eq!(generic_quality.status.code(), Some(2));
    let generic_report: Value =
        serde_json::from_slice(&fs::read(&generic_quality_path).unwrap()).unwrap();
    assert_eq!(generic_report["qualifiedForReview"], false);
    let mut changed_construction_receipt = construction_receipt.clone();
    changed_construction_receipt["participantId"] = json!("substituted-participant");
    let changed_construction_receipt_path = fixture.0.join("changed-construction-receipt.json");
    fs::write(
        &changed_construction_receipt_path,
        serde_json::to_vec_pretty(&changed_construction_receipt).unwrap(),
    )
    .unwrap();
    let changed_construction_rejected = run(Command::new("python3")
        .arg(repository_root.join("scripts/propose-multi-repo-case-plan.py"))
        .arg("--difficulty")
        .arg(&difficulty_path)
        .arg("--intent")
        .arg(&intent_path)
        .arg("--construction-receipt")
        .arg(&changed_construction_receipt_path)
        .arg("--quality-report")
        .arg(&quality_path)
        .arg("--output")
        .arg(fixture.0.join("changed-construction-proposal.json")));
    assert!(!changed_construction_rejected.status.success());
    assert!(
        String::from_utf8_lossy(&changed_construction_rejected.stderr)
            .contains("construction receipt digest mismatch")
    );
    let proposal_path = fixture.0.join("proposal.json");
    let proposed = run(Command::new("python3")
        .arg(repository_root.join("scripts/propose-multi-repo-case-plan.py"))
        .arg("--difficulty")
        .arg(&difficulty_path)
        .arg("--intent")
        .arg(&intent_path)
        .arg("--construction-receipt")
        .arg(construction_root.join("construction-receipt.json"))
        .arg("--quality-report")
        .arg(&quality_path)
        .arg("--output")
        .arg(&proposal_path));
    assert!(
        proposed.status.success(),
        "{}",
        String::from_utf8_lossy(&proposed.stderr)
    );
    let proposal: Value = serde_json::from_slice(&fs::read(&proposal_path).unwrap()).unwrap();
    assert_eq!(proposal["status"], "review-required");
    assert_eq!(proposal["automaticPromotion"], false);
    assert_eq!(proposal["allowedEdits"].as_array().unwrap().len(), 3);
    let risk_ids: Vec<_> = proposal["risks"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["id"].clone())
        .collect();
    let proposal_sha256 = digest(&fs::read(&proposal_path).unwrap());
    let review = json!({
        "schema":"agentlab.multi_repo_case_plan_review.v1",
        "proposalSha256":proposal_sha256,
        "verdict":"approve-for-calibration",
        "reviewer":"fixture-maintainer",
        "acknowledgedRiskIds":risk_ids,
        "rationale":"The staged behavior and independent Oracle match the pinned recursive impact surface."
    });
    let review_path = fixture.0.join("review.json");
    fs::write(&review_path, serde_json::to_vec_pretty(&review).unwrap()).unwrap();
    let plan_path = fixture.0.join("plan.json");
    let reviewed = run(Command::new("python3")
        .arg(repository_root.join("scripts/review-multi-repo-case-plan.py"))
        .arg("--proposal")
        .arg(&proposal_path)
        .arg("--review")
        .arg(&review_path)
        .arg("--output")
        .arg(&plan_path));
    assert!(
        reviewed.status.success(),
        "{}",
        String::from_utf8_lossy(&reviewed.stderr)
    );
    let reviewed_plan: Value = serde_json::from_slice(&fs::read(&plan_path).unwrap()).unwrap();
    assert_eq!(reviewed_plan["schema"], "agentlab.multi_repo_case_plan.v2");
    assert_eq!(reviewed_plan["review"]["proposalSha256"], proposal_sha256);

    let mut stale_review = review.clone();
    stale_review["proposalSha256"] = json!("0".repeat(64));
    let stale_review_path = fixture.0.join("stale-review.json");
    fs::write(
        &stale_review_path,
        serde_json::to_vec_pretty(&stale_review).unwrap(),
    )
    .unwrap();
    let stale_reviewed = run(Command::new("python3")
        .arg(repository_root.join("scripts/review-multi-repo-case-plan.py"))
        .arg("--proposal")
        .arg(&proposal_path)
        .arg("--review")
        .arg(&stale_review_path)
        .arg("--output")
        .arg(fixture.0.join("stale-plan.json")));
    assert!(!stale_reviewed.status.success());
    assert!(String::from_utf8_lossy(&stale_reviewed.stderr)
        .contains("review does not bind the exact proposal"));
    let case_path = fixture.0.join("evaluation-case.json");
    let generated = run(Command::new("python3")
        .arg(repository_root.join("scripts/generate-multi-repo-case.py"))
        .arg("--difficulty")
        .arg(&difficulty_path)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--proposal")
        .arg(&proposal_path)
        .arg("--review")
        .arg(&review_path)
        .arg("--construction-quality")
        .arg(&quality_path)
        .arg("--calibration")
        .arg(calibration_root.join("summary.json"))
        .arg("--output")
        .arg(&case_path));
    assert!(
        generated.status.success(),
        "{}",
        String::from_utf8_lossy(&generated.stderr)
    );
    let frozen_text = fs::read_to_string(&case_path).unwrap();
    let frozen: Value = serde_json::from_str(&frozen_text).unwrap();
    assert_eq!(frozen["status"], "frozen-calibrated");
    assert_eq!(frozen["sourceSetSha256"], source_set);
    assert_eq!(frozen["sources"].as_array().unwrap().len(), 3);
    assert_eq!(frozen["stages"].as_array().unwrap().len(), 2);
    assert_eq!(frozen["calibration"]["qualified"], true);
    assert_eq!(
        frozen["qualificationMatrix"]["schema"],
        "agentlab.case_qualification_matrix.v1"
    );
    assert_eq!(
        frozen["qualificationMatrix"]["repairChecks"]
            .as_array()
            .unwrap()
            .len(),
        5
    );
    assert_eq!(
        frozen["qualificationMatrix"]["preservationChecks"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        frozen["qualificationMatrix"]["deviceChecks"]["status"],
        "separate-gate"
    );
    assert_eq!(
        frozen["qualificationMatrix"]["freshness"]["qualified"],
        false
    );
    assert_eq!(frozen["construction"]["status"], "candidate-unverified");
    assert_eq!(frozen["constructionQuality"]["qualifiedForReview"], true);
    assert_eq!(frozen["automaticPromotion"], false);
    assert!(!frozen_text.contains("policyFor(tier)"));
    assert!(!frozen_text.contains("for (let attempts"));

    let qualification = run(Command::new("python3")
        .arg(repository_root.join("scripts/validate-case-qualification.py"))
        .arg("--case")
        .arg(&case_path)
        .arg("--calibration")
        .arg(calibration_root.join("summary.json")));
    assert!(
        qualification.status.success(),
        "{}",
        String::from_utf8_lossy(&qualification.stderr)
    );
    let qualification_result: Value = serde_json::from_slice(&qualification.stdout).unwrap();
    assert_eq!(qualification_result["repairChecks"], 5);
    assert_eq!(qualification_result["preservationChecks"], 1);

    let mut changed_after_review = reviewed_plan.clone();
    changed_after_review["title"] = json!("Changed after exact review");
    let changed_plan_path = fixture.0.join("changed-plan.json");
    fs::write(
        &changed_plan_path,
        serde_json::to_vec_pretty(&changed_after_review).unwrap(),
    )
    .unwrap();
    let changed_rejected = run(Command::new("python3")
        .arg(repository_root.join("scripts/generate-multi-repo-case.py"))
        .arg("--difficulty")
        .arg(&difficulty_path)
        .arg("--plan")
        .arg(&changed_plan_path)
        .arg("--proposal")
        .arg(&proposal_path)
        .arg("--review")
        .arg(&review_path)
        .arg("--construction-quality")
        .arg(&quality_path)
        .arg("--calibration")
        .arg(calibration_root.join("summary.json"))
        .arg("--output")
        .arg(fixture.0.join("changed-case.json")));
    assert!(!changed_rejected.status.success());
    assert!(String::from_utf8_lossy(&changed_rejected.stderr)
        .contains("v2 plan differs from reviewed proposal"));

    let mut tampered: Value =
        serde_json::from_slice(&fs::read(calibration_root.join("summary.json")).unwrap()).unwrap();
    tampered["variants"]["reference"]["stages"]["turn-2"]["pass"] = json!(false);
    let tampered_path = fixture.0.join("tampered-calibration.json");
    fs::write(
        &tampered_path,
        serde_json::to_vec_pretty(&tampered).unwrap(),
    )
    .unwrap();
    let rejected = run(Command::new("python3")
        .arg(repository_root.join("scripts/generate-multi-repo-case.py"))
        .arg("--difficulty")
        .arg(&difficulty_path)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--proposal")
        .arg(&proposal_path)
        .arg("--review")
        .arg(&review_path)
        .arg("--construction-quality")
        .arg(&quality_path)
        .arg("--calibration")
        .arg(&tampered_path)
        .arg("--output")
        .arg(fixture.0.join("rejected-case.json")));
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("calibration mismatch"));
}
