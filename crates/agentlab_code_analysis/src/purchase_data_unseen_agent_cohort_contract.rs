use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

const PACKET_SCHEMA: &str = "agentlab.purchase_data_integrated_review_packet.v1";
const PERFORMANCE_SCHEMA: &str = "agentlab.purchase_data_case_performance_qualification.v1";
const CONTRACT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_cohort_contract.v1";
const PERFORMANCE_ATTACHMENT: &str = "case-performance-qualification";
const CASE_REVIEW_PATH: &str = ".github/workflows/multi-repo-case-review.yml";
const CAMPAIGN_PATH: &str = ".github/workflows/multi-repo-assessed-campaign.yml";
const DISPATCH_SOURCE_PATH: &str =
    "crates/agentlab_code_analysis/src/participant_experiment_dispatch.rs";
const DISPATCH_SCHEMA_PATH: &str = "schemas/participant-experiment-dispatch.schema.json";
const PUBLICATION_SOURCE_PATH: &str =
    "crates/agentlab_code_analysis/src/purchase_data_exact_patch_publication.rs";
const PUBLICATION_SCHEMA_PATH: &str = "schemas/purchase-data-exact-patch-publication.schema.json";
const PUBLICATION_WORKFLOW_PATH: &str =
    ".github/workflows/purchase-data-exact-patch-publication.yml";
const REEXECUTION_SOURCE_PATH: &str =
    "crates/agentlab_code_analysis/src/purchase_data_published_revision_reexecution.rs";
const REEXECUTION_SCHEMA_PATH: &str =
    "schemas/purchase-data-published-revision-reexecution.schema.json";
const RUNTIME_BUNDLE_SCHEMA_PATH: &str =
    "schemas/purchase-data-published-revision-runtime-bundle.schema.json";
const REEXECUTION_WORKFLOW_PATH: &str =
    ".github/workflows/purchase-data-published-revision-reexecution.yml";

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

struct TextInput {
    bytes: Vec<u8>,
    text: String,
}

impl TextInput {
    fn load(path: &Path, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let text = String::from_utf8(bytes.clone())
            .map_err(|error| format!("{label} must be UTF-8: {error}"))?;
        Ok(Self { bytes, text })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }

    fn require_fragments(&self, fragments: &[&str], label: &str) -> Result<(), String> {
        for fragment in fragments {
            if !self.text.contains(fragment) {
                return Err(format!("{label} contract fragment is absent: {fragment}"));
            }
        }
        Ok(())
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

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn valid_revision(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn validate_packet(packet: &Value) -> Result<(), String> {
    same(
        string(packet, "schema", "integrated packet")?,
        PACKET_SCHEMA,
        "integrated packet schema",
    )?;
    same(
        string(packet, "status", "integrated packet")?,
        "current-evidence-bound-independent-dual-review-required",
        "integrated packet status",
    )?;
    same(
        string(packet, "nextGate", "integrated packet")?,
        "authenticated-distinct-semantic-and-oracle-reviewers-then-upstream-publication-rebinding-and-unseen-agent-cohort-evaluation",
        "integrated packet next gate",
    )?;
    for key in [
        "relativePerformanceDetectorCalibrated",
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "performanceCalibrated",
    ] {
        exact_bool(packet, key, true, "integrated packet")?;
    }
    for key in ["allowsCaseContract", "automaticPromotion"] {
        exact_bool(packet, key, false, "integrated packet")?;
    }
    let review = &packet["reviewDecisionContract"];
    if review["minimumDistinctReviewerCount"].as_u64() != Some(2) {
        return Err("integrated packet minimum reviewer count differs".into());
    }
    for key in [
        "semanticAndOracleReviewerMustDiffer",
        "reviewersMustDifferFromCandidateAuthor",
        "approvalRequiresEveryAnswerYes",
    ] {
        exact_bool(review, key, true, "integrated review contract")?;
    }
    let lineage = &packet["sourceLineage"];
    for key in ["analysisSourceSetSha256", "runtimeSourceSetSha256"] {
        if !valid_sha256(string(lineage, key, "source lineage")?) {
            return Err(format!("source lineage {key} is invalid"));
        }
    }
    for key in ["baseRevision", "candidateRevision"] {
        if !valid_revision(string(lineage, key, "source lineage")?) {
            return Err(format!("source lineage {key} is invalid"));
        }
    }
    Ok(())
}

fn validate_performance(packet: &Value, root: &Path) -> Result<Input, String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("cannot resolve qualification root: {error}"))?;
    let attachment = &packet["evidenceAttachments"][PERFORMANCE_ATTACHMENT];
    let relative = string(attachment, "path", "performance attachment")?;
    if relative.starts_with('/')
        || relative
            .split('/')
            .any(|part| part.is_empty() || part == "..")
    {
        return Err("performance attachment path is invalid".into());
    }
    let path = root.join(relative);
    let input = Input::load(&path, "performance qualification")?;
    let resolved = path
        .canonicalize()
        .map_err(|error| format!("cannot resolve performance qualification: {error}"))?;
    if !resolved.starts_with(&root) {
        return Err("performance qualification leaves qualification root".into());
    }
    same(
        &input.sha256(),
        string(attachment, "sha256", "performance attachment")?,
        "performance qualification digest",
    )?;
    if attachment["byteLength"].as_u64() != Some(input.bytes.len() as u64) {
        return Err("performance qualification byte length differs".into());
    }
    same(
        string(&input.value, "schema", "performance qualification")?,
        PERFORMANCE_SCHEMA,
        "performance qualification schema",
    )?;
    same(
        string(&input.value, "status", "performance qualification")?,
        "case-bound-reference-baseline-meaningful-wrong-performance-calibrated",
        "performance qualification status",
    )?;
    for key in [
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "performanceCalibrated",
    ] {
        exact_bool(&input.value, key, true, "performance qualification")?;
    }
    for (key, expected) in [
        ("roleCount", 3),
        ("coldRunCount", 6),
        ("functionalVerdictCount", 288),
        ("profileSampleCount", 288),
    ] {
        if input.value["coverage"][key].as_u64() != Some(expected) {
            return Err(format!("performance qualification coverage {key} differs"));
        }
    }
    Ok(input)
}

fn binding(path: &str, input: &TextInput) -> Value {
    json!({"path": path, "sha256": input.sha256()})
}

fn derive(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let packet = Input::load(&path(values, "--packet")?, "integrated packet")?;
    let expected_packet = value(values, "--expected-packet-sha256")?;
    if !valid_sha256(expected_packet) || packet.sha256() != expected_packet {
        return Err("expected integrated packet digest differs".into());
    }
    validate_packet(&packet.value)?;
    let performance = validate_performance(&packet.value, &path(values, "--qualification-root")?)?;
    let case_review = TextInput::load(
        &path(values, "--case-review-workflow")?,
        "case-review workflow",
    )?;
    case_review.require_fragments(
        &[
            "name: Multi-repository case review and freeze",
            "prepare-multi-repo-blind-cut.py",
            "--source-visibility held-out-public-revision",
            "build-blind-case-cut.py validate",
        ],
        "case-review workflow",
    )?;
    let campaign = TextInput::load(
        &path(values, "--assessed-campaign-workflow")?,
        "assessed-campaign workflow",
    )?;
    campaign.require_fragments(
        &[
            "name: Multi-repository assessed-Agent campaign",
            "JSON array of 3-8 unique participantId/model objects ordered weakest to strongest before any outcomes exist",
            "options: ['3', '5', '10', '20']",
            "needs: freeze-plan",
            "agentlab-participant-experiment-dispatch -- freeze",
            "agentlab-participant-experiment-dispatch -- materialize",
            "gh attestation verify",
            "score-case-discrimination.py",
            "prepare-harmony-assessed-handoff.py",
        ],
        "assessed-campaign workflow",
    )?;
    let dispatch_source = TextInput::load(
        &path(values, "--participant-dispatch-source")?,
        "participant dispatch source",
    )?;
    dispatch_source.require_fragments(
        &[
            "const DISPATCH_SCHEMA: &str = \"agentlab.participant_experiment_dispatch.v1\"",
            "\"attested-plan-gate-frozen-before-assessment\"",
            "\"freeze\" =>",
            "\"materialize\" =>",
            "validate_attestation(",
            "\"automaticPromotion\": false",
        ],
        "participant dispatch source",
    )?;
    let dispatch_schema = TextInput::load(
        &path(values, "--participant-dispatch-schema")?,
        "participant dispatch schema",
    )?;
    dispatch_schema.require_fragments(
        &[
            "\"$schema\": \"https://json-schema.org/draft/2020-12/schema\"",
            "\"schema\": {\"const\": \"agentlab.participant_experiment_dispatch.v1\"}",
            "\"status\": {\"const\": \"attested-plan-gate-frozen-before-assessment\"}",
            "\"allowsAssessmentExecution\": {\"const\": true}",
            "\"automaticPromotion\": {\"const\": false}",
        ],
        "participant dispatch schema",
    )?;
    let publication_source = TextInput::load(
        &path(values, "--exact-patch-publication-source")?,
        "exact-patch publication source",
    )?;
    publication_source.require_fragments(
        &[
            "const OUTPUT_SCHEMA: &str = \"agentlab.purchase_data_exact_patch_publication.v1\"",
            "exact_patch_tree(",
            "published revision exact reviewed-patch tree",
            "published revision is absent from the upstream origin",
            "\"automaticPromotion\": false",
        ],
        "exact-patch publication source",
    )?;
    let publication_schema = TextInput::load(
        &path(values, "--exact-patch-publication-schema")?,
        "exact-patch publication schema",
    )?;
    publication_schema.require_fragments(
        &[
            "\"schema\": {\"const\": \"agentlab.purchase_data_exact_patch_publication.v1\"}",
            "\"publishedRevisionContainsExactReviewedPatch\": {\"const\": true}",
            "\"verifiedOnline\": {\"const\": true}",
            "\"automaticPromotion\": {\"const\": false}",
        ],
        "exact-patch publication schema",
    )?;
    let publication_workflow = TextInput::load(
        &path(values, "--exact-patch-publication-workflow")?,
        "exact-patch publication workflow",
    )?;
    publication_workflow.require_fragments(
        &[
            "name: Record purchase-data exact patch publication",
            "github.ref == 'refs/heads/main'",
            "purchase-data-integrated-oracle-review.yml",
            "agentlab-purchase-data-exact-patch-publication",
            "Attest the exact publication receipt",
        ],
        "exact-patch publication workflow",
    )?;
    let reexecution_source = TextInput::load(
        &path(values, "--published-revision-reexecution-source")?,
        "published-revision re-execution source",
    )?;
    reexecution_source.require_fragments(
        &[
            "const OUTPUT_SCHEMA: &str = \"agentlab.purchase_data_published_revision_reexecution.v1\"",
            "validate_publication_attestation(",
            "validate_semantic(",
            "validate_runtime(",
            "published-revision-semantic-ohostest-performance-passed",
            "\"automaticPromotion\": false",
        ],
        "published-revision re-execution source",
    )?;
    let reexecution_schema = TextInput::load(
        &path(values, "--published-revision-reexecution-schema")?,
        "published-revision re-execution schema",
    )?;
    reexecution_schema.require_fragments(
        &[
            "\"schema\": {\"const\": \"agentlab.purchase_data_published_revision_reexecution.v1\"}",
            "\"semanticPassed\": {\"const\": true}",
            "\"ohosTestPassed\": {\"const\": true}",
            "\"performancePassed\": {\"const\": true}",
            "\"automaticPromotion\": {\"const\": false}",
        ],
        "published-revision re-execution schema",
    )?;
    let runtime_bundle_schema = TextInput::load(
        &path(values, "--published-revision-runtime-bundle-schema")?,
        "published-revision runtime bundle schema",
    )?;
    runtime_bundle_schema.require_fragments(
        &[
            "\"schema\": {\"const\": \"agentlab.purchase_data_published_revision_runtime_bundle.v1\"}",
            "\"ohosTestReceipt\": {\"$ref\": \"#/$defs/fileBinding\"}",
            "\"performanceQualification\": {\"$ref\": \"#/$defs/fileBinding\"}",
            "\"automaticPromotion\": {\"const\": false}",
        ],
        "published-revision runtime bundle schema",
    )?;
    let reexecution_workflow = TextInput::load(
        &path(values, "--published-revision-reexecution-workflow")?,
        "published-revision re-execution workflow",
    )?;
    reexecution_workflow.require_fragments(
        &[
            "name: Verify purchase-data published revision re-execution",
            "github.ref == 'refs/heads/main'",
            "gh attestation verify",
            "agentlab-purchase-data-published-revision-reexecution",
            "Attest the exact published-revision re-execution receipt",
        ],
        "published-revision re-execution workflow",
    )?;

    Ok(json!({
        "schema": CONTRACT_SCHEMA,
        "status": "execution-contract-frozen-prerequisites-pending",
        "packetSha256": packet.sha256(),
        "semanticCandidateId": packet.value["semanticCandidateId"],
        "runtimeCandidateId": packet.value["runtimeCandidateId"],
        "sourceLineage": packet.value["sourceLineage"],
        "performanceQualification": {
            "path": packet.value["evidenceAttachments"][PERFORMANCE_ATTACHMENT]["path"],
            "sha256": performance.sha256(),
            "coldRunCount": 6,
            "functionalVerdictCount": 288,
            "profileSampleCount": 288,
            "relativeMetricAuthority": "appCpuUsagePercent",
            "controlledVariantsAreAgentRuns": false
        },
        "implementationBindings": {
            "trustedCaseReview": binding(CASE_REVIEW_PATH, &case_review),
            "assessedCampaign": binding(CAMPAIGN_PATH, &campaign),
            "participantExperimentDispatch": binding(DISPATCH_SOURCE_PATH, &dispatch_source),
            "participantExperimentDispatchSchema": binding(DISPATCH_SCHEMA_PATH, &dispatch_schema),
            "exactPatchPublication": binding(PUBLICATION_SOURCE_PATH, &publication_source),
            "exactPatchPublicationSchema": binding(PUBLICATION_SCHEMA_PATH, &publication_schema),
            "exactPatchPublicationWorkflow": binding(PUBLICATION_WORKFLOW_PATH, &publication_workflow),
            "publishedRevisionReexecution": binding(REEXECUTION_SOURCE_PATH, &reexecution_source),
            "publishedRevisionReexecutionSchema": binding(REEXECUTION_SCHEMA_PATH, &reexecution_schema),
            "publishedRevisionRuntimeBundleSchema": binding(RUNTIME_BUNDLE_SCHEMA_PATH, &runtime_bundle_schema),
            "publishedRevisionReexecutionWorkflow": binding(REEXECUTION_WORKFLOW_PATH, &reexecution_workflow)
        },
        "requiredSequence": [
            {"ordinal": 1, "gate": "independent-dual-integrated-review", "requiredEvidence": "approved agentlab.purchase_data_integrated_review_gate.v1 bound to this packet"},
            {"ordinal": 2, "gate": "exact-patch-upstream-publication", "requiredEvidence": "published upstream revision containing the exact reviewed patch"},
            {"ordinal": 3, "gate": "published-revision-reexecution", "requiredEvidence": "semantic, OHOS Test and performance evidence rebound to the published source revision"},
            {"ordinal": 4, "gate": "trusted-case-freeze", "requiredEvidence": "successful trusted-main multi-repo-case-review run with held-out public revision"},
            {"ordinal": 5, "gate": "unseen-agent-cohort", "requiredEvidence": "pre-outcome attested portable dispatch and repeated blind attempts for every declared profile"},
            {"ordinal": 6, "gate": "harmony-functional-performance-feedback", "requiredEvidence": "Harmony handoff plus OHOS Test and relative SmartPerf results linked to each assessed attempt"}
        ],
        "participantCohort": {
            "minimumProfiles": 3,
            "maximumProfiles": 8,
            "profileOrder": "weakest-to-strongest-declared-before-outcomes",
            "participantAndModelIdentitiesMustBeUnique": true,
            "allowedTrialsPerProfile": [3, 5, 10, 20],
            "freshRuntimePerAttempt": true,
            "portableDispatchSchema": "agentlab.participant_experiment_dispatch.v1",
            "materializedPlanCompatibilitySchema": "agentlab.participant_experiment_plan.v1"
        },
        "authoritySeparation": {
            "participantReceives": ["blind task contract", "held-out source repositories", "participant-visible build and test instructions"],
            "participantMustNotReceive": ["gold repair", "evaluator Oracle", "reference workspace", "calibration outcomes", "controlled baseline or meaningful-wrong variants"],
            "evaluatorRetains": ["OHOS Test functional Oracle", "dependency obligations", "case-performance policy", "SmartPerf comparison authority"]
        },
        "currentReadiness": {
            "independentDualReviewApproved": false,
            "exactPatchPublishedUpstream": false,
            "publishedRevisionRebound": false,
            "trustedFrozenCaseAvailable": false,
            "unseenAgentCohortExecuted": false,
            "harmonyAttemptFeedbackExecuted": false,
            "readyToDispatch": false
        },
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "nextGate": "two-distinct-authenticated-reviewers-approve-exact-packet"
    }))
}

fn path(values: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    values
        .get(key)
        .map(PathBuf::from)
        .ok_or_else(|| format!("missing {key}"))
}

fn value<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
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
        eprintln!("purchase-data unseen Agent cohort contract invalid: {error}");
        std::process::exit(1);
    }
}
