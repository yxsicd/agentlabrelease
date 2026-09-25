use agentlab_code_analysis::{analyze, digest, ANALYZER_DIGEST, GRAMMAR, GRAMMAR_DIGEST};
use serde_json::{json, Value};
use sha2::{Digest as _, Sha256};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

const MAX_ANALYSIS_JOBS: usize = 64;
const ANALYZER_ID: &str = "agentlab-multi-repo-analysis@0.1.0";
const CACHE_SCHEMA: &str = "agentlab.ast_file_cache.v1";
const BUNDLE_CACHE_SCHEMA: &str = "agentlab.analysis_bundle_cache.v1";
const AUTHORITY_ARTIFACTS: [&str; 3] = [
    "workspace_facts.jsonl",
    "difficulty_candidates.json",
    "unsupported_sources.jsonl",
];

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

struct AnalysisCache {
    root: PathBuf,
    hits: AtomicUsize,
    misses: AtomicUsize,
    invalid_entries: AtomicUsize,
    writes: AtomicUsize,
    bundle_hits: AtomicUsize,
    bundle_misses: AtomicUsize,
    bundle_writes: AtomicUsize,
    file_cache_enabled: bool,
}

impl AnalysisCache {
    fn new(root: PathBuf, file_cache_enabled: bool) -> Result<Self, Box<dyn std::error::Error>> {
        fs::create_dir_all(&root)?;
        Ok(Self {
            root,
            hits: AtomicUsize::new(0),
            misses: AtomicUsize::new(0),
            invalid_entries: AtomicUsize::new(0),
            writes: AtomicUsize::new(0),
            bundle_hits: AtomicUsize::new(0),
            bundle_misses: AtomicUsize::new(0),
            bundle_writes: AtomicUsize::new(0),
            file_cache_enabled,
        })
    }

    fn key(path: &str, source_sha256: &str) -> String {
        digest(
            format!(
                "{CACHE_SCHEMA}\0{ANALYZER_ID}\0{ANALYZER_DIGEST}\0{GRAMMAR_DIGEST}\0{path}\0{source_sha256}"
            )
                .as_bytes(),
        )
    }

    fn entry_path(&self, key: &str) -> PathBuf {
        self.root.join(&key[..2]).join(format!("{key}.json"))
    }

    fn bundle_key(source_set_sha256: &str) -> String {
        digest(
            format!(
                "{BUNDLE_CACHE_SCHEMA}\0{ANALYZER_ID}\0{ANALYZER_DIGEST}\0{GRAMMAR_DIGEST}\0{source_set_sha256}"
            )
            .as_bytes(),
        )
    }

    fn bundle_root(&self, key: &str) -> PathBuf {
        self.root.join("bundles").join(&key[..2]).join(key)
    }

    fn try_restore_bundle(
        &self,
        source_set_sha256: &str,
        manifest_sha256: &str,
        output: &Path,
    ) -> Result<Option<Value>, Box<dyn std::error::Error>> {
        let key = Self::bundle_key(source_set_sha256);
        let bundle_root = self.bundle_root(&key);
        let index_path = bundle_root.join("index.json");
        if !index_path.exists() {
            self.bundle_misses.fetch_add(1, Ordering::Relaxed);
            return Ok(None);
        }
        let result = (|| -> Result<Value, Box<dyn std::error::Error>> {
            let metadata = fs::symlink_metadata(&index_path)?;
            if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
                return Err(fail("bundle cache index is not a regular file"));
            }
            let index: Value = serde_json::from_slice(&fs::read(&index_path)?)?;
            if index.get("schema").and_then(Value::as_str) != Some(BUNDLE_CACHE_SCHEMA)
                || index.get("key").and_then(Value::as_str) != Some(&key)
                || index.get("analyzer").and_then(Value::as_str) != Some(ANALYZER_ID)
                || index.get("analyzerDigest").and_then(Value::as_str) != Some(ANALYZER_DIGEST)
                || index.get("grammarDigest").and_then(Value::as_str) != Some(GRAMMAR_DIGEST)
                || index.get("sourceSetSha256").and_then(Value::as_str) != Some(source_set_sha256)
            {
                return Err(fail("bundle cache index identity differs"));
            }
            let digests = index
                .get("artifactSha256")
                .and_then(Value::as_object)
                .ok_or_else(|| fail("bundle cache artifact digests are absent"))?;
            fs::create_dir_all(output)?;
            let mut actual_digests = BTreeMap::new();
            for name in AUTHORITY_ARTIFACTS {
                let source = bundle_root.join(name);
                let metadata = fs::symlink_metadata(&source)?;
                if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
                    return Err(fail(format!("bundle cache {name} is not a regular file")));
                }
                let actual_digest = file_digest(&source)?;
                if digests.get(name).and_then(Value::as_str) != Some(&actual_digest) {
                    return Err(fail(format!("bundle cache {name} digest differs")));
                }
                actual_digests.insert(name, actual_digest);
                link_or_copy(&source, &output.join(name))?;
            }
            let receipt_path = bundle_root.join("multi_repo_analysis.json");
            let metadata = fs::symlink_metadata(&receipt_path)?;
            if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
                return Err(fail("bundle cache receipt is not a regular file"));
            }
            let receipt_bytes = fs::read(&receipt_path)?;
            if index.get("receiptSha256").and_then(Value::as_str) != Some(&digest(&receipt_bytes)) {
                return Err(fail("bundle cache receipt digest differs"));
            }
            let mut receipt: Value = serde_json::from_slice(&receipt_bytes)?;
            if receipt.get("schema").and_then(Value::as_str)
                != Some("agentlab.multi_repo_analysis.v1")
                || receipt.get("analyzerDigest").and_then(Value::as_str) != Some(ANALYZER_DIGEST)
                || receipt.get("grammarDigest").and_then(Value::as_str) != Some(GRAMMAR_DIGEST)
                || receipt.get("sourceSetSha256").and_then(Value::as_str) != Some(source_set_sha256)
            {
                return Err(fail("bundle cache receipt identity differs"));
            }
            for (name, field) in [
                ("workspace_facts.jsonl", "workspaceFactsSha256"),
                ("difficulty_candidates.json", "difficultyCandidatesSha256"),
                ("unsupported_sources.jsonl", "unsupportedSourcesSha256"),
            ] {
                if receipt.get(field).and_then(Value::as_str)
                    != actual_digests.get(name).map(String::as_str)
                {
                    return Err(fail(format!(
                        "bundle cache receipt {field} differs from {name}"
                    )));
                }
            }
            let object = receipt
                .as_object_mut()
                .ok_or_else(|| fail("bundle cache receipt is not an object"))?;
            object.insert("manifestSha256".into(), json!(manifest_sha256));
            fs::write(
                output.join("multi_repo_analysis.json"),
                serde_json::to_vec_pretty(&receipt)?,
            )?;
            Ok(receipt)
        })();
        match result {
            Ok(receipt) => {
                self.bundle_hits.fetch_add(1, Ordering::Relaxed);
                Ok(Some(receipt))
            }
            Err(_) => {
                self.invalid_entries.fetch_add(1, Ordering::Relaxed);
                self.bundle_misses.fetch_add(1, Ordering::Relaxed);
                Ok(None)
            }
        }
    }

    fn store_bundle(
        &self,
        source_set_sha256: &str,
        output: &Path,
        receipt: &Value,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let key = Self::bundle_key(source_set_sha256);
        let bundle_root = self.bundle_root(&key);
        fs::create_dir_all(&bundle_root)?;
        let mut artifact_sha256 = serde_json::Map::new();
        for name in AUTHORITY_ARTIFACTS {
            let source = output.join(name);
            artifact_sha256.insert(name.into(), json!(file_digest(&source)?));
            link_or_copy(&source, &bundle_root.join(name))?;
        }
        let receipt_bytes = serde_json::to_vec_pretty(receipt)?;
        fs::write(bundle_root.join("multi_repo_analysis.json"), &receipt_bytes)?;
        let index = json!({
            "schema":BUNDLE_CACHE_SCHEMA,
            "key":key,
            "analyzer":ANALYZER_ID,
            "analyzerDigest":ANALYZER_DIGEST,
            "grammarDigest":GRAMMAR_DIGEST,
            "sourceSetSha256":source_set_sha256,
            "artifactSha256":artifact_sha256,
            "receiptSha256":digest(&receipt_bytes)
        });
        fs::write(bundle_root.join("index.json"), serde_json::to_vec(&index)?)?;
        self.bundle_writes.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }

    fn load(
        &self,
        path: &str,
        source_sha256: &str,
        revision: &str,
    ) -> Option<agentlab_code_analysis::Analysis> {
        let key = Self::key(path, source_sha256);
        let entry_path = self.entry_path(&key);
        let metadata = fs::symlink_metadata(&entry_path).ok()?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            self.invalid_entries.fetch_add(1, Ordering::Relaxed);
            return None;
        }
        let value: Value = match fs::read(&entry_path)
            .ok()
            .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        {
            Some(value) => value,
            None => {
                self.invalid_entries.fetch_add(1, Ordering::Relaxed);
                return None;
            }
        };
        let valid_header = value.get("schema").and_then(Value::as_str) == Some(CACHE_SCHEMA)
            && value.get("key").and_then(Value::as_str) == Some(&key)
            && value.get("analyzer").and_then(Value::as_str) == Some(ANALYZER_ID)
            && value.get("analyzerDigest").and_then(Value::as_str) == Some(ANALYZER_DIGEST)
            && value.get("grammarDigest").and_then(Value::as_str) == Some(GRAMMAR_DIGEST)
            && value.get("path").and_then(Value::as_str) == Some(path)
            && value.get("sourceSha256").and_then(Value::as_str) == Some(source_sha256);
        let Some(has_errors) = value.get("hasErrors").and_then(Value::as_bool) else {
            self.invalid_entries.fetch_add(1, Ordering::Relaxed);
            return None;
        };
        let Some(cached_rows) = value.get("rows").and_then(Value::as_array) else {
            self.invalid_entries.fetch_add(1, Ordering::Relaxed);
            return None;
        };
        let valid_rows = valid_header
            && !cached_rows.is_empty()
            && value.get("rowsSha256").and_then(Value::as_str)
                == serde_json::to_vec(cached_rows)
                    .ok()
                    .as_deref()
                    .map(digest)
                    .as_deref()
            && cached_rows.iter().all(|row| {
                row.as_object().is_some_and(|object| {
                    object.get("id").and_then(Value::as_str).is_some()
                        && object.get("kind").and_then(Value::as_str).is_some()
                        && object.get("path").and_then(Value::as_str) == Some(path)
                        && !object.contains_key("sourceRevision")
                })
            })
            && cached_rows.iter().any(|row| {
                row.get("kind").and_then(Value::as_str) == Some("parse-file")
                    && row.get("sha256").and_then(Value::as_str) == Some(source_sha256)
            });
        if !valid_rows {
            self.invalid_entries.fetch_add(1, Ordering::Relaxed);
            return None;
        }
        let mut rows = cached_rows.clone();
        for row in &mut rows {
            row.as_object_mut()
                .unwrap()
                .insert("sourceRevision".into(), json!(revision));
        }
        self.hits.fetch_add(1, Ordering::Relaxed);
        Some(agentlab_code_analysis::Analysis { rows, has_errors })
    }

    fn store(
        &self,
        path: &str,
        source_sha256: &str,
        analysis: &agentlab_code_analysis::Analysis,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let key = Self::key(path, source_sha256);
        let entry_path = self.entry_path(&key);
        let parent = entry_path
            .parent()
            .ok_or_else(|| fail("cache entry has no parent directory"))?;
        fs::create_dir_all(parent)?;
        let mut rows = analysis.rows.clone();
        for row in &mut rows {
            row.as_object_mut()
                .ok_or_else(|| fail("analysis row is not an object"))?
                .remove("sourceRevision");
        }
        let value = json!({
            "schema":CACHE_SCHEMA,
            "key":key,
            "analyzer":ANALYZER_ID,
            "analyzerDigest":ANALYZER_DIGEST,
            "grammarDigest":GRAMMAR_DIGEST,
            "path":path,
            "sourceSha256":source_sha256,
            "hasErrors":analysis.has_errors,
            "rowsSha256":digest(&serde_json::to_vec(&rows)?),
            "rows":rows
        });
        let temporary = parent.join(format!(
            ".{key}.tmp-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        fs::write(&temporary, serde_json::to_vec(&value)?)?;
        fs::rename(&temporary, &entry_path)?;
        self.writes.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }

    fn report(&self) -> Value {
        json!({
            "schema":"agentlab.analysis_cache_execution.v1",
            "cacheAuthority":false,
            "bundleKeyContract":"analyzer implementation digest + grammar digest + portable source-set SHA-256",
            "fileKeyContract":"analyzer implementation digest + grammar digest + source path + committed blob SHA-256",
            "fileCacheEnabled":self.file_cache_enabled,
            "hits":self.hits.load(Ordering::Relaxed),
            "misses":self.misses.load(Ordering::Relaxed),
            "invalidEntries":self.invalid_entries.load(Ordering::Relaxed),
            "writes":self.writes.load(Ordering::Relaxed)
            ,"bundleHits":self.bundle_hits.load(Ordering::Relaxed)
            ,"bundleMisses":self.bundle_misses.load(Ordering::Relaxed)
            ,"bundleWrites":self.bundle_writes.load(Ordering::Relaxed)
        })
    }
}

fn file_digest(path: &Path) -> Result<String, Box<dyn std::error::Error>> {
    let mut file = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hash.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn link_or_copy(source: &Path, target: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let parent = target
        .parent()
        .ok_or_else(|| fail("cache artifact target has no parent directory"))?;
    fs::create_dir_all(parent)?;
    let file_name = target
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| fail("cache artifact target has no UTF-8 file name"))?;
    let temporary = parent.join(format!(
        ".{file_name}.tmp-{}-{:?}",
        std::process::id(),
        std::thread::current().id()
    ));
    if fs::hard_link(source, &temporary).is_err() {
        fs::copy(source, &temporary)?;
    }
    fs::rename(temporary, target)?;
    Ok(())
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

fn analyze_sources(
    repository: &Repository,
    paths: &[String],
    blobs: &BTreeMap<String, Vec<u8>>,
    jobs: usize,
    cache: Option<&AnalysisCache>,
) -> Result<Vec<agentlab_code_analysis::Analysis>, Box<dyn std::error::Error>> {
    if paths.is_empty() {
        return Ok(Vec::new());
    }
    let next = AtomicUsize::new(0);
    let results = Mutex::new(
        std::iter::repeat_with(|| None)
            .take(paths.len())
            .collect::<Vec<Option<Result<agentlab_code_analysis::Analysis, String>>>>(),
    );
    let worker_count = jobs.min(paths.len());
    std::thread::scope(|scope| {
        for _ in 0..worker_count {
            scope.spawn(|| loop {
                let index = next.fetch_add(1, Ordering::Relaxed);
                if index >= paths.len() {
                    break;
                }
                let path = &paths[index];
                let source_sha256 = digest(&blobs[path]);
                let result = if let Some(cache) = cache {
                    if let Some(analysis) = cache.load(path, &source_sha256, &repository.revision) {
                        Ok(analysis)
                    } else {
                        cache.misses.fetch_add(1, Ordering::Relaxed);
                        analyze(path, &blobs[path], &repository.revision).and_then(|analysis| {
                            cache
                                .store(path, &source_sha256, &analysis)
                                .map_err(|error| error.to_string())?;
                            Ok(analysis)
                        })
                    }
                } else {
                    analyze(path, &blobs[path], &repository.revision)
                };
                results.lock().unwrap()[index] = Some(result);
            });
        }
    });
    results
        .into_inner()
        .map_err(|_| fail("analysis result lock poisoned"))?
        .into_iter()
        .enumerate()
        .map(|(index, result)| {
            result
                .ok_or_else(|| fail(format!("missing analysis result for {}", paths[index])))?
                .map_err(|error| fail(format!("analysis failed for {}: {error}", paths[index])))
        })
        .collect()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let mut jobs = std::thread::available_parallelism()
        .map(usize::from)
        .unwrap_or(1)
        .min(8);
    let mut cache_root = None;
    let mut cache_files = false;
    let mut positional = Vec::new();
    let mut index = 0usize;
    while index < args.len() {
        if args[index] == "--jobs" {
            index += 1;
            let count = args
                .get(index)
                .and_then(|value| value.to_str())
                .ok_or_else(|| fail("--jobs must be a positive integer"))?
                .parse::<usize>()?;
            if count == 0 {
                return Err(fail("--jobs must be a positive integer"));
            }
            jobs = count;
        } else if args[index] == "--cache-dir" {
            index += 1;
            let value = args
                .get(index)
                .ok_or_else(|| fail("--cache-dir requires a path"))?;
            if value.is_empty() {
                return Err(fail("--cache-dir requires a path"));
            }
            cache_root = Some(PathBuf::from(value));
        } else if args[index] == "--cache-files" {
            cache_files = true;
        } else {
            positional.push(args[index].clone());
        }
        index += 1;
    }
    if positional.len() != 2 {
        return Err(fail(
            "Usage: agentlab-multi-repo-analysis [--jobs N] [--cache-dir PATH [--cache-files]] <manifest.json> <output-directory>",
        ));
    }
    if jobs > MAX_ANALYSIS_JOBS {
        return Err(fail(format!("--jobs must not exceed {MAX_ANALYSIS_JOBS}")));
    }
    let manifest_path = PathBuf::from(&positional[0]);
    let output = PathBuf::from(&positional[1]);
    if cache_files && cache_root.is_none() {
        return Err(fail("--cache-files requires --cache-dir PATH"));
    }
    let cache = cache_root
        .map(|root| AnalysisCache::new(root, cache_files))
        .transpose()?;
    let manifest_bytes = fs::read(&manifest_path)?;
    let manifest_sha256 = digest(&manifest_bytes);
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
        "repositories":repositories.values().map(|repository|json!({
            "id":repository.id,"repository":repository.source,"revision":repository.revision
        })).collect::<Vec<_>>(),
        "moduleBindings":canonical_bindings
    });
    let source_set_sha256 = digest(&serde_json::to_vec(&source_set)?);
    if let Some(cache) = &cache {
        if let Some(receipt) =
            cache.try_restore_bundle(&source_set_sha256, &manifest_sha256, &output)?
        {
            println!("{}", receipt);
            eprintln!("{}", cache.report());
            return Ok(());
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
        let source_file_candidate_count = source_paths.len();
        let mut file_count = 0usize;
        let mut syntax_error_count = 0usize;
        let mut fact_count = 0usize;
        let mut supported_paths = Vec::new();
        for path in &source_paths {
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
            supported_paths.push(path.clone());
        }
        let analyses = analyze_sources(
            repository,
            &supported_paths,
            &source_blobs,
            jobs,
            cache.as_ref().filter(|cache| cache.file_cache_enabled),
        )?;
        for analysis in analyses {
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
        "manifestSha256":manifest_sha256,
        "sourceSetSha256":source_set_sha256,
        "analyzer":ANALYZER_ID,
        "analyzerDigest":ANALYZER_DIGEST,
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
    if let Some(cache) = &cache {
        cache.store_bundle(&source_set_sha256, &output, &receipt)?;
    }
    println!("{}", receipt);
    if let Some(cache) = &cache {
        eprintln!("{}", cache.report());
    }
    Ok(())
}
