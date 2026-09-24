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
    let oracle_sha256 = digest(&fs::read(example.join("oracle.mjs")).unwrap());
    let plan = json!({
        "schema":"agentlab.multi_repo_case_plan.v1",
        "caseId":"case-cross-repo-retry-policy-v1",
        "candidateId":candidate_id,
        "sourceSetSha256":source_set,
        "title":"Propagate retry policy across contract, service and application repositories",
        "allowedEdits":[
            {"repositoryId":"contracts","path":"src/policy.ts"},
            {"repositoryId":"service","path":"src/reservation.ts"},
            {"repositoryId":"app","path":"src/checkout.ts"}
        ],
        "stages":[
            {
                "id":"turn-1",
                "demand":"Add premium policy with three attempts while preserving the standard one-attempt boundary. Make the service obey the shared policy and report the actual attempt count.",
                "checkIds":["standard-one-attempt","premium-third-attempt","premium-exhaustion"]
            },
            {
                "id":"turn-2",
                "demand":"Update the application result mapping to preserve tier and actual attempt count for accepted and exhausted requests without changing retry ownership.",
                "checkIds":["accepted-consumer-output","fallback-consumer-output","standard-consumer-output"]
            }
        ],
        "oracle":{
            "sha256":oracle_sha256,
            "authority":"independent-executable-oracle",
            "receiptSchema":"agentlab.multi_repo_oracle_receipt.v1"
        },
        "calibrationExpectations":{
            "baseline":{"turn-1":false,"turn-2":false},
            "reference":{"turn-1":true,"turn-2":true},
            "hardcoded-premium":{"turn-1":false,"turn-2":false},
            "stale-consumer":{"turn-1":true,"turn-2":false}
        }
    });
    let plan_path = fixture.0.join("plan.json");
    fs::write(&plan_path, serde_json::to_vec_pretty(&plan).unwrap()).unwrap();
    let case_path = fixture.0.join("evaluation-case.json");
    let generated = run(Command::new("python3")
        .arg(repository_root.join("scripts/generate-multi-repo-case.py"))
        .arg("--difficulty")
        .arg(&difficulty_path)
        .arg("--plan")
        .arg(&plan_path)
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
    assert_eq!(frozen["automaticPromotion"], false);
    assert!(!frozen_text.contains("policyFor(tier)"));
    assert!(!frozen_text.contains("for (let attempts"));

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
        .arg("--calibration")
        .arg(&tampered_path)
        .arg("--output")
        .arg(fixture.0.join("rejected-case.json")));
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("calibration mismatch"));
}
