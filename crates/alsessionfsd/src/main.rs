use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

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
    if !args.is_empty() {
        eprintln!("unexpected arguments: {}", args.join(" "));
        std::process::exit(2);
    }
    let listener = TcpListener::bind(&bind).unwrap_or_else(|error| {
        eprintln!("failed to bind {bind}: {error}");
        std::process::exit(1);
    });
    eprintln!("alsessionfsd listening on {bind}");
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                thread::spawn(move || handle_connection(stream));
            }
            Err(error) => eprintln!("accept failed: {error}"),
        }
    }
}

fn usage(code: i32) -> ! {
    eprintln!(
        "usage: alsessionfsd serve [--bind 127.0.0.1:19780]\n\n\
         endpoints:\n\
           GET /health\n\
           GET /capabilities\n\
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

fn handle_connection(mut stream: TcpStream) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(10)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(10)));
    let Some(request) = read_http_header(&mut stream) else {
        return;
    };
    let (status, body) = route_request(&request);
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

fn route_request(request: &str) -> (u16, String) {
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
        return (200, health_body());
    }
    if target == "/capabilities" || target == "/v1/capabilities" {
        return (200, capabilities_body());
    }
    let (path, query) = split_target(target);
    if path == "/v1/sessions/fork" {
        let params = parse_query(query);
        return match fork_session(&params) {
            Ok(body) => (200, body),
            Err(message) => error(400, "badForkRequest", &message),
        };
    }
    error(404, "notFound", "unknown endpoint")
}

fn health_body() -> String {
    "{\n  \"schema\": \"agentlab.sessionfs.service_status.v1\",\n  \"ok\": true,\n  \"service\": \"alsessionfsd\",\n  \"backend\": \"copy-tree-preview\"\n}\n".into()
}

fn capabilities_body() -> String {
    "{\n  \"schema\": \"agentlab.sessionfs.capabilities.v1\",\n  \"ok\": true,\n  \"service\": \"alsessionfsd\",\n  \"backends\": [\"copy-tree-preview\"],\n  \"operations\": [\"session.fork\"]\n}\n".into()
}

fn fork_session(params: &BTreeMap<String, String>) -> Result<String, String> {
    let parent = required_path(params, "parentRoot")?;
    let child = required_path(params, "childRoot")?;
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
    fs::create_dir_all(&child).map_err(|error| format!("failed to create childRoot: {error}"))?;
    let started = Instant::now();
    let mut copied_files = 0_usize;
    let mut copied_bytes = 0_u64;
    for rel in &include {
        let from = parent.join(rel);
        let to = child.join(rel);
        if from.exists() {
            copy_tree(&from, &to, &mut copied_files, &mut copied_bytes)?;
        } else {
            fs::create_dir_all(&to)
                .map_err(|error| format!("failed to create {}: {error}", to.display()))?;
        }
    }
    for rel in &reset {
        fs::create_dir_all(child.join(rel))
            .map_err(|error| format!("failed to create reset dir {rel}: {error}"))?;
    }
    let elapsed = started.elapsed().as_micros();
    Ok(format!(
        "{{\n  \"schema\": \"agentlab.sessionfs.fork_receipt.v1\",\n  \"ok\": true,\n  \"operation\": \"session.fork\",\n  \"backend\": \"copy-tree-preview\",\n  \"parentRoot\": \"{}\",\n  \"childRoot\": \"{}\",\n  \"copiedFiles\": {},\n  \"copiedBytes\": {},\n  \"elapsedMicros\": {},\n  \"include\": {},\n  \"reset\": {}\n}}\n",
        json_escape(&parent.display().to_string()),
        json_escape(&child.display().to_string()),
        copied_files,
        copied_bytes,
        elapsed,
        json_string_array(&include),
        json_string_array(&reset)
    ))
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
