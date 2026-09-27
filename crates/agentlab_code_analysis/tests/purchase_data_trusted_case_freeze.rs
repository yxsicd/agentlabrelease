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
const REEXECUTION_METHOD: &str = "4444444444444444444444444444444444444444";
const CASE_REVIEW_METHOD: &str = "5555555555555555555555555555555555555555";
const FREEZE_METHOD: &str = "6666666666666666666666666666666666666666";
const SOURCE_SET: &str = "7777777777777777777777777777777777777777777777777777777777777777";

struct Fixture {
    root: PathBuf,
    contract: PathBuf,
    reexecution: PathBuf,
    reexecution_run: PathBuf,
    reexecution_attestation: PathBuf,
    case_review_run: PathBuf,
    case_review_root: PathBuf,
    output: PathBuf,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-trusted-case-freeze-{}-{}-{}",
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

fn attestation(subject: &str, run_id: u64, method: &str, workflow: &str) -> Value {
    let signer = format!("https://github.com/{WORKFLOW_REPOSITORY}/{workflow}@refs/heads/main");
    let invocation =
        format!("https://github.com/{WORKFLOW_REPOSITORY}/actions/runs/{run_id}/attempts/1");
    json!([{"verificationResult": {
        "statement": {
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": [{"digest": {"sha256": subject}}],
            "predicate": {"runDetails": {"metadata": {"invocationId": invocation}}}
        },
        "signature": {"certificate": {
            "issuer": "https://token.actions.githubusercontent.com",
            "sourceRepositoryURI": format!("https://github.com/{WORKFLOW_REPOSITORY}"),
            "sourceRepositoryDigest": method,
            "sourceRepositoryRef": "refs/heads/main",
            "githubWorkflowRepository": WORKFLOW_REPOSITORY,
            "githubWorkflowRef": "refs/heads/main",
            "githubWorkflowSHA": method,
            "subjectAlternativeName": signer,
            "buildSignerURI": signer,
            "buildSignerDigest": method,
            "runnerEnvironment": "github-hosted",
            "runInvocationURI": invocation
        }}
    }}])
}

fn file_row(root: &Path, relative: &str, role: &str) -> Value {
    let bytes = fs::read(root.join(relative)).unwrap();
    json!({
        "path": relative,
        "role": role,
        "sha256": digest(&bytes),
        "bytes": bytes.len()
    })
}

fn inventory_digest(rows: &[Value]) -> String {
    let mut rows = rows.to_vec();
    rows.sort_by(|left, right| left["path"].as_str().cmp(&right["path"].as_str()));
    let mut bytes = serde_json::to_vec(&rows).unwrap();
    bytes.push(b'\n');
    digest(&bytes)
}

fn fixture() -> Fixture {
    let root = temp_root();
    let contract = root.join("contract.json");
    write(
        &contract,
        &json!({
            "schema": "agentlab.purchase_data_unseen_agent_cohort_contract.v1",
            "status": "execution-contract-frozen-prerequisites-pending",
            "automaticPromotion": false
        }),
    );
    let reexecution = root.join("reexecution.json");
    write(
        &reexecution,
        &json!({
            "schema": "agentlab.purchase_data_published_revision_reexecution.v1",
            "status": "published-revision-semantic-ohostest-performance-passed",
            "contractSha256": digest(&fs::read(&contract).unwrap()),
            "publishedRevision": PUBLISHED,
            "publishedTreeOid": TREE,
            "repository": SOURCE_REPOSITORY,
            "semanticPassed": true,
            "ohosTestPassed": true,
            "performancePassed": true,
            "semanticSourceSetSha256": SOURCE_SET,
            "runtimeSourceSetSha256": "8".repeat(64),
            "runId": 1001,
            "runAttempt": 1,
            "trustedMainRun": true,
            "workflow": {
                "repository": WORKFLOW_REPOSITORY,
                "path": ".github/workflows/purchase-data-published-revision-reexecution.yml",
                "sourceRevision": REEXECUTION_METHOD,
                "sourceRef": "refs/heads/main",
                "runId": 1001,
                "runAttempt": 1
            },
            "allowsCaseContract": false,
            "automaticPromotion": false,
            "nextGate": "trusted-held-out-case-freeze"
        }),
    );
    let reexecution_run = root.join("reexecution-run.json");
    write(
        &reexecution_run,
        &source_run(
            1001,
            ".github/workflows/purchase-data-published-revision-reexecution.yml",
            REEXECUTION_METHOD,
        ),
    );
    let reexecution_attestation = root.join("reexecution-attestation.json");
    write(
        &reexecution_attestation,
        &attestation(
            &digest(&fs::read(&reexecution).unwrap()),
            1001,
            REEXECUTION_METHOD,
            ".github/workflows/purchase-data-published-revision-reexecution.yml",
        ),
    );
    let case_review_run = root.join("case-review-run.json");
    write(
        &case_review_run,
        &source_run(
            2001,
            ".github/workflows/multi-repo-case-review.yml",
            CASE_REVIEW_METHOD,
        ),
    );
    let case_review_root = root.join("case-review");
    let case = json!({
        "schema": "agentlab.multi_repo_evaluation_case.v1",
        "id": "purchase-data-held-out-001",
        "status": "frozen-calibrated",
        "title": "Repair the published purchase-data behavior",
        "sourceSetSha256": SOURCE_SET,
        "sources": [
            {"id": "purchase-data", "repository": SOURCE_REPOSITORY, "revision": PUBLISHED},
            {"id": "contracts", "repository": "https://example.invalid/contracts.git", "revision": "9".repeat(40)}
        ],
        "allowedEdits": [{"repositoryId": "purchase-data", "path": "entry/src/main/ets/pages/Index.ets"}],
        "stages": [{"id": "repair", "demand": "Repair the behavior.", "checkIds": ["hidden-check"]}],
        "oracle": {"sha256": "a".repeat(64), "receiptSchema": "oracle.v1"},
        "automaticPromotion": false
    });
    write(&case_review_root.join("evaluation-case.json"), &case);

    let participant_root = case_review_root.join("blind-cut/participant");
    write(
        &participant_root.join("task.json"),
        &json!({"schema": "agentlab.multi_repo_participant_task.v1", "caseId": "purchase-data-held-out-001"}),
    );
    write(
        &participant_root.join("source-bindings.json"),
        &json!({"schema": "agentlab.multi_repo_source_bindings.v1", "sourceSetSha256": SOURCE_SET}),
    );
    let participant_rows = vec![
        file_row(&participant_root, "source-bindings.json", "source"),
        file_row(&participant_root, "task.json", "task"),
    ];
    let participant_manifest = json!({
        "schema": "agentlab.blind_case_participant_bundle.v1",
        "cutId": "purchase-data-held-out-001-blind-v1",
        "caseId": "purchase-data-held-out-001",
        "methodRevision": CASE_REVIEW_METHOD,
        "sourceSetSha256": SOURCE_SET,
        "files": participant_rows,
        "constraints": {"environmentRef": "release-locked-multi-repo-assessment"}
    });
    write(
        &participant_root.join("manifest.json"),
        &participant_manifest,
    );

    let evaluator_root = case_review_root.join("blind-cut/evaluator");
    write(&evaluator_root.join("evaluation-case.json"), &case);
    fs::create_dir_all(evaluator_root.join("reference")).unwrap();
    fs::write(
        evaluator_root.join("oracle.mjs"),
        b"export const hidden = true;\n",
    )
    .unwrap();
    fs::write(
        evaluator_root.join("reference/contracts.ts"),
        b"export const expected = true;\n",
    )
    .unwrap();
    let evaluator_rows = vec![
        file_row(&evaluator_root, "evaluation-case.json", "review"),
        file_row(&evaluator_root, "oracle.mjs", "oracle"),
        file_row(&evaluator_root, "reference/contracts.ts", "reference"),
    ];
    let evaluator_manifest = json!({
        "schema": "agentlab.blind_case_evaluator_bundle.v1",
        "cutId": "purchase-data-held-out-001-blind-v1",
        "caseId": "purchase-data-held-out-001",
        "methodRevision": CASE_REVIEW_METHOD,
        "sourceSetSha256": SOURCE_SET,
        "participantManifestSha256": digest(&fs::read(participant_root.join("manifest.json")).unwrap()),
        "files": evaluator_rows
    });
    write(&evaluator_root.join("manifest.json"), &evaluator_manifest);

    let participant_manifest_sha =
        digest(&fs::read(participant_root.join("manifest.json")).unwrap());
    let evaluator_manifest_sha = digest(&fs::read(evaluator_root.join("manifest.json")).unwrap());
    write(
        &case_review_root.join("blind-cut/cut-receipt.json"),
        &json!({
            "schema": "agentlab.blind_case_cut_receipt.v1",
            "cutId": "purchase-data-held-out-001-blind-v1",
            "caseId": "purchase-data-held-out-001",
            "methodRevision": CASE_REVIEW_METHOD,
            "sourceSetSha256": SOURCE_SET,
            "participantBundle": {
                "manifestSha256": participant_manifest_sha,
                "fileCount": 2,
                "inventorySha256": inventory_digest(participant_manifest["files"].as_array().unwrap())
            },
            "evaluatorBundle": {
                "manifestSha256": evaluator_manifest_sha,
                "fileCount": 3,
                "inventorySha256": inventory_digest(evaluator_manifest["files"].as_array().unwrap())
            },
            "boundary": {
                "physicallySeparatedRoots": true,
                "participantManifestContainsEvaluatorInventory": false,
                "byteIdenticalCrossBundleFiles": false,
                "participantMount": "participant",
                "evaluatorMount": "evaluator",
                "semanticLeakReview": "required"
            },
            "freshness": {
                "sourceVisibility": "held-out-public-revision",
                "cutConstructedAt": "2026-09-27T00:00:00Z",
                "participantAccessBeforeCut": false,
                "modelTrainingExclusionKnown": false,
                "contaminationReview": "review-required",
                "declaredHeldOutAtCut": true,
                "heldOutEvidenceStatus": "declaration-only",
                "eligibleForBlindPilot": true,
                "eligibleForUnseenAgentDiscrimination": false
            },
            "review": {"independent": false, "status": "required"},
            "automaticPromotion": false
        }),
    );
    let output = root.join("case-freeze.json");
    Fixture {
        root,
        contract,
        reexecution,
        reexecution_run,
        reexecution_attestation,
        case_review_run,
        case_review_root,
        output,
    }
}

impl Fixture {
    fn run(&self) -> Output {
        Command::new(env!(
            "CARGO_BIN_EXE_agentlab-purchase-data-trusted-case-freeze"
        ))
        .args([
            "--contract",
            self.contract.to_str().unwrap(),
            "--reexecution",
            self.reexecution.to_str().unwrap(),
            "--reexecution-source-run",
            self.reexecution_run.to_str().unwrap(),
            "--reexecution-attestation-verification",
            self.reexecution_attestation.to_str().unwrap(),
            "--case-review-source-run",
            self.case_review_run.to_str().unwrap(),
            "--case-review-root",
            self.case_review_root.to_str().unwrap(),
            "--workflow-repository",
            WORKFLOW_REPOSITORY,
            "--workflow-source-revision",
            FREEZE_METHOD,
            "--workflow-run-id",
            "3001",
            "--workflow-run-attempt",
            "1",
            "--output",
            self.output.to_str().unwrap(),
        ])
        .output()
        .unwrap()
    }
}

#[test]
fn freezes_exact_published_case_and_physically_separated_blind_cut() {
    let fixture = fixture();
    let result = fixture.run();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&fixture.output);
    assert_eq!(value["status"], "trusted-held-out-case-frozen");
    assert_eq!(value["publishedRevision"], PUBLISHED);
    assert_eq!(value["caseReviewRunId"], 2001);
    assert_eq!(value["sourceSetSha256"], SOURCE_SET);
    assert_eq!(value["allowsCaseContract"], true);
    assert_eq!(value["allowsUnseenAgentDispatch"], false);
    assert_eq!(value["automaticPromotion"], false);
    assert_eq!(value["evidence"].as_object().unwrap().len(), 7);
}

#[test]
fn rejects_case_without_exact_published_revision() {
    let fixture = fixture();
    let case_path = fixture.case_review_root.join("evaluation-case.json");
    let mut case = read(&case_path);
    case["sources"][0]["revision"] = json!("1".repeat(40));
    write(&case_path, &case);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("evaluation case does not contain the exact published source once"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_semantic_source_set_drift() {
    let fixture = fixture();
    let case_path = fixture.case_review_root.join("evaluation-case.json");
    let mut case = read(&case_path);
    case["sourceSetSha256"] = json!("1".repeat(64));
    write(&case_path, &case);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("evaluation case published semantic source set differs"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_tampered_participant_bytes() {
    let fixture = fixture();
    fs::write(
        fixture
            .case_review_root
            .join("blind-cut/participant/task.json"),
        b"tampered\n",
    )
    .unwrap();
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("participant bundle file digest differs")
    );
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_reexecution_attestation_for_another_receipt() {
    let fixture = fixture();
    let mut value = read(&fixture.reexecution_attestation);
    value[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] =
        json!("1".repeat(64));
    write(&fixture.reexecution_attestation, &value);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("GitHub attestation does not bind the exact trusted workflow identity"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_unbound_evaluator_file() {
    let fixture = fixture();
    fs::write(
        fixture
            .case_review_root
            .join("blind-cut/evaluator/secret.txt"),
        b"unbound\n",
    )
    .unwrap();
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("evaluator bundle contains unbound files")
    );
    assert!(!fixture.output.exists());
}
