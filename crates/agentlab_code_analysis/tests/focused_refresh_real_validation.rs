use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn retained_operator_refresh_preserves_scope_and_original_cut() {
    let receipts = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples/maintainer-knowledge-gate/first-four/qualification-receipts");
    let load = |name: &str| -> Value {
        serde_json::from_slice(&fs::read(receipts.join(name)).unwrap()).unwrap()
    };
    let audit = load("abilitystage-focused-audit.json");
    let fact = load(audit["proposedFact"].as_str().unwrap());
    let receipt = load(audit["proposalReceipt"].as_str().unwrap());
    let comparison = load(audit["comparison"].as_str().unwrap());
    let diagnostic = load("abilitystage-oracle-finding.json");
    let probe = load("abilitystage-failure-control-probe.json");
    let sha = format!("{:x}", Sha256::digest(serde_json::to_vec(&fact).unwrap()));
    assert_eq!(audit["proposedFactValueSha256"], sha);
    assert_eq!(receipt["acceptedFactSha256"], sha);
    assert_eq!(receipt["candidateId"], diagnostic["candidateId"]);
    assert_eq!(
        audit["originalCandidateSha256"],
        diagnostic["candidateSha256"]
    );
    assert_eq!(
        audit["originalKnowledgeCutSha256"],
        diagnostic["knowledgeCutSha256"]
    );
    assert_eq!(fact["sourceRevision"], probe["source"]["revision"]);
    assert!(fact["evidence"]
        .as_array()
        .unwrap()
        .iter()
        .any(|e| e["path"] == probe["source"]["path"]
            && e["gitBlobOid"] == probe["source"]["gitBlobOid"]));
    assert_eq!(comparison["before"], comparison["after"]);
    assert_eq!(audit["producer"], "operator-reviewed-source");
    for field in [
        "historicalCandidateRewritten",
        "authorityWritePerformed",
        "newAgentRun",
        "runtimeQualified",
        "automaticPromotion",
    ] {
        assert_eq!(audit[field], false);
    }
}

#[test]
fn focused_refresh_executes_real_validation_without_weakening_expansion() {
    let root = std::env::temp_dir().join(format!(
        "focused-real-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(root.join("unit")).unwrap();
    let git = |args: &[&str]| {
        let result = Command::new("git")
            .arg("-C")
            .arg(&root)
            .args(args)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        String::from_utf8(result.stdout).unwrap().trim().to_owned()
    };
    git(&["init"]);
    git(&["config", "user.name", "Fixture"]);
    git(&["config", "user.email", "fixture@example.invalid"]);
    let paths = [
        "unit/one.rs",
        "unit/two.rs",
        "unit/config.toml",
        "unit/check.rs",
        "unit/oracle.rs",
        "unit/unrelated.rs",
    ];
    for (index, path) in paths.iter().enumerate() {
        fs::write(root.join(path), format!("source-{index}\n")).unwrap();
    }
    git(&["add", "unit"]);
    git(&["commit", "-m", "source evidence"]);
    let revision = git(&["rev-parse", "HEAD"]);
    let evidence: Vec<Value> = paths
        .iter()
        .map(|path| {
            json!({"path":path,
        "gitBlobOid":git(&["rev-parse", &format!("{revision}:{path}")])})
        })
        .collect();
    let dimensions = json!(["responsibility", "boundary", "relations", "behavior"]);
    let old = json!({"id":"agent-analysis-arbitrary-contract", "repositoryId":"arbitrary-repo",
        "sourceRevision":revision, "scopeSkillIds":["scope-arbitrary-unit"], "kind":"analysis",
        "dimensions":dimensions, "interpretation":"The implementation has source-bound responsibility, relations, behavior and boundaries that remain unqualified for runtime.",
        "limitations":["This source fixture does not qualify an actual platform or application runtime.",
            "Independent behavior and wrong implementation calibration remain unexecuted."],
        "evidence":evidence[..3]});
    let request = json!({"schema":"agentlab.maintainer_skill_focused_refresh_request.v1",
        "repository":{"id":"arbitrary-repo", "revision":revision},
        "scope":{"id":"scope-arbitrary-unit", "pathBoundary":"unit"},
        "existingFact":old, "requiredDimensions":dimensions,
        "requiredImplementationPaths":[{"path":paths[3],"reason":"bound check owner"}],
        "requiredOraclePaths":[{"path":paths[4],"reason":"independent check body"}],
        "sourceAssessment":{"sha256":"a".repeat(64)}, "candidateId":"shadow-case-arbitrary-contract"});
    let mut proposal = old.clone();
    proposal["schema"] = json!("agentlab.maintainer_skill_fact_proposal.v1");
    proposal["evidence"] = json!(evidence[..5]);
    let scripts =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/maintainer-knowledge-gate");
    let write = |name: &str, value: &Value| {
        fs::write(root.join(name), serde_json::to_vec(value).unwrap()).unwrap()
    };
    let invoke = |script: &str, label: &str| {
        Command::new("python3")
            .arg(scripts.join(script))
            .args(["validate", "--request"])
            .arg(root.join("request.json"))
            .arg("--proposal")
            .arg(root.join("proposal.json"))
            .arg("--source")
            .arg(&root)
            .arg("--program-facts")
            .arg(root.join("facts.jsonl"))
            .arg("--output")
            .arg(root.join(format!("{label}-facts.jsonl")))
            .arg("--receipt")
            .arg(root.join(format!("{label}-receipt.json")))
            .output()
            .unwrap()
    };
    write("request.json", &request);
    write("proposal.json", &proposal);
    write("facts.jsonl", &old);
    let result = invoke("focused_fact_refresh.py", "valid");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let receipt: Value =
        serde_json::from_slice(&fs::read(root.join("valid-receipt.json")).unwrap()).unwrap();
    assert_eq!(receipt["addedEvidencePaths"], json!([paths[3], paths[4]]));
    assert_eq!(receipt["automaticPromotion"], false);
    for label in [
        "missing-dimensions",
        "extra-path",
        "missing-path",
        "wrong-blob",
        "stale-baseline",
    ] {
        let mut req = request.clone();
        let mut prop = proposal.clone();
        let mut baseline = old.clone();
        match label {
            "missing-dimensions" => {
                req.as_object_mut().unwrap().remove("requiredDimensions");
            }
            "extra-path" => {
                prop["evidence"]
                    .as_array_mut()
                    .unwrap()
                    .push(evidence[5].clone());
            }
            "missing-path" => {
                prop["evidence"].as_array_mut().unwrap().pop();
            }
            "wrong-blob" => {
                prop["evidence"][4]["gitBlobOid"] = json!("0".repeat(40));
            }
            "stale-baseline" => {
                baseline["interpretation"] = json!("concurrent maintainer update");
            }
            _ => unreachable!(),
        }
        write("request.json", &req);
        write("proposal.json", &prop);
        write("facts.jsonl", &baseline);
        assert!(
            !invoke("focused_fact_refresh.py", label).status.success(),
            "accepted {label}"
        );
        assert!(!root.join(format!("{label}-facts.jsonl")).exists());
    }
    // Ordinary expansion still accepts exactly three independently checked blobs.
    write("request.json", &request);
    write("proposal.json", &proposal);
    fs::write(root.join("facts.jsonl"), "").unwrap();
    assert!(!invoke("agent_flywheel.py", "expanded-five")
        .status
        .success());
    proposal["evidence"] = json!(evidence[..3]);
    write("proposal.json", &proposal);
    assert!(invoke("agent_flywheel.py", "expanded-three")
        .status
        .success());
    fs::remove_dir_all(root).unwrap();
}
