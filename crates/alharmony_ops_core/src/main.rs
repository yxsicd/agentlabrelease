use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc::TrySendError;
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use alharmony_ops_core::{
    artifact_inspect, build_debug_plan, env_status, ohpm_install_plan, project_create_plan,
    project_verify, JsonValue, Receipt,
};

#[derive(Debug)]
struct ServiceConfig {
    task_root: Option<PathBuf>,
    queue_capacity: usize,
    max_batch: usize,
    max_active_requests: usize,
    active_requests: AtomicUsize,
    fork_backend: String,
    sessionfs_endpoint: Option<String>,
}

#[derive(Clone, Debug)]
struct TaskScope {
    task_id: String,
    root: PathBuf,
}

fn main() {
    let mut args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.is_empty() || args[0] == "--help" || args[0] == "-h" {
        usage(0);
    }
    let command = args.remove(0);
    if command == "serve" || command == "service" {
        run_service(args);
    }
    let receipt = dispatch_cli(&command, &mut args);
    if !args.is_empty() {
        eprintln!("unexpected arguments: {}", args.join(" "));
        std::process::exit(2);
    }
    print!("{}", receipt.to_json_pretty());
    if !receipt.ok {
        std::process::exit(1);
    }
}

fn dispatch_cli(command: &str, args: &mut Vec<String>) -> Receipt {
    match command {
        "env-status" | "harmony.env.status" => {
            let harmony_home = take_value(args, "--harmony-home").map(PathBuf::from);
            env_status(harmony_home.as_deref())
        }
        "project-create-plan" | "harmony.project.create" => {
            let root = required_path(args, "--project-root");
            let bundle = take_value(args, "--bundle-name")
                .unwrap_or_else(|| "com.agentlab.demo".to_string());
            let label =
                take_value(args, "--app-label").unwrap_or_else(|| "AgentLab Demo".to_string());
            project_create_plan(&root, &bundle, &label)
        }
        "project-verify" | "harmony.project.verify" => {
            let root = required_path(args, "--project-root");
            project_verify(&root)
        }
        "ohpm-install-plan" | "harmony.ohpm.install" => {
            let root = required_path(args, "--project-root");
            let harmony = required_path(args, "--harmony-home");
            ohpm_install_plan(&root, &harmony)
        }
        "build-debug-plan" | "harmony.build.debug" => {
            let root = required_path(args, "--project-root");
            let harmony = required_path(args, "--harmony-home");
            build_debug_plan(&root, &harmony)
        }
        "artifact-inspect" | "harmony.artifact.inspect" => {
            let path = required_path(args, "--artifact");
            artifact_inspect(&path)
        }
        _ => {
            eprintln!("unknown command: {command}");
            usage(2);
        }
    }
}

fn run_service(mut args: Vec<String>) -> ! {
    let bind = take_value(&mut args, "--bind").unwrap_or_else(|| "127.0.0.1:19731".to_string());
    let workers = take_value(&mut args, "--workers")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or_else(|| {
            thread::available_parallelism()
                .map(|value| value.get())
                .unwrap_or(4)
        });
    let queue_capacity = take_value(&mut args, "--queue-capacity")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(workers.saturating_mul(4).max(1));
    let max_batch = take_value(&mut args, "--max-batch")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(100_000);
    let max_active_requests = take_value(&mut args, "--max-active-requests")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(workers);
    let task_root =
        take_value(&mut args, "--task-root").map(|value| normalize_path(Path::new(&value)));
    let fork_backend =
        take_value(&mut args, "--fork-backend").unwrap_or_else(|| "copy-tree".to_string());
    if !matches!(fork_backend.as_str(), "copy-tree" | "sessionfs" | "auto") {
        eprintln!("--fork-backend must be one of: auto, copy-tree, sessionfs");
        std::process::exit(2);
    }
    let sessionfs_endpoint = take_value(&mut args, "--sessionfs-endpoint");
    if fork_backend == "sessionfs" && sessionfs_endpoint.is_none() {
        eprintln!("--fork-backend sessionfs requires --sessionfs-endpoint");
        std::process::exit(2);
    }
    if !args.is_empty() {
        eprintln!("unexpected service arguments: {}", args.join(" "));
        std::process::exit(2);
    }

    let listener = TcpListener::bind(&bind).unwrap_or_else(|error| {
        eprintln!("failed to bind {bind}: {error}");
        std::process::exit(1);
    });
    eprintln!(
        "alharmony-ops service listening on {bind} with {workers} workers, queue_capacity={queue_capacity}, max_active_requests={max_active_requests}, task_root={}",
        task_root
            .as_ref()
            .map(|value| value.display().to_string())
            .unwrap_or_else(|| "<disabled>".to_string())
    );

    let config = Arc::new(ServiceConfig {
        task_root,
        queue_capacity,
        max_batch,
        max_active_requests,
        active_requests: AtomicUsize::new(0),
        fork_backend,
        sessionfs_endpoint,
    });
    let (tx, rx) = mpsc::sync_channel::<TcpStream>(queue_capacity);
    let rx = Arc::new(Mutex::new(rx));
    for _ in 0..workers {
        let rx = Arc::clone(&rx);
        let config = Arc::clone(&config);
        thread::spawn(move || loop {
            let stream = match rx.lock().expect("worker receiver poisoned").recv() {
                Ok(stream) => stream,
                Err(_) => return,
            };
            handle_connection(stream, &config);
        });
    }

    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => match tx.try_send(stream) {
                Ok(()) => {}
                Err(TrySendError::Full(returned_stream)) => {
                    stream = returned_stream;
                    let body = service_error_body(
                        "queueFull",
                        "service queue is full; retry with backoff or lower concurrency",
                    );
                    let _ = write_http_response(&mut stream, 503, &body, true);
                }
                Err(TrySendError::Disconnected(_)) => break,
            },
            Err(error) => eprintln!("accept failed: {error}"),
        }
    }
    std::process::exit(0);
}

fn handle_connection(mut stream: TcpStream, config: &ServiceConfig) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(5)));
    for _ in 0..1_000_000_u32 {
        let Some(request) = read_http_header(&mut stream) else {
            return;
        };
        let close_after_response = request_wants_close(&request);
        let Some(_active_guard) = ActiveRequestGuard::try_begin(config) else {
            let body = service_error_body(
                "activeRequestLimit",
                "service active request limit is reached; retry with backoff or lower concurrency",
            );
            let _ = write_http_response(&mut stream, 503, &body, true);
            return;
        };
        let (status, body) = route_request(&request, config);
        if write_http_response(&mut stream, status, &body, close_after_response).is_err() {
            return;
        }
        if close_after_response {
            return;
        }
    }
}

struct ActiveRequestGuard<'a> {
    active: &'a AtomicUsize,
}

impl<'a> ActiveRequestGuard<'a> {
    fn try_begin(config: &'a ServiceConfig) -> Option<Self> {
        loop {
            let current = config.active_requests.load(Ordering::Relaxed);
            if current >= config.max_active_requests {
                return None;
            }
            if config
                .active_requests
                .compare_exchange_weak(current, current + 1, Ordering::AcqRel, Ordering::Relaxed)
                .is_ok()
            {
                return Some(Self {
                    active: &config.active_requests,
                });
            }
        }
    }
}

impl Drop for ActiveRequestGuard<'_> {
    fn drop(&mut self) {
        self.active.fetch_sub(1, Ordering::AcqRel);
    }
}

fn write_http_response(
    stream: &mut TcpStream,
    status: u16,
    body: &str,
    close_after_response: bool,
) -> std::io::Result<()> {
    let reason = match status {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        503 => "Service Unavailable",
        _ => "Internal Server Error",
    };
    let connection = if close_after_response {
        "close"
    } else {
        "keep-alive"
    };
    let response = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: {connection}\r\n\r\n{}",
        body.len(), body
    );
    stream.write_all(response.as_bytes())
}

fn read_http_header(stream: &mut TcpStream) -> Option<String> {
    let mut buffer = [0_u8; 8192];
    let mut used = 0_usize;
    while used < buffer.len() {
        match stream.read(&mut buffer[used..]) {
            Ok(0) => return None,
            Ok(n) => {
                used += n;
                if buffer[..used].windows(4).any(|w| w == b"\r\n\r\n") {
                    return Some(String::from_utf8_lossy(&buffer[..used]).into_owned());
                }
            }
            Err(_) => return None,
        }
    }
    Some(String::from_utf8_lossy(&buffer[..used]).into_owned())
}

fn request_wants_close(request: &str) -> bool {
    let request_line = request.lines().next().unwrap_or_default();
    let http10 = request_line.ends_with("HTTP/1.0");
    request.lines().any(|line| {
        let lower = line.trim().to_ascii_lowercase();
        lower == "connection: close"
    }) || http10
}

fn route_request(request: &str, config: &ServiceConfig) -> (u16, String) {
    let Some(line) = request.lines().next() else {
        return service_error(400, "emptyRequest", "request line is missing");
    };
    let mut parts = line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("");
    if method != "GET" {
        return service_error(
            400,
            "unsupportedMethod",
            "only GET is supported by the preview service",
        );
    }
    if target == "/health" || target == "/v1/health" || target == "/v1/service/status" {
        return (200, service_status_body(config));
    }
    let (path, query) = split_target(target);
    let params = parse_query(query);
    if let Some(operation) = path.strip_prefix("/v1/ops/") {
        return match dispatch_http(operation, &params, config) {
            Ok(receipt) => (200, receipt.to_json_pretty()),
            Err(message) => service_error(400, "badOperationRequest", &message),
        };
    }
    if let Some(operation) = path.strip_prefix("/v1/batch/") {
        return match dispatch_batch_http(operation, &params, config) {
            Ok(body) => (200, body),
            Err(message) => service_error(400, "badBatchRequest", &message),
        };
    }
    service_error(404, "notFound", "unknown endpoint")
}

fn service_status_body(config: &ServiceConfig) -> String {
    let task_root = match &config.task_root {
        Some(value) => format!("\"{}\"", json_escape(&value.display().to_string())),
        None => "null".to_string(),
    };
    format!(
        "{{
  \"schema\": \"agentlab.harmony_ops.service_status.v1\",
  \"ok\": true,
  \"service\": \"alharmony-ops\",
  \"receiptSchema\": \"agentlab.harmony_ops.receipt.v1\",
  \"queueCapacity\": {},
  \"maxBatch\": {},
  \"maxActiveRequests\": {},
  \"activeRequests\": {},
  \"taskIsolation\": {{
    \"enabled\": {},
    \"taskRoot\": {}
  }}
}}
",
        config.queue_capacity,
        config.max_batch,
        config.max_active_requests,
        config.active_requests.load(Ordering::Relaxed),
        if config.task_root.is_some() {
            "true"
        } else {
            "false"
        },
        task_root
    )
}

fn dispatch_batch_http(
    operation: &str,
    params: &BTreeMap<String, String>,
    config: &ServiceConfig,
) -> Result<String, String> {
    let count = params
        .get("n")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| (1..=config.max_batch).contains(value))
        .unwrap_or(1);
    let task = validate_task_for_operation(operation, params, config)?;
    let started = Instant::now();
    let mut ok_count = 0_usize;
    let mut last = None;
    for index in 0..count {
        let receipt_task = if index + 1 == count {
            task.as_ref()
        } else {
            None
        };
        let receipt = dispatch_http_with_task(operation, params, receipt_task, config)?;
        if receipt.ok {
            ok_count += 1;
        }
        last = Some(receipt);
    }
    let elapsed_us = started.elapsed().as_micros();
    let last = last.expect("batch count is never zero");
    let last_json = last.to_json_pretty();
    Ok(format!(
        r#"{{
  "schema": "agentlab.harmony_ops.batch_receipt.v1",
  "ok": {},
  "operation": "{}",
  "count": {},
  "okCount": {},
  "elapsedMicros": {},
  "lastReceipt": {}
}}
"#,
        if ok_count == count { "true" } else { "false" },
        json_escape(operation),
        count,
        ok_count,
        elapsed_us,
        last_json.trim_end()
    ))
}

fn dispatch_http(
    operation: &str,
    params: &BTreeMap<String, String>,
    config: &ServiceConfig,
) -> Result<Receipt, String> {
    let task = validate_task_for_operation(operation, params, config)?;
    dispatch_http_with_task(operation, params, task.as_ref(), config)
}

fn validate_task_for_operation(
    operation: &str,
    params: &BTreeMap<String, String>,
    config: &ServiceConfig,
) -> Result<Option<TaskScope>, String> {
    match operation {
        "harmony.env.status"
        | "harmony.workspace.index"
        | "harmony.workspace.match"
        | "harmony.workspace.lease"
        | "harmony.workspace.release"
        | "harmony.workspace.gc" => Ok(None),
        "harmony.task.prepare" | "harmony.task.fork" => validate_task_prepare(config, params),
        "harmony.project.create" | "harmony.project.verify" | "harmony.project.patch" => {
            let root = required_param_path(params, "projectRoot")?;
            validate_task_paths(config, params, &[("projectRoot", &root)])
        }
        "harmony.project.sync" => {
            let root = required_param_path(params, "projectRoot")?;
            let source = required_param_path(params, "sourceRoot")?;
            validate_task_paths(
                config,
                params,
                &[("projectRoot", &root), ("sourceRoot", &source)],
            )
        }
        "harmony.ohpm.install" | "harmony.build.debug" | "harmony.project.fingerprint" => {
            let root = required_param_path(params, "projectRoot")?;
            let _harmony = required_param_path(params, "harmonyHome")?;
            validate_task_paths(config, params, &[("projectRoot", &root)])
        }
        "harmony.artifact.inspect" => {
            let artifact = required_param_path(params, "artifact")?;
            validate_task_paths(config, params, &[("artifact", &artifact)])
        }
        _ => Err(format!("unknown operation: {operation}")),
    }
}

fn dispatch_http_with_task(
    operation: &str,
    params: &BTreeMap<String, String>,
    task: Option<&TaskScope>,
    config: &ServiceConfig,
) -> Result<Receipt, String> {
    match operation {
        "harmony.env.status" => Ok(env_status(param_path(params, "harmonyHome").as_deref())),
        "harmony.task.prepare" => {
            let Some(task) = task else {
                return Err("task isolation must be enabled for harmony.task.prepare".into());
            };
            let receipt = task_prepare(task)?;
            append_task_receipt(task, &receipt);
            Ok(receipt)
        }
        "harmony.task.fork" => {
            let Some(task) = task else {
                return Err("task isolation must be enabled for harmony.task.fork".into());
            };
            let parent_task_id = required_param(params, "parentTaskId")?;
            let receipt = task_fork(task, parent_task_id, config)?;
            append_task_receipt(task, &receipt);
            Ok(receipt)
        }
        "harmony.workspace.index" => workspace_index(config),
        "harmony.workspace.match" => workspace_match(config, params),
        "harmony.workspace.lease" => workspace_lease(config, params),
        "harmony.workspace.release" => workspace_release(config, params),
        "harmony.workspace.gc" => workspace_gc(config, params),
        "harmony.project.create" => {
            let root = required_param_path(params, "projectRoot")?;
            let bundle = params
                .get("bundleName")
                .map(String::as_str)
                .unwrap_or("com.agentlab.demo");
            let label = params
                .get("appLabel")
                .map(String::as_str)
                .unwrap_or("AgentLab Demo");
            if param_bool(params, "materialize") || param_bool(params, "execute") {
                let Some(task) = task else {
                    return Err("materialized project.create requires task isolation".into());
                };
                Ok(add_task_evidence(
                    project_create_materialized(&root, bundle, label)?,
                    Some(task),
                ))
            } else {
                Ok(add_task_evidence(
                    project_create_plan(&root, bundle, label),
                    task,
                ))
            }
        }
        "harmony.project.patch" => {
            let root = required_param_path(params, "projectRoot")?;
            let rel = required_param(params, "path")?;
            let find = required_param(params, "find")?;
            let replace = params.get("replace").map(String::as_str).unwrap_or("");
            Ok(add_task_evidence(
                project_patch_text(&root, rel, find, replace, param_bool(params, "replaceAll"))?,
                task,
            ))
        }
        "harmony.project.sync" => {
            let root = required_param_path(params, "projectRoot")?;
            let source = required_param_path(params, "sourceRoot")?;
            Ok(add_task_evidence(
                project_sync(&root, &source, param_bool(params, "deleteMissing"), task)?,
                task,
            ))
        }
        "harmony.project.verify" => {
            let root = required_param_path(params, "projectRoot")?;
            Ok(add_task_evidence(project_verify(&root), task))
        }
        "harmony.project.fingerprint" => {
            let root = required_param_path(params, "projectRoot")?;
            let harmony = required_param_path(params, "harmonyHome")?;
            Ok(add_task_evidence(
                project_fingerprint(&root, &harmony)?,
                task,
            ))
        }
        "harmony.ohpm.install" => {
            let root = required_param_path(params, "projectRoot")?;
            let harmony = required_param_path(params, "harmonyHome")?;
            if param_bool(params, "execute") {
                let Some(task) = task else {
                    return Err("executing ohpm.install requires task isolation".into());
                };
                Ok(add_task_evidence(
                    execute_ohpm_install(&root, &harmony)?,
                    Some(task),
                ))
            } else {
                Ok(add_task_evidence(ohpm_install_plan(&root, &harmony), task))
            }
        }
        "harmony.build.debug" => {
            let root = required_param_path(params, "projectRoot")?;
            let harmony = required_param_path(params, "harmonyHome")?;
            if param_bool(params, "execute") {
                let Some(task) = task else {
                    return Err("executing build.debug requires task isolation".into());
                };
                Ok(add_task_evidence(
                    execute_build_debug(&root, &harmony, task)?,
                    Some(task),
                ))
            } else {
                Ok(add_task_evidence(build_debug_plan(&root, &harmony), task))
            }
        }
        "harmony.artifact.inspect" => {
            let artifact = required_param_path(params, "artifact")?;
            Ok(add_task_evidence(artifact_inspect(&artifact), task))
        }
        _ => Err(format!("unknown operation: {operation}")),
    }
}

#[derive(Debug)]
struct WorkspaceCandidate {
    task_id: String,
    task_root: PathBuf,
    project_root: String,
    input_fingerprint: String,
    input_file_count: i128,
    input_bytes: i128,
    artifact_path: String,
    artifact_bytes: i128,
    updated_at: i128,
    partition_fingerprints: BTreeMap<String, String>,
    partition_file_counts: BTreeMap<String, i128>,
    partition_bytes: BTreeMap<String, i128>,
}

fn workspace_index(config: &ServiceConfig) -> Result<Receipt, String> {
    let candidates = workspace_candidates(config)?;
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "candidateCount".into(),
        JsonValue::Number(candidates.len() as i128),
    );
    evidence.insert(
        "candidates".into(),
        JsonValue::Array(candidates.iter().take(100).map(candidate_json).collect()),
    );
    if let Some(task_root) = &config.task_root {
        evidence.insert(
            "taskRoot".into(),
            JsonValue::string(task_root.display().to_string()),
        );
    }
    Ok(Receipt::new(
        "harmony.workspace.index",
        alharmony_ops_core::SideEffect::ReadOnly,
    )
    .evidence("workspaceIndex", JsonValue::Object(evidence))
    .next("harmony.workspace.match"))
}

fn workspace_match(
    config: &ServiceConfig,
    params: &BTreeMap<String, String>,
) -> Result<Receipt, String> {
    let input_fingerprint = required_param(params, "inputFingerprint")?;
    let max_results = params
        .get("maxResults")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(8)
        .min(50);
    let query_file_count = params
        .get("inputFileCount")
        .and_then(|value| value.parse::<i128>().ok());
    let query_bytes = params
        .get("inputBytes")
        .and_then(|value| value.parse::<i128>().ok());
    let query_partitions = partition_query_fingerprints(params);
    let mut scored: Vec<(i128, WorkspaceCandidate)> = workspace_candidates(config)?
        .into_iter()
        .map(|candidate| {
            let mut score = if candidate.input_fingerprint == input_fingerprint {
                1000
            } else {
                0
            };
            if let Some(count) = query_file_count {
                let diff = (candidate.input_file_count - count).abs();
                score += (100 - diff).max(0);
            }
            if let Some(bytes) = query_bytes {
                let denom = bytes.max(candidate.input_bytes).max(1);
                let diff = (candidate.input_bytes - bytes).abs();
                score += (100 - (diff * 100 / denom)).max(0);
            }
            for (partition, fingerprint) in &query_partitions {
                if candidate
                    .partition_fingerprints
                    .get(partition)
                    .is_some_and(|candidate_fp| candidate_fp == fingerprint)
                {
                    score += partition_weight(partition);
                }
            }
            score += (candidate.updated_at / 1_000_000_000_000).max(0).min(10);
            (score, candidate)
        })
        .collect();
    scored.sort_by(|a, b| b.0.cmp(&a.0));
    let exact_matches = scored
        .iter()
        .filter(|(_, candidate)| candidate.input_fingerprint == input_fingerprint)
        .count();
    let partition_hint_count = query_partitions.len();
    let mut candidates = Vec::new();
    for (score, candidate) in scored.into_iter().take(max_results) {
        let mut item = match candidate_json(&candidate) {
            JsonValue::Object(map) => map,
            _ => BTreeMap::new(),
        };
        item.insert("score".into(), JsonValue::Number(score));
        item.insert(
            "exactInputFingerprint".into(),
            JsonValue::Bool(candidate.input_fingerprint == input_fingerprint),
        );
        let matched_partitions = query_partitions
            .iter()
            .filter(|(partition, fingerprint)| {
                candidate
                    .partition_fingerprints
                    .get(*partition)
                    .is_some_and(|candidate_fp| candidate_fp == *fingerprint)
            })
            .map(|(partition, _)| JsonValue::string(partition))
            .collect::<Vec<_>>();
        item.insert(
            "matchedPartitions".into(),
            JsonValue::Array(matched_partitions),
        );
        candidates.push(JsonValue::Object(item));
    }
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "inputFingerprint".into(),
        JsonValue::string(input_fingerprint),
    );
    evidence.insert("maxResults".into(), JsonValue::Number(max_results as i128));
    evidence.insert(
        "exactMatches".into(),
        JsonValue::Number(exact_matches as i128),
    );
    evidence.insert(
        "partitionHintCount".into(),
        JsonValue::Number(partition_hint_count as i128),
    );
    evidence.insert(
        "queryPartitions".into(),
        JsonValue::Object(partition_strings_json(&query_partitions)),
    );
    evidence.insert("candidates".into(), JsonValue::Array(candidates));
    Ok(Receipt::new(
        "harmony.workspace.match",
        alharmony_ops_core::SideEffect::ReadOnly,
    )
    .evidence("workspaceMatch", JsonValue::Object(evidence))
    .next("harmony.task.fork"))
}

fn workspace_candidates(config: &ServiceConfig) -> Result<Vec<WorkspaceCandidate>, String> {
    let task_root = config
        .task_root
        .as_ref()
        .ok_or_else(|| "workspace index requires service --task-root".to_string())?;
    if !task_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    let read_dir = fs::read_dir(task_root)
        .map_err(|error| format!("failed to read taskRoot {}: {error}", task_root.display()))?;
    for entry in read_dir.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let state_path = path.join("state/build-state.json");
        if !state_path.is_file() {
            continue;
        }
        let Ok(body) = fs::read_to_string(&state_path) else {
            continue;
        };
        let task_id = json_string_field(&body, "taskId")
            .unwrap_or_else(|| entry.file_name().to_string_lossy().into_owned());
        let Some(input_fingerprint) = json_string_field(&body, "inputFingerprint") else {
            continue;
        };
        out.push(WorkspaceCandidate {
            task_id,
            task_root: path,
            project_root: json_string_field(&body, "projectRoot").unwrap_or_default(),
            input_fingerprint,
            input_file_count: json_number_field(&body, "inputFileCount").unwrap_or(0),
            input_bytes: json_number_field(&body, "inputBytes").unwrap_or(0),
            artifact_path: json_string_field(&body, "artifactPath").unwrap_or_default(),
            artifact_bytes: json_number_field(&body, "artifactBytes").unwrap_or(0),
            updated_at: json_number_field(&body, "updatedAtUnixMillis").unwrap_or(0),
            partition_fingerprints: parse_partition_string_fields(&body, "Fingerprint"),
            partition_file_counts: parse_partition_number_fields(&body, "FileCount"),
            partition_bytes: parse_partition_number_fields(&body, "Bytes"),
        });
    }
    out.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(out)
}

fn candidate_json(candidate: &WorkspaceCandidate) -> JsonValue {
    let mut item = BTreeMap::new();
    item.insert(
        "taskId".into(),
        JsonValue::string(candidate.task_id.clone()),
    );
    item.insert(
        "taskRoot".into(),
        JsonValue::string(candidate.task_root.display().to_string()),
    );
    item.insert(
        "projectRoot".into(),
        JsonValue::string(candidate.project_root.clone()),
    );
    item.insert(
        "inputFingerprint".into(),
        JsonValue::string(candidate.input_fingerprint.clone()),
    );
    item.insert(
        "inputFileCount".into(),
        JsonValue::Number(candidate.input_file_count),
    );
    item.insert(
        "inputBytes".into(),
        JsonValue::Number(candidate.input_bytes),
    );
    item.insert(
        "artifactPath".into(),
        JsonValue::string(candidate.artifact_path.clone()),
    );
    item.insert(
        "artifactBytes".into(),
        JsonValue::Number(candidate.artifact_bytes),
    );
    item.insert(
        "updatedAtUnixMillis".into(),
        JsonValue::Number(candidate.updated_at),
    );
    item.insert(
        "partitionFingerprints".into(),
        JsonValue::Object(partition_strings_json(&candidate.partition_fingerprints)),
    );
    item.insert(
        "partitionFileCounts".into(),
        JsonValue::Object(partition_numbers_json(&candidate.partition_file_counts)),
    );
    item.insert(
        "partitionBytes".into(),
        JsonValue::Object(partition_numbers_json(&candidate.partition_bytes)),
    );
    JsonValue::Object(item)
}

fn workspace_lease(
    config: &ServiceConfig,
    params: &BTreeMap<String, String>,
) -> Result<Receipt, String> {
    let task_root = config
        .task_root
        .as_ref()
        .ok_or_else(|| "workspace lease requires service --task-root".to_string())?;
    let candidate_task_id = required_param(params, "candidateTaskId")?;
    validate_task_id(candidate_task_id)?;
    let lease_id = params
        .get("leaseId")
        .map(String::as_str)
        .unwrap_or(candidate_task_id);
    validate_task_id(lease_id)?;
    let ttl_millis = params
        .get("ttlMillis")
        .and_then(|value| value.parse::<i128>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(3_600_000);
    let renew = param_bool(params, "renew");
    let candidate_root = task_root.join(candidate_task_id);
    if !candidate_root.join("state/build-state.json").is_file() {
        return Err(format!(
            "candidate task has no build state: {candidate_task_id}"
        ));
    }
    let leases_dir = task_root.join("_leases");
    fs::create_dir_all(&leases_dir)
        .map_err(|error| format!("failed to create lease dir: {error}"))?;
    let lease_path = leases_dir.join(format!("{lease_id}.json"));
    let now = now_millis();
    let mut replaced_expired = false;
    if lease_path.is_file() {
        let body = fs::read_to_string(&lease_path)
            .map_err(|error| format!("failed to read existing lease: {error}"))?;
        let expires = json_number_field(&body, "expiresAtUnixMillis").unwrap_or(0);
        if expires > now && !renew {
            return Err(format!("active lease already exists: {lease_id}"));
        }
        replaced_expired = expires <= now;
    }
    let expires_at = now + ttl_millis;
    let mut lease = BTreeMap::new();
    lease.insert(
        "schema".into(),
        JsonValue::string("agentlab.harmony_ops.workspace_lease.v1"),
    );
    lease.insert("leaseId".into(), JsonValue::string(lease_id));
    lease.insert(
        "candidateTaskId".into(),
        JsonValue::string(candidate_task_id),
    );
    lease.insert(
        "candidateTaskRoot".into(),
        JsonValue::string(candidate_root.display().to_string()),
    );
    lease.insert("createdAtUnixMillis".into(), JsonValue::Number(now));
    lease.insert("expiresAtUnixMillis".into(), JsonValue::Number(expires_at));
    lease.insert("ttlMillis".into(), JsonValue::Number(ttl_millis));
    fs::write(&lease_path, json_object_pretty(&lease))
        .map_err(|error| format!("failed to write lease: {error}"))?;
    let mut evidence = lease;
    evidence.insert(
        "leasePath".into(),
        JsonValue::string(lease_path.display().to_string()),
    );
    evidence.insert("renew".into(), JsonValue::Bool(renew));
    evidence.insert("replacedExpired".into(), JsonValue::Bool(replaced_expired));
    Ok(Receipt::new(
        "harmony.workspace.lease",
        alharmony_ops_core::SideEffect::WorkspaceWrite,
    )
    .evidence("workspaceLease", JsonValue::Object(evidence))
    .next("harmony.task.fork"))
}

fn workspace_release(
    config: &ServiceConfig,
    params: &BTreeMap<String, String>,
) -> Result<Receipt, String> {
    let task_root = config
        .task_root
        .as_ref()
        .ok_or_else(|| "workspace release requires service --task-root".to_string())?;
    let lease_id = required_param(params, "leaseId")?;
    validate_task_id(lease_id)?;
    let lease_path = task_root.join("_leases").join(format!("{lease_id}.json"));
    let existed = lease_path.is_file();
    if existed {
        fs::remove_file(&lease_path).map_err(|error| format!("failed to remove lease: {error}"))?;
    }
    let mut evidence = BTreeMap::new();
    evidence.insert("leaseId".into(), JsonValue::string(lease_id));
    evidence.insert(
        "leasePath".into(),
        JsonValue::string(lease_path.display().to_string()),
    );
    evidence.insert("existed".into(), JsonValue::Bool(existed));
    Ok(Receipt::new(
        "harmony.workspace.release",
        alharmony_ops_core::SideEffect::WorkspaceWrite,
    )
    .evidence("workspaceRelease", JsonValue::Object(evidence))
    .next("harmony.workspace.gc"))
}

fn workspace_gc(
    config: &ServiceConfig,
    params: &BTreeMap<String, String>,
) -> Result<Receipt, String> {
    let task_root = config
        .task_root
        .as_ref()
        .ok_or_else(|| "workspace gc requires service --task-root".to_string())?;
    let keep_last = params
        .get("keepLast")
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(64);
    let max_delete = params
        .get("maxDelete")
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(16)
        .min(256);
    let max_bytes = params
        .get("maxBytes")
        .and_then(|value| value.parse::<u64>().ok());
    let execute = param_bool(params, "execute");
    let leased = active_leased_tasks(task_root)?;
    let mut candidates = workspace_candidates(config)?;
    candidates.sort_by(|a, b| a.updated_at.cmp(&b.updated_at));
    let total = candidates.len();
    let mut candidate_sizes: BTreeMap<String, u64> = BTreeMap::new();
    let mut total_bytes = 0_u64;
    for candidate in &candidates {
        let size = dir_size(&candidate.task_root);
        total_bytes = total_bytes.saturating_add(size);
        candidate_sizes.insert(candidate.task_id.clone(), size);
    }
    let reclaim_window = total.saturating_sub(keep_last);
    let mut planned = Vec::new();
    let mut planned_freed_bytes = 0_u64;
    let mut remaining_bytes = total_bytes;
    for candidate in candidates.iter().take(reclaim_window) {
        if planned.len() >= max_delete {
            break;
        }
        if leased.contains(&candidate.task_id) {
            continue;
        }
        let need_by_count =
            planned.len() < reclaim_window.saturating_sub(leased.len()).min(max_delete);
        let need_by_bytes = max_bytes.is_some_and(|limit| remaining_bytes > limit);
        if !need_by_count && !need_by_bytes {
            continue;
        }
        let size = *candidate_sizes.get(&candidate.task_id).unwrap_or(&0);
        planned.push(candidate.task_id.clone());
        planned_freed_bytes = planned_freed_bytes.saturating_add(size);
        remaining_bytes = remaining_bytes.saturating_sub(size);
        if max_bytes.is_some_and(|limit| remaining_bytes <= limit)
            && planned.len() >= reclaim_window.saturating_sub(leased.len()).min(max_delete)
        {
            break;
        }
    }
    let mut deleted = 0_usize;
    let mut deleted_bytes = 0_u64;
    if execute {
        for task_id in &planned {
            validate_task_id(task_id)?;
            let root = task_root.join(task_id);
            let bytes = *candidate_sizes.get(task_id).unwrap_or(&dir_size(&root));
            if root.is_dir() {
                fs::remove_dir_all(&root)
                    .map_err(|error| format!("failed to delete task {task_id}: {error}"))?;
                deleted += 1;
                deleted_bytes = deleted_bytes.saturating_add(bytes);
            }
        }
    }
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "taskRoot".into(),
        JsonValue::string(task_root.display().to_string()),
    );
    evidence.insert("candidateCount".into(), JsonValue::Number(total as i128));
    evidence.insert(
        "leasedTaskCount".into(),
        JsonValue::Number(leased.len() as i128),
    );
    evidence.insert("keepLast".into(), JsonValue::Number(keep_last as i128));
    evidence.insert("maxDelete".into(), JsonValue::Number(max_delete as i128));
    evidence.insert("totalBytes".into(), JsonValue::Number(total_bytes as i128));
    evidence.insert(
        "maxBytes".into(),
        max_bytes
            .map(|value| JsonValue::Number(value as i128))
            .unwrap_or(JsonValue::Null),
    );
    evidence.insert("execute".into(), JsonValue::Bool(execute));
    evidence.insert(
        "plannedDeletes".into(),
        JsonValue::Array(
            planned
                .iter()
                .map(|task_id| JsonValue::string(task_id))
                .collect(),
        ),
    );
    evidence.insert(
        "reclaimWindow".into(),
        JsonValue::Number(reclaim_window as i128),
    );
    evidence.insert(
        "plannedFreedBytes".into(),
        JsonValue::Number(planned_freed_bytes as i128),
    );
    evidence.insert(
        "projectedBytesAfterPlan".into(),
        JsonValue::Number(total_bytes.saturating_sub(planned_freed_bytes) as i128),
    );
    evidence.insert("deletedCount".into(), JsonValue::Number(deleted as i128));
    evidence.insert(
        "deletedBytes".into(),
        JsonValue::Number(deleted_bytes as i128),
    );
    let side_effect = if execute && deleted > 0 {
        alharmony_ops_core::SideEffect::WorkspaceWrite
    } else {
        alharmony_ops_core::SideEffect::ReadOnly
    };
    Ok(Receipt::new("harmony.workspace.gc", side_effect)
        .evidence("workspaceGc", JsonValue::Object(evidence))
        .next("harmony.workspace.index"))
}

fn active_leased_tasks(task_root: &Path) -> Result<BTreeSet<String>, String> {
    let mut out = BTreeSet::new();
    let leases_dir = task_root.join("_leases");
    if !leases_dir.is_dir() {
        return Ok(out);
    }
    let now = now_millis();
    let read_dir = fs::read_dir(&leases_dir)
        .map_err(|error| format!("failed to read lease dir {}: {error}", leases_dir.display()))?;
    for entry in read_dir.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let Ok(body) = fs::read_to_string(&path) else {
            continue;
        };
        let expires = json_number_field(&body, "expiresAtUnixMillis").unwrap_or(0);
        if expires <= now {
            let _ = fs::remove_file(&path);
            continue;
        }
        if let Some(task_id) = json_string_field(&body, "candidateTaskId") {
            out.insert(task_id);
        }
    }
    Ok(out)
}

fn dir_size(path: &Path) -> u64 {
    let Ok(meta) = fs::metadata(path) else {
        return 0;
    };
    if meta.is_file() {
        return meta.len();
    }
    if !meta.is_dir() {
        return 0;
    }
    let Ok(read_dir) = fs::read_dir(path) else {
        return 0;
    };
    read_dir
        .flatten()
        .map(|entry| dir_size(&entry.path()))
        .sum()
}

fn project_fingerprint(project_root: &Path, harmony_home: &Path) -> Result<Receipt, String> {
    let input = build_input_fingerprint(project_root, harmony_home)?;
    let partitions = build_partition_fingerprints(project_root, harmony_home)?;
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "projectRoot".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    evidence.insert(
        "harmonyHome".into(),
        JsonValue::string(harmony_home.display().to_string()),
    );
    evidence.insert(
        "inputFingerprint".into(),
        JsonValue::string(input.fingerprint),
    );
    evidence.insert(
        "inputFileCount".into(),
        JsonValue::Number(input.file_count as i128),
    );
    evidence.insert(
        "inputBytes".into(),
        JsonValue::Number(input.total_bytes as i128),
    );
    insert_partition_evidence(&mut evidence, &partitions);
    Ok(Receipt::new(
        "harmony.project.fingerprint",
        alharmony_ops_core::SideEffect::ReadOnly,
    )
    .evidence("fingerprint", JsonValue::Object(evidence))
    .next("harmony.workspace.match"))
}

fn insert_partition_evidence(
    evidence: &mut BTreeMap<String, JsonValue>,
    partitions: &BTreeMap<String, FingerprintSummary>,
) {
    let mut fp = BTreeMap::new();
    let mut counts = BTreeMap::new();
    let mut bytes = BTreeMap::new();
    for (partition, summary) in partitions {
        fp.insert(
            partition.clone(),
            JsonValue::string(summary.fingerprint.clone()),
        );
        counts.insert(
            partition.clone(),
            JsonValue::Number(summary.file_count as i128),
        );
        bytes.insert(
            partition.clone(),
            JsonValue::Number(summary.total_bytes as i128),
        );
    }
    evidence.insert("partitionFingerprints".into(), JsonValue::Object(fp));
    evidence.insert("partitionFileCounts".into(), JsonValue::Object(counts));
    evidence.insert("partitionBytes".into(), JsonValue::Object(bytes));
}

fn build_partition_fingerprints(
    project_root: &Path,
    harmony_home: &Path,
) -> Result<BTreeMap<String, FingerprintSummary>, String> {
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    for rel in [
        "hvigorfile.ts",
        "hvigor/hvigor-config.json5",
        "build-profile.json5",
        "oh-package.json5",
        "oh-package-lock.json5",
        "AppScope",
        "entry/hvigorfile.ts",
        "entry/build-profile.json5",
        "entry/oh-package.json5",
        "entry/oh-package-lock.json5",
        "entry/src",
    ] {
        collect_existing_files(project_root, Path::new(rel), &mut files)?;
    }
    let mut by_partition: BTreeMap<String, Vec<(String, PathBuf)>> = BTreeMap::new();
    for (rel, path) in files {
        by_partition
            .entry(classify_project_partition(&rel).to_string())
            .or_default()
            .push((rel, path));
    }
    let mut sdk = Vec::new();
    for rel in ["version.txt", "bin/hvigorw", "bin/ohpm"] {
        let path = harmony_home.join(rel);
        if path.is_file() {
            sdk.push((format!("sdk/{rel}"), path));
        }
    }
    if !sdk.is_empty() {
        by_partition.insert("sdk".into(), sdk);
    }
    let mut out = BTreeMap::new();
    for (partition, entries) in by_partition {
        out.insert(
            partition.clone(),
            fingerprint_entries(&format!("partition:{partition}"), &entries)?,
        );
    }
    Ok(out)
}

fn known_partitions() -> &'static [&'static str] {
    &[
        "arkts",
        "resources",
        "profile",
        "dependencies",
        "build-script",
        "other",
        "sdk",
    ]
}

fn partition_field_prefix(partition: &str) -> &'static str {
    match partition {
        "arkts" => "arkts",
        "resources" => "resources",
        "profile" => "profile",
        "dependencies" => "dependencies",
        "build-script" => "buildScript",
        "other" => "other",
        "sdk" => "sdk",
        _ => "unknown",
    }
}

fn partition_fingerprint_param(partition: &str) -> String {
    format!("{}Fingerprint", partition_field_prefix(partition))
}

fn partition_weight(partition: &str) -> i128 {
    match partition {
        "arkts" => 260,
        "dependencies" => 240,
        "build-script" => 220,
        "profile" => 180,
        "resources" => 160,
        "sdk" => 120,
        _ => 80,
    }
}

fn partition_query_fingerprints(params: &BTreeMap<String, String>) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for partition in known_partitions() {
        let key = partition_fingerprint_param(partition);
        if let Some(value) = params.get(&key) {
            out.insert((*partition).to_string(), value.clone());
        }
    }
    out
}

fn parse_partition_string_fields(body: &str, suffix: &str) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for partition in known_partitions() {
        let key = format!("{}{}", partition_field_prefix(partition), suffix);
        if let Some(value) = json_string_field(body, &key) {
            out.insert((*partition).to_string(), value);
        }
    }
    out
}

fn parse_partition_number_fields(body: &str, suffix: &str) -> BTreeMap<String, i128> {
    let mut out = BTreeMap::new();
    for partition in known_partitions() {
        let key = format!("{}{}", partition_field_prefix(partition), suffix);
        if let Some(value) = json_number_field(body, &key) {
            out.insert((*partition).to_string(), value);
        }
    }
    out
}

fn partition_strings_json(values: &BTreeMap<String, String>) -> BTreeMap<String, JsonValue> {
    values
        .iter()
        .map(|(key, value)| (key.clone(), JsonValue::string(value.clone())))
        .collect()
}

fn partition_numbers_json(values: &BTreeMap<String, i128>) -> BTreeMap<String, JsonValue> {
    values
        .iter()
        .map(|(key, value)| (key.clone(), JsonValue::Number(*value)))
        .collect()
}

#[derive(Debug)]
struct SyncFile {
    rel: String,
    path: PathBuf,
    bytes: u64,
    fingerprint: String,
}

fn project_sync(
    project_root: &Path,
    source_root: &Path,
    delete_missing: bool,
    task: Option<&TaskScope>,
) -> Result<Receipt, String> {
    if !source_root.is_dir() {
        return Err(format!(
            "sourceRoot is not a directory: {}",
            source_root.display()
        ));
    }
    if normalize_path(project_root) == normalize_path(source_root) {
        return Err("sourceRoot must differ from projectRoot".into());
    }
    if is_path_under(source_root, project_root) || is_path_under(project_root, source_root) {
        return Err("sourceRoot and projectRoot must not contain each other".into());
    }
    let started = Instant::now();
    let source_files = collect_sync_files(source_root)?;
    let mut source_rels = BTreeSet::new();
    let mut copied_files = 0_usize;
    let mut skipped_files = 0_usize;
    let mut copied_bytes = 0_u64;
    let mut source_bytes = 0_u64;
    let mut changed_files: Vec<JsonValue> = Vec::new();
    let mut partition_counts: BTreeMap<String, i128> = BTreeMap::new();

    for file in &source_files {
        validate_project_relative_path(&file.rel)?;
        source_rels.insert(file.rel.clone());
        source_bytes += file.bytes;
        let target = normalize_path(&project_root.join(&file.rel));
        if !is_path_under(&target, project_root) {
            return Err(format!(
                "sync target must stay under projectRoot: {}",
                file.rel
            ));
        }
        let same = if target.is_file() {
            let target_fp = file_content_fingerprint(&target)?;
            target_fp.fingerprint == file.fingerprint && target_fp.total_bytes == file.bytes
        } else {
            false
        };
        if same {
            skipped_files += 1;
            continue;
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| format!("failed to create {}: {error}", parent.display()))?;
        }
        let bytes = fs::copy(&file.path, &target).map_err(|error| {
            format!(
                "failed to sync {} to {}: {error}",
                file.path.display(),
                target.display()
            )
        })?;
        copied_files += 1;
        copied_bytes += bytes;
        bump_partition(&mut partition_counts, classify_project_partition(&file.rel));
        push_limited_change(
            &mut changed_files,
            &file.rel,
            "copied",
            file.bytes,
            &file.fingerprint,
        );
    }

    let mut deleted_files = 0_usize;
    let mut deleted_bytes = 0_u64;
    if delete_missing && project_root.is_dir() {
        let target_files = collect_sync_files(project_root)?;
        for file in target_files {
            if source_rels.contains(&file.rel) {
                continue;
            }
            let target = normalize_path(&project_root.join(&file.rel));
            if !is_path_under(&target, project_root) || !target.is_file() {
                continue;
            }
            fs::remove_file(&target).map_err(|error| {
                format!("failed to delete stale file {}: {error}", target.display())
            })?;
            deleted_files += 1;
            deleted_bytes += file.bytes;
            bump_partition(&mut partition_counts, classify_project_partition(&file.rel));
            push_limited_change(
                &mut changed_files,
                &file.rel,
                "deleted",
                file.bytes,
                &file.fingerprint,
            );
        }
    }

    let changed = copied_files > 0 || deleted_files > 0;
    if let Some(task) = task {
        write_dirty_partitions(task, &partition_counts, changed_files.len())?;
    }
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "projectRoot".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    evidence.insert(
        "sourceRoot".into(),
        JsonValue::string(source_root.display().to_string()),
    );
    evidence.insert("deleteMissing".into(), JsonValue::Bool(delete_missing));
    evidence.insert("changed".into(), JsonValue::Bool(changed));
    evidence.insert(
        "sourceFiles".into(),
        JsonValue::Number(source_files.len() as i128),
    );
    evidence.insert(
        "sourceBytes".into(),
        JsonValue::Number(source_bytes as i128),
    );
    evidence.insert(
        "copiedFiles".into(),
        JsonValue::Number(copied_files as i128),
    );
    evidence.insert(
        "copiedBytes".into(),
        JsonValue::Number(copied_bytes as i128),
    );
    evidence.insert(
        "skippedFiles".into(),
        JsonValue::Number(skipped_files as i128),
    );
    evidence.insert(
        "deletedFiles".into(),
        JsonValue::Number(deleted_files as i128),
    );
    evidence.insert(
        "deletedBytes".into(),
        JsonValue::Number(deleted_bytes as i128),
    );
    evidence.insert(
        "elapsedMicros".into(),
        JsonValue::Number(started.elapsed().as_micros() as i128),
    );
    evidence.insert(
        "partitions".into(),
        JsonValue::Object(partition_count_object(&partition_counts)),
    );
    evidence.insert("changedFilesSample".into(), JsonValue::Array(changed_files));
    let side_effect = if changed {
        alharmony_ops_core::SideEffect::WorkspaceWrite
    } else {
        alharmony_ops_core::SideEffect::ReadOnly
    };
    Ok(Receipt::new("harmony.project.sync", side_effect)
        .evidence("sync", JsonValue::Object(evidence))
        .next("harmony.project.verify"))
}

fn collect_sync_files(root: &Path) -> Result<Vec<SyncFile>, String> {
    let mut out = Vec::new();
    collect_sync_files_inner(root, root, &mut out)?;
    out.sort_by(|a, b| a.rel.cmp(&b.rel));
    Ok(out)
}

fn collect_sync_files_inner(
    root: &Path,
    dir: &Path,
    out: &mut Vec<SyncFile>,
) -> Result<(), String> {
    let read_dir = fs::read_dir(dir)
        .map_err(|error| format!("failed to read sync directory {}: {error}", dir.display()))?;
    for entry in read_dir {
        let entry =
            entry.map_err(|error| format!("failed to read sync directory entry: {error}"))?;
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if should_skip_sync_name(&name) {
            continue;
        }
        let meta = entry
            .metadata()
            .map_err(|error| format!("failed to stat {}: {error}", path.display()))?;
        if meta.is_dir() {
            collect_sync_files_inner(root, &path, out)?;
        } else if meta.is_file() {
            let rel = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .display()
                .to_string();
            let fp = file_content_fingerprint(&path)?;
            out.push(SyncFile {
                rel,
                path,
                bytes: meta.len(),
                fingerprint: fp.fingerprint,
            });
        }
    }
    Ok(())
}

fn should_skip_sync_name(name: &str) -> bool {
    matches!(
        name,
        "build" | ".hvigor" | "node_modules" | "oh_modules" | ".git" | ".DS_Store"
    )
}

fn bump_partition(counts: &mut BTreeMap<String, i128>, partition: &str) {
    *counts.entry(partition.to_string()).or_insert(0) += 1;
}

fn partition_count_object(counts: &BTreeMap<String, i128>) -> BTreeMap<String, JsonValue> {
    counts
        .iter()
        .map(|(key, value)| (key.clone(), JsonValue::Number(*value)))
        .collect()
}

fn push_limited_change(
    changes: &mut Vec<JsonValue>,
    path: &str,
    action: &str,
    bytes: u64,
    fingerprint: &str,
) {
    if changes.len() >= 128 {
        return;
    }
    let mut item = BTreeMap::new();
    item.insert("path".into(), JsonValue::string(path));
    item.insert("action".into(), JsonValue::string(action));
    item.insert(
        "partition".into(),
        JsonValue::string(classify_project_partition(path)),
    );
    item.insert("bytes".into(), JsonValue::Number(bytes as i128));
    item.insert("fingerprint".into(), JsonValue::string(fingerprint));
    changes.push(JsonValue::Object(item));
}

fn write_dirty_partitions(
    task: &TaskScope,
    counts: &BTreeMap<String, i128>,
    sampled_changes: usize,
) -> Result<(), String> {
    if counts.is_empty() {
        return Ok(());
    }
    let state_dir = task.root.join("state");
    fs::create_dir_all(&state_dir)
        .map_err(|error| format!("failed to create dirty state dir: {error}"))?;
    let mut state = BTreeMap::new();
    state.insert(
        "schema".into(),
        JsonValue::string("agentlab.harmony_ops.dirty_partitions.v1"),
    );
    state.insert("taskId".into(), JsonValue::string(task.task_id.clone()));
    state.insert(
        "updatedAtUnixMillis".into(),
        JsonValue::Number(now_millis()),
    );
    state.insert(
        "partitions".into(),
        JsonValue::Object(partition_count_object(counts)),
    );
    state.insert(
        "sampledChanges".into(),
        JsonValue::Number(sampled_changes as i128),
    );
    fs::write(
        state_dir.join("dirty-partitions.json"),
        json_object_pretty(&state),
    )
    .map_err(|error| format!("failed to write dirty partition state: {error}"))
}

fn project_patch_text(
    project_root: &Path,
    rel_path: &str,
    find: &str,
    replace: &str,
    replace_all: bool,
) -> Result<Receipt, String> {
    if find.is_empty() {
        return Err("find must be non-empty".into());
    }
    validate_project_relative_path(rel_path)?;
    let target = normalize_path(&project_root.join(rel_path));
    if !is_path_under(&target, project_root) {
        return Err(format!(
            "patch target must stay under projectRoot: {rel_path}"
        ));
    }
    if !target.is_file() {
        return Err(format!("patch target is not a file: {}", target.display()));
    }
    let before = fs::read_to_string(&target)
        .map_err(|error| format!("failed to read patch target {}: {error}", target.display()))?;
    let occurrences = before.matches(find).count();
    if occurrences == 0 {
        let mut evidence = BTreeMap::new();
        evidence.insert("path".into(), JsonValue::string(rel_path));
        evidence.insert(
            "partition".into(),
            JsonValue::string(classify_project_partition(rel_path)),
        );
        evidence.insert("changed".into(), JsonValue::Bool(false));
        evidence.insert("occurrences".into(), JsonValue::Number(0));
        return Ok(Receipt::blocked(
            "harmony.project.patch",
            alharmony_ops_core::SideEffect::ReadOnly,
            alharmony_ops_core::RecoveryOwner::Agent,
            "find text was not present in the target file",
            Some("harmony.project.verify"),
        )
        .evidence("patch", JsonValue::Object(evidence)));
    }
    let before_fp = file_fingerprint(&target)?;
    let after = if replace_all {
        before.replace(find, replace)
    } else {
        before.replacen(find, replace, 1)
    };
    let changed = after != before;
    if changed {
        fs::write(&target, after).map_err(|error| {
            format!("failed to write patch target {}: {error}", target.display())
        })?;
    }
    let after_fp = file_fingerprint(&target)?;
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "projectRoot".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    evidence.insert("path".into(), JsonValue::string(rel_path));
    evidence.insert(
        "partition".into(),
        JsonValue::string(classify_project_partition(rel_path)),
    );
    evidence.insert("changed".into(), JsonValue::Bool(changed));
    evidence.insert("replaceAll".into(), JsonValue::Bool(replace_all));
    evidence.insert("occurrences".into(), JsonValue::Number(occurrences as i128));
    evidence.insert(
        "beforeFingerprint".into(),
        JsonValue::string(before_fp.fingerprint),
    );
    evidence.insert(
        "afterFingerprint".into(),
        JsonValue::string(after_fp.fingerprint),
    );
    evidence.insert(
        "afterBytes".into(),
        JsonValue::Number(after_fp.total_bytes as i128),
    );
    let side_effect = if changed {
        alharmony_ops_core::SideEffect::WorkspaceWrite
    } else {
        alharmony_ops_core::SideEffect::ReadOnly
    };
    Ok(Receipt::new("harmony.project.patch", side_effect)
        .evidence("patch", JsonValue::Object(evidence))
        .next("harmony.project.verify"))
}

fn required_param<'a>(params: &'a BTreeMap<String, String>, name: &str) -> Result<&'a str, String> {
    params
        .get(name)
        .map(String::as_str)
        .ok_or_else(|| format!("missing query parameter: {name}"))
}

fn validate_project_relative_path(rel_path: &str) -> Result<(), String> {
    if rel_path.is_empty() || rel_path.starts_with('/') || rel_path.starts_with('\\') {
        return Err("path must be a non-empty project-relative path".into());
    }
    let path = Path::new(rel_path);
    for component in path.components() {
        match component {
            Component::Normal(_) | Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err("path must not contain traversal, root, or prefix components".into());
            }
        }
    }
    Ok(())
}

fn classify_project_partition(rel_path: &str) -> &'static str {
    if rel_path.starts_with("entry/src/main/ets/") {
        "arkts"
    } else if rel_path.starts_with("entry/src/main/resources/")
        || rel_path.starts_with("AppScope/resources/")
    {
        "resources"
    } else if rel_path == "entry/src/main/module.json5"
        || rel_path.ends_with("build-profile.json5")
        || rel_path == "AppScope/app.json5"
    {
        "profile"
    } else if rel_path.contains("oh-package") {
        "dependencies"
    } else if rel_path == "hvigorfile.ts"
        || rel_path.ends_with("/hvigorfile.ts")
        || rel_path.starts_with("hvigor/")
    {
        "build-script"
    } else {
        "other"
    }
}

fn project_create_materialized(
    project_root: &Path,
    bundle_name: &str,
    app_label: &str,
) -> Result<Receipt, String> {
    let files = harmony_minimal_project_files(bundle_name, app_label);
    for (rel, content) in &files {
        write_project_file(project_root, rel, content)?;
    }
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "projectRoot".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    evidence.insert("bundleName".into(), JsonValue::string(bundle_name));
    evidence.insert("appLabel".into(), JsonValue::string(app_label));
    evidence.insert("materialized".into(), JsonValue::Bool(true));
    evidence.insert("fileCount".into(), JsonValue::Number(files.len() as i128));
    evidence.insert(
        "files".into(),
        JsonValue::Array(
            files
                .iter()
                .map(|(rel, _)| JsonValue::string(*rel))
                .collect(),
        ),
    );
    Ok(Receipt::new(
        "harmony.project.create",
        alharmony_ops_core::SideEffect::WorkspaceWrite,
    )
    .evidence("project", JsonValue::Object(evidence))
    .next("harmony.project.verify"))
}

fn write_project_file(project_root: &Path, rel: &str, content: &str) -> Result<(), String> {
    let path = project_root.join(rel);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("failed to create {}: {error}", parent.display()))?;
    }
    fs::write(&path, content)
        .map_err(|error| format!("failed to write {}: {error}", path.display()))
}

fn harmony_minimal_project_files(
    bundle_name: &str,
    app_label: &str,
) -> Vec<(&'static str, String)> {
    vec![
        (
            "hvigorfile.ts",
            "import { appTasks } from '@ohos/hvigor-ohos-plugin';\n\nexport default {\n  system: appTasks,\n  plugins: []\n};\n".into(),
        ),
        (
            "hvigor/hvigor-config.json5",
            "{\n  \"modelVersion\": \"5.0.0\",\n  \"dependencies\": {},\n  \"execution\": {\n    \"daemon\": false,\n    \"parallel\": false,\n    \"incremental\": true,\n    \"typeCheck\": false\n  },\n  \"logging\": {\n    \"level\": \"info\"\n  }\n}\n".into(),
        ),
        (
            "build-profile.json5",
            format!(
                "{{\n  \"app\": {{\n    \"signingConfigs\": [],\n    \"products\": [\n      {{\n        \"name\": \"default\",\n        \"signingConfig\": \"default\",\n        \"compatibleSdkVersion\": \"6.0.0(20)\",\n        \"runtimeOS\": \"HarmonyOS\"\n      }}\n    ],\n    \"buildModeSet\": [\n      {{ \"name\": \"debug\" }},\n      {{ \"name\": \"release\" }}\n    ]\n  }},\n  \"modules\": [\n    {{\n      \"name\": \"entry\",\n      \"srcPath\": \"./entry\",\n      \"targets\": [\n        {{ \"name\": \"default\", \"applyToProducts\": [ \"default\" ] }}\n      ]\n    }}\n  ]\n}}\n"
            ),
        ),
        (
            "oh-package.json5",
            "{\n  \"modelVersion\": \"5.0.0\",\n  \"dependencies\": {},\n  \"devDependencies\": {}\n}\n".into(),
        ),
        (
            "AppScope/app.json5",
            format!(
                "{{\n  \"app\": {{\n    \"bundleName\": \"{}\",\n    \"vendor\": \"agentlab\",\n    \"versionCode\": 1000000,\n    \"versionName\": \"1.0.0\",\n    \"icon\": \"$media:app_icon\",\n    \"label\": \"$string:app_name\"\n  }}\n}}\n",
                json_escape(bundle_name)
            ),
        ),
        (
            "AppScope/resources/base/media/app_icon.svg",
            "<svg width=\"64\" height=\"64\" viewBox=\"0 0 64 64\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"64\" height=\"64\" rx=\"12\" fill=\"#0A59F7\"/></svg>\n".into(),
        ),
        (
            "entry/hvigorfile.ts",
            "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\n\nexport default {\n  system: hapTasks,\n  plugins: []\n};\n".into(),
        ),
        (
            "entry/build-profile.json5",
            "{\n  \"apiType\": \"stageMode\",\n  \"buildOption\": {},\n  \"targets\": [\n    { \"name\": \"default\" }\n  ]\n}\n".into(),
        ),
        (
            "entry/oh-package.json5",
            "{\n  \"name\": \"entry\",\n  \"version\": \"1.0.0\",\n  \"description\": \"AgentLab Harmony E2E entry module\",\n  \"main\": \"\",\n  \"author\": \"agentlab\",\n  \"license\": \"Apache-2.0\",\n  \"dependencies\": {}\n}\n".into(),
        ),
        (
            "entry/src/main/module.json5",
            "{\n  \"module\": {\n    \"name\": \"entry\",\n    \"type\": \"entry\",\n    \"description\": \"$string:module_desc\",\n    \"mainElement\": \"EntryAbility\",\n    \"deviceTypes\": [ \"default\", \"phone\", \"tablet\" ],\n    \"deliveryWithInstall\": true,\n    \"installationFree\": false,\n    \"pages\": \"$profile:main_pages\",\n    \"abilities\": [\n      {\n        \"name\": \"EntryAbility\",\n        \"srcEntry\": \"./ets/entryability/EntryAbility.ets\",\n        \"description\": \"$string:EntryAbility_desc\",\n        \"icon\": \"$media:icon\",\n        \"label\": \"$string:EntryAbility_label\",\n        \"startWindowIcon\": \"$media:startIcon\",\n        \"startWindowBackground\": \"$color:start_window_background\",\n        \"exported\": true,\n        \"skills\": [\n          {\n            \"entities\": [ \"entity.system.home\" ],\n            \"actions\": [ \"action.system.home\" ]\n          }\n        ]\n      }\n    ]\n  }\n}\n".into(),
        ),
        (
            "entry/src/main/ets/entryability/EntryAbility.ets",
            "import { AbilityConstant, UIAbility, Want } from '@kit.AbilityKit';\nimport { hilog } from '@kit.PerformanceAnalysisKit';\nimport { window } from '@kit.ArkUI';\n\nexport default class EntryAbility extends UIAbility {\n  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {\n    hilog.info(0x0000, 'AgentLabE2E', 'Ability onCreate');\n  }\n\n  onWindowStageCreate(windowStage: window.WindowStage): void {\n    windowStage.loadContent('pages/Index');\n  }\n}\n".into(),
        ),
        (
            "entry/src/main/ets/pages/Index.ets",
            format!(
                "@Entry\n@Component\nstruct Index {{\n  @State message: string = '{}';\n\n  build() {{\n    Row() {{\n      Column() {{\n        Text(this.message)\n          .fontSize(28)\n          .fontWeight(FontWeight.Bold)\n      }}\n      .width('100%')\n    }}\n    .height('100%')\n  }}\n}}\n",
                ets_single_quote_escape(app_label)
            ),
        ),
        (
            "entry/src/main/resources/base/profile/main_pages.json",
            "{\n  \"src\": [ \"pages/Index\" ]\n}\n".into(),
        ),
        (
            "entry/src/main/resources/base/element/string.json",
            format!(
                "{{\n  \"string\": [\n    {{ \"name\": \"app_name\", \"value\": \"{}\" }},\n    {{ \"name\": \"module_desc\", \"value\": \"AgentLab E2E module\" }},\n    {{ \"name\": \"EntryAbility_desc\", \"value\": \"Entry ability\" }},\n    {{ \"name\": \"EntryAbility_label\", \"value\": \"{}\" }}\n  ]\n}}\n",
                json_escape(app_label),
                json_escape(app_label)
            ),
        ),
        (
            "entry/src/main/resources/en_US/element/string.json",
            format!(
                "{{\n  \"string\": [\n    {{ \"name\": \"app_name\", \"value\": \"{}\" }},\n    {{ \"name\": \"module_desc\", \"value\": \"AgentLab E2E module\" }},\n    {{ \"name\": \"EntryAbility_desc\", \"value\": \"Entry ability\" }},\n    {{ \"name\": \"EntryAbility_label\", \"value\": \"{}\" }}\n  ]\n}}\n",
                json_escape(app_label),
                json_escape(app_label)
            ),
        ),
        (
            "entry/src/main/resources/base/element/color.json",
            "{\n  \"color\": [\n    { \"name\": \"start_window_background\", \"value\": \"#FFFFFF\" }\n  ]\n}\n".into(),
        ),
        (
            "entry/src/main/resources/base/media/icon.svg",
            "<svg width=\"64\" height=\"64\" viewBox=\"0 0 64 64\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"64\" height=\"64\" rx=\"12\" fill=\"#0A59F7\"/></svg>\n".into(),
        ),
        (
            "entry/src/main/resources/base/media/startIcon.svg",
            "<svg width=\"64\" height=\"64\" viewBox=\"0 0 64 64\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"64\" height=\"64\" rx=\"12\" fill=\"#0A59F7\"/></svg>\n".into(),
        ),
    ]
}

fn ets_single_quote_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('\'', "\\'")
}

fn execute_ohpm_install(project_root: &Path, harmony_home: &Path) -> Result<Receipt, String> {
    execute_local_process(
        "harmony.ohpm.install",
        project_root,
        &harmony_home.join("bin/ohpm"),
        &["install"],
        Some("harmony.build.debug"),
    )
}

fn execute_build_debug(
    project_root: &Path,
    harmony_home: &Path,
    task: &TaskScope,
) -> Result<Receipt, String> {
    let input = build_input_fingerprint(project_root, harmony_home)?;
    if let Some(receipt) = try_build_cache_hit(project_root, task, &input)? {
        return Ok(receipt);
    }
    let mut receipt = execute_local_process(
        "harmony.build.debug",
        project_root,
        &harmony_home.join("bin/hvigorw"),
        &[
            "--no-daemon",
            "--no-parallel",
            "--no-type-check",
            "--analyze=false",
            "--mode",
            "module",
            "-p",
            "product=default",
            "assembleHap",
        ],
        Some("harmony.artifact.inspect"),
    )?;
    let mut cache_evidence = build_cache_evidence(task, &input, false);
    if receipt.ok {
        if let Some(artifact) = latest_artifact(project_root) {
            let artifact_fingerprint = file_fingerprint(&artifact.path)?;
            write_build_state(
                task,
                project_root,
                harmony_home,
                &input,
                &artifact,
                &artifact_fingerprint,
            )?;
            cache_evidence.insert("stateUpdated".into(), JsonValue::Bool(true));
            cache_evidence.insert(
                "artifactFingerprint".into(),
                JsonValue::string(artifact_fingerprint.fingerprint.clone()),
            );
        } else {
            cache_evidence.insert("stateUpdated".into(), JsonValue::Bool(false));
            receipt
                .diagnostics
                .push("build succeeded but no Harmony artifact was discovered".into());
        }
    } else {
        cache_evidence.insert("stateUpdated".into(), JsonValue::Bool(false));
    }
    Ok(receipt.evidence("buildCache", JsonValue::Object(cache_evidence)))
}

#[derive(Clone, Debug)]
struct FingerprintSummary {
    fingerprint: String,
    file_count: usize,
    total_bytes: u64,
}

#[derive(Clone, Debug)]
struct ArtifactSummary {
    path: PathBuf,
    bytes: u64,
    extension: String,
}

fn build_cache_evidence(
    task: &TaskScope,
    input: &FingerprintSummary,
    cache_hit: bool,
) -> BTreeMap<String, JsonValue> {
    let mut evidence = BTreeMap::new();
    evidence.insert("cacheHit".into(), JsonValue::Bool(cache_hit));
    evidence.insert(
        "inputFingerprint".into(),
        JsonValue::string(input.fingerprint.clone()),
    );
    evidence.insert(
        "inputFileCount".into(),
        JsonValue::Number(input.file_count as i128),
    );
    evidence.insert(
        "inputBytes".into(),
        JsonValue::Number(input.total_bytes as i128),
    );
    evidence.insert(
        "statePath".into(),
        JsonValue::string(build_state_path(task).display().to_string()),
    );
    evidence
}

fn try_build_cache_hit(
    project_root: &Path,
    task: &TaskScope,
    input: &FingerprintSummary,
) -> Result<Option<Receipt>, String> {
    let state_path = build_state_path(task);
    let Ok(state) = fs::read_to_string(&state_path) else {
        return Ok(None);
    };
    let Some(prior_input) = json_string_field(&state, "inputFingerprint") else {
        return Ok(None);
    };
    if prior_input != input.fingerprint {
        return Ok(None);
    }
    let Some(artifact_path) = json_string_field(&state, "artifactPath") else {
        return Ok(None);
    };
    let artifact = PathBuf::from(artifact_path);
    if !artifact.is_file() {
        return Ok(None);
    }
    if !is_path_under(&artifact, project_root) {
        return Ok(None);
    }
    let actual = file_fingerprint(&artifact)?;
    let Some(expected_artifact_fp) = json_string_field(&state, "artifactFingerprint") else {
        return Ok(None);
    };
    let expected_bytes = json_number_field(&state, "artifactBytes").unwrap_or(-1);
    if expected_artifact_fp != actual.fingerprint || expected_bytes != actual.total_bytes as i128 {
        return Ok(None);
    }
    let mut cache = build_cache_evidence(task, input, true);
    cache.insert(
        "artifactPath".into(),
        JsonValue::string(artifact.display().to_string()),
    );
    cache.insert(
        "artifactBytes".into(),
        JsonValue::Number(actual.total_bytes as i128),
    );
    cache.insert(
        "artifactFingerprint".into(),
        JsonValue::string(actual.fingerprint),
    );
    cache.insert("stateMatched".into(), JsonValue::Bool(true));
    Ok(Some(
        Receipt::new("harmony.build.debug", alharmony_ops_core::SideEffect::ReadOnly)
            .evidence("buildCache", JsonValue::Object(cache))
            .diagnostic("Skipped hvigor because the task build input fingerprint matched the last successful unsigned artifact.")
            .next("harmony.artifact.inspect"),
    ))
}

fn write_build_state(
    task: &TaskScope,
    project_root: &Path,
    harmony_home: &Path,
    input: &FingerprintSummary,
    artifact: &ArtifactSummary,
    artifact_fingerprint: &FingerprintSummary,
) -> Result<(), String> {
    let state_dir = task.root.join("state");
    fs::create_dir_all(&state_dir)
        .map_err(|error| format!("failed to create build state dir: {error}"))?;
    let mut state = BTreeMap::new();
    state.insert(
        "schema".into(),
        JsonValue::string("agentlab.harmony_ops.build_state.v1"),
    );
    state.insert("operation".into(), JsonValue::string("harmony.build.debug"));
    state.insert("taskId".into(), JsonValue::string(task.task_id.clone()));
    state.insert(
        "taskRoot".into(),
        JsonValue::string(task.root.display().to_string()),
    );
    state.insert(
        "projectRoot".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    state.insert(
        "harmonyHome".into(),
        JsonValue::string(harmony_home.display().to_string()),
    );
    state.insert(
        "inputFingerprint".into(),
        JsonValue::string(input.fingerprint.clone()),
    );
    state.insert(
        "inputFileCount".into(),
        JsonValue::Number(input.file_count as i128),
    );
    state.insert(
        "inputBytes".into(),
        JsonValue::Number(input.total_bytes as i128),
    );
    state.insert(
        "artifactPath".into(),
        JsonValue::string(artifact.path.display().to_string()),
    );
    state.insert(
        "artifactBytes".into(),
        JsonValue::Number(artifact.bytes as i128),
    );
    state.insert(
        "artifactExtension".into(),
        JsonValue::string(artifact.extension.clone()),
    );
    state.insert(
        "artifactFingerprint".into(),
        JsonValue::string(artifact_fingerprint.fingerprint.clone()),
    );
    let partitions = build_partition_fingerprints(project_root, harmony_home)?;
    insert_partition_evidence(&mut state, &partitions);
    for (partition, summary) in &partitions {
        let prefix = partition_field_prefix(partition);
        state.insert(
            format!("{prefix}Fingerprint"),
            JsonValue::string(summary.fingerprint.clone()),
        );
        state.insert(
            format!("{prefix}FileCount"),
            JsonValue::Number(summary.file_count as i128),
        );
        state.insert(
            format!("{prefix}Bytes"),
            JsonValue::Number(summary.total_bytes as i128),
        );
    }
    state.insert(
        "updatedAtUnixMillis".into(),
        JsonValue::Number(now_millis()),
    );
    fs::write(build_state_path(task), json_object_pretty(&state))
        .map_err(|error| format!("failed to write build state: {error}"))
}

fn build_state_path(task: &TaskScope) -> PathBuf {
    task.root.join("state/build-state.json")
}

fn build_input_fingerprint(
    project_root: &Path,
    harmony_home: &Path,
) -> Result<FingerprintSummary, String> {
    let mut entries: Vec<(String, PathBuf)> = Vec::new();
    for rel in [
        "hvigorfile.ts",
        "hvigor/hvigor-config.json5",
        "build-profile.json5",
        "oh-package.json5",
        "oh-package-lock.json5",
        "AppScope",
        "entry/hvigorfile.ts",
        "entry/build-profile.json5",
        "entry/oh-package.json5",
        "entry/oh-package-lock.json5",
        "entry/src",
    ] {
        collect_existing_files(project_root, Path::new(rel), &mut entries)?;
    }
    for rel in ["version.txt", "bin/hvigorw", "bin/ohpm"] {
        collect_existing_files(harmony_home, Path::new(rel), &mut entries)?;
    }
    fingerprint_entries("build-input", &entries)
}

fn file_fingerprint(path: &Path) -> Result<FingerprintSummary, String> {
    fingerprint_entries("file", &[(path.display().to_string(), path.to_path_buf())])
}

fn file_content_fingerprint(path: &Path) -> Result<FingerprintSummary, String> {
    fingerprint_entries(
        "file-content",
        &[("content".to_string(), path.to_path_buf())],
    )
}

fn collect_existing_files(
    root: &Path,
    rel: &Path,
    out: &mut Vec<(String, PathBuf)>,
) -> Result<(), String> {
    let path = root.join(rel);
    if path.is_file() {
        out.push((rel.display().to_string(), path));
    } else if path.is_dir() {
        collect_dir_files(root, &path, out)?;
    }
    Ok(())
}

fn collect_dir_files(
    root: &Path,
    dir: &Path,
    out: &mut Vec<(String, PathBuf)>,
) -> Result<(), String> {
    let read_dir = fs::read_dir(dir)
        .map_err(|error| format!("failed to read directory {}: {error}", dir.display()))?;
    for entry in read_dir {
        let entry = entry.map_err(|error| format!("failed to read directory entry: {error}"))?;
        let path = entry.path();
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name == "build" || name == ".hvigor" || name == "node_modules" || name == "oh_modules" {
            continue;
        }
        let meta = entry
            .metadata()
            .map_err(|error| format!("failed to stat {}: {error}", path.display()))?;
        if meta.is_dir() {
            collect_dir_files(root, &path, out)?;
        } else if meta.is_file() {
            let rel = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .display()
                .to_string();
            out.push((rel, path));
        }
    }
    Ok(())
}

fn fingerprint_entries(
    namespace: &str,
    entries: &[(String, PathBuf)],
) -> Result<FingerprintSummary, String> {
    let mut sorted = entries.to_vec();
    sorted.sort_by(|a, b| a.0.cmp(&b.0));
    let mut hash = FNV_OFFSET;
    update_hash(&mut hash, namespace.as_bytes());
    let mut total_bytes = 0_u64;
    let mut file_count = 0_usize;
    for (rel, path) in sorted {
        let data = fs::read(&path).map_err(|error| {
            format!(
                "failed to read fingerprint input {}: {error}",
                path.display()
            )
        })?;
        update_hash(&mut hash, rel.as_bytes());
        update_hash(&mut hash, b"\0");
        update_hash(&mut hash, data.len().to_string().as_bytes());
        update_hash(&mut hash, b"\0");
        update_hash(&mut hash, &data);
        file_count += 1;
        total_bytes += data.len() as u64;
    }
    Ok(FingerprintSummary {
        fingerprint: format!("fnv1a64:{hash:016x}"),
        file_count,
        total_bytes,
    })
}

const FNV_OFFSET: u64 = 0xcbf29ce484222325;
const FNV_PRIME: u64 = 0x100000001b3;

fn update_hash(hash: &mut u64, bytes: &[u8]) {
    for byte in bytes {
        *hash ^= *byte as u64;
        *hash = hash.wrapping_mul(FNV_PRIME);
    }
}

fn latest_artifact(root: &Path) -> Option<ArtifactSummary> {
    let mut artifacts = Vec::new();
    collect_artifact_summaries(root, &mut artifacts, 0);
    artifacts.sort_by_key(|artifact| {
        fs::metadata(&artifact.path)
            .and_then(|meta| meta.modified())
            .ok()
    });
    artifacts.pop()
}

fn collect_artifact_summaries(path: &Path, out: &mut Vec<ArtifactSummary>, depth: usize) {
    if depth > 24 || out.len() >= 64 {
        return;
    }
    let Ok(read_dir) = fs::read_dir(path) else {
        return;
    };
    for entry in read_dir.flatten() {
        let p = entry.path();
        let Ok(meta) = entry.metadata() else {
            continue;
        };
        if meta.is_dir() {
            collect_artifact_summaries(&p, out, depth + 1);
        } else if meta.is_file() {
            let ext = p
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or("")
                .to_string();
            if matches!(ext.as_str(), "hap" | "app" | "har" | "hsp") {
                out.push(ArtifactSummary {
                    path: p,
                    bytes: meta.len(),
                    extension: ext,
                });
            }
        }
    }
}

fn json_string_field(body: &str, key: &str) -> Option<String> {
    let pattern = format!("\"{key}\"");
    let start = body.find(&pattern)? + pattern.len();
    let rest = &body[start..];
    let colon = rest.find(':')?;
    let rest = rest[colon + 1..].trim_start();
    if !rest.starts_with('"') {
        return None;
    }
    parse_json_string(rest)
}

fn json_number_field(body: &str, key: &str) -> Option<i128> {
    let pattern = format!("\"{key}\"");
    let start = body.find(&pattern)? + pattern.len();
    let rest = &body[start..];
    let colon = rest.find(':')?;
    let mut rest = rest[colon + 1..].trim_start();
    let end = rest
        .find(|ch: char| !(ch == '-' || ch.is_ascii_digit()))
        .unwrap_or(rest.len());
    rest = &rest[..end];
    rest.parse::<i128>().ok()
}

fn parse_json_string(value: &str) -> Option<String> {
    let mut chars = value.chars();
    if chars.next()? != '"' {
        return None;
    }
    let mut out = String::new();
    let mut escaped = false;
    for ch in chars {
        if escaped {
            match ch {
                '"' => out.push('"'),
                '\\' => out.push('\\'),
                '/' => out.push('/'),
                'n' => out.push('\n'),
                'r' => out.push('\r'),
                't' => out.push('\t'),
                other => out.push(other),
            }
            escaped = false;
        } else if ch == '\\' {
            escaped = true;
        } else if ch == '"' {
            return Some(out);
        } else {
            out.push(ch);
        }
    }
    None
}

fn is_path_under(path: &Path, root: &Path) -> bool {
    let path = normalize_path(path);
    let root = normalize_path(root);
    path == root || path.starts_with(root)
}

fn execute_local_process(
    operation: &'static str,
    project_root: &Path,
    command: &Path,
    args: &[&str],
    next_action: Option<&'static str>,
) -> Result<Receipt, String> {
    if !project_root.is_dir() {
        return Err(format!(
            "projectRoot does not exist: {}",
            project_root.display()
        ));
    }
    if !command.is_file() {
        return Err(format!("command does not exist: {}", command.display()));
    }
    let started = Instant::now();
    let output = Command::new(command)
        .args(args)
        .current_dir(project_root)
        .output()
        .map_err(|error| format!("failed to execute {}: {error}", command.display()))?;
    let elapsed_ms = started.elapsed().as_millis() as i128;
    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    let mut evidence = BTreeMap::new();
    evidence.insert(
        "cwd".into(),
        JsonValue::string(project_root.display().to_string()),
    );
    evidence.insert(
        "command".into(),
        JsonValue::string(command.display().to_string()),
    );
    evidence.insert(
        "args".into(),
        JsonValue::Array(args.iter().map(|arg| JsonValue::string(*arg)).collect()),
    );
    evidence.insert(
        "exitCode".into(),
        JsonValue::Number(output.status.code().unwrap_or(-1) as i128),
    );
    evidence.insert("elapsedMillis".into(), JsonValue::Number(elapsed_ms));
    evidence.insert(
        "stdoutTail".into(),
        JsonValue::string(tail_chars(&stdout, 4096)),
    );
    evidence.insert(
        "stderrTail".into(),
        JsonValue::string(tail_chars(&stderr, 4096)),
    );
    let artifacts = find_artifacts(project_root);
    if !artifacts.is_empty() {
        evidence.insert("artifacts".into(), JsonValue::Array(artifacts));
    }
    let mut receipt = Receipt::new(operation, alharmony_ops_core::SideEffect::LocalProcess)
        .evidence("execution", JsonValue::Object(evidence));
    receipt.ok = output.status.success();
    receipt.next_action = if output.status.success() {
        next_action
    } else {
        Some("harmony.project.verify")
    };
    if !output.status.success() {
        receipt.recovery_owner = alharmony_ops_core::RecoveryOwner::Agent;
        receipt
            .diagnostics
            .push(format!("{operation} command failed"));
    }
    Ok(receipt)
}

fn tail_chars(value: &str, max_chars: usize) -> String {
    let chars: Vec<char> = value.chars().collect();
    let start = chars.len().saturating_sub(max_chars);
    chars[start..].iter().collect()
}

fn find_artifacts(root: &Path) -> Vec<JsonValue> {
    let mut out = Vec::new();
    collect_artifacts(root, &mut out, 0);
    out
}

fn collect_artifacts(path: &Path, out: &mut Vec<JsonValue>, depth: usize) {
    if depth > 24 || out.len() >= 64 {
        return;
    }
    let Ok(read_dir) = fs::read_dir(path) else {
        return;
    };
    for entry in read_dir.flatten() {
        let p = entry.path();
        let Ok(meta) = entry.metadata() else {
            continue;
        };
        if meta.is_dir() {
            collect_artifacts(&p, out, depth + 1);
        } else if meta.is_file() {
            let ext = p.extension().and_then(|value| value.to_str()).unwrap_or("");
            if matches!(ext, "hap" | "app" | "har" | "hsp") {
                let mut item = BTreeMap::new();
                item.insert("path".into(), JsonValue::string(p.display().to_string()));
                item.insert("bytes".into(), JsonValue::Number(meta.len() as i128));
                item.insert("extension".into(), JsonValue::string(ext));
                out.push(JsonValue::Object(item));
            }
        }
    }
}

fn param_bool(params: &BTreeMap<String, String>, name: &str) -> bool {
    matches!(
        params.get(name).map(String::as_str),
        Some("1" | "true" | "yes" | "on")
    )
}

fn task_fork(
    child: &TaskScope,
    parent_task_id: &str,
    config: &ServiceConfig,
) -> Result<Receipt, String> {
    validate_task_id(parent_task_id)?;
    let Some(pool_root) = child.root.parent() else {
        return Err("child task root has no parent pool root".into());
    };
    let parent_root = normalize_path(&pool_root.join(parent_task_id));
    if !parent_root.is_dir() {
        return Err(format!("parent task does not exist: {parent_task_id}"));
    }
    if child.root == parent_root {
        return Err("child taskId must differ from parentTaskId".into());
    }
    if child.root.exists() && !is_empty_dir(&child.root)? {
        return Err(format!(
            "child task root already exists and is not empty: {}",
            child.root.display()
        ));
    }
    let fork_result = fork_task_storage(&parent_root, &child.root, config)?;
    for rel in [
        "workspace",
        "artifacts",
        "tmp",
        "receipts",
        "state",
        "cache",
    ] {
        fs::create_dir_all(child.root.join(rel))
            .map_err(|error| format!("failed to ensure child task dir {rel}: {error}"))?;
    }
    rewrite_forked_state_paths(&child.root, &parent_root, child, parent_task_id)?;
    let refreshed_state = refresh_forked_build_state(&child.root, child)?;
    let mut manifest = BTreeMap::new();
    manifest.insert("taskId".into(), JsonValue::string(child.task_id.clone()));
    manifest.insert("parentTaskId".into(), JsonValue::string(parent_task_id));
    manifest.insert(
        "taskRoot".into(),
        JsonValue::string(child.root.display().to_string()),
    );
    manifest.insert(
        "parentTaskRoot".into(),
        JsonValue::string(parent_root.display().to_string()),
    );
    manifest.insert("forkedAtUnixMillis".into(), JsonValue::Number(now_millis()));
    manifest.insert(
        "forkStrategy".into(),
        JsonValue::string(fork_result.strategy.clone()),
    );
    manifest.insert(
        "workspace".into(),
        JsonValue::string(child.root.join("workspace").display().to_string()),
    );
    manifest.insert(
        "artifacts".into(),
        JsonValue::string(child.root.join("artifacts").display().to_string()),
    );
    manifest.insert(
        "tmp".into(),
        JsonValue::string(child.root.join("tmp").display().to_string()),
    );
    manifest.insert(
        "receipts".into(),
        JsonValue::string(child.root.join("receipts").display().to_string()),
    );
    manifest.insert(
        "state".into(),
        JsonValue::string(child.root.join("state").display().to_string()),
    );
    manifest.insert(
        "cache".into(),
        JsonValue::string(child.root.join("cache").display().to_string()),
    );
    fs::write(child.root.join("task.json"), json_object_pretty(&manifest))
        .map_err(|error| format!("failed to write child task manifest: {error}"))?;
    let mut evidence = BTreeMap::new();
    evidence.insert("parentTaskId".into(), JsonValue::string(parent_task_id));
    evidence.insert(
        "childTaskId".into(),
        JsonValue::string(child.task_id.clone()),
    );
    evidence.insert("strategy".into(), JsonValue::string(fork_result.strategy));
    evidence.insert("backend".into(), JsonValue::string(fork_result.backend));
    evidence.insert("fallback".into(), JsonValue::Bool(fork_result.fallback));
    evidence.insert(
        "copiedFiles".into(),
        JsonValue::Number(fork_result.copied_files as i128),
    );
    evidence.insert(
        "copiedBytes".into(),
        JsonValue::Number(fork_result.copied_bytes as i128),
    );
    evidence.insert(
        "elapsedMicros".into(),
        JsonValue::Number(fork_result.elapsed_micros as i128),
    );
    evidence.insert(
        "parentTaskRoot".into(),
        JsonValue::string(parent_root.display().to_string()),
    );
    evidence.insert(
        "childTaskRoot".into(),
        JsonValue::string(child.root.display().to_string()),
    );
    evidence.insert("sessionForkSemantics".into(), JsonValue::Bool(true));
    evidence.insert(
        "buildStateRefreshed".into(),
        JsonValue::Bool(refreshed_state),
    );
    Ok(Receipt::new(
        "harmony.task.fork",
        alharmony_ops_core::SideEffect::WorkspaceWrite,
    )
    .evidence("fork", JsonValue::Object(evidence))
    .evidence("task", JsonValue::Object(manifest))
    .next("harmony.project.patch"))
}

#[derive(Debug)]
struct ForkStorageResult {
    backend: String,
    strategy: String,
    fallback: bool,
    copied_files: usize,
    copied_bytes: u64,
    elapsed_micros: u128,
}

fn fork_task_storage(
    parent_root: &Path,
    child_root: &Path,
    config: &ServiceConfig,
) -> Result<ForkStorageResult, String> {
    match config.fork_backend.as_str() {
        "copy-tree" => fork_task_storage_copy(parent_root, child_root, false),
        "sessionfs" => fork_task_storage_sessionfs(parent_root, child_root, config, false),
        "auto" => match fork_task_storage_sessionfs(parent_root, child_root, config, false) {
            Ok(result) => Ok(result),
            Err(error) => {
                if child_root.exists() {
                    fs::remove_dir_all(child_root).map_err(|cleanup_error| {
                        format!(
                            "sessionfs fork failed ({error}); failed to clean child root for fallback: {cleanup_error}"
                        )
                    })?;
                }
                let mut result = fork_task_storage_copy(parent_root, child_root, true)?;
                result.backend = "copy-tree-fallback".into();
                Ok(result)
            }
        },
        other => Err(format!("unsupported fork backend: {other}")),
    }
}

fn fork_task_storage_copy(
    parent_root: &Path,
    child_root: &Path,
    fallback: bool,
) -> Result<ForkStorageResult, String> {
    let started = Instant::now();
    let mut copied_files = 0_usize;
    let mut copied_bytes = 0_u64;
    fs::create_dir_all(child_root)
        .map_err(|error| format!("failed to create child task root: {error}"))?;
    for rel in ["workspace", "artifacts", "state", "cache"] {
        let from = parent_root.join(rel);
        let to = child_root.join(rel);
        if from.exists() {
            copy_tree(&from, &to, &mut copied_files, &mut copied_bytes)?;
        } else {
            fs::create_dir_all(&to)
                .map_err(|error| format!("failed to create {}: {error}", to.display()))?;
        }
    }
    for rel in ["receipts", "tmp"] {
        fs::create_dir_all(child_root.join(rel))
            .map_err(|error| format!("failed to create child task dir {rel}: {error}"))?;
    }
    Ok(ForkStorageResult {
        backend: if fallback {
            "copy-tree-fallback".into()
        } else {
            "copy-tree".into()
        },
        strategy: if fallback {
            "copy-tree-fallback".into()
        } else {
            "copy-tree".into()
        },
        fallback,
        copied_files,
        copied_bytes,
        elapsed_micros: started.elapsed().as_micros(),
    })
}

fn fork_task_storage_sessionfs(
    parent_root: &Path,
    child_root: &Path,
    config: &ServiceConfig,
    fallback: bool,
) -> Result<ForkStorageResult, String> {
    let endpoint = config
        .sessionfs_endpoint
        .as_deref()
        .ok_or_else(|| "sessionfs endpoint is not configured".to_string())?;
    let body = sessionfs_fork_http(endpoint, parent_root, child_root)?;
    Ok(ForkStorageResult {
        backend: json_string_field(&body, "backend").unwrap_or_else(|| "sessionfs".into()),
        strategy: "sessionfs".into(),
        fallback,
        copied_files: json_number_field(&body, "copiedFiles").unwrap_or(0).max(0) as usize,
        copied_bytes: json_number_field(&body, "copiedBytes").unwrap_or(0).max(0) as u64,
        elapsed_micros: json_number_field(&body, "elapsedMicros")
            .unwrap_or(0)
            .max(0) as u128,
    })
}

fn sessionfs_fork_http(
    endpoint: &str,
    parent_root: &Path,
    child_root: &Path,
) -> Result<String, String> {
    let endpoint = endpoint.trim_end_matches('/');
    let url = format!(
        "{}/v1/sessions/fork?parentRoot={}&childRoot={}&include=workspace,artifacts,state,cache&reset=receipts,tmp",
        endpoint,
        percent_encode(&parent_root.display().to_string()),
        percent_encode(&child_root.display().to_string())
    );
    let (status, body) = http_get(&url)?;
    if status != 200 {
        return Err(format!(
            "sessionfs fork returned HTTP {status}: {}",
            tail_chars(&body, 512)
        ));
    }
    if !(body.contains("\"ok\": true") || body.contains("\"ok\":true")) {
        return Err(format!(
            "sessionfs fork did not return ok=true: {}",
            tail_chars(&body, 512)
        ));
    }
    Ok(body)
}

fn http_get(url: &str) -> Result<(u16, String), String> {
    let rest = url.strip_prefix("http://").ok_or_else(|| {
        "only http:// sessionfs endpoints are supported in this preview".to_string()
    })?;
    let (authority, path) = match rest.split_once('/') {
        Some((authority, path)) => (authority, format!("/{path}")),
        None => (rest, "/".to_string()),
    };
    let mut stream = TcpStream::connect(authority)
        .map_err(|error| format!("failed to connect to sessionfs {authority}: {error}"))?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(30)));
    let request = format!("GET {path} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n\r\n");
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("failed to write sessionfs request: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("failed to read sessionfs response: {error}"))?;
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return Err("sessionfs response was missing header terminator".into());
    };
    let status = headers
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or_else(|| "sessionfs response had no HTTP status".to_string())?;
    Ok((status, body.to_string()))
}

fn percent_encode(value: &str) -> String {
    let mut out = String::new();
    for byte in value.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                out.push(byte as char)
            }
            other => out.push_str(&format!("%{other:02X}")),
        }
    }
    out
}

fn refresh_forked_build_state(child_root: &Path, child: &TaskScope) -> Result<bool, String> {
    let state_path = child_root.join("state/build-state.json");
    if !state_path.is_file() {
        return Ok(false);
    }
    let body = fs::read_to_string(&state_path)
        .map_err(|error| format!("failed to read forked build state: {error}"))?;
    let Some(project_root) = json_string_field(&body, "projectRoot") else {
        return Ok(false);
    };
    let Some(harmony_home) = json_string_field(&body, "harmonyHome") else {
        return Ok(false);
    };
    let Some(artifact_path) = json_string_field(&body, "artifactPath") else {
        return Ok(false);
    };
    let project_root = PathBuf::from(project_root);
    let harmony_home = PathBuf::from(harmony_home);
    let artifact_path = PathBuf::from(artifact_path);
    if !project_root.is_dir() || !artifact_path.is_file() {
        return Ok(false);
    }
    if !is_path_under(&project_root, child_root) || !is_path_under(&artifact_path, &project_root) {
        return Ok(false);
    }
    let meta = fs::metadata(&artifact_path)
        .map_err(|error| format!("failed to stat forked artifact: {error}"))?;
    let input = build_input_fingerprint(&project_root, &harmony_home)?;
    let artifact_fingerprint = file_fingerprint(&artifact_path)?;
    let artifact = ArtifactSummary {
        path: artifact_path,
        bytes: meta.len(),
        extension: "hap".into(),
    };
    write_build_state(
        child,
        &project_root,
        &harmony_home,
        &input,
        &artifact,
        &artifact_fingerprint,
    )?;
    Ok(true)
}

fn is_empty_dir(path: &Path) -> Result<bool, String> {
    let mut entries = fs::read_dir(path)
        .map_err(|error| format!("failed to read child task dir {}: {error}", path.display()))?;
    Ok(entries.next().is_none())
}

fn copy_tree(
    from: &Path,
    to: &Path,
    copied_files: &mut usize,
    copied_bytes: &mut u64,
) -> Result<(), String> {
    if from.is_file() {
        if let Some(parent) = to.parent() {
            fs::create_dir_all(parent)
                .map_err(|error| format!("failed to create {}: {error}", parent.display()))?;
        }
        let bytes = fs::copy(from, to).map_err(|error| {
            format!(
                "failed to copy {} to {}: {error}",
                from.display(),
                to.display()
            )
        })?;
        *copied_files += 1;
        *copied_bytes += bytes;
        return Ok(());
    }
    fs::create_dir_all(to)
        .map_err(|error| format!("failed to create {}: {error}", to.display()))?;
    let read_dir = fs::read_dir(from)
        .map_err(|error| format!("failed to read {}: {error}", from.display()))?;
    for entry in read_dir {
        let entry = entry.map_err(|error| format!("failed to read directory entry: {error}"))?;
        let source = entry.path();
        let target = to.join(entry.file_name());
        let meta = entry
            .metadata()
            .map_err(|error| format!("failed to stat {}: {error}", source.display()))?;
        if meta.is_dir() {
            copy_tree(&source, &target, copied_files, copied_bytes)?;
        } else if meta.is_file() {
            let bytes = fs::copy(&source, &target).map_err(|error| {
                format!(
                    "failed to copy {} to {}: {error}",
                    source.display(),
                    target.display()
                )
            })?;
            *copied_files += 1;
            *copied_bytes += bytes;
        }
    }
    Ok(())
}

fn rewrite_forked_state_paths(
    child_root: &Path,
    parent_root: &Path,
    child: &TaskScope,
    parent_task_id: &str,
) -> Result<(), String> {
    let state_path = child_root.join("state/build-state.json");
    if !state_path.is_file() {
        return Ok(());
    }
    let mut body = fs::read_to_string(&state_path)
        .map_err(|error| format!("failed to read forked build state: {error}"))?;
    body = body.replace(
        &parent_root.display().to_string(),
        &child_root.display().to_string(),
    );
    body = body.replace(
        &format!("\"taskId\": \"{}\"", json_escape(parent_task_id)),
        &format!("\"taskId\": \"{}\"", json_escape(&child.task_id)),
    );
    body = body.replace(
        &format!("\"taskId\":\"{}\"", json_escape(parent_task_id)),
        &format!("\"taskId\":\"{}\"", json_escape(&child.task_id)),
    );
    fs::write(&state_path, body)
        .map_err(|error| format!("failed to rewrite forked build state: {error}"))
}

fn validate_task_prepare(
    config: &ServiceConfig,
    params: &BTreeMap<String, String>,
) -> Result<Option<TaskScope>, String> {
    let Some(task_root) = &config.task_root else {
        return Err("harmony.task.prepare requires service --task-root".into());
    };
    let task_id = params
        .get("taskId")
        .ok_or_else(|| "missing query parameter: taskId".to_string())?;
    validate_task_id(task_id)?;
    Ok(Some(TaskScope {
        task_id: task_id.clone(),
        root: normalize_path(&task_root.join(task_id)),
    }))
}

fn task_prepare(task: &TaskScope) -> Result<Receipt, String> {
    for rel in [
        "workspace",
        "artifacts",
        "tmp",
        "receipts",
        "state",
        "cache",
    ] {
        fs::create_dir_all(task.root.join(rel))
            .map_err(|error| format!("failed to create task sandbox {rel}: {error}"))?;
    }
    let mut manifest = BTreeMap::new();
    manifest.insert("taskId".into(), JsonValue::string(task.task_id.clone()));
    manifest.insert(
        "taskRoot".into(),
        JsonValue::string(task.root.display().to_string()),
    );
    manifest.insert(
        "workspace".into(),
        JsonValue::string(task.root.join("workspace").display().to_string()),
    );
    manifest.insert(
        "artifacts".into(),
        JsonValue::string(task.root.join("artifacts").display().to_string()),
    );
    manifest.insert(
        "tmp".into(),
        JsonValue::string(task.root.join("tmp").display().to_string()),
    );
    manifest.insert(
        "receipts".into(),
        JsonValue::string(task.root.join("receipts").display().to_string()),
    );
    manifest.insert(
        "preparedAtUnixMillis".into(),
        JsonValue::Number(now_millis()),
    );
    let task_json = json_object_pretty(&manifest);
    fs::write(task.root.join("task.json"), task_json)
        .map_err(|error| format!("failed to write task manifest: {error}"))?;
    let receipt = Receipt::new(
        "harmony.task.prepare",
        alharmony_ops_core::SideEffect::WorkspaceWrite,
    )
    .evidence("task", JsonValue::Object(manifest))
    .next("harmony.project.create");
    Ok(receipt)
}

fn append_task_receipt(task: &TaskScope, receipt: &Receipt) {
    let receipts_dir = task.root.join("receipts");
    if fs::create_dir_all(&receipts_dir).is_err() {
        return;
    }
    let json = compact_json(&receipt.to_json_pretty());
    let line = format!(
        r#"{{"tsUnixMillis":{},"operation":"{}","ok":{},"receipt":{}}}
"#,
        now_millis(),
        json_escape(receipt.operation),
        if receipt.ok { "true" } else { "false" },
        json
    );
    if let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(receipts_dir.join("events.jsonl"))
    {
        let _ = file.write_all(line.as_bytes());
    }
}

fn compact_json(value: &str) -> String {
    value.lines().map(str::trim).collect::<String>()
}

fn json_object_pretty(map: &BTreeMap<String, JsonValue>) -> String {
    let value = JsonValue::Object(map.clone());
    let mut out = String::new();
    write_json_value(&mut out, &value, 0);
    out.push('\n');
    out
}

fn write_json_value(out: &mut String, value: &JsonValue, indent: usize) {
    match value {
        JsonValue::Null => out.push_str("null"),
        JsonValue::Bool(v) => out.push_str(if *v { "true" } else { "false" }),
        JsonValue::Number(v) => out.push_str(&v.to_string()),
        JsonValue::String(v) => {
            out.push('"');
            out.push_str(&json_escape(v));
            out.push('"');
        }
        JsonValue::Array(items) => {
            out.push('[');
            for (idx, item) in items.iter().enumerate() {
                if idx != 0 {
                    out.push_str(", ");
                }
                write_json_value(out, item, indent);
            }
            out.push(']');
        }
        JsonValue::Object(map) => {
            if map.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push_str("{\n");
            for (idx, (key, item)) in map.iter().enumerate() {
                for _ in 0..indent + 1 {
                    out.push_str("  ");
                }
                out.push('"');
                out.push_str(&json_escape(key));
                out.push_str("\": ");
                write_json_value(out, item, indent + 1);
                if idx + 1 != map.len() {
                    out.push(',');
                }
                out.push('\n');
            }
            for _ in 0..indent {
                out.push_str("  ");
            }
            out.push('}');
        }
    }
}

fn now_millis() -> i128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis() as i128)
        .unwrap_or(0)
}

fn validate_task_paths(
    config: &ServiceConfig,
    params: &BTreeMap<String, String>,
    paths: &[(&str, &PathBuf)],
) -> Result<Option<TaskScope>, String> {
    let Some(task_root) = &config.task_root else {
        return Ok(None);
    };
    let task_id = params.get("taskId").ok_or_else(|| {
        "missing query parameter: taskId when task isolation is enabled".to_string()
    })?;
    validate_task_id(task_id)?;
    let scope_root = normalize_path(&task_root.join(task_id));
    for (name, path) in paths {
        let normalized = normalize_path(path);
        if normalized != scope_root && !normalized.starts_with(&scope_root) {
            return Err(format!(
                "{name} must stay under task scope {}",
                scope_root.display()
            ));
        }
    }
    Ok(Some(TaskScope {
        task_id: task_id.clone(),
        root: scope_root,
    }))
}

fn validate_task_id(task_id: &str) -> Result<(), String> {
    if task_id.is_empty() || task_id.len() > 80 {
        return Err("taskId must be non-empty and at most 80 bytes".into());
    }
    if task_id.contains("..") || task_id.contains('/') || task_id.contains('\\') {
        return Err("taskId must not contain path traversal or separators".into());
    }
    if !task_id
        .bytes()
        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_'))
    {
        return Err("taskId may contain only ASCII letters, digits, '.', '-', '_'".into());
    }
    Ok(())
}

fn add_task_evidence(receipt: Receipt, task: Option<&TaskScope>) -> Receipt {
    let Some(task) = task else {
        return receipt;
    };
    let mut evidence = BTreeMap::new();
    evidence.insert("taskId".into(), JsonValue::string(task.task_id.clone()));
    evidence.insert(
        "taskRoot".into(),
        JsonValue::string(task.root.display().to_string()),
    );
    evidence.insert("pathIsolation".into(), JsonValue::Bool(true));
    let receipt = receipt.evidence("task", JsonValue::Object(evidence));
    append_task_receipt(task, &receipt);
    receipt
}

fn normalize_path(path: &Path) -> PathBuf {
    let mut out = if path.is_absolute() {
        PathBuf::from("/")
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    };
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => out.push(prefix.as_os_str()),
            Component::RootDir => out = PathBuf::from("/"),
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            Component::Normal(value) => out.push(value),
        }
    }
    out
}

fn split_target(target: &str) -> (&str, &str) {
    match target.split_once('?') {
        Some((path, query)) => (path, query),
        None => (target, ""),
    }
}

fn parse_query(query: &str) -> BTreeMap<String, String> {
    let mut params = BTreeMap::new();
    for part in query.split('&').filter(|part| !part.is_empty()) {
        let (key, value) = part.split_once('=').unwrap_or((part, ""));
        params.insert(url_decode(key), url_decode(value));
    }
    params
}

fn param_path(params: &BTreeMap<String, String>, name: &str) -> Option<PathBuf> {
    params.get(name).map(PathBuf::from)
}

fn required_param_path(params: &BTreeMap<String, String>, name: &str) -> Result<PathBuf, String> {
    param_path(params, name).ok_or_else(|| format!("missing query parameter: {name}"))
}

fn url_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0_usize;
    while i < bytes.len() {
        match bytes[i] {
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            b'%' if i + 2 < bytes.len() => {
                if let (Some(a), Some(b)) = (hex(bytes[i + 1]), hex(bytes[i + 2])) {
                    out.push(a * 16 + b);
                    i += 3;
                } else {
                    out.push(bytes[i]);
                    i += 1;
                }
            }
            byte => {
                out.push(byte);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hex(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn service_error(status: u16, code: &str, message: &str) -> (u16, String) {
    (status, service_error_body(code, message))
}

fn service_error_body(code: &str, message: &str) -> String {
    format!(
        "{{\n  \"schema\": \"agentlab.harmony_ops.service_error.v1\",\n  \"ok\": false,\n  \"error\": {{\n    \"code\": \"{}\",\n    \"message\": \"{}\"\n  }}\n}}\n",
        json_escape(code),
        json_escape(message)
    )
}

fn json_escape(value: &str) -> String {
    let mut out = String::new();
    for ch in value.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c => out.push(c),
        }
    }
    out
}

fn required_path(args: &mut Vec<String>, name: &str) -> PathBuf {
    match take_value(args, name) {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("missing required argument: {name}");
            usage(2);
        }
    }
}

fn take_value(args: &mut Vec<String>, name: &str) -> Option<String> {
    let idx = args.iter().position(|arg| arg == name)?;
    args.remove(idx);
    if idx >= args.len() {
        eprintln!("{name} requires a value");
        std::process::exit(2);
    }
    Some(args.remove(idx))
}

fn usage(code: i32) -> ! {
    eprintln!(
        "usage: alharmony-ops <serve|env-status|project-create-plan|project-verify|ohpm-install-plan|build-debug-plan|artifact-inspect> [args]\n\n\
         serve [--bind 127.0.0.1:19731] [--workers N] [--queue-capacity N] [--max-active-requests N] [--max-batch N] [--task-root DIR]\n\
         env-status [--harmony-home DIR]\n\
         project-create-plan --project-root DIR [--bundle-name NAME] [--app-label LABEL]\n\
         project-verify --project-root DIR\n\
         ohpm-install-plan --project-root DIR --harmony-home DIR\n\
         build-debug-plan --project-root DIR --harmony-home DIR\n\
         artifact-inspect --artifact FILE\n\n\
         service endpoints: GET /v1/ops/<operation>?projectRoot=...&harmonyHome=...&artifact=...\n\
         batch endpoint: GET /v1/batch/<operation>?n=<count>&projectRoot=...&harmonyHome=...&artifact=...\n\
         task isolation: start with --task-root DIR, then pass taskId=... and keep project/artifact paths under DIR/taskId
\
         execute mode: add materialize=true for project.create and execute=true for ohpm/build inside task sandbox"
    );
    std::process::exit(code);
}
