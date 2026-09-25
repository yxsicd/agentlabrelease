use agentlab_code_analysis::{analyze, digest, GRAMMAR, GRAMMAR_DIGEST};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};

#[derive(Clone)]
struct Repository {
    id: String,
    source: String,
    root: PathBuf,
    revision: String,
    files: BTreeSet<String>,
}

#[derive(Clone)]
struct Binding {
    repository_id: String,
    path: String,
}

fn fail(message: impl Into<String>) -> Box<dyn std::error::Error> {
    message.into().into()
}

fn git(root: &Path, args: &[&str]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let result = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()?;
    if !result.status.success() {
        return Err(fail(format!(
            "git {} failed for {}: {}",
            args.join(" "),
            root.display(),
            String::from_utf8_lossy(&result.stderr).trim()
        )));
    }
    Ok(result.stdout)
}

fn supports_nul_batch_input(root: &Path) -> bool {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["cat-file", "--batch", "-z"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn git_batch_blobs(
    repository: &Repository,
    paths: &[String],
    nul_input: bool,
) -> Result<BTreeMap<String, Vec<u8>>, Box<dyn std::error::Error>> {
    if paths.is_empty() {
        return Ok(BTreeMap::new());
    }
    let mut child = Command::new("git")
        .arg("-C")
        .arg(&repository.root)
        .args(if nul_input {
            &["cat-file", "--batch", "-z"][..]
        } else {
            &["cat-file", "--batch"][..]
        })
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| fail("missing git stdin"))?;
    let revision = repository.revision.clone();
    let query_paths = paths.to_vec();
    let writer = std::thread::spawn(move || -> std::io::Result<()> {
        let delimiter = if nul_input { b'\0' } else { b'\n' };
        for path in &query_paths {
            stdin.write_all(format!("{revision}:{path}").as_bytes())?;
            stdin.write_all(&[delimiter])?;
        }
        Ok(())
    });
    let mut stdout = BufReader::new(
        child
            .stdout
            .take()
            .ok_or_else(|| fail("missing git stdout"))?,
    );
    let mut blobs = BTreeMap::new();
    for path in paths {
        let mut header = Vec::new();
        stdout.read_until(b'\n', &mut header)?;
        if header.pop() != Some(b'\n') {
            return Err(fail(format!("unterminated git cat-file header for {path}")));
        }
        let header = std::str::from_utf8(&header)?;
        let parts = header.split_whitespace().collect::<Vec<_>>();
        if parts.len() != 3 || parts[1] != "blob" {
            return Err(fail(format!(
                "unexpected git cat-file header for {path}: {header}"
            )));
        }
        let size = parts[2].parse::<usize>()?;
        let mut bytes = vec![0; size];
        stdout.read_exact(&mut bytes)?;
        let mut delimiter = [0];
        stdout.read_exact(&mut delimiter)?;
        if delimiter != [b'\n'] {
            return Err(fail(format!("unterminated git blob for {path}")));
        }
        blobs.insert(path.clone(), bytes);
    }
    writer
        .join()
        .map_err(|_| fail("git cat-file input writer panicked"))??;
    let status = child.wait()?;
    if !status.success() {
        let mut stderr = Vec::new();
        child
            .stderr
            .take()
            .ok_or_else(|| fail("missing git stderr"))?
            .read_to_end(&mut stderr)?;
        return Err(fail(format!(
            "git cat-file --batch failed for {}: {}",
            repository.root.display(),
            String::from_utf8_lossy(&stderr).trim()
        )));
    }
    Ok(blobs)
}

fn git_blobs(
    repository: &Repository,
    paths: &[String],
) -> Result<BTreeMap<String, Vec<u8>>, Box<dyn std::error::Error>> {
    if supports_nul_batch_input(&repository.root) {
        return git_batch_blobs(repository, paths, true);
    }

    // Git before the `cat-file --batch -z` option accepts only line-delimited
    // queries. Batch ordinary paths and read newline-containing paths through
    // an argv-bound single-object query so no path byte is interpreted as a
    // protocol delimiter.
    let ordinary_paths = paths
        .iter()
        .filter(|path| !path.contains('\n'))
        .cloned()
        .collect::<Vec<_>>();
    let mut blobs = git_batch_blobs(repository, &ordinary_paths, false)?;
    for path in paths.iter().filter(|path| path.contains('\n')) {
        let object = format!("{}:{path}", repository.revision);
        let bytes = git(&repository.root, &["cat-file", "blob", &object])?;
        blobs.insert(path.clone(), bytes);
    }
    Ok(blobs)
}

fn exact_revision(value: &Value, label: &str) -> Result<String, Box<dyn std::error::Error>> {
    let revision = value
        .as_str()
        .ok_or_else(|| fail(format!("{label} must be a 40-character Git revision")))?;
    if revision.len() != 40 || !revision.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(fail(format!("{label} must be a 40-character Git revision")));
    }
    Ok(revision.to_ascii_lowercase())
}

fn required_string(value: &Value, key: &str) -> Result<String, Box<dyn std::error::Error>> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| fail(format!("missing non-empty {key}")))
}

fn normalize(path: &Path) -> Option<String> {
    let mut parts = Vec::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::Normal(part) => parts.push(part.to_str()?.to_owned()),
            Component::ParentDir => {
                parts.pop()?;
            }
            _ => return None,
        }
    }
    Some(parts.join("/"))
}

fn resolve_relative(repository: &Repository, importer: &str, specifier: &str) -> Option<String> {
    let base = Path::new(importer)
        .parent()
        .unwrap_or_else(|| Path::new(""))
        .join(specifier);
    let normalized = normalize(&base)?;
    let mut candidates = vec![normalized.clone()];
    if Path::new(&normalized).extension().is_none() {
        candidates.extend([
            format!("{normalized}.ets"),
            format!("{normalized}.ts"),
            format!("{normalized}/index.ets"),
            format!("{normalized}/index.ts"),
        ]);
    }
    candidates
        .into_iter()
        .find(|candidate| repository.files.contains(candidate))
}

fn stable_id(prefix: &str, parts: &[&str]) -> String {
    let joined = parts.join("\0");
    format!("{prefix}-{}", &digest(joined.as_bytes())[..24])
}

fn write_jsonl(path: &Path, rows: &[Value]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    for row in rows {
        serde_json::to_writer(&mut bytes, row)?;
        bytes.push(b'\n');
    }
    let mut output = BufWriter::new(File::create(path)?);
    output.write_all(&bytes)?;
    output.flush()?;
    Ok(bytes)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err(fail(
            "Usage: agentlab-multi-repo-analysis <manifest.json> <output-directory>",
        ));
    }
    let manifest_path = PathBuf::from(&args[0]);
    let output = PathBuf::from(&args[1]);
    let manifest_bytes = fs::read(&manifest_path)?;
    let manifest: Value = serde_json::from_slice(&manifest_bytes)?;
    if manifest.get("schema").and_then(Value::as_str) != Some("agentlab.multi_repo_manifest.v1") {
        return Err(fail("unsupported multi-repository manifest schema"));
    }
    let entries = manifest
        .get("repositories")
        .and_then(Value::as_array)
        .filter(|entries| entries.len() >= 2)
        .ok_or_else(|| fail("multi-repository analysis requires at least two repositories"))?;
    let mut repositories = BTreeMap::new();
    for entry in entries {
        let id = required_string(entry, "id")?;
        if repositories.contains_key(&id) {
            return Err(fail(format!("duplicate repository id {id}")));
        }
        let root = PathBuf::from(required_string(entry, "root")?);
        let source = required_string(entry, "repository")?;
        let revision = exact_revision(
            entry.get("revision").unwrap_or(&Value::Null),
            &format!("repository {id} revision"),
        )?;
        let object = format!("{revision}^{{commit}}");
        git(&root, &["cat-file", "-e", &object])?;
        let names = git(&root, &["ls-tree", "-r", "--name-only", "-z", &revision])?;
        let files = names
            .split(|byte| *byte == 0)
            .filter(|raw| !raw.is_empty())
            .map(|raw| std::str::from_utf8(raw).map(str::to_owned))
            .collect::<Result<BTreeSet<_>, _>>()?;
        repositories.insert(
            id.clone(),
            Repository {
                id,
                source,
                root,
                revision,
                files,
            },
        );
    }

    let mut bindings = BTreeMap::new();
    if let Some(binding_rows) = manifest.get("moduleBindings").and_then(Value::as_object) {
        for (specifier, value) in binding_rows {
            let repository_id = required_string(value, "repositoryId")?;
            let path = required_string(value, "path")?;
            let repository = repositories.get(&repository_id).ok_or_else(|| {
                fail(format!(
                    "binding {specifier} names unknown repository {repository_id}"
                ))
            })?;
            if !repository.files.contains(&path) {
                return Err(fail(format!(
                    "binding {specifier} target {repository_id}:{path} is absent at pinned revision"
                )));
            }
            if !(path.ends_with(".ets") || path.ends_with(".ts")) {
                return Err(fail(format!(
                    "binding {specifier} target {repository_id}:{path} is not an ArkTS/TypeScript source"
                )));
            }
            bindings.insert(
                specifier.clone(),
                Binding {
                    repository_id,
                    path,
                },
            );
        }
    }

    let mut facts = Vec::new();
    let mut module_facts = Vec::new();
    let mut repository_receipts = Vec::new();
    let mut unsupported_sources = Vec::new();
    for repository in repositories.values() {
        let source_paths = repository
            .files
            .iter()
            .filter(|path| path.ends_with(".ets") || path.ends_with(".ts"))
            .cloned()
            .collect::<Vec<_>>();
        let source_blobs = git_blobs(repository, &source_paths)?;
        let mut source_file_candidate_count = 0usize;
        let mut file_count = 0usize;
        let mut syntax_error_count = 0usize;
        let mut fact_count = 0usize;
        for path in &source_paths {
            source_file_candidate_count += 1;
            let bytes = &source_blobs[path];
            if let Err(error) = std::str::from_utf8(&bytes) {
                unsupported_sources.push(json!({
                    "schema":"agentlab.unsupported_source.v1",
                    "repositoryId":repository.id,
                    "path":path,
                    "sourceIdentity":format!("git:{}@{}",repository.source,repository.revision),
                    "sha256":digest(&bytes),
                    "byteLength":bytes.len(),
                    "reason":"non-utf8-source",
                    "invalidUtf8AtByte":error.valid_up_to()
                }));
                continue;
            }
            let analysis = analyze(path, &bytes, &repository.revision)?;
            file_count += 1;
            syntax_error_count += usize::from(analysis.has_errors);
            for mut row in analysis.rows {
                let local_id = required_string(&row, "id")?;
                let global_id = stable_id("workspace-fact", &[&repository.id, &local_id]);
                let object = row.as_object_mut().unwrap();
                object.insert("id".into(), json!(global_id));
                object.insert("localFactId".into(), json!(local_id));
                object.insert("repositoryId".into(), json!(repository.id));
                object.insert(
                    "sourceIdentity".into(),
                    json!(format!("git:{}@{}", repository.source, repository.revision)),
                );
                if object.get("kind").and_then(Value::as_str) == Some("module-reference") {
                    module_facts.push(facts.len());
                }
                facts.push(row);
                fact_count += 1;
            }
        }
        repository_receipts.push(json!({
            "id":repository.id,
            "repository":repository.source,
            "revision":repository.revision,
            "sourceIdentity":format!("git:{}@{}",repository.source,repository.revision),
            "sourceFileCandidates":source_file_candidate_count,
            "files":file_count,
            "unsupportedSources":source_file_candidate_count-file_count,
            "filesWithSyntaxErrors":syntax_error_count,
            "facts":fact_count
        }));
    }

    let file_index: BTreeMap<(String, String), String> = facts
        .iter()
        .filter(|row| row.get("kind").and_then(Value::as_str) == Some("parse-file"))
        .map(|row| {
            (
                (
                    row["repositoryId"].as_str().unwrap().to_owned(),
                    row["path"].as_str().unwrap().to_owned(),
                ),
                row["id"].as_str().unwrap().to_owned(),
            )
        })
        .collect();
    let mut edges = Vec::new();
    for index in module_facts {
        let repository_id = facts[index]["repositoryId"].as_str().unwrap().to_owned();
        let importer = facts[index]["path"].as_str().unwrap().to_owned();
        let specifier = facts[index]["specifier"].as_str().unwrap().to_owned();
        let (resolved, unresolved_reason) = if specifier.starts_with('.') {
            match resolve_relative(&repositories[&repository_id], &importer, &specifier) {
                Some(path) if file_index.contains_key(&(repository_id.clone(), path.clone())) => (
                    Some((repository_id.clone(), path, "relative-file")),
                    "relative-target-absent-at-pinned-revision",
                ),
                Some(_) => (None, "relative-target-unsupported-source"),
                None => (None, "relative-target-absent-at-pinned-revision"),
            }
        } else {
            match bindings.get(&specifier) {
                Some(binding)
                    if file_index
                        .contains_key(&(binding.repository_id.clone(), binding.path.clone())) =>
                {
                    (
                        Some((
                            binding.repository_id.clone(),
                            binding.path.clone(),
                            "explicit-manifest-binding",
                        )),
                        "external-or-unbound-module",
                    )
                }
                Some(_) => (None, "bound-target-unsupported-source"),
                None => (None, "external-or-unbound-module"),
            }
        };
        let object = facts[index].as_object_mut().unwrap();
        if let Some((target_repository, target_path, method)) = resolved {
            let target_fact_id = file_index
                .get(&(target_repository.clone(), target_path.clone()))
                .ok_or_else(|| fail("resolved module target has no parse-file fact"))?
                .clone();
            object.insert("resolution".into(), json!("resolved"));
            object.insert("resolutionMethod".into(), json!(method));
            object.insert("targetRepositoryId".into(), json!(target_repository));
            object.insert("targetPath".into(), json!(target_path));
            object.insert("targetFactId".into(), json!(target_fact_id));
            let source_fact_id = object["id"].as_str().unwrap();
            let target_repository = object["targetRepositoryId"].as_str().unwrap();
            let target_path = object["targetPath"].as_str().unwrap();
            let source_identity = format!(
                "git:{}@{}",
                repositories[&repository_id].source, repositories[&repository_id].revision
            );
            let target_identity = format!(
                "git:{}@{}",
                repositories[target_repository].source, repositories[target_repository].revision
            );
            edges.push(json!({
                "id":stable_id("module-edge", &[source_fact_id,target_repository,target_path]),
                "kind":"module-dependency",
                "sourceFactId":source_fact_id,
                "sourceRepositoryId":repository_id,
                "sourcePath":importer,
                "sourceIdentity":source_identity,
                "targetFactId":object["targetFactId"],
                "targetRepositoryId":target_repository,
                "targetPath":target_path,
                "targetIdentity":target_identity,
                "specifier":specifier,
                "resolutionMethod":method
            }));
        } else {
            object.insert("resolution".into(), json!("unresolved"));
            object.insert("resolutionReason".into(), json!(unresolved_reason));
        }
    }
    edges.sort_by_key(|row| row["id"].as_str().unwrap().to_owned());

    let mut reverse: BTreeMap<(String, String), Vec<(String, String, String)>> = BTreeMap::new();
    for edge in &edges {
        reverse
            .entry((
                edge["targetRepositoryId"].as_str().unwrap().to_owned(),
                edge["targetPath"].as_str().unwrap().to_owned(),
            ))
            .or_default()
            .push((
                edge["sourceRepositoryId"].as_str().unwrap().to_owned(),
                edge["sourcePath"].as_str().unwrap().to_owned(),
                edge["id"].as_str().unwrap().to_owned(),
            ));
    }
    for dependents in reverse.values_mut() {
        dependents.sort();
    }
    let cross_targets: BTreeSet<(String, String)> = edges
        .iter()
        .filter(|edge| edge["sourceRepositoryId"] != edge["targetRepositoryId"])
        .map(|edge| {
            (
                edge["targetRepositoryId"].as_str().unwrap().to_owned(),
                edge["targetPath"].as_str().unwrap().to_owned(),
            )
        })
        .collect();
    let mut candidates = Vec::new();
    for seed in cross_targets {
        let mut queue = VecDeque::from([(seed.clone(), 0usize)]);
        let mut visited = BTreeMap::from([(seed.clone(), 0usize)]);
        let mut evidence = BTreeSet::new();
        while let Some((node, depth)) = queue.pop_front() {
            for (repository_id, path, edge_id) in reverse.get(&node).into_iter().flatten() {
                evidence.insert(edge_id.clone());
                let dependent = (repository_id.clone(), path.clone());
                if !visited.contains_key(&dependent) {
                    visited.insert(dependent.clone(), depth + 1);
                    queue.push_back((dependent, depth + 1));
                }
            }
        }
        let affected: Vec<Value> = visited
            .iter()
            .map(|((repository_id, path), depth)| {
                json!({"repositoryId":repository_id,"path":path,"dependencyDepth":depth})
            })
            .collect();
        let repository_count = visited
            .keys()
            .map(|(repository_id, _)| repository_id)
            .collect::<BTreeSet<_>>()
            .len();
        let max_depth = visited.values().copied().max().unwrap_or(0);
        candidates.push(json!({
            "id":stable_id("difficulty", &["cross-repository-impact",&seed.0,&seed.1]),
            "schema":"agentlab.difficulty_point.v1",
            "dimensionId":"multi-repository-change-impact",
            "primaryDimension":"program-analysis",
            "mechanism":"recursive reverse dependency closure crosses repository boundaries",
            "status":"candidate",
            "maturityState":"candidate",
            "seed":{"repositoryId":seed.0,"path":seed.1},
            "affectedFiles":affected,
            "affectedRepositoryCount":repository_count,
            "maxDependencyDepth":max_depth,
            "evidenceIds":evidence,
            "verificationContract":{
                "caseReady":false,
                "required":["exact repository revisions","repository-specific build checks","behavior oracle covering affected boundary"]
            },
            "automaticPromotion":false
        }));
    }
    let mut shared_external_modules: BTreeMap<String, Vec<(String, String, String)>> =
        BTreeMap::new();
    for row in facts.iter().filter(|row| {
        row.get("kind").and_then(Value::as_str) == Some("module-reference")
            && row.get("resolution").and_then(Value::as_str) == Some("unresolved")
            && row
                .get("specifier")
                .and_then(Value::as_str)
                .is_some_and(|specifier| !specifier.starts_with('.'))
    }) {
        shared_external_modules
            .entry(row["specifier"].as_str().unwrap().to_owned())
            .or_default()
            .push((
                row["repositoryId"].as_str().unwrap().to_owned(),
                row["path"].as_str().unwrap().to_owned(),
                row["id"].as_str().unwrap().to_owned(),
            ));
    }
    let mut shared_external_module_count = 0usize;
    for (specifier, mut observations) in shared_external_modules {
        observations.sort();
        observations.dedup();
        let affected_repositories = observations
            .iter()
            .map(|(repository_id, _, _)| repository_id)
            .collect::<BTreeSet<_>>();
        if affected_repositories.len() < 2 {
            continue;
        }
        shared_external_module_count += 1;
        let affected = observations
            .iter()
            .map(|(repository_id, path, _)| (repository_id, path))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .map(|(repository_id, path)| {
                json!({"repositoryId":repository_id,"path":path,"dependencyDepth":1})
            })
            .collect::<Vec<_>>();
        let evidence = observations
            .iter()
            .map(|(_, _, fact_id)| fact_id)
            .collect::<Vec<_>>();
        candidates.push(json!({
            "id":stable_id("difficulty", &["shared-external-module-contract",&specifier]),
            "schema":"agentlab.difficulty_point.v1",
            "dimensionId":"multi-repository-change-impact",
            "primaryDimension":"program-analysis",
            "relationType":"shared-external-module-contract",
            "mechanism":"shared unresolved external module contract spans repository boundaries",
            "status":"candidate",
            "maturityState":"candidate",
            "seed":{"specifier":specifier},
            "affectedFiles":affected,
            "affectedRepositoryCount":affected_repositories.len(),
            "maxDependencyDepth":1,
            "evidenceIds":evidence,
            "verificationContract":{
                "caseReady":false,
                "required":[
                    "external module contract version and semantics",
                    "repository-specific build checks",
                    "cross-repository behavior oracle"
                ]
            },
            "automaticPromotion":false
        }));
    }
    let mut calls_by_file: BTreeMap<(String, String), Vec<(String, String)>> = BTreeMap::new();
    for row in facts
        .iter()
        .filter(|row| row.get("kind").and_then(Value::as_str) == Some("call"))
    {
        calls_by_file
            .entry((
                row["repositoryId"].as_str().unwrap().to_owned(),
                row["path"].as_str().unwrap().to_owned(),
            ))
            .or_default()
            .push((
                row["targetExpression"].as_str().unwrap().to_owned(),
                row["id"].as_str().unwrap().to_owned(),
            ));
    }
    let mut shared_external_api_calls: BTreeMap<
        (String, String, String),
        Vec<(String, String, String, String)>,
    > = BTreeMap::new();
    for row in facts.iter().filter(|row| {
        row.get("kind").and_then(Value::as_str) == Some("module-reference")
            && row.get("resolution").and_then(Value::as_str) == Some("unresolved")
            && row
                .get("specifier")
                .and_then(Value::as_str)
                .is_some_and(|specifier| !specifier.starts_with('.'))
    }) {
        let repository_id = row["repositoryId"].as_str().unwrap();
        let path = row["path"].as_str().unwrap();
        let module_fact_id = row["id"].as_str().unwrap();
        let Some(bindings) = row.get("importedBindings").and_then(Value::as_array) else {
            continue;
        };
        for binding in bindings {
            let Some(exported) = binding.get("exported").and_then(Value::as_str) else {
                continue;
            };
            let Some(local) = binding.get("local").and_then(Value::as_str) else {
                continue;
            };
            for (target, call_fact_id) in calls_by_file
                .get(&(repository_id.to_owned(), path.to_owned()))
                .into_iter()
                .flatten()
            {
                let normalized_target = if target == local {
                    Some(exported.to_owned())
                } else {
                    target.strip_prefix(&format!("{local}.")).map(|suffix| {
                        if exported == "*" {
                            suffix.to_owned()
                        } else {
                            format!("{exported}.{suffix}")
                        }
                    })
                };
                let Some(normalized_target) = normalized_target else {
                    continue;
                };
                shared_external_api_calls
                    .entry((
                        row["specifier"].as_str().unwrap().to_owned(),
                        exported.to_owned(),
                        normalized_target,
                    ))
                    .or_default()
                    .push((
                        repository_id.to_owned(),
                        path.to_owned(),
                        module_fact_id.to_owned(),
                        call_fact_id.to_owned(),
                    ));
            }
        }
    }
    let mut shared_external_api_call_count = 0usize;
    for ((specifier, exported_symbol, call_target), mut observations) in shared_external_api_calls {
        observations.sort();
        observations.dedup();
        let affected_repositories = observations
            .iter()
            .map(|(repository_id, _, _, _)| repository_id)
            .collect::<BTreeSet<_>>();
        if affected_repositories.len() < 2 {
            continue;
        }
        shared_external_api_call_count += 1;
        let affected = observations
            .iter()
            .map(|(repository_id, path, _, _)| (repository_id, path))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .map(|(repository_id, path)| {
                json!({"repositoryId":repository_id,"path":path,"dependencyDepth":1})
            })
            .collect::<Vec<_>>();
        let evidence = observations
            .iter()
            .flat_map(|(_, _, module_fact_id, call_fact_id)| [module_fact_id, call_fact_id])
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        candidates.push(json!({
            "id":stable_id("difficulty", &["shared-external-api-call-contract",&specifier,&exported_symbol,&call_target]),
            "schema":"agentlab.difficulty_point.v1",
            "dimensionId":"multi-repository-change-impact",
            "primaryDimension":"program-analysis",
            "relationType":"shared-external-api-call-contract",
            "mechanism":"same external API call target is observed across repository boundaries",
            "status":"candidate",
            "maturityState":"candidate",
            "seed":{
                "specifier":specifier,
                "exportedSymbol":exported_symbol,
                "callTarget":call_target
            },
            "affectedFiles":affected,
            "affectedRepositoryCount":affected_repositories.len(),
            "maxDependencyDepth":1,
            "evidenceIds":evidence,
            "verificationContract":{
                "caseReady":false,
                "required":[
                    "external API version and behavioral contract",
                    "call-site lifecycle and error-path semantics",
                    "repository-specific repair and preservation checks",
                    "cross-repository behavior oracle"
                ]
            },
            "automaticPromotion":false
        }));
    }
    for row in facts.iter().filter(|row| {
        row.get("kind").and_then(Value::as_str) == Some("module-reference")
            && row.get("resolution").and_then(Value::as_str) == Some("unresolved")
    }) {
        candidates.push(json!({
            "id":stable_id("difficulty", &["unresolved-module",row["id"].as_str().unwrap()]),
            "schema":"agentlab.difficulty_point.v1",
            "dimensionId":"unresolved-module-boundary",
            "primaryDimension":"program-analysis",
            "mechanism":row["resolutionReason"],
            "status":"candidate",
            "maturityState":"candidate",
            "seed":{"repositoryId":row["repositoryId"],"path":row["path"],"specifier":row["specifier"]},
            "evidenceIds":[row["id"]],
            "verificationContract":{"caseReady":false,"required":["explicit module binding or external dependency policy","independent behavior oracle"]},
            "automaticPromotion":false
        }));
    }
    candidates.sort_by_key(|row| row["id"].as_str().unwrap().to_owned());
    facts.extend(edges.clone());
    facts.sort_by_key(|row| row["id"].as_str().unwrap().to_owned());
    fs::create_dir_all(&output)?;
    let fact_bytes = write_jsonl(&output.join("workspace_facts.jsonl"), &facts)?;
    let unsupported_source_bytes = write_jsonl(
        &output.join("unsupported_sources.jsonl"),
        &unsupported_sources,
    )?;
    let canonical_bindings: BTreeMap<_, _> = bindings
        .iter()
        .map(|(specifier, binding)| {
            (
                specifier,
                json!({"repositoryId":binding.repository_id,"path":binding.path}),
            )
        })
        .collect();
    let source_set = json!({
        "schema":"agentlab.multi_repo_source_set.v1",
        "repositories":repository_receipts.iter().map(|row|json!({
            "id":row["id"],"repository":row["repository"],"revision":row["revision"]
        })).collect::<Vec<_>>(),
        "moduleBindings":canonical_bindings
    });
    let source_set_sha256 = digest(&serde_json::to_vec(&source_set)?);
    let difficulty = json!({
        "schema":"agentlab.difficulty_candidates.v2",
        "method":"revision-fenced multi-repository dependency graph, recursive reverse impact closure, shared external module clustering and imported-binding API-call localization",
        "sourceSetSha256":source_set_sha256,
        "sources":source_set["repositories"],
        "moduleBindings":source_set["moduleBindings"],
        "candidates":candidates,
        "automaticPromotion":false
    });
    let difficulty_bytes = serde_json::to_vec_pretty(&difficulty)?;
    fs::write(output.join("difficulty_candidates.json"), &difficulty_bytes)?;
    let unresolved = facts
        .iter()
        .filter(|row| {
            row.get("kind").and_then(Value::as_str) == Some("module-reference")
                && row.get("resolution").and_then(Value::as_str) == Some("unresolved")
        })
        .count();
    let receipt = json!({
        "schema":"agentlab.multi_repo_analysis.v1",
        "manifestSha256":digest(&manifest_bytes),
        "sourceSetSha256":source_set_sha256,
        "analyzer":"agentlab-multi-repo-analysis@0.1.0",
        "grammar":GRAMMAR,
        "grammarDigest":GRAMMAR_DIGEST,
        "repositories":repository_receipts,
        "facts":facts.len(),
        "unsupportedSources":unsupported_sources.len(),
        "unsupportedSourcesSha256":digest(&unsupported_source_bytes),
        "moduleDependencyEdges":edges.len(),
        "crossRepositoryEdges":edges.iter().filter(|edge|edge["sourceRepositoryId"]!=edge["targetRepositoryId"]).count(),
        "sharedExternalModuleContracts":shared_external_module_count,
        "sharedExternalApiCallContracts":shared_external_api_call_count,
        "unresolvedModuleReferences":unresolved,
        "difficultyCandidates":difficulty["candidates"].as_array().unwrap().len(),
        "workspaceFactsSha256":digest(&fact_bytes),
        "difficultyCandidatesSha256":digest(&difficulty_bytes),
        "coverage":"committed UTF-8 ArkTS/TypeScript syntax facts plus relative-file and explicit-manifest module bindings; exact non-UTF-8 exclusions are recorded in unsupported_sources.jsonl; no compiler type resolution, dynamic import resolution, call-target resolution or dataflow",
        "automaticPromotion":false
    });
    fs::write(
        output.join("multi_repo_analysis.json"),
        serde_json::to_vec_pretty(&receipt)?,
    )?;
    println!("{}", receipt);
    Ok(())
}
