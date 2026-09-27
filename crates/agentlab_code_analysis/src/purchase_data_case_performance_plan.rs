use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_case_performance_calibration_plan.v1";
const CANDIDATE_ID: &str = "purchase-data-finalization-ee2bc87594f1";
const CANDIDATE_REVISION: &str = "ee2bc87594f1d59e136d4c2c1f1e7e5444f9ccf8";
const SOURCE_SET: &str = "cbc01c94755f2d8da5449902ad1a309488d0a9defa9fede23318ad360dd4c2c2";
const SOURCE_SHA: &str = "cd53dcfe1c5e364d67b57e59e27f4336c32d6058ef5abf45bd75385817d24bb0";
const ENVIRONMENT: &str = "hwlinux:emulator-26.0.0.821:harmonyos-7.0.0-phone-x86:codex-phone-7";

const INPUTS: &[(&str, &str, &str)] = &[
    (
        "integrated-review-packet",
        "purchase-data-integrated-review-packet.json",
        "agentlab.purchase_data_integrated_review_packet.v1",
    ),
    (
        "functional-mutation-plan",
        "purchase-data-ohostest-mutation-plan.json",
        "agentlab.purchase_data_ohostest_mutation_plan.v1",
    ),
    (
        "functional-mutation-qualification",
        "purchase-data-ohostest-mutation-qualification.json",
        "agentlab.purchase_data_ohostest_mutation_qualification.v1",
    ),
    (
        "clean-profile-qualification",
        "purchase-data-ohostest-profile-qualification.json",
        "agentlab.purchase_data_ohostest_profile_qualification.v1",
    ),
    (
        "performance-detector-qualification",
        "purchase-data-ohostest-performance-detector-qualification.json",
        "agentlab.purchase_data_ohostest_performance_detector_qualification.v1",
    ),
    (
        "case-performance-policy",
        "purchase-data-case-performance-policy.json",
        "agentlab.harmony_performance_policy.v1",
    ),
];

struct Input {
    path: String,
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(root: &std::path::Path, relative: &str, label: &str) -> Result<Self, String> {
        if relative.starts_with('/') || relative.split('/').any(|part| part == "..") {
            return Err(format!("{label} path is invalid"));
        }
        let path = root.join(relative);
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
            path: relative.to_owned(),
            bytes,
            value,
        })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }
}

struct Workload {
    path: String,
    bytes: Vec<u8>,
}

impl Workload {
    fn load(root: &std::path::Path) -> Result<Self, String> {
        let relative = "purchase-data-case-performance-workload.tsv";
        let path = root.join(relative);
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect case workload: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err("case workload must be a regular file".into());
        }
        let bytes =
            fs::read(path).map_err(|error| format!("cannot read case workload: {error}"))?;
        let text = std::str::from_utf8(&bytes)
            .map_err(|error| format!("case workload is not UTF-8: {error}"))?;
        let expected = concat!(
            "schema\tagentlab.harmony_profile_workload.v1\n",
            "workload\tpurchase-data-case-bound-ohostest-repeat-v1\n",
            "profile-samples\t48\n",
            "start-app\t7\tEntryAbility\txxx.xxx.xxx\n",
            "repeat-ohostest\t6\t8\tOpenHarmonyTestRunner\n",
            "case-bound-function\tplanPurchaseFinalization\n",
            "case-bound-test\tpurchaseFinalizationPerformanceWorkload\t5000\n",
        );
        if text != expected {
            return Err("case workload contract differs".into());
        }
        Ok(Self {
            path: relative.to_owned(),
            bytes,
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

fn validate_integrated(value: &Value) -> Result<(), String> {
    same(
        string(value, "status", "integrated packet")?,
        "current-evidence-bound-independent-dual-review-required",
        "integrated packet status",
    )?;
    same(
        string(value, "runtimeCandidateId", "integrated packet")?,
        CANDIDATE_ID,
        "integrated packet runtime candidate",
    )?;
    same(
        string(
            &value["sourceLineage"],
            "candidateRevision",
            "integrated packet",
        )?,
        CANDIDATE_REVISION,
        "integrated packet candidate revision",
    )?;
    same(
        string(
            &value["sourceLineage"],
            "runtimeSourceSetSha256",
            "integrated packet",
        )?,
        SOURCE_SET,
        "integrated packet runtime source set",
    )?;
    exact_bool(
        value,
        "relativePerformanceDetectorCalibrated",
        true,
        "integrated packet",
    )?;
    for key in [
        "performanceCalibrated",
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(value, key, false, "integrated packet")?;
    }
    Ok(())
}

fn validate_mutation_plan(
    plan: &Value,
    qualification: &Value,
    plan_sha: &str,
) -> Result<(), String> {
    same(
        string(plan, "candidateId", "mutation plan")?,
        CANDIDATE_ID,
        "mutation plan candidate",
    )?;
    same(
        string(&plan["source"], "sha256", "mutation plan source")?,
        SOURCE_SHA,
        "mutation plan source digest",
    )?;
    if plan["variants"].as_array().map(Vec::len) != Some(6) {
        return Err("mutation plan variant count differs".into());
    }
    same(
        string(qualification, "status", "mutation qualification")?,
        "mutation-discrimination-qualified-source-review-still-required",
        "mutation qualification status",
    )?;
    same(
        string(
            qualification,
            "mutationPlanSha256",
            "mutation qualification",
        )?,
        plan_sha,
        "mutation qualification plan digest",
    )?;
    for key in ["candidateRevision", "candidateSourceSha256"] {
        let expected = if key == "candidateRevision" {
            CANDIDATE_REVISION
        } else {
            SOURCE_SHA
        };
        same(
            string(qualification, key, "mutation qualification")?,
            expected,
            &format!("mutation qualification {key}"),
        )?;
    }
    if qualification["variantCount"].as_u64() != Some(6)
        || qualification["killedVariantCount"].as_u64() != Some(6)
        || qualification["testCount"].as_u64() != Some(7)
        || qualification["mutationScore"].as_f64() != Some(1.0)
    {
        return Err("mutation qualification coverage differs".into());
    }
    exact_bool(
        qualification,
        "expectedMatrixVerified",
        true,
        "mutation qualification",
    )?;
    exact_bool(
        qualification,
        "performanceCalibrated",
        false,
        "mutation qualification",
    )?;
    Ok(())
}

fn validate_profile(value: &Value) -> Result<(), String> {
    same(
        string(value, "status", "profile qualification")?,
        "linux-emulator-functional-and-relative-performance-repeatability-qualified-independent-review-required",
        "profile qualification status",
    )?;
    for (key, expected) in [
        ("candidateRevision", CANDIDATE_REVISION),
        ("candidateSourceSha256", SOURCE_SHA),
        ("sourceSetSha256", SOURCE_SET),
        ("environmentIdentity", ENVIRONMENT),
    ] {
        same(
            string(value, key, "profile qualification")?,
            expected,
            &format!("profile qualification {key}"),
        )?;
    }
    if value["coverage"]["profileRunCount"].as_u64() != Some(2)
        || value["coverage"]["profileSampleCount"].as_u64() != Some(96)
    {
        return Err("profile qualification coverage differs".into());
    }
    exact_bool(
        value,
        "emulatorRelativePerformanceRepeatabilityQualified",
        true,
        "profile qualification",
    )?;
    exact_bool(
        value,
        "performanceCalibrated",
        false,
        "profile qualification",
    )
}

fn validate_detector(value: &Value) -> Result<(), String> {
    same(
        string(value, "status", "detector qualification")?,
        "controlled-performance-detector-qualified-independent-review-required",
        "detector qualification status",
    )?;
    for (key, expected) in [
        ("candidateRevision", CANDIDATE_REVISION),
        ("sourceSetSha256", SOURCE_SET),
        ("environmentIdentity", ENVIRONMENT),
    ] {
        same(
            string(value, key, "detector qualification")?,
            expected,
            &format!("detector qualification {key}"),
        )?;
    }
    exact_bool(
        value,
        "relativePerformanceDetectorCalibrated",
        true,
        "detector qualification",
    )?;
    for key in [
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "performanceCalibrated",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(value, key, false, "detector qualification")?;
    }
    let metrics: BTreeSet<&str> = value["metrics"]["consistentRegressedMetrics"]
        .as_array()
        .ok_or_else(|| "detector regressed metrics must be an array".to_owned())?
        .iter()
        .map(|row| {
            row.as_str()
                .ok_or_else(|| "detector regressed metric must be a string".to_owned())
        })
        .collect::<Result<_, _>>()?;
    if metrics != BTreeSet::from(["appCpuUsagePercent"]) {
        return Err("detector regressed metric inventory differs".into());
    }
    Ok(())
}

fn validate_policy(value: &Value) -> Result<(), String> {
    same(
        string(value, "id", "case performance policy")?,
        "purchase-data-case-bound-cpu-pss-v1",
        "case performance policy id",
    )?;
    exact_bool(value, "requiresWorkload", true, "case performance policy")?;
    let required = value["requiredMetrics"]
        .as_array()
        .ok_or_else(|| "case performance required metrics must be an array".to_owned())?;
    let metrics: BTreeSet<&str> = required
        .iter()
        .map(|row| string(row, "metric", "case performance metric"))
        .collect::<Result<_, _>>()?;
    if required.len() != 2 || metrics != BTreeSet::from(["appCpuUsagePercent", "appPssKiB"]) {
        return Err("case performance required metric inventory differs".into());
    }
    same(
        string(
            &value["authority"],
            "absolutePowerThermal",
            "case performance policy",
        )?,
        "unavailable-on-emulator",
        "case performance absolute authority",
    )
}

fn attachment(input: &Input, schema: &str) -> Value {
    json!({
        "path": input.path,
        "sha256": input.sha256(),
        "byteLength": input.bytes.len(),
        "schema": schema,
        "status": input.value["status"].as_str()
    })
}

fn build(root: PathBuf) -> Result<Value, String> {
    let mut inputs = Vec::new();
    for (id, relative, schema) in INPUTS {
        let input = Input::load(&root, relative, id)?;
        same(
            string(&input.value, "schema", id)?,
            schema,
            &format!("{id} schema"),
        )?;
        inputs.push(input);
    }
    let integrated = &inputs[0];
    let mutation_plan = &inputs[1];
    let mutation_qualification = &inputs[2];
    let profile = &inputs[3];
    let detector = &inputs[4];
    let policy = &inputs[5];
    validate_integrated(&integrated.value)?;
    validate_mutation_plan(
        &mutation_plan.value,
        &mutation_qualification.value,
        &mutation_plan.sha256(),
    )?;
    validate_profile(&profile.value)?;
    validate_detector(&detector.value)?;
    validate_policy(&policy.value)?;
    if integrated.value["evidenceAttachments"]["functional-mutation-qualification"]["sha256"]
        != mutation_qualification.sha256()
        || integrated.value["evidenceAttachments"]["profile-qualification"]["sha256"]
            != profile.sha256()
        || integrated.value["evidenceAttachments"]["performance-detector-qualification"]["sha256"]
            != detector.sha256()
    {
        return Err("integrated packet qualification lineage differs".into());
    }
    let workload = Workload::load(&root)?;
    let mut attachments = serde_json::Map::new();
    for ((id, _, schema), input) in INPUTS.iter().zip(&inputs) {
        attachments.insert((*id).into(), attachment(input, schema));
    }
    attachments.insert(
        "case-performance-workload".into(),
        json!({
            "path": workload.path,
            "sha256": workload.sha256(),
            "byteLength": workload.bytes.len(),
            "schema": "agentlab.harmony_profile_workload.v1"
        }),
    );

    let source_path = "entry/src/main/ets/common/PurchaseFinalizationPolicy.ets";
    let test_path = "entry/src/ohosTest/ets/test/PurchaseFinalizationPolicy.test.ets";
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "case-bound-performance-calibration-planned-not-executed",
        "candidateId": CANDIDATE_ID,
        "candidateRevision": CANDIDATE_REVISION,
        "sourceSetSha256": SOURCE_SET,
        "candidateSourceSha256": SOURCE_SHA,
        "environmentIdentity": ENVIRONMENT,
        "evidenceAttachments": attachments,
        "casePerformanceRequirement": {
            "schema": "agentlab.case_performance_requirement.v1",
            "metric": "appCpuUsagePercent",
            "statistic": "mean",
            "direction": "lower",
            "performancePolicySha256": policy.sha256(),
            "profileWorkloadSha256": workload.sha256(),
            "caseBoundFunction": "planPurchaseFinalization",
            "caseBoundWorkloadVerified": false,
            "authority": "same-environment-linux-x86-emulator-relative-proxy"
        },
        "evaluatorWorkloadEdit": {
            "role": "evaluator-only-not-participant-source",
            "path": test_path,
            "insertBefore": "    it('finishRejectionRemainsObservable', 0, async () => {",
            "expectedOccurrenceCount": 1,
            "testName": "purchaseFinalizationPerformanceWorkload",
            "iterationCount": 5000,
            "content": concat!(
                "    it('purchaseFinalizationPerformanceWorkload', 0, () => {\n",
                "      const encodedPurchase = purchaseData(JSON.stringify({\n",
                "        productId: 'p-performance',\n",
                "        productType: '0',\n",
                "        purchaseOrderId: 'order-performance',\n",
                "        purchaseToken: 'token-performance',\n",
                "        finishStatus: '2'\n",
                "      }));\n",
                "      let plan = new PurchaseFinalizationPlan();\n",
                "      for (let iteration: number = 0; iteration < 5000; iteration++) {\n",
                "        plan = planPurchaseFinalization(encodedPurchase, identityDecode);\n",
                "      }\n",
                "      expect(plan.shouldFinish).assertTrue();\n",
                "      expect(plan.request.purchaseToken).assertEqual('token-performance');\n",
                "    })\n\n"
            )
        },
        "calibrationRoles": [
            {
                "role": "reference",
                "id": "clean-candidate-ee2bc87594f1",
                "sourcePath": source_path,
                "sourceSha256": SOURCE_SHA,
                "edit": null,
                "expectedFunctionalResult": "8-of-8-pass",
                "expectedPerformanceResult": "repeatable-reference"
            },
            {
                "role": "baseline-task-start",
                "id": "redundant-purchase-data-reparse-200x-v1",
                "sourcePath": source_path,
                "semanticFault": "The task-start implementation reparses identical purchaseData 200 additional times before reading the same jwsPurchaseOrder.",
                "edit": {
                    "find": "    const jwsPurchaseOrder = (JSON.parse(purchaseData) as PurchaseData).jwsPurchaseOrder;",
                    "replace": concat!(
                        "    let parsedPurchaseData = JSON.parse(purchaseData) as PurchaseData;\n",
                        "    for (let pass: number = 0; pass < 200; pass++) {\n",
                        "      parsedPurchaseData = JSON.parse(purchaseData) as PurchaseData;\n",
                        "    }\n",
                        "    const jwsPurchaseOrder = parsedPurchaseData.jwsPurchaseOrder;"
                    ),
                    "expectedOccurrenceCount": 1
                },
                "expectedFunctionalResult": "8-of-8-pass",
                "expectedPerformanceResult": "rejected-versus-reference-on-appCpuUsagePercent"
            },
            {
                "role": "meaningful-wrong",
                "id": "redundant-purchase-order-decode-1000x-v2",
                "sourcePath": source_path,
                "semanticFault": "The implementation repeats the same JWS decode and payload parse 1000 additional times before using an equivalent final payload.",
                "edit": {
                    "find": "    const purchaseOrderPayload =\n      JSON.parse(decodeJws(jwsPurchaseOrder)) as PurchaseOrderPayload;",
                    "replace": concat!(
                        "    let purchaseOrderPayload =\n",
                        "      JSON.parse(decodeJws(jwsPurchaseOrder)) as PurchaseOrderPayload;\n",
                        "    for (let pass: number = 0; pass < 1000; pass++) {\n",
                        "      purchaseOrderPayload =\n",
                        "        JSON.parse(decodeJws(jwsPurchaseOrder)) as PurchaseOrderPayload;\n",
                        "    }"
                    ),
                    "expectedOccurrenceCount": 1
                },
                "expectedFunctionalResult": "8-of-8-pass",
                "expectedPerformanceResult": "rejected-versus-reference-on-appCpuUsagePercent"
            }
        ],
        "executionMatrix": {
            "coldRunCountPerRole": 2,
            "roleCount": 3,
            "totalColdRunCount": 6,
            "profileSampleCountPerRun": 48,
            "functionalRepeatCountPerRun": 6,
            "functionalTestCountPerRepeat": 8,
            "expectedFunctionalVerdictCountPerRole": 96,
            "requiredCommonRegressedMetric": "appCpuUsagePercent",
            "requiresNoInstallInsideProfileWindow": true,
            "requiresEmulatorPortReleasedAfterEveryRun": true
        },
        "execution": {
            "referenceBuilt": false,
            "baselineBuilt": false,
            "meaningfulWrongBuilt": false,
            "linuxX86EmulatorExecuted": false,
            "functionalMatrixVerified": false,
            "caseBoundWorkloadObserved": false,
            "performanceMatrixVerified": false
        },
        "relativePerformanceDetectorCalibrated": true,
        "distinctBaselineReferenceWrongCaseCalibrationComplete": false,
        "performanceCalibrated": false,
        "absolutePowerThermalQualified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This plan replaces the unrelated EntryPage load with an evaluator-owned workload and two functionally equivalent performance faults inside planPurchaseFinalization. It binds exact current evidence and predeclares six cold runs, but it contains no new build, emulator or performance result. Controlled variants are calibration inputs, never Agent runs, unseen cases or gold repairs. Emulator CPU/PSS remain relative proxies; live vendor IAP, Cordova runtime, real-device and absolute power/thermal authority remain unqualified.",
        "nextGate": "build-and-run-reference-baseline-and-meaningful-wrong-case-bound-matrix-on-linux-emulator"
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
    Ok((
        root.ok_or_else(|| "missing --qualification-root".to_owned())?,
        output.ok_or_else(|| "missing --output".to_owned())?,
    ))
}

fn run() -> Result<(), String> {
    let (root, output) = parse_args()?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = build(root)?;
    let mut bytes = serde_json::to_vec_pretty(&value)
        .map_err(|error| format!("cannot serialize case performance plan: {error}"))?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write case performance plan: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data case performance plan invalid: {error}");
        std::process::exit(1);
    }
}
