use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const PLAN_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_plan.v1";
const CALIBRATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_calibration.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_qualification.v1";

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

fn validate(plan: &Input, calibration: &Input) -> Result<Value, String> {
    same(
        string(&plan.value, "schema", "mutation plan")?,
        PLAN_SCHEMA,
        "mutation plan schema",
    )?;
    same(
        string(&plan.value, "status", "mutation plan")?,
        "mutation-calibration-planned-not-executed",
        "mutation plan status",
    )?;
    exact_bool(&plan.value, "allowsCaseContract", false, "mutation plan")?;
    exact_bool(&plan.value, "automaticPromotion", false, "mutation plan")?;

    same(
        string(&calibration.value, "schema", "mutation calibration")?,
        CALIBRATION_SCHEMA,
        "mutation calibration schema",
    )?;
    same(
        string(&calibration.value, "status", "mutation calibration")?,
        "passed",
        "mutation calibration status",
    )?;
    exact_bool(
        &calibration.value,
        "expectedMatrixVerified",
        true,
        "mutation calibration",
    )?;
    exact_bool(
        &calibration.value,
        "sourceRestored",
        true,
        "mutation calibration",
    )?;
    exact_bool(
        &calibration.value,
        "worktreeCleanAfterExecution",
        true,
        "mutation calibration",
    )?;
    exact_bool(
        &calibration.value,
        "allowsCaseContract",
        false,
        "mutation calibration",
    )?;
    exact_bool(
        &calibration.value,
        "automaticPromotion",
        false,
        "mutation calibration",
    )?;

    same(
        string(
            &calibration.value,
            "candidateRevision",
            "mutation calibration",
        )?,
        string(&plan.value, "candidateRevision", "mutation plan")?,
        "candidate revision",
    )?;
    same(
        string(
            &calibration.value,
            "candidateSourceSha256",
            "mutation calibration",
        )?,
        string(&plan.value["source"], "sha256", "mutation plan source")?,
        "candidate source digest",
    )?;
    same(
        string(&calibration.value, "framework", "mutation calibration")?,
        "instrument-test-ohosTest-hypium",
        "mutation calibration framework",
    )?;
    same(
        string(&calibration.value, "executionHost", "mutation calibration")?,
        "hwlinux",
        "mutation calibration host",
    )?;

    let plan_tests = string_set(&plan.value["testNames"], "mutation plan tests")?;
    let plan_variants = plan.value["variants"]
        .as_array()
        .ok_or_else(|| "mutation plan variants must be an array".to_owned())?;
    let results = calibration.value["results"]
        .as_array()
        .ok_or_else(|| "mutation calibration results must be an array".to_owned())?;
    if plan_variants.len() != 6 || results.len() != plan_variants.len() {
        return Err("mutation variant inventory differs".into());
    }

    let mut result_ids = BTreeSet::new();
    for result in results {
        result_ids.insert(string(result, "id", "mutation result")?.to_owned());
    }
    if result_ids.len() != results.len() {
        return Err("mutation calibration result ids contain duplicates".into());
    }

    for variant in plan_variants {
        let id = string(variant, "id", "mutation variant")?;
        let result = results
            .iter()
            .find(|row| row["id"].as_str() == Some(id))
            .ok_or_else(|| format!("mutation calibration omits variant {id}"))?;
        for key in [
            "built",
            "emulatorExecutionAttempted",
            "variantKilled",
            "expectedMatrixMatched",
        ] {
            exact_bool(result, key, true, &format!("mutation result {id}"))?;
        }
        if result["observedTestCount"].as_u64() != Some(plan_tests.len() as u64) {
            return Err(format!("mutation result {id} observed test count differs"));
        }
        let expected = string_set(
            &variant["expectedKilledTests"],
            &format!("mutation variant {id} expected killed tests"),
        )?;
        let calibrated_expected = string_set(
            &result["expectedKilledTests"],
            &format!("mutation result {id} expected killed tests"),
        )?;
        let observed = string_set(
            &result["observedKilledTests"],
            &format!("mutation result {id} observed killed tests"),
        )?;
        if expected != calibrated_expected || expected != observed {
            return Err(format!("mutation result {id} kill matrix differs"));
        }
        let surviving = string_set(
            &result["observedSurvivingTests"],
            &format!("mutation result {id} surviving tests"),
        )?;
        if !expected.is_disjoint(&surviving)
            || expected.union(&surviving).cloned().collect::<BTreeSet<_>>() != plan_tests
        {
            return Err(format!("mutation result {id} test partition differs"));
        }
    }

    for (key, expected) in [
        ("variantCount", 6),
        ("builtVariantCount", 6),
        ("emulatorExecutedVariantCount", 6),
        ("killedVariantCount", 6),
        ("exactExpectedMatrixMatchCount", 6),
    ] {
        if calibration.value[key].as_u64() != Some(expected) {
            return Err(format!("mutation calibration {key} differs"));
        }
    }
    if calibration.value["mutationScore"].as_f64() != Some(1.0) {
        return Err("mutation calibration score differs".into());
    }

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "mutation-discrimination-qualified-source-review-still-required",
        "candidateId": plan.value["candidateId"],
        "candidateRevision": plan.value["candidateRevision"],
        "candidateSourceSha256": plan.value["source"]["sha256"],
        "mutationPlanSha256": plan.sha256(),
        "mutationCalibrationSha256": calibration.sha256(),
        "framework": calibration.value["framework"],
        "executionHost": calibration.value["executionHost"],
        "variantCount": 6,
        "testCount": plan_tests.len(),
        "killedVariantCount": 6,
        "mutationScore": 1.0,
        "expectedMatrixVerified": true,
        "sourceRestored": true,
        "worktreeCleanAfterExecution": true,
        "independentReviewVerified": false,
        "behaviorOracleVerified": false,
        "performanceCalibrated": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "All six planned meaningful-wrong source variants were built and executed through seven OHOS Tests on one Linux x86 emulator, and every observed kill matrix matched the source-bound hypothesis. This is discrimination evidence only; it does not prove live vendor-IAP behavior, real-device behavior, performance, power, thermal, whole-application semantics or independent source approval.",
        "nextGate": "independent-source-review-and-live-behavior-oracle"
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
    let plan = Input::load(get("--mutation-plan")?, "mutation plan")?;
    let calibration = Input::load(get("--mutation-calibration")?, "mutation calibration")?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let qualification = validate(&plan, &calibration)?;
    let mut bytes = serde_json::to_vec_pretty(&qualification).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test mutation qualification invalid: {error}");
        std::process::exit(1);
    }
}
