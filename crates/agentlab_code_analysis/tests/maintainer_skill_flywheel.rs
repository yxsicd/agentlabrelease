use agentlab_code_analysis::{digest, maintainer_skill_flywheel::assess};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-maintainer-skill-flywheel-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}

fn jsonl(path: &Path, rows: &[Value]) {
    let text = rows
        .iter()
        .map(|row| serde_json::to_string(row).unwrap() + "\n")
        .collect::<String>();
    fs::write(path, text).unwrap();
}

fn scope(id: &str, repository_id: &str) -> Value {
    json!({
        "schema":"agentlab.maintainer_scope_skill.v1",
        "id":id,
        "skillLayer":"instance",
        "stage":"repository-scope",
        "ownershipPlane":"target-operations",
        "assetClass":"reusable-knowledge",
        "status":"source-supported",
        "repositoryId":repository_id,
        "repository":format!("https://example.invalid/{repository_id}.git"),
        "sourceRevision":"1".repeat(40),
        "sourceTreeOid":"2".repeat(40),
        "strategy":"generic-source-boundary",
        "kind":"source-component",
        "pathBoundary":"src",
        "responsibility":"Maintain the source component and its external contract.",
        "documentedTitle":null,
        "documentedPurpose":null,
        "trackedFileCount":1,
        "sourceFileCount":1,
        "codeLineCount":10,
        "testFileCount":0,
        "languages":{"generic":1},
        "externalDependencyCount":0,
        "externalDependencies":[],
        "buildEntrypoints":[],
        "testEntrypoints":[],
        "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}],
        "coverage":"all tracked files under this leaf boundary are assigned exactly once",
        "automaticPromotion":false
    })
}

fn complete_fact(id: &str, repository_id: &str, skill_id: &str) -> Value {
    json!({
        "id":id,
        "kind":"semantic-contract",
        "repositoryId":repository_id,
        "sourceRevision":"1".repeat(40),
        "scopeSkillIds":[skill_id],
        "dimensions":["responsibility","boundary","relations","behavior","operation"],
        "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}]
    })
}

#[test]
fn generic_evidence_rounds_advance_arbitrary_repositories_without_name_rules() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(
        &scopes,
        &[
            scope("skill-scope-alpha-src", "alpha-library"),
            scope("skill-scope-beta-src", "beta-service"),
        ],
    );

    let first = assess(&scopes, None, 1, None).unwrap();
    assert_eq!(first["decision"], "continue");
    assert_eq!(first["totals"]["structuralReadyCount"], 2);
    assert_eq!(first["totals"]["programBoundCount"], 0);
    assert_eq!(first["totals"]["semanticReadyCount"], 0);
    assert_eq!(first["totals"]["maintenanceReadyCount"], 0);

    jsonl(
        &facts,
        &[
            complete_fact(
                "fact-alpha-contract",
                "alpha-library",
                "skill-scope-alpha-src",
            ),
            complete_fact("fact-beta-contract", "beta-service", "skill-scope-beta-src"),
        ],
    );
    let first_bytes = serde_json::to_vec_pretty(&first).unwrap();
    let parent = digest(&first_bytes);
    let second = assess(&scopes, Some(&facts), 2, Some(&parent)).unwrap();
    assert_eq!(second["decision"], "ready");
    assert_eq!(second["totals"]["programBoundCount"], 2);
    assert_eq!(second["totals"]["semanticReadyCount"], 2);
    assert_eq!(second["totals"]["maintenanceReadyCount"], 2);
    assert!(second["repositories"]
        .as_array()
        .unwrap()
        .iter()
        .all(|repository| repository["readyForCaseGeneration"] == true));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn explicit_fact_binding_cannot_name_a_missing_or_cross_repository_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("skill-scope-alpha-src", "alpha-library")]);
    jsonl(
        &facts,
        &[complete_fact(
            "fact-beta-contract",
            "beta-service",
            "skill-scope-alpha-src",
        )],
    );
    let error = assess(&scopes, Some(&facts), 1, None).unwrap_err();
    assert!(error.contains("crosses repository boundary"));
    fs::remove_dir_all(root).unwrap();
}
