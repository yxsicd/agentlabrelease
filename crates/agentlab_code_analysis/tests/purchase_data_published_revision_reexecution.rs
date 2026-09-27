use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);
const WORKFLOW_REPOSITORY: &str = "example/agentlabrelease";
const SOURCE_REPOSITORY: &str = "https://example.invalid/purchase-data.git";
const PUBLISHED: &str = "2222222222222222222222222222222222222222";
const TREE: &str = "3333333333333333333333333333333333333333";
const METHOD: &str = "4444444444444444444444444444444444444444";
const SEMANTIC_SET: &str = "5555555555555555555555555555555555555555555555555555555555555555";
const RUNTIME_SET: &str = "6666666666666666666666666666666666666666666666666666666666666666";

struct Fixture {
    root: PathBuf,
    contract: PathBuf,
    publication: PathBuf,
    publication_run: PathBuf,
    publication_attestation: PathBuf,
    semantic_run: PathBuf,
    semantic_root: PathBuf,
    runtime_root: PathBuf,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-published-reexecution-{}-{}-{}",
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

fn write(path: &Path, value: &Value) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn binding(path: &Path, relative: &str) -> Value {
    let bytes = fs::read(path).unwrap();
    json!({"path": relative, "sha256": digest(&bytes), "byteLength": bytes.len()})
}

fn source_run(id: u64, path: &str, head: &str) -> Value {
    json!({
        "id": id,
        "run_attempt": 1,
        "repository": {"full_name": WORKFLOW_REPOSITORY},
        "path": path,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": head,
        "status": "completed",
        "conclusion": "success"
    })
}

fn fixture() -> Fixture {
    let root = temp_root();
    let contract = root.join("contract.json");
    write(
        &contract,
        &json!({
            "schema": "agentlab.purchase_data_unseen_agent_cohort_contract.v1",
            "status": "execution-contract-frozen-prerequisites-pending",
            "sourceLineage": {
                "candidateRevision": "1111111111111111111111111111111111111111",
                "runtimeSourceSetSha256": RUNTIME_SET
            },
            "automaticPromotion": false
        }),
    );
    let publication = root.join("publication.json");
    write(
        &publication,
        &json!({
            "schema": "agentlab.purchase_data_exact_patch_publication.v1",
            "status": "exact-reviewed-patch-published",
            "contractSha256": digest(&fs::read(&contract).unwrap()),
            "reviewedCandidateRevision": "1111111111111111111111111111111111111111",
            "repository": SOURCE_REPOSITORY,
            "publishedRevision": PUBLISHED,
            "publishedTreeOid": TREE,
            "publishedRevisionContainsExactReviewedPatch": true,
            "verifiedOnline": true,
            "automaticPromotion": false
        }),
    );
    let publication_run = root.join("publication-run.json");
    write(
        &publication_run,
        &source_run(
            1001,
            ".github/workflows/purchase-data-exact-patch-publication.yml",
            METHOD,
        ),
    );
    let publication_sha = digest(&fs::read(&publication).unwrap());
    let signer = format!(
        "https://github.com/{WORKFLOW_REPOSITORY}/.github/workflows/purchase-data-exact-patch-publication.yml@refs/heads/main"
    );
    let invocation =
        format!("https://github.com/{WORKFLOW_REPOSITORY}/actions/runs/1001/attempts/1");
    let publication_attestation = root.join("publication-attestation.json");
    write(
        &publication_attestation,
        &json!([{"verificationResult": {
            "statement": {
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": [{"digest": {"sha256": publication_sha}}],
                "predicate": {"runDetails": {"metadata": {"invocationId": invocation}}}
            },
            "signature": {"certificate": {
                "issuer": "https://token.actions.githubusercontent.com",
                "sourceRepositoryURI": format!("https://github.com/{WORKFLOW_REPOSITORY}"),
                "sourceRepositoryDigest": METHOD,
                "sourceRepositoryRef": "refs/heads/main",
                "githubWorkflowRepository": WORKFLOW_REPOSITORY,
                "githubWorkflowRef": "refs/heads/main",
                "githubWorkflowSHA": METHOD,
                "subjectAlternativeName": signer,
                "buildSignerURI": signer,
                "buildSignerDigest": METHOD,
                "runnerEnvironment": "github-hosted",
                "runInvocationURI": invocation
            }}
        }}]),
    );

    let semantic_root = root.join("semantic");
    let spec = semantic_root.join("source-spec.json");
    write(
        &spec,
        &json!({
            "schema": "agentlab.multi_repo_source_spec.v1",
            "sources": [{"id": "purchase-data", "repository": SOURCE_REPOSITORY, "revision": PUBLISHED}],
            "moduleBindings": [],
            "automaticPromotion": false
        }),
    );
    let manifest = semantic_root.join("manifest.json");
    write(
        &manifest,
        &json!({
            "schema": "agentlab.multi_repo_manifest.v1",
            "repositories": [{"id": "purchase-data", "repository": SOURCE_REPOSITORY, "revision": PUBLISHED, "root": "repositories/purchase-data"}],
            "moduleBindings": []
        }),
    );
    let facts = semantic_root.join("analysis/workspace_facts.jsonl");
    fs::create_dir_all(facts.parent().unwrap()).unwrap();
    fs::write(&facts, b"{\"fact\":1}\n").unwrap();
    let unsupported = semantic_root.join("analysis/unsupported_sources.jsonl");
    fs::write(&unsupported, b"").unwrap();
    let difficulty = semantic_root.join("analysis/difficulty_candidates.json");
    write(
        &difficulty,
        &json!({
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": SEMANTIC_SET,
            "sources": [{"id": "purchase-data", "repository": SOURCE_REPOSITORY, "revision": PUBLISHED}],
            "moduleBindings": [],
            "automaticPromotion": false
        }),
    );
    let analysis = semantic_root.join("analysis/multi_repo_analysis.json");
    write(
        &analysis,
        &json!({
            "schema": "agentlab.multi_repo_analysis.v1",
            "manifestSha256": digest(&fs::read(&manifest).unwrap()),
            "difficultyCandidatesSha256": digest(&fs::read(&difficulty).unwrap()),
            "workspaceFactsSha256": digest(&fs::read(&facts).unwrap()),
            "unsupportedSourcesSha256": digest(&fs::read(&unsupported).unwrap()),
            "sourceSetSha256": SEMANTIC_SET,
            "facts": 1,
            "difficultyCandidates": 0,
            "unsupportedSources": 0,
            "automaticPromotion": false
        }),
    );
    let analysis_run = semantic_root.join("analysis-run.json");
    write(
        &analysis_run,
        &json!({
            "schema": "agentlab.multi_repo_analysis_run.v1",
            "methodRevision": METHOD,
            "sourceSetSha256": SEMANTIC_SET,
            "sourceSpecSha256": digest(&fs::read(&spec).unwrap()),
            "manifestSha256": digest(&fs::read(&manifest).unwrap()),
            "analysisReceiptSha256": digest(&fs::read(&analysis).unwrap()),
            "difficultyEvidenceSha256": digest(&fs::read(&difficulty).unwrap()),
            "programFactsSha256": digest(&fs::read(&facts).unwrap()),
            "unsupportedSourcesSha256": digest(&fs::read(&unsupported).unwrap()),
            "automaticPromotion": false
        }),
    );
    let semantic_run = root.join("semantic-run.json");
    write(
        &semantic_run,
        &source_run(1002, ".github/workflows/multi-repo-analysis.yml", METHOD),
    );

    let runtime_root = root.join("runtime");
    fs::create_dir_all(runtime_root.join("ohostest")).unwrap();
    fs::create_dir_all(runtime_root.join("packages")).unwrap();
    let app_hap = runtime_root.join("packages/app.hap");
    let test_hap = runtime_root.join("packages/test.hap");
    fs::write(&app_hap, b"app-hap-bytes").unwrap();
    fs::write(&test_hap, b"test-hap-bytes").unwrap();
    let packages = json!({
        "app": {"path": "app.hap", "sha256": digest(b"app-hap-bytes"), "byteLength": 13},
        "test": {"path": "test.hap", "sha256": digest(b"test-hap-bytes"), "byteLength": 14}
    });
    let build = runtime_root.join("ohostest/build-receipt.json");
    write(
        &build,
        &json!({
            "schema": "agentlab.harmony_standard_test_source_build_receipt.v1",
            "status": "passed", "passed": true,
            "sourceSetSha256": RUNTIME_SET,
            "projectTreeSha256": "9".repeat(64),
            "packages": packages,
            "automaticPromotion": false
        }),
    );
    let execution = runtime_root.join("ohostest/execution-receipt.json");
    write(
        &execution,
        &json!({
            "schema": "agentlab.harmony_standard_test_execution_receipt.v1",
            "status": "passed", "passed": true,
            "sourceSetSha256": RUNTIME_SET,
            "projectTreeSha256": "9".repeat(64),
            "packages": packages,
            "automaticPromotion": false
        }),
    );
    let source_test = runtime_root.join("ohostest/source-test-receipt.json");
    write(
        &source_test,
        &json!({
            "schema": "agentlab.harmony_source_standard_test_receipt.v1",
            "status": "passed", "passed": true,
            "sourceSetSha256": RUNTIME_SET,
            "projectTreeSha256": "9".repeat(64),
            "framework": "instrument-test-ohosTest-hypium",
            "buildReceipt": binding(&build, "build-receipt.json"),
            "executionReceipt": binding(&execution, "execution-receipt.json"),
            "packages": packages,
            "automaticPromotion": false
        }),
    );
    let performance = runtime_root.join("performance-qualification.json");
    write(
        &performance,
        &json!({
            "schema": "agentlab.purchase_data_case_performance_qualification.v1",
            "status": "case-bound-reference-baseline-meaningful-wrong-performance-calibrated",
            "candidateRevision": PUBLISHED,
            "environmentIdentity": "hwlinux:emulator:test",
            "functionalMatrixVerified": true,
            "performanceMatrixVerified": true,
            "performanceCalibrated": true,
            "distinctBaselineReferenceWrongCaseCalibrationComplete": true,
            "coverage": {"roleCount": 3, "coldRunCount": 6, "functionalVerdictCount": 288, "profileSampleCount": 288},
            "automaticPromotion": false
        }),
    );
    write(
        &runtime_root.join("bundle-manifest.json"),
        &json!({
            "schema": "agentlab.purchase_data_published_revision_runtime_bundle.v1",
            "repository": SOURCE_REPOSITORY,
            "publishedRevision": PUBLISHED,
            "publishedTreeOid": TREE,
            "sourceSetSha256": RUNTIME_SET,
            "environmentIdentity": "hwlinux:emulator:test",
            "ohosTestReceipt": binding(&source_test, "ohostest/source-test-receipt.json"),
            "packages": {
                "app": binding(&app_hap, "packages/app.hap"),
                "test": binding(&test_hap, "packages/test.hap")
            },
            "performanceQualification": binding(&performance, "performance-qualification.json"),
            "automaticPromotion": false
        }),
    );
    Fixture {
        root,
        contract,
        publication,
        publication_run,
        publication_attestation,
        semantic_run,
        semantic_root,
        runtime_root,
    }
}

fn run(fixture: &Fixture, output: &Path) -> Output {
    Command::new(env!(
        "CARGO_BIN_EXE_agentlab-purchase-data-published-revision-reexecution"
    ))
    .args([
        "--contract",
        fixture.contract.to_str().unwrap(),
        "--publication",
        fixture.publication.to_str().unwrap(),
        "--publication-source-run",
        fixture.publication_run.to_str().unwrap(),
        "--publication-attestation-verification",
        fixture.publication_attestation.to_str().unwrap(),
        "--semantic-source-run",
        fixture.semantic_run.to_str().unwrap(),
        "--semantic-root",
        fixture.semantic_root.to_str().unwrap(),
        "--runtime-root",
        fixture.runtime_root.to_str().unwrap(),
        "--runtime-archive-sha256",
        &"a".repeat(64),
        "--workflow-repository",
        WORKFLOW_REPOSITORY,
        "--workflow-source-revision",
        METHOD,
        "--workflow-run-id",
        "1003",
        "--workflow-run-attempt",
        "2",
        "--output",
        output.to_str().unwrap(),
    ])
    .output()
    .unwrap()
}

#[test]
fn compiles_exact_semantic_ohostest_and_performance_evidence() {
    let fixture = fixture();
    let output = fixture.root.join("reexecution.json");
    let result = run(&fixture, &output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&output);
    assert_eq!(value["publishedRevision"], PUBLISHED);
    assert_eq!(value["semanticPassed"], true);
    assert_eq!(value["ohosTestPassed"], true);
    assert_eq!(value["performancePassed"], true);
    assert_eq!(value["runId"], 1003);
    assert_eq!(value["runAttempt"], 2);
    assert_eq!(value["automaticPromotion"], false);
}

#[test]
fn rejects_semantic_analysis_of_a_different_revision() {
    let fixture = fixture();
    let spec = fixture.semantic_root.join("source-spec.json");
    let mut value = read(&spec);
    value["sources"][0]["revision"] = json!("f".repeat(40));
    write(&spec, &value);
    let result = run(&fixture, &fixture.root.join("reexecution.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("exact published source once"));
}

#[test]
fn rejects_failed_ohostest_execution() {
    let fixture = fixture();
    let execution = fixture.runtime_root.join("ohostest/execution-receipt.json");
    let mut value = read(&execution);
    value["status"] = json!("failed");
    value["passed"] = json!(false);
    write(&execution, &value);
    let result = run(&fixture, &fixture.root.join("reexecution.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("execution receipt digest differs"));
}

#[test]
fn rejects_performance_evidence_for_a_different_revision() {
    let fixture = fixture();
    let performance = fixture.runtime_root.join("performance-qualification.json");
    let mut value = read(&performance);
    value["candidateRevision"] = json!("f".repeat(40));
    write(&performance, &value);
    let manifest = fixture.runtime_root.join("bundle-manifest.json");
    let mut bundle = read(&manifest);
    bundle["performanceQualification"] = binding(&performance, "performance-qualification.json");
    write(&manifest, &bundle);
    let result = run(&fixture, &fixture.root.join("reexecution.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("performance qualification revision differs"));
}

#[test]
fn rejects_publication_attestation_from_a_self_hosted_runner() {
    let fixture = fixture();
    let mut value = read(&fixture.publication_attestation);
    value[0]["verificationResult"]["signature"]["certificate"]["runnerEnvironment"] =
        json!("self-hosted");
    write(&fixture.publication_attestation, &value);
    let result = run(&fixture, &fixture.root.join("reexecution.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("trusted workflow identity"));
}

#[test]
fn rejects_runtime_binding_that_escapes_the_bundle() {
    let fixture = fixture();
    let manifest = fixture.runtime_root.join("bundle-manifest.json");
    let mut value = read(&manifest);
    value["ohosTestReceipt"]["path"] = json!("../outside.json");
    write(&manifest, &value);
    let result = run(&fixture, &fixture.root.join("reexecution.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("path is invalid"));
}

#[test]
fn rejects_runtime_package_bytes_that_differ_from_the_receipt() {
    let fixture = fixture();
    fs::write(fixture.runtime_root.join("packages/app.hap"), b"tampered").unwrap();
    let result = run(&fixture, &fixture.root.join("reexecution.json"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("runtime app package digest differs"));
}
