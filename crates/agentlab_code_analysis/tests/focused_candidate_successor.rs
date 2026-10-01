use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn sha(value: &Value) -> String {
    format!("{:x}", Sha256::digest(serde_json::to_vec(value).unwrap()))
}

#[test]
fn two_arbitrary_repositories_keep_parents_and_clear_borrowed_qualification() {
    let root = std::env::temp_dir().join(format!(
        "successor-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples/maintainer-knowledge-gate/focused_fact_refresh.py");
    for name in ["arbitrary-alpha", "unrelated-beta"] {
        let base = root.join(name);
        fs::create_dir_all(base.join("construction-plans")).unwrap();
        let write = |path: &str, value: &Value| {
            fs::write(base.join(path), serde_json::to_vec(value).unwrap()).unwrap()
        };
        let fact = json!({"id":"fact-example", "repositoryId":name,"sourceRevision":"1".repeat(40),
            "scopeSkillIds":["scope-example"],"limitations":["runtime unknown", "calibration unknown"],
            "evidence":[{"path":"pkg/main.rs","gitBlobOid":"2".repeat(40)},
                {"path":"pkg/check.rs","gitBlobOid":"3".repeat(40)}]});
        let parent = json!({"schema":"agentlab.shadow_case_candidate.v1", "id":"shadow-case-arbitrary-parent",
            "repositoryId":name,"sourceRevision":"1".repeat(40),"sourceSetSha256":"4".repeat(64),
            "knowledgeCutSha256":"5".repeat(64),"maintainerSkillRefreshRoundId":"round-old",
            "scopeSkillIds":["scope-example"],"factIds":["fact-example"],
            "title":"Preserve the source contract", "mechanism":"Source-bound contract retained across stages with an independent check, not runtime proof.",
            "stagedDemands":["first bounded change", "later requirement"],"editablePaths":["pkg/main.rs"],"contextPaths":[],
            "oracleHypothesis":{"framework":"repository-test","observables":["state kept", "result correct"],
                "requiredEnvironment":["controlled repository runner"],"wrongVariants":["lost state", "wrong result"],"status":"hypothesis-unqualified"},
            "limitations":["original gap", "no runtime proof"],"lineage":{"loopReceiptSha256":"6".repeat(64)},
            "status":"shadow-proposal","automaticPromotion":false});
        let plan = json!({"schema":"agentlab.shadow_case_construction_plan.v1","candidateId":parent["id"],
            "candidateSha256":sha(&parent),"requiredImplementationPaths":[{"path":"pkg/main.rs","reason":"owner"}],
            "requiredOraclePaths":[{"path":"pkg/check.rs","reason":"independent check"}],
            "runtimeRequirements":[{"id":"runner","description":"controlled runner","status":"qualified","evidence":[{"path":"parent-only.json","sha256":"7".repeat(64)}]}],
            "oracleExecution":{"status":"qualified","evidence":[{"path":"parent-only.json","sha256":"7".repeat(64)}]},
            "wrongVariantCalibration":{"status":"qualified","evidence":[],"requiredCount":2,"executedCount":2},"automaticPromotion":false});
        let receipt = json!({"acceptedFactId":fact["id"],"changeKind":"updated", "candidateId":parent["id"],"acceptedFactSha256":sha(&fact)});
        write("program_facts.jsonl", &fact);
        write("case_generation_candidates.jsonl", &parent);
        write(
            "maintainer_scope_skills.jsonl",
            &json!({"id":"scope-example","repositoryId":name,"sourceRevision":"1".repeat(40),"pathBoundary":"pkg"}),
        );
        fs::write(
            base.join("maintainer_skill_refresh_rounds.jsonl"),
            b"{\"id\":\"round-old\",\"roundIndex\":1}\n{\"id\":\"round-new\",\"roundIndex\":2}\n",
        )
        .unwrap();
        write(
            "maintainer-knowledge-cut.json",
            &json!({"sourceSetSha256":"4".repeat(64),"tables":{"programFacts":{"path":"program_facts.jsonl","sha256":sha(&fact)}}}),
        );
        write("construction-plans/parent.json", &plan);
        write("refresh.json", &receipt);
        let parent_plan_bytes = fs::read(base.join("construction-plans/parent.json")).unwrap();
        let invoke = |label: &str| {
            Command::new("python3")
                .arg(&script)
                .arg("rebind-candidate")
                .arg("--knowledge")
                .arg(&base)
                .args(["--candidate-id", "shadow-case-arbitrary-parent"])
                .arg("--plan")
                .arg(base.join("construction-plans/parent.json"))
                .arg("--focused-receipt")
                .arg(base.join("refresh.json"))
                .arg("--evidence-root")
                .arg(&base)
                .arg("--output")
                .arg(base.join(format!("{label}.json")))
                .output()
                .unwrap()
        };
        let result = invoke("first");
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let output: Value =
            serde_json::from_slice(&fs::read(base.join("first.json")).unwrap()).unwrap();
        assert_eq!(output["readinessDecision"], "blocked-qualification");
        assert_eq!(output["parentPreserved"], true);
        assert_eq!(output["parentPlanPreserved"], true);
        let table_bytes = fs::read(base.join("case_generation_candidates.jsonl")).unwrap();
        let rows: Vec<Value> = std::str::from_utf8(&table_bytes)
            .unwrap()
            .lines()
            .map(|s| serde_json::from_str(s).unwrap())
            .collect();
        assert_eq!(rows.len(), 2);
        assert!(rows.contains(&parent));
        let child = rows
            .iter()
            .find(|r| r["id"] == output["candidateId"])
            .unwrap();
        assert_eq!(child["lineage"]["parentCandidateSha256"], sha(&parent));
        assert_eq!(
            child["lineage"]["parentKnowledgeCutSha256"],
            parent["knowledgeCutSha256"]
        );
        let child_plan_bytes =
            fs::read(base.join(output["successorPlan"].as_str().unwrap())).unwrap();
        let child_plan: Value = serde_json::from_slice(&child_plan_bytes).unwrap();
        for lane in ["oracleExecution", "wrongVariantCalibration"] {
            assert_eq!(child_plan[lane]["status"], "unqualified");
            assert_eq!(child_plan[lane]["evidence"], json!([]));
        }
        assert_eq!(
            child_plan["runtimeRequirements"][0]["status"],
            "unqualified"
        );
        assert_eq!(child_plan["wrongVariantCalibration"]["executedCount"], 0);
        assert_eq!(
            fs::read(base.join("construction-plans/parent.json")).unwrap(),
            parent_plan_bytes
        );
        assert!(invoke("repeat").status.success());
        assert_eq!(
            fs::read(base.join("case_generation_candidates.jsonl")).unwrap(),
            table_bytes
        );
        assert_eq!(
            fs::read(base.join(output["successorPlan"].as_str().unwrap())).unwrap(),
            child_plan_bytes
        );
        // Simulate interruption after child-plan creation, before candidate append.
        write("case_generation_candidates.jsonl", &parent);
        assert!(invoke("recover-interrupted").status.success());
        assert_eq!(
            fs::read(base.join("case_generation_candidates.jsonl")).unwrap(),
            table_bytes
        );
        assert_eq!(
            fs::read(base.join(output["successorPlan"].as_str().unwrap())).unwrap(),
            child_plan_bytes
        );
        let mut bad = receipt.clone();
        bad["acceptedFactSha256"] = json!("f".repeat(64));
        write("refresh.json", &bad);
        assert!(!invoke("bad").status.success());
        assert!(!base.join("bad.json").exists());
        assert_eq!(
            fs::read(base.join("case_generation_candidates.jsonl")).unwrap(),
            table_bytes
        );
    }
    fs::remove_dir_all(root).unwrap();
}
