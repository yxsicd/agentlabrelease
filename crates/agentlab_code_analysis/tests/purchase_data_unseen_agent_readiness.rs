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

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-unseen-readiness-{}-{}-{}",
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
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

struct Fixture {
    root: PathBuf,
    contract: PathBuf,
    gate: PathBuf,
    publication: PathBuf,
    reexecution: PathBuf,
    reexecution_attestation: PathBuf,
    case_freeze: PathBuf,
    case_freeze_attestation: PathBuf,
    dispatch: PathBuf,
    attestation: PathBuf,
    output: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let root = temp_root();
        let contract = repository().join(
            "release/qualifications/alpha13-payment-feedback-analysis-165bcbd/\
             purchase-data-unseen-agent-cohort-contract.json",
        );
        let contract_value = read(&contract);
        let gate = root.join("gate.json");
        write(
            &gate,
            &json!({
                "schema": "agentlab.purchase_data_integrated_review_gate.v1",
                "status": "independent-dual-review-approved-next-calibration-only",
                "packetSha256": contract_value["packetSha256"],
                "sourceLineage": contract_value["sourceLineage"],
                "semanticCandidateId": contract_value["semanticCandidateId"],
                "runtimeCandidateId": contract_value["runtimeCandidateId"],
                "distinctAuthenticatedReviewerCount": 2,
                "reviewers": [
                    {"role": "semantic", "identity": "github:semantic-reviewer", "verdict": "approve-for-next-calibration-gate"},
                    {"role": "oracle", "identity": "github:oracle-reviewer", "verdict": "approve-for-next-calibration-gate"}
                ],
                "semanticAlignmentVerified": true,
                "independentSourceReviewCompleted": true,
                "independentOracleReviewCompleted": true,
                "allowsExactPatchPublication": true,
                "requiresUpstreamRevisionReexecution": true,
                "allowsUnseenAgentCohortEvaluation": true,
                "allowsCaseContract": false,
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
                "reviewGateSha256": digest(&fs::read(&gate).unwrap()),
                "packetSha256": contract_value["packetSha256"],
                "reviewedCandidateRevision": contract_value["sourceLineage"]["candidateRevision"],
                "reviewedPatchSha256": "1111111111111111111111111111111111111111111111111111111111111111",
                "repository": "example/purchase-data",
                "publishedRevision": "2222222222222222222222222222222222222222",
                "publishedTreeOid": "1212121212121212121212121212121212121212",
                "publishedRevisionContainsExactReviewedPatch": true,
                "reviewGateRunId": 10001,
                "verifiedOnline": true,
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
                "publicationSha256": digest(&fs::read(&publication).unwrap()),
                "publishedRevision": "2222222222222222222222222222222222222222",
                "publishedTreeOid": "1212121212121212121212121212121212121212",
                "repository": "example/purchase-data",
                "semanticPassed": true,
                "ohosTestPassed": true,
                "performancePassed": true,
                "runId": 10002,
                "runAttempt": 1,
                "trustedMainRun": true,
                "semanticEvidenceSha256": "3333333333333333333333333333333333333333333333333333333333333333",
                "ohosTestEvidenceSha256": "4444444444444444444444444444444444444444444444444444444444444444",
                "performanceEvidenceSha256": "5555555555555555555555555555555555555555555555555555555555555555",
                "semanticSourceSetSha256": "abababababababababababababababababababababababababababababababab",
                "runtimeSourceSetSha256": contract_value["sourceLineage"]["runtimeSourceSetSha256"],
                "runtimeArchiveSha256": "c".repeat(64),
                "semanticAnalysisRunId": 10001,
                "environmentIdentity": "hwlinux:emulator:test",
                "workflow": {
                    "repository": "example/agentlabrelease",
                    "path": ".github/workflows/purchase-data-published-revision-reexecution.yml",
                    "sourceRevision": "8989898989898989898989898989898989898989",
                    "sourceRef": "refs/heads/main",
                    "runId": 10002,
                    "runAttempt": 1
                },
                "allowsCaseContract": false,
                "automaticPromotion": false
            }),
        );
        let reexecution_attestation = root.join("reexecution-attestation.json");
        write(
            &reexecution_attestation,
            &json!([{
                "verificationResult": {
                    "signature": {"certificate": {
                        "issuer": "https://token.actions.githubusercontent.com",
                        "sourceRepositoryURI": "https://github.com/example/agentlabrelease",
                        "sourceRepositoryDigest": "8989898989898989898989898989898989898989",
                        "sourceRepositoryRef": "refs/heads/main",
                        "githubWorkflowRepository": "example/agentlabrelease",
                        "githubWorkflowRef": "refs/heads/main",
                        "githubWorkflowSHA": "8989898989898989898989898989898989898989",
                        "subjectAlternativeName": "https://github.com/example/agentlabrelease/.github/workflows/purchase-data-published-revision-reexecution.yml@refs/heads/main",
                        "buildSignerURI": "https://github.com/example/agentlabrelease/.github/workflows/purchase-data-published-revision-reexecution.yml@refs/heads/main",
                        "buildSignerDigest": "8989898989898989898989898989898989898989",
                        "runnerEnvironment": "github-hosted",
                        "runInvocationURI": "https://github.com/example/agentlabrelease/actions/runs/10002/attempts/1"
                    }},
                    "statement": {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "subject": [{"digest": {"sha256": digest(&fs::read(&reexecution).unwrap())}}],
                        "predicate": {"runDetails": {"metadata": {
                            "invocationId": "https://github.com/example/agentlabrelease/actions/runs/10002/attempts/1"
                        }}}
                    }
                }
            }]),
        );
        let case_freeze = root.join("case-freeze.json");
        write(
            &case_freeze,
            &json!({
                "schema": "agentlab.purchase_data_trusted_case_freeze.v1",
                "status": "trusted-held-out-case-frozen",
                "contractSha256": digest(&fs::read(&contract).unwrap()),
                "reexecutionSha256": digest(&fs::read(&reexecution).unwrap()),
                "publishedRevision": "2222222222222222222222222222222222222222",
                "publishedTreeOid": "1212121212121212121212121212121212121212",
                "repository": "example/purchase-data",
                "sourceVisibility": "held-out-public-revision",
                "caseReviewRunId": 12345,
                "caseReviewRunAttempt": 1,
                "caseReviewSourceRevision": "8787878787878787878787878787878787878787",
                "evaluationCaseSha256": "6666666666666666666666666666666666666666666666666666666666666666",
                "sourceSetSha256": "abababababababababababababababababababababababababababababababab",
                "blindCutReceiptSha256": "7777777777777777777777777777777777777777777777777777777777777777",
                "participantManifestSha256": "7878787878787878787878787878787878787878787878787878787878787878",
                "evaluatorManifestSha256": "7979797979797979797979797979797979797979797979797979797979797979",
                "runId": 12346,
                "runAttempt": 1,
                "trustedMainRun": true,
                "workflow": {
                    "repository": "example/agentlabrelease",
                    "path": ".github/workflows/purchase-data-trusted-case-freeze.yml",
                    "sourceRevision": "8686868686868686868686868686868686868686",
                    "sourceRef": "refs/heads/main",
                    "runId": 12346,
                    "runAttempt": 1
                },
                "allowsCaseContract": true,
                "allowsUnseenAgentDispatch": false,
                "automaticPromotion": false,
                "nextGate": "pre-outcome-attested-unseen-agent-dispatch"
            }),
        );
        let case_freeze_attestation = root.join("case-freeze-attestation.json");
        write(
            &case_freeze_attestation,
            &json!([{
                "verificationResult": {
                    "signature": {"certificate": {
                        "issuer": "https://token.actions.githubusercontent.com",
                        "sourceRepositoryURI": "https://github.com/example/agentlabrelease",
                        "sourceRepositoryDigest": "8686868686868686868686868686868686868686",
                        "sourceRepositoryRef": "refs/heads/main",
                        "githubWorkflowRepository": "example/agentlabrelease",
                        "githubWorkflowRef": "refs/heads/main",
                        "githubWorkflowSHA": "8686868686868686868686868686868686868686",
                        "subjectAlternativeName": "https://github.com/example/agentlabrelease/.github/workflows/purchase-data-trusted-case-freeze.yml@refs/heads/main",
                        "buildSignerURI": "https://github.com/example/agentlabrelease/.github/workflows/purchase-data-trusted-case-freeze.yml@refs/heads/main",
                        "buildSignerDigest": "8686868686868686868686868686868686868686",
                        "runnerEnvironment": "github-hosted",
                        "runInvocationURI": "https://github.com/example/agentlabrelease/actions/runs/12346/attempts/1"
                    }},
                    "statement": {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "subject": [{"digest": {"sha256": digest(&fs::read(&case_freeze).unwrap())}}],
                        "predicate": {"runDetails": {"metadata": {
                            "invocationId": "https://github.com/example/agentlabrelease/actions/runs/12346/attempts/1"
                        }}}
                    }
                }
            }]),
        );
        let dispatch = root.join("dispatch.json");
        write(
            &dispatch,
            &json!({
                "schema": "agentlab.participant_experiment_dispatch.v1",
                "status": "attested-plan-gate-frozen-before-assessment",
                "workflow": {
                    "repository": "example/agentlabrelease",
                    "path": ".github/workflows/multi-repo-assessed-campaign.yml",
                    "runId": 23456,
                    "runAttempt": 1
                },
                "caseId": "purchase-data-case",
                "sourceSetSha256": "abababababababababababababababababababababababababababababababab",
                "evaluationCaseSha256": "6666666666666666666666666666666666666666666666666666666666666666",
                "caseReviewRunId": 12345,
                "methodRevision": "9999999999999999999999999999999999999999",
                "providerRoute": "test-provider",
                "trialsPerParticipant": 5,
                "participantProfileCount": 3,
                "participantProfiles": [
                    {"ordinal": 0, "participantId": "weak", "model": "model-a"},
                    {"ordinal": 1, "participantId": "middle", "model": "model-b"},
                    {"ordinal": 2, "participantId": "strong", "model": "model-c"}
                ],
                "executionProtocol": {
                    "schema": "agentlab.participant_execution_protocol_portable.v1",
                    "agentImplementation": "pi",
                    "agentPackage": "@earendil-works/pi-coding-agent",
                    "agentPackageVersion": "1.2.3",
                    "participantAdapter": {"path": "adapter.py", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
                    "participantDriver": {"path": "driver.py", "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
                    "participantPackageLock": {"path": "package-lock.json", "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"},
                    "runtimeDockerfile": {"path": "participant.Dockerfile", "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"},
                    "runtimeBuildScript": {"path": "participant-runtime.sh", "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},
                    "runtimeImageArchive": {
                        "filename": "participant-runtime-image.tar",
                        "byteLength": 1024,
                        "sha256": "1212121212121212121212121212121212121212121212121212121212121212",
                        "imageId": "sha256:1313131313131313131313131313131313131313131313131313131313131313"
                    },
                    "participantManifestSha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                    "promptAuthority": "digest-bound-adapter-driver-and-blind-case-manifest",
                    "sessionPolicy": "fresh-per-attempt-persistent-across-case-stages",
                    "thinkingMode": "off",
                    "reasoningEffort": null,
                    "extensionPolicy": "disabled",
                    "skillsPolicy": "disabled",
                    "contextFilePolicy": "disabled",
                    "turnTimeoutSeconds": 420,
                    "samplingPolicy": "provider-default-stochastic-repeated-trials",
                    "portableRuntimeQualified": true,
                    "crossCampaignProviderReproducibilityQualified": false
                },
                "allowsAssessmentExecution": true,
                "automaticPromotion": false
            }),
        );
        let attestation = root.join("attestation.json");
        write(
            &attestation,
            &json!([{
                "verificationResult": {
                    "signature": {"certificate": {
                        "issuer": "https://token.actions.githubusercontent.com",
                        "sourceRepositoryURI": "https://github.com/example/agentlabrelease",
                        "sourceRepositoryDigest": "9999999999999999999999999999999999999999",
                        "sourceRepositoryRef": "refs/heads/main",
                        "githubWorkflowRepository": "example/agentlabrelease",
                        "githubWorkflowRef": "refs/heads/main",
                        "githubWorkflowSHA": "9999999999999999999999999999999999999999",
                        "subjectAlternativeName": "https://github.com/example/agentlabrelease/.github/workflows/multi-repo-assessed-campaign.yml@refs/heads/main",
                        "buildSignerURI": "https://github.com/example/agentlabrelease/.github/workflows/multi-repo-assessed-campaign.yml@refs/heads/main",
                        "buildSignerDigest": "9999999999999999999999999999999999999999",
                        "runnerEnvironment": "github-hosted",
                        "runInvocationURI": "https://github.com/example/agentlabrelease/actions/runs/23456/attempts/1"
                    }},
                    "statement": {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "subject": [{"digest": {"sha256": digest(&fs::read(&dispatch).unwrap())}}],
                        "predicate": {"runDetails": {"metadata": {
                            "invocationId": "https://github.com/example/agentlabrelease/actions/runs/23456/attempts/1"
                        }}}
                    }
                }
            }]),
        );
        let output = root.join("readiness.json");
        Self {
            root,
            contract,
            gate,
            publication,
            reexecution,
            reexecution_attestation,
            case_freeze,
            case_freeze_attestation,
            dispatch,
            attestation,
            output,
        }
    }

    fn run(&self) -> Output {
        Command::new(env!(
            "CARGO_BIN_EXE_agentlab-purchase-data-unseen-agent-readiness"
        ))
        .args([
            "--contract",
            self.contract.to_str().unwrap(),
            "--review-gate",
            self.gate.to_str().unwrap(),
            "--publication",
            self.publication.to_str().unwrap(),
            "--reexecution",
            self.reexecution.to_str().unwrap(),
            "--reexecution-attestation-verification",
            self.reexecution_attestation.to_str().unwrap(),
            "--case-freeze",
            self.case_freeze.to_str().unwrap(),
            "--case-freeze-attestation-verification",
            self.case_freeze_attestation.to_str().unwrap(),
            "--participant-dispatch",
            self.dispatch.to_str().unwrap(),
            "--dispatch-attestation-verification",
            self.attestation.to_str().unwrap(),
            "--output",
            self.output.to_str().unwrap(),
        ])
        .current_dir(repository())
        .output()
        .unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[test]
fn compiles_exact_evidence_chain_into_operator_gated_dispatch_readiness() {
    let fixture = Fixture::new();
    let result = fixture.run();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value = read(&fixture.output);
    assert_eq!(value["status"], "ready-to-dispatch-unseen-agent-cohort");
    assert_eq!(
        value["publishedRevision"],
        "2222222222222222222222222222222222222222"
    );
    assert_eq!(
        value["currentReadiness"]["independentDualReviewApproved"],
        true
    );
    assert_eq!(
        value["currentReadiness"]["exactPatchPublishedUpstream"],
        true
    );
    assert_eq!(value["currentReadiness"]["publishedRevisionRebound"], true);
    assert_eq!(
        value["currentReadiness"]["trustedFrozenCaseAvailable"],
        true
    );
    assert_eq!(
        value["currentReadiness"]["participantDispatchPredeclaredAndAttested"],
        true
    );
    assert_eq!(
        value["currentReadiness"]["unseenAgentCohortExecuted"],
        false
    );
    assert_eq!(value["currentReadiness"]["readyToDispatch"], true);
    assert_eq!(value["allowsUnseenAgentDispatch"], true);
    assert_eq!(value["automaticDispatch"], false);
    assert_eq!(value["automaticPromotion"], false);
    assert_eq!(value["evidence"].as_object().unwrap().len(), 9);
}

#[test]
fn rejects_non_approved_review_gate() {
    let fixture = Fixture::new();
    let mut gate = read(&fixture.gate);
    gate["status"] = json!("independent-dual-review-deferred");
    write(&fixture.gate, &gate);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("review gate status differs"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_publication_or_reexecution_lineage_drift() {
    let fixture = Fixture::new();
    let mut publication = read(&fixture.publication);
    publication["publishedRevision"] = json!("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    write(&fixture.publication, &publication);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("re-execution publication digest differs")
    );
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_case_or_dispatch_drift() {
    let fixture = Fixture::new();
    let mut dispatch = read(&fixture.dispatch);
    dispatch["caseReviewRunId"] = json!(12346);
    write(&fixture.dispatch, &dispatch);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("participant dispatch case-review run differs"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_attestation_for_another_dispatch() {
    let fixture = Fixture::new();
    let mut attestation = read(&fixture.attestation);
    attestation[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] =
        json!("abababababababababababababababababababababababababababababababab");
    write(&fixture.attestation, &attestation);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("GitHub attestation does not bind the exact trusted workflow identity"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_attestation_for_another_reexecution_receipt() {
    let fixture = Fixture::new();
    let mut attestation = read(&fixture.reexecution_attestation);
    attestation[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] =
        json!("abababababababababababababababababababababababababababababababab");
    write(&fixture.reexecution_attestation, &attestation);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("GitHub attestation does not bind the exact trusted workflow identity"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_attestation_for_another_case_freeze_receipt() {
    let fixture = Fixture::new();
    let mut attestation = read(&fixture.case_freeze_attestation);
    attestation[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] =
        json!("abababababababababababababababababababababababababababababababab");
    write(&fixture.case_freeze_attestation, &attestation);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("GitHub attestation does not bind the exact trusted workflow identity"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_attestation_from_another_workflow_attempt() {
    let fixture = Fixture::new();
    let mut attestation = read(&fixture.attestation);
    attestation[0]["verificationResult"]["statement"]["predicate"]["runDetails"]["metadata"]
        ["invocationId"] =
        json!("https://github.com/example/agentlabrelease/actions/runs/23456/attempts/2");
    write(&fixture.attestation, &attestation);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("GitHub attestation does not bind the exact trusted workflow identity"));
    assert!(!fixture.output.exists());
}

#[test]
fn rejects_cryptographically_verified_but_wrong_certificate_identity() {
    let fixture = Fixture::new();
    let mut attestation = read(&fixture.attestation);
    attestation[0]["verificationResult"]["signature"]["certificate"]["sourceRepositoryRef"] =
        json!("refs/heads/feature");
    write(&fixture.attestation, &attestation);
    let result = fixture.run();
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("GitHub attestation does not bind the exact trusted workflow identity"));
    assert!(!fixture.output.exists());
}
