use agentlab_code_analysis::digest;
use serde_json::{json, Map, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const PACKET_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_packet.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_mutation_plan.v1";
const SOURCE_PATH: &str = "entry/src/main/ets/common/PurchaseFinalizationPolicy.ets";

const TEST_NAMES: &[&str] = &[
    "missingJwsDoesNotFinish",
    "malformedDataDoesNotFinish",
    "decodeFailureDoesNotFinish",
    "alreadyFinishedPurchaseDoesNotFinishAgain",
    "pendingPurchaseForwardsExactFinishFields",
    "missingProductTypeBlocksFinish",
    "finishRejectionRemainsObservable",
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

fn extract_new_file(patch: &str, path: &str) -> Result<String, String> {
    let marker = format!("diff --git a/{path} b/{path}");
    let section = patch
        .split_once(&marker)
        .map(|(_, tail)| tail)
        .ok_or_else(|| format!("candidate patch omits {path}"))?;
    let section = section.split("\ndiff --git ").next().unwrap_or(section);
    let hunk = section
        .split_once("@@ -0,0 +1,68 @@\n")
        .map(|(_, tail)| tail)
        .ok_or_else(|| format!("candidate patch new-file hunk differs: {path}"))?;
    let mut lines = Vec::new();
    for line in hunk.lines() {
        let added = line
            .strip_prefix('+')
            .ok_or_else(|| format!("candidate patch source hunk is not add-only: {path}"))?;
        lines.push(added);
    }
    if lines.len() != 68 {
        return Err(format!("candidate patch source line count differs: {path}"));
    }
    Ok(lines.join("\n") + "\n")
}

fn mutation(
    id: &str,
    kind: &str,
    semantic_fault: &str,
    find: &str,
    replace: &str,
    expected_killed_tests: &[&str],
) -> Value {
    json!({
        "id": id,
        "role": "meaningful-wrong",
        "mutationKind": kind,
        "semanticFault": semantic_fault,
        "edit": {
            "path": SOURCE_PATH,
            "find": find,
            "replace": replace,
            "expectedOccurrenceCount": 1
        },
        "expectedKilledTests": expected_killed_tests,
        "expectedSurvivingTests": TEST_NAMES
            .iter()
            .copied()
            .filter(|name| !expected_killed_tests.contains(name))
            .collect::<Vec<_>>()
    })
}

fn build_plan(packet: &Input, patch_bytes: &[u8], patch_text: &str) -> Result<Value, String> {
    same(
        string(&packet.value, "schema", "review packet")?,
        PACKET_SCHEMA,
        "review packet schema",
    )?;
    same(
        string(&packet.value, "status", "review packet")?,
        "independent-source-review-required",
        "review packet status",
    )?;
    for key in [
        "publishedToUpstream",
        "independentReviewVerified",
        "behaviorOracleVerified",
        "performanceCalibrated",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(&packet.value, key, false, "review packet")?;
    }
    exact_strings(
        &packet.value["testNames"],
        TEST_NAMES,
        "OHOS Test inventory",
    )?;
    same(
        string(
            &packet.value["artifacts"]["patch"],
            "sha256",
            "candidate patch",
        )?,
        &digest(patch_bytes),
        "candidate patch digest",
    )?;
    if packet.value["artifacts"]["patch"]["byteLength"].as_u64() != Some(patch_bytes.len() as u64) {
        return Err("candidate patch byte length differs".into());
    }
    let source = extract_new_file(patch_text, SOURCE_PATH)?;
    let variants = vec![
        mutation(
            "unsafe-default-finish",
            "unsafe-default",
            "A newly created plan starts authorized to finish, so early-return and exception paths fail open.",
            "shouldFinish: boolean = false;",
            "shouldFinish: boolean = true;",
            &[
                "missingJwsDoesNotFinish",
                "malformedDataDoesNotFinish",
                "decodeFailureDoesNotFinish",
                "alreadyFinishedPurchaseDoesNotFinishAgain",
                "missingProductTypeBlocksFinish",
            ],
        ),
        mutation(
            "drop-already-finished-guard",
            "guard-removal",
            "An already finished purchase is scheduled for finish a second time.",
            "if (purchaseOrderPayload.finishStatus === FinishStatus.FINISHED) {",
            "if (false) {",
            &["alreadyFinishedPurchaseDoesNotFinishAgain"],
        ),
        mutation(
            "drop-product-type-guard",
            "guard-removal",
            "A purchase without a product type is sent to the finish API.",
            "if (!purchaseOrderPayload.productType) {",
            "if (false) {",
            &["missingProductTypeBlocksFinish"],
        ),
        mutation(
            "erase-purchase-token",
            "request-data-corruption",
            "The finish request loses the exact purchase token selected from the decoded order.",
            "purchaseToken: purchaseOrderPayload.purchaseToken,",
            "purchaseToken: '',",
            &["pendingPurchaseForwardsExactFinishFields"],
        ),
        mutation(
            "swallow-finish-rejection",
            "error-swallowing",
            "A rejected finish API call is converted into a resolved promise and becomes unobservable.",
            "return finishPurchase(plan.request);",
            "return finishPurchase(plan.request).catch((): Promise<void> => Promise.resolve());",
            &["finishRejectionRemainsObservable"],
        ),
        mutation(
            "finish-on-parse-or-decode-error",
            "exception-fail-open",
            "Malformed purchase data or a decode failure schedules a finish request instead of failing closed.",
            "plan.reason = 'invalid-purchase-data';\n    return plan;",
            "plan.shouldFinish = true;\n    plan.reason = 'finish-required';\n    return plan;",
            &["malformedDataDoesNotFinish", "decodeFailureDoesNotFinish"],
        ),
    ];
    for variant in &variants {
        let find = string(&variant["edit"], "find", "mutation edit")?;
        if source.matches(find).count() != 1 {
            return Err(format!(
                "mutation anchor occurrence differs: {}",
                variant["id"]
            ));
        }
    }
    let mut test_to_variants = Map::new();
    for test in TEST_NAMES {
        let ids = variants
            .iter()
            .filter(|variant| {
                variant["expectedKilledTests"]
                    .as_array()
                    .is_some_and(|tests| tests.iter().any(|value| value == test))
            })
            .map(|variant| variant["id"].clone())
            .collect::<Vec<_>>();
        if ids.is_empty() {
            return Err(format!("no meaningful mutation targets OHOS Test {test}"));
        }
        test_to_variants.insert((*test).to_owned(), Value::Array(ids));
    }
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "mutation-calibration-planned-not-executed",
        "candidateId": packet.value["candidateId"],
        "sourceRepository": packet.value["sourceRepository"],
        "baseRevision": packet.value["baseRevision"],
        "candidateRevision": packet.value["candidateRevision"],
        "reviewPacketSha256": packet.sha256(),
        "candidatePatchSha256": digest(patch_bytes),
        "source": {
            "path": SOURCE_PATH,
            "sha256": digest(source.as_bytes()),
            "byteLength": source.len(),
            "lineCount": 68
        },
        "testNames": TEST_NAMES,
        "variants": variants,
        "coverage": {
            "variantCount": 6,
            "meaningfulWrongVariantCount": 6,
            "testCount": 7,
            "everyTestTargeted": true,
            "testToExpectedKillingVariants": test_to_variants
        },
        "execution": {
            "sourceVariantsBuilt": false,
            "ohosTestHapsBuilt": false,
            "linuxX86EmulatorExecuted": false,
            "observedKilledVariantCount": 0,
            "mutationScore": null,
            "expectedMatrixVerified": false
        },
        "independentReviewVerified": false,
        "behaviorOracleVerified": false,
        "performanceCalibrated": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "This is a source-bound mutation calibration plan. Expected killed tests are hypotheses until every variant is built and executed through the standard OHOS Test lane on the Linux emulator. Planning alone is not discrimination evidence and cannot approve source publication or case promotion.",
        "nextGate": "build-and-execute-all-meaningful-wrong-variants-on-linux-emulator"
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
    let packet = Input::load(get("--review-packet")?, "review packet")?;
    let (patch_bytes, patch_text) = load_patch(get("--candidate-patch")?)?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let plan = build_plan(&packet, &patch_bytes, &patch_text)?;
    let mut bytes = serde_json::to_vec_pretty(&plan).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test mutation plan invalid: {error}");
        std::process::exit(1);
    }
}
