use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ForkBackend {
    Auto,
    CopyTree,
    BtrfsSubvolume,
}

impl ForkBackend {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "auto" => Ok(Self::Auto),
            "copy-tree" | "copy-tree-preview" => Ok(Self::CopyTree),
            "btrfs" | "btrfs-subvolume" => Ok(Self::BtrfsSubvolume),
            other => Err(format!("unsupported backend: {other}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::CopyTree => "copy-tree-preview",
            Self::BtrfsSubvolume => "btrfs-subvolume",
        }
    }
}

#[derive(Clone, Debug)]
struct ServiceConfig {
    backend: ForkBackend,
    storage_root: Option<PathBuf>,
}

fn main() {
    let mut args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.is_empty() || args[0] == "--help" || args[0] == "-h" {
        usage(0);
    }
    let command = args.remove(0);
    if command != "serve" && command != "service" {
        eprintln!("unknown command: {command}");
        usage(2);
    }
    let bind = take_value(&mut args, "--bind").unwrap_or_else(|| "127.0.0.1:19780".to_string());
    let backend = take_value(&mut args, "--backend")
        .map(|value| {
            ForkBackend::parse(&value).unwrap_or_else(|error| {
                eprintln!("{error}");
                usage(2);
            })
        })
        .unwrap_or(ForkBackend::Auto);
    let storage_root = take_value(&mut args, "--storage-root").map(|value| {
        let root = normalize_path(Path::new(&value));
        fs::canonicalize(&root).unwrap_or_else(|error| {
            eprintln!("failed to resolve storage root {}: {error}", root.display());
            std::process::exit(2);
        })
    });
    if let Some(root) = &storage_root {
        if !root.is_dir() {
            eprintln!("storage root is not a directory: {}", root.display());
            std::process::exit(2);
        }
    }
    if !args.is_empty() {
        eprintln!("unexpected arguments: {}", args.join(" "));
        std::process::exit(2);
    }
    let config = ServiceConfig {
        backend,
        storage_root,
    };
    let listener = TcpListener::bind(&bind).unwrap_or_else(|error| {
        eprintln!("failed to bind {bind}: {error}");
        std::process::exit(1);
    });
    eprintln!(
        "alsessionfsd listening on {bind} backend={} storageRoot={}",
        config.backend.as_str(),
        config
            .storage_root
            .as_ref()
            .map(|root| root.display().to_string())
            .unwrap_or_else(|| "<unconfined-preview>".into())
    );
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                let config = config.clone();
                thread::spawn(move || handle_connection(stream, &config));
            }
            Err(error) => eprintln!("accept failed: {error}"),
        }
    }
}

fn usage(code: i32) -> ! {
    eprintln!(
        "usage: alsessionfsd serve [--bind 127.0.0.1:19780] [--backend auto|copy-tree|btrfs-subvolume] [--storage-root PATH]\n\n\
         endpoints:\n\
           GET /health\n\
           GET /capabilities\n\
           GET /v1/sessions/create?root=...\n\
           GET /v1/sessions/fork?parentRoot=...&childRoot=...&include=workspace,artifacts,state,cache&reset=receipts,tmp"
    );
    std::process::exit(code);
}

fn take_value(args: &mut Vec<String>, flag: &str) -> Option<String> {
    let index = args.iter().position(|arg| arg == flag)?;
    args.remove(index);
    if index >= args.len() {
        eprintln!("missing value for {flag}");
        std::process::exit(2);
    }
    Some(args.remove(index))
}

fn handle_connection(mut stream: TcpStream, config: &ServiceConfig) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(10)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(10)));
    let Some(request) = read_http_header(&mut stream) else {
        return;
    };
    let (status, body) = route_request(&request, config);
    let _ = write_json_response(&mut stream, status, &body);
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

fn write_json_response(stream: &mut TcpStream, status: u16, body: &str) -> std::io::Result<()> {
    let reason = match status {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        500 => "Internal Server Error",
        _ => "OK",
    };
    let response = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(), body
    );
    stream.write_all(response.as_bytes())
}

fn route_request(request: &str, config: &ServiceConfig) -> (u16, String) {
    let Some(line) = request.lines().next() else {
        return error(400, "emptyRequest", "missing request line");
    };
    let mut parts = line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("");
    if method != "GET" {
        return error(400, "unsupportedMethod", "only GET is supported in preview");
    }
    if target == "/health" || target == "/v1/health" {
        return (200, health_body(config));
    }
    if target == "/capabilities" || target == "/v1/capabilities" {
        return (200, capabilities_body(config));
    }
    let (path, query) = split_target(target);
    if path == "/v1/sessions/create" {
        let params = parse_query(query);
        return match create_session(&params, config) {
            Ok(body) => (200, body),
            Err(message) => error(400, "badCreateRequest", &message),
        };
    }
    if path == "/v1/sessions/fork" {
        let params = parse_query(query);
        return match fork_session(&params, config) {
            Ok(body) => (200, body),
            Err(message) => error(400, "badForkRequest", &message),
        };
    }
    error(404, "notFound", "unknown endpoint")
}

fn health_body(config: &ServiceConfig) -> String {
    format!(
        "{{\n  \"schema\": \"agentlab.sessionfs.service_status.v1\",\n  \"ok\": true,\n  \"service\": \"alsessionfsd\",\n  \"backend\": \"{}\",\n  \"btrfsCommandReady\": {},\n  \"btrfsStorageReady\": {},\n  \"storageRoot\": {}\n}}\n",
        config.backend.as_str(),
        btrfs_command_ready(),
        config
            .storage_root
            .as_deref()
            .is_some_and(btrfs_filesystem_ready),
        json_optional_string(config.storage_root.as_deref())
    )
}

fn capabilities_body(config: &ServiceConfig) -> String {
    let mut backends = vec!["copy-tree-preview".to_string()];
    if btrfs_command_ready() {
        backends.push("btrfs-subvolume".into());
    }
    format!(
        "{{\n  \"schema\": \"agentlab.sessionfs.capabilities.v1\",\n  \"ok\": true,\n  \"service\": \"alsessionfsd\",\n  \"configuredBackend\": \"{}\",\n  \"backends\": {},\n  \"operations\": [\"session.create\", \"session.fork\"],\n  \"btrfsStorageReady\": {},\n  \"storageRoot\": {}\n}}\n",
        config.backend.as_str(),
        json_string_array(&backends),
        config
            .storage_root
            .as_deref()
            .is_some_and(btrfs_filesystem_ready),
        json_optional_string(config.storage_root.as_deref())
    )
}

#[derive(Debug)]
struct CreateStorageResult {
    backend: String,
    fallback: bool,
    copy_on_write: bool,
    reused: bool,
}

fn create_session(
    params: &BTreeMap<String, String>,
    config: &ServiceConfig,
) -> Result<String, String> {
    let root = required_path(params, "root")?;
    validate_storage_path(config, &root)?;
    let started = Instant::now();
    let result = match config.backend {
        ForkBackend::CopyTree => create_directory_session(&root, false)?,
        ForkBackend::BtrfsSubvolume => create_btrfs_session(&root, false)?,
        ForkBackend::Auto => {
            let existed_before = root.exists();
            match create_btrfs_session(&root, false) {
                Ok(result) => result,
                Err(error) => {
                    if !existed_before {
                        cleanup_child_after_failed_btrfs(&root);
                    }
                    eprintln!("btrfs session create failed, using directory fallback: {error}");
                    create_directory_session(&root, true)?
                }
            }
        }
    };
    Ok(format!(
        "{{\n  \"schema\": \"agentlab.sessionfs.create_receipt.v1\",\n  \"ok\": true,\n  \"operation\": \"session.create\",\n  \"backend\": \"{}\",\n  \"fallback\": {},\n  \"copyOnWrite\": {},\n  \"reused\": {},\n  \"root\": \"{}\",\n  \"elapsedMicros\": {}\n}}\n",
        result.backend,
        result.fallback,
        result.copy_on_write,
        result.reused,
        json_escape(&root.display().to_string()),
        started.elapsed().as_micros()
    ))
}

fn validate_storage_path(config: &ServiceConfig, path: &Path) -> Result<(), String> {
    if let Some(root) = &config.storage_root {
        if path == root || !path.starts_with(root) {
            return Err(format!(
                "session root must be a child of storageRoot {}",
                root.display()
            ));
        }
        let mut current = root.clone();
        let relative = path
            .strip_prefix(root)
            .map_err(|_| "session root escaped storageRoot".to_string())?;
        for component in relative.components() {
            let Component::Normal(component) = component else {
                return Err("session root contains unsupported path components".into());
            };
            current.push(component);
            match fs::symlink_metadata(&current) {
                Ok(meta) if meta.file_type().is_symlink() => {
                    return Err(format!(
                        "session root must not traverse symlink: {}",
                        current.display()
                    ));
                }
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
                Err(error) => {
                    return Err(format!(
                        "failed to inspect session root path {}: {error}",
                        current.display()
                    ));
                }
            }
        }
    }
    Ok(())
}

fn create_directory_session(root: &Path, fallback: bool) -> Result<CreateStorageResult, String> {
    let reused = root.exists();
    if reused && !root.is_dir() {
        return Err(format!(
            "session root exists and is not a directory: {}",
            root.display()
        ));
    }
    fs::create_dir_all(root)
        .map_err(|error| format!("failed to create session root {}: {error}", root.display()))?;
    Ok(CreateStorageResult {
        backend: if fallback {
            "directory-fallback".into()
        } else {
            "directory".into()
        },
        fallback,
        copy_on_write: false,
        reused,
    })
}

fn create_btrfs_session(root: &Path, fallback: bool) -> Result<CreateStorageResult, String> {
    if root.exists() && btrfs_subvolume_ready(root) {
        return Ok(CreateStorageResult {
            backend: "btrfs-subvolume".into(),
            fallback,
            copy_on_write: true,
            reused: true,
        });
    }
    if root.exists() {
        if !root.is_dir() {
            return Err(format!(
                "session root exists and is not a directory: {}",
                root.display()
            ));
        }
        if !is_empty_dir(root)? {
            return Err(format!(
                "session root exists but is not a Btrfs subvolume and is not empty: {}",
                root.display()
            ));
        }
        fs::remove_dir(root)
            .map_err(|error| format!("failed to remove empty session root: {error}"))?;
    }
    let parent = root
        .parent()
        .ok_or_else(|| "session root has no parent directory".to_string())?;
    if !btrfs_filesystem_ready(parent) {
        return Err(format!(
            "session root parent is not on an accessible Btrfs filesystem: {}",
            parent.display()
        ));
    }
    let output = Command::new("btrfs")
        .args(["subvolume", "create"])
        .arg(root)
        .output()
        .map_err(|error| format!("failed to execute btrfs subvolume create: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "btrfs subvolume create failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(CreateStorageResult {
        backend: "btrfs-subvolume".into(),
        fallback,
        copy_on_write: true,
        reused: false,
    })
}

fn fork_session(
    params: &BTreeMap<String, String>,
    config: &ServiceConfig,
) -> Result<String, String> {
    let parent = required_path(params, "parentRoot")?;
    let child = required_path(params, "childRoot")?;
    validate_storage_paths(config, &parent, &child)?;
    if !parent.is_dir() {
        return Err(format!(
            "parentRoot is not a directory: {}",
            parent.display()
        ));
    }
    if child.exists() && !is_empty_dir(&child)? {
        return Err(format!(
            "childRoot already exists and is not empty: {}",
            child.display()
        ));
    }
    let include = params
        .get("include")
        .map(|value| split_csv(value))
        .unwrap_or_else(|| {
            vec![
                "workspace".into(),
                "artifacts".into(),
                "state".into(),
                "cache".into(),
            ]
        });
    let reset = params
        .get("reset")
        .map(|value| split_csv(value))
        .unwrap_or_else(|| vec!["receipts".into(), "tmp".into()]);
    for rel in include.iter().chain(reset.iter()) {
        validate_rel(rel)?;
    }
    let started = Instant::now();
    let mut copied_files = 0_usize;
    let mut copied_bytes = 0_u64;
    let (backend, fallback, copy_on_write) = match config.backend {
        ForkBackend::CopyTree => {
            fork_copy_tree(
                &parent,
                &child,
                &include,
                &reset,
                &mut copied_files,
                &mut copied_bytes,
            )?;
            ("copy-tree-preview", false, false)
        }
        ForkBackend::BtrfsSubvolume => {
            fork_btrfs_subvolume(&parent, &child, &include, &reset)?;
            ("btrfs-subvolume", false, true)
        }
        ForkBackend::Auto => match fork_btrfs_subvolume(&parent, &child, &include, &reset) {
            Ok(()) => ("btrfs-subvolume", false, true),
            Err(error) => {
                cleanup_child_after_failed_btrfs(&child);
                eprintln!("btrfs fast fork failed, using copy-tree fallback: {error}");
                fork_copy_tree(
                    &parent,
                    &child,
                    &include,
                    &reset,
                    &mut copied_files,
                    &mut copied_bytes,
                )?;
                ("copy-tree-fallback", true, false)
            }
        },
    };
    let elapsed = started.elapsed().as_micros();
    Ok(format!(
        "{{\n  \"schema\": \"agentlab.sessionfs.fork_receipt.v1\",\n  \"ok\": true,\n  \"operation\": \"session.fork\",\n  \"backend\": \"{}\",\n  \"fallback\": {},\n  \"copyOnWrite\": {},\n  \"parentRoot\": \"{}\",\n  \"childRoot\": \"{}\",\n  \"copiedFiles\": {},\n  \"copiedBytes\": {},\n  \"elapsedMicros\": {},\n  \"include\": {},\n  \"reset\": {}\n}}\n",
        backend,
        fallback,
        copy_on_write,
        json_escape(&parent.display().to_string()),
        json_escape(&child.display().to_string()),
        copied_files,
        copied_bytes,
        elapsed,
        json_string_array(&include),
        json_string_array(&reset)
    ))
}

fn validate_storage_paths(
    config: &ServiceConfig,
    parent: &Path,
    child: &Path,
) -> Result<(), String> {
    validate_storage_path(config, parent)?;
    validate_storage_path(config, child)?;
    if parent == child {
        return Err("parentRoot and childRoot must differ".into());
    }
    if child.starts_with(parent) || parent.starts_with(child) {
        return Err("parentRoot and childRoot must not contain one another".into());
    }
    Ok(())
}

fn fork_copy_tree(
    parent: &Path,
    child: &Path,
    include: &[String],
    reset: &[String],
    copied_files: &mut usize,
    copied_bytes: &mut u64,
) -> Result<(), String> {
    fs::create_dir_all(child).map_err(|error| format!("failed to create childRoot: {error}"))?;
    for rel in include {
        let from = parent.join(rel);
        let to = child.join(rel);
        if from.exists() {
            copy_tree(&from, &to, copied_files, copied_bytes)?;
        } else {
            fs::create_dir_all(&to)
                .map_err(|error| format!("failed to create {}: {error}", to.display()))?;
        }
    }
    for rel in reset {
        fs::create_dir_all(child.join(&rel))
            .map_err(|error| format!("failed to create reset dir {rel}: {error}"))?;
    }
    Ok(())
}

fn btrfs_command_ready() -> bool {
    Command::new("btrfs")
        .arg("version")
        .output()
        .is_ok_and(|output| output.status.success())
}

fn btrfs_filesystem_ready(path: &Path) -> bool {
    if !path.is_dir() {
        return false;
    }
    Command::new("btrfs")
        .args(["filesystem", "show"])
        .arg(path)
        .output()
        .is_ok_and(|output| output.status.success())
}

fn btrfs_subvolume_ready(path: &Path) -> bool {
    if !path.is_dir() {
        return false;
    }
    Command::new("btrfs")
        .args(["subvolume", "show"])
        .arg(path)
        .output()
        .is_ok_and(|output| output.status.success())
}

fn fork_btrfs_subvolume(
    parent: &Path,
    child: &Path,
    include: &[String],
    reset: &[String],
) -> Result<(), String> {
    validate_btrfs_contract_paths(include, reset)?;
    if child.exists() {
        if !is_empty_dir(child)? {
            return Err(format!(
                "childRoot already exists and is not empty: {}",
                child.display()
            ));
        }
        fs::remove_dir(child).map_err(|error| {
            format!("failed to remove empty childRoot before snapshot: {error}")
        })?;
    }
    let Some(child_parent) = child.parent() else {
        return Err("childRoot has no parent directory".into());
    };
    fs::create_dir_all(child_parent)
        .map_err(|error| format!("failed to create childRoot parent: {error}"))?;
    let output = Command::new("btrfs")
        .args(["subvolume", "snapshot"])
        .arg(parent)
        .arg(child)
        .output()
        .map_err(|error| format!("failed to execute btrfs snapshot: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "btrfs snapshot failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    if let Err(error) = prune_snapshot_to_contract(child, include, reset) {
        cleanup_child_after_failed_btrfs(child);
        return Err(error);
    }
    Ok(())
}

fn validate_btrfs_contract_paths(include: &[String], reset: &[String]) -> Result<(), String> {
    for rel in include.iter().chain(reset.iter()) {
        let mut components = Path::new(rel).components();
        if !matches!(components.next(), Some(Component::Normal(_))) || components.next().is_some() {
            return Err(format!(
                "btrfs-subvolume backend currently requires top-level include/reset paths: {rel}"
            ));
        }
    }
    Ok(())
}

fn prune_snapshot_to_contract(
    child: &Path,
    include: &[String],
    reset: &[String],
) -> Result<(), String> {
    let include = include.iter().cloned().collect::<BTreeSet<_>>();
    let reset = reset.iter().cloned().collect::<BTreeSet<_>>();
    for entry in fs::read_dir(child)
        .map_err(|error| format!("failed to read snapshot root {}: {error}", child.display()))?
    {
        let entry = entry.map_err(|error| format!("failed to read snapshot entry: {error}"))?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if include.contains(&name) {
            continue;
        }
        remove_path(&entry.path())?;
    }
    for rel in include {
        fs::create_dir_all(child.join(&rel))
            .map_err(|error| format!("failed to ensure included dir {rel}: {error}"))?;
    }
    for rel in reset {
        let path = child.join(&rel);
        if path.exists() {
            remove_path(&path)?;
        }
        fs::create_dir_all(&path)
            .map_err(|error| format!("failed to create reset dir {rel}: {error}"))?;
    }
    Ok(())
}

fn remove_path(path: &Path) -> Result<(), String> {
    let meta = fs::symlink_metadata(path)
        .map_err(|error| format!("failed to stat {}: {error}", path.display()))?;
    if meta.is_dir() && !meta.file_type().is_symlink() {
        fs::remove_dir_all(path)
            .map_err(|error| format!("failed to remove directory {}: {error}", path.display()))
    } else {
        fs::remove_file(path)
            .map_err(|error| format!("failed to remove file {}: {error}", path.display()))
    }
}

fn cleanup_child_after_failed_btrfs(child: &Path) {
    if !child.exists() {
        return;
    }
    let _ = Command::new("btrfs")
        .args(["subvolume", "delete"])
        .arg(child)
        .output();
    if child.exists() {
        let _ = fs::remove_dir_all(child);
    }
}

fn required_path(params: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    let value = params
        .get(key)
        .ok_or_else(|| format!("missing query parameter: {key}"))?;
    Ok(normalize_path(Path::new(value)))
}

fn split_csv(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn validate_rel(rel: &str) -> Result<(), String> {
    if rel.is_empty() || rel.starts_with('/') || rel.starts_with('\\') {
        return Err("relative path must not be empty or absolute".into());
    }
    for component in Path::new(rel).components() {
        match component {
            Component::Normal(_) | Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err("relative path must not contain traversal".into());
            }
        }
    }
    Ok(())
}

fn is_empty_dir(path: &Path) -> Result<bool, String> {
    let mut entries = fs::read_dir(path).map_err(|error| format!("failed to read dir: {error}"))?;
    Ok(entries.next().is_none())
}

fn copy_tree(
    from: &Path,
    to: &Path,
    files: &mut usize,
    bytes_total: &mut u64,
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
        *files += 1;
        *bytes_total += bytes;
        return Ok(());
    }
    fs::create_dir_all(to)
        .map_err(|error| format!("failed to create {}: {error}", to.display()))?;
    for entry in
        fs::read_dir(from).map_err(|error| format!("failed to read {}: {error}", from.display()))?
    {
        let entry = entry.map_err(|error| format!("failed to read directory entry: {error}"))?;
        let source = entry.path();
        let target = to.join(entry.file_name());
        let meta = entry
            .metadata()
            .map_err(|error| format!("failed to stat {}: {error}", source.display()))?;
        if meta.is_dir() {
            copy_tree(&source, &target, files, bytes_total)?;
        } else if meta.is_file() {
            let bytes = fs::copy(&source, &target).map_err(|error| {
                format!(
                    "failed to copy {} to {}: {error}",
                    source.display(),
                    target.display()
                )
            })?;
            *files += 1;
            *bytes_total += bytes;
        }
    }
    Ok(())
}

fn split_target(target: &str) -> (&str, &str) {
    match target.split_once('?') {
        Some((path, query)) => (path, query),
        None => (target, ""),
    }
}

fn parse_query(query: &str) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for pair in query.split('&').filter(|pair| !pair.is_empty()) {
        let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
        out.insert(percent_decode(key), percent_decode(value));
    }
    out
}

fn percent_decode(value: &str) -> String {
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
                let hi = hex(bytes[i + 1]);
                let lo = hex(bytes[i + 2]);
                if let (Some(hi), Some(lo)) = (hi, lo) {
                    out.push((hi << 4) | lo);
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

fn normalize_path(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            _ => out.push(component.as_os_str()),
        }
    }
    out
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
            other => out.push(other),
        }
    }
    out
}

fn json_string_array(values: &[String]) -> String {
    let values = values
        .iter()
        .map(|value| format!("\"{}\"", json_escape(value)))
        .collect::<Vec<_>>()
        .join(", ");
    format!("[{values}]")
}

fn json_optional_string(value: Option<&Path>) -> String {
    value
        .map(|path| format!("\"{}\"", json_escape(&path.display().to_string())))
        .unwrap_or_else(|| "null".into())
}

fn error(status: u16, code: &str, message: &str) -> (u16, String) {
    (
        status,
        format!(
            "{{\n  \"schema\": \"agentlab.sessionfs.error.v1\",\n  \"ok\": false,\n  \"error\": {{\n    \"code\": \"{}\",\n    \"message\": \"{}\"\n  }}\n}}\n",
            json_escape(code),
            json_escape(message)
        ),
    )
}
