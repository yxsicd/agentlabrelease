use agentlab_code_analysis::digest;
use serde_json::{json, Map, Value};
use std::{
    env, fs,
    path::{Path, PathBuf},
};

const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_integrated_review_packet.v1";
const SEMANTIC_SCHEMA: &str = "agentlab.multi_repo_candidate_review_packet.v11";
const ORACLE_PLAN_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_plan.v1";
const ORACLE_CALIBRATION_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_calibration.v1";
const SOURCE_REVIEW_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_packet.v1";
const MUTATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_qualification.v1";
const RUNTIME_BRIDGE_SCHEMA: &str = "agentlab.purchase_data_runtime_oracle_bridge.v1";
const PROFILE_SCHEMA: &str = "agentlab.purchase_data_ohostest_profile_qualification.v1";
const DETECTOR_SCHEMA: &str =
    "agentlab.purchase_data_ohostest_performance_detector_qualification.v1";

const SEMANTIC_CANDIDATE: &str = "difficulty-c75c82b3a697d8053e74bb37";
const RUNTIME_CANDIDATE: &str = "purchase-data-finalization-ee2bc87594f1";
const ANALYSIS_SOURCE_SET: &str =
    "0b72a6d7c985f68b4e00d4dec6848e6cf5b25d34a903d7d9c8b365acc214ad1b";
const RUNTIME_SOURCE_SET: &str = "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2";
const BASE_REVISION: &str = "59260e2b0f9663be2d35288f4f339b8ce60ae5a3";
const CANDIDATE_REVISION: &str = "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8";

const ATTACHMENTS: &[(&str, &str, &str)] = &[
    (
        "semantic-review-packet",
        "review-packets/purchase-data-control-flow-v11.json",
        SEMANTIC_SCHEMA,
    ),
    (
        "behavior-oracle-plan",
        "purchase-data-behavior-oracle-plan.json",
        ORACLE_PLAN_SCHEMA,
    ),
    (
        "behavior-oracle-calibration",
        "purchase-data-behavior-oracle-calibration.json",
        ORACLE_CALIBRATION_SCHEMA,
    ),
    (
        "source-review-packet",
        "purchase-data-ohostest-review-packet.json",
        SOURCE_REVIEW_SCHEMA,
    ),
    (
        "functional-mutation-qualification",
        "purchase-data-ohostest-mutation-qualification.json",
        MUTATION_SCHEMA,
    ),
    (
        "runtime-oracle-bridge",
        "purchase-data-runtime-oracle-bridge.json",
        RUNTIME_BRIDGE_SCHEMA,
    ),
    (
        "profile-qualification",
        "purchase-data-ohostest-profile-qualification.json",
        PROFILE_SCHEMA,
    ),
    (
        "performance-detector-qualification",
        "purchase-data-ohostest-performance-detector-qualification.json",
        DETECTOR_SCHEMA,
    ),
];

struct Input {
    relative_path: &'static str,
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(root: &Path, relative_path: &'static str, label: &str) -> Result<Self, String> {
        let path = root.join(relative_path);
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(&path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("cannot parse {label}: {error}"))?;
        if !value.is_object() {
            return Err(format!("{label} must be a JSON object"));
        }
        Ok(Self {
            relative_path,
            bytes,
            value,
        })
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

fn exact_u64(value: &Value, key: &str, expected: u64, label: &str) -> Result<(), String> {
    if value[key].as_u64() != Some(expected) {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}

fn exact_array_len(value: &Value, key: &str, expected: usize, label: &str) -> Result<(), String> {
    if value[key].as_array().map(Vec::len) != Some(expected) {
        return Err(format!("{label} {key} length differs"));
    }
    Ok(())
}

fn false_boundary(value: &Value, keys: &[&str], label: &str) -> Result<(), String> {
    for key in keys {
        exact_bool(value, key, false, label)?;
    }
    Ok(())
}

fn validate_semantic(input: &Input) -> Result<(), String> {
    let value = &input.value;
    same(
        string(value, "schema", "semantic packet")?,
        SEMANTIC_SCHEMA,
        "semantic packet schema",
    )?;
    same(
        string(value, "status", "semantic packet")?,
        "independent-semantic-review-required",
        "semantic packet status",
    )?;
    same(
        string(value, "candidateId", "semantic packet")?,
        SEMANTIC_CANDIDATE,
        "semantic candidate",
    )?;
    same(
        string(value, "sourceSetSha256", "semantic packet")?,
        ANALYSIS_SOURCE_SET,
        "semantic source set",
    )?;
    false_boundary(
        value,
        &[
            "semanticAlignmentVerified",
            "behaviorOracleVerified",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "semantic packet",
    )?;
    let attachments = value["evidenceAttachments"]
        .as_object()
        .ok_or_else(|| "semantic packet evidence attachments are absent".to_owned())?;
    for required in [
        "bounded-expression-flow-program-analysis",
        "external-sink-contract-qualification",
        "cordova-object-flow-qualification",
        "selected-control-flow-qualification",
    ] {
        if !attachments.contains_key(required) {
            return Err(format!("semantic packet attachment is absent: {required}"));
        }
    }
    Ok(())
}

fn validate_oracle_plan(plan: &Input, semantic: &Input) -> Result<(), String> {
    let value = &plan.value;
    same(
        string(value, "schema", "Oracle plan")?,
        ORACLE_PLAN_SCHEMA,
        "Oracle plan schema",
    )?;
    same(
        string(value, "candidateId", "Oracle plan")?,
        SEMANTIC_CANDIDATE,
        "Oracle plan candidate",
    )?;
    same(
        string(value, "sourceSetSha256", "Oracle plan")?,
        ANALYSIS_SOURCE_SET,
        "Oracle plan source set",
    )?;
    same(
        string(value, "reviewPacketSha256", "Oracle plan")?,
        &semantic.sha256(),
        "Oracle plan semantic packet digest",
    )?;
    exact_array_len(value, "repositories", 2, "Oracle plan")?;
    exact_array_len(value, "methods", 5, "Oracle plan")?;
    exact_array_len(value, "checks", 10, "Oracle plan")?;
    exact_array_len(value, "variants", 6, "Oracle plan")?;
    Ok(())
}

fn validate_oracle_calibration(
    calibration: &Input,
    plan: &Input,
    semantic: &Input,
) -> Result<(), String> {
    let value = &calibration.value;
    same(
        string(value, "schema", "Oracle calibration")?,
        ORACLE_CALIBRATION_SCHEMA,
        "Oracle calibration schema",
    )?;
    same(
        string(value, "status", "Oracle calibration")?,
        "source-seam-calibrated-independent-review-required",
        "Oracle calibration status",
    )?;
    same(
        string(value, "candidateId", "Oracle calibration")?,
        SEMANTIC_CANDIDATE,
        "Oracle calibration candidate",
    )?;
    same(
        string(value, "sourceSetSha256", "Oracle calibration")?,
        ANALYSIS_SOURCE_SET,
        "Oracle calibration source set",
    )?;
    same(
        string(value, "reviewPacketSha256", "Oracle calibration")?,
        &semantic.sha256(),
        "Oracle calibration semantic packet",
    )?;
    same(
        string(value, "planSha256", "Oracle calibration")?,
        &plan.sha256(),
        "Oracle calibration plan",
    )?;
    exact_bool(value, "sourceSeamCalibrated", true, "Oracle calibration")?;
    false_boundary(
        value,
        &[
            "semanticAlignmentVerified",
            "behaviorOracleVerified",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "Oracle calibration",
    )?;
    let coverage = &value["coverage"];
    exact_u64(
        coverage,
        "repositoryCount",
        2,
        "Oracle calibration coverage",
    )?;
    exact_u64(coverage, "methodCount", 5, "Oracle calibration coverage")?;
    exact_u64(coverage, "checkCount", 10, "Oracle calibration coverage")?;
    exact_u64(
        coverage,
        "negativeControlCount",
        5,
        "Oracle calibration coverage",
    )?;
    exact_u64(
        coverage,
        "undetectedNegativeControlCount",
        0,
        "Oracle calibration coverage",
    )?;
    exact_bool(
        coverage,
        "allNegativeControlsDetected",
        true,
        "Oracle calibration coverage",
    )
}

fn validate_source_review(input: &Input) -> Result<(), String> {
    let value = &input.value;
    same(
        string(value, "schema", "source review packet")?,
        SOURCE_REVIEW_SCHEMA,
        "source review packet schema",
    )?;
    same(
        string(value, "status", "source review packet")?,
        "independent-source-review-required",
        "source review packet status",
    )?;
    same(
        string(value, "candidateId", "source review packet")?,
        RUNTIME_CANDIDATE,
        "source review candidate",
    )?;
    same(
        string(value, "baseRevision", "source review packet")?,
        BASE_REVISION,
        "source review base revision",
    )?;
    same(
        string(value, "candidateRevision", "source review packet")?,
        CANDIDATE_REVISION,
        "source review candidate revision",
    )?;
    exact_u64(
        &value["execution"],
        "testCount",
        7,
        "source review execution",
    )?;
    exact_u64(&value["execution"], "passed", 7, "source review execution")?;
    false_boundary(
        value,
        &[
            "publishedToUpstream",
            "independentReviewVerified",
            "behaviorOracleVerified",
            "performanceCalibrated",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "source review packet",
    )
}

fn validate_mutation(input: &Input) -> Result<(), String> {
    let value = &input.value;
    same(
        string(value, "schema", "mutation qualification")?,
        MUTATION_SCHEMA,
        "mutation qualification schema",
    )?;
    same(
        string(value, "status", "mutation qualification")?,
        "mutation-discrimination-qualified-source-review-still-required",
        "mutation qualification status",
    )?;
    same(
        string(value, "candidateId", "mutation qualification")?,
        RUNTIME_CANDIDATE,
        "mutation candidate",
    )?;
    same(
        string(value, "candidateRevision", "mutation qualification")?,
        CANDIDATE_REVISION,
        "mutation candidate revision",
    )?;
    exact_u64(value, "variantCount", 6, "mutation qualification")?;
    exact_u64(value, "killedVariantCount", 6, "mutation qualification")?;
    exact_u64(value, "testCount", 7, "mutation qualification")?;
    exact_bool(
        value,
        "expectedMatrixVerified",
        true,
        "mutation qualification",
    )?;
    if value["mutationScore"].as_f64() != Some(1.0) {
        return Err("mutation qualification score differs".into());
    }
    false_boundary(
        value,
        &[
            "independentReviewVerified",
            "behaviorOracleVerified",
            "performanceCalibrated",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "mutation qualification",
    )
}

fn validate_runtime_bridge(
    bridge: &Input,
    plan: &Input,
    calibration: &Input,
    mutation: &Input,
) -> Result<(), String> {
    let value = &bridge.value;
    same(
        string(value, "schema", "runtime bridge")?,
        RUNTIME_BRIDGE_SCHEMA,
        "runtime bridge schema",
    )?;
    same(
        string(value, "status", "runtime bridge")?,
        "harmony-runtime-oracle-bridge-qualified-independent-review-required",
        "runtime bridge status",
    )?;
    same(
        string(value, "semanticCandidateId", "runtime bridge")?,
        SEMANTIC_CANDIDATE,
        "runtime bridge semantic candidate",
    )?;
    same(
        string(value, "runtimeCandidateId", "runtime bridge")?,
        RUNTIME_CANDIDATE,
        "runtime bridge runtime candidate",
    )?;
    same(
        string(value, "baseRevision", "runtime bridge")?,
        BASE_REVISION,
        "runtime bridge base revision",
    )?;
    same(
        string(value, "candidateRevision", "runtime bridge")?,
        CANDIDATE_REVISION,
        "runtime bridge candidate revision",
    )?;
    same(
        string(&value["artifactSha256"], "behaviorPlan", "runtime bridge")?,
        &plan.sha256(),
        "runtime bridge behavior plan",
    )?;
    same(
        string(
            &value["artifactSha256"],
            "behaviorCalibration",
            "runtime bridge",
        )?,
        &calibration.sha256(),
        "runtime bridge behavior calibration",
    )?;
    same(
        string(
            &value["artifactSha256"],
            "mutationQualification",
            "runtime bridge",
        )?,
        &mutation.sha256(),
        "runtime bridge mutation qualification",
    )?;
    let coverage = &value["coverage"];
    exact_u64(
        coverage,
        "crossRepositoryBehaviorCheckCount",
        10,
        "runtime bridge coverage",
    )?;
    exact_u64(
        coverage,
        "harmonyRuntimeBoundCheckCount",
        5,
        "runtime bridge coverage",
    )?;
    exact_u64(
        coverage,
        "cordovaRuntimeBoundCheckCount",
        0,
        "runtime bridge coverage",
    )?;
    exact_u64(
        coverage,
        "runtimeMutationVariantCount",
        6,
        "runtime bridge coverage",
    )?;
    exact_u64(
        coverage,
        "runtimeKilledMutationVariantCount",
        6,
        "runtime bridge coverage",
    )?;
    exact_bool(
        coverage,
        "exactRuntimeTestMapping",
        true,
        "runtime bridge coverage",
    )?;
    false_boundary(
        value,
        &[
            "cordovaRuntimeCalibrated",
            "semanticAlignmentVerified",
            "behaviorOracleVerified",
            "independentOracleReviewCompleted",
            "liveVendorIapExecuted",
            "realDeviceExecuted",
            "performanceCalibrated",
            "powerCalibrated",
            "thermalCalibrated",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "runtime bridge",
    )
}

fn validate_profile(input: &Input) -> Result<(), String> {
    let value = &input.value;
    same(
        string(value, "schema", "profile qualification")?,
        PROFILE_SCHEMA,
        "profile qualification schema",
    )?;
    same(string(value, "status", "profile qualification")?, "linux-emulator-functional-and-relative-performance-repeatability-qualified-independent-review-required", "profile qualification status")?;
    same(
        string(value, "candidateRevision", "profile qualification")?,
        CANDIDATE_REVISION,
        "profile candidate revision",
    )?;
    same(
        string(value, "sourceSetSha256", "profile qualification")?,
        RUNTIME_SOURCE_SET,
        "profile source set",
    )?;
    exact_bool(
        value,
        "emulatorRelativePerformanceRepeatabilityQualified",
        true,
        "profile qualification",
    )?;
    let coverage = &value["coverage"];
    exact_u64(coverage, "profileRunCount", 2, "profile coverage")?;
    exact_u64(coverage, "profileSampleCount", 96, "profile coverage")?;
    exact_u64(coverage, "functionalRepeatCount", 12, "profile coverage")?;
    exact_u64(coverage, "functionalAssertionCount", 84, "profile coverage")?;
    false_boundary(
        value,
        &[
            "performanceCalibrated",
            "behaviorOracleVerified",
            "independentOracleReviewCompleted",
            "liveVendorIapExecuted",
            "realDeviceExecuted",
            "absolutePowerThermalQualified",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "profile qualification",
    )
}

fn validate_detector(input: &Input, profile: &Input) -> Result<(), String> {
    let value = &input.value;
    same(
        string(value, "schema", "detector qualification")?,
        DETECTOR_SCHEMA,
        "detector qualification schema",
    )?;
    same(
        string(value, "status", "detector qualification")?,
        "controlled-performance-detector-qualified-independent-review-required",
        "detector qualification status",
    )?;
    same(
        string(value, "candidateRevision", "detector qualification")?,
        CANDIDATE_REVISION,
        "detector candidate revision",
    )?;
    same(
        string(value, "sourceSetSha256", "detector qualification")?,
        RUNTIME_SOURCE_SET,
        "detector source set",
    )?;
    same(
        string(
            &value["artifactSha256"],
            "profileQualification",
            "detector qualification",
        )?,
        &profile.sha256(),
        "detector profile qualification",
    )?;
    exact_bool(
        value,
        "relativePerformanceDetectorCalibrated",
        true,
        "detector qualification",
    )?;
    exact_bool(
        value,
        "controlledMeaningfulWrongFunctionallyQualified",
        true,
        "detector qualification",
    )?;
    let coverage = &value["coverage"];
    exact_u64(coverage, "baselineProfileRunCount", 1, "detector coverage")?;
    exact_u64(
        coverage,
        "controlledWrongProfileRunCount",
        2,
        "detector coverage",
    )?;
    exact_u64(
        coverage,
        "controlledWrongFunctionalRepeatCount",
        12,
        "detector coverage",
    )?;
    exact_u64(
        coverage,
        "controlledWrongFunctionalAssertionCount",
        84,
        "detector coverage",
    )?;
    exact_u64(
        coverage,
        "controlledWrongProfileSampleCount",
        96,
        "detector coverage",
    )?;
    let metrics = value["metrics"]["consistentRegressedMetrics"]
        .as_array()
        .ok_or_else(|| "detector regressed metrics are absent".to_owned())?;
    if metrics.len() != 1 || metrics[0].as_str() != Some("appCpuUsagePercent") {
        return Err("detector regressed metrics differ".into());
    }
    false_boundary(
        value,
        &[
            "distinctBaselineReferenceWrongCaseCalibrationComplete",
            "performanceCalibrated",
            "independentOracleReviewCompleted",
            "liveVendorIapExecuted",
            "realDeviceExecuted",
            "absolutePowerThermalQualified",
            "allowsCaseContract",
            "automaticPromotion",
        ],
        "detector qualification",
    )
}

fn attachment(input: &Input, schema: &str, status: Option<&str>) -> Value {
    let mut value = Map::new();
    value.insert("path".into(), json!(input.relative_path));
    value.insert("schema".into(), json!(schema));
    value.insert("sha256".into(), json!(input.sha256()));
    value.insert("byteLength".into(), json!(input.bytes.len()));
    if let Some(status) = status {
        value.insert("status".into(), json!(status));
    }
    Value::Object(value)
}

fn build(root: &Path) -> Result<Value, String> {
    let inputs = ATTACHMENTS
        .iter()
        .map(|(id, path, _)| Input::load(root, path, id))
        .collect::<Result<Vec<_>, _>>()?;
    let semantic = &inputs[0];
    let plan = &inputs[1];
    let calibration = &inputs[2];
    let source_review = &inputs[3];
    let mutation = &inputs[4];
    let bridge = &inputs[5];
    let profile = &inputs[6];
    let detector = &inputs[7];

    validate_semantic(semantic)?;
    validate_oracle_plan(plan, semantic)?;
    validate_oracle_calibration(calibration, plan, semantic)?;
    validate_source_review(source_review)?;
    validate_mutation(mutation)?;
    validate_runtime_bridge(bridge, plan, calibration, mutation)?;
    validate_profile(profile)?;
    validate_detector(detector, profile)?;

    let mut attachments = Map::new();
    for ((id, _, schema), input) in ATTACHMENTS.iter().zip(&inputs) {
        attachments.insert(
            (*id).into(),
            attachment(input, schema, input.value["status"].as_str()),
        );
    }

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "current-evidence-bound-independent-dual-review-required",
        "semanticCandidateId": SEMANTIC_CANDIDATE,
        "runtimeCandidateId": RUNTIME_CANDIDATE,
        "sourceLineage": {
            "analysisSourceSetSha256": ANALYSIS_SOURCE_SET,
            "runtimeSourceSetSha256": RUNTIME_SOURCE_SET,
            "baseRevision": BASE_REVISION,
            "candidateRevision": CANDIDATE_REVISION
        },
        "evidenceAttachments": attachments,
        "coverage": {
            "repositoryCount": 2,
            "crossRepositoryBehaviorCheckCount": 10,
            "sourceSeamNegativeControlCount": 5,
            "harmonyRuntimeBoundCheckCount": 5,
            "cordovaRuntimeBoundCheckCount": 0,
            "ohosTestCount": 7,
            "functionalMeaningfulWrongVariantCount": 6,
            "functionalKilledMeaningfulWrongVariantCount": 6,
            "functionalMutationScore": 1.0,
            "cleanProfileRunCount": 2,
            "cleanProfileSampleCount": 96,
            "controlledPerformanceWrongRunCount": 2,
            "controlledPerformanceWrongSampleCount": 96,
            "controlledPerformanceWrongFunctionalAssertionCount": 84,
            "consistentRegressedMetrics": ["appCpuUsagePercent"]
        },
        "reviewDecisionContract": {
            "reviewerIdentityAuthority": "authenticated-github-actor-on-trusted-main",
            "minimumDistinctReviewerCount": 2,
            "semanticAndOracleReviewerMustDiffer": true,
            "reviewersMustDifferFromCandidateAuthor": true,
            "approvalRequiresEveryAnswerYes": true,
            "answers": ["yes", "no", "unknown"],
            "verdicts": ["approve-for-next-calibration-gate", "reject-candidate", "defer-for-more-evidence"],
            "questions": [
                {"id": "cross-repository-semantic-coherence", "question": "Do the exact two-repository facts and selected control-flow evidence support one coherent purchase-data behavior contract?"},
                {"id": "source-patch-preservation", "question": "Does the exact source patch preserve intended production behavior while creating a legitimate OHOS Test seam?"},
                {"id": "functional-oracle-discrimination", "question": "Do the seven OHOS Tests and six killed meaningful-wrong variants discriminate the intended Harmony behavior boundaries?"},
                {"id": "runtime-mapping-scope", "question": "Is the mapping from five Harmony source-seam checks to runtime OHOS Tests exact without implying Cordova runtime execution?"},
                {"id": "performance-detector-scope", "question": "Does the retained controlled CPU regression calibrate only the relative detector without being treated as an unseen case or gold repair?"},
                {"id": "residual-boundary-honesty", "question": "Are live vendor IAP, real-device, Cordova runtime, absolute power/thermal and case-level performance calibration correctly left unqualified?"}
            ]
        },
        "risks": [
            {"id": "independent-semantic-review-pending", "statement": "The current semantic packet is exact and reviewable but has not been approved by an authenticated independent reviewer."},
            {"id": "self-authored-source-candidate", "statement": "The OHOS Test source candidate and its review packet remain self-authored until an independent source decision is retained."},
            {"id": "cordova-runtime-source-seam-only", "statement": "All five Cordova behavior checks remain source-seam-only and have no runtime-bound execution evidence."},
            {"id": "live-vendor-iap-unexecuted", "statement": "The retained emulator executions do not contact or qualify the live vendor IAP service."},
            {"id": "x86-emulator-not-real-device", "statement": "Linux x86 emulator evidence does not establish real-device behavior."},
            {"id": "relative-detector-not-case-calibration", "statement": "The controlled performance variant calibrates the relative CPU detector but is not distinct baseline/reference/wrong case calibration."},
            {"id": "absolute-power-thermal-unavailable", "statement": "Absolute power and thermal authority are unavailable in the retained emulator lane."},
            {"id": "upstream-source-unpublished", "statement": "The exact OHOS Test candidate revision has not been published upstream and rebound to a new source identity."}
        ],
        "semanticAlignmentVerified": false,
        "independentSourceReviewCompleted": false,
        "independentOracleReviewCompleted": false,
        "behaviorOracleVerified": false,
        "cordovaRuntimeCalibrated": false,
        "liveVendorIapExecuted": false,
        "realDeviceExecuted": false,
        "relativePerformanceDetectorCalibrated": true,
        "distinctBaselineReferenceWrongCaseCalibrationComplete": false,
        "performanceCalibrated": false,
        "absolutePowerThermalQualified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This packet binds the current semantic, source, functional mutation, runtime mapping, repeatable profile and relative performance-detector evidence into one review input. It does not perform or impersonate independent review, publish source, authorize a case contract, convert controlled variants into Agent runs, or qualify Cordova runtime, live vendor IAP, real-device, absolute power/thermal or distinct case-level performance behavior.",
        "nextGate": "authenticated-distinct-semantic-and-oracle-reviewers-then-upstream-publication-and-distinct-case-performance-calibration"
    }))
}

fn parse_args() -> Result<(PathBuf, PathBuf), String> {
    let mut args = env::args().skip(1);
    let mut root = None;
    let mut output = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--qualification-root" => root = args.next().map(PathBuf::from),
            "--output" => output = args.next().map(PathBuf::from),
            _ => return Err(format!("unknown argument: {arg}")),
        }
    }
    let root = root.ok_or_else(|| "--qualification-root is required".to_owned())?;
    let output = output.ok_or_else(|| "--output is required".to_owned())?;
    if !root.is_dir() || root.is_symlink() {
        return Err("qualification root must be a directory".into());
    }
    if output.exists() || output.is_symlink() {
        return Err("output already exists".into());
    }
    Ok((root, output))
}

fn run() -> Result<(), String> {
    let (root, output) = parse_args()?;
    let value = build(&root)?;
    let parent = output
        .parent()
        .ok_or_else(|| "output parent is absent".to_owned())?;
    if !parent.is_dir() || parent.is_symlink() {
        return Err("output parent must be a directory".into());
    }
    let mut bytes = serde_json::to_vec_pretty(&value)
        .map_err(|error| format!("cannot serialize review packet: {error}"))?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write review packet: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data integrated review packet invalid: {error}");
        std::process::exit(1);
    }
}
