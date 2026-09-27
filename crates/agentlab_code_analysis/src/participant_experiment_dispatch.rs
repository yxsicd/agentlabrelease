use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    io::Read,
    path::{Path, PathBuf},
};

const DISPATCH_SCHEMA: &str = "agentlab.participant_experiment_dispatch.v1";
const PLAN_SCHEMA: &str = "agentlab.participant_experiment_plan.v1";
const WORKFLOW_PATH: &str = ".github/workflows/multi-repo-assessed-campaign.yml";
const SLSA_PROVENANCE: &str = "https://slsa.dev/provenance/v1";

struct FileInput {
    bytes: Vec<u8>,
    value: Option<Value>,
}

impl FileInput {
    fn load(path: &Path, label: &str, json: bool) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let value = if json {
            let value: Value = serde_json::from_slice(&bytes)
                .map_err(|error| format!("cannot parse {label}: {error}"))?;
            if !value.is_object() {
                return Err(format!("{label} must contain a JSON object"));
            }
            Some(value)
        } else {
            None
        };
        Ok(Self { bytes, value })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }

    fn object(&self) -> &Value {
        self.value.as_ref().expect("JSON input")
    }
}

fn file_sha256(path: &Path, label: &str) -> Result<(u64, String), String> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular file"));
    }
    let mut file = fs::File::open(path).map_err(|error| format!("cannot read {label}: {error}"))?;
    let mut hasher = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0u8; 1024 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| format!("cannot read {label}: {error}"))?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        hasher.update(&buffer[..count]);
    }
    Ok((bytes, format!("{:x}", hasher.finalize())))
}

fn parse_values(args: impl Iterator<Item = String>) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut args = args;
    while let Some(flag) = args.next() {
        if !flag.starts_with("--") {
            return Err(format!("unexpected argument: {flag}"));
        }
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), value).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    Ok(values)
}

fn required<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn path(values: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(required(values, key)?))
}

fn number(values: &BTreeMap<String, String>, key: &str) -> Result<u64, String> {
    required(values, key)?
        .parse::<u64>()
        .ok()
        .filter(|value| *value > 0)
        .ok_or_else(|| format!("{key} must be a positive integer"))
}

fn valid_lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn valid_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 200
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(byte, b'_' | b'.' | b':' | b'@' | b'/' | b'+' | b'-')
        })
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

fn exact_fields(value: &Value, expected: &[&str], label: &str) -> Result<(), String> {
    let object = value
        .as_object()
        .ok_or_else(|| format!("{label} must be an object"))?;
    let actual: BTreeSet<&str> = object.keys().map(String::as_str).collect();
    let expected: BTreeSet<&str> = expected.iter().copied().collect();
    if actual != expected {
        return Err(format!("{label} fields differ"));
    }
    Ok(())
}

fn write_new(path: &Path, value: &Value, label: &str) -> Result<(), String> {
    if path.exists() {
        return Err(format!("refusing to overwrite {label}"));
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {label} directory: {error}"))?;
    }
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(path, bytes).map_err(|error| format!("cannot write {label}: {error}"))
}

fn repository_binding(root: &Path, file: &Path, label: &str) -> Result<Value, String> {
    let input = FileInput::load(file, label, false)?;
    let root = root
        .canonicalize()
        .map_err(|error| format!("cannot resolve repository root: {error}"))?;
    let resolved = file
        .canonicalize()
        .map_err(|error| format!("cannot resolve {label}: {error}"))?;
    let relative = resolved
        .strip_prefix(&root)
        .map_err(|_| format!("{label} must be repository-owned"))?
        .to_string_lossy()
        .replace('\\', "/");
    if !valid_token(&relative) {
        return Err(format!("{label} repository path is invalid"));
    }
    Ok(json!({"path": relative, "sha256": input.sha256()}))
}

fn package_version(lock: &Value) -> Result<&str, String> {
    let version = lock["packages"]["node_modules/@mariozechner/pi-coding-agent"]["version"]
        .as_str()
        .ok_or_else(|| "Pi package is absent from participant lock".to_owned())?;
    if !valid_token(version) {
        return Err("Pi package version is invalid".into());
    }
    Ok(version)
}

fn normalize_profiles(raw: &str) -> Result<Vec<Value>, String> {
    let value: Value = serde_json::from_str(raw)
        .map_err(|error| format!("cannot parse participant profiles: {error}"))?;
    let rows = value
        .as_array()
        .filter(|rows| (3..=8).contains(&rows.len()))
        .ok_or_else(|| {
            "participant profiles must contain three to eight ordered tiers".to_owned()
        })?;
    let mut participants = BTreeSet::new();
    let mut models = BTreeSet::new();
    let mut profiles = Vec::new();
    for (ordinal, row) in rows.iter().enumerate() {
        exact_fields(row, &["participantId", "model"], "participant profile")?;
        let participant = string(row, "participantId", "participant profile")?;
        let model = string(row, "model", "participant profile")?;
        if !valid_token(participant) || !participants.insert(participant.to_owned()) {
            return Err("participant identity is invalid or duplicated".into());
        }
        if !valid_token(model) || !models.insert(model.to_owned()) {
            return Err("participant model is invalid or duplicated".into());
        }
        profiles.push(json!({
            "ordinal": ordinal,
            "participantId": participant,
            "model": model,
        }));
    }
    Ok(profiles)
}

fn freeze(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let repository_root = path(values, "--repository-root")?;
    let case = FileInput::load(&path(values, "--case")?, "evaluation case", true)?;
    let case_id = string(case.object(), "id", "evaluation case")?;
    let source_set = string(case.object(), "sourceSetSha256", "evaluation case")?;
    if !valid_token(case_id) || !valid_lower_hex(source_set, 64) {
        return Err("evaluation case identity is invalid".into());
    }
    let method_revision = required(values, "--method-revision")?;
    let image_id = required(values, "--runtime-image-id")?;
    let provider_route = required(values, "--provider-route")?;
    let repository = required(values, "--repository")?;
    if !valid_lower_hex(method_revision, 40) {
        return Err("method revision is invalid".into());
    }
    if !image_id.starts_with("sha256:") || !valid_lower_hex(&image_id[7..], 64) {
        return Err("runtime image ID is invalid".into());
    }
    if !valid_token(provider_route) || !valid_token(repository) {
        return Err("provider route or repository is invalid".into());
    }
    let trials = number(values, "--trials")?;
    if ![3, 5, 10, 20].contains(&trials) {
        return Err("trials must be one of 3, 5, 10 or 20".into());
    }
    let profiles = normalize_profiles(required(values, "--profiles-json")?)?;
    let package_lock = FileInput::load(
        &path(values, "--participant-package-lock")?,
        "participant package lock",
        true,
    )?;
    let version = package_version(package_lock.object())?;
    let manifest = FileInput::load(
        &path(values, "--participant-manifest")?,
        "participant manifest",
        true,
    )?;
    same(
        string(manifest.object(), "schema", "participant manifest")?,
        "agentlab.blind_case_participant_bundle.v1",
        "participant manifest schema",
    )?;
    let archive_path = path(values, "--runtime-image-archive")?;
    let (archive_bytes, archive_sha256) =
        file_sha256(&archive_path, "participant runtime image archive")?;
    Ok(json!({
        "schema": DISPATCH_SCHEMA,
        "status": "attested-plan-gate-frozen-before-assessment",
        "workflow": {
            "repository": repository,
            "path": WORKFLOW_PATH,
            "runId": number(values, "--workflow-run-id")?,
            "runAttempt": number(values, "--workflow-run-attempt")?,
        },
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "evaluationCaseSha256": case.sha256(),
        "caseReviewRunId": number(values, "--case-review-run-id")?,
        "methodRevision": method_revision,
        "providerRoute": provider_route,
        "trialsPerParticipant": trials,
        "participantProfileCount": profiles.len(),
        "participantProfiles": profiles,
        "executionProtocol": {
            "schema": "agentlab.participant_execution_protocol_portable.v1",
            "agentImplementation": "pi",
            "agentPackage": "@mariozechner/pi-coding-agent",
            "agentPackageVersion": version,
            "participantAdapter": repository_binding(&repository_root, &path(values, "--participant-adapter")?, "participant adapter")?,
            "participantDriver": repository_binding(&repository_root, &path(values, "--participant-driver")?, "participant driver")?,
            "participantPackageLock": repository_binding(&repository_root, &path(values, "--participant-package-lock")?, "participant package lock")?,
            "runtimeDockerfile": repository_binding(&repository_root, &path(values, "--runtime-dockerfile")?, "participant runtime Dockerfile")?,
            "runtimeBuildScript": repository_binding(&repository_root, &path(values, "--runtime-build-script")?, "participant runtime build script")?,
            "runtimeImageArchive": {
                "filename": archive_path.file_name().and_then(|name| name.to_str()).ok_or_else(|| "runtime image archive filename is invalid".to_owned())?,
                "byteLength": archive_bytes,
                "sha256": archive_sha256,
                "imageId": image_id,
            },
            "participantManifestSha256": manifest.sha256(),
            "promptAuthority": "digest-bound-adapter-driver-and-blind-case-manifest",
            "sessionPolicy": "fresh-per-attempt-persistent-across-case-stages",
            "thinkingMode": "off",
            "reasoningEffort": null,
            "extensionPolicy": "disabled",
            "skillsPolicy": "disabled",
            "contextFilePolicy": "disabled",
            "turnTimeoutSeconds": 420,
            "samplingPolicy": "provider-default-stochastic-repeated-trials",
            "portableRuntimeQualified": true,
            "crossCampaignProviderReproducibilityQualified": false,
        },
        "allowsAssessmentExecution": true,
        "automaticPromotion": false,
    }))
}

fn validate_binding(root: &Path, protocol: &Value, key: &str, label: &str) -> Result<(), String> {
    let binding = &protocol[key];
    exact_fields(binding, &["path", "sha256"], label)?;
    let relative = string(binding, "path", label)?;
    if !valid_token(relative)
        || Path::new(relative).is_absolute()
        || relative.split('/').any(|part| part == "..")
    {
        return Err(format!("{label} path is invalid"));
    }
    let input = FileInput::load(&root.join(relative), label, false)?;
    same(
        string(binding, "sha256", label)?,
        &input.sha256(),
        &format!("{label} digest"),
    )
}

fn validate_dispatch(dispatch: &FileInput) -> Result<(), String> {
    let value = dispatch.object();
    exact_fields(
        value,
        &[
            "schema",
            "status",
            "workflow",
            "caseId",
            "sourceSetSha256",
            "evaluationCaseSha256",
            "caseReviewRunId",
            "methodRevision",
            "providerRoute",
            "trialsPerParticipant",
            "participantProfileCount",
            "participantProfiles",
            "executionProtocol",
            "allowsAssessmentExecution",
            "automaticPromotion",
        ],
        "dispatch",
    )?;
    same(
        string(value, "schema", "dispatch")?,
        DISPATCH_SCHEMA,
        "dispatch schema",
    )?;
    same(
        string(value, "status", "dispatch")?,
        "attested-plan-gate-frozen-before-assessment",
        "dispatch status",
    )?;
    if value["allowsAssessmentExecution"].as_bool() != Some(true)
        || value["automaticPromotion"].as_bool() != Some(false)
    {
        return Err("dispatch authority differs".into());
    }
    for (key, length) in [
        ("sourceSetSha256", 64),
        ("evaluationCaseSha256", 64),
        ("methodRevision", 40),
    ] {
        if !valid_lower_hex(string(value, key, "dispatch")?, length) {
            return Err(format!("dispatch {key} is invalid"));
        }
    }
    if !valid_token(string(value, "caseId", "dispatch")?)
        || !valid_token(string(value, "providerRoute", "dispatch")?)
        || value["caseReviewRunId"]
            .as_u64()
            .filter(|number| *number > 0)
            .is_none()
        || !matches!(
            value["trialsPerParticipant"].as_u64(),
            Some(3 | 5 | 10 | 20)
        )
    {
        return Err("dispatch case, route, review run or trial count is invalid".into());
    }
    let workflow = &value["workflow"];
    exact_fields(
        workflow,
        &["repository", "path", "runId", "runAttempt"],
        "dispatch workflow",
    )?;
    if !valid_token(string(workflow, "repository", "dispatch workflow")?)
        || string(workflow, "path", "dispatch workflow")? != WORKFLOW_PATH
        || workflow["runId"]
            .as_u64()
            .filter(|number| *number > 0)
            .is_none()
        || workflow["runAttempt"]
            .as_u64()
            .filter(|number| *number > 0)
            .is_none()
    {
        return Err("dispatch workflow identity is invalid".into());
    }
    let profiles = value["participantProfiles"]
        .as_array()
        .filter(|rows| (3..=8).contains(&rows.len()))
        .ok_or_else(|| "dispatch participant profiles are invalid".to_owned())?;
    if value["participantProfileCount"].as_u64() != Some(profiles.len() as u64) {
        return Err("dispatch participant profile count differs".into());
    }
    let mut participants = BTreeSet::new();
    let mut models = BTreeSet::new();
    for (ordinal, row) in profiles.iter().enumerate() {
        exact_fields(
            row,
            &["ordinal", "participantId", "model"],
            "dispatch participant profile",
        )?;
        if row["ordinal"].as_u64() != Some(ordinal as u64)
            || !participants.insert(string(
                row,
                "participantId",
                "dispatch participant profile",
            )?)
            || !models.insert(string(row, "model", "dispatch participant profile")?)
        {
            return Err("dispatch participant profile order or uniqueness differs".into());
        }
    }
    let protocol = &value["executionProtocol"];
    exact_fields(
        protocol,
        &[
            "schema",
            "agentImplementation",
            "agentPackage",
            "agentPackageVersion",
            "participantAdapter",
            "participantDriver",
            "participantPackageLock",
            "runtimeDockerfile",
            "runtimeBuildScript",
            "runtimeImageArchive",
            "participantManifestSha256",
            "promptAuthority",
            "sessionPolicy",
            "thinkingMode",
            "reasoningEffort",
            "extensionPolicy",
            "skillsPolicy",
            "contextFilePolicy",
            "turnTimeoutSeconds",
            "samplingPolicy",
            "portableRuntimeQualified",
            "crossCampaignProviderReproducibilityQualified",
        ],
        "portable execution protocol",
    )?;
    same(
        string(protocol, "schema", "portable execution protocol")?,
        "agentlab.participant_execution_protocol_portable.v1",
        "portable execution protocol schema",
    )?;
    same(
        string(
            protocol,
            "agentImplementation",
            "portable execution protocol",
        )?,
        "pi",
        "participant implementation",
    )?;
    same(
        string(protocol, "agentPackage", "portable execution protocol")?,
        "@mariozechner/pi-coding-agent",
        "participant package",
    )?;
    if !valid_token(string(
        protocol,
        "agentPackageVersion",
        "portable execution protocol",
    )?) {
        return Err("participant package version is invalid".into());
    }
    for (key, expected) in [
        (
            "promptAuthority",
            "digest-bound-adapter-driver-and-blind-case-manifest",
        ),
        (
            "sessionPolicy",
            "fresh-per-attempt-persistent-across-case-stages",
        ),
        ("thinkingMode", "off"),
        ("extensionPolicy", "disabled"),
        ("skillsPolicy", "disabled"),
        ("contextFilePolicy", "disabled"),
        (
            "samplingPolicy",
            "provider-default-stochastic-repeated-trials",
        ),
    ] {
        same(
            string(protocol, key, "portable execution protocol")?,
            expected,
            &format!("portable execution protocol {key}"),
        )?;
    }
    if !protocol["reasoningEffort"].is_null()
        || protocol["turnTimeoutSeconds"].as_u64() != Some(420)
        || !valid_lower_hex(
            string(
                protocol,
                "participantManifestSha256",
                "portable execution protocol",
            )?,
            64,
        )
    {
        return Err("portable execution protocol policy differs".into());
    }
    for key in [
        "participantAdapter",
        "participantDriver",
        "participantPackageLock",
        "runtimeDockerfile",
        "runtimeBuildScript",
    ] {
        let binding = &protocol[key];
        exact_fields(binding, &["path", "sha256"], key)?;
        let relative = string(binding, "path", key)?;
        if !valid_token(relative)
            || Path::new(relative).is_absolute()
            || relative.split('/').any(|part| part == "..")
            || !valid_lower_hex(string(binding, "sha256", key)?, 64)
        {
            return Err(format!(
                "portable execution protocol {key} binding is invalid"
            ));
        }
    }
    let archive = &protocol["runtimeImageArchive"];
    exact_fields(
        archive,
        &["filename", "byteLength", "sha256", "imageId"],
        "runtime image archive binding",
    )?;
    if archive["byteLength"]
        .as_u64()
        .filter(|value| *value > 0)
        .is_none()
        || !valid_lower_hex(
            string(archive, "sha256", "runtime image archive binding")?,
            64,
        )
        || !valid_token(string(
            archive,
            "filename",
            "runtime image archive binding",
        )?)
        || !string(archive, "imageId", "runtime image archive binding")?.starts_with("sha256:")
        || !valid_lower_hex(
            &string(archive, "imageId", "runtime image archive binding")?[7..],
            64,
        )
        || protocol["portableRuntimeQualified"].as_bool() != Some(true)
        || protocol["crossCampaignProviderReproducibilityQualified"].as_bool() != Some(false)
    {
        return Err("portable runtime qualification differs".into());
    }
    Ok(())
}

fn validate_attestation(
    path: &Path,
    dispatch_sha: &str,
    run_id: u64,
    run_attempt: u64,
) -> Result<String, String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("cannot inspect dispatch attestation verification: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err("dispatch attestation verification must be a regular file".into());
    }
    let bytes = fs::read(path)
        .map_err(|error| format!("cannot read dispatch attestation verification: {error}"))?;
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|error| format!("cannot parse dispatch attestation verification: {error}"))?;
    let rows = value
        .as_array()
        .filter(|rows| !rows.is_empty())
        .ok_or_else(|| "dispatch attestation verification is empty".to_owned())?;
    let suffix = format!("/actions/runs/{run_id}/attempts/{run_attempt}");
    let matched = rows.iter().any(|row| {
        let statement = &row["verificationResult"]["statement"];
        statement["predicateType"].as_str() == Some(SLSA_PROVENANCE)
            && statement["subject"].as_array().is_some_and(|subjects| {
                subjects
                    .iter()
                    .any(|subject| subject["digest"]["sha256"].as_str() == Some(dispatch_sha))
            })
            && statement["predicate"]["runDetails"]["metadata"]["invocationId"]
                .as_str()
                .is_some_and(|value| value.ends_with(&suffix))
    });
    if !matched {
        return Err("dispatch attestation does not bind the exact workflow run".into());
    }
    Ok(digest(&bytes))
}

fn materialize(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let dispatch = FileInput::load(&path(values, "--dispatch")?, "participant dispatch", true)?;
    validate_dispatch(&dispatch)?;
    let value = dispatch.object();
    let run_id = number(values, "--workflow-run-id")?;
    let run_attempt = number(values, "--workflow-run-attempt")?;
    let workflow = &value["workflow"];
    same(
        string(workflow, "repository", "dispatch workflow")?,
        required(values, "--repository")?,
        "dispatch repository",
    )?;
    same(
        string(workflow, "path", "dispatch workflow")?,
        WORKFLOW_PATH,
        "dispatch workflow path",
    )?;
    if workflow["runId"].as_u64() != Some(run_id)
        || workflow["runAttempt"].as_u64() != Some(run_attempt)
    {
        return Err("dispatch workflow run identity differs".into());
    }
    same(
        string(value, "methodRevision", "dispatch")?,
        required(values, "--method-revision")?,
        "dispatch method revision",
    )?;
    let case = FileInput::load(&path(values, "--case")?, "evaluation case", true)?;
    same(
        string(value, "caseId", "dispatch")?,
        string(case.object(), "id", "evaluation case")?,
        "dispatch case identity",
    )?;
    same(
        string(value, "sourceSetSha256", "dispatch")?,
        string(case.object(), "sourceSetSha256", "evaluation case")?,
        "dispatch source set",
    )?;
    same(
        string(value, "evaluationCaseSha256", "dispatch")?,
        &case.sha256(),
        "dispatch evaluation case digest",
    )?;
    let repository_root = path(values, "--repository-root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve repository root: {error}"))?;
    let protocol = &value["executionProtocol"];
    for (key, label) in [
        ("participantAdapter", "participant adapter"),
        ("participantDriver", "participant driver"),
        ("participantPackageLock", "participant package lock"),
        ("runtimeDockerfile", "participant runtime Dockerfile"),
        ("runtimeBuildScript", "participant runtime build script"),
    ] {
        validate_binding(&repository_root, protocol, key, label)?;
    }
    let archive_path = path(values, "--runtime-image-archive")?;
    let archive_binding = &protocol["runtimeImageArchive"];
    same(
        archive_path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| "runtime image archive filename is invalid".to_owned())?,
        string(archive_binding, "filename", "runtime image archive binding")?,
        "runtime image archive filename",
    )?;
    let (archive_bytes, archive_sha) =
        file_sha256(&archive_path, "participant runtime image archive")?;
    if archive_binding["byteLength"].as_u64() != Some(archive_bytes) {
        return Err("runtime image archive byte length differs".into());
    }
    same(
        string(archive_binding, "sha256", "runtime image archive binding")?,
        &archive_sha,
        "runtime image archive digest",
    )?;
    let runtime = FileInput::load(
        &path(values, "--runtime-config")?,
        "participant runtime config",
        true,
    )?;
    same(
        string(runtime.object(), "schema", "participant runtime config")?,
        "agentlab.participant_docker_runtime.v1",
        "participant runtime schema",
    )?;
    same(
        string(runtime.object(), "imageId", "participant runtime config")?,
        string(archive_binding, "imageId", "runtime image archive binding")?,
        "materialized runtime image identity",
    )?;
    same(
        string(
            runtime.object(),
            "piPackageLockSha256",
            "participant runtime config",
        )?,
        string(
            &protocol["participantPackageLock"],
            "sha256",
            "participant package lock",
        )?,
        "materialized participant package lock",
    )?;
    same(
        string(
            runtime.object(),
            "participantManifestSha256",
            "participant runtime config",
        )?,
        string(
            protocol,
            "participantManifestSha256",
            "portable execution protocol",
        )?,
        "materialized participant manifest",
    )?;
    let attestation_sha = validate_attestation(
        &path(values, "--attestation-verification")?,
        &dispatch.sha256(),
        run_id,
        run_attempt,
    )?;
    let local_protocol = json!({
        "schema": "agentlab.participant_execution_protocol.v1",
        "agentImplementation": protocol["agentImplementation"],
        "agentPackage": protocol["agentPackage"],
        "agentPackageVersion": protocol["agentPackageVersion"],
        "participantAdapter": protocol["participantAdapter"],
        "participantDriver": protocol["participantDriver"],
        "participantPackageLockSha256": protocol["participantPackageLock"]["sha256"],
        "participantRuntimeConfigSha256": runtime.sha256(),
        "runtimeImageId": archive_binding["imageId"],
        "participantManifestSha256": protocol["participantManifestSha256"],
        "promptAuthority": protocol["promptAuthority"],
        "sessionPolicy": protocol["sessionPolicy"],
        "thinkingMode": protocol["thinkingMode"],
        "reasoningEffort": protocol["reasoningEffort"],
        "extensionPolicy": protocol["extensionPolicy"],
        "skillsPolicy": protocol["skillsPolicy"],
        "contextFilePolicy": protocol["contextFilePolicy"],
        "turnTimeoutSeconds": protocol["turnTimeoutSeconds"],
        "samplingPolicy": protocol["samplingPolicy"],
        "withinCampaignExecutionProtocolQualified": true,
        "crossCampaignProviderReproducibilityQualified": false,
    });
    let plan = json!({
        "schema": PLAN_SCHEMA,
        "status": "predeclared-before-attempts",
        "caseId": value["caseId"],
        "sourceSetSha256": value["sourceSetSha256"],
        "evaluationCaseSha256": value["evaluationCaseSha256"],
        "caseReviewRunId": value["caseReviewRunId"],
        "methodRevision": value["methodRevision"],
        "providerRoute": value["providerRoute"],
        "trialsPerParticipant": value["trialsPerParticipant"],
        "participantProfileCount": value["participantProfileCount"],
        "participantProfiles": value["participantProfiles"],
        "executionProtocol": local_protocol,
        "automaticPromotion": false,
    });
    let output = path(values, "--output")?;
    write_new(&output, &plan, "participant experiment plan")?;
    let plan_input = FileInput::load(&output, "participant experiment plan", true)?;
    let receipt = json!({
        "schema": "agentlab.participant_experiment_dispatch_materialization.v1",
        "status": "attested-portable-dispatch-materialized-before-attempts",
        "dispatchSha256": dispatch.sha256(),
        "dispatchAttestationVerificationSha256": attestation_sha,
        "planSha256": plan_input.sha256(),
        "runtimeConfigSha256": runtime.sha256(),
        "runtimeImageArchiveSha256": archive_sha,
        "runtimeImageId": archive_binding["imageId"],
        "workflowRunId": run_id,
        "workflowRunAttempt": run_attempt,
        "portableRuntimeQualified": true,
        "attemptsStarted": false,
        "automaticPromotion": false,
    });
    write_new(
        &path(values, "--verification-output")?,
        &receipt,
        "dispatch materialization receipt",
    )?;
    Ok(receipt)
}

fn run() -> Result<Value, String> {
    let mut args = env::args().skip(1);
    let command = args
        .next()
        .ok_or_else(|| "missing command: freeze or materialize".to_owned())?;
    let values = parse_values(args)?;
    match command.as_str() {
        "freeze" => {
            let value = freeze(&values)?;
            write_new(&path(&values, "--output")?, &value, "participant dispatch")?;
            Ok(json!({
                "ok": true,
                "schema": DISPATCH_SCHEMA,
                "participantProfileCount": value["participantProfileCount"],
                "trialsPerParticipant": value["trialsPerParticipant"],
            }))
        }
        "materialize" => materialize(&values),
        _ => Err(format!("unknown command: {command}")),
    }
}

fn main() {
    match run() {
        Ok(value) => println!("{}", serde_json::to_string(&value).unwrap()),
        Err(error) => {
            eprintln!("participant experiment dispatch invalid: {error}");
            std::process::exit(1);
        }
    }
}
