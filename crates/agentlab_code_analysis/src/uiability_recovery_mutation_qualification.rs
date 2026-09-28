use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::PathBuf,
};

const PLAN_SCHEMA: &str = "agentlab.uiability_recovery_oracle_plan.v1";
const RECEIPT_SCHEMA: &str = "agentlab.uiability_recovery_runtime_receipt.v1";
const CALIBRATION_SCHEMA: &str = "agentlab.uiability_recovery_mutation_calibration.v1";
const OUTPUT_SCHEMA: &str = "agentlab.uiability_recovery_mutation_qualification.v1";
const EXPECTED_TEXT: &str = "Recovered Twice";
const NORMAL: &str = "NORMAL";
const RECOVERY: &str = "APP_RECOVERY";
const ENTRY_PATH: &str =
    "Ability/UIAbilityRecover/entry/src/main/ets/entryability/EntryAbility.ets";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: PathBuf, label: &str) -> Result<Self, String> {
        let meta =
            fs::symlink_metadata(&path).map_err(|e| format!("cannot inspect {label}: {e}"))?;
        if !meta.file_type().is_file() || meta.file_type().is_symlink() {
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

fn text<'a>(v: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
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
fn valid_sha(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
fn require_sha(v: &Value, key: &str, label: &str) -> Result<(), String> {
    if !valid_sha(text(v, key, label)?) {
        return Err(format!("{label} {key} is not a SHA-256"));
    }
    Ok(())
}
fn tuple(v: &Value, expected_text: &str, reason: &str, label: &str) -> Result<(), String> {
    same(
        text(v, "visibleText", label)?,
        expected_text,
        &format!("{label} visibleText"),
    )?;
    same(
        text(v, "launchReason", label)?,
        reason,
        &format!("{label} launchReason"),
    )
}
fn direct(run: &Value, label: &str, peer: &str) -> Result<(), String> {
    same(
        text(run, "routeDecision", label)?,
        "peer_direct",
        &format!("{label} route"),
    )?;
    same(
        text(run, "targetPeerId", label)?,
        peer,
        &format!("{label} peer"),
    )?;
    require_sha(run, "applicationHapSha256", label)?;
    require_sha(run, "beforeLayoutSha256", label)?;
    require_sha(run, "afterLayoutSha256", label)?;
    require_sha(run, "appScopeSha256", label)?;
    if !text(run, "bundleName", label)?.starts_with("com.samples.myapplication.") {
        return Err(format!("{label} bundleName differs"));
    }
    text(run, "operationId", label)?;
    tuple(
        &run["before"],
        EXPECTED_TEXT,
        NORMAL,
        &format!("{label} before"),
    )
}

fn validate(plan: &Input, receipt: &Input, calibration: &Input) -> Result<Value, String> {
    same(
        text(&plan.value, "schema", "plan")?,
        PLAN_SCHEMA,
        "plan schema",
    )?;
    same(
        text(&receipt.value, "schema", "reference receipt")?,
        RECEIPT_SCHEMA,
        "reference receipt schema",
    )?;
    same(
        text(&calibration.value, "schema", "calibration")?,
        CALIBRATION_SCHEMA,
        "calibration schema",
    )?;
    same(
        text(&calibration.value, "status", "calibration")?,
        "passed",
        "calibration status",
    )?;
    boolean(&plan.value, "allowsCaseContract", false, "plan")?;
    boolean(&plan.value, "automaticPromotion", false, "plan")?;
    boolean(
        &receipt.value,
        "automaticPromotion",
        false,
        "reference receipt",
    )?;
    for key in [
        "sameOracleApplied",
        "referenceSandwichVerified",
        "identityIsolationVerified",
        "abnormalStopRecoveryCycle",
        "independentOracleExecuted",
    ] {
        boolean(&calibration.value, key, true, "calibration")?;
    }
    for key in [
        "normalExitNegativeControl",
        "exactApi22Runtime",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        boolean(&calibration.value, key, false, "calibration")?;
    }
    same(
        text(&calibration.value, "planSha256", "calibration")?,
        &plan.sha256(),
        "calibration plan digest",
    )?;
    same(
        text(
            &calibration.value,
            "referenceRuntimeReceiptSha256",
            "calibration",
        )?,
        &receipt.sha256(),
        "calibration receipt digest",
    )?;
    same(
        text(&receipt.value, "planSha256", "reference receipt")?,
        &plan.sha256(),
        "reference receipt plan digest",
    )?;
    for key in ["repositoryId", "revision", "treeOid"] {
        same(
            text(&calibration.value["source"], key, "calibration source")?,
            text(&plan.value["source"], key, "plan source")?,
            &format!("source {key}"),
        )?;
        same(
            text(&receipt.value["source"], key, "receipt source")?,
            text(&plan.value["source"], key, "plan source")?,
            &format!("receipt source {key}"),
        )?;
    }
    for key in ["host", "emulator", "runtime", "architecture"] {
        same(
            text(
                &calibration.value["environment"],
                key,
                "calibration environment",
            )?,
            text(&receipt.value["environment"], key, "receipt environment")?,
            &format!("environment {key}"),
        )?;
    }
    if calibration.value["environment"]["buildTargetApi"]
        != receipt.value["environment"]["buildTargetApi"]
    {
        return Err("environment buildTargetApi differs".into());
    }

    let selected: BTreeSet<&str> = plan.value["wrongVariants"]
        .as_array()
        .ok_or("plan wrongVariants must be an array")?
        .iter()
        .filter_map(|v| v["id"].as_str())
        .filter(|id| *id == "hardcoded-recovered-value" || *id == "restore-wiring-disabled")
        .collect();
    if selected != BTreeSet::from(["hardcoded-recovered-value", "restore-wiring-disabled"]) {
        return Err("plan does not contain both selected variants".into());
    }
    let peer = text(&calibration.value["execution"], "targetPeerId", "execution")?;
    same(
        text(
            &calibration.value["execution"],
            "routeDecision",
            "execution",
        )?,
        "peer_direct",
        "execution route",
    )?;
    same(
        text(
            &calibration.value["execution"],
            "oracleAuthority",
            "execution",
        )?,
        "host-supervisor-layout-dump",
        "Oracle authority",
    )?;
    same(
        text(&calibration.value["execution"], "trigger", "execution")?,
        "click-AgentLabRecoveryTrigger-appRecovery-saveAppState-restartApp",
        "execution trigger",
    )?;

    let refs = calibration.value["referenceControls"]
        .as_array()
        .ok_or("referenceControls must be an array")?;
    if refs.len() != 2 {
        return Err("reference control count differs".into());
    }
    let mut phases = BTreeSet::new();
    let mut bundles = BTreeSet::new();
    let mut haps = BTreeSet::new();
    for run in refs {
        let label = format!("reference {}", text(run, "phase", "reference")?);
        phases.insert(text(run, "phase", &label)?.to_owned());
        boolean(run, "built", true, &label)?;
        boolean(run, "executed", true, &label)?;
        boolean(run, "oraclePassed", true, &label)?;
        direct(run, &label, peer)?;
        tuple(
            &run["after"],
            EXPECTED_TEXT,
            RECOVERY,
            &format!("{label} after"),
        )?;
        bundles.insert(text(run, "bundleName", &label)?.to_owned());
        haps.insert(text(run, "applicationHapSha256", &label)?.to_owned());
    }
    if phases != BTreeSet::from(["post".into(), "pre".into()]) {
        return Err("reference phases differ".into());
    }

    let variants = calibration.value["variants"]
        .as_array()
        .ok_or("variants must be an array")?;
    if variants.len() != 2 {
        return Err("variant count differs".into());
    }
    let mut ids = BTreeSet::new();
    for run in variants {
        let id = text(run, "id", "variant")?;
        ids.insert(id.to_owned());
        for key in ["built", "executed", "oracleKilled"] {
            boolean(run, key, true, &format!("variant {id}"))?;
        }
        direct(run, &format!("variant {id}"), peer)?;
        require_sha(
            &run["sourceMutation"],
            "mutatedFileSha256",
            &format!("variant {id} mutation"),
        )?;
        require_sha(
            &run["sourceMutation"],
            "normalizedPatchSha256",
            &format!("variant {id} mutation"),
        )?;
        same(
            text(
                &run["sourceMutation"],
                "path",
                &format!("variant {id} mutation"),
            )?,
            ENTRY_PATH,
            &format!("variant {id} mutation path"),
        )?;
        if run["sourceMutation"]["normalizedPatchByteLength"]
            .as_u64()
            .unwrap_or(0)
            == 0
        {
            return Err(format!("variant {id} mutation patch is empty"));
        }
        let killed: BTreeSet<&str> = run["failedAssertions"]
            .as_array()
            .ok_or_else(|| format!("variant {id} failedAssertions must be an array"))?
            .iter()
            .filter_map(Value::as_str)
            .collect();
        if killed != BTreeSet::from(["recovery-assertion"]) {
            return Err(format!("variant {id} failed assertion differs"));
        }
        let after = &run["after"];
        if tuple(
            after,
            EXPECTED_TEXT,
            RECOVERY,
            &format!("variant {id} after"),
        )
        .is_ok()
        {
            return Err(format!("variant {id} was not killed"));
        }
        match id {
            "hardcoded-recovered-value" => {
                same(
                    text(
                        &run["sourceMutation"],
                        "mutatedFileSha256",
                        "hardcoded mutation",
                    )?,
                    "2b129bc9dbab6f96d8df491bca92c319a7a2c7405afe5d90729b644d590b62af",
                    "hardcoded mutated file digest",
                )?;
                same(
                    text(
                        &run["sourceMutation"],
                        "normalizedPatchSha256",
                        "hardcoded mutation",
                    )?,
                    "df98ea528360b403cc2cbda7b6979318fc5d7ef89c1c6472cf1a254e95c38200",
                    "hardcoded normalized patch digest",
                )?;
                if run["sourceMutation"]["normalizedPatchByteLength"].as_u64() != Some(467) {
                    return Err("hardcoded normalized patch length differs".into());
                }
                tuple(after, "Welcome", RECOVERY, "hardcoded variant after")?
            }
            "restore-wiring-disabled" => {
                same(
                    text(
                        &run["sourceMutation"],
                        "mutatedFileSha256",
                        "wiring mutation",
                    )?,
                    "154a5038cdc6b4270744e738dc44c5b428e5338e6be4ec91c19ff4e547e56027",
                    "wiring mutated file digest",
                )?;
                same(
                    text(
                        &run["sourceMutation"],
                        "normalizedPatchSha256",
                        "wiring mutation",
                    )?,
                    "468321a435f9921c9caa84df0bb3cfd0f7f83f43415e64dd2dd5085e303823e0",
                    "wiring normalized patch digest",
                )?;
                if run["sourceMutation"]["normalizedPatchByteLength"].as_u64() != Some(349) {
                    return Err("wiring normalized patch length differs".into());
                }
                tuple(after, EXPECTED_TEXT, NORMAL, "wiring variant after")?
            }
            _ => return Err(format!("unexpected variant {id}")),
        }
        bundles.insert(text(run, "bundleName", &format!("variant {id}"))?.to_owned());
        haps.insert(text(run, "applicationHapSha256", &format!("variant {id}"))?.to_owned());
    }
    if ids
        != BTreeSet::from([
            "hardcoded-recovered-value".into(),
            "restore-wiring-disabled".into(),
        ])
    {
        return Err("variant inventory differs".into());
    }
    if bundles.len() != 4 {
        return Err("execution bundle identities are not isolated".into());
    }
    if haps.len() != 4 {
        return Err("application artifact identities are not unique".into());
    }
    if calibration.value["variantCount"].as_u64() != Some(2)
        || calibration.value["killedVariantCount"].as_u64() != Some(2)
        || calibration.value["mutationScore"].as_f64() != Some(1.0)
    {
        return Err("mutation summary differs".into());
    }
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "mutation-discrimination-qualified-normal-exit-negative-control-required",
        "candidateId": plan.value["candidate"]["id"],
        "source": plan.value["source"],
        "planSha256": plan.sha256(),
        "referenceRuntimeReceiptSha256": receipt.sha256(),
        "mutationCalibrationSha256": calibration.sha256(),
        "variantCount": 2,
        "killedVariantCount": 2,
        "mutationScore": 1.0,
        "referenceSandwichVerified": true,
        "identityIsolationVerified": true,
        "abnormalStopRecoveryCycle": true,
        "independentOracleExecuted": true,
        "normalExitNegativeControl": false,
        "exactApi22Runtime": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": "Two source-bound meaningful-wrong variants were built and killed by the same external layout Oracle between isolated pre/post reference controls on one HarmonyOS 7 API 26 x86_64 emulator. This qualifies abnormal recovery discrimination only; it does not qualify normal-exit behavior, exact API 22 runtime, real-device behavior, performance, power, thermal or the case contract.",
        "nextGate": "normal-exit-negative-control-on-independent-bundle-identity"
    }))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut values = BTreeMap::new();
    while let Some(flag) = args.next() {
        values.insert(
            flag.clone(),
            PathBuf::from(
                args.next()
                    .ok_or_else(|| format!("missing value for {flag}"))?,
            ),
        );
    }
    let get = |key: &str| {
        values
            .get(key)
            .cloned()
            .ok_or_else(|| format!("missing {key}"))
    };
    let plan = Input::load(get("--oracle-plan")?, "oracle plan")?;
    let receipt = Input::load(
        get("--reference-runtime-receipt")?,
        "reference runtime receipt",
    )?;
    let calibration = Input::load(get("--mutation-calibration")?, "mutation calibration")?;
    let output = get("--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = validate(&plan, &receipt, &calibration)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|e| format!("cannot write output: {e}"))
}

fn main() {
    if let Err(e) = run() {
        eprintln!("UIAbility recovery mutation qualification invalid: {e}");
        std::process::exit(1);
    }
}
