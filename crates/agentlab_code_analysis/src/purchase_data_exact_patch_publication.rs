use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

const CONTRACT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_cohort_contract.v1";
const PACKET_SCHEMA: &str = "agentlab.purchase_data_integrated_review_packet.v1";
const GATE_SCHEMA: &str = "agentlab.purchase_data_integrated_review_gate.v1";
const SOURCE_PACKET_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_packet.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_exact_patch_publication.v1";

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

struct TemporaryIndex(PathBuf);

impl Drop for TemporaryIndex {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
        let lock = self.0.with_extension("lock");
        let _ = fs::remove_file(lock);
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

fn valid_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn sha<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    let value = string(value, key, label)?;
    if !valid_hex(value, 64) {
        return Err(format!("{label} {key} is not lowercase SHA-256"));
    }
    Ok(value)
}

fn revision<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    let value = string(value, key, label)?;
    if !valid_hex(value, 40) {
        return Err(format!("{label} {key} is not an exact revision"));
    }
    Ok(value)
}

fn safe_relative(value: &str, label: &str) -> Result<PathBuf, String> {
    let path = Path::new(value);
    if path.is_absolute()
        || value.split('/').any(|part| part.is_empty() || part == "..")
        || value.contains('\\')
    {
        return Err(format!("{label} path is invalid"));
    }
    Ok(path.to_path_buf())
}

fn canonical_regular_below(root: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("cannot resolve {label} root: {error}"))?;
    let path = root.join(safe_relative(relative, label)?);
    let metadata =
        fs::symlink_metadata(&path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular file"));
    }
    let resolved = path
        .canonicalize()
        .map_err(|error| format!("cannot resolve {label}: {error}"))?;
    if !resolved.starts_with(&root) {
        return Err(format!("{label} leaves its trusted root"));
    }
    Ok(resolved)
}

fn validate_contract(contract: &Input, packet: &Input) -> Result<(), String> {
    same(
        string(&contract.value, "schema", "cohort contract")?,
        CONTRACT_SCHEMA,
        "cohort contract schema",
    )?;
    same(
        string(&contract.value, "status", "cohort contract")?,
        "execution-contract-frozen-prerequisites-pending",
        "cohort contract status",
    )?;
    same(
        sha(&contract.value, "packetSha256", "cohort contract")?,
        &packet.sha256(),
        "cohort contract packet digest",
    )?;
    exact_bool(
        &contract.value,
        "allowsCaseContract",
        false,
        "cohort contract",
    )?;
    exact_bool(
        &contract.value,
        "automaticPromotion",
        false,
        "cohort contract",
    )
}

fn validate_packet_and_gate(packet: &Input, gate: &Input) -> Result<(), String> {
    same(
        string(&packet.value, "schema", "integrated packet")?,
        PACKET_SCHEMA,
        "integrated packet schema",
    )?;
    same(
        string(&gate.value, "schema", "integrated review gate")?,
        GATE_SCHEMA,
        "integrated review gate schema",
    )?;
    same(
        string(&gate.value, "status", "integrated review gate")?,
        "independent-dual-review-approved-next-calibration-only",
        "integrated review gate status",
    )?;
    same(
        sha(&gate.value, "packetSha256", "integrated review gate")?,
        &packet.sha256(),
        "integrated review gate packet digest",
    )?;
    if gate.value["sourceLineage"] != packet.value["sourceLineage"] {
        return Err("integrated review gate source lineage differs".into());
    }
    if gate.value["distinctAuthenticatedReviewerCount"].as_u64() != Some(2) {
        return Err("integrated review gate reviewer count differs".into());
    }
    let reviewers = gate.value["reviewers"]
        .as_array()
        .filter(|rows| rows.len() == 2)
        .ok_or_else(|| "integrated review gate reviewers differ".to_owned())?;
    let first = string(&reviewers[0], "identity", "integrated reviewer")?;
    let second = string(&reviewers[1], "identity", "integrated reviewer")?;
    if !first.starts_with("github:")
        || !second.starts_with("github:")
        || first.eq_ignore_ascii_case(second)
    {
        return Err(
            "integrated review gate reviewers are not distinct authenticated actors".into(),
        );
    }
    for key in [
        "semanticAlignmentVerified",
        "independentSourceReviewCompleted",
        "independentOracleReviewCompleted",
        "allowsExactPatchPublication",
        "requiresUpstreamRevisionReexecution",
    ] {
        exact_bool(&gate.value, key, true, "integrated review gate")?;
    }
    for key in ["allowsCaseContract", "automaticPromotion"] {
        exact_bool(&gate.value, key, false, "integrated review gate")?;
    }
    for key in ["semanticDecisionSha256", "oracleDecisionSha256"] {
        sha(&gate.value, key, "integrated review gate")?;
    }
    Ok(())
}

fn load_source_packet(
    packet: &Input,
    qualification_root: &Path,
) -> Result<(Input, PathBuf), String> {
    let binding = &packet.value["evidenceAttachments"]["source-review-packet"];
    let path = canonical_regular_below(
        qualification_root,
        string(binding, "path", "source-review packet binding")?,
        "source-review packet",
    )?;
    let source = Input::load(&path, "source-review packet")?;
    same(
        sha(binding, "sha256", "source-review packet binding")?,
        &source.sha256(),
        "source-review packet digest",
    )?;
    if binding["byteLength"].as_u64() != Some(source.bytes.len() as u64) {
        return Err("source-review packet byte length differs".into());
    }
    same(
        string(&source.value, "schema", "source-review packet")?,
        SOURCE_PACKET_SCHEMA,
        "source-review packet schema",
    )?;
    for key in ["baseRevision", "candidateRevision"] {
        same(
            revision(&source.value, key, "source-review packet")?,
            revision(
                &packet.value["sourceLineage"],
                key,
                "integrated source lineage",
            )?,
            &format!("source-review packet {key}"),
        )?;
    }
    Ok((source, path))
}

fn load_patch(source: &Input, agentlab_root: &Path) -> Result<(PathBuf, Vec<u8>), String> {
    let binding = &source.value["artifacts"]["patch"];
    let path = canonical_regular_below(
        agentlab_root,
        string(binding, "path", "reviewed patch binding")?,
        "reviewed patch",
    )?;
    let bytes = fs::read(&path).map_err(|error| format!("cannot read reviewed patch: {error}"))?;
    same(
        sha(binding, "sha256", "reviewed patch binding")?,
        &digest(&bytes),
        "reviewed patch digest",
    )?;
    if binding["byteLength"].as_u64() != Some(bytes.len() as u64) {
        return Err("reviewed patch byte length differs".into());
    }
    Ok((path, bytes))
}

fn git(root: &Path, args: &[&str], index: Option<&Path>) -> Result<String, String> {
    let mut command = Command::new("git");
    command.arg("-C").arg(root).args(args);
    if let Some(index) = index {
        command.env("GIT_INDEX_FILE", index);
    }
    let output = command
        .output()
        .map_err(|error| format!("cannot execute git {}: {error}", args.join(" ")))?;
    if !output.status.success() {
        return Err(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    String::from_utf8(output.stdout)
        .map(|value| value.trim().to_owned())
        .map_err(|error| format!("git {} output is not UTF-8: {error}", args.join(" ")))
}

fn exact_patch_tree(root: &Path, base_revision: &str, patch: &Path) -> Result<String, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| format!("system clock is invalid: {error}"))?
        .as_nanos();
    let index = TemporaryIndex(env::temp_dir().join(format!(
        "agentlab-publication-index-{}-{nonce}",
        std::process::id()
    )));
    git(root, &["read-tree", base_revision], Some(&index.0))?;
    let patch = patch
        .to_str()
        .ok_or_else(|| "reviewed patch path is not UTF-8".to_owned())?;
    git(
        root,
        &["apply", "--cached", "--whitespace=nowarn", patch],
        Some(&index.0),
    )?;
    git(root, &["write-tree"], Some(&index.0))
}

fn verify_published_repository(
    root: &Path,
    repository: &str,
    base_revision: &str,
    published_revision: &str,
    patch: &Path,
) -> Result<(String, String), String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("cannot resolve published repository: {error}"))?;
    same(
        &git(&root, &["remote", "get-url", "origin"], None)?,
        repository,
        "published repository origin",
    )?;
    same(
        &git(&root, &["rev-parse", "HEAD"], None)?,
        published_revision,
        "published repository HEAD",
    )?;
    if !git(
        &root,
        &["status", "--porcelain=v1", "--untracked-files=no"],
        None,
    )?
    .is_empty()
    {
        return Err("published repository tracked worktree is dirty".into());
    }
    git(
        &root,
        &[
            "merge-base",
            "--is-ancestor",
            base_revision,
            published_revision,
        ],
        None,
    )?;
    let expected_tree = exact_patch_tree(&root, base_revision, patch)?;
    let published_tree = git(
        &root,
        &["rev-parse", &format!("{published_revision}^{{tree}}")],
        None,
    )?;
    same(
        &published_tree,
        &expected_tree,
        "published revision exact reviewed-patch tree",
    )?;
    let remote = git(&root, &["ls-remote", "--exit-code", "origin"], None)?;
    if !remote.lines().any(|line| {
        line.split_whitespace()
            .next()
            .is_some_and(|revision| revision == published_revision)
    }) {
        return Err("published revision is absent from the upstream origin".into());
    }
    Ok((published_tree, digest(remote.as_bytes())))
}

fn derive(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let contract = Input::load(&path(values, "--contract")?, "cohort contract")?;
    let packet = Input::load(&path(values, "--integrated-packet")?, "integrated packet")?;
    let gate = Input::load(&path(values, "--review-gate")?, "integrated review gate")?;
    validate_contract(&contract, &packet)?;
    validate_packet_and_gate(&packet, &gate)?;
    let (source, _) = load_source_packet(&packet, &path(values, "--qualification-root")?)?;
    let (patch, _) = load_patch(&source, &path(values, "--agentlab-root")?)?;
    let published_revision = value(values, "--published-revision")?;
    if !valid_hex(published_revision, 40) {
        return Err("published revision is not exact 40-hex".into());
    }
    let review_gate_run_id = value(values, "--review-gate-run-id")?
        .parse::<u64>()
        .ok()
        .filter(|value| *value > 0)
        .ok_or_else(|| "review gate run ID is invalid".to_owned())?;
    let repository = string(&source.value, "sourceRepository", "source-review packet")?;
    let base_revision = revision(&source.value, "baseRevision", "source-review packet")?;
    let (published_tree, remote_observation_sha) = verify_published_repository(
        &path(values, "--source-repository-root")?,
        repository,
        base_revision,
        published_revision,
        &patch,
    )?;
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "exact-reviewed-patch-published",
        "contractSha256": contract.sha256(),
        "reviewGateSha256": gate.sha256(),
        "packetSha256": packet.sha256(),
        "reviewedCandidateRevision": source.value["candidateRevision"],
        "reviewedPatchSha256": source.value["artifacts"]["patch"]["sha256"],
        "repository": repository,
        "baseRevision": base_revision,
        "publishedRevision": published_revision,
        "publishedTreeOid": published_tree,
        "remoteObservationSha256": remote_observation_sha,
        "reviewGateRunId": review_gate_run_id,
        "publishedRevisionContainsExactReviewedPatch": true,
        "verifiedOnline": true,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "nextGate": "reexecute-exact-published-revision"
    }))
}

fn value<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn path(values: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(value(values, key)?))
}

fn parse_values(args: impl Iterator<Item = String>) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut args = args;
    while let Some(flag) = args.next() {
        let argument = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), argument).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    Ok(values)
}

fn run() -> Result<(), String> {
    let values = parse_values(env::args().skip(1))?;
    let output = path(&values, "--output")?;
    if output.exists() {
        return Err("refusing to overwrite output".into());
    }
    let value = derive(&values)?;
    let mut bytes = serde_json::to_vec_pretty(&value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(output, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data exact patch publication invalid: {error}");
        std::process::exit(1);
    }
}
