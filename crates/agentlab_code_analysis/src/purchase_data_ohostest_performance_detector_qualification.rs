use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

const PROFILE_QUALIFICATION_SCHEMA: &str =
    "agentlab.purchase_data_ohostest_profile_qualification.v1";
const CALIBRATION_SCHEMA: &str =
    "agentlab.purchase_data_ohostest_performance_detector_calibration.v1";
const VARIANT_RUN_SCHEMA: &str = "agentlab.purchase_data_ohostest_performance_variant_run.v1";
const SUMMARY_SCHEMA: &str = "agentlab.smartperf_summary.v2";
const COMPARISON_SCHEMA: &str = "agentlab.smartperf_comparison.v1";
const RECEIPT_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const REPORT_SCHEMA: &str = "agentlab.harmony_hypium_native_report.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_performance_detector_qualification.v1";
const REVISION: &str = "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8";
const SOURCE_SET_SHA: &str = "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2";
const BASE_APP_SHA: &str = "dfd61c2e5a33249aed059192798c449f7ab3a3a44d69b900fdd508978cdda073";
const BASE_TEST_SHA: &str = "5a2015114fd435daba3e25331df6a7ac48445827230079870cc2571c710934fe";
const WRONG_APP_SHA: &str = "7bf92151da1a85ba3291c4997d5f4e291cc38833f5e5dbef72a4b2e42ec2a7b3";
const WRONG_TEST_SHA: &str = "2a9ee43900d7f4813b896909bc40b192319f7db79df117f4e4243b56278d53b5";
const BASE_SOURCE_SHA: &str = "daf0f32975c9c9d05174995b165669d3b19388df03f2d6b8284131cab9c1aea0";
const WRONG_SOURCE_SHA: &str = "99c0dd5acdf45973401cd8fefd7bc9daa055af4a12342ae8d0c3656c34f3924f";
const RUNNER_SCRIPT_SHA: &str = "094883ee81762c3acde40c4e8a3a723f5f0e5a223fb18f9434ebc7e8e01199ff";
const EXPLORATORY_FAILURE_SHA: &str =
    "455d62f3d1aaf2171cef03ae46a3515993f1a33ae1b6ddf76c1bc8fc59fb14f3";
const REPORT_SHA: &str = "123fbf9bcff0dbf9c946b60e7f407b4695582072c45f15ebc249cb33aa93ba65";
const ENVIRONMENT: &str = "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7";
const POLICY_ID: &str = "purchase-data-ohostest-cpu-pss-repeatability-v2";
const POLICY_SHA: &str = "3a431b7567c21946b7c2869b3f617b55a422c3f2fc953669d64c2e576d6c8a95";
const WORKLOAD_ID: &str = "purchase-data-ohostest-foreground-repeat-v3";
const WORKLOAD_SHA: &str = "9a9430a6267db477461d9d7466513cbd8e97e6b571647537175709e8a0ac3781";
const TASK_ID: &str = "purchase-data-finalization-ee2bc87594f1";
const CASE_ID: &str = "purchase-data-finalization-candidate-clean-v1";
const BASELINE_CANONICAL_SUMMARY_SHA: &str =
    "577e4b671f0886e69e671babbf7c0eeda351c91d8d2384610d56f01ff2bc122e";
const WRONG_RUN_1_CANONICAL_SUMMARY_SHA: &str =
    "7e2bfce67e1278ace08cfed356e79a63feb4a6a5defda6b2d0b7aca2c5571c65";
const WRONG_RUN_2_CANONICAL_SUMMARY_SHA: &str =
    "52fcc56e2406fb2f5a1122d3a32aaae26614d87df02f0c6f46fd1789453f707f";

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

fn string<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    value[key]
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
fn number(value: &Value, key: &str, label: &str) -> Result<f64, String> {
    value[key]
        .as_f64()
        .filter(|n| n.is_finite())
        .ok_or_else(|| format!("{label} {key} is invalid"))
}
fn close(actual: f64, expected: f64, label: &str) -> Result<(), String> {
    let tolerance = 1e-9_f64.max(expected.abs() * 1e-12);
    if (actual - expected).abs() > tolerance {
        return Err(format!("{label} differs"));
    }
    Ok(())
}

fn validate_profile_qualification(path: &Path) -> Result<Input, String> {
    let input = Input::load(path, "profile qualification")?;
    let value = &input.value;
    same(
        string(value, "schema", "profile qualification")?,
        PROFILE_QUALIFICATION_SCHEMA,
        "profile qualification schema",
    )?;
    same(
        string(value, "candidateRevision", "profile qualification")?,
        REVISION,
        "profile candidate revision",
    )?;
    same(
        string(value, "sourceSetSha256", "profile qualification")?,
        SOURCE_SET_SHA,
        "profile source set",
    )?;
    same(
        string(value, "appHapSha256", "profile qualification")?,
        BASE_APP_SHA,
        "profile app HAP",
    )?;
    same(
        string(value, "testHapSha256", "profile qualification")?,
        BASE_TEST_SHA,
        "profile test HAP",
    )?;
    exact_bool(
        value,
        "emulatorRelativePerformanceRepeatabilityQualified",
        true,
        "profile qualification",
    )?;
    for key in [
        "performanceCalibrated",
        "behaviorOracleVerified",
        "independentOracleReviewCompleted",
        "liveVendorIapExecuted",
        "realDeviceExecuted",
        "absolutePowerThermalQualified",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(value, key, false, "profile qualification")?;
    }
    Ok(input)
}

fn validate_sources(root: &Path) -> Result<(), String> {
    let base = regular_bytes(&root.join("EntryPage.base.ets"), "base EntryPage source")?;
    let wrong = regular_bytes(
        &root.join("EntryPage.controlled-wrong.ets"),
        "controlled wrong EntryPage source",
    )?;
    same(&digest(&base), BASE_SOURCE_SHA, "base source digest")?;
    same(
        &digest(&wrong),
        WRONG_SOURCE_SHA,
        "controlled wrong source digest",
    )?;
    let base_text =
        String::from_utf8(base).map_err(|e| format!("base source is not UTF-8: {e}"))?;
    let wrong_text = String::from_utf8(wrong)
        .map_err(|e| format!("controlled wrong source is not UTF-8: {e}"))?;
    let mut expected = base_text.replacen(
        "struct EntryPage {\n  private vpValue",
        "struct EntryPage {\n  private retainedCalibrationMemory: Uint8Array = new Uint8Array(64 * 1024 * 1024);\n  private performanceCalibrationTimer: number = -1;\n  private performanceCalibrationAccumulator: number = 1;\n  private vpValue",
        1,
    ).replacen(
        "  aboutToAppear() {\n  }",
        "  aboutToAppear() {\n    for (let offset: number = 0; offset < this.retainedCalibrationMemory.length; offset += 4096) {\n      this.retainedCalibrationMemory[offset] = 1;\n    }\n    this.performanceCalibrationTimer = setInterval(() => {\n      const deadline: number = Date.now() + 400;\n      while (Date.now() < deadline) {\n        this.performanceCalibrationAccumulator =\n          (this.performanceCalibrationAccumulator * 1664525 + 1013904223) % 2147483647;\n      }\n    }, 500);\n  }\n\n  aboutToDisappear() {\n    if (this.performanceCalibrationTimer >= 0) {\n      clearInterval(this.performanceCalibrationTimer);\n    }\n  }",
        1,
    );
    if !expected.ends_with('\n') {
        expected.push('\n');
    }
    if wrong_text != expected {
        return Err("controlled wrong source mutation differs".into());
    }
    same(
        &digest(&regular_bytes(
            &root.join("run-controlled-performance.sh"),
            "calibration runner",
        )?),
        RUNNER_SCRIPT_SHA,
        "calibration runner digest",
    )
}

fn validate_summary(
    input: &Input,
    run_id: &str,
    source_sha: &str,
    label: &str,
) -> Result<(f64, f64), String> {
    let value = &input.value;
    same(
        string(value, "schema", label)?,
        SUMMARY_SCHEMA,
        &format!("{label} schema"),
    )?;
    same(
        string(value, "taskId", label)?,
        TASK_ID,
        &format!("{label} task"),
    )?;
    same(
        string(value, "sourceIdentity", label)?,
        &format!("artifact-sha256:{source_sha}"),
        &format!("{label} source identity"),
    )?;
    same(
        string(value, "runId", label)?,
        run_id,
        &format!("{label} run id"),
    )?;
    same(
        string(value, "environmentIdentity", label)?,
        ENVIRONMENT,
        &format!("{label} environment"),
    )?;
    exact_bool(value, "profileValid", true, label)?;
    exact_u64(value, "sampleCount", 48, label)?;
    same(
        string(&value["performancePolicy"], "id", label)?,
        POLICY_ID,
        &format!("{label} policy id"),
    )?;
    same(
        string(&value["performancePolicy"], "sha256", label)?,
        POLICY_SHA,
        &format!("{label} policy digest"),
    )?;
    same(
        string(&value["profileWorkload"], "id", label)?,
        WORKLOAD_ID,
        &format!("{label} workload id"),
    )?;
    same(
        string(&value["profileWorkload"], "sha256", label)?,
        WORKLOAD_SHA,
        &format!("{label} workload digest"),
    )?;
    let cpu = number(
        &value["canonicalMetrics"]["appCpuUsagePercent"],
        "mean",
        label,
    )?;
    let pss = number(&value["canonicalMetrics"]["appPssKiB"], "mean", label)?;
    if cpu < 0.0 || pss <= 0.0 {
        return Err(format!("{label} canonical metrics are invalid"));
    }
    Ok((cpu, pss))
}

fn validate_report(input: &Input, label: &str) -> Result<(), String> {
    same(
        string(&input.value, "schema", label)?,
        REPORT_SCHEMA,
        &format!("{label} schema"),
    )?;
    exact_bool(&input.value, "passed", true, label)?;
    exact_bool(&input.value, "timedOut", false, label)?;
    exact_u64(&input.value, "processExitCode", 0, label)?;
    exact_u64(&input.value, "nativeFinalCode", 0, label)?;
    exact_u64(&input.value["counts"], "total", 7, label)?;
    exact_u64(&input.value["counts"], "pass", 7, label)?;
    for key in ["failure", "error", "ignore"] {
        exact_u64(&input.value["counts"], key, 0, label)?;
    }
    same(
        &input.sha256(),
        REPORT_SHA,
        &format!("{label} canonical digest"),
    )
}

fn validate_variant(root: &Path, run_id: &str) -> Result<(Input, Input, f64, f64), String> {
    let run = root.join(run_id);
    let manifest = Input::load(
        &run.join("run-manifest.json"),
        &format!("{run_id} manifest"),
    )?;
    let summary = Input::load(
        &run.join("smartperf-summary.json"),
        &format!("{run_id} summary"),
    )?;
    let value = &manifest.value;
    same(
        string(value, "schema", "variant manifest")?,
        VARIANT_RUN_SCHEMA,
        "variant manifest schema",
    )?;
    same(
        string(value, "status", "variant manifest")?,
        "passed",
        "variant status",
    )?;
    same(
        string(value, "runId", "variant manifest")?,
        run_id,
        "variant run id",
    )?;
    same(
        string(value, "role", "variant manifest")?,
        "controlled-meaningful-wrong-not-agent-not-gold",
        "variant role",
    )?;
    same(
        string(value, "baseRevision", "variant manifest")?,
        REVISION,
        "variant base revision",
    )?;
    same(
        string(value, "sourceSetSha256", "variant manifest")?,
        SOURCE_SET_SHA,
        "variant source set",
    )?;
    same(
        string(value, "baselineAppHapSha256", "variant manifest")?,
        BASE_APP_SHA,
        "variant baseline app",
    )?;
    same(
        string(value, "appHapSha256", "variant manifest")?,
        WRONG_APP_SHA,
        "variant app HAP",
    )?;
    same(
        string(value, "testHapSha256", "variant manifest")?,
        WRONG_TEST_SHA,
        "variant test HAP",
    )?;
    same(
        string(value, "environmentIdentity", "variant manifest")?,
        ENVIRONMENT,
        "variant environment",
    )?;
    let mutation = &value["controlledMutation"];
    same(
        string(mutation, "id", "controlled mutation")?,
        "retain-64m-and-bounded-cpu-entry-page-v2",
        "mutation id",
    )?;
    same(
        string(mutation, "kind", "controlled mutation")?,
        "combined-cpu-memory",
        "mutation kind",
    )?;
    exact_u64(mutation, "bytes", 67_108_864, "controlled mutation")?;
    exact_u64(mutation, "intervalMs", 500, "controlled mutation")?;
    exact_u64(mutation, "busyWindowMs", 400, "controlled mutation")?;
    same(
        string(mutation, "sourcePath", "controlled mutation")?,
        "entry/src/main/ets/pages/EntryPage.ets",
        "mutation source path",
    )?;
    same(
        string(mutation, "baseSourceFileSha256", "controlled mutation")?,
        BASE_SOURCE_SHA,
        "mutation base digest",
    )?;
    same(
        string(mutation, "candidateSourceFileSha256", "controlled mutation")?,
        WRONG_SOURCE_SHA,
        "mutation candidate digest",
    )?;
    exact_u64(value, "functionalRepeatCount", 6, "variant manifest")?;
    exact_u64(value, "profileSampleCount", 48, "variant manifest")?;
    exact_bool(
        value,
        "functionalRepeatsWithinProfileWindow",
        true,
        "variant manifest",
    )?;
    exact_bool(
        value,
        "performanceDetectorCalibrationOnly",
        true,
        "variant manifest",
    )?;
    for key in [
        "liveVendorIapExecuted",
        "realDeviceExecuted",
        "absolutePowerThermalAuthority",
        "automaticPromotion",
    ] {
        exact_bool(value, key, false, "variant manifest")?;
    }
    same(
        string(value, "smartPerfSummarySha256", "variant manifest")?,
        &summary.sha256(),
        "variant summary digest",
    )?;
    same(
        string(value, "performancePolicySha256", "variant manifest")?,
        POLICY_SHA,
        "variant policy digest",
    )?;
    same(
        string(value, "profileWorkloadSha256", "variant manifest")?,
        WORKLOAD_SHA,
        "variant workload digest",
    )?;
    let actions = regular_bytes(
        &run.join("profile-workload-actions.tsv"),
        "variant workload actions",
    )?;
    same(
        string(value, "profileWorkloadActionsSha256", "variant manifest")?,
        &digest(&actions),
        "variant workload actions digest",
    )?;
    if String::from_utf8_lossy(&actions).lines().count() != 13 {
        return Err("variant workload action count differs".into());
    }
    let window_start = string(value, "profileWindowStartedAt", "variant manifest")?;
    let window_finish = string(value, "profileWindowFinishedAt", "variant manifest")?;
    let repeats = value["functionalRepeats"]
        .as_array()
        .ok_or("functional repeats must be an array")?;
    if repeats.len() != 6 {
        return Err("functional repeat count differs".into());
    }
    for (index, retained) in repeats.iter().enumerate() {
        let ordinal = index + 1;
        if retained["ordinal"].as_u64() != Some(ordinal as u64) {
            return Err("functional repeat ordinal differs".into());
        }
        let test = run.join("tests").join(ordinal.to_string());
        let receipt = Input::load(
            &test.join("receipt.json"),
            &format!("{run_id} receipt {ordinal}"),
        )?;
        let report = Input::load(
            &test.join("native-report.json"),
            &format!("{run_id} report {ordinal}"),
        )?;
        same(
            string(retained, "receiptSha256", "retained repeat")?,
            &receipt.sha256(),
            "retained receipt digest",
        )?;
        same(
            string(retained, "nativeReportSha256", "retained repeat")?,
            &report.sha256(),
            "retained report digest",
        )?;
        validate_report(&report, &format!("{run_id} report {ordinal}"))?;
        same(
            string(&receipt.value, "schema", "functional receipt")?,
            RECEIPT_SCHEMA,
            "functional receipt schema",
        )?;
        same(
            string(&receipt.value, "caseId", "functional receipt")?,
            CASE_ID,
            "functional receipt case",
        )?;
        same(
            string(&receipt.value, "sourceSetSha256", "functional receipt")?,
            SOURCE_SET_SHA,
            "functional receipt source set",
        )?;
        same(
            string(
                &receipt.value["packages"]["app"],
                "sha256",
                "functional receipt",
            )?,
            WRONG_APP_SHA,
            "functional receipt app HAP",
        )?;
        same(
            string(
                &receipt.value["packages"]["test"],
                "sha256",
                "functional receipt",
            )?,
            WRONG_TEST_SHA,
            "functional receipt test HAP",
        )?;
        same(
            string(&receipt.value["report"], "sha256", "functional receipt")?,
            &report.sha256(),
            "functional receipt report",
        )?;
        exact_bool(&receipt.value, "passed", true, "functional receipt")?;
        exact_bool(
            &receipt.value,
            "packagesInstalled",
            false,
            "functional receipt",
        )?;
        exact_bool(
            &receipt.value,
            "automaticPromotion",
            false,
            "functional receipt",
        )?;
        let started = string(&receipt.value, "startedAt", "functional receipt")?;
        let finished = string(&receipt.value, "finishedAt", "functional receipt")?;
        if !(window_start <= started && started <= finished && finished <= window_finish) {
            return Err("functional receipt escaped profile window".into());
        }
    }
    let (cpu, pss) = validate_summary(
        &summary,
        run_id,
        WRONG_APP_SHA,
        &format!("{run_id} summary"),
    )?;
    let raw = regular_bytes(&run.join("smartperf.txt"), "variant raw SmartPerf")?;
    same(
        string(&summary.value["input"], "sha256", "variant summary")?,
        &digest(&raw),
        "variant raw SmartPerf digest",
    )?;
    Ok((manifest, summary, cpu, pss))
}

fn validate_comparison(
    path: &Path,
    baseline_metrics: (f64, f64),
    candidate_metrics: (f64, f64),
    run_id: &str,
) -> Result<(Input, Vec<String>), String> {
    let input = Input::load(path, &format!("{run_id} comparison"))?;
    let value = &input.value;
    same(
        string(value, "schema", "comparison")?,
        COMPARISON_SCHEMA,
        "comparison schema",
    )?;
    same(
        string(value, "taskId", "comparison")?,
        TASK_ID,
        "comparison task",
    )?;
    same(
        string(value, "baselineRunId", "comparison")?,
        "run-1",
        "comparison baseline run",
    )?;
    same(
        string(value, "candidateRunId", "comparison")?,
        run_id,
        "comparison candidate run",
    )?;
    same(
        string(value, "baselineSourceIdentity", "comparison")?,
        &format!("artifact-sha256:{BASE_APP_SHA}"),
        "comparison baseline identity",
    )?;
    same(
        string(value, "candidateSourceIdentity", "comparison")?,
        &format!("artifact-sha256:{WRONG_APP_SHA}"),
        "comparison candidate identity",
    )?;
    same(
        string(value, "baselineSummarySha256", "comparison")?,
        BASELINE_CANONICAL_SUMMARY_SHA,
        "comparison baseline digest",
    )?;
    same(
        string(value, "candidateSummarySha256", "comparison")?,
        if run_id == "wrong-run-1" {
            WRONG_RUN_1_CANONICAL_SUMMARY_SHA
        } else {
            WRONG_RUN_2_CANONICAL_SUMMARY_SHA
        },
        "comparison candidate digest",
    )?;
    same(
        string(value, "environmentIdentity", "comparison")?,
        ENVIRONMENT,
        "comparison environment",
    )?;
    same(
        string(&value["performancePolicy"], "sha256", "comparison")?,
        POLICY_SHA,
        "comparison policy",
    )?;
    same(
        string(&value["profileWorkload"], "sha256", "comparison")?,
        WORKLOAD_SHA,
        "comparison workload",
    )?;
    exact_bool(value, "comparable", true, "comparison")?;
    same(
        string(value, "decision", "comparison")?,
        "performance-regression-candidate",
        "comparison decision",
    )?;
    let metrics = value["metrics"]
        .as_array()
        .ok_or("comparison metrics must be an array")?;
    if metrics.len() != 2 {
        return Err("comparison metric count differs".into());
    }
    let mut regressed = Vec::new();
    for (metric, baseline_value, candidate_value, relative, absolute) in [
        (
            "appCpuUsagePercent",
            baseline_metrics.0,
            candidate_metrics.0,
            0.20,
            Some(2.0),
        ),
        (
            "appPssKiB",
            baseline_metrics.1,
            candidate_metrics.1,
            0.15,
            None,
        ),
    ] {
        let row = metrics
            .iter()
            .find(|row| row["metric"] == metric)
            .ok_or_else(|| format!("comparison {metric} is absent"))?;
        close(
            number(row, "baseline", "comparison metric")?,
            baseline_value,
            "comparison baseline value",
        )?;
        close(
            number(row, "candidate", "comparison metric")?,
            candidate_value,
            "comparison candidate value",
        )?;
        let increase = candidate_value - baseline_value;
        let ratio = candidate_value / baseline_value;
        close(
            number(row, "absoluteIncrease", "comparison metric")?,
            increase,
            "comparison absolute increase",
        )?;
        close(
            number(row, "candidateToBaselineRatio", "comparison metric")?,
            ratio,
            "comparison ratio",
        )?;
        close(
            number(
                &row["guardrail"],
                "maximumRelativeIncrease",
                "comparison guardrail",
            )?,
            relative,
            "comparison relative guardrail",
        )?;
        if let Some(bound) = absolute {
            close(
                number(
                    &row["guardrail"],
                    "maximumAbsoluteIncrease",
                    "comparison guardrail",
                )?,
                bound,
                "comparison absolute guardrail",
            )?;
        }
        let passed = ratio <= 1.0 + relative || absolute.is_some_and(|bound| increase <= bound);
        let expected = if passed { "passed" } else { "regressed" };
        same(
            string(row, "status", "comparison metric")?,
            expected,
            "comparison metric verdict",
        )?;
        if !passed {
            regressed.push(metric.to_string());
        }
    }
    if !regressed
        .iter()
        .any(|metric| metric == "appCpuUsagePercent")
    {
        return Err("controlled wrong did not regress appCpuUsagePercent".into());
    }
    Ok((input, regressed))
}

fn validate(profile_qualification: &Input, root: &Path) -> Result<Value, String> {
    validate_sources(root)?;
    let exploratory = Input::load(
        &root.join("exploratory-retained-memory-failure.json"),
        "exploratory retained-memory failure",
    )?;
    same(
        &exploratory.sha256(),
        EXPLORATORY_FAILURE_SHA,
        "exploratory failure digest",
    )?;
    same(
        string(&exploratory.value, "status", "exploratory failure")?,
        "rejected-no-repeatable-common-regression",
        "exploratory failure status",
    )?;
    if exploratory.value["consistentRegressedMetrics"]
        .as_array()
        .map(Vec::is_empty)
        != Some(true)
    {
        return Err("exploratory failure unexpectedly qualified".into());
    }
    exact_bool(
        &exploratory.value,
        "automaticPromotion",
        false,
        "exploratory failure",
    )?;
    let policy = Input::load(&root.join("performance-policy.json"), "performance policy")?;
    same(&policy.sha256(), POLICY_SHA, "performance policy digest")?;
    let workload = regular_bytes(&root.join("profile-workload.tsv"), "profile workload")?;
    same(&digest(&workload), WORKLOAD_SHA, "profile workload digest")?;
    let baseline_manifest =
        Input::load(&root.join("run-1/run-manifest.json"), "baseline manifest")?;
    same(
        string(
            &baseline_manifest.value,
            "appHapSha256",
            "baseline manifest",
        )?,
        BASE_APP_SHA,
        "baseline app HAP",
    )?;
    same(
        string(
            &baseline_manifest.value,
            "testHapSha256",
            "baseline manifest",
        )?,
        BASE_TEST_SHA,
        "baseline test HAP",
    )?;
    let baseline_summary = Input::load(
        &root.join("run-1/smartperf-summary.json"),
        "baseline summary",
    )?;
    let baseline_metrics =
        validate_summary(&baseline_summary, "run-1", BASE_APP_SHA, "baseline summary")?;
    let baseline_raw = regular_bytes(&root.join("run-1/smartperf.txt"), "baseline raw SmartPerf")?;
    same(
        string(
            &baseline_summary.value["input"],
            "sha256",
            "baseline summary",
        )?,
        &digest(&baseline_raw),
        "baseline raw SmartPerf digest",
    )?;
    let (manifest1, summary1, cpu1, pss1) = validate_variant(root, "wrong-run-1")?;
    let (manifest2, summary2, cpu2, pss2) = validate_variant(root, "wrong-run-2")?;
    let (comparison1, regressed1) = validate_comparison(
        &root.join("wrong-comparison-1.json"),
        baseline_metrics,
        (cpu1, pss1),
        "wrong-run-1",
    )?;
    let (comparison2, regressed2) = validate_comparison(
        &root.join("wrong-comparison-2.json"),
        baseline_metrics,
        (cpu2, pss2),
        "wrong-run-2",
    )?;
    let common: Vec<String> = regressed1
        .into_iter()
        .filter(|metric| regressed2.contains(metric))
        .collect();
    if !common.iter().any(|metric| metric == "appCpuUsagePercent") {
        return Err("controlled wrong repeats lack common CPU regression".into());
    }
    let calibration = Input::load(
        &root.join("controlled-performance-calibration.json"),
        "detector calibration",
    )?;
    let value = &calibration.value;
    same(
        string(value, "schema", "detector calibration")?,
        CALIBRATION_SCHEMA,
        "detector calibration schema",
    )?;
    same(
        string(value, "status", "detector calibration")?,
        "qualified-review-required",
        "detector calibration status",
    )?;
    same(
        string(value, "caseId", "detector calibration")?,
        CASE_ID,
        "detector calibration case",
    )?;
    same(
        string(value, "baseRevision", "detector calibration")?,
        REVISION,
        "detector calibration revision",
    )?;
    same(
        string(value, "sourceSetSha256", "detector calibration")?,
        SOURCE_SET_SHA,
        "detector calibration source set",
    )?;
    same(
        string(&value["baseline"], "appHapSha256", "detector calibration")?,
        BASE_APP_SHA,
        "detector baseline HAP",
    )?;
    same(
        string(&value["baseline"], "summarySha256", "detector calibration")?,
        &baseline_summary.sha256(),
        "detector baseline summary",
    )?;
    same(
        string(&value["baseline"], "manifestSha256", "detector calibration")?,
        &baseline_manifest.sha256(),
        "detector baseline manifest",
    )?;
    same(
        string(
            &value["controlledWrong"],
            "appHapSha256",
            "detector calibration",
        )?,
        WRONG_APP_SHA,
        "detector wrong app HAP",
    )?;
    same(
        string(
            &value["controlledWrong"],
            "testHapSha256",
            "detector calibration",
        )?,
        WRONG_TEST_SHA,
        "detector wrong test HAP",
    )?;
    let run_ids = value["controlledWrong"]["runIds"]
        .as_array()
        .ok_or("detector run ids must be an array")?;
    if run_ids != &vec![json!("wrong-run-1"), json!("wrong-run-2")] {
        return Err("detector run ids differ".into());
    }
    let expected_manifest_shas = vec![json!(manifest1.sha256()), json!(manifest2.sha256())];
    if value["controlledWrong"]["manifestSha256s"].as_array() != Some(&expected_manifest_shas) {
        return Err("detector manifest digests differ".into());
    }
    let expected_summary_shas = vec![json!(summary1.sha256()), json!(summary2.sha256())];
    if value["controlledWrong"]["summarySha256s"].as_array() != Some(&expected_summary_shas) {
        return Err("detector summary digests differ".into());
    }
    let expected_comparison_shas = vec![json!(comparison1.sha256()), json!(comparison2.sha256())];
    if value["comparisonSha256s"].as_array() != Some(&expected_comparison_shas) {
        return Err("detector comparison digests differ".into());
    }
    if value["consistentRegressedMetrics"]
        .as_array()
        .map(|rows| rows.iter().any(|row| row == "appCpuUsagePercent"))
        != Some(true)
    {
        return Err("detector common CPU regression is absent".into());
    }
    exact_u64(
        value,
        "functionalAssertionCount",
        84,
        "detector calibration",
    )?;
    exact_u64(value, "profileSampleCount", 96, "detector calibration")?;
    exact_bool(
        value,
        "relativePerformanceDetectorCalibrated",
        true,
        "detector calibration",
    )?;
    for key in [
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "performanceCalibrated",
        "automaticPromotion",
    ] {
        exact_bool(value, key, false, "detector calibration")?;
    }
    same(
        string(&value["authority"], "functional", "detector calibration")?,
        "ohosTest-hypium-source-bound",
        "detector functional authority",
    )?;
    same(
        string(
            &value["authority"],
            "relativePerformance",
            "detector calibration",
        )?,
        "smartperf-emulator-proxy",
        "detector performance authority",
    )?;
    same(
        string(
            &value["authority"],
            "absolutePowerThermal",
            "detector calibration",
        )?,
        "unavailable-on-emulator",
        "detector power thermal authority",
    )?;
    if String::from_utf8_lossy(&regular_bytes(
        &root.join("final-calibration-hdc-targets.txt"),
        "final HDC targets",
    )?)
    .trim()
        != "[Empty]"
        || !regular_bytes(
            &root.join("final-calibration-emulator-processes.txt"),
            "final emulator processes",
        )?
        .is_empty()
    {
        return Err("calibration final postcondition differs".into());
    }
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "controlled-performance-detector-qualified-independent-review-required",
        "candidateRevision": REVISION,
        "sourceSetSha256": SOURCE_SET_SHA,
        "environmentIdentity": ENVIRONMENT,
        "baselineAppHapSha256": BASE_APP_SHA,
        "controlledWrongAppHapSha256": WRONG_APP_SHA,
        "controlledWrongTestHapSha256": WRONG_TEST_SHA,
        "controlledMutation": value["controlledWrong"]["mutation"].clone(),
        "artifactSha256": {
            "profileQualification": profile_qualification.sha256(), "calibration": calibration.sha256(),
            "runner": RUNNER_SCRIPT_SHA, "policy": POLICY_SHA, "workload": WORKLOAD_SHA,
            "exploratoryRetainedMemoryFailure": EXPLORATORY_FAILURE_SHA,
            "baselineSummary": baseline_summary.sha256(), "wrongRun1Manifest": manifest1.sha256(),
            "wrongRun2Manifest": manifest2.sha256(), "wrongRun1Summary": summary1.sha256(),
            "wrongRun2Summary": summary2.sha256(), "wrongComparison1": comparison1.sha256(),
            "wrongComparison2": comparison2.sha256()
        },
        "coverage": {"baselineProfileRunCount": 1, "controlledWrongProfileRunCount": 2, "controlledWrongFunctionalRepeatCount": 12, "controlledWrongFunctionalAssertionCount": 84, "controlledWrongProfileSampleCount": 96},
        "metrics": {"baseline": {"appCpuUsagePercentMean": baseline_metrics.0, "appPssKiBMean": baseline_metrics.1}, "wrongRun1": {"appCpuUsagePercentMean": cpu1, "appPssKiBMean": pss1}, "wrongRun2": {"appCpuUsagePercentMean": cpu2, "appPssKiBMean": pss2}, "consistentRegressedMetrics": common},
        "controlledMeaningfulWrongFunctionallyQualified": true,
        "relativePerformanceDetectorCalibrated": true,
        "emulatorRelativePerformanceRepeatabilityQualified": true,
        "distinctBaselineReferenceWrongCaseCalibrationComplete": false,
        "performanceCalibrated": false,
        "independentOracleReviewCompleted": false,
        "liveVendorIapExecuted": false,
        "realDeviceExecuted": false,
        "absolutePowerThermalQualified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "The exact clean candidate remains functionally passing while a controlled combined 64 MiB retained-memory and 400/500 ms bounded-CPU variant passes 84/84 OHOS Test assertions and is rejected in two cold runs by the predeclared emulator CPU guardrail. This Rust qualification calibrates the relative performance detector only; the controlled variant is not an Agent run, unseen case or gold repair, and it does not complete distinct baseline/reference/wrong case calibration, independent review, live vendor IAP, real-device or absolute power/thermal qualification.",
        "nextGate": "independent-semantic-and-oracle-review-then-distinct-case-variant-performance-calibration-and-upstream-reexecution"
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
    let profile = validate_profile_qualification(&get("--profile-qualification")?)?;
    let root = get("--calibration-evidence")?;
    if !fs::symlink_metadata(&root)
        .map_err(|e| format!("cannot inspect calibration evidence: {e}"))?
        .file_type()
        .is_dir()
    {
        return Err("calibration evidence must be a directory".into());
    }
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = validate(&profile, &root)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|e| format!("cannot write output: {e}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test performance detector qualification invalid: {error}");
        std::process::exit(1);
    }
}
