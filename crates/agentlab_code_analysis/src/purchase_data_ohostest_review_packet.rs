use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const QUALIFICATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_candidate_qualification.v1";
const OBSERVATION_SCHEMA: &str = "agentlab.purchase_data_ohostest_candidate_observation.v1";
const RECEIPT_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const REPORT_SCHEMA: &str = "agentlab.harmony_hypium_native_report.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_packet.v1";

const CHANGED_FILES: &[&str] = &[
    "entry/src/main/ets/common/PurchaseFinalizationPolicy.ets",
    "entry/src/main/ets/pages/ConsumablesPage.ets",
    "entry/src/ohosTest/ets/test/Ability.test.ets",
    "entry/src/ohosTest/ets/test/List.test.ets",
    "entry/src/ohosTest/ets/test/PurchaseFinalizationPolicy.test.ets",
    "entry/src/ohosTest/module.json5",
];

const RISK_IDS: &[&str] = &[
    "self-authored-candidate",
    "signature-verification-outside-test-seam",
    "live-vendor-iap-service-unexecuted",
    "x86-emulator-not-real-device",
    "performance-power-thermal-uncalibrated",
    "semantic-and-behavior-oracle-review-pending",
];

const QUESTIONS: &[(&str, &str)] = &[
    (
        "exact-lineage",
        "Does the exact patch represent the recorded base-to-candidate transition and match every retained digest?",
    ),
    (
        "production-seam-preservation",
        "Does extracting PurchaseFinalizationPolicy preserve intended purchase finalization behavior without introducing a new production defect?",
    ),
    (
        "guard-and-field-correctness",
        "Are finish guards, productType conversion, token and order identifiers correct for the source API contract?",
    ),
    (
        "ohostest-discrimination",
        "Do the seven OHOS Test cases distinguish meaningful wrong implementations rather than only replay the extracted implementation?",
    ),
    (
        "failure-observability",
        "Do decode and finish failures remain observable enough for a verifiable AgentLab case contract?",
    ),
    (
        "boundary-honesty",
        "Does the candidate remain review-only until semantic, behavior-Oracle, live-runtime and performance gates are independently satisfied?",
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

fn require_hex(value: &str, length: usize, label: &str) -> Result<(), String> {
    if !valid_lower_hex(value, length) {
        return Err(format!("{label} is not lowercase hexadecimal"));
    }
    Ok(())
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

fn load_patch(path: PathBuf) -> Result<(Vec<u8>, String), String> {
    let metadata = fs::symlink_metadata(&path)
        .map_err(|error| format!("cannot inspect candidate patch: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err("candidate patch must be a regular file".into());
    }
    let bytes = fs::read(path).map_err(|error| format!("cannot read candidate patch: {error}"))?;
    let text = String::from_utf8(bytes.clone())
        .map_err(|error| format!("candidate patch is not UTF-8: {error}"))?;
    Ok((bytes, text))
}

fn validate(
    qualification: &Input,
    observation: &Input,
    receipt: &Input,
    report: &Input,
    patch_bytes: &[u8],
    patch_text: &str,
) -> Result<Value, String> {
    same(
        string(&qualification.value, "schema", "candidate qualification")?,
        QUALIFICATION_SCHEMA,
        "candidate qualification schema",
    )?;
    same(
        string(&qualification.value, "status", "candidate qualification")?,
        "candidate-revision-emulator-qualified-independent-review-pending",
        "candidate qualification status",
    )?;
    for key in [
        "publishedToUpstream",
        "independentReviewVerified",
        "behaviorOracleVerified",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(&qualification.value, key, false, "candidate qualification")?;
    }

    same(
        string(&observation.value, "schema", "candidate observation")?,
        OBSERVATION_SCHEMA,
        "candidate observation schema",
    )?;
    same(
        string(&receipt.value, "schema", "execution receipt")?,
        RECEIPT_SCHEMA,
        "execution receipt schema",
    )?;
    same(
        string(&report.value, "schema", "native report")?,
        REPORT_SCHEMA,
        "native report schema",
    )?;

    let base_revision = string(&qualification.value, "baseRevision", "qualification")?;
    let candidate_revision = string(&qualification.value, "candidateRevision", "qualification")?;
    require_hex(base_revision, 40, "base revision")?;
    require_hex(candidate_revision, 40, "candidate revision")?;
    same(
        string(&observation.value, "baseRevision", "observation")?,
        base_revision,
        "observed base revision",
    )?;
    same(
        string(&observation.value, "candidateRevision", "observation")?,
        candidate_revision,
        "observed candidate revision",
    )?;
    same(
        string(
            &observation.value["executionBinding"],
            "sourceRevision",
            "execution binding",
        )?,
        candidate_revision,
        "execution source revision",
    )?;

    let patch_sha = digest(patch_bytes);
    same(
        string(
            &qualification.value,
            "candidatePatchSha256",
            "qualification",
        )?,
        &patch_sha,
        "candidate patch digest",
    )?;
    same(
        string(&observation.value, "candidatePatchSha256", "observation")?,
        &patch_sha,
        "observed patch digest",
    )?;
    let first_line = patch_text.lines().next().unwrap_or_default();
    same(
        first_line,
        &format!("From {candidate_revision} Mon Sep 17 00:00:00 2001"),
        "format-patch candidate revision",
    )?;
    if !patch_text
        .lines()
        .any(|line| line == "From: AgentLab Evidence <agentlab-evidence@localhost>")
    {
        return Err("format-patch candidate author differs".into());
    }

    let changed_files: Vec<&str> = patch_text
        .lines()
        .filter_map(|line| line.strip_prefix("diff --git a/"))
        .map(|line| line.split(" b/").next().unwrap_or_default())
        .collect();
    if changed_files != CHANGED_FILES {
        return Err("candidate patch changed-file inventory differs".into());
    }
    if !patch_text.contains("6 files changed, 206 insertions(+), 20 deletions(-)") {
        return Err("candidate patch diffstat differs".into());
    }

    let test_names = qualification.value["testNames"]
        .as_array()
        .ok_or_else(|| "qualification testNames must be an array".to_owned())?;
    if test_names.len() != 7 {
        return Err("qualification test inventory differs".into());
    }
    for name in test_names {
        let name = name
            .as_str()
            .ok_or_else(|| "qualification testNames must contain strings".to_owned())?;
        if !patch_text.contains(&format!("it('{name}'")) {
            return Err(format!("candidate patch omits OHOS Test {name}"));
        }
    }

    for (name, input) in [
        ("executionReceiptSha256", receipt),
        ("nativeReportSha256", report),
        ("observationSha256", observation),
    ] {
        same(
            string(
                &qualification.value["lineage"],
                name,
                "qualification lineage",
            )?,
            &input.sha256(),
            name,
        )?;
    }
    exact_bool(&receipt.value, "passed", true, "execution receipt")?;
    exact_bool(&report.value, "passed", true, "native report")?;
    if report.value["counts"]["total"].as_u64() != Some(7)
        || report.value["counts"]["pass"].as_u64() != Some(7)
        || report.value["counts"]["failure"].as_u64() != Some(0)
        || report.value["counts"]["error"].as_u64() != Some(0)
        || report.value["counts"]["ignore"].as_u64() != Some(0)
    {
        return Err("native report counts differ".into());
    }
    exact_strings(
        &observation.value["review"]["addedBoundaryTests"],
        &["missingJwsDoesNotFinish", "decodeFailureDoesNotFinish"],
        "added boundary tests",
    )?;

    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "candidateId": format!("purchase-data-finalization-{}", &candidate_revision[..12]),
        "status": "independent-source-review-required",
        "sourceRepository": qualification.value["sourceRepository"],
        "baseRevision": base_revision,
        "candidateRevision": candidate_revision,
        "candidateAuthor": {
            "name": "AgentLab Evidence",
            "email": "agentlab-evidence@localhost",
            "authority": "exact-format-patch-header"
        },
        "projectTreeSha256": qualification.value["projectTreeSha256"],
        "artifacts": {
            "patch": {
                "path": "release/qualifications/alpha13-payment-feedback-analysis-165bcbd/purchase-data-ohostest-candidate.patch",
                "sha256": patch_sha,
                "byteLength": patch_bytes.len()
            },
            "qualificationSha256": qualification.sha256(),
            "observationSha256": observation.sha256(),
            "executionReceiptSha256": receipt.sha256(),
            "nativeReportSha256": report.sha256()
        },
        "change": {
            "fileCount": CHANGED_FILES.len(),
            "insertions": 206,
            "deletions": 20,
            "paths": CHANGED_FILES,
            "productionSourceFileCount": 2,
            "ohosTestFileCount": 4
        },
        "execution": {
            "framework": receipt.value["framework"],
            "testCount": 7,
            "passed": 7,
            "failure": 0,
            "error": 0,
            "ignore": 0,
            "linuxX86EmulatorExecuted": true,
            "emulatorStopped": true,
            "worktreeCleanBeforeBuild": observation.value["executionBinding"]["worktreeCleanBeforeBuild"],
            "worktreeCleanAfterExecution": observation.value["executionBinding"]["worktreeCleanAfterExecution"]
        },
        "testNames": qualification.value["testNames"],
        "reviewDecisionContract": {
            "reviewerIdentityAuthority": "authenticated-github-actor-on-trusted-main",
            "answers": ["yes", "no", "unknown"],
            "verdicts": [
                "approve-for-upstream-publication",
                "reject-candidate",
                "defer-for-more-evidence"
            ],
            "approvalRequiresEveryAnswerYes": true,
            "reviewerMustAcknowledgeEveryRisk": true,
            "reviewerMustDifferFromCandidateAuthor": true,
            "questions": QUESTIONS.iter().map(|(id, question)| json!({
                "id": id,
                "question": question
            })).collect::<Vec<_>>()
        },
        "risks": RISK_IDS,
        "publishedToUpstream": false,
        "independentReviewVerified": false,
        "behaviorOracleVerified": false,
        "performanceCalibrated": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This packet makes the exact candidate patch and clean emulator evidence reviewable. It does not itself approve the patch, publish upstream source, prove live vendor-IAP behavior, establish semantic alignment, calibrate performance/power/thermal behavior, or authorize case promotion.",
        "nextGate": "authenticated-independent-source-review-on-trusted-main"
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
    let qualification = Input::load(get("--qualification")?, "candidate qualification")?;
    let observation = Input::load(get("--observation")?, "candidate observation")?;
    let receipt = Input::load(get("--execution-receipt")?, "execution receipt")?;
    let report = Input::load(get("--native-report")?, "native report")?;
    let (patch_bytes, patch_text) = load_patch(get("--patch")?)?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let packet = validate(
        &qualification,
        &observation,
        &receipt,
        &report,
        &patch_bytes,
        &patch_text,
    )?;
    let mut bytes = serde_json::to_vec_pretty(&packet).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test review packet invalid: {error}");
        std::process::exit(1);
    }
}
