use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

const BRIDGE_SCHEMA: &str = "agentlab.purchase_data_runtime_oracle_bridge.v1";
const RECEIPT_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const REPORT_SCHEMA: &str = "agentlab.harmony_hypium_native_report.v1";
const RUN_SCHEMA: &str = "agentlab.purchase_data_ohostest_profile_run.v1";
const SUMMARY_SCHEMA: &str = "agentlab.smartperf_summary.v2";
const COMPARISON_SCHEMA: &str = "agentlab.smartperf_comparison.v1";
const POLICY_SCHEMA: &str = "agentlab.harmony_performance_policy.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_profile_qualification.v1";
const REVISION: &str = "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8";
const SOURCE_SHA: &str = "cd53dcfe1c5e364d67b57e59e27f4336c32d6058ef5abf45bd75385817d24bb0";
const SOURCE_SET_SHA: &str = "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2";
const APP_SHA: &str = "dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073";
const TEST_SHA: &str = "5a2015114fd435daba3e25331df6a7ac48445827230079870cc2571c710934fe";
const REPORT_SHA: &str = "123fbf9bcff0dbf9c946b60e7f407b4695582072c45f15ebc249cb33aa93ba65";
const ENVIRONMENT: &str = "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7";
const POLICY_ID: &str = "purchase-data-ohostest-cpu-pss-repeatability-v2";
const WORKLOAD_ID: &str = "purchase-data-ohostest-foreground-repeat-v3";

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
    fn sha256(&self) -> String {
        digest(&self.bytes)
    }
}

fn regular_bytes(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        fs::symlink_metadata(path).map_err(|e| format!("cannot inspect {label}: {e}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular file"));
    }
    fs::read(path).map_err(|e| format!("cannot read {label}: {e}"))
}

fn text(path: &Path, label: &str) -> Result<String, String> {
    String::from_utf8(regular_bytes(path, label)?).map_err(|e| format!("{label} is not UTF-8: {e}"))
}

fn string<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|v| !v.is_empty())
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

fn validate_report(input: &Input, label: &str) -> Result<(), String> {
    same(
        string(&input.value, "schema", label)?,
        REPORT_SCHEMA,
        &format!("{label} schema"),
    )?;
    exact_bool(&input.value, "passed", true, label)?;
    exact_u64(&input.value["counts"], "total", 7, label)?;
    exact_u64(&input.value["counts"], "pass", 7, label)?;
    for key in ["failure", "error", "ignore"] {
        exact_u64(&input.value["counts"], key, 0, label)?;
    }
    exact_u64(&input.value, "processExitCode", 0, label)?;
    exact_u64(&input.value, "nativeFinalCode", 0, label)?;
    exact_bool(&input.value, "timedOut", false, label)
}

fn validate_receipt(
    input: &Input,
    report: &Input,
    label: &str,
    window_start: &str,
    window_finish: &str,
    require_no_install: bool,
) -> Result<(), String> {
    same(
        string(&input.value, "schema", label)?,
        RECEIPT_SCHEMA,
        &format!("{label} schema"),
    )?;
    same(
        string(&input.value, "status", label)?,
        "passed",
        &format!("{label} status"),
    )?;
    exact_bool(&input.value, "passed", true, label)?;
    if require_no_install {
        exact_bool(&input.value, "packagesInstalled", false, label)?;
    }
    same(
        string(&input.value, "caseId", label)?,
        "purchase-data-finalization-candidate-clean-v1",
        &format!("{label} case"),
    )?;
    same(
        string(&input.value, "framework", label)?,
        "instrument-test-ohosTest-hypium",
        &format!("{label} framework"),
    )?;
    same(
        string(&input.value, "sourceSetSha256", label)?,
        SOURCE_SET_SHA,
        &format!("{label} source set"),
    )?;
    same(
        string(&input.value["packages"]["app"], "sha256", label)?,
        APP_SHA,
        &format!("{label} app HAP"),
    )?;
    same(
        string(&input.value["packages"]["test"], "sha256", label)?,
        TEST_SHA,
        &format!("{label} test HAP"),
    )?;
    same(
        string(&input.value["report"], "sha256", label)?,
        &report.sha256(),
        &format!("{label} report digest"),
    )?;
    same(
        &report.sha256(),
        REPORT_SHA,
        &format!("{label} canonical report digest"),
    )?;
    let started = string(&input.value, "startedAt", label)?;
    let finished = string(&input.value, "finishedAt", label)?;
    if !(window_start <= started && started <= finished && finished <= window_finish) {
        return Err(format!("{label} escaped profile window"));
    }
    let command = input.value["command"]
        .as_array()
        .ok_or_else(|| format!("{label} command is absent"))?;
    if command.iter().any(|v| v.as_str() == Some("install")) || command.len() != 16 {
        return Err(format!("{label} command differs"));
    }
    validate_report(report, &format!("{label} native report"))
}

struct RunEvidence {
    manifest: Input,
}

fn validate_run(
    root: &Path,
    run_id: &str,
    policy_sha: &str,
    workload_sha: &str,
) -> Result<RunEvidence, String> {
    let run = root.join(run_id);
    let manifest = Input::load(
        &run.join("run-manifest.json"),
        &format!("{run_id} manifest"),
    )?;
    let summary = Input::load(
        &run.join("smartperf-summary.json"),
        &format!("{run_id} summary"),
    )?;
    let m = &manifest.value;
    same(
        string(m, "schema", "run manifest")?,
        RUN_SCHEMA,
        "run manifest schema",
    )?;
    same(
        string(m, "status", "run manifest")?,
        "passed",
        "run manifest status",
    )?;
    same(string(m, "runId", "run manifest")?, run_id, "run id")?;
    same(
        string(m, "candidateRevision", "run manifest")?,
        REVISION,
        "candidate revision",
    )?;
    same(
        string(m, "candidateSourceSha256", "run manifest")?,
        SOURCE_SHA,
        "candidate source",
    )?;
    same(
        string(m, "sourceSetSha256", "run manifest")?,
        SOURCE_SET_SHA,
        "source set",
    )?;
    same(
        string(m, "appHapSha256", "run manifest")?,
        APP_SHA,
        "app HAP",
    )?;
    same(
        string(m, "testHapSha256", "run manifest")?,
        TEST_SHA,
        "test HAP",
    )?;
    same(
        string(m, "environmentIdentity", "run manifest")?,
        ENVIRONMENT,
        "environment",
    )?;
    same(
        string(m, "performancePolicySha256", "run manifest")?,
        policy_sha,
        "performance policy digest",
    )?;
    same(
        string(m, "profileWorkloadSha256", "run manifest")?,
        workload_sha,
        "profile workload digest",
    )?;
    exact_u64(m, "functionalRepeatCount", 6, "run manifest")?;
    exact_u64(m, "profileSampleCount", 48, "run manifest")?;
    for (key, expected) in [
        ("functionalRepeatsWithinProfileWindow", true),
        ("performanceRepeatabilityOnly", true),
        ("realDeviceExecuted", false),
        ("liveVendorIapExecuted", false),
        ("absolutePowerThermalAuthority", false),
        ("automaticPromotion", false),
    ] {
        exact_bool(m, key, expected, "run manifest")?;
    }
    same(
        string(m, "smartPerfSummarySha256", "run manifest")?,
        &summary.sha256(),
        "summary digest",
    )?;
    for (field, file) in [
        ("runnerSha256", "run-harmony-instrument-test.py"),
        (
            "standardTestContractSha256",
            "harmony-standard-test-contract.py",
        ),
        ("normalizerSha256", "summarize-smartperf.py"),
        ("comparatorSha256", "compare-smartperf.py"),
        ("runProfileScriptSha256", "run-profile.sh"),
    ] {
        same(
            string(m, field, "run manifest")?,
            &digest(&regular_bytes(&root.join(file), file)?),
            field,
        )?;
    }
    let actions = regular_bytes(
        &run.join("profile-workload-actions.tsv"),
        "workload actions",
    )?;
    same(
        string(m, "profileWorkloadActionsSha256", "run manifest")?,
        &digest(&actions),
        "workload actions digest",
    )?;
    exact_u64(m, "profileWorkloadActionCount", 13, "run manifest")?;
    let started = string(m, "profileWindowStartedAt", "run manifest")?.to_owned();
    let finished = string(m, "profileWindowFinishedAt", "run manifest")?.to_owned();
    if started >= finished {
        return Err("profile window order differs".into());
    }
    same(
        text(
            &run.join("profile-window-started-at.txt"),
            "profile window start",
        )?
        .trim(),
        &started,
        "profile window start",
    )?;
    same(
        text(
            &run.join("profile-window-finished-at.txt"),
            "profile window finish",
        )?
        .trim(),
        &finished,
        "profile window finish",
    )?;
    let repeats = m["functionalRepeats"]
        .as_array()
        .ok_or("functional repeats must be an array")?;
    if repeats.len() != 6 {
        return Err("functional repeat inventory differs".into());
    }
    for ordinal in 1..=6 {
        let dir = run.join("tests").join(ordinal.to_string());
        let receipt = Input::load(
            &dir.join("receipt.json"),
            &format!("{run_id} receipt {ordinal}"),
        )?;
        let report = Input::load(
            &dir.join("native-report.json"),
            &format!("{run_id} report {ordinal}"),
        )?;
        let row = &repeats[ordinal - 1];
        exact_u64(row, "ordinal", ordinal as u64, "repeat manifest")?;
        same(
            string(row, "receiptSha256", "repeat manifest")?,
            &receipt.sha256(),
            "repeat receipt digest",
        )?;
        same(
            string(row, "nativeReportSha256", "repeat manifest")?,
            &report.sha256(),
            "repeat report digest",
        )?;
        validate_receipt(
            &receipt,
            &report,
            &format!("{run_id} repeat {ordinal}"),
            &started,
            &finished,
            true,
        )?;
    }
    let s = &summary.value;
    same(
        string(s, "schema", "SmartPerf summary")?,
        SUMMARY_SCHEMA,
        "SmartPerf summary schema",
    )?;
    exact_bool(s, "profileValid", true, "SmartPerf summary")?;
    exact_u64(s, "sampleCount", 48, "SmartPerf summary")?;
    same(
        string(s, "runId", "SmartPerf summary")?,
        run_id,
        "SmartPerf run id",
    )?;
    same(
        string(s, "environmentIdentity", "SmartPerf summary")?,
        ENVIRONMENT,
        "SmartPerf environment",
    )?;
    same(
        string(&s["performancePolicy"], "id", "SmartPerf policy")?,
        POLICY_ID,
        "SmartPerf policy id",
    )?;
    same(
        string(&s["performancePolicy"], "sha256", "SmartPerf policy")?,
        policy_sha,
        "SmartPerf policy digest",
    )?;
    same(
        string(&s["profileWorkload"], "id", "SmartPerf workload")?,
        WORKLOAD_ID,
        "SmartPerf workload id",
    )?;
    same(
        string(&s["profileWorkload"], "sha256", "SmartPerf workload")?,
        workload_sha,
        "SmartPerf workload digest",
    )?;
    exact_bool(
        &s["metricAvailability"],
        "appCpuUsagePercent",
        true,
        "metric availability",
    )?;
    exact_bool(
        &s["metricAvailability"],
        "appPssKiB",
        true,
        "metric availability",
    )?;
    if s["canonicalMetrics"]["appCpuUsagePercent"]["mean"]
        .as_f64()
        .is_none()
        || s["canonicalMetrics"]["appPssKiB"]["mean"]
            .as_f64()
            .is_none()
    {
        return Err("required canonical metric is absent".into());
    }
    Ok(RunEvidence { manifest })
}

fn validate(
    bridge: &Input,
    candidate_receipt: &Input,
    candidate_report: &Input,
    root: &Path,
) -> Result<Value, String> {
    same(
        string(&bridge.value, "schema", "runtime bridge")?,
        BRIDGE_SCHEMA,
        "runtime bridge schema",
    )?;
    same(
        string(&bridge.value, "status", "runtime bridge")?,
        "harmony-runtime-oracle-bridge-qualified-independent-review-required",
        "runtime bridge status",
    )?;
    same(
        string(&bridge.value, "candidateRevision", "runtime bridge")?,
        REVISION,
        "runtime bridge revision",
    )?;
    same(
        string(&bridge.value, "candidateSourceSha256", "runtime bridge")?,
        SOURCE_SHA,
        "runtime bridge source",
    )?;
    exact_u64(
        &bridge.value["coverage"],
        "harmonyRuntimeBoundCheckCount",
        5,
        "runtime bridge",
    )?;
    exact_u64(
        &bridge.value["coverage"],
        "ohosTestCount",
        7,
        "runtime bridge",
    )?;
    for key in [
        "behaviorOracleVerified",
        "allowsCaseContract",
        "automaticPromotion",
        "performanceCalibrated",
    ] {
        exact_bool(&bridge.value, key, false, "runtime bridge")?;
    }
    validate_receipt(
        candidate_receipt,
        candidate_report,
        "candidate execution",
        "0000",
        "9999",
        false,
    )?;

    let policy = Input::load(&root.join("performance-policy.json"), "performance policy")?;
    same(
        string(&policy.value, "schema", "performance policy")?,
        POLICY_SCHEMA,
        "performance policy schema",
    )?;
    same(
        string(&policy.value, "id", "performance policy")?,
        POLICY_ID,
        "performance policy id",
    )?;
    exact_bool(
        &policy.value,
        "requiresWorkload",
        true,
        "performance policy",
    )?;
    same(
        string(
            &policy.value["authority"],
            "absolutePowerThermal",
            "performance policy",
        )?,
        "unavailable-on-emulator",
        "power thermal authority",
    )?;
    let required = policy.value["requiredMetrics"]
        .as_array()
        .ok_or("required metrics must be an array")?;
    if required.len() != 2
        || required[0]["metric"] != "appCpuUsagePercent"
        || required[0]["statistic"] != "mean"
        || required[0]["maximumRelativeIncrease"].as_f64() != Some(0.2)
        || required[0]["maximumAbsoluteIncrease"].as_f64() != Some(2.0)
        || required[1]["metric"] != "appPssKiB"
        || required[1]["statistic"] != "mean"
        || required[1]["maximumRelativeIncrease"].as_f64() != Some(0.15)
    {
        return Err("performance policy guardrails differ".into());
    }
    let workload_bytes = regular_bytes(&root.join("profile-workload.tsv"), "profile workload")?;
    let workload = String::from_utf8_lossy(&workload_bytes);
    for exact in [
        "schema\tagentlab.harmony_profile_workload.v1",
        &format!("workload\t{WORKLOAD_ID}"),
        "profile-samples\t48",
        "start-app\t7\tEntryAbility\txxx.xxx.xxx",
        "repeat-ohostest\t6\t7\tOpenHarmonyTestRunner",
    ] {
        if !workload.lines().any(|line| line == exact) {
            return Err("profile workload differs".into());
        }
    }
    let policy_sha = policy.sha256();
    let workload_sha = digest(&workload_bytes);
    let run1 = validate_run(root, "run-1", &policy_sha, &workload_sha)?;
    let run2 = validate_run(root, "run-2", &policy_sha, &workload_sha)?;

    let comparison = Input::load(
        &root.join("smartperf-comparison.json"),
        "SmartPerf comparison",
    )?;
    let c = &comparison.value;
    same(
        string(c, "schema", "SmartPerf comparison")?,
        COMPARISON_SCHEMA,
        "comparison schema",
    )?;
    exact_bool(c, "comparable", true, "SmartPerf comparison")?;
    same(
        string(c, "decision", "SmartPerf comparison")?,
        "within-relative-guardrails",
        "comparison decision",
    )?;
    same(
        string(c, "baselineSummarySha256", "SmartPerf comparison")?,
        "577e4b671f0886e69e671babbf7c0eeda351c91d8d2384610d56f01ff2bc122e",
        "baseline canonical summary digest",
    )?;
    same(
        string(c, "candidateSummarySha256", "SmartPerf comparison")?,
        "b9ade0678348e4297c26abde01c951fee3d746a02a0b6e5855f3a53fc2686341",
        "candidate canonical summary digest",
    )?;
    same(
        string(&c["performancePolicy"], "sha256", "SmartPerf comparison")?,
        &policy_sha,
        "comparison policy digest",
    )?;
    same(
        string(&c["profileWorkload"], "sha256", "SmartPerf comparison")?,
        &workload_sha,
        "comparison workload digest",
    )?;
    let metrics = c["metrics"]
        .as_array()
        .ok_or("comparison metrics must be an array")?;
    if metrics.len() != 2 || metrics.iter().any(|row| row["status"] != "passed") {
        return Err("comparison metric verdicts differ".into());
    }
    let cpu = metrics
        .iter()
        .find(|row| row["metric"] == "appCpuUsagePercent")
        .ok_or("CPU comparison missing")?;
    let pss = metrics
        .iter()
        .find(|row| row["metric"] == "appPssKiB")
        .ok_or("PSS comparison missing")?;
    if cpu["guardrail"]["maximumRelativeIncrease"].as_f64() != Some(0.2)
        || cpu["guardrail"]["maximumAbsoluteIncrease"].as_f64() != Some(2.0)
        || pss["guardrail"]["maximumRelativeIncrease"].as_f64() != Some(0.15)
    {
        return Err("comparison guardrails differ".into());
    }
    if text(&root.join("final-hdc-targets.txt"), "final HDC targets")?.trim() != "[Empty]"
        || !regular_bytes(
            &root.join("final-emulator-processes.txt"),
            "final emulator processes",
        )?
        .is_empty()
    {
        return Err("emulator final postcondition differs".into());
    }
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "linux-emulator-functional-and-relative-performance-repeatability-qualified-independent-review-required",
        "candidateRevision": REVISION,
        "candidateSourceSha256": SOURCE_SHA,
        "sourceSetSha256": SOURCE_SET_SHA,
        "appHapSha256": APP_SHA,
        "testHapSha256": TEST_SHA,
        "environmentIdentity": ENVIRONMENT,
        "artifactSha256": {
            "runtimeOracleBridge": bridge.sha256(), "candidateExecutionReceipt": candidate_receipt.sha256(),
            "candidateNativeReport": candidate_report.sha256(), "performancePolicy": policy_sha,
            "profileWorkload": workload_sha, "run1Manifest": run1.manifest.sha256(),
            "run2Manifest": run2.manifest.sha256(), "comparison": comparison.sha256()
        },
        "coverage": {"profileRunCount": 2, "profileSampleCount": 96, "functionalRepeatCount": 12, "functionalAssertionCount": 84},
        "emulatorRelativePerformanceRepeatabilityQualified": true,
        "performanceCalibrated": false,
        "behaviorOracleVerified": false,
        "independentOracleReviewCompleted": false,
        "liveVendorIapExecuted": false,
        "realDeviceExecuted": false,
        "absolutePowerThermalQualified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "Two Linux x86 emulator cold runs each retained 48 SmartPerf samples while six exact OHOS Test suites passed 7/7 without reinstalling the bound HAPs inside the profile window. CPU and PSS passed the predeclared same-environment repeatability policy. This is not distinct baseline/reference/wrong performance calibration, live vendor IAP, real-device, absolute power/thermal, independent Oracle review or case promotion evidence.",
        "nextGate": "independent-semantic-and-oracle-review-then-controlled-baseline-reference-wrong-performance-calibration-and-upstream-reexecution"
    }))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut values = BTreeMap::new();
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
    let bridge = Input::load(&get("--runtime-oracle-bridge")?, "runtime Oracle bridge")?;
    let receipt = Input::load(
        &get("--candidate-execution-receipt")?,
        "candidate execution receipt",
    )?;
    let report = Input::load(
        &get("--candidate-native-report")?,
        "candidate native report",
    )?;
    let root = get("--profile-evidence")?;
    if !fs::symlink_metadata(&root)
        .map_err(|e| format!("cannot inspect profile evidence: {e}"))?
        .file_type()
        .is_dir()
    {
        return Err("profile evidence must be a directory".into());
    }
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = validate(&bridge, &receipt, &report, &root)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|e| format!("cannot write output: {e}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test profile qualification invalid: {error}");
        std::process::exit(1);
    }
}
