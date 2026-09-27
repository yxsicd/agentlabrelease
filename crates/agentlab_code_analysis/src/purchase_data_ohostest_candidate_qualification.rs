use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const REFERENCE_SCHEMA: &str = "agentlab.purchase_data_ohostest_reference_qualification.v1";
const RECEIPT_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const REPORT_SCHEMA: &str = "agentlab.harmony_hypium_native_report.v1";
const OBSERVATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_candidate_observation.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_candidate_qualification.v1";

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

fn valid_lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn require_sha(value: &Value, key: &str, label: &str) -> Result<String, String> {
    let sha = string(value, key, label)?;
    if !valid_lower_hex(sha, 64) {
        return Err(format!("{label} {key} is not a lowercase SHA-256"));
    }
    Ok(sha.to_owned())
}

fn require_revision(value: &Value, key: &str, label: &str) -> Result<String, String> {
    let revision = string(value, key, label)?;
    if !valid_lower_hex(revision, 40) {
        return Err(format!("{label} {key} is not a lowercase Git revision"));
    }
    Ok(revision.to_owned())
}

fn exact_strings(value: &Value, expected: &[&str], label: &str) -> Result<(), String> {
    let rows = value
        .as_array()
        .ok_or_else(|| format!("{label} must be an array"))?;
    let actual: BTreeSet<&str> = rows
        .iter()
        .map(|row| {
            row.as_str()
                .ok_or_else(|| format!("{label} must contain strings"))
        })
        .collect::<Result<_, _>>()?;
    let expected: BTreeSet<&str> = expected.iter().copied().collect();
    if rows.len() != expected.len() || actual != expected {
        return Err(format!("{label} differs"));
    }
    Ok(())
}

fn validate(
    reference: &Input,
    receipt: &Input,
    report: &Input,
    observation: &Input,
) -> Result<Value, String> {
    same(
        string(&reference.value, "schema", "reference qualification")?,
        REFERENCE_SCHEMA,
        "reference qualification schema",
    )?;
    same(
        string(&reference.value, "status", "reference qualification")?,
        "reference-testability-refactor-emulator-qualified-upstream-change-required",
        "reference qualification status",
    )?;
    exact_bool(
        &reference.value,
        "referencePatchOnly",
        true,
        "reference qualification",
    )?;
    exact_bool(
        &reference.value,
        "upstreamRevisionModified",
        false,
        "reference qualification",
    )?;

    same(
        string(&receipt.value, "schema", "execution receipt")?,
        RECEIPT_SCHEMA,
        "execution receipt schema",
    )?;
    same(
        string(&receipt.value, "caseId", "execution receipt")?,
        "purchase-data-finalization-candidate-clean-v1",
        "execution receipt case",
    )?;
    same(
        string(&receipt.value, "framework", "execution receipt")?,
        "instrument-test-ohosTest-hypium",
        "execution receipt framework",
    )?;
    same(
        string(&receipt.value, "status", "execution receipt")?,
        "passed",
        "execution receipt status",
    )?;
    exact_bool(&receipt.value, "passed", true, "execution receipt")?;
    exact_bool(
        &receipt.value,
        "automaticPromotion",
        false,
        "execution receipt",
    )?;

    same(
        string(&report.value, "schema", "native report")?,
        REPORT_SCHEMA,
        "native report schema",
    )?;
    exact_bool(&report.value, "passed", true, "native report")?;
    exact_bool(&report.value, "timedOut", false, "native report")?;
    for (key, expected) in [
        ("total", 7),
        ("pass", 7),
        ("failure", 0),
        ("error", 0),
        ("ignore", 0),
    ] {
        if report.value["counts"][key].as_u64() != Some(expected) {
            return Err(format!("native report count {key} differs"));
        }
    }
    if report.value["nativeFinalCode"].as_i64() != Some(0)
        || report.value["processExitCode"].as_i64() != Some(0)
    {
        return Err("native or process final code differs".into());
    }
    if !matches!(report.value["failureReasons"].as_array(), Some(reasons) if reasons.is_empty()) {
        return Err("native report failure reasons differ".into());
    }
    same(
        string(&receipt.value["report"], "sha256", "receipt report")?,
        &report.sha256(),
        "receipt native report digest",
    )?;

    same(
        string(&observation.value, "schema", "candidate observation")?,
        OBSERVATION_SCHEMA,
        "candidate observation schema",
    )?;
    same(
        string(
            &observation.value,
            "sourceRepository",
            "candidate observation",
        )?,
        "https://gitcode.com/HarmonyOS_Samples/iapkit-sample-clientdemo-arkts.git",
        "candidate source repository",
    )?;
    same(
        string(
            &observation.value,
            "candidateBranch",
            "candidate observation",
        )?,
        "agentlab/purchase-data-ohostest-candidate-v1",
        "candidate branch",
    )?;
    let base_revision = require_revision(&observation.value, "baseRevision", "observation")?;
    let parent_revision = require_revision(&observation.value, "parentRevision", "observation")?;
    let candidate_revision =
        require_revision(&observation.value, "candidateRevision", "observation")?;
    same(
        &parent_revision,
        &base_revision,
        "candidate parent revision",
    )?;
    if candidate_revision == base_revision {
        return Err("candidate revision did not advance from its base".into());
    }
    same(
        string(
            &observation.value["executionBinding"],
            "status",
            "candidate execution binding",
        )?,
        "exact-clean-git-candidate-revision",
        "candidate execution binding status",
    )?;
    same(
        string(
            &observation.value["executionBinding"],
            "sourceRevision",
            "candidate execution binding",
        )?,
        &candidate_revision,
        "candidate execution source revision",
    )?;
    exact_bool(
        &observation.value["executionBinding"],
        "worktreeCleanBeforeBuild",
        true,
        "candidate execution binding",
    )?;
    exact_bool(
        &observation.value["executionBinding"],
        "worktreeCleanAfterExecution",
        true,
        "candidate execution binding",
    )?;
    same(
        &base_revision,
        string(&reference.value, "baseRevision", "reference qualification")?,
        "candidate base revision",
    )?;
    let candidate_patch = require_sha(
        &observation.value,
        "candidatePatchSha256",
        "candidate observation",
    )?;
    same(
        &candidate_patch,
        string(
            &observation.value,
            "sourceSetSha256",
            "candidate observation",
        )?,
        "candidate patch source-set identity",
    )?;
    same(
        &candidate_patch,
        string(&receipt.value, "sourceSetSha256", "execution receipt")?,
        "execution source-set identity",
    )?;
    same(
        string(&observation.value["review"], "status", "candidate review")?,
        "self-reviewed-candidate-independent-review-pending",
        "candidate review status",
    )?;
    exact_bool(
        &observation.value["review"],
        "independentReviewVerified",
        false,
        "candidate review",
    )?;
    for key in [
        "publishedToUpstream",
        "behaviorOracleVerified",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(&observation.value, key, false, "candidate observation")?;
    }
    exact_strings(
        &observation.value["review"]["addedBoundaryTests"],
        &["missingJwsDoesNotFinish", "decodeFailureDoesNotFinish"],
        "candidate review boundary tests",
    )?;
    exact_strings(
        &observation.value["testNames"],
        &[
            "missingJwsDoesNotFinish",
            "malformedDataDoesNotFinish",
            "decodeFailureDoesNotFinish",
            "alreadyFinishedPurchaseDoesNotFinishAgain",
            "pendingPurchaseForwardsExactFinishFields",
            "missingProductTypeBlocksFinish",
            "finishRejectionRemainsObservable",
        ],
        "candidate OHOS Test inventory",
    )?;
    for package in ["app", "test"] {
        let package_value = &receipt.value["packages"][package];
        require_sha(package_value, "sha256", "execution package")?;
        if package_value["byteLength"].as_u64().unwrap_or(0) == 0 {
            return Err(format!("execution {package} package is empty"));
        }
    }
    let project_tree_sha = require_sha(&receipt.value, "projectTreeSha256", "execution receipt")?;
    same(
        &project_tree_sha,
        string(
            &observation.value["executionBinding"],
            "projectTreeSha256",
            "candidate execution binding",
        )?,
        "candidate clean project tree digest",
    )?;

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "candidate-revision-emulator-qualified-independent-review-pending",
        "sourceRepository": observation.value["sourceRepository"],
        "baseRevision": base_revision,
        "candidateRevision": candidate_revision,
        "candidatePatchSha256": candidate_patch,
        "projectTreeSha256": project_tree_sha,
        "framework": receipt.value["framework"],
        "coverage": {
            "testCount": 7,
            "passed": 7,
            "failure": 0,
            "error": 0,
            "ignore": 0,
            "mainHapBuilt": true,
            "ohosTestHapBuilt": true,
            "emulatorExecuted": true,
            "emulatorStopped": true
        },
        "lineage": {
            "referenceQualificationSha256": reference.sha256(),
            "executionReceiptSha256": receipt.sha256(),
            "nativeReportSha256": report.sha256(),
            "observationSha256": observation.sha256()
        },
        "packages": receipt.value["packages"],
        "testNames": observation.value["testNames"],
        "publishedToUpstream": false,
        "independentReviewVerified": false,
        "behaviorOracleVerified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This qualifies one local Git candidate revision and seven source-bound OHOS Test cases on the Linux x86 emulator. It does not publish the candidate upstream, substitute self-review for independent review, validate live IAP service behavior, approve the cross-repository semantic claim, or authorize case promotion.",
        "nextGate": "independent-review-then-upstream-publication-and-exact-revision-reexecution"
    }))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut values = std::collections::BTreeMap::new();
    while let Some(flag) = args.next() {
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        values.insert(flag, PathBuf::from(value));
    }
    let get = |flag: &str| {
        values
            .get(flag)
            .cloned()
            .ok_or_else(|| format!("missing {flag}"))
    };
    let reference = Input::load(get("--reference-qualification")?, "reference qualification")?;
    let receipt = Input::load(get("--execution-receipt")?, "execution receipt")?;
    let report = Input::load(get("--native-report")?, "native report")?;
    let observation = Input::load(get("--observation")?, "candidate observation")?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let qualified = validate(&reference, &receipt, &report, &observation)?;
    let mut bytes = serde_json::to_vec_pretty(&qualified).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test candidate qualification invalid: {error}");
        std::process::exit(1);
    }
}
