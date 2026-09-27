use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

const CONTRACT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_cohort_contract.v1";
const GATE_SCHEMA: &str = "agentlab.purchase_data_integrated_review_gate.v1";
const PUBLICATION_SCHEMA: &str = "agentlab.purchase_data_exact_patch_publication.v1";
const REEXECUTION_SCHEMA: &str = "agentlab.purchase_data_published_revision_reexecution.v1";
const CASE_FREEZE_SCHEMA: &str = "agentlab.purchase_data_trusted_case_freeze.v1";
const PLAN_SCHEMA: &str = "agentlab.participant_experiment_plan.v1";
const ATTESTATION_SCHEMA: &str = "agentlab.participant_experiment_plan_attestation.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_dispatch_readiness.v1";

struct Input {
    bytes: Vec<u8>,
    value: Value,
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
) -> Result<(), String> {
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
    for key in ["semanticPassed", "ohosTestPassed", "performancePassed"] {
        exact_bool(&reexecution.value, key, true, "re-execution")?;
    }
    exact_bool(&reexecution.value, "trustedMainRun", true, "re-execution")?;
    if reexecution.value["runId"]
        .as_u64()
        .filter(|id| *id > 0)
        .is_none()
    {
        return Err("re-execution runId is invalid".into());
    }
    for key in [
        "semanticEvidenceSha256",
        "ohosTestEvidenceSha256",
        "performanceEvidenceSha256",
    ] {
        sha(&reexecution.value, key, "re-execution")?;
    }
    exact_bool(
        &reexecution.value,
        "automaticPromotion",
        false,
        "re-execution",
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

fn validate_execution_protocol(protocol: &Value) -> Result<(), String> {
    same(
        string(protocol, "schema", "execution protocol")?,
        "agentlab.participant_execution_protocol.v1",
        "execution protocol schema",
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
            string(protocol, key, "execution protocol")?,
            expected,
            &format!("execution protocol {key}"),
        )?;
    }
    string(protocol, "agentPackageVersion", "execution protocol")?;
    for key in ["participantAdapter", "participantDriver"] {
        let binding = &protocol[key];
        string(binding, "path", "execution protocol binding")?;
        sha(binding, "sha256", "execution protocol binding")?;
    }
    for key in [
        "participantPackageLockSha256",
        "participantRuntimeConfigSha256",
        "participantManifestSha256",
    ] {
        sha(protocol, key, "execution protocol")?;
    }
    let image = string(protocol, "runtimeImageId", "execution protocol")?;
    if !image.starts_with("sha256:") || !valid_hex(&image[7..], 64) {
        return Err("execution protocol runtime image ID is invalid".into());
    }
    if !protocol["reasoningEffort"].is_null() {
        return Err("execution protocol reasoning effort must be null".into());
    }
    if protocol["turnTimeoutSeconds"].as_u64() != Some(420) {
        return Err("execution protocol turn timeout differs".into());
    }
    exact_bool(
        protocol,
        "withinCampaignExecutionProtocolQualified",
        true,
        "execution protocol",
    )?;
    exact_bool(
        protocol,
        "crossCampaignProviderReproducibilityQualified",
        false,
        "execution protocol",
    )
}

fn validate_plan(plan: &Input, run: u64, case_sha: &str, source_set: &str) -> Result<(), String> {
    same(
        string(&plan.value, "schema", "experiment plan")?,
        PLAN_SCHEMA,
        "experiment plan schema",
    )?;
    same(
        string(&plan.value, "status", "experiment plan")?,
        "predeclared-before-attempts",
        "experiment plan status",
    )?;
    if plan.value["caseReviewRunId"].as_u64() != Some(run) {
        return Err("experiment plan case-review run differs".into());
    }
    same(
        sha(&plan.value, "evaluationCaseSha256", "experiment plan")?,
        case_sha,
        "experiment plan case digest",
    )?;
    same(
        sha(&plan.value, "sourceSetSha256", "experiment plan")?,
        source_set,
        "experiment plan source set",
    )?;
    revision(&plan.value, "methodRevision", "experiment plan")?;
    let trials = plan.value["trialsPerParticipant"].as_u64();
    if !matches!(trials, Some(3 | 5 | 10 | 20)) {
        return Err("experiment plan trial count is invalid".into());
    }
    let profiles = plan.value["participantProfiles"]
        .as_array()
        .filter(|items| (3..=8).contains(&items.len()))
        .ok_or_else(|| "experiment plan must contain 3-8 profiles".to_owned())?;
    let mut identities = std::collections::BTreeSet::new();
    for (offset, profile) in profiles.iter().enumerate() {
        if profile["ordinal"].as_u64() != Some(offset as u64) {
            return Err("experiment plan profile ordinals differ".into());
        }
        let participant = string(profile, "participantId", "experiment profile")?;
        let model = string(profile, "model", "experiment profile")?;
        if !identities.insert(("participant", participant.to_owned()))
            || !identities.insert(("model", model.to_owned()))
        {
            return Err("experiment plan participant or model identity is duplicated".into());
        }
    }
    if plan.value["participantProfileCount"].as_u64() != Some(profiles.len() as u64) {
        return Err("experiment plan profile count differs".into());
    }
    validate_execution_protocol(&plan.value["executionProtocol"])?;
    exact_bool(&plan.value, "automaticPromotion", false, "experiment plan")
}

fn validate_attestation(plan: &Input, attestation: &Input) -> Result<(), String> {
    same(
        string(&attestation.value, "schema", "plan attestation")?,
        ATTESTATION_SCHEMA,
        "plan attestation schema",
    )?;
    same(
        string(&attestation.value, "status", "plan attestation")?,
        "verified-github-attestation",
        "plan attestation status",
    )?;
    same(
        sha(&attestation.value, "planSha256", "plan attestation")?,
        &plan.sha256(),
        "plan attestation plan digest",
    )?;
    same(
        string(&attestation.value, "workflowPath", "plan attestation")?,
        ".github/workflows/multi-repo-assessed-campaign.yml",
        "plan attestation workflow",
    )?;
    string(&attestation.value, "repository", "plan attestation")?;
    if attestation.value["runId"]
        .as_u64()
        .filter(|id| *id > 0)
        .is_none()
    {
        return Err("plan attestation runId is invalid".into());
    }
    exact_bool(
        &attestation.value,
        "verifiedOnline",
        true,
        "plan attestation",
    )?;
    exact_bool(
        &attestation.value,
        "automaticPromotion",
        false,
        "plan attestation",
    )
}

fn derive(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let contract = Input::load(&path(values, "--contract")?, "contract")?;
    let gate = Input::load(&path(values, "--review-gate")?, "review gate")?;
    let publication = Input::load(&path(values, "--publication")?, "publication")?;
    let reexecution = Input::load(&path(values, "--reexecution")?, "re-execution")?;
    let case_freeze = Input::load(&path(values, "--case-freeze")?, "case freeze")?;
    let plan = Input::load(&path(values, "--experiment-plan")?, "experiment plan")?;
    let attestation = Input::load(&path(values, "--plan-attestation")?, "plan attestation")?;
    validate_contract(&contract)?;
    validate_gate(&contract, &gate)?;
    let published = validate_publication(&contract, &gate, &publication)?;
    validate_reexecution(&contract, &publication, &reexecution, &published)?;
    let (case_run, case_sha, source_set) =
        validate_case_freeze(&reexecution, &case_freeze, &published)?;
    validate_plan(&plan, case_run, &case_sha, &source_set)?;
    validate_attestation(&plan, &attestation)?;

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "ready-to-dispatch-unseen-agent-cohort",
        "semanticCandidateId": contract.value["semanticCandidateId"],
        "runtimeCandidateId": contract.value["runtimeCandidateId"],
        "sourceLineage": contract.value["sourceLineage"],
        "publishedRevision": published,
        "caseReviewRunId": case_run,
        "evaluationCaseSha256": case_sha,
        "participantProfileCount": plan.value["participantProfileCount"],
        "trialsPerParticipant": plan.value["trialsPerParticipant"],
        "evidence": {
            "contract": bind(&contract), "reviewGate": bind(&gate),
            "publication": bind(&publication), "reexecution": bind(&reexecution),
            "caseFreeze": bind(&case_freeze), "experimentPlan": bind(&plan),
            "planAttestation": bind(&attestation)
        },
        "currentReadiness": {
            "independentDualReviewApproved": true,
            "exactPatchPublishedUpstream": true,
            "publishedRevisionRebound": true,
            "trustedFrozenCaseAvailable": true,
            "experimentPlanPredeclaredAndAttested": true,
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
