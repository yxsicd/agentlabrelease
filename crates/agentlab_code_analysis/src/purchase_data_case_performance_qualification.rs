use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    env, fs,
    path::{Path, PathBuf},
};

const REVISION: &str = "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8";
const ENVIRONMENT: &str = "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7";
const POLICY_SHA: &str = "ae914ba0c30dd8aec098531497021d75a3fa1311e7c371290d43a0a4eccffb3e";
const WORKLOAD_SHA: &str = "7812fa159f8c7ec8ea69f48987cca39b0f373280eb7af847c16ea4dfaf7d563f";
const PLAN_SCHEMA: &str = "agentlab.purchase_data_case_performance_calibration_plan.v1";
const ROLE_SCHEMA: &str = "agentlab.purchase_data_case_performance_role.v1";
const RUN_SCHEMA: &str = "agentlab.purchase_data_case_performance_run.v1";
const SUMMARY_SCHEMA: &str = "agentlab.smartperf_summary.v2";
const COMPARISON_SCHEMA: &str = "agentlab.smartperf_comparison.v1";
const RECEIPT_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const REPORT_SCHEMA: &str = "agentlab.harmony_hypium_native_report.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_case_performance_qualification.v1";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}
impl Input {
    fn load(path: &Path, label: &str) -> Result<Self, String> {
        let metadata =
            fs::symlink_metadata(path).map_err(|e| format!("cannot inspect {label}: {e}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(path).map_err(|e| format!("cannot read {label}: {e}"))?;
        let value: Value =
            serde_json::from_slice(&bytes).map_err(|e| format!("cannot parse {label}: {e}"))?;
        if !value.is_object() {
            return Err(format!("{label} must be a JSON object"));
        }
        Ok(Self { bytes, value })
    }
    fn sha(&self) -> String {
        digest(&self.bytes)
    }
}

fn string<'a>(v: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("{label} {key} is absent"))
}
fn same(actual: &str, expected: &str, label: &str) -> Result<(), String> {
    if actual != expected {
        return Err(format!("{label} differs"));
    }
    Ok(())
}
fn boolean(v: &Value, key: &str, expected: bool, label: &str) -> Result<(), String> {
    if v[key].as_bool() != Some(expected) {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}
fn count(v: &Value, key: &str, expected: u64, label: &str) -> Result<(), String> {
    if v[key].as_u64() != Some(expected) {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}
fn regular_bytes(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        fs::symlink_metadata(path).map_err(|e| format!("cannot inspect {label}: {e}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular file"));
    }
    fs::read(path).map_err(|e| format!("cannot read {label}: {e}"))
}

fn validate_plan(path: &Path) -> Result<Input, String> {
    let input = Input::load(path, "case performance plan")?;
    let v = &input.value;
    same(string(v, "schema", "plan")?, PLAN_SCHEMA, "plan schema")?;
    same(
        string(v, "candidateRevision", "plan")?,
        REVISION,
        "plan revision",
    )?;
    same(
        v["calibrationRoles"][2]["id"].as_str().unwrap_or(""),
        "redundant-purchase-order-decode-1000x-v2",
        "meaningful-wrong plan id",
    )?;
    if !v["calibrationRoles"][2]["edit"]["replace"]
        .as_str()
        .unwrap_or("")
        .contains("pass < 1000")
    {
        return Err("meaningful-wrong plan edit differs".into());
    }
    boolean(v, "performanceCalibrated", false, "plan")?;
    boolean(v, "automaticPromotion", false, "plan")?;
    Ok(input)
}

fn validate_receipt(
    run: &Path,
    ordinal: u64,
    expected_receipt: &str,
    expected_report: &str,
) -> Result<(), String> {
    let dir = run.join(format!("tests/{ordinal}"));
    let receipt = Input::load(&dir.join("receipt.json"), "functional receipt")?;
    same(&receipt.sha(), expected_receipt, "receipt digest")?;
    same(
        string(&receipt.value, "schema", "receipt")?,
        RECEIPT_SCHEMA,
        "receipt schema",
    )?;
    boolean(&receipt.value, "passed", true, "receipt")?;
    boolean(&receipt.value, "packagesInstalled", false, "receipt")?;
    let report_path = dir.join(string(&receipt.value["report"], "path", "receipt report")?);
    let report = Input::load(&report_path, "native report")?;
    same(&report.sha(), expected_report, "native report digest")?;
    same(
        string(&report.value, "schema", "native report")?,
        REPORT_SCHEMA,
        "native report schema",
    )?;
    boolean(&report.value, "passed", true, "native report")?;
    for (key, expected) in [
        ("error", 0),
        ("failure", 0),
        ("ignore", 0),
        ("pass", 8),
        ("total", 8),
    ] {
        count(
            &report.value["counts"],
            key,
            expected,
            "native report counts",
        )?;
    }
    Ok(())
}

fn validate_run(root: &Path, role: &str, run_number: u64, meta: &Value) -> Result<Value, String> {
    let run = root.join(format!("{role}/run-{run_number}"));
    let manifest = Input::load(&run.join("run-manifest.json"), "run manifest")?;
    let v = &manifest.value;
    same(string(v, "schema", "run")?, RUN_SCHEMA, "run schema")?;
    same(string(v, "role", "run")?, role, "run role")?;
    same(
        string(v, "candidateRevision", "run")?,
        REVISION,
        "run revision",
    )?;
    same(
        string(v, "environmentIdentity", "run")?,
        ENVIRONMENT,
        "run environment",
    )?;
    for key in [
        "sourceSha256",
        "testSourceSha256",
        "appHapSha256",
        "testHapSha256",
    ] {
        same(
            string(v, key, "run")?,
            string(meta, key, "role metadata")?,
            &format!("run {key}"),
        )?;
    }
    same(
        string(v, "performancePolicySha256", "run")?,
        POLICY_SHA,
        "run policy",
    )?;
    same(
        string(v, "profileWorkloadSha256", "run")?,
        WORKLOAD_SHA,
        "run workload",
    )?;
    count(v, "functionalRepeatCount", 6, "run")?;
    count(v, "functionalTestCountPerRepeat", 8, "run")?;
    count(v, "functionalVerdictCount", 48, "run")?;
    count(v, "profileSampleCount", 48, "run")?;
    count(v, "caseBoundIterationCountPerRepeat", 5000, "run")?;
    boolean(v, "functionalRepeatsWithinProfileWindow", true, "run")?;
    boolean(v, "packagesInstalledInsideProfileWindow", false, "run")?;
    boolean(v, "automaticPromotion", false, "run")?;
    boolean(
        v,
        "controlledVariantNotAgentRun",
        role != "reference",
        "run",
    )?;
    if !regular_bytes(
        &run.join("final-emulator-processes.txt"),
        "final emulator state",
    )?
    .is_empty()
    {
        return Err("final emulator process state is not empty".into());
    }
    let hdc = String::from_utf8(regular_bytes(
        &run.join("final-hdc-targets.txt"),
        "final HDC state",
    )?)
    .map_err(|e| e.to_string())?;
    if hdc.trim() != "[Empty]" {
        return Err("final HDC state differs".into());
    }
    let summary = Input::load(&run.join("smartperf-summary.json"), "SmartPerf summary")?;
    same(
        &summary.sha(),
        string(v, "smartPerfSummarySha256", "run")?,
        "SmartPerf summary digest",
    )?;
    same(
        string(&summary.value, "schema", "summary")?,
        SUMMARY_SCHEMA,
        "summary schema",
    )?;
    boolean(&summary.value, "profileValid", true, "summary")?;
    count(&summary.value, "sampleCount", 48, "summary")?;
    if regular_bytes(&run.join("smartperf.txt"), "raw SmartPerf")?.is_empty() {
        return Err("raw SmartPerf is empty".into());
    }
    let repeats = v["functionalRepeats"]
        .as_array()
        .ok_or("functional repeats are absent")?;
    if repeats.len() != 6 {
        return Err("functional repeat count differs".into());
    }
    for (index, repeat) in repeats.iter().enumerate() {
        let ordinal = (index + 1) as u64;
        count(repeat, "ordinal", ordinal, "functional repeat")?;
        validate_receipt(
            run.as_path(),
            ordinal,
            string(repeat, "receiptSha256", "repeat")?,
            string(repeat, "nativeReportSha256", "repeat")?,
        )?;
    }
    Ok(json!({"run": run_number, "manifestSha256": manifest.sha(), "summarySha256": summary.sha()}))
}

fn validate_comparison(
    root: &Path,
    name: &str,
    expected_decision: &str,
    expect_cpu_regression: bool,
) -> Result<Value, String> {
    let input = Input::load(&root.join(name), "comparison")?;
    let v = &input.value;
    same(
        string(v, "schema", "comparison")?,
        COMPARISON_SCHEMA,
        "comparison schema",
    )?;
    same(
        string(v, "decision", "comparison")?,
        expected_decision,
        "comparison decision",
    )?;
    boolean(v, "comparable", true, "comparison")?;
    same(
        string(v, "environmentIdentity", "comparison")?,
        ENVIRONMENT,
        "comparison environment",
    )?;
    same(
        string(&v["performancePolicy"], "sha256", "comparison policy")?,
        POLICY_SHA,
        "comparison policy",
    )?;
    same(
        string(&v["profileWorkload"], "sha256", "comparison workload")?,
        WORKLOAD_SHA,
        "comparison workload",
    )?;
    let cpu = v["metrics"]
        .as_array()
        .and_then(|metrics| metrics.iter().find(|m| m["metric"] == "appCpuUsagePercent"))
        .ok_or("CPU metric is absent")?;
    same(
        string(cpu, "status", "CPU metric")?,
        if expect_cpu_regression {
            "regressed"
        } else {
            "passed"
        },
        "CPU verdict",
    )?;
    Ok(json!({"path": name, "sha256": input.sha(), "decision": expected_decision}))
}

fn build(plan_path: &Path, root: &Path) -> Result<Value, String> {
    let plan = validate_plan(plan_path)?;
    same(
        &digest(&regular_bytes(
            &root.join("performance-policy.json"),
            "performance policy",
        )?),
        POLICY_SHA,
        "performance policy digest",
    )?;
    same(
        &digest(&regular_bytes(
            &root.join("profile-workload.tsv"),
            "profile workload",
        )?),
        WORKLOAD_SHA,
        "profile workload digest",
    )?;
    let mut roles = Vec::new();
    for role in ["reference", "baseline-task-start", "meaningful-wrong"] {
        let meta = Input::load(&root.join(role).join("role-metadata.json"), "role metadata")?;
        same(
            string(&meta.value, "schema", "role metadata")?,
            ROLE_SCHEMA,
            "role metadata schema",
        )?;
        same(
            string(&meta.value, "role", "role metadata")?,
            role,
            "role metadata role",
        )?;
        same(
            string(&meta.value, "candidateRevision", "role metadata")?,
            REVISION,
            "role revision",
        )?;
        same(
            string(&meta.value, "performancePolicySha256", "role metadata")?,
            POLICY_SHA,
            "role policy",
        )?;
        same(
            string(&meta.value, "profileWorkloadSha256", "role metadata")?,
            WORKLOAD_SHA,
            "role workload",
        )?;
        boolean(&meta.value, "automaticPromotion", false, "role metadata")?;
        let runs = [
            validate_run(root, role, 1, &meta.value)?,
            validate_run(root, role, 2, &meta.value)?,
        ];
        roles.push(json!({"role":role,"metadataSha256":meta.sha(),"sourceSha256":meta.value["sourceSha256"],"appHapSha256":meta.value["appHapSha256"],"testHapSha256":meta.value["testHapSha256"],"runs":runs}));
    }
    let comparisons = vec![
        validate_comparison(
            root,
            "reference-repeatability.json",
            "within-relative-guardrails",
            false,
        )?,
        validate_comparison(
            root,
            "baseline-task-start-comparison-1.json",
            "performance-regression-candidate",
            true,
        )?,
        validate_comparison(
            root,
            "baseline-task-start-comparison-2.json",
            "performance-regression-candidate",
            true,
        )?,
        validate_comparison(
            root,
            "meaningful-wrong-comparison-1.json",
            "performance-regression-candidate",
            true,
        )?,
        validate_comparison(
            root,
            "meaningful-wrong-comparison-2.json",
            "performance-regression-candidate",
            true,
        )?,
    ];
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "case-bound-reference-baseline-meaningful-wrong-performance-calibrated",
        "candidateRevision": REVISION,
        "planSha256": plan.sha(),
        "environmentIdentity": ENVIRONMENT,
        "roles": roles,
        "comparisons": comparisons,
        "coverage": {"roleCount":3,"coldRunCount":6,"functionalVerdictCount":288,"profileSampleCount":288},
        "requiredCommonRegressedMetric": "appCpuUsagePercent",
        "functionalMatrixVerified": true,
        "caseBoundWorkloadObserved": true,
        "performanceMatrixVerified": true,
        "distinctBaselineReferenceWrongCaseCalibrationComplete": true,
        "performanceCalibrated": true,
        "controlledVariantsAreNotAgentRunsUnseenCasesOrGoldRepairs": true,
        "independentOracleReviewCompleted": false,
        "liveVendorIapExecuted": false,
        "realDeviceExecuted": false,
        "absolutePowerThermalQualified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "Six Linux x86 emulator cold runs retain 288 passing OHOS Test verdicts and 288 SmartPerf samples. Reference repeatability passed, while both case-bound controlled variants were rejected on appCpuUsagePercent in both runs. This completes relative case-bound performance calibration only; controlled variants are not Agent runs, unseen cases or gold repairs, and independent review, live vendor IAP, real-device and absolute power/thermal qualification remain open."
    }))
}

fn parse_args() -> Result<(PathBuf, PathBuf, PathBuf), String> {
    let mut args = env::args().skip(1);
    let mut plan = None;
    let mut evidence = None;
    let mut output = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--plan" => plan = args.next().map(PathBuf::from),
            "--evidence" => evidence = args.next().map(PathBuf::from),
            "--output" => output = args.next().map(PathBuf::from),
            _ => return Err(format!("unknown argument: {arg}")),
        }
    }
    Ok((
        plan.ok_or("missing --plan")?,
        evidence.ok_or("missing --evidence")?,
        output.ok_or("missing --output")?,
    ))
}
fn run() -> Result<(), String> {
    let (plan, evidence, output) = parse_args()?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = build(&plan, &evidence)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|e| e.to_string())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data case performance qualification invalid: {error}");
        std::process::exit(1)
    }
}
