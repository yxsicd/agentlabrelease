use agentlab_code_analysis::{
    digest, validate_github_actions_attestation, GitHubActionsAttestationIdentity,
};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

const CONTRACT_SCHEMA: &str = "agentlab.purchase_data_unseen_agent_cohort_contract.v1";
const PUBLICATION_SCHEMA: &str = "agentlab.purchase_data_exact_patch_publication.v1";
const SOURCE_SPEC_SCHEMA: &str = "agentlab.multi_repo_source_spec.v1";
const MANIFEST_SCHEMA: &str = "agentlab.multi_repo_manifest.v1";
const ANALYSIS_SCHEMA: &str = "agentlab.multi_repo_analysis.v1";
const ANALYSIS_RUN_SCHEMA: &str = "agentlab.multi_repo_analysis_run.v1";
const DIFFICULTY_SCHEMA: &str = "agentlab.difficulty_candidates.v2";
const RUNTIME_BUNDLE_SCHEMA: &str = "agentlab.purchase_data_published_revision_runtime_bundle.v1";
const SOURCE_TEST_SCHEMA: &str = "agentlab.harmony_source_standard_test_receipt.v1";
const BUILD_SCHEMA: &str = "agentlab.harmony_standard_test_source_build_receipt.v1";
const EXECUTION_SCHEMA: &str = "agentlab.harmony_standard_test_execution_receipt.v1";
const PERFORMANCE_SCHEMA: &str = "agentlab.purchase_data_case_performance_qualification.v1";
const OUTPUT_SCHEMA: &str = "agentlab.purchase_data_published_revision_reexecution.v1";
const PUBLICATION_WORKFLOW: &str = ".github/workflows/purchase-data-exact-patch-publication.yml";
const ANALYSIS_WORKFLOW: &str = ".github/workflows/multi-repo-analysis.yml";
const REEXECUTION_WORKFLOW: &str =
    ".github/workflows/purchase-data-published-revision-reexecution.yml";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: &Path, label: &str, object: bool) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
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
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| format!("cannot inspect {label} root: {error}"))?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(format!("{label} root must be a regular directory"));
    }
    path.canonicalize()
        .map_err(|error| format!("cannot resolve {label} root: {error}"))
}

fn regular_below(root: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let path = root.join(safe_relative(relative, label)?);
    let metadata =
        fs::symlink_metadata(&path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular file"));
    }
    let resolved = path
        .canonicalize()
        .map_err(|error| format!("cannot resolve {label}: {error}"))?;
    if !resolved.starts_with(root) {
        return Err(format!("{label} leaves its trusted root"));
    }
    Ok(resolved)
}

fn bound_input(root: &Path, binding: &Value, label: &str) -> Result<Input, String> {
    let path = regular_below(root, string(binding, "path", label)?, label)?;
    let input = Input::object(&path, label)?;
    same(
        &input.sha256(),
        sha(binding, "sha256", label)?,
        &format!("{label} digest"),
    )?;
    if binding["byteLength"].as_u64() != Some(input.bytes.len() as u64) {
        return Err(format!("{label} byte length differs"));
    }
    Ok(input)
}

fn fixed_input(root: &Path, relative: &str, label: &str) -> Result<Input, String> {
    Input::object(&regular_below(root, relative, label)?, label)
}

fn validate_contract_and_publication(
    contract: &Input,
    publication: &Input,
) -> Result<(String, String, String), String> {
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
        string(&publication.value, "schema", "publication")?,
        PUBLICATION_SCHEMA,
        "publication schema",
    )?;
    same(
        string(&publication.value, "status", "publication")?,
        "exact-reviewed-patch-published",
        "publication status",
    )?;
    same(
        sha(&publication.value, "contractSha256", "publication")?,
        &contract.sha256(),
        "publication contract digest",
    )?;
    same(
        revision(
            &publication.value,
            "reviewedCandidateRevision",
            "publication",
        )?,
        revision(
            &contract.value["sourceLineage"],
            "candidateRevision",
            "contract source lineage",
        )?,
        "publication reviewed candidate revision",
    )?;
    for key in [
        "publishedRevisionContainsExactReviewedPatch",
        "verifiedOnline",
    ] {
        exact_bool(&publication.value, key, true, "publication")?;
    }
    exact_bool(
        &publication.value,
        "automaticPromotion",
        false,
        "publication",
    )?;
    let repository = string(&publication.value, "repository", "publication")?.to_owned();
    let published = revision(&publication.value, "publishedRevision", "publication")?.to_owned();
    let tree = revision(&publication.value, "publishedTreeOid", "publication")?.to_owned();
    Ok((repository, published, tree))
}

fn validate_run(
    run: &Input,
    repository: &str,
    workflow: &str,
    label: &str,
) -> Result<(u64, u64, String), String> {
    same(
        string(&run.value["repository"], "full_name", label)?,
        repository,
        &format!("{label} repository"),
    )?;
    same(
        string(&run.value, "path", label)?,
        workflow,
        &format!("{label} workflow path"),
    )?;
    same(
        string(&run.value, "event", label)?,
        "workflow_dispatch",
        &format!("{label} event"),
    )?;
    same(
        string(&run.value, "head_branch", label)?,
        "main",
        &format!("{label} branch"),
    )?;
    same(
        string(&run.value, "status", label)?,
        "completed",
        &format!("{label} status"),
    )?;
    same(
        string(&run.value, "conclusion", label)?,
        "success",
        &format!("{label} conclusion"),
    )?;
    let head = revision(&run.value, "head_sha", label)?.to_owned();
    Ok((
        positive(&run.value, "id", label)?,
        positive(&run.value, "run_attempt", label)?,
        head,
    ))
}

fn validate_publication_attestation(
    publication: &Input,
    run: &Input,
    attestation: &Input,
    repository: &str,
) -> Result<(), String> {
    let (run_id, run_attempt, source_digest) = validate_run(
        run,
        repository,
        PUBLICATION_WORKFLOW,
        "publication source run",
    )?;
    validate_github_actions_attestation(
        &attestation.value,
        &GitHubActionsAttestationIdentity {
            repository,
            workflow_path: PUBLICATION_WORKFLOW,
            source_digest: &source_digest,
            source_ref: "refs/heads/main",
            run_id,
            run_attempt,
            subject_sha256: &publication.sha256(),
        },
    )
}

fn validate_semantic(
    root: &Path,
    source_run: &Input,
    workflow_repository: &str,
    source_repository: &str,
    published: &str,
) -> Result<(Input, Input, String, u64), String> {
    let (run_id, _, source_run_revision) = validate_run(
        source_run,
        workflow_repository,
        ANALYSIS_WORKFLOW,
        "semantic source run",
    )?;
    let spec = fixed_input(root, "source-spec.json", "semantic source specification")?;
    let manifest = fixed_input(root, "manifest.json", "semantic manifest")?;
    let analysis = fixed_input(
        root,
        "analysis/multi_repo_analysis.json",
        "semantic analysis receipt",
    )?;
    let difficulty = fixed_input(
        root,
        "analysis/difficulty_candidates.json",
        "semantic difficulty evidence",
    )?;
    let run = fixed_input(root, "analysis-run.json", "semantic analysis run")?;
    same(
        string(&spec.value, "schema", "semantic source specification")?,
        SOURCE_SPEC_SCHEMA,
        "semantic source specification schema",
    )?;
    exact_bool(
        &spec.value,
        "automaticPromotion",
        false,
        "semantic source specification",
    )?;
    let sources = spec.value["sources"]
        .as_array()
        .filter(|rows| !rows.is_empty())
        .ok_or_else(|| "semantic source specification has no sources".to_owned())?;
    let source_matches = sources.iter().filter(|row| {
        row["repository"].as_str() == Some(source_repository)
            && row["revision"].as_str() == Some(published)
    });
    if source_matches.count() != 1 {
        return Err(
            "semantic source specification does not bind the exact published source once".into(),
        );
    }
    same(
        string(&manifest.value, "schema", "semantic manifest")?,
        MANIFEST_SCHEMA,
        "semantic manifest schema",
    )?;
    let portable_manifest_sources = manifest.value["repositories"]
        .as_array()
        .ok_or_else(|| "semantic manifest repositories are absent".to_owned())?
        .iter()
        .map(|row| {
            json!({
                "id": row["id"],
                "repository": row["repository"],
                "revision": row["revision"]
            })
        })
        .collect::<Vec<_>>();
    if portable_manifest_sources != *sources
        || manifest.value["moduleBindings"] != spec.value["moduleBindings"]
    {
        return Err("semantic manifest source selection differs".into());
    }
    same(
        string(&analysis.value, "schema", "semantic analysis receipt")?,
        ANALYSIS_SCHEMA,
        "semantic analysis receipt schema",
    )?;
    exact_bool(
        &analysis.value,
        "automaticPromotion",
        false,
        "semantic analysis receipt",
    )?;
    same(
        sha(
            &analysis.value,
            "manifestSha256",
            "semantic analysis receipt",
        )?,
        &manifest.sha256(),
        "semantic analysis manifest digest",
    )?;
    if analysis.value["facts"]
        .as_u64()
        .filter(|count| *count > 0)
        .is_none()
    {
        return Err("semantic analysis contains no program facts".into());
    }
    same(
        string(&difficulty.value, "schema", "semantic difficulty evidence")?,
        DIFFICULTY_SCHEMA,
        "semantic difficulty evidence schema",
    )?;
    exact_bool(
        &difficulty.value,
        "automaticPromotion",
        false,
        "semantic difficulty evidence",
    )?;
    same(
        sha(
            &analysis.value,
            "difficultyCandidatesSha256",
            "semantic analysis receipt",
        )?,
        &difficulty.sha256(),
        "semantic difficulty evidence digest",
    )?;
    same(
        string(&run.value, "schema", "semantic analysis run")?,
        ANALYSIS_RUN_SCHEMA,
        "semantic analysis run schema",
    )?;
    exact_bool(
        &run.value,
        "automaticPromotion",
        false,
        "semantic analysis run",
    )?;
    same(
        revision(&run.value, "methodRevision", "semantic analysis run")?,
        &source_run_revision,
        "semantic analysis method revision",
    )?;
    same(
        sha(&run.value, "sourceSpecSha256", "semantic analysis run")?,
        &spec.sha256(),
        "semantic source specification digest",
    )?;
    same(
        sha(&run.value, "manifestSha256", "semantic analysis run")?,
        &manifest.sha256(),
        "semantic run manifest digest",
    )?;
    same(
        sha(&run.value, "analysisReceiptSha256", "semantic analysis run")?,
        &analysis.sha256(),
        "semantic analysis receipt digest",
    )?;
    same(
        sha(
            &run.value,
            "difficultyEvidenceSha256",
            "semantic analysis run",
        )?,
        &difficulty.sha256(),
        "semantic run difficulty digest",
    )?;
    let source_set = sha(
        &analysis.value,
        "sourceSetSha256",
        "semantic analysis receipt",
    )?
    .to_owned();
    same(
        sha(&run.value, "sourceSetSha256", "semantic analysis run")?,
        &source_set,
        "semantic analysis source set",
    )?;
    for (field, relative, label) in [
        (
            "programFactsSha256",
            "analysis/workspace_facts.jsonl",
            "semantic program facts",
        ),
        (
            "unsupportedSourcesSha256",
            "analysis/unsupported_sources.jsonl",
            "semantic unsupported sources",
        ),
    ] {
        let path = regular_below(root, relative, label)?;
        let file_sha =
            digest(&fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?);
        same(
            sha(&run.value, field, "semantic analysis run")?,
            &file_sha,
            &format!("{label} run digest"),
        )?;
        let receipt_field = match field {
            "programFactsSha256" => "workspaceFactsSha256",
            "unsupportedSourcesSha256" => "unsupportedSourcesSha256",
            _ => unreachable!(),
        };
        same(
            sha(&analysis.value, receipt_field, "semantic analysis receipt")?,
            &file_sha,
            &format!("{label} receipt digest"),
        )?;
    }
    Ok((run, analysis, source_set, run_id))
}

fn same_binding(left: &Value, right: &Value, label: &str) -> Result<(), String> {
    for key in ["sha256", "byteLength"] {
        if left[key] != right[key] {
            return Err(format!("{label} {key} differs"));
        }
    }
    Ok(())
}

fn validate_runtime(
    root: &Path,
    source_repository: &str,
    published: &str,
    tree: &str,
    expected_source_set: &str,
) -> Result<(Input, Input, Input, String), String> {
    let bundle = fixed_input(root, "bundle-manifest.json", "runtime bundle manifest")?;
    same(
        string(&bundle.value, "schema", "runtime bundle manifest")?,
        RUNTIME_BUNDLE_SCHEMA,
        "runtime bundle schema",
    )?;
    same(
        string(&bundle.value, "repository", "runtime bundle manifest")?,
        source_repository,
        "runtime bundle repository",
    )?;
    same(
        revision(
            &bundle.value,
            "publishedRevision",
            "runtime bundle manifest",
        )?,
        published,
        "runtime bundle published revision",
    )?;
    same(
        revision(&bundle.value, "publishedTreeOid", "runtime bundle manifest")?,
        tree,
        "runtime bundle published tree",
    )?;
    let source_set = sha(&bundle.value, "sourceSetSha256", "runtime bundle manifest")?;
    same(source_set, expected_source_set, "runtime bundle source set")?;
    exact_bool(
        &bundle.value,
        "automaticPromotion",
        false,
        "runtime bundle manifest",
    )?;
    let environment = string(
        &bundle.value,
        "environmentIdentity",
        "runtime bundle manifest",
    )?
    .to_owned();
    let source_test = bound_input(root, &bundle.value["ohosTestReceipt"], "OHOS Test receipt")?;
    same(
        string(&source_test.value, "schema", "OHOS Test receipt")?,
        SOURCE_TEST_SCHEMA,
        "OHOS Test receipt schema",
    )?;
    same(
        string(&source_test.value, "status", "OHOS Test receipt")?,
        "passed",
        "OHOS Test receipt status",
    )?;
    exact_bool(&source_test.value, "passed", true, "OHOS Test receipt")?;
    exact_bool(
        &source_test.value,
        "automaticPromotion",
        false,
        "OHOS Test receipt",
    )?;
    same(
        sha(&source_test.value, "sourceSetSha256", "OHOS Test receipt")?,
        source_set,
        "OHOS Test source set",
    )?;
    same(
        string(&source_test.value, "framework", "OHOS Test receipt")?,
        "instrument-test-ohosTest-hypium",
        "OHOS Test framework",
    )?;
    let receipt_path = regular_below(
        root,
        string(
            &bundle.value["ohosTestReceipt"],
            "path",
            "OHOS Test receipt",
        )?,
        "OHOS Test receipt",
    )?;
    let receipt_root = receipt_path
        .parent()
        .ok_or_else(|| "OHOS Test receipt has no parent".to_owned())?
        .canonicalize()
        .map_err(|error| format!("cannot resolve OHOS Test receipt parent: {error}"))?;
    let build = bound_input(
        &receipt_root,
        &source_test.value["buildReceipt"],
        "OHOS Test build receipt",
    )?;
    let execution = bound_input(
        &receipt_root,
        &source_test.value["executionReceipt"],
        "OHOS Test execution receipt",
    )?;
    for (input, schema, label) in [
        (&build, BUILD_SCHEMA, "OHOS Test build receipt"),
        (&execution, EXECUTION_SCHEMA, "OHOS Test execution receipt"),
    ] {
        same(
            string(&input.value, "schema", label)?,
            schema,
            &format!("{label} schema"),
        )?;
        same(
            string(&input.value, "status", label)?,
            "passed",
            &format!("{label} status"),
        )?;
        exact_bool(&input.value, "passed", true, label)?;
        exact_bool(&input.value, "automaticPromotion", false, label)?;
        same(
            sha(&input.value, "sourceSetSha256", label)?,
            source_set,
            &format!("{label} source set"),
        )?;
    }
    same(
        sha(&build.value, "projectTreeSha256", "OHOS Test build receipt")?,
        sha(
            &execution.value,
            "projectTreeSha256",
            "OHOS Test execution receipt",
        )?,
        "OHOS Test project tree",
    )?;
    for package in ["app", "test"] {
        same_binding(
            &source_test.value["packages"][package],
            &build.value["packages"][package],
            &format!("OHOS Test {package} package build binding"),
        )?;
        same_binding(
            &source_test.value["packages"][package],
            &execution.value["packages"][package],
            &format!("OHOS Test {package} package execution binding"),
        )?;
        let package_binding = &bundle.value["packages"][package];
        let package_path = regular_below(
            root,
            string(
                package_binding,
                "path",
                &format!("runtime {package} package"),
            )?,
            &format!("runtime {package} package"),
        )?;
        let package_bytes = fs::read(&package_path)
            .map_err(|error| format!("cannot read runtime {package} package: {error}"))?;
        same(
            sha(
                package_binding,
                "sha256",
                &format!("runtime {package} package"),
            )?,
            &digest(&package_bytes),
            &format!("runtime {package} package digest"),
        )?;
        if package_binding["byteLength"].as_u64() != Some(package_bytes.len() as u64) {
            return Err(format!("runtime {package} package byte length differs"));
        }
        same_binding(
            package_binding,
            &source_test.value["packages"][package],
            &format!("runtime {package} package receipt binding"),
        )?;
    }
    let performance = bound_input(
        root,
        &bundle.value["performanceQualification"],
        "performance qualification",
    )?;
    same(
        string(&performance.value, "schema", "performance qualification")?,
        PERFORMANCE_SCHEMA,
        "performance qualification schema",
    )?;
    same(
        string(&performance.value, "status", "performance qualification")?,
        "case-bound-reference-baseline-meaningful-wrong-performance-calibrated",
        "performance qualification status",
    )?;
    same(
        revision(
            &performance.value,
            "candidateRevision",
            "performance qualification",
        )?,
        published,
        "performance qualification revision",
    )?;
    same(
        string(
            &performance.value,
            "environmentIdentity",
            "performance qualification",
        )?,
        &environment,
        "performance environment",
    )?;
    for key in [
        "functionalMatrixVerified",
        "performanceMatrixVerified",
        "performanceCalibrated",
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
    ] {
        exact_bool(&performance.value, key, true, "performance qualification")?;
    }
    exact_bool(
        &performance.value,
        "automaticPromotion",
        false,
        "performance qualification",
    )?;
    for (key, minimum) in [
        ("roleCount", 3),
        ("coldRunCount", 6),
        ("functionalVerdictCount", 1),
        ("profileSampleCount", 1),
    ] {
        if performance.value["coverage"][key]
            .as_u64()
            .filter(|value| *value >= minimum)
            .is_none()
        {
            return Err(format!(
                "performance qualification coverage {key} is insufficient"
            ));
        }
    }
    Ok((bundle, source_test, performance, environment))
}

fn evidence(input: &Input) -> Value {
    json!({"sha256": input.sha256(), "byteLength": input.bytes.len()})
}

fn derive(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let contract = Input::object(&path(values, "--contract")?, "contract")?;
    let publication = Input::object(&path(values, "--publication")?, "publication")?;
    let publication_run = Input::object(
        &path(values, "--publication-source-run")?,
        "publication source run",
    )?;
    let publication_attestation = Input::any_json(
        &path(values, "--publication-attestation-verification")?,
        "publication attestation verification",
    )?;
    let semantic_run = Input::object(
        &path(values, "--semantic-source-run")?,
        "semantic source run",
    )?;
    let workflow_repository = value(values, "--workflow-repository")?;
    let workflow_source_revision = value(values, "--workflow-source-revision")?;
    if !valid_hex(workflow_source_revision, 40) {
        return Err("workflow source revision is not exact 40-hex".into());
    }
    let workflow_run_id = parse_positive(values, "--workflow-run-id")?;
    let workflow_run_attempt = parse_positive(values, "--workflow-run-attempt")?;
    let runtime_archive_sha256 = value(values, "--runtime-archive-sha256")?;
    if !valid_hex(runtime_archive_sha256, 64) {
        return Err("runtime archive digest is not lowercase SHA-256".into());
    }
    let (source_repository, published, tree) =
        validate_contract_and_publication(&contract, &publication)?;
    validate_publication_attestation(
        &publication,
        &publication_run,
        &publication_attestation,
        workflow_repository,
    )?;
    same(
        &source_repository,
        string(&publication.value, "repository", "publication")?,
        "publication repository",
    )?;
    let semantic_root = canonical_root(&path(values, "--semantic-root")?, "semantic")?;
    let (analysis_run, analysis_receipt, semantic_source_set, semantic_run_id) = validate_semantic(
        &semantic_root,
        &semantic_run,
        workflow_repository,
        &source_repository,
        &published,
    )?;
    let runtime_root = canonical_root(&path(values, "--runtime-root")?, "runtime")?;
    let expected_runtime_source_set = sha(
        &contract.value["sourceLineage"],
        "runtimeSourceSetSha256",
        "contract source lineage",
    )?;
    let (runtime_bundle, ohos_test, performance, environment) = validate_runtime(
        &runtime_root,
        &source_repository,
        &published,
        &tree,
        expected_runtime_source_set,
    )?;
    Ok(json!({
        "schema": OUTPUT_SCHEMA,
        "status": "published-revision-semantic-ohostest-performance-passed",
        "contractSha256": contract.sha256(),
        "publicationSha256": publication.sha256(),
        "publishedRevision": published,
        "publishedTreeOid": tree,
        "repository": source_repository,
        "semanticPassed": true,
        "ohosTestPassed": true,
        "performancePassed": true,
        "semanticSourceSetSha256": semantic_source_set,
        "runtimeSourceSetSha256": expected_runtime_source_set,
        "environmentIdentity": environment,
        "semanticEvidenceSha256": analysis_run.sha256(),
        "ohosTestEvidenceSha256": ohos_test.sha256(),
        "performanceEvidenceSha256": performance.sha256(),
        "runtimeArchiveSha256": runtime_archive_sha256,
        "semanticAnalysisRunId": semantic_run_id,
        "runId": workflow_run_id,
        "runAttempt": workflow_run_attempt,
        "trustedMainRun": true,
        "workflow": {
            "repository": workflow_repository,
            "path": REEXECUTION_WORKFLOW,
            "sourceRevision": workflow_source_revision,
            "sourceRef": "refs/heads/main",
            "runId": workflow_run_id,
            "runAttempt": workflow_run_attempt
        },
        "evidence": {
            "publicationSourceRun": evidence(&publication_run),
            "publicationAttestationVerification": evidence(&publication_attestation),
            "semanticSourceRun": evidence(&semantic_run),
            "semanticAnalysisRun": evidence(&analysis_run),
            "semanticAnalysisReceipt": evidence(&analysis_receipt),
            "runtimeBundleManifest": evidence(&runtime_bundle),
            "ohosTestReceipt": evidence(&ohos_test),
            "performanceQualification": evidence(&performance)
        },
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "nextGate": "trusted-held-out-case-freeze"
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

fn parse_positive(values: &BTreeMap<String, String>, key: &str) -> Result<u64, String> {
    value(values, key)?
        .parse::<u64>()
        .ok()
        .filter(|item| *item > 0)
        .ok_or_else(|| format!("{key} is invalid"))
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
        eprintln!("purchase-data published-revision re-execution invalid: {error}");
        std::process::exit(1);
    }
}
