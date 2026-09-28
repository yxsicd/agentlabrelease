use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{env, fs, path::PathBuf, process::Command};

const CANDIDATE_ID: &str = "shadow-case-uiability-backup-restore-state-recovery";
const ENTRY: &str = "Ability/UIAbilityRecover/entry/src/main/ets/entryability/EntryAbility.ets";
const PAGE: &str = "Ability/UIAbilityRecover/entry/src/main/ets/pages/Index.ets";
const TEST: &str = "Ability/UIAbilityRecover/entry/src/ohosTest/ets/test/Ability.test.ets";

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

fn required_string<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
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

fn git(root: &PathBuf, args: &[&str]) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| format!("cannot execute git: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "git command failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(output.stdout)
}

fn canonical_sha(value: &Value) -> Result<String, String> {
    serde_json::to_vec(value)
        .map(|bytes| digest(&bytes))
        .map_err(|error| format!("cannot canonicalize JSON: {error}"))
}

fn exact_anchor(source: &str, anchor: &str, label: &str) -> Result<(), String> {
    if source.matches(anchor).count() != 1 {
        return Err(format!("{label} anchor occurrence differs"));
    }
    Ok(())
}

fn binding(root: &PathBuf, revision: &str, path: &str) -> Result<Value, String> {
    let object = String::from_utf8(git(root, &["rev-parse", &format!("{revision}:{path}")])?)
        .map_err(|error| format!("blob oid is not UTF-8: {error}"))?;
    let bytes = git(root, &["show", &format!("{revision}:{path}")])?;
    Ok(json!({
        "path": path,
        "gitBlobOid": object.trim(),
        "sha256": digest(&bytes),
        "byteLength": bytes.len()
    }))
}

fn listed_paths<'a>(value: &'a Value, field: &str) -> Result<Vec<&'a str>, String> {
    value[field]
        .as_array()
        .ok_or_else(|| format!("{field} must be an array"))?
        .iter()
        .map(|row| {
            row["path"]
                .as_str()
                .filter(|path| !path.is_empty())
                .ok_or_else(|| format!("{field} contains an invalid path"))
        })
        .collect()
}

fn load_patch(path: PathBuf) -> Result<Vec<u8>, String> {
    let metadata = fs::symlink_metadata(&path)
        .map_err(|error| format!("cannot inspect reference patch: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err("reference patch must be a regular file".into());
    }
    fs::read(path).map_err(|error| format!("cannot read reference patch: {error}"))
}

fn validate_patch(bytes: &[u8]) -> Result<(), String> {
    let text = std::str::from_utf8(bytes)
        .map_err(|error| format!("reference patch is not UTF-8: {error}"))?;
    let expected = [ENTRY, PAGE, TEST];
    let headers: Vec<&str> = text
        .lines()
        .filter(|line| line.starts_with("diff --git "))
        .collect();
    if headers.len() != expected.len() {
        return Err("reference patch file count differs".into());
    }
    for path in expected {
        let marker = format!("diff --git a/{path} b/{path}");
        if headers.iter().filter(|line| **line == marker).count() != 1 {
            return Err(format!("reference patch path differs: {path}"));
        }
    }
    Ok(())
}

fn build(
    candidate: &Input,
    plan: &Input,
    source: PathBuf,
    reference_patch: &[u8],
) -> Result<Value, String> {
    same(
        required_string(&candidate.value, "schema", "candidate")?,
        "agentlab.shadow_case_candidate.v1",
        "candidate schema",
    )?;
    same(
        required_string(&candidate.value, "id", "candidate")?,
        CANDIDATE_ID,
        "candidate id",
    )?;
    same(
        required_string(&candidate.value, "status", "candidate")?,
        "shadow-proposal",
        "candidate status",
    )?;
    if candidate.value["automaticPromotion"].as_bool() != Some(false) {
        return Err("candidate automaticPromotion differs".into());
    }
    same(
        required_string(&plan.value, "schema", "construction plan")?,
        "agentlab.shadow_case_construction_plan.v1",
        "construction plan schema",
    )?;
    same(
        required_string(&plan.value, "candidateId", "construction plan")?,
        CANDIDATE_ID,
        "construction plan candidate",
    )?;
    if plan.value["automaticPromotion"].as_bool() != Some(false) {
        return Err("construction plan automaticPromotion differs".into());
    }
    same(
        required_string(&plan.value, "candidateSha256", "construction plan")?,
        &canonical_sha(&candidate.value)?,
        "construction plan candidate digest",
    )?;

    let revision = required_string(&candidate.value, "sourceRevision", "candidate")?;
    let head = String::from_utf8(git(&source, &["rev-parse", "HEAD"])?)
        .map_err(|error| format!("source HEAD is not UTF-8: {error}"))?;
    same(head.trim(), revision, "source checkout revision")?;
    let status = git(&source, &["status", "--porcelain"])?;
    if !status.is_empty() {
        return Err("source checkout is dirty".into());
    }

    let implementation = listed_paths(&plan.value, "requiredImplementationPaths")?;
    let oracle = listed_paths(&plan.value, "requiredOraclePaths")?;
    for path in [ENTRY, PAGE] {
        if !implementation.contains(&path) {
            return Err(format!(
                "construction plan omits implementation path: {path}"
            ));
        }
    }
    for path in [TEST, PAGE] {
        if !oracle.contains(&path) {
            return Err(format!("construction plan omits Oracle path: {path}"));
        }
    }
    let visible: Vec<&str> = candidate.value["editablePaths"]
        .as_array()
        .into_iter()
        .flatten()
        .chain(
            candidate.value["contextPaths"]
                .as_array()
                .into_iter()
                .flatten(),
        )
        .filter_map(Value::as_str)
        .collect();
    for path in implementation.iter().chain(oracle.iter()) {
        if !visible.contains(path) {
            return Err(format!("candidate does not expose required path: {path}"));
        }
    }

    let entry = String::from_utf8(git(&source, &["show", &format!("{revision}:{ENTRY}")])?)
        .map_err(|error| format!("EntryAbility source is not UTF-8: {error}"))?;
    let page = String::from_utf8(git(&source, &["show", &format!("{revision}:{PAGE}")])?)
        .map_err(|error| format!("Index source is not UTF-8: {error}"))?;
    let test = String::from_utf8(git(&source, &["show", &format!("{revision}:{TEST}")])?)
        .map_err(|error| format!("Ability test source is not UTF-8: {error}"))?;
    exact_anchor(
        &entry,
        "let recoveryMyData = want.parameters['myData'];",
        "restore read",
    )?;
    exact_anchor(&entry, "wantParam['myData'] = 'my1234567';", "save state")?;
    exact_anchor(
        &page,
        "@State message: string = 'Hello World';",
        "page state",
    )?;
    exact_anchor(&page, "this.message = 'Welcome';", "page interaction")?;
    exact_anchor(&test, "it('UIAbility_Recover_01'", "existing OHOS Test")?;
    validate_patch(reference_patch)?;

    let bindings = [ENTRY, PAGE, TEST]
        .iter()
        .map(|path| binding(&source, revision, path))
        .collect::<Result<Vec<_>, _>>()?;
    let tree = String::from_utf8(git(
        &source,
        &["rev-parse", &format!("{revision}^{{tree}}")],
    )?)
    .map_err(|error| format!("source tree oid is not UTF-8: {error}"))?;

    Ok(json!({
        "schema": "agentlab.uiability_recovery_oracle_plan.v1",
        "status": "oracle-and-calibration-planned-trigger-probe-required",
        "candidate": {
            "id": CANDIDATE_ID,
            "sha256": canonical_sha(&candidate.value)?
        },
        "constructionPlan": {
            "sha256": plan.sha256(),
            "candidateSha256": canonical_sha(&candidate.value)?
        },
        "source": {
            "repositoryId": candidate.value["repositoryId"],
            "revision": revision,
            "treeOid": tree.trim(),
            "bindings": bindings
        },
        "oracle": {
            "framework": "instrument-test-ohosTest-hypium",
            "authority": "supervisor-owned-multi-process-orchestration",
            "testSourcePath": TEST,
            "phases": [
                {
                    "id": "fresh-cold-launch",
                    "testFilter": "ActsAbilityTest#AgentLab_Cold_Default",
                    "precondition": "fresh-install-or-cleared-application-state",
                    "expectedVisibleText": "Hello World"
                },
                {
                    "id": "seed-dynamic-state",
                    "testFilter": "ActsAbilityTest#AgentLab_Seed_Dynamic",
                    "action": "click-HelloWorld-twice-and-background",
                    "expectedVisibleText": "Recovered Twice"
                },
                {
                    "id": "abnormal-termination",
                    "owner": "host-supervisor",
                    "selectedTrigger": null,
                    "allowedProbeCandidates": [
                        "background-process-sigkill",
                        "platform-recovery-fault-injection"
                    ],
                    "rejectedShortcut": "kill-the-bundle-from-inside-its-own-ohosTest-process",
                    "status": "exact-image-probe-required"
                },
                {
                    "id": "recovery-assertion",
                    "testFilter": "ActsAbilityTest#AgentLab_Recovery_RestoresLatest",
                    "expectedVisibleText": "Recovered Twice",
                    "requiresLaunchReason": "APP_RECOVERY"
                },
                {
                    "id": "normal-exit-negative-control",
                    "testFilter": "ActsAbilityTest#AgentLab_NormalExit_ColdDefault",
                    "expectedVisibleText": "Hello World",
                    "proves": "recovery-is-not-unconditional-persistence"
                }
            ]
        },
        "referenceContract": {
            "patch": {
                "sha256": digest(reference_patch),
                "byteLength": reference_patch.len(),
                "changedPaths": [ENTRY, PAGE, TEST]
            },
            "stateOwner": "AppStorage-myData-bound-to-Index",
            "restoreOnlyWhen": "launchParam.launchReason == AbilityConstant.LaunchReason.APP_RECOVERY",
            "saveValue": "latest-visible-interaction-state-not-a-constant",
            "requiredSourceAnchors": [
                {"path": ENTRY, "anchor": "let recoveryMyData = want.parameters['myData'];"},
                {"path": ENTRY, "anchor": "wantParam['myData'] = 'my1234567';"},
                {"path": PAGE, "anchor": "@State message: string = 'Hello World';"},
                {"path": PAGE, "anchor": "this.message = 'Welcome';"},
                {"path": TEST, "anchor": "it('UIAbility_Recover_01'"}
            ]
        },
        "wrongVariants": [
            {
                "id": "hardcoded-recovered-value",
                "fault": "restore always substitutes Welcome instead of consuming the latest saved value",
                "expectedKilledBy": ["recovery-assertion"]
            },
            {
                "id": "unconditional-persistent-state",
                "fault": "ordinary persistence restores state after normal exit instead of APP_RECOVERY only",
                "expectedKilledBy": ["normal-exit-negative-control"]
            },
            {
                "id": "restore-wiring-disabled",
                "fault": "setRestoreEnabled or the backup metadata chain is removed",
                "expectedKilledBy": ["recovery-assertion"]
            }
        ],
        "qualification": {
            "api22EmulatorBuildDeploy": false,
            "abnormalStopRecoveryCycle": false,
            "independentOracleExecuted": false,
            "wrongVariantsBuilt": 0,
            "wrongVariantsExecuted": 0,
            "requiredWrongVariants": 2,
            "triggerProbeCompleted": false
        },
        "allowsCaseContract": false,
        "automaticPromotion": false
    }))
}

fn main() -> Result<(), String> {
    let mut args = env::args_os().skip(1);
    let mut candidate = None;
    let mut plan = None;
    let mut source = None;
    let mut reference_patch = None;
    let mut output = None;
    while let Some(flag) = args.next() {
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {}", flag.to_string_lossy()))?;
        match flag.to_str() {
            Some("--candidate") => candidate = Some(PathBuf::from(value)),
            Some("--construction-plan") => plan = Some(PathBuf::from(value)),
            Some("--source") => source = Some(PathBuf::from(value)),
            Some("--reference-patch") => reference_patch = Some(PathBuf::from(value)),
            Some("--output") => output = Some(PathBuf::from(value)),
            _ => return Err(format!("unknown argument: {}", flag.to_string_lossy())),
        }
    }
    let candidate = Input::load(candidate.ok_or("--candidate is required")?, "candidate")?;
    let plan = Input::load(
        plan.ok_or("--construction-plan is required")?,
        "construction plan",
    )?;
    let source = source.ok_or("--source is required")?;
    let reference_patch = load_patch(reference_patch.ok_or("--reference-patch is required")?)?;
    let output = output.ok_or("--output is required")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = build(&candidate, &plan, source, &reference_patch)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(&output, bytes).map_err(|error| format!("cannot write output: {error}"))?;
    println!("{}", value);
    Ok(())
}
