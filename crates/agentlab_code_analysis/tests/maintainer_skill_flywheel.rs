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

fn rows_from_file(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
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
fn stale_or_missing_source_identity_cannot_advance_any_dimension() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    for revision in [json!("9".repeat(40)), Value::Null, json!("main")] {
        let mut fact = complete_fact("fact", "arbitrary-repository", "scope");
        fact["sourceRevision"] = revision;
        jsonl(&facts, &[fact]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["totals"]["programBoundCount"], 0);
        assert_eq!(report["totals"]["semanticReadyCount"], 0);
        assert_eq!(report["totals"]["maintenanceReadyCount"], 0);
        assert_eq!(report["skills"][0]["provenDimensions"], json!([]));
        assert_eq!(
            report["skills"][0]["rejectedEvidenceBindings"][0]["reason"],
            "source-revision-mismatch"
        );
        assert_eq!(report["gapCounts"]["MS-EVIDENCE-IDENTITY-MISMATCH"], 1);
    }
    jsonl(
        &facts,
        &[complete_fact("fact", "arbitrary-repository", "scope")],
    );
    let refreshed = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(refreshed["decision"], "ready");
    assert_eq!(
        refreshed["skills"][0]["rejectedEvidenceBindings"],
        json!([])
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn inherited_cross_repository_or_stale_facts_are_not_semantic_proof() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    let mut anchor = complete_fact("anchor", "arbitrary-repository", "scope");
    anchor["dimensions"] = json!(["boundary"]);
    for (repository, revision) in [
        ("different-repository", "1".repeat(40)),
        ("arbitrary-repository", "9".repeat(40)),
    ] {
        let mut inherited = complete_fact("inherited", repository, "scope");
        inherited["sourceRevision"] = json!(revision);
        inherited["scopeSkillIds"] = json!([]);
        inherited["evidence"] = json!([]);
        inherited["evidenceFactIds"] = json!(["anchor"]);
        jsonl(&facts, &[anchor.clone(), inherited]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["totals"]["semanticReadyCount"], 0);
        assert_eq!(
            report["skills"][0]["evidenceBindings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            report["skills"][0]["rejectedEvidenceBindings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn implicit_operation_binding_never_qualifies_a_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    let mut semantic = complete_fact("semantic", "arbitrary-repository", "scope");
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    for inherit in [false, true] {
        let mut operation = complete_fact("operation", "arbitrary-repository", "scope");
        operation["dimensions"] = json!(["operation"]);
        operation["scopeSkillIds"] = json!([]);
        if inherit {
            operation["evidence"] = json!([]);
            operation["evidenceFactIds"] = json!(["semantic"]);
        }
        jsonl(&facts, &[semantic.clone(), operation.clone()]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["skills"][0]["maturity"], "L2-semantic-ready");
        let binding = report["skills"][0]["evidenceBindings"]
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["factId"] == "operation")
            .unwrap();
        assert_eq!(binding["dimensions"], json!([]));
        operation["scopeSkillIds"] = json!(["scope"]);
        jsonl(&facts, &[semantic.clone(), operation]);
        let qualified = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(qualified["skills"][0]["maturity"], "L3-maintenance-ready");
    }
    fs::remove_dir_all(root).unwrap();
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
fn operation_maturity_requires_explicit_revision_bound_dimension() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("skill-scope-alpha-src", "alpha-library")]);
    jsonl(
        &facts,
        &[
            json!({
                "id":"fact-alpha-semantic",
                "kind":"semantic-contract",
                "repositoryId":"alpha-library",
                "sourceRevision":"1".repeat(40),
                "scopeSkillIds":["skill-scope-alpha-src"],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}]
            }),
            json!({
                "id":"fact-alpha-blocked-build-preflight",
                "kind":"build-test-entrypoint",
                "repositoryId":"alpha-library",
                "sourceRevision":"1".repeat(40),
                "scopeSkillIds":["skill-scope-alpha-src"],
                "evidence":[{"path":"qualification.json","sha256":"4".repeat(64)}]
            }),
        ],
    );
    let blocked = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(blocked["totals"]["semanticReadyCount"], 1);
    assert_eq!(blocked["totals"]["maintenanceReadyCount"], 0);
    assert_eq!(blocked["skills"][0]["maturity"], "L2-semantic-ready");
    assert!(blocked["skills"][0]["gaps"]
        .as_array()
        .unwrap()
        .iter()
        .any(|gap| gap["code"] == "MS-OPERATION-EVIDENCE-MISSING"));

    let mut rows = rows_from_file(&facts);
    rows.push(json!({
        "id":"verification-alpha-runtime",
        "kind":"runtime-verification",
        "repositoryId":"alpha-library",
        "sourceRevision":"1".repeat(40),
        "scopeSkillIds":["skill-scope-alpha-src"],
        "dimensions":["operation"],
        "evidence":[{"path":"qualified-runtime.json","sha256":"5".repeat(64)}]
    }));
    jsonl(&facts, &rows);
    let qualified = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(qualified["totals"]["maintenanceReadyCount"], 1);
    assert_eq!(qualified["skills"][0]["maturity"], "L3-maintenance-ready");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn composite_selectors_bind_exact_owned_paths_and_reject_shared_anchor_siblings() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let mut one = scope("skill-scope-arbitrary-one", "arbitrary");
    one["ownershipSelectors"] = json!([
        {"type":"prefix","path":"src/one"},
        {"type":"files","paths":["src/root.generic"]}
    ]);
    one["evidence"] = json!([{"path":"src/one/main.generic","gitBlobOid":"3".repeat(40)}]);
    let mut two = scope("skill-scope-arbitrary-two", "arbitrary");
    two["ownershipSelectors"] = json!([{"type":"prefix","path":"src/two"}]);
    two["evidence"] = json!([{"path":"src/two/main.generic","gitBlobOid":"4".repeat(40)}]);
    jsonl(&scopes, &[one, two]);
    jsonl(
        &facts,
        &[
            json!({
                "id":"fact-one", "kind":"semantic-contract", "repositoryId":"arbitrary",
                "sourceRevision":"1".repeat(40), "scopeSkillIds":[],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/root.generic","gitBlobOid":"5".repeat(40)}]
            }),
            json!({
                "id":"fact-two", "kind":"semantic-contract", "repositoryId":"arbitrary",
                "sourceRevision":"1".repeat(40), "scopeSkillIds":[],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/two/main.generic","gitBlobOid":"4".repeat(40)}]
            }),
        ],
    );
    let assessment = assess(&scopes, Some(&facts), 1, None).unwrap();
    let rows = assessment["skills"].as_array().unwrap();
    let first = rows
        .iter()
        .find(|row| row["skillId"] == "skill-scope-arbitrary-one")
        .unwrap();
    let second = rows
        .iter()
        .find(|row| row["skillId"] == "skill-scope-arbitrary-two")
        .unwrap();
    assert_eq!(first["checks"]["programEvidenceBound"], true);
    assert_eq!(second["checks"]["programEvidenceBound"], true);
    assert_eq!(first["evidenceBindings"][0]["factId"], "fact-one");
    assert_eq!(second["evidenceBindings"][0]["factId"], "fact-two");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn legacy_virtual_boundaries_retain_v1_identity_compatibility() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let mut legacy = scope("skill-scope-arbitrary-support", "arbitrary");
    legacy["pathBoundary"] = json!("src/_support");
    legacy["evidence"] = json!([{
        "path":"src/build-profile.json5", "gitBlobOid":"3".repeat(40)
    }]);
    jsonl(&scopes, &[legacy]);
    let assessment = assess(&scopes, None, 1, None).unwrap();
    assert_eq!(assessment["totals"]["structuralReadyCount"], 1);
    assert_eq!(assessment["skills"][0]["checks"]["identityReady"], true);
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
