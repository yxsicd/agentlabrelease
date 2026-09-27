use agentlab_code_analysis::{
    digest, validate_github_actions_attestation, GitHubActionsAttestationIdentity,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};

const CONTRACT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_cohort_contract.v1";
const GATE_SCHEMA: &str = "agentlab.purchase_data_integrated_review_gate.v1";
const PUBLICATION_SCHEMA: &str = "agentlab.purchase_data_exact_patch_publication.v1";
const REEXECUTION_SCHEMA: &str = "agentlab.purchase_data_published_revision_reexecution.v1";
const REEXECUTION_WORKFLOW: &str =
    ".github/workflows/purchase-data-published-revision-reexecution.yml";
const CASE_FREEZE_SCHEMA: &str = "agentlab.purchase_data_trusted_case_freeze.v1";
const DISPATCH_SCHEMA: &str = "agentlab.participant_experiment_dispatch.v1";
const DISPATCH_WORKFLOW: &str = ".github/workflows/multi-repo-assessed-campaign.yml";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_dispatch_readiness.v1";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

struct RawInput {
    bytes: Vec<u8>,
    value: Value,
}

impl RawInput {
    fn load(path: &Path, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("cannot parse {label}: {error}"))?;
        Ok(Self { bytes, value })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }
}

impl Input {
    fn load(path: &Path, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("cannot parse {label}: {error}"))?;
        if !value.is_object() {
            return Err(format!("{label} must be a JSON object"));
        }
        Ok(Self { bytes, value })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }
}

fn string<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| format!("{label} {key} is absent"))
}

fn same(actual: &str, expected: &str, label: &str) -> Result<(), String> {
    if actual != expected {
        return Err(format!("{label} differs"));
    }
    Ok(())
}

fn exact_bool(value: &Value, key: &str, expected: bool, label: &str) -> Result<(), String> {
    if value[key].as_bool() != Some(expected) {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}

fn valid_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn sha<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    let value = string(value, key, label)?;
    if !valid_hex(value, 64) {
        return Err(format!("{label} {key} is not a lowercase SHA-256"));
    }
    Ok(value)
}

fn revision<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    let value = string(value, key, label)?;
    if !valid_hex(value, 40) {
        return Err(format!("{label} {key} is not an exact lowercase revision"));
    }
    Ok(value)
}

fn bind(input: &Input) -> Value {
    json!({"sha256": input.sha256(), "byteLength": input.bytes.len()})
}

fn validate_contract(contract: &Input) -> Result<(), String> {
    same(
        string(&contract.value, "schema", "contract")?,
        CONTRACT_SCHEMA,
        "contract schema",
    )?;
    same(
        string(&contract.value, "status", "contract")?,
        "execution-contract-frozen-prerequisites-pending",
        "contract status",
    )?;
    sha(&contract.value, "packetSha256", "contract")?;
    for key in ["analysisSourceSetSha256", "runtimeSourceSetSha256"] {
        sha(
            &contract.value["sourceLineage"],
            key,
            "contract source lineage",
        )?;
    }
    for key in ["baseRevision", "candidateRevision"] {
        revision(
            &contract.value["sourceLineage"],
            key,
            "contract source lineage",
        )?;
    }
    for key in [
        "independentDualReviewApproved",
        "exactPatchPublishedUpstream",
        "publishedRevisionRebound",
        "trustedFrozenCaseAvailable",
        "unseenAgentCohortExecuted",
        "harmonyAttemptFeedbackExecuted",
        "readyToDispatch",
    ] {
        exact_bool(
            &contract.value["currentReadiness"],
            key,
            false,
            "contract readiness",
        )?;
    }
    exact_bool(&contract.value, "allowsCaseContract", false, "contract")?;
    exact_bool(&contract.value, "automaticPromotion", false, "contract")
}

fn validate_gate(contract: &Input, gate: &Input) -> Result<(), String> {
    same(
        string(&gate.value, "schema", "review gate")?,
        GATE_SCHEMA,
        "review gate schema",
    )?;
    same(
        string(&gate.value, "status", "review gate")?,
        "independent-dual-review-approved-next-calibration-only",
        "review gate status",
    )?;
    same(
        sha(&gate.value, "packetSha256", "review gate")?,
        sha(&contract.value, "packetSha256", "contract")?,
        "review gate packet digest",
    )?;
    if gate.value["sourceLineage"] != contract.value["sourceLineage"] {
        return Err("review gate source lineage differs".into());
    }
    for key in ["semanticCandidateId", "runtimeCandidateId"] {
        same(
            string(&gate.value, key, "review gate")?,
            string(&contract.value, key, "contract")?,
            &format!("review gate {key}"),
        )?;
    }
    if gate.value["distinctAuthenticatedReviewerCount"].as_u64() != Some(2) {
        return Err("review gate distinct authenticated reviewer count differs".into());
    }
    let reviewers = gate.value["reviewers"]
        .as_array()
        .filter(|rows| rows.len() == 2)
        .ok_or_else(|| "review gate must contain exactly two reviewers".to_owned())?;
    let mut identities = std::collections::BTreeSet::new();
    for (reviewer, role) in reviewers.iter().zip(["semantic", "oracle"]) {
        same(
            string(reviewer, "role", "review gate reviewer")?,
            role,
            "review gate reviewer role",
        )?;
        let identity = string(reviewer, "identity", "review gate reviewer")?;
        if !identity.starts_with("github:") || !identities.insert(identity.to_ascii_lowercase()) {
            return Err("review gate reviewer identity is invalid or duplicated".into());
        }
        same(
            string(reviewer, "verdict", "review gate reviewer")?,
            "approve-for-next-calibration-gate",
            "review gate reviewer verdict",
        )?;
    }
    for key in [
        "semanticAlignmentVerified",
        "independentSourceReviewCompleted",
        "independentOracleReviewCompleted",
        "allowsExactPatchPublication",
        "requiresUpstreamRevisionReexecution",
        "allowsUnseenAgentCohortEvaluation",
    ] {
        exact_bool(&gate.value, key, true, "review gate")?;
    }
    exact_bool(&gate.value, "allowsCaseContract", false, "review gate")?;
    exact_bool(&gate.value, "automaticPromotion", false, "review gate")
}

fn validate_publication(
    contract: &Input,
    gate: &Input,
    publication: &Input,
) -> Result<String, String> {
    same(
        string(&publication.value, "schema", "publication")?,
        PUBLICATION_SCHEMA,
        "publication schema",
    )?;
    same(
        string(&publication.value, "status", "publication")?,
        "exact-reviewed-patch-published",
        "publication status",
    )?;
    same(
        sha(&publication.value, "contractSha256", "publication")?,
        &contract.sha256(),
        "publication contract digest",
    )?;
    same(
        sha(&publication.value, "reviewGateSha256", "publication")?,
        &gate.sha256(),
        "publication review gate digest",
    )?;
    same(
        sha(&publication.value, "packetSha256", "publication")?,
        sha(&contract.value, "packetSha256", "contract")?,
        "publication packet digest",
    )?;
    same(
        revision(
            &publication.value,
            "reviewedCandidateRevision",
            "publication",
        )?,
        revision(
            &contract.value["sourceLineage"],
            "candidateRevision",
            "contract source lineage",
        )?,
        "publication reviewed candidate revision",
    )?;
    sha(&publication.value, "reviewedPatchSha256", "publication")?;
    string(&publication.value, "repository", "publication")?;
    let published = revision(&publication.value, "publishedRevision", "publication")?.to_owned();
    exact_bool(
        &publication.value,
        "publishedRevisionContainsExactReviewedPatch",
        true,
        "publication",
    )?;
    exact_bool(&publication.value, "verifiedOnline", true, "publication")?;
    if publication.value["reviewGateRunId"]
        .as_u64()
        .filter(|id| *id > 0)
        .is_none()
    {
        return Err("publication reviewGateRunId is invalid".into());
    }
    exact_bool(
        &publication.value,
        "automaticPromotion",
        false,
        "publication",
    )?;
    Ok(published)
}

fn validate_reexecution(
    contract: &Input,
    publication: &Input,
    reexecution: &Input,
    published: &str,
) -> Result<(u64, u64), String> {
    same(
        string(&reexecution.value, "schema", "re-execution")?,
        REEXECUTION_SCHEMA,
        "re-execution schema",
    )?;
    same(
        string(&reexecution.value, "status", "re-execution")?,
        "published-revision-semantic-ohostest-performance-passed",
        "re-execution status",
    )?;
    same(
        sha(&reexecution.value, "contractSha256", "re-execution")?,
        &contract.sha256(),
        "re-execution contract digest",
    )?;
    same(
        sha(&reexecution.value, "publicationSha256", "re-execution")?,
        &publication.sha256(),
        "re-execution publication digest",
    )?;
    same(
        revision(&reexecution.value, "publishedRevision", "re-execution")?,
        published,
        "re-execution published revision",
    )?;
    same(
        revision(&reexecution.value, "publishedTreeOid", "re-execution")?,
        revision(&publication.value, "publishedTreeOid", "publication")?,
        "re-execution published tree",
    )?;
    same(
        string(&reexecution.value, "repository", "re-execution")?,
        string(&publication.value, "repository", "publication")?,
        "re-execution repository",
    )?;
    for key in ["semanticPassed", "ohosTestPassed", "performancePassed"] {
        exact_bool(&reexecution.value, key, true, "re-execution")?;
    }
    exact_bool(&reexecution.value, "trustedMainRun", true, "re-execution")?;
    let run_id = reexecution.value["runId"]
        .as_u64()
        .filter(|id| *id > 0)
        .ok_or_else(|| "re-execution runId is invalid".to_owned())?;
    let run_attempt = reexecution.value["runAttempt"]
        .as_u64()
        .filter(|id| *id > 0)
        .ok_or_else(|| "re-execution runAttempt is invalid".to_owned())?;
    for key in [
        "semanticEvidenceSha256",
        "ohosTestEvidenceSha256",
        "performanceEvidenceSha256",
        "semanticSourceSetSha256",
        "runtimeSourceSetSha256",
        "runtimeArchiveSha256",
    ] {
        sha(&reexecution.value, key, "re-execution")?;
    }
    same(
        sha(&reexecution.value, "runtimeSourceSetSha256", "re-execution")?,
        sha(
            &contract.value["sourceLineage"],
            "runtimeSourceSetSha256",
            "contract source lineage",
        )?,
        "re-execution runtime source set",
    )?;
    if reexecution.value["semanticAnalysisRunId"]
        .as_u64()
        .filter(|id| *id > 0)
        .is_none()
    {
        return Err("re-execution semanticAnalysisRunId is invalid".into());
    }
    string(&reexecution.value, "environmentIdentity", "re-execution")?;
    let workflow = &reexecution.value["workflow"];
    string(workflow, "repository", "re-execution workflow")?;
    same(
        string(workflow, "path", "re-execution workflow")?,
        REEXECUTION_WORKFLOW,
        "re-execution workflow path",
    )?;
    same(
        string(workflow, "sourceRef", "re-execution workflow")?,
        "refs/heads/main",
        "re-execution workflow source ref",
    )?;
    revision(workflow, "sourceRevision", "re-execution workflow")?;
    if workflow["runId"].as_u64() != Some(run_id)
        || workflow["runAttempt"].as_u64() != Some(run_attempt)
    {
        return Err("re-execution workflow invocation differs".into());
    }
    exact_bool(
        &reexecution.value,
        "allowsCaseContract",
        false,
        "re-execution",
    )?;
    exact_bool(
        &reexecution.value,
        "automaticPromotion",
        false,
        "re-execution",
    )?;
    Ok((run_id, run_attempt))
}

fn validate_reexecution_attestation(
    reexecution: &Input,
    attestation: &RawInput,
    run_id: u64,
    run_attempt: u64,
) -> Result<(), String> {
    validate_github_actions_attestation(
        &attestation.value,
        &GitHubActionsAttestationIdentity {
            repository: string(
                &reexecution.value["workflow"],
                "repository",
                "re-execution workflow",
            )?,
            workflow_path: REEXECUTION_WORKFLOW,
            source_digest: revision(
                &reexecution.value["workflow"],
                "sourceRevision",
                "re-execution workflow",
            )?,
            source_ref: "refs/heads/main",
            run_id,
            run_attempt,
            subject_sha256: &reexecution.sha256(),
        },
    )
}

fn validate_case_freeze(
    reexecution: &Input,
    case_freeze: &Input,
    published: &str,
) -> Result<(u64, String, String), String> {
    same(
        string(&case_freeze.value, "schema", "case freeze")?,
        CASE_FREEZE_SCHEMA,
        "case freeze schema",
    )?;
    same(
        string(&case_freeze.value, "status", "case freeze")?,
        "trusted-held-out-case-frozen",
        "case freeze status",
    )?;
    same(
        sha(&case_freeze.value, "reexecutionSha256", "case freeze")?,
        &reexecution.sha256(),
        "case freeze re-execution digest",
    )?;
    same(
        revision(&case_freeze.value, "publishedRevision", "case freeze")?,
        published,
        "case freeze published revision",
    )?;
    same(
        string(&case_freeze.value, "sourceVisibility", "case freeze")?,
        "held-out-public-revision",
        "case freeze source visibility",
    )?;
    let run = case_freeze.value["caseReviewRunId"]
        .as_u64()
        .filter(|run| *run > 0)
        .ok_or_else(|| "case freeze caseReviewRunId is invalid".to_owned())?;
    let case_sha = sha(&case_freeze.value, "evaluationCaseSha256", "case freeze")?.to_owned();
    let source_set = sha(&case_freeze.value, "sourceSetSha256", "case freeze")?.to_owned();
    sha(&case_freeze.value, "blindCutReceiptSha256", "case freeze")?;
    exact_bool(&case_freeze.value, "trustedMainRun", true, "case freeze")?;
    exact_bool(
        &case_freeze.value,
        "automaticPromotion",
        false,
        "case freeze",
    )?;
    Ok((run, case_sha, source_set))
}

fn validate_portable_execution_protocol(protocol: &Value) -> Result<(), String> {
    same(
        string(protocol, "schema", "portable execution protocol")?,
        "agentlab.participant_execution_protocol_portable.v1",
        "portable execution protocol schema",
    )?;
    for (key, expected) in [
        ("agentImplementation", "pi"),
        ("agentPackage", "@mariozechner/pi-coding-agent"),
        (
            "promptAuthority",
            "digest-bound-adapter-driver-and-blind-case-manifest",
        ),
        (
            "sessionPolicy",
            "fresh-per-attempt-persistent-across-case-stages",
        ),
        ("thinkingMode", "off"),
        ("extensionPolicy", "disabled"),
        ("skillsPolicy", "disabled"),
        ("contextFilePolicy", "disabled"),
        (
            "samplingPolicy",
            "provider-default-stochastic-repeated-trials",
        ),
    ] {
        same(
            string(protocol, key, "portable execution protocol")?,
            expected,
            &format!("portable execution protocol {key}"),
        )?;
    }
    string(
        protocol,
        "agentPackageVersion",
        "portable execution protocol",
    )?;
    for key in [
        "participantAdapter",
        "participantDriver",
        "participantPackageLock",
        "runtimeDockerfile",
        "runtimeBuildScript",
    ] {
        let binding = &protocol[key];
        let relative = string(binding, "path", "portable execution protocol binding")?;
        if Path::new(relative).is_absolute()
            || relative
                .split('/')
                .any(|part| part.is_empty() || part == "..")
        {
            return Err(format!("portable execution protocol {key} path is invalid"));
        }
        sha(binding, "sha256", "portable execution protocol binding")?;
    }
    sha(
        protocol,
        "participantManifestSha256",
        "portable execution protocol",
    )?;
    let archive = &protocol["runtimeImageArchive"];
    string(archive, "filename", "runtime image archive")?;
    if archive["byteLength"]
        .as_u64()
        .filter(|bytes| *bytes > 0)
        .is_none()
    {
        return Err("runtime image archive byte length is invalid".into());
    }
    sha(archive, "sha256", "runtime image archive")?;
    let image = string(archive, "imageId", "runtime image archive")?;
    if !image.starts_with("sha256:") || !valid_hex(&image[7..], 64) {
        return Err("portable execution protocol runtime image ID is invalid".into());
    }
    if !protocol["reasoningEffort"].is_null() {
        return Err("portable execution protocol reasoning effort must be null".into());
    }
    if protocol["turnTimeoutSeconds"].as_u64() != Some(420) {
        return Err("portable execution protocol turn timeout differs".into());
    }
    exact_bool(
        protocol,
        "portableRuntimeQualified",
        true,
        "portable execution protocol",
    )?;
    exact_bool(
        protocol,
        "crossCampaignProviderReproducibilityQualified",
        false,
        "portable execution protocol",
    )
}

fn validate_dispatch(
    dispatch: &Input,
    run: u64,
    case_sha: &str,
    source_set: &str,
) -> Result<(u64, u64), String> {
    same(
        string(&dispatch.value, "schema", "participant dispatch")?,
        DISPATCH_SCHEMA,
        "participant dispatch schema",
    )?;
    same(
        string(&dispatch.value, "status", "participant dispatch")?,
        "attested-plan-gate-frozen-before-assessment",
        "participant dispatch status",
    )?;
    if dispatch.value["caseReviewRunId"].as_u64() != Some(run) {
        return Err("participant dispatch case-review run differs".into());
    }
    same(
        sha(
            &dispatch.value,
            "evaluationCaseSha256",
            "participant dispatch",
        )?,
        case_sha,
        "participant dispatch case digest",
    )?;
    same(
        sha(&dispatch.value, "sourceSetSha256", "participant dispatch")?,
        source_set,
        "participant dispatch source set",
    )?;
    revision(&dispatch.value, "methodRevision", "participant dispatch")?;
    let trials = dispatch.value["trialsPerParticipant"].as_u64();
    if !matches!(trials, Some(3 | 5 | 10 | 20)) {
        return Err("participant dispatch trial count is invalid".into());
    }
    let profiles = dispatch.value["participantProfiles"]
        .as_array()
        .filter(|items| (3..=8).contains(&items.len()))
        .ok_or_else(|| "participant dispatch must contain 3-8 profiles".to_owned())?;
    let mut participants = BTreeSet::new();
    let mut models = BTreeSet::new();
    for (offset, profile) in profiles.iter().enumerate() {
        if profile["ordinal"].as_u64() != Some(offset as u64) {
            return Err("participant dispatch profile ordinals differ".into());
        }
        let participant = string(profile, "participantId", "dispatch profile")?;
        let model = string(profile, "model", "dispatch profile")?;
        if !participants.insert(participant.to_owned()) || !models.insert(model.to_owned()) {
            return Err("participant dispatch identity is duplicated".into());
        }
    }
    if dispatch.value["participantProfileCount"].as_u64() != Some(profiles.len() as u64) {
        return Err("participant dispatch profile count differs".into());
    }
    validate_portable_execution_protocol(&dispatch.value["executionProtocol"])?;
    exact_bool(
        &dispatch.value,
        "allowsAssessmentExecution",
        true,
        "participant dispatch",
    )?;
    exact_bool(
        &dispatch.value,
        "automaticPromotion",
        false,
        "participant dispatch",
    )?;
    let workflow = &dispatch.value["workflow"];
    string(workflow, "repository", "participant dispatch workflow")?;
    same(
        string(workflow, "path", "participant dispatch workflow")?,
        DISPATCH_WORKFLOW,
        "participant dispatch workflow path",
    )?;
    let run_id = workflow["runId"]
        .as_u64()
        .filter(|value| *value > 0)
        .ok_or_else(|| "participant dispatch workflow run is invalid".to_owned())?;
    let run_attempt = workflow["runAttempt"]
        .as_u64()
        .filter(|value| *value > 0)
        .ok_or_else(|| "participant dispatch workflow attempt is invalid".to_owned())?;
    Ok((run_id, run_attempt))
}

fn validate_attestation(
    dispatch: &Input,
    attestation: &RawInput,
    run_id: u64,
    run_attempt: u64,
) -> Result<(), String> {
    validate_github_actions_attestation(
        &attestation.value,
        &GitHubActionsAttestationIdentity {
            repository: string(
                &dispatch.value["workflow"],
                "repository",
                "participant dispatch workflow",
            )?,
            workflow_path: DISPATCH_WORKFLOW,
            source_digest: string(&dispatch.value, "methodRevision", "participant dispatch")?,
            source_ref: "refs/heads/main",
            run_id,
            run_attempt,
            subject_sha256: &dispatch.sha256(),
        },
    )
}

fn derive(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let contract = Input::load(&path(values, "--contract")?, "contract")?;
    let gate = Input::load(&path(values, "--review-gate")?, "review gate")?;
    let publication = Input::load(&path(values, "--publication")?, "publication")?;
    let reexecution = Input::load(&path(values, "--reexecution")?, "re-execution")?;
    let reexecution_attestation = RawInput::load(
        &path(values, "--reexecution-attestation-verification")?,
        "re-execution attestation verification",
    )?;
    let case_freeze = Input::load(&path(values, "--case-freeze")?, "case freeze")?;
    let dispatch = Input::load(
        &path(values, "--participant-dispatch")?,
        "participant dispatch",
    )?;
    let attestation = RawInput::load(
        &path(values, "--dispatch-attestation-verification")?,
        "dispatch attestation verification",
    )?;
    validate_contract(&contract)?;
    validate_gate(&contract, &gate)?;
    let published = validate_publication(&contract, &gate, &publication)?;
    let (reexecution_run, reexecution_attempt) =
        validate_reexecution(&contract, &publication, &reexecution, &published)?;
    validate_reexecution_attestation(
        &reexecution,
        &reexecution_attestation,
        reexecution_run,
        reexecution_attempt,
    )?;
    let (case_run, case_sha, source_set) =
        validate_case_freeze(&reexecution, &case_freeze, &published)?;
    let (dispatch_run, dispatch_attempt) =
        validate_dispatch(&dispatch, case_run, &case_sha, &source_set)?;
    validate_attestation(&dispatch, &attestation, dispatch_run, dispatch_attempt)?;

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "ready-to-dispatch-unseen-agent-cohort",
        "semanticCandidateId": contract.value["semanticCandidateId"],
        "runtimeCandidateId": contract.value["runtimeCandidateId"],
        "sourceLineage": contract.value["sourceLineage"],
        "publishedRevision": published,
        "caseReviewRunId": case_run,
        "evaluationCaseSha256": case_sha,
        "participantProfileCount": dispatch.value["participantProfileCount"],
        "trialsPerParticipant": dispatch.value["trialsPerParticipant"],
        "dispatchWorkflowRunId": dispatch_run,
        "dispatchWorkflowRunAttempt": dispatch_attempt,
        "evidence": {
            "contract": bind(&contract), "reviewGate": bind(&gate),
            "publication": bind(&publication), "reexecution": bind(&reexecution),
            "reexecutionAttestationVerification": {
                "sha256": reexecution_attestation.sha256(),
                "byteLength": reexecution_attestation.bytes.len()
            },
            "caseFreeze": bind(&case_freeze), "participantDispatch": bind(&dispatch),
            "dispatchAttestationVerification": {
                "sha256": attestation.sha256(),
                "byteLength": attestation.bytes.len()
            }
        },
        "currentReadiness": {
            "independentDualReviewApproved": true,
            "exactPatchPublishedUpstream": true,
            "publishedRevisionRebound": true,
            "trustedFrozenCaseAvailable": true,
            "participantDispatchPredeclaredAndAttested": true,
            "unseenAgentCohortExecuted": false,
            "harmonyAttemptFeedbackExecuted": false,
            "readyToDispatch": true
        },
        "allowsCaseContract": true,
        "allowsUnseenAgentDispatch": true,
        "automaticDispatch": false,
        "automaticPromotion": false,
        "nextGate": "explicit-operator-dispatch-of-predeclared-unseen-agent-cohort"
    }))
}

fn path(values: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    values
        .get(key)
        .map(PathBuf::from)
        .ok_or_else(|| format!("missing {key}"))
}

fn parse_values(args: impl Iterator<Item = String>) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut args = args;
    while let Some(flag) = args.next() {
        let argument = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), argument).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    Ok(values)
}

fn run() -> Result<(), String> {
    let values = parse_values(env::args().skip(1))?;
    let output = path(&values, "--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = derive(&values)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data unseen Agent readiness invalid: {error}");
        std::process::exit(1);
    }
}
