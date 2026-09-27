use agentlab_code_analysis::digest;
use serde_json::{json, Map, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const BEHAVIOR_PLAN_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_plan.v1";
const BEHAVIOR_CALIBRATION_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_calibration.v1";
const OBSERVATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_candidate_observation.v1";
const CANDIDATE_QUALIFICATION_SCHEMA: &str =
    "agentlab.purchase_data_ohostest_candidate_qualification.v1";
const MUTATION_PLAN_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_plan.v1";
const MUTATION_CALIBRATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_calibration.v1";
const MUTATION_QUALIFICATION_SCHEMA: &str =
    "agentlab.purchase_data_ohostest_mutation_qualification.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_runtime_oracle_bridge.v1";

const HARMONY_CHECK_TO_TESTS: &[(&str, &[&str])] = &[
    (
        "harmony-invalid-data-is-not-finished",
        &[
            "missingJwsDoesNotFinish",
            "malformedDataDoesNotFinish",
            "decodeFailureDoesNotFinish",
        ],
    ),
    (
        "harmony-finished-order-is-not-finished-again",
        &["alreadyFinishedPurchaseDoesNotFinishAgain"],
    ),
    (
        "harmony-pending-order-forwards-exact-identity",
        &["pendingPurchaseForwardsExactFinishFields"],
    ),
    (
        "harmony-missing-product-type-blocks-finish",
        &["missingProductTypeBlocksFinish"],
    ),
    (
        "harmony-finish-rejection-is-observable",
        &["finishRejectionRemainsObservable"],
    ),
];

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: PathBuf, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(&path)
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

fn load_bytes(path: PathBuf, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        fs::symlink_metadata(&path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular file"));
    }
    fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))
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

fn string_set(value: &Value, label: &str) -> Result<BTreeSet<String>, String> {
    let rows = value
        .as_array()
        .ok_or_else(|| format!("{label} must be an array"))?;
    let values: BTreeSet<String> = rows
        .iter()
        .map(|row| {
            row.as_str()
                .filter(|item| !item.is_empty())
                .map(str::to_owned)
                .ok_or_else(|| format!("{label} must contain non-empty strings"))
        })
        .collect::<Result<_, _>>()?;
    if values.len() != rows.len() {
        return Err(format!("{label} contains duplicates"));
    }
    Ok(values)
}

fn validate_non_promoting(value: &Value, label: &str) -> Result<(), String> {
    exact_bool(value, "allowsCaseContract", false, label)?;
    exact_bool(value, "automaticPromotion", false, label)
}

struct BridgeInputs<'a> {
    behavior_plan: &'a Input,
    behavior_calibration: &'a Input,
    seam_bytes: &'a [u8],
    observation: &'a Input,
    candidate_qualification: &'a Input,
    mutation_plan: &'a Input,
    mutation_calibration: &'a Input,
    mutation_qualification: &'a Input,
}

fn validate(inputs: BridgeInputs<'_>) -> Result<Value, String> {
    let BridgeInputs {
        behavior_plan,
        behavior_calibration,
        seam_bytes,
        observation,
        candidate_qualification,
        mutation_plan,
        mutation_calibration,
        mutation_qualification,
    } = inputs;

    same(
        string(&behavior_plan.value, "schema", "behavior plan")?,
        BEHAVIOR_PLAN_SCHEMA,
        "behavior plan schema",
    )?;
    exact_bool(
        &behavior_plan.value["qualificationBoundary"],
        "semanticAlignmentApproved",
        false,
        "behavior plan qualification boundary",
    )?;
    exact_bool(
        &behavior_plan.value["qualificationBoundary"],
        "independentOracleReviewCompleted",
        false,
        "behavior plan qualification boundary",
    )?;
    same(
        string(
            &behavior_plan.value,
            "seamExecutableSha256",
            "behavior plan",
        )?,
        &digest(seam_bytes),
        "behavior seam digest",
    )?;

    same(
        string(
            &behavior_calibration.value,
            "schema",
            "behavior calibration",
        )?,
        BEHAVIOR_CALIBRATION_SCHEMA,
        "behavior calibration schema",
    )?;
    same(
        string(
            &behavior_calibration.value,
            "status",
            "behavior calibration",
        )?,
        "source-seam-calibrated-independent-review-required",
        "behavior calibration status",
    )?;
    same(
        string(
            &behavior_calibration.value,
            "planSha256",
            "behavior calibration",
        )?,
        &behavior_plan.sha256(),
        "behavior calibration plan digest",
    )?;
    same(
        string(
            &behavior_calibration.value,
            "seamExecutableSha256",
            "behavior calibration",
        )?,
        &digest(seam_bytes),
        "behavior calibration seam digest",
    )?;
    exact_bool(
        &behavior_calibration.value,
        "sourceSeamCalibrated",
        true,
        "behavior calibration",
    )?;
    exact_bool(
        &behavior_calibration.value["coverage"],
        "exactSourceAllChecksPassed",
        true,
        "behavior calibration coverage",
    )?;
    exact_bool(
        &behavior_calibration.value["coverage"],
        "allNegativeControlsDetected",
        true,
        "behavior calibration coverage",
    )?;
    if behavior_calibration.value["coverage"]["checkCount"].as_u64() != Some(10)
        || behavior_calibration.value["coverage"]["negativeControlCount"].as_u64() != Some(5)
        || behavior_calibration.value["coverage"]["undetectedNegativeControlCount"].as_u64()
            != Some(0)
    {
        return Err("behavior calibration coverage counts differ".into());
    }
    let planned_behavior_variants = behavior_plan.value["variants"]
        .as_array()
        .ok_or_else(|| "behavior plan variants must be an array".to_owned())?;
    let calibrated_behavior_variants = behavior_calibration.value["variants"]
        .as_array()
        .ok_or_else(|| "behavior calibration variants must be an array".to_owned())?;
    if planned_behavior_variants.len() != 6
        || calibrated_behavior_variants.len() != planned_behavior_variants.len()
    {
        return Err("behavior variant inventory differs".into());
    }
    let planned_behavior_variant_ids: BTreeSet<String> = planned_behavior_variants
        .iter()
        .map(|row| string(row, "id", "behavior plan variant").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    let calibrated_behavior_variant_ids: BTreeSet<String> = calibrated_behavior_variants
        .iter()
        .map(|row| string(row, "id", "behavior calibration variant").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    if planned_behavior_variant_ids != calibrated_behavior_variant_ids {
        return Err("behavior variant identities differ".into());
    }
    for variant in calibrated_behavior_variants {
        let id = string(variant, "id", "behavior calibration variant")?;
        exact_bool(
            variant,
            "expectationMatched",
            true,
            &format!("behavior calibration variant {id}"),
        )?;
        let expected = string_set(
            &variant["expectedFailedChecks"],
            &format!("behavior calibration variant {id} expected failures"),
        )?;
        let observed = string_set(
            &variant["observedFailedChecks"],
            &format!("behavior calibration variant {id} observed failures"),
        )?;
        if expected != observed {
            return Err(format!("behavior calibration variant {id} failures differ"));
        }
        match string(variant, "role", "behavior calibration variant")? {
            "exact-source" if expected.is_empty() => {
                let checks = variant["checks"]
                    .as_object()
                    .ok_or_else(|| "exact-source behavior checks must be an object".to_owned())?;
                if checks.len() != 10 || checks.values().any(|value| value.as_bool() != Some(true))
                {
                    return Err("exact-source behavior check results differ".into());
                }
            }
            "meaningful-wrong" if !expected.is_empty() => {}
            _ => return Err(format!("behavior calibration variant {id} role differs")),
        }
    }
    validate_non_promoting(&behavior_calibration.value, "behavior calibration")?;

    same(
        string(&observation.value, "schema", "candidate observation")?,
        OBSERVATION_SCHEMA,
        "candidate observation schema",
    )?;
    validate_non_promoting(&observation.value, "candidate observation")?;
    same(
        string(
            &candidate_qualification.value,
            "schema",
            "candidate qualification",
        )?,
        CANDIDATE_QUALIFICATION_SCHEMA,
        "candidate qualification schema",
    )?;
    same(
        string(
            &candidate_qualification.value,
            "status",
            "candidate qualification",
        )?,
        "candidate-revision-emulator-qualified-independent-review-pending",
        "candidate qualification status",
    )?;
    validate_non_promoting(&candidate_qualification.value, "candidate qualification")?;
    same(
        string(
            &candidate_qualification.value["lineage"],
            "observationSha256",
            "candidate qualification lineage",
        )?,
        &observation.sha256(),
        "candidate observation digest",
    )?;

    let harmony_repository = behavior_plan.value["repositories"]
        .as_array()
        .and_then(|rows| rows.iter().find(|row| row["id"] == "harmony-iap-client"))
        .ok_or_else(|| "behavior plan Harmony repository is absent".to_owned())?;
    for (actual, expected, label) in [
        (
            string(
                &observation.value,
                "sourceRepository",
                "candidate observation",
            )?,
            string(
                harmony_repository,
                "repository",
                "behavior plan Harmony repository",
            )?,
            "Harmony source repository",
        ),
        (
            string(&observation.value, "baseRevision", "candidate observation")?,
            string(
                harmony_repository,
                "revision",
                "behavior plan Harmony repository",
            )?,
            "Harmony base revision",
        ),
        (
            string(
                &candidate_qualification.value,
                "candidateRevision",
                "candidate qualification",
            )?,
            string(
                &observation.value,
                "candidateRevision",
                "candidate observation",
            )?,
            "candidate revision",
        ),
    ] {
        same(actual, expected, label)?;
    }
    if candidate_qualification.value["coverage"]["passed"].as_u64() != Some(7)
        || candidate_qualification.value["coverage"]["testCount"].as_u64() != Some(7)
    {
        return Err("candidate OHOS Test coverage differs".into());
    }
    exact_bool(
        &candidate_qualification.value["coverage"],
        "emulatorExecuted",
        true,
        "candidate qualification coverage",
    )?;

    same(
        string(&mutation_plan.value, "schema", "mutation plan")?,
        MUTATION_PLAN_SCHEMA,
        "mutation plan schema",
    )?;
    validate_non_promoting(&mutation_plan.value, "mutation plan")?;
    same(
        string(
            &mutation_calibration.value,
            "schema",
            "mutation calibration",
        )?,
        MUTATION_CALIBRATION_SCHEMA,
        "mutation calibration schema",
    )?;
    same(
        string(
            &mutation_calibration.value,
            "status",
            "mutation calibration",
        )?,
        "passed",
        "mutation calibration status",
    )?;
    validate_non_promoting(&mutation_calibration.value, "mutation calibration")?;
    same(
        string(
            &mutation_qualification.value,
            "schema",
            "mutation qualification",
        )?,
        MUTATION_QUALIFICATION_SCHEMA,
        "mutation qualification schema",
    )?;
    same(
        string(
            &mutation_qualification.value,
            "status",
            "mutation qualification",
        )?,
        "mutation-discrimination-qualified-source-review-still-required",
        "mutation qualification status",
    )?;
    validate_non_promoting(&mutation_qualification.value, "mutation qualification")?;
    for (actual, expected, label) in [
        (
            string(
                &mutation_qualification.value,
                "mutationPlanSha256",
                "mutation qualification",
            )?,
            mutation_plan.sha256(),
            "mutation plan digest",
        ),
        (
            string(
                &mutation_qualification.value,
                "mutationCalibrationSha256",
                "mutation qualification",
            )?,
            mutation_calibration.sha256(),
            "mutation calibration digest",
        ),
        (
            string(&mutation_plan.value, "baseRevision", "mutation plan")?,
            string(&observation.value, "baseRevision", "candidate observation")?.to_owned(),
            "mutation base revision",
        ),
        (
            string(&mutation_plan.value, "candidateRevision", "mutation plan")?,
            string(
                &observation.value,
                "candidateRevision",
                "candidate observation",
            )?
            .to_owned(),
            "mutation candidate revision",
        ),
    ] {
        same(actual, &expected, label)?;
    }
    exact_bool(
        &mutation_qualification.value,
        "expectedMatrixVerified",
        true,
        "mutation qualification",
    )?;
    if mutation_qualification.value["variantCount"].as_u64() != Some(6)
        || mutation_qualification.value["testCount"].as_u64() != Some(7)
        || mutation_qualification.value["killedVariantCount"].as_u64() != Some(6)
        || mutation_qualification.value["mutationScore"].as_f64() != Some(1.0)
    {
        return Err("mutation qualification coverage differs".into());
    }

    let behavior_checks = behavior_calibration.value["checks"]
        .as_array()
        .ok_or_else(|| "behavior calibration checks must be an array".to_owned())?;
    let behavior_check_ids: BTreeSet<String> = behavior_checks
        .iter()
        .map(|row| string(row, "id", "behavior check").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    let runtime_tests = string_set(&mutation_plan.value["testNames"], "runtime OHOS Tests")?;
    let mut mapped_tests = BTreeSet::new();
    let mut mappings = Vec::new();
    for (check_id, tests) in HARMONY_CHECK_TO_TESTS {
        if !behavior_check_ids.contains(*check_id) {
            return Err(format!(
                "behavior calibration omits Harmony check {check_id}"
            ));
        }
        let expected_tests: BTreeSet<String> =
            tests.iter().map(|value| (*value).to_owned()).collect();
        if !expected_tests.is_subset(&runtime_tests) {
            return Err(format!("runtime test inventory differs for {check_id}"));
        }
        if !mapped_tests.is_disjoint(&expected_tests) {
            return Err("runtime OHOS Test is mapped to multiple behavior checks".into());
        }
        mapped_tests.extend(expected_tests.iter().cloned());
        let killing_variants: BTreeSet<String> = tests
            .iter()
            .flat_map(|test| {
                mutation_plan.value["coverage"]["testToExpectedKillingVariants"][test]
                    .as_array()
                    .into_iter()
                    .flatten()
            })
            .map(|value| {
                value
                    .as_str()
                    .filter(|item| !item.is_empty())
                    .map(str::to_owned)
                    .ok_or_else(|| format!("killing variant is invalid for {check_id}"))
            })
            .collect::<Result<_, _>>()?;
        if killing_variants.is_empty() {
            return Err(format!("no meaningful wrong variant covers {check_id}"));
        }
        mappings.push(json!({
            "behaviorCheckId": check_id,
            "ohosTestNames": tests,
            "observedKillingVariantIds": killing_variants,
            "sourceSeamPassed": true,
            "runtimeCandidatePassed": true,
            "meaningfulWrongVariantsKilled": true
        }));
    }
    if mapped_tests != runtime_tests {
        return Err("runtime OHOS Test mapping is not exact".into());
    }

    let harmony_check_ids: BTreeSet<String> = behavior_check_ids
        .iter()
        .filter(|id| id.starts_with("harmony-"))
        .cloned()
        .collect();
    let cordova_check_ids: BTreeSet<String> = behavior_check_ids
        .iter()
        .filter(|id| id.starts_with("cordova-"))
        .cloned()
        .collect();
    if harmony_check_ids.len() != HARMONY_CHECK_TO_TESTS.len() || cordova_check_ids.len() != 5 {
        return Err("cross-repository behavior check partition differs".into());
    }

    let mut artifact_sha256 = Map::new();
    for (key, value) in [
        ("behaviorPlan", behavior_plan.sha256()),
        ("behaviorCalibration", behavior_calibration.sha256()),
        ("behaviorSeamExecutable", digest(seam_bytes)),
        ("candidateObservation", observation.sha256()),
        ("candidateQualification", candidate_qualification.sha256()),
        ("mutationPlan", mutation_plan.sha256()),
        ("mutationCalibration", mutation_calibration.sha256()),
        ("mutationQualification", mutation_qualification.sha256()),
    ] {
        artifact_sha256.insert(key.to_owned(), Value::String(value));
    }

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "harmony-runtime-oracle-bridge-qualified-independent-review-required",
        "semanticCandidateId": behavior_plan.value["candidateId"],
        "runtimeCandidateId": mutation_plan.value["candidateId"],
        "sourceRepository": observation.value["sourceRepository"],
        "baseRevision": observation.value["baseRevision"],
        "candidateRevision": observation.value["candidateRevision"],
        "candidateSourceSha256": mutation_plan.value["source"]["sha256"],
        "artifactSha256": artifact_sha256,
        "coverage": {
            "crossRepositoryBehaviorCheckCount": behavior_check_ids.len(),
            "sourceSeamNegativeControlCount": 5,
            "harmonyBehaviorCheckCount": harmony_check_ids.len(),
            "harmonyRuntimeBoundCheckCount": mappings.len(),
            "cordovaBehaviorCheckCount": cordova_check_ids.len(),
            "cordovaRuntimeBoundCheckCount": 0,
            "ohosTestCount": runtime_tests.len(),
            "runtimeMutationVariantCount": 6,
            "runtimeKilledMutationVariantCount": 6,
            "runtimeMutationScore": 1.0,
            "exactRuntimeTestMapping": true,
            "exactObservedMutationMatrix": true
        },
        "harmonyRuntimeMappings": mappings,
        "execution": {
            "framework": "instrument-test-ohosTest-hypium",
            "host": "hwlinux",
            "linuxX86EmulatorExecuted": true,
            "candidatePassed": true,
            "sourceVariantsBuilt": true,
            "meaningfulWrongVariantsExecuted": true,
            "candidateSourceRestored": true,
            "worktreeCleanAfterExecution": true
        },
        "semanticAlignmentVerified": false,
        "independentOracleReviewCompleted": false,
        "behaviorOracleVerified": false,
        "cordovaRuntimeCalibrated": false,
        "liveVendorIapExecuted": false,
        "realDeviceExecuted": false,
        "performanceCalibrated": false,
        "powerCalibrated": false,
        "thermalCalibrated": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This bridge binds five source-seam Harmony behavior checks to seven OHOS Tests and six observed meaningful-wrong variants executed on one Linux x86 emulator. It does not runtime-calibrate the five Cordova checks, execute live vendor IAP, prove a real device, complete independent semantic or Oracle review, qualify performance/power/thermal behavior, approve a case contract or publish source upstream.",
        "nextGate": "independent-semantic-and-oracle-review-then-upstream-publication-and-exact-revision-reexecution"
    }))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut values = std::collections::BTreeMap::new();
    while let Some(flag) = args.next() {
        let argument = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        values.insert(flag, PathBuf::from(argument));
    }
    let get = |flag: &str| {
        values
            .get(flag)
            .cloned()
            .ok_or_else(|| format!("missing {flag}"))
    };
    let behavior_plan = Input::load(get("--behavior-plan")?, "behavior plan")?;
    let behavior_calibration = Input::load(get("--behavior-calibration")?, "behavior calibration")?;
    let seam_bytes = load_bytes(get("--behavior-seam")?, "behavior seam")?;
    let observation = Input::load(get("--candidate-observation")?, "candidate observation")?;
    let candidate_qualification =
        Input::load(get("--candidate-qualification")?, "candidate qualification")?;
    let mutation_plan = Input::load(get("--mutation-plan")?, "mutation plan")?;
    let mutation_calibration = Input::load(get("--mutation-calibration")?, "mutation calibration")?;
    let mutation_qualification =
        Input::load(get("--mutation-qualification")?, "mutation qualification")?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let result = validate(BridgeInputs {
        behavior_plan: &behavior_plan,
        behavior_calibration: &behavior_calibration,
        seam_bytes: &seam_bytes,
        observation: &observation,
        candidate_qualification: &candidate_qualification,
        mutation_plan: &mutation_plan,
        mutation_calibration: &mutation_calibration,
        mutation_qualification: &mutation_qualification,
    })?;
    let mut bytes = serde_json::to_vec_pretty(&result).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data runtime Oracle bridge invalid: {error}");
        std::process::exit(1);
    }
}
