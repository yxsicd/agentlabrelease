use agentlab_code_analysis::{
    digest, validate_github_actions_attestation, GitHubActionsAttestationIdentity,
};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};

const CONTRACT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_cohort_contract.v1";
const REEXECUTION_SCHEMA: &str = "agentlab.purchase_data_published_revision_reexecution.v1";
const CASE_SCHEMA: &str = "agentlab.multi_repo_evaluation_case.v1";
const CUT_SCHEMA: &str = "agentlab.blind_case_cut_receipt.v1";
const PARTICIPANT_SCHEMA: &str = "agentlab.blind_case_participant_bundle.v1";
const EVALUATOR_SCHEMA: &str = "agentlab.blind_case_evaluator_bundle.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_trusted_case_freeze.v1";
const REEXECUTION_WORKFLOW: &str =
    ".github/workflows/purchase-data-published-revision-reexecution.yml";
const CASE_REVIEW_WORKFLOW: &str = ".github/workflows/multi-repo-case-review.yml";
const FREEZE_WORKFLOW: &str = ".github/workflows/purchase-data-trusted-case-freeze.yml";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: &Path, label: &str, object: bool) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular non-symlink file"));
        }
        let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("cannot parse {label}: {error}"))?;
        if object && !value.is_object() {
            return Err(format!("{label} must be a JSON object"));
        }
        Ok(Self { bytes, value })
    }

    fn object(path: &Path, label: &str) -> Result<Self, String> {
        Self::load(path, label, true)
    }

    fn any_json(path: &Path, label: &str) -> Result<Self, String> {
        Self::load(path, label, false)
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

fn positive(value: &Value, key: &str, label: &str) -> Result<u64, String> {
    value[key]
        .as_u64()
        .filter(|item| *item > 0)
        .ok_or_else(|| format!("{label} {key} is invalid"))
}

fn exact_keys(value: &Value, expected: &[&str], label: &str) -> Result<(), String> {
    let actual = value
        .as_object()
        .ok_or_else(|| format!("{label} must be an object"))?
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(format!("{label} fields differ"));
    }
    Ok(())
}

fn safe_relative(value: &str, label: &str) -> Result<PathBuf, String> {
    let path = Path::new(value);
    if path.is_absolute()
        || value.contains('\\')
        || value
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(format!("{label} path is invalid"));
    }
    Ok(path.to_path_buf())
}

fn canonical_root(path: &Path, label: &str) -> Result<PathBuf, String> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular non-symlink directory"));
    }
    path.canonicalize()
        .map_err(|error| format!("cannot resolve {label}: {error}"))
}

fn regular_below(root: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let path = root.join(safe_relative(relative, label)?);
    let metadata =
        fs::symlink_metadata(&path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular non-symlink file"));
    }
    let resolved = path
        .canonicalize()
        .map_err(|error| format!("cannot resolve {label}: {error}"))?;
    if !resolved.starts_with(root) {
        return Err(format!("{label} leaves its trusted root"));
    }
    Ok(resolved)
}

fn collect_files(root: &Path, current: &Path, rows: &mut BTreeSet<String>) -> Result<(), String> {
    for entry in fs::read_dir(current).map_err(|error| format!("cannot list bundle: {error}"))? {
        let entry = entry.map_err(|error| format!("cannot inspect bundle entry: {error}"))?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect bundle path: {error}"))?;
        if metadata.file_type().is_symlink() {
            return Err(format!("bundle contains symlink: {}", path.display()));
        }
        if metadata.file_type().is_dir() {
            collect_files(root, &path, rows)?;
        } else if metadata.file_type().is_file() {
            let relative = path
                .strip_prefix(root)
                .map_err(|_| "bundle path escapes its root".to_owned())?
                .to_str()
                .ok_or_else(|| "bundle path is not UTF-8".to_owned())?
                .replace('\\', "/");
            rows.insert(relative);
        } else {
            return Err(format!(
                "bundle contains unsupported entry: {}",
                path.display()
            ));
        }
    }
    Ok(())
}

fn exact_files(root: &Path, label: &str) -> Result<BTreeSet<String>, String> {
    let root = canonical_root(root, label)?;
    let mut rows = BTreeSet::new();
    collect_files(&root, &root, &mut rows)?;
    Ok(rows)
}

fn validate_run(
    input: &Input,
    repository: &str,
    workflow: &str,
    label: &str,
) -> Result<(u64, u64, String), String> {
    same(
        string(&input.value["repository"], "full_name", label)?,
        repository,
        &format!("{label} repository"),
    )?;
    for (key, expected) in [
        ("path", workflow),
        ("event", "workflow_dispatch"),
        ("head_branch", "main"),
        ("status", "completed"),
        ("conclusion", "success"),
    ] {
        same(
            string(&input.value, key, label)?,
            expected,
            &format!("{label} {key}"),
        )?;
    }
    Ok((
        positive(&input.value, "id", label)?,
        positive(&input.value, "run_attempt", label)?,
        revision(&input.value, "head_sha", label)?.to_owned(),
    ))
}

fn validate_contract_reexecution(
    contract: &Input,
    reexecution: &Input,
) -> Result<(String, String, String, String, u64, u64), String> {
    same(
        string(&contract.value, "schema", "contract")?,
        CONTRACT_SCHEMA,
        "contract schema",
    )?;
    same(
        string(&contract.value, "status", "contract")?,
        "execution-contract-frozen-prerequisites-pending",
        "contract status",
    )?;
    exact_bool(&contract.value, "automaticPromotion", false, "contract")?;
    same(
        string(&reexecution.value, "schema", "re-execution")?,
        REEXECUTION_SCHEMA,
        "re-execution schema",
    )?;
    same(
        string(&reexecution.value, "status", "re-execution")?,
        "published-revision-semantic-ohostest-performance-passed",
        "re-execution status",
    )?;
    same(
        sha(&reexecution.value, "contractSha256", "re-execution")?,
        &contract.sha256(),
        "re-execution contract digest",
    )?;
    for key in [
        "semanticPassed",
        "ohosTestPassed",
        "performancePassed",
        "trustedMainRun",
    ] {
        exact_bool(&reexecution.value, key, true, "re-execution")?;
    }
    exact_bool(
        &reexecution.value,
        "allowsCaseContract",
        false,
        "re-execution",
    )?;
    exact_bool(
        &reexecution.value,
        "automaticPromotion",
        false,
        "re-execution",
    )?;
    same(
        string(&reexecution.value, "nextGate", "re-execution")?,
        "trusted-held-out-case-freeze",
        "re-execution next gate",
    )?;
    let workflow = &reexecution.value["workflow"];
    same(
        string(workflow, "path", "re-execution workflow")?,
        REEXECUTION_WORKFLOW,
        "re-execution workflow path",
    )?;
    same(
        string(workflow, "sourceRef", "re-execution workflow")?,
        "refs/heads/main",
        "re-execution workflow ref",
    )?;
    let run_id = positive(workflow, "runId", "re-execution workflow")?;
    let run_attempt = positive(workflow, "runAttempt", "re-execution workflow")?;
    if reexecution.value["runId"].as_u64() != Some(run_id)
        || reexecution.value["runAttempt"].as_u64() != Some(run_attempt)
    {
        return Err("re-execution workflow invocation differs".into());
    }
    Ok((
        string(&reexecution.value, "repository", "re-execution")?.to_owned(),
        revision(&reexecution.value, "publishedRevision", "re-execution")?.to_owned(),
        revision(&reexecution.value, "publishedTreeOid", "re-execution")?.to_owned(),
        sha(
            &reexecution.value,
            "semanticSourceSetSha256",
            "re-execution",
        )?
        .to_owned(),
        run_id,
        run_attempt,
    ))
}

fn validate_reexecution_provenance(
    reexecution: &Input,
    run: &Input,
    attestation: &Input,
    workflow_repository: &str,
    run_id: u64,
    run_attempt: u64,
) -> Result<(), String> {
    let (_, _, head) = validate_run(
        run,
        workflow_repository,
        REEXECUTION_WORKFLOW,
        "re-execution source run",
    )?;
    if run.value["id"].as_u64() != Some(run_id)
        || run.value["run_attempt"].as_u64() != Some(run_attempt)
    {
        return Err("re-execution source run invocation differs".into());
    }
    same(
        string(
            &reexecution.value["workflow"],
            "repository",
            "re-execution workflow",
        )?,
        workflow_repository,
        "re-execution workflow repository",
    )?;
    same(
        revision(
            &reexecution.value["workflow"],
            "sourceRevision",
            "re-execution workflow",
        )?,
        &head,
        "re-execution workflow source revision",
    )?;
    validate_github_actions_attestation(
        &attestation.value,
        &GitHubActionsAttestationIdentity {
            repository: workflow_repository,
            workflow_path: REEXECUTION_WORKFLOW,
            source_digest: &head,
            source_ref: "refs/heads/main",
            run_id,
            run_attempt,
            subject_sha256: &reexecution.sha256(),
        },
    )
}

#[derive(Clone)]
struct InventoryRow {
    path: String,
    role: String,
    sha256: String,
    bytes: u64,
}

fn inventory_json(rows: &[InventoryRow]) -> Value {
    Value::Array(
        rows.iter()
            .map(|row| {
                json!({
                    "path": row.path,
                    "role": row.role,
                    "sha256": row.sha256,
                    "bytes": row.bytes
                })
            })
            .collect(),
    )
}

fn inventory_digest(rows: &[InventoryRow]) -> Result<String, String> {
    let mut bytes = serde_json::to_vec(&inventory_json(rows)).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    Ok(digest(&bytes))
}

fn validate_inventory(
    root: &Path,
    value: &Value,
    roles: &[&str],
    label: &str,
) -> Result<Vec<InventoryRow>, String> {
    let values = value
        .as_array()
        .filter(|rows| !rows.is_empty())
        .ok_or_else(|| format!("{label} inventory is absent"))?;
    let mut seen = BTreeSet::new();
    let mut rows = Vec::new();
    for (index, value) in values.iter().enumerate() {
        exact_keys(value, &["path", "role", "sha256", "bytes"], label)?;
        let relative = string(value, "path", label)?;
        safe_relative(relative, label)?;
        if !seen.insert(relative.to_owned()) {
            return Err(format!("duplicate {label} path: {relative}"));
        }
        let role = string(value, "role", label)?;
        if !roles.contains(&role) {
            return Err(format!("unsupported {label} role at row {index}: {role}"));
        }
        let expected = sha(value, "sha256", label)?;
        let path = regular_below(root, relative, label)?;
        let bytes = fs::read(&path).map_err(|error| format!("cannot read {label}: {error}"))?;
        same(&digest(&bytes), expected, &format!("{label} file digest"))?;
        if value["bytes"].as_u64() != Some(bytes.len() as u64) {
            return Err(format!("{label} file byte length differs"));
        }
        rows.push(InventoryRow {
            path: relative.to_owned(),
            role: role.to_owned(),
            sha256: expected.to_owned(),
            bytes: bytes.len() as u64,
        });
    }
    rows.sort_by(|left, right| left.path.cmp(&right.path));
    let mut expected = rows
        .iter()
        .map(|row| row.path.clone())
        .collect::<BTreeSet<_>>();
    expected.insert("manifest.json".to_owned());
    if exact_files(root, label)? != expected {
        return Err(format!("{label} contains unbound files"));
    }
    Ok(rows)
}

struct FrozenCase {
    case: Input,
    cut: Input,
    participant_manifest: Input,
    evaluator_manifest: Input,
    source_set: String,
}

fn validate_case_review(
    root: &Path,
    run: &Input,
    workflow_repository: &str,
    published_repository: &str,
    published_revision: &str,
    semantic_source_set: &str,
) -> Result<(FrozenCase, u64, u64, String), String> {
    let root = canonical_root(root, "case-review root")?;
    let (run_id, run_attempt, head) = validate_run(
        run,
        workflow_repository,
        CASE_REVIEW_WORKFLOW,
        "case-review source run",
    )?;
    let case = Input::object(
        &regular_below(&root, "evaluation-case.json", "evaluation case")?,
        "evaluation case",
    )?;
    same(
        string(&case.value, "schema", "evaluation case")?,
        CASE_SCHEMA,
        "evaluation case schema",
    )?;
    same(
        string(&case.value, "status", "evaluation case")?,
        "frozen-calibrated",
        "evaluation case status",
    )?;
    exact_bool(&case.value, "automaticPromotion", false, "evaluation case")?;
    let source_set = sha(&case.value, "sourceSetSha256", "evaluation case")?.to_owned();
    same(
        &source_set,
        semantic_source_set,
        "evaluation case published semantic source set",
    )?;
    let sources = case.value["sources"]
        .as_array()
        .filter(|rows| rows.len() >= 2)
        .ok_or_else(|| "evaluation case requires multiple repositories".to_owned())?;
    let mut identities = BTreeSet::new();
    let mut published_matches = 0;
    for source in sources {
        let id = string(source, "id", "evaluation case source")?;
        let repository = string(source, "repository", "evaluation case source")?;
        let revision = revision(source, "revision", "evaluation case source")?;
        if !identities.insert(id.to_owned()) {
            return Err(format!("duplicate evaluation case source id: {id}"));
        }
        if repository == published_repository && revision == published_revision {
            published_matches += 1;
        }
    }
    if published_matches != 1 {
        return Err("evaluation case does not contain the exact published source once".into());
    }

    let blind_root = canonical_root(&root.join("blind-cut"), "blind cut root")?;
    let cut = Input::object(
        &regular_below(&blind_root, "cut-receipt.json", "blind cut receipt")?,
        "blind cut receipt",
    )?;
    let participant_root = canonical_root(&blind_root.join("participant"), "participant bundle")?;
    let evaluator_root = canonical_root(&blind_root.join("evaluator"), "evaluator bundle")?;
    let participant_manifest = Input::object(
        &regular_below(&participant_root, "manifest.json", "participant manifest")?,
        "participant manifest",
    )?;
    let evaluator_manifest = Input::object(
        &regular_below(&evaluator_root, "manifest.json", "evaluator manifest")?,
        "evaluator manifest",
    )?;
    same(
        string(&cut.value, "schema", "blind cut receipt")?,
        CUT_SCHEMA,
        "blind cut receipt schema",
    )?;
    same(
        string(
            &participant_manifest.value,
            "schema",
            "participant manifest",
        )?,
        PARTICIPANT_SCHEMA,
        "participant manifest schema",
    )?;
    same(
        string(&evaluator_manifest.value, "schema", "evaluator manifest")?,
        EVALUATOR_SCHEMA,
        "evaluator manifest schema",
    )?;
    exact_keys(
        &participant_manifest.value,
        &[
            "schema",
            "cutId",
            "caseId",
            "methodRevision",
            "sourceSetSha256",
            "files",
            "constraints",
        ],
        "participant manifest",
    )?;
    exact_keys(
        &evaluator_manifest.value,
        &[
            "schema",
            "cutId",
            "caseId",
            "methodRevision",
            "sourceSetSha256",
            "participantManifestSha256",
            "files",
        ],
        "evaluator manifest",
    )?;
    for key in ["cutId", "caseId", "methodRevision", "sourceSetSha256"] {
        let cut_value = string(&cut.value, key, "blind cut receipt")?;
        same(
            string(&participant_manifest.value, key, "participant manifest")?,
            cut_value,
            &format!("participant {key}"),
        )?;
        same(
            string(&evaluator_manifest.value, key, "evaluator manifest")?,
            cut_value,
            &format!("evaluator {key}"),
        )?;
    }
    same(
        string(&cut.value, "caseId", "blind cut receipt")?,
        string(&case.value, "id", "evaluation case")?,
        "blind cut case id",
    )?;
    same(
        revision(&cut.value, "methodRevision", "blind cut receipt")?,
        &head,
        "blind cut case-review method revision",
    )?;
    same(
        sha(&cut.value, "sourceSetSha256", "blind cut receipt")?,
        &source_set,
        "blind cut source set",
    )?;
    same(
        string(
            &cut.value["freshness"],
            "sourceVisibility",
            "blind cut freshness",
        )?,
        "held-out-public-revision",
        "blind cut source visibility",
    )?;
    for key in ["participantAccessBeforeCut", "modelTrainingExclusionKnown"] {
        exact_bool(&cut.value["freshness"], key, false, "blind cut freshness")?;
    }
    exact_bool(
        &cut.value["freshness"],
        "declaredHeldOutAtCut",
        true,
        "blind cut freshness",
    )?;
    exact_bool(
        &cut.value["freshness"],
        "eligibleForUnseenAgentDiscrimination",
        false,
        "blind cut freshness",
    )?;
    same(
        string(
            &cut.value["freshness"],
            "heldOutEvidenceStatus",
            "blind cut freshness",
        )?,
        "declaration-only",
        "blind cut held-out evidence status",
    )?;
    exact_bool(
        &cut.value["review"],
        "independent",
        false,
        "blind cut review",
    )?;
    exact_bool(&cut.value, "automaticPromotion", false, "blind cut receipt")?;
    exact_bool(
        &cut.value["boundary"],
        "physicallySeparatedRoots",
        true,
        "blind cut boundary",
    )?;
    exact_bool(
        &cut.value["boundary"],
        "participantManifestContainsEvaluatorInventory",
        false,
        "blind cut boundary",
    )?;
    exact_bool(
        &cut.value["boundary"],
        "byteIdenticalCrossBundleFiles",
        false,
        "blind cut boundary",
    )?;
    let participant = validate_inventory(
        &participant_root,
        &participant_manifest.value["files"],
        &["task", "source", "context", "constraint"],
        "participant bundle",
    )?;
    let evaluator = validate_inventory(
        &evaluator_root,
        &evaluator_manifest.value["files"],
        &["oracle", "reference", "preservation", "review", "analysis"],
        "evaluator bundle",
    )?;
    let mut expected_cut_files = BTreeSet::from(["cut-receipt.json".to_owned()]);
    expected_cut_files.extend(
        exact_files(&participant_root, "participant bundle")?
            .into_iter()
            .map(|path| format!("participant/{path}")),
    );
    expected_cut_files.extend(
        exact_files(&evaluator_root, "evaluator bundle")?
            .into_iter()
            .map(|path| format!("evaluator/{path}")),
    );
    if exact_files(&blind_root, "blind cut root")? != expected_cut_files {
        return Err("blind cut root contains files outside its bound bundles".into());
    }
    if participant.iter().filter(|row| row.role == "task").count() != 1
        || !evaluator.iter().any(|row| row.role == "oracle")
        || !evaluator.iter().any(|row| row.role == "reference")
    {
        return Err("blind cut required roles differ".into());
    }
    let participant_digests = participant
        .iter()
        .map(|row| row.sha256.as_str())
        .collect::<BTreeSet<_>>();
    if evaluator
        .iter()
        .any(|row| participant_digests.contains(row.sha256.as_str()))
    {
        return Err("participant and evaluator bundle bytes overlap".into());
    }
    same(
        sha(
            &cut.value["participantBundle"],
            "manifestSha256",
            "blind cut participant bundle",
        )?,
        &participant_manifest.sha256(),
        "blind cut participant manifest digest",
    )?;
    same(
        sha(
            &cut.value["participantBundle"],
            "inventorySha256",
            "blind cut participant bundle",
        )?,
        &inventory_digest(&participant)?,
        "blind cut participant inventory digest",
    )?;
    if cut.value["participantBundle"]["fileCount"].as_u64() != Some(participant.len() as u64) {
        return Err("blind cut participant file count differs".into());
    }
    same(
        sha(
            &cut.value["evaluatorBundle"],
            "manifestSha256",
            "blind cut evaluator bundle",
        )?,
        &evaluator_manifest.sha256(),
        "blind cut evaluator manifest digest",
    )?;
    same(
        sha(
            &cut.value["evaluatorBundle"],
            "inventorySha256",
            "blind cut evaluator bundle",
        )?,
        &inventory_digest(&evaluator)?,
        "blind cut evaluator inventory digest",
    )?;
    if cut.value["evaluatorBundle"]["fileCount"].as_u64() != Some(evaluator.len() as u64) {
        return Err("blind cut evaluator file count differs".into());
    }
    same(
        sha(
            &evaluator_manifest.value,
            "participantManifestSha256",
            "evaluator manifest",
        )?,
        &participant_manifest.sha256(),
        "evaluator participant-manifest binding",
    )?;
    let evaluator_case = evaluator
        .iter()
        .find(|row| row.path == "evaluation-case.json" && row.role == "review")
        .ok_or_else(|| "evaluator bundle lacks the frozen evaluation case".to_owned())?;
    same(
        &evaluator_case.sha256,
        &case.sha256(),
        "evaluator frozen case digest",
    )?;
    let evaluator_case_path = regular_below(
        &evaluator_root,
        "evaluation-case.json",
        "evaluator evaluation case",
    )?;
    let evaluator_case_input = Input::object(&evaluator_case_path, "evaluator evaluation case")?;
    same(
        &evaluator_case_input.sha256(),
        &case.sha256(),
        "case-review root evaluation case",
    )?;
    Ok((
        FrozenCase {
            case,
            cut,
            participant_manifest,
            evaluator_manifest,
            source_set,
        },
        run_id,
        run_attempt,
        head,
    ))
}

fn evidence(input: &Input) -> Value {
    json!({"sha256": input.sha256(), "byteLength": input.bytes.len()})
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

fn parse_positive(values: &BTreeMap<String, String>, key: &str) -> Result<u64, String> {
    value(values, key)?
        .parse::<u64>()
        .ok()
        .filter(|item| *item > 0)
        .ok_or_else(|| format!("{key} is not a positive integer"))
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

fn derive(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let contract = Input::object(&path(values, "--contract")?, "contract")?;
    let reexecution = Input::object(&path(values, "--reexecution")?, "re-execution")?;
    let reexecution_run = Input::object(
        &path(values, "--reexecution-source-run")?,
        "re-execution source run",
    )?;
    let reexecution_attestation = Input::any_json(
        &path(values, "--reexecution-attestation-verification")?,
        "re-execution attestation verification",
    )?;
    let case_review_run = Input::object(
        &path(values, "--case-review-source-run")?,
        "case-review source run",
    )?;
    let workflow_repository = value(values, "--workflow-repository")?;
    let workflow_source_revision = value(values, "--workflow-source-revision")?;
    if !valid_hex(workflow_source_revision, 40) {
        return Err("workflow source revision is not exact 40-hex".into());
    }
    let workflow_run_id = parse_positive(values, "--workflow-run-id")?;
    let workflow_run_attempt = parse_positive(values, "--workflow-run-attempt")?;
    let (repository, published, tree, semantic_source_set, reexecution_run_id, reexecution_attempt) =
        validate_contract_reexecution(&contract, &reexecution)?;
    validate_reexecution_provenance(
        &reexecution,
        &reexecution_run,
        &reexecution_attestation,
        workflow_repository,
        reexecution_run_id,
        reexecution_attempt,
    )?;
    let (frozen, case_review_run_id, case_review_attempt, case_review_revision) =
        validate_case_review(
            &path(values, "--case-review-root")?,
            &case_review_run,
            workflow_repository,
            &repository,
            &published,
            &semantic_source_set,
        )?;
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "trusted-held-out-case-frozen",
        "contractSha256": contract.sha256(),
        "reexecutionSha256": reexecution.sha256(),
        "publishedRevision": published,
        "publishedTreeOid": tree,
        "repository": repository,
        "sourceVisibility": "held-out-public-revision",
        "caseReviewRunId": case_review_run_id,
        "caseReviewRunAttempt": case_review_attempt,
        "caseReviewSourceRevision": case_review_revision,
        "evaluationCaseSha256": frozen.case.sha256(),
        "sourceSetSha256": frozen.source_set,
        "blindCutReceiptSha256": frozen.cut.sha256(),
        "participantManifestSha256": frozen.participant_manifest.sha256(),
        "evaluatorManifestSha256": frozen.evaluator_manifest.sha256(),
        "runId": workflow_run_id,
        "runAttempt": workflow_run_attempt,
        "trustedMainRun": true,
        "workflow": {
            "repository": workflow_repository,
            "path": FREEZE_WORKFLOW,
            "sourceRevision": workflow_source_revision,
            "sourceRef": "refs/heads/main",
            "runId": workflow_run_id,
            "runAttempt": workflow_run_attempt
        },
        "evidence": {
            "reexecutionSourceRun": evidence(&reexecution_run),
            "reexecutionAttestationVerification": evidence(&reexecution_attestation),
            "caseReviewSourceRun": evidence(&case_review_run),
            "evaluationCase": evidence(&frozen.case),
            "blindCutReceipt": evidence(&frozen.cut),
            "participantManifest": evidence(&frozen.participant_manifest),
            "evaluatorManifest": evidence(&frozen.evaluator_manifest)
        },
        "allowsCaseContract": true,
        "allowsUnseenAgentDispatch": false,
        "automaticPromotion": false,
        "nextGate": "pre-outcome-attested-unseen-agent-dispatch"
    }))
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
    fs::write(&output, bytes).map_err(|error| format!("cannot write output: {error}"))?;
    println!(
        "{}",
        serde_json::to_string(&json!({
            "ok": true,
            "schema": OUTPUT_SCHEMA,
            "output": output
        }))
        .map_err(|error| error.to_string())?
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("trusted case freeze invalid: {error}");
        std::process::exit(1);
    }
}
