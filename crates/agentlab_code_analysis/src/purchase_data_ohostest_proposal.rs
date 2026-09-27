use agentlab_code_analysis::{analyze, digest};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

const PLAN_SCHEMA: &str = "agentlab.purchase_data_behavior_oracle_plan.v1";
const BUILD_SCHEMA: &str = "agentlab.multi_repo_source_build_qualification.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_ohostest_proposal.v1";
const HARMONY_REPOSITORY: &str = "harmony-iap-client";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: &Path, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
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

struct Arguments {
    plan: PathBuf,
    build: PathBuf,
    repositories: BTreeMap<String, PathBuf>,
    output: PathBuf,
}

fn string<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| format!("{label} {key} is absent"))
}

fn exact(value: &Value, key: &str, expected: &str, label: &str) -> Result<(), String> {
    if string(value, key, label)? != expected {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn safe_relative(path: &str) -> bool {
    !path.is_empty()
        && !Path::new(path).is_absolute()
        && Path::new(path)
            .components()
            .all(|part| matches!(part, Component::Normal(_)))
}

fn git(root: &Path, arguments: &[&str], label: &str) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(arguments)
        .output()
        .map_err(|error| format!("cannot run git for {label}: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "git failed for {label}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(output.stdout)
}

fn git_text(root: &Path, arguments: &[&str], label: &str) -> Result<String, String> {
    String::from_utf8(git(root, arguments, label)?)
        .map(|value| value.trim().to_owned())
        .map_err(|error| format!("git returned non-UTF-8 for {label}: {error}"))
}

fn git_file(root: &Path, revision: &str, path: &str, label: &str) -> Result<Vec<u8>, String> {
    if !safe_relative(path) {
        return Err(format!("unsafe source path for {label}: {path}"));
    }
    git(root, &["show", &format!("{revision}:{path}")], label)
}

fn parse_arguments() -> Result<Arguments, String> {
    let mut plan = None;
    let mut build = None;
    let mut output = None;
    let mut repositories = BTreeMap::new();
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        match flag.as_str() {
            "--behavior-plan" if plan.is_none() => plan = Some(PathBuf::from(value)),
            "--build-qualification" if build.is_none() => build = Some(PathBuf::from(value)),
            "--output" if output.is_none() => output = Some(PathBuf::from(value)),
            "--repository" => {
                let (id, path) = value
                    .split_once('=')
                    .ok_or_else(|| "--repository must be ID=PATH".to_string())?;
                if id.is_empty()
                    || repositories
                        .insert(id.to_owned(), PathBuf::from(path))
                        .is_some()
                {
                    return Err(format!("invalid or duplicate repository: {id}"));
                }
            }
            _ => return Err(format!("unknown or duplicate argument: {flag}")),
        }
    }
    Ok(Arguments {
        plan: plan.ok_or("missing required argument: --behavior-plan")?,
        build: build.ok_or("missing required argument: --build-qualification")?,
        repositories,
        output: output.ok_or("missing required argument: --output")?,
    })
}

fn validate_lineage(plan: &Input, build: &Input) -> Result<(), String> {
    exact(&plan.value, "schema", PLAN_SCHEMA, "behavior plan")?;
    exact(&build.value, "schema", BUILD_SCHEMA, "build qualification")?;
    exact(
        &build.value,
        "status",
        "partial-build-qualified-review-required",
        "build qualification",
    )?;
    for key in ["candidateId", "sourceSetSha256"] {
        if string(&plan.value, key, "behavior plan")?
            != string(&build.value, key, "build qualification")?
        {
            return Err(format!("build qualification {key} differs"));
        }
    }
    for (value, label) in [
        (&plan.value, "behavior plan"),
        (&build.value, "build qualification"),
    ] {
        if !valid_sha256(string(value, "reviewPacketSha256", label)?) {
            return Err(format!("{label} review packet digest is invalid"));
        }
    }
    if build.value["allowsCaseContract"].as_bool() != Some(false)
        || build.value["automaticPromotion"].as_bool() != Some(false)
    {
        return Err("build qualification exceeds proposal authority".into());
    }
    Ok(())
}

fn repository_row<'a>(plan: &'a Value, id: &str) -> Result<&'a Value, String> {
    plan["repositories"]
        .as_array()
        .and_then(|rows| rows.iter().find(|row| row["id"] == id))
        .ok_or_else(|| format!("behavior plan repository is absent: {id}"))
}

fn exact_source(plan: &Value, root: &Path) -> Result<(String, String, Vec<u8>, String), String> {
    let repository = repository_row(plan, HARMONY_REPOSITORY)?;
    let revision = string(repository, "revision", "Harmony repository")?;
    let resolved = git_text(
        root,
        &["rev-parse", &format!("{revision}^{{commit}}")],
        "Harmony revision",
    )?;
    if resolved != revision {
        return Err("Harmony repository revision differs".into());
    }
    let files = repository["files"]
        .as_array()
        .ok_or_else(|| "Harmony source files are absent".to_string())?;
    if files.len() != 1 {
        return Err("Harmony source file inventory differs".into());
    }
    let row = &files[0];
    let path = string(row, "path", "Harmony source file")?;
    let bytes = git_file(root, revision, path, "Harmony source file")?;
    if digest(&bytes) != string(row, "contentSha256", "Harmony source file")? {
        return Err("Harmony source content digest differs".into());
    }
    let blob = git_text(
        root,
        &["rev-parse", &format!("{revision}:{path}")],
        "Harmony source blob",
    )?;
    if blob != string(row, "gitBlobOid", "Harmony source file")? {
        return Err("Harmony source blob differs".into());
    }
    Ok((revision.to_owned(), path.to_owned(), bytes, blob))
}

fn source_paths(root: &Path, revision: &str) -> Result<Vec<String>, String> {
    let listing = git_text(
        root,
        &["ls-tree", "-r", "--name-only", revision],
        "source tree",
    )?;
    Ok(listing.lines().map(str::to_owned).collect())
}

fn methods_and_checks(plan: &Value) -> Result<(Vec<String>, Vec<String>), String> {
    let methods: Vec<String> = plan["methods"]
        .as_array()
        .ok_or_else(|| "behavior plan methods are absent".to_string())?
        .iter()
        .filter(|row| row["runtime"] == "harmony")
        .map(|row| string(row, "id", "Harmony method").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    let checks: Vec<String> = plan["checks"]
        .as_array()
        .ok_or_else(|| "behavior plan checks are absent".to_string())?
        .iter()
        .filter(|row| row["stage"] == "harmony-finalization")
        .map(|row| string(row, "id", "Harmony check").map(str::to_owned))
        .collect::<Result<_, _>>()?;
    if methods.len() != 2
        || methods.iter().collect::<BTreeSet<_>>().len() != 2
        || checks.len() != 5
        || checks.iter().collect::<BTreeSet<_>>().len() != 5
    {
        return Err("Harmony method or check inventory differs".into());
    }
    Ok((methods, checks))
}

fn build_proposal(plan: &Input, build: &Input, root: &Path) -> Result<Value, String> {
    validate_lineage(plan, build)?;
    let (revision, source_path, source, blob) = exact_source(&plan.value, root)?;
    let source_text = std::str::from_utf8(&source).map_err(|error| error.to_string())?;
    let analysis = analyze(&source_path, &source, &revision)?;
    if analysis.has_errors {
        return Err("Harmony source contains syntax errors".into());
    }
    let (methods, checks) = methods_and_checks(&plan.value)?;
    for method in &methods {
        if !analysis.rows.iter().any(|row| {
            row["kind"] == "symbol" && row["symbol"] == *method && row["owner"] == "ConsumablesPage"
        }) {
            return Err(format!(
                "Harmony method is not owned by ConsumablesPage: {method}"
            ));
        }
    }
    let paths = source_paths(root, &revision)?;
    let existing_tests: Vec<_> = paths
        .iter()
        .filter(|path| {
            path.starts_with("entry/src/ohosTest/")
                && (path.ends_with(".ets") || path.ends_with(".ts"))
        })
        .cloned()
        .collect();
    let build_profile = git_file(
        root,
        &revision,
        "entry/build-profile.json5",
        "Harmony build profile",
    )?;
    let package = git_file(
        root,
        &revision,
        "oh-package.json5",
        "Harmony package manifest",
    )?;
    let has_target = String::from_utf8_lossy(&build_profile).contains("ohosTest");
    let has_hypium = String::from_utf8_lossy(&package).contains("@ohos/hypium");
    if !has_target || !has_hypium {
        return Err("Harmony repository lacks the declared OHOS Test lane".into());
    }
    let component_exported = source_text.contains("export struct ConsumablesPage");
    let direct_decoder = analysis.rows.iter().any(|row| {
        row["kind"] == "call"
            && row["owner"] == "ConsumablesPage::dealPurchaseData"
            && row["targetExpression"] == "JWSUtil.decodeJwsObj"
    });
    let direct_sink = analysis.rows.iter().any(|row| {
        row["kind"] == "call"
            && row["owner"] == "ConsumablesPage::finishPurchase"
            && row["targetExpression"] == "iap.finishPurchase"
    });
    if !direct_decoder || !direct_sink {
        return Err("expected Harmony decoder or finish sink is absent".into());
    }
    let mut blockers = Vec::new();
    if existing_tests.is_empty() {
        blockers.push("no-source-bound-ohostest");
    }
    if !component_exported {
        blockers.push("component-not-exported-for-direct-test");
    }
    if direct_decoder {
        blockers.push("decoder-is-static-direct-dependency");
    }
    if direct_sink {
        blockers.push("finish-sink-is-static-direct-dependency");
    }
    blockers.push("ui-only-path-requires-external-account-and-vendor-service");
    Ok(json!({
        "schema":OUTPUT_SCHEMA,
        "status":"testability-refactor-required-before-standard-test-authoring",
        "candidateId":plan.value["candidateId"],
        "sourceSetSha256":plan.value["sourceSetSha256"],
        "lineage":{
            "behaviorPlanSha256":plan.sha256(),
            "buildQualificationSha256":build.sha256(),
            "behaviorPlanReviewPacketSha256":plan.value["reviewPacketSha256"],
            "buildQualificationReviewPacketSha256":build.value["reviewPacketSha256"],
            "repositoryId":HARMONY_REPOSITORY,
            "sourceRevision":revision,
            "sourcePath":source_path,
            "sourceBlobOid":blob,
            "sourceSha256":digest(&source)
        },
        "observedStandardLane":{
            "framework":"instrument-test-ohosTest-hypium",
            "buildTargetDeclared":has_target,
            "hypiumDependencyDeclared":has_hypium,
            "existingTestSourcePaths":existing_tests,
            "sourceTestCount":existing_tests.len()
        },
        "programAnalysis":{
            "methodIds":methods,
            "methodOwner":"ConsumablesPage",
            "componentExported":component_exported,
            "directDecoderCall":"JWSUtil.decodeJwsObj",
            "directFinishSinkCall":"iap.finishPurchase",
            "syntaxHasErrors":false,
            "analyzerMethod":agentlab_code_analysis::GRAMMAR
        },
        "blockedBehaviorCheckIds":checks,
        "blockers":blockers,
        "requiredTestabilityRefactor":[
            "extract-an-exported-purchase-finalization-policy-from-the-arkui-component",
            "inject-the-jws-decoder-and-finish-purchase-sink-behind-bounded-interfaces",
            "keep-the-component-as-an-adapter-without-changing-user-visible-purchase-semantics",
            "author-hypium-positive-and-negative-tests-for-all-five-harmony-checks"
        ],
        "qualificationBoundary":{
            "exactSourceInspected":true,
            "ohosTestSourceAuthored":false,
            "ohosTestExecuted":false,
            "emulatorExecuted":false,
            "behaviorOracleVerified":false,
            "allowsRuntimeCalibration":false,
            "allowsCaseContract":false,
            "automaticPromotion":false
        },
        "nextGate":"review-and-implement-testability-refactor-then-author-source-bound-ohostest"
    }))
}

fn run() -> Result<(), String> {
    let args = parse_arguments()?;
    if args.output.exists() {
        return Err(format!(
            "refusing to overwrite output: {}",
            args.output.display()
        ));
    }
    if args.repositories.len() != 1 || !args.repositories.contains_key(HARMONY_REPOSITORY) {
        return Err("exactly one harmony-iap-client repository is required".into());
    }
    let plan = Input::load(&args.plan, "behavior plan")?;
    let build = Input::load(&args.build, "build qualification")?;
    let proposal = build_proposal(
        &plan,
        &build,
        args.repositories.get(HARMONY_REPOSITORY).unwrap(),
    )?;
    if let Some(parent) = args.output.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create output directory: {error}"))?;
    }
    let mut bytes = serde_json::to_vec_pretty(&proposal).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(&args.output, &bytes).map_err(|error| format!("cannot write output: {error}"))?;
    println!(
        "{}",
        json!({
            "ok":true,
            "status":proposal["status"],
            "blockedCheckCount":proposal["blockedBehaviorCheckIds"].as_array().map_or(0, Vec::len),
            "outputSha256":digest(&bytes)
        })
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test proposal invalid: {error}");
        std::process::exit(1);
    }
}
