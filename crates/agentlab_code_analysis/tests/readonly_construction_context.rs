use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn write(root: &Path, name: &str, value: &Value) {
    fs::write(root.join(name), serde_json::to_vec(value).unwrap()).unwrap();
}

#[test]
fn readonly_context_requires_exact_unique_ownership_and_never_grants_edits() {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    for scenario in [
        "valid",
        "editable",
        "no-context",
        "missing-blob",
        "wrong-revision",
        "wrong-repository",
        "no-owner",
        "duplicate-owner",
        "conflicting-blob",
        "implementation",
    ] {
        let root = std::env::temp_dir().join(format!(
            "readonly-context-{}-{}-{scenario}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let revision = "a".repeat(40);
        let candidate = json!({
            "id":"case", "repositoryId":"test-repository", "sourceRevision":revision,
            "sourceSetSha256":"b".repeat(64), "knowledgeCutSha256":"c".repeat(64),
            "maintainerSkillRefreshRoundId":"round", "scopeSkillIds":["owned"], "factIds":["fact"],
            "editablePaths":if scenario == "editable" {json!(["owned/impl.ets", "shared/model.ets"])} else {json!(["owned/impl.ets"])},
            "contextPaths":if scenario == "no-context" {json!([])} else {json!(["shared/model.ets"])},
            "oracleHypothesis":{"wrongVariants":["wrong-a","wrong-b"]}
        });
        write(&root, "case_generation_candidates.jsonl", &candidate);
        write(
            &root,
            "maintainer-knowledge-cut.json",
            &json!({"sourceSetSha256":"b".repeat(64)}),
        );
        write(
            &root,
            "maintainer_skill_refresh_rounds.jsonl",
            &json!({"id":"round"}),
        );
        let owned = json!({"id":"owned","repositoryId":"test-repository","sourceRevision":revision,"pathBoundary":"owned"});
        let owner = json!({"id":"context-owner","repositoryId":if scenario == "wrong-repository" {"another-repository"} else {"test-repository"},"sourceRevision":if scenario == "wrong-revision" {"d".repeat(40)} else {revision.clone()},"pathBoundary":"shared"});
        let mut scopes = vec![owned];
        if scenario != "no-owner" {
            scopes.push(owner.clone());
        }
        if scenario == "duplicate-owner" {
            let mut duplicate = owner;
            duplicate["id"] = json!("duplicate");
            scopes.push(duplicate);
        }
        fs::write(
            root.join("maintainer_scope_skills.jsonl"),
            scopes
                .iter()
                .map(|v| serde_json::to_string(v).unwrap() + "\n")
                .collect::<String>(),
        )
        .unwrap();
        let mut evidence = vec![
            json!({"path":"owned/impl.ets","gitBlobOid":"1".repeat(40)}),
            json!({"path":"shared/model.ets","gitBlobOid":if scenario == "missing-blob" {String::new()} else {"2".repeat(40)}}),
        ];
        if scenario == "conflicting-blob" {
            evidence.push(json!({"path":"shared/model.ets","gitBlobOid":"3".repeat(40)}));
        }
        write(
            &root,
            "program_facts.jsonl",
            &json!({"id":"fact","repositoryId":"test-repository","sourceRevision":revision,"evidence":evidence}),
        );
        let candidate_sha = format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&candidate).unwrap())
        );
        let plan = json!({
            "schema":"agentlab.shadow_case_construction_plan.v1", "candidateId":"case","candidateSha256":candidate_sha,
            "requiredImplementationPaths":[{"path":if scenario == "implementation" {"shared/model.ets"} else {"owned/impl.ets"},"reason":"implementation"}],
            "requiredOraclePaths":[{"path":"shared/model.ets","reason":"read-only source context"}],
            "runtimeRequirements":[{"id":"runtime","description":"independent execution required","status":"unqualified","evidence":[]}],
            "oracleExecution":{"status":"unqualified","evidence":[]},
            "wrongVariantCalibration":{"status":"unqualified","evidence":[],"requiredCount":2,"executedCount":0},"automaticPromotion":false
        });
        write(&root, "plan.json", &plan);
        let result = Command::new("python3")
            .arg(repo.join("examples/maintainer-knowledge-gate/shadow_construction_readiness.py"))
            .arg("--knowledge")
            .arg(&root)
            .args(["--candidate-id", "case", "--plan"])
            .arg(root.join("plan.json"))
            .arg("--evidence-root")
            .arg(&root)
            .arg("--output")
            .arg(root.join("receipt.json"))
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{scenario}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        let receipt: Value =
            serde_json::from_slice(&fs::read(root.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["automaticPromotion"], false);
        assert_eq!(
            receipt["decision"],
            if scenario == "valid" {
                "blocked-qualification"
            } else {
                "blocked-knowledge-refresh"
            },
            "{scenario}"
        );
        assert_eq!(
            receipt["qualificationBlockers"].as_array().unwrap().len(),
            3
        );
        if scenario == "valid" {
            let context = &receipt["checks"]["oraclePaths"][0];
            assert_eq!(context["inCandidateScope"], false);
            assert_eq!(context["readOnlyContextBound"], true);
            assert_eq!(
                context["contextOwnerScopeSkillIds"],
                json!(["context-owner"])
            );
            assert!(receipt["knowledgeBlockers"].as_array().unwrap().is_empty());
        }
        assert_eq!(
            serde_json::from_slice::<Value>(
                &fs::read(root.join("case_generation_candidates.jsonl")).unwrap()
            )
            .unwrap(),
            candidate
        );
        fs::remove_dir_all(root).unwrap();
    }
}
