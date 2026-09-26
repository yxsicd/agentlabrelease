use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::PathBuf;

const GATE_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_gate.v1";
const BEHAVIOR_PLAN_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_plan.v1";
const CALIBRATION_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_calibration.v1";
const OHOSTEST_PROPOSAL_SCHEMA: &str = "agentlab.purchase_data_ohostest_proposal.v1";
const CLOSURE_SCHEMA: &str = "agentlab.release_closure.v1";
const TARGET_SCHEMA: &str = "agentlab.target_descriptor.v1";
const REGISTRY_SCHEMA: &str = "agentlab.component_registry.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_runtime_calibration_plan.v1";

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
        let bytes = fs::read(&path).map_err(|error| format!("cannot read {label}: {error}"))?;
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

fn exact_bool(value: &Value, key: &str, expected: bool, label: &str) -> Result<(), String> {
    if value[key].as_bool() != Some(expected) {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}

fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn ensure_same(actual: &str, expected: &str, label: &str) -> Result<(), String> {
    if actual != expected {
        return Err(format!("{label} differs"));
    }
    Ok(())
}

fn array_strings(value: &Value, key: &str, label: &str) -> Result<BTreeSet<String>, String> {
    let rows = value[key]
        .as_array()
        .ok_or_else(|| format!("{label} {key} must be an array"))?;
    rows.iter()
        .map(|row| {
            row.as_str()
                .map(str::to_owned)
                .ok_or_else(|| format!("{label} {key} must contain strings"))
        })
        .collect()
}

fn validate_gate(gate: &Value) -> Result<(), String> {
    ensure_same(
        string(gate, "schema", "Oracle gate")?,
        GATE_SCHEMA,
        "Oracle gate schema",
    )?;
    ensure_same(
        string(gate, "status", "Oracle gate")?,
        "approved-for-runtime-calibration",
        "Oracle gate status",
    )?;
    ensure_same(
        string(gate, "verdict", "Oracle gate")?,
        "approve-for-runtime-calibration",
        "Oracle gate verdict",
    )?;
    ensure_same(
        string(gate, "nextGate", "Oracle gate")?,
        "runtime-calibration-and-independent-runtime-oracle-validation",
        "Oracle gate next gate",
    )?;
    exact_bool(gate, "semanticAlignmentVerified", true, "Oracle gate")?;
    exact_bool(gate, "behaviorOracleCandidateReviewed", true, "Oracle gate")?;
    exact_bool(gate, "behaviorOracleVerified", false, "Oracle gate")?;
    exact_bool(gate, "allowsRuntimeCalibration", true, "Oracle gate")?;
    exact_bool(gate, "allowsCaseContract", false, "Oracle gate")?;
    exact_bool(gate, "automaticPromotion", false, "Oracle gate")?;
    let semantic = string(gate, "semanticReviewer", "Oracle gate")?;
    let oracle = string(gate, "oracleReviewer", "Oracle gate")?;
    if !semantic.starts_with("github:") || !oracle.starts_with("github:") || semantic == oracle {
        return Err("Oracle gate reviewers are not distinct GitHub identities".into());
    }
    Ok(())
}

fn validate_behavior_lineage(
    gate: &Input,
    plan: &Input,
    calibration: &Input,
) -> Result<(), String> {
    ensure_same(
        string(&plan.value, "schema", "behavior plan")?,
        BEHAVIOR_PLAN_SCHEMA,
        "behavior plan schema",
    )?;
    ensure_same(
        string(&calibration.value, "schema", "behavior calibration")?,
        CALIBRATION_SCHEMA,
        "behavior calibration schema",
    )?;
    ensure_same(
        string(&gate.value, "planSha256", "Oracle gate")?,
        &plan.sha256(),
        "Oracle gate plan digest",
    )?;
    ensure_same(
        string(&gate.value, "calibrationSha256", "Oracle gate")?,
        &calibration.sha256(),
        "Oracle gate calibration digest",
    )?;
    ensure_same(
        string(&calibration.value, "planSha256", "behavior calibration")?,
        &plan.sha256(),
        "behavior calibration plan digest",
    )?;
    for key in ["candidateId", "sourceSetSha256", "methodRevision"] {
        let expected = string(&gate.value, key, "Oracle gate")?;
        ensure_same(
            string(&plan.value, key, "behavior plan")?,
            expected,
            &format!("behavior plan {key}"),
        )?;
        ensure_same(
            string(&calibration.value, key, "behavior calibration")?,
            expected,
            &format!("behavior calibration {key}"),
        )?;
    }
    exact_bool(
        &calibration.value,
        "sourceSeamCalibrated",
        true,
        "behavior calibration",
    )?;
    exact_bool(
        &calibration.value,
        "behaviorOracleVerified",
        false,
        "behavior calibration",
    )?;
    exact_bool(
        &calibration.value,
        "allowsCaseContract",
        false,
        "behavior calibration",
    )?;
    exact_bool(
        &calibration.value,
        "automaticPromotion",
        false,
        "behavior calibration",
    )?;
    let coverage = &calibration.value["coverage"];
    let expected_numbers = [
        ("repositoryCount", 2),
        ("methodCount", 5),
        ("checkCount", 10),
        ("negativeControlCount", 5),
        ("undetectedNegativeControlCount", 0),
    ];
    for (key, expected) in expected_numbers {
        if coverage[key].as_u64() != Some(expected) {
            return Err(format!("behavior calibration coverage {key} differs"));
        }
    }
    exact_bool(
        coverage,
        "exactSourceAllChecksPassed",
        true,
        "behavior calibration coverage",
    )?;
    exact_bool(
        coverage,
        "allNegativeControlsDetected",
        true,
        "behavior calibration coverage",
    )?;
    Ok(())
}

fn validate_ohostest_proposal(
    gate: &Input,
    behavior_plan: &Input,
    proposal: &Input,
) -> Result<bool, String> {
    ensure_same(
        string(&proposal.value, "schema", "OHOS Test proposal")?,
        OHOSTEST_PROPOSAL_SCHEMA,
        "OHOS Test proposal schema",
    )?;
    let status = string(&proposal.value, "status", "OHOS Test proposal")?;
    let testability_blocked = match status {
        "testability-refactor-required-before-standard-test-authoring" => true,
        "source-bound-ohostest-ready-for-execution" => false,
        _ => return Err("OHOS Test proposal status differs".into()),
    };
    for key in ["candidateId", "sourceSetSha256"] {
        ensure_same(
            string(&proposal.value, key, "OHOS Test proposal")?,
            string(&gate.value, key, "Oracle gate")?,
            &format!("OHOS Test proposal {key}"),
        )?;
    }
    ensure_same(
        string(
            &proposal.value["lineage"],
            "behaviorPlanSha256",
            "OHOS Test proposal lineage",
        )?,
        &behavior_plan.sha256(),
        "OHOS Test proposal behavior plan digest",
    )?;
    let lane = &proposal.value["observedStandardLane"];
    ensure_same(
        string(lane, "framework", "OHOS Test proposal lane")?,
        "instrument-test-ohosTest-hypium",
        "OHOS Test proposal framework",
    )?;
    exact_bool(lane, "buildTargetDeclared", true, "OHOS Test proposal lane")?;
    exact_bool(
        lane,
        "hypiumDependencyDeclared",
        true,
        "OHOS Test proposal lane",
    )?;
    let source_test_count = lane["sourceTestCount"]
        .as_u64()
        .ok_or_else(|| "OHOS Test proposal source test count is absent".to_string())?;
    let source_test_paths =
        array_strings(lane, "existingTestSourcePaths", "OHOS Test proposal lane")?;
    if (testability_blocked && (source_test_count != 0 || !source_test_paths.is_empty()))
        || (!testability_blocked
            && (source_test_count == 0 || source_test_count as usize != source_test_paths.len()))
    {
        return Err("OHOS Test proposal source test inventory differs".into());
    }
    let checks = array_strings(
        &proposal.value,
        "blockedBehaviorCheckIds",
        "OHOS Test proposal",
    )?;
    if checks.len() != 5 {
        return Err("OHOS Test proposal blocked check inventory differs".into());
    }
    let boundary = &proposal.value["qualificationBoundary"];
    exact_bool(
        boundary,
        "ohosTestSourceAuthored",
        !testability_blocked,
        "OHOS Test proposal boundary",
    )?;
    for key in [
        "ohosTestExecuted",
        "emulatorExecuted",
        "behaviorOracleVerified",
        "allowsRuntimeCalibration",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(boundary, key, false, "OHOS Test proposal boundary")?;
    }
    Ok(testability_blocked)
}

fn validate_target(target: &Input) -> Result<(), String> {
    ensure_same(
        string(&target.value, "schema", "target")?,
        TARGET_SCHEMA,
        "target schema",
    )?;
    ensure_same(
        string(&target.value, "id", "target")?,
        "generic-linux",
        "target id",
    )?;
    ensure_same(
        string(&target.value, "platform", "target")?,
        "linux-x64",
        "target platform",
    )?;
    let emulator = &target.value["emulatorSupport"];
    ensure_same(
        string(emulator, "status", "emulator support")?,
        "experimental",
        "emulator status",
    )?;
    ensure_same(
        string(emulator, "platform", "emulator support")?,
        "linux-x64",
        "emulator platform",
    )?;
    ensure_same(
        string(emulator, "acceleration", "emulator support")?,
        "kvm",
        "emulator acceleration",
    )?;
    ensure_same(
        string(emulator, "imageAbi", "emulator support")?,
        "x86",
        "emulator image ABI",
    )?;
    if !array_strings(emulator, "requiredHostFeatures", "emulator support")?.contains("/dev/kvm") {
        return Err("emulator support does not require /dev/kvm".into());
    }
    let operations = array_strings(emulator, "qualifiedOperations", "emulator support")?;
    for required in [
        "hdc-install-launch-probe",
        "smartperf-proxy-profile",
        "declarative-ui-layout-oracle",
        "evaluation-instance-export",
    ] {
        if !operations.contains(required) {
            return Err(format!("emulator operation is not qualified: {required}"));
        }
    }
    if !array_strings(emulator, "remainingGates", "emulator support")?
        .contains("application-specific-oracle-calibration")
    {
        return Err("target hides the application-specific Oracle gate".into());
    }
    Ok(())
}

fn validate_release_assets(closure: &Input, registry: &Input) -> Result<Vec<Value>, String> {
    ensure_same(
        string(&closure.value, "schema", "release closure")?,
        CLOSURE_SCHEMA,
        "release closure schema",
    )?;
    ensure_same(
        string(&closure.value, "status", "release closure")?,
        "developer-preview-candidate",
        "release closure status",
    )?;
    ensure_same(
        string(&registry.value, "schema", "component registry")?,
        REGISTRY_SCHEMA,
        "component registry schema",
    )?;
    ensure_same(
        string(
            &closure.value["componentRegistry"],
            "sha256",
            "closure component registry",
        )?,
        &registry.sha256(),
        "component registry digest",
    )?;
    let target = &closure.value["targetCompatibility"]["hwlinux-emulator"];
    ensure_same(
        string(target, "platform", "closure emulator target")?,
        "linux-x64",
        "closure emulator platform",
    )?;
    ensure_same(
        string(target, "status", "closure emulator target")?,
        "experimental",
        "closure emulator status",
    )?;
    if !array_strings(target, "deploymentModes", "closure emulator target")?
        .contains("x86-kvm-emulator")
    {
        return Err("release closure lacks x86 KVM emulator deployment".into());
    }

    let required_kinds = BTreeSet::from([
        "harmony-emulator-manifest",
        "harmony-emulator-tools",
        "harmony-system-image",
    ]);
    let closure_assets = closure.value["assets"]
        .as_array()
        .ok_or_else(|| "release closure assets are absent".to_string())?;
    let selected: Vec<_> = closure_assets
        .iter()
        .filter(|row| {
            row["kind"]
                .as_str()
                .is_some_and(|kind| required_kinds.contains(kind))
        })
        .collect();
    if selected.len() != 3 {
        return Err("release closure must bind exactly three emulator assets".into());
    }
    let immutable_refs: BTreeSet<_> = selected
        .iter()
        .map(|row| string(row, "immutableRef", "closure asset"))
        .collect::<Result<_, _>>()?;
    if immutable_refs.len() != 1 {
        return Err("emulator assets do not share one immutable reference".into());
    }
    let registry_components = registry.value["components"]
        .as_array()
        .ok_or_else(|| "component registry components are absent".to_string())?;
    let mut result = Vec::new();
    for asset in selected {
        let asset_id = string(asset, "id", "closure asset")?;
        let component_id = string(asset, "registryComponent", "closure asset")?;
        let sha256 = string(asset, "sha256", "closure asset")?;
        if !valid_sha(sha256) || asset["bytes"].as_u64().filter(|bytes| *bytes > 0).is_none() {
            return Err(format!("closure asset identity is invalid: {asset_id}"));
        }
        let component = registry_components
            .iter()
            .find(|row| row["id"] == component_id)
            .ok_or_else(|| format!("registry component is absent: {component_id}"))?;
        ensure_same(
            string(component, "status", "registry component")?,
            "selected",
            "registry component status",
        )?;
        ensure_same(
            string(component, "immutableRef", "registry component")?,
            string(asset, "immutableRef", "closure asset")?,
            "registry immutable reference",
        )?;
        let registry_asset = component["assets"]
            .as_array()
            .and_then(|rows| rows.iter().find(|row| row["id"] == asset_id))
            .ok_or_else(|| format!("registry asset is absent: {asset_id}"))?;
        for key in ["url", "sha256", "bytes"] {
            if registry_asset[key] != asset[key] {
                return Err(format!("registry asset {key} differs: {asset_id}"));
            }
        }
        result.push(json!({
            "id": asset_id,
            "kind": asset["kind"],
            "registryComponent": component_id,
            "immutableRef": asset["immutableRef"],
            "sha256": sha256,
            "bytes": asset["bytes"],
            "url": asset["url"],
        }));
    }
    result.sort_by_key(|row| row["id"].as_str().unwrap_or_default().to_owned());
    Ok(result)
}

fn build_plan(
    gate: &Input,
    behavior_plan: &Input,
    calibration: &Input,
    ohostest_proposal: &Input,
    closure: &Input,
    target: &Input,
    registry: &Input,
) -> Result<Value, String> {
    validate_gate(&gate.value)?;
    validate_behavior_lineage(gate, behavior_plan, calibration)?;
    let testability_blocked = validate_ohostest_proposal(gate, behavior_plan, ohostest_proposal)?;
    validate_target(target)?;
    let assets = validate_release_assets(closure, registry)?;
    let checks = behavior_plan.value["checks"]
        .as_array()
        .ok_or_else(|| "behavior plan checks are absent".to_string())?;
    let check_ids: Vec<_> = checks
        .iter()
        .map(|row| string(row, "id", "behavior check").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    if check_ids.len() != 10 || check_ids.iter().collect::<BTreeSet<_>>().len() != 10 {
        return Err("runtime behavior check inventory differs".into());
    }
    let first_stage_status = if testability_blocked {
        "blocked-testability-refactor-required"
    } else {
        "planned-not-executed"
    };
    let downstream_status = if testability_blocked {
        "blocked-upstream-stage"
    } else {
        "planned-not-executed"
    };
    let status = if testability_blocked {
        "runtime-calibration-blocked-testability-refactor-required"
    } else {
        "runtime-calibration-planned-not-executed"
    };
    let next_gate = if testability_blocked {
        "implement-reviewed-testability-refactor-author-ohostest-then-regenerate-runtime-plan"
    } else {
        "execute-all-stages-and-independently-validate-runtime-receipts"
    };
    let stages = vec![
        json!({
            "id":"source-build-and-standard-test-authoring",
            "status":first_stage_status,
            "requiredEvidence":["exact-source-build-receipt","ohostest-source-contract","native-test-execution-receipt"],
            "authority":"exact-git-revisions-and-ohostest"
        }),
        json!({
            "id":"linux-emulator-functional-calibration",
            "status":downstream_status,
            "requiredEvidence":["kvm-preflight","hap-install","process-launch","bounded-runtime-oracle-receipt"],
            "checkIds":check_ids,
            "authority":"x86-kvm-harmony-emulator"
        }),
        json!({
            "id":"repeat-performance-profile",
            "status":downstream_status,
            "requiredEvidence":["functional-pass","smartperf-baseline","smartperf-candidate","repeat-comparison"],
            "observedMetrics":["cpu","pss","fps"],
            "absolutePowerThermal":"unavailable-on-emulator"
        }),
    ];
    Ok(json!({
        "schema":OUTPUT_SCHEMA,
        "status":status,
        "candidateId":gate.value["candidateId"],
        "sourceSetSha256":gate.value["sourceSetSha256"],
        "methodRevision":gate.value["methodRevision"],
        "lineage":{
            "oracleGateSha256":gate.sha256(),
            "behaviorPlanSha256":behavior_plan.sha256(),
            "behaviorCalibrationSha256":calibration.sha256(),
            "ohosTestProposalSha256":ohostest_proposal.sha256(),
            "releaseClosureSha256":closure.sha256(),
            "targetDescriptorSha256":target.sha256(),
            "componentRegistrySha256":registry.sha256()
        },
        "release":{
            "version":closure.value["releaseVersion"],
            "tag":closure.value["releaseTag"],
            "status":closure.value["status"],
            "targetId":target.value["id"],
            "componentRegistrySchema":registry.value["schema"]
        },
        "environment":{
            "platform":"linux-x64",
            "architecture":"x86_64",
            "acceleration":"kvm",
            "requiredHostFeatures":["/dev/kvm"],
            "imageAbi":"x86"
        },
        "immutableAssets":assets,
        "stages":stages,
        "execution":{
            "sourceBuildExecuted":false,
            "ohosTestExecuted":false,
            "emulatorExecuted":false,
            "functionalOracleVerified":false,
            "performanceProfileExecuted":false
        },
        "behaviorOracleVerified":false,
        "allowsCaseContract":false,
        "automaticPromotion":false,
        "nextGate":next_gate
    }))
}

fn arguments() -> Result<BTreeMap<String, PathBuf>, String> {
    let mut values = BTreeMap::new();
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        if !flag.starts_with("--") {
            return Err(format!("unexpected argument: {flag}"));
        }
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), PathBuf::from(value)).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    for required in [
        "--oracle-gate",
        "--behavior-plan",
        "--behavior-calibration",
        "--ohostest-proposal",
        "--release-closure",
        "--target",
        "--component-registry",
        "--output",
    ] {
        if !values.contains_key(required) {
            return Err(format!("missing required argument: {required}"));
        }
    }
    if values.len() != 8 {
        return Err("unknown runtime-plan argument".into());
    }
    Ok(values)
}

fn run() -> Result<(), String> {
    let args = arguments()?;
    let output = &args["--output"];
    if output.exists() {
        return Err(format!(
            "refusing to overwrite output: {}",
            output.display()
        ));
    }
    let gate = Input::load(args["--oracle-gate"].clone(), "Oracle gate")?;
    let behavior_plan = Input::load(args["--behavior-plan"].clone(), "behavior plan")?;
    let calibration = Input::load(
        args["--behavior-calibration"].clone(),
        "behavior calibration",
    )?;
    let ohostest_proposal = Input::load(args["--ohostest-proposal"].clone(), "OHOS Test proposal")?;
    let closure = Input::load(args["--release-closure"].clone(), "release closure")?;
    let target = Input::load(args["--target"].clone(), "target descriptor")?;
    let registry = Input::load(args["--component-registry"].clone(), "component registry")?;
    let plan = build_plan(
        &gate,
        &behavior_plan,
        &calibration,
        &ohostest_proposal,
        &closure,
        &target,
        &registry,
    )?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create output directory: {error}"))?;
    }
    let mut bytes = serde_json::to_vec_pretty(&plan).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, &bytes).map_err(|error| format!("cannot write output: {error}"))?;
    println!(
        "{}",
        json!({
            "ok":true,
            "status":plan["status"],
            "outputSha256":digest(&bytes),
            "stageCount":plan["stages"].as_array().map_or(0, Vec::len)
        })
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data runtime calibration plan invalid: {error}");
        std::process::exit(1);
    }
}
