use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const PROPOSAL_SCHEMA: &str = "agentlab.purchase_data_ohostest_proposal.v1";
const RECEIPT_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const REPORT_SCHEMA: &str = "agentlab.harmony_hypium_native_report.v1";
const OBSERVATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_reference_observation.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_reference_qualification.v1";

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

fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn require_sha(value: &Value, key: &str, label: &str) -> Result<String, String> {
    let sha = string(value, key, label)?;
    if !valid_sha(sha) {
        return Err(format!("{label} {key} is not a lowercase SHA-256"));
    }
    Ok(sha.to_owned())
}

fn validate(
    proposal: &Input,
    receipt: &Input,
    report: &Input,
    observation: &Input,
) -> Result<Value, String> {
    same(
        string(&proposal.value, "schema", "proposal")?,
        PROPOSAL_SCHEMA,
        "proposal schema",
    )?;
    same(
        string(&proposal.value, "status", "proposal")?,
        "testability-refactor-required-before-standard-test-authoring",
        "proposal status",
    )?;
    exact_bool(
        &proposal.value["qualificationBoundary"],
        "ohosTestSourceAuthored",
        false,
        "proposal qualification boundary",
    )?;

    same(
        string(&receipt.value, "schema", "receipt")?,
        RECEIPT_SCHEMA,
        "receipt schema",
    )?;
    same(
        string(&receipt.value, "status", "receipt")?,
        "passed",
        "receipt status",
    )?;
    same(
        string(&receipt.value, "framework", "receipt")?,
        "instrument-test-ohosTest-hypium",
        "receipt framework",
    )?;
    exact_bool(&receipt.value, "passed", true, "receipt")?;
    exact_bool(&receipt.value, "automaticPromotion", false, "receipt")?;

    same(
        string(&report.value, "schema", "native report")?,
        REPORT_SCHEMA,
        "native report schema",
    )?;
    exact_bool(&report.value, "passed", true, "native report")?;
    exact_bool(&report.value, "timedOut", false, "native report")?;
    for (key, expected) in [
        ("total", 5),
        ("pass", 5),
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
    same(
        string(&receipt.value["report"], "sha256", "receipt report")?,
        &report.sha256(),
        "receipt native report digest",
    )?;

    same(
        string(&observation.value, "schema", "observation")?,
        OBSERVATION_SCHEMA,
        "observation schema",
    )?;
    exact_bool(
        &observation.value,
        "referencePatchOnly",
        true,
        "observation",
    )?;
    exact_bool(
        &observation.value,
        "upstreamRevisionModified",
        false,
        "observation",
    )?;
    exact_bool(
        &observation.value,
        "automaticPromotion",
        false,
        "observation",
    )?;
    same(
        string(&observation.value, "baseRevision", "observation")?,
        string(
            &proposal.value["lineage"],
            "sourceRevision",
            "proposal lineage",
        )?,
        "reference base revision",
    )?;
    same(
        string(&observation.value, "sourceSetSha256", "observation")?,
        string(&receipt.value, "sourceSetSha256", "receipt")?,
        "reference source set",
    )?;
    for key in [
        "sourceSetSha256",
        "referencePatchSha256",
        "mainBuildLogSha256",
        "ohosTestBuildLogSha256",
        "aaTestLogSha256",
    ] {
        require_sha(&observation.value, key, "observation")?;
    }
    for package in ["app", "test"] {
        same(
            string(
                &observation.value["packages"][package],
                "sha256",
                "observation package",
            )?,
            string(
                &receipt.value["packages"][package],
                "sha256",
                "receipt package",
            )?,
            &format!("{package} package digest"),
        )?;
    }
    let test_names = observation.value["testNames"]
        .as_array()
        .ok_or_else(|| "observation testNames must be an array".to_owned())?;
    let actual: BTreeSet<&str> = test_names
        .iter()
        .map(|row| {
            row.as_str()
                .ok_or_else(|| "testNames must contain strings".to_owned())
        })
        .collect::<Result<_, _>>()?;
    let expected = BTreeSet::from([
        "malformedDataDoesNotFinish",
        "alreadyFinishedPurchaseDoesNotFinishAgain",
        "pendingPurchaseForwardsExactFinishFields",
        "missingProductTypeBlocksFinish",
        "finishRejectionRemainsObservable",
    ]);
    if test_names.len() != expected.len() || actual != expected {
        return Err("reference OHOS Test inventory differs".into());
    }

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "reference-testability-refactor-emulator-qualified-upstream-change-required",
        "baseRevision": observation.value["baseRevision"],
        "sourceSetSha256": observation.value["sourceSetSha256"],
        "framework": receipt.value["framework"],
        "coverage": {
            "testCount": 5,
            "passed": 5,
            "failure": 0,
            "error": 0,
            "ignore": 0,
            "mainHapBuilt": true,
            "ohosTestHapBuilt": true,
            "emulatorExecuted": true
        },
        "lineage": {
            "proposalSha256": proposal.sha256(),
            "executionReceiptSha256": receipt.sha256(),
            "nativeReportSha256": report.sha256(),
            "observationSha256": observation.sha256(),
            "referencePatchSha256": observation.value["referencePatchSha256"]
        },
        "packages": receipt.value["packages"],
        "testNames": observation.value["testNames"],
        "referencePatchOnly": true,
        "upstreamRevisionModified": false,
        "behaviorOracleVerified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This qualifies one isolated reference refactor and its five source-bound OHOS Test cases on the Linux x86 emulator. It does not modify or approve the upstream revision, validate live IAP service behavior, approve the cross-repository semantic claim, or authorize case promotion.",
        "nextGate": "independent-review-of-reference-patch-then-upstream-revision-bound-reexecution"
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
    let proposal = Input::load(get("--proposal")?, "proposal")?;
    let receipt = Input::load(get("--execution-receipt")?, "execution receipt")?;
    let report = Input::load(get("--native-report")?, "native report")?;
    let observation = Input::load(get("--observation")?, "observation")?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let qualified = validate(&proposal, &receipt, &report, &observation)?;
    let mut bytes = serde_json::to_vec_pretty(&qualified).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test reference qualification invalid: {error}");
        std::process::exit(1);
    }
}
