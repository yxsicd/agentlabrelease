use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use alharmony_ops_core::{
    artifact_inspect, build_debug_plan, env_status, ohpm_install_plan, project_create_plan,
    project_verify, Receipt,
};

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
    if !args.is_empty() {
        eprintln!("unexpected service arguments: {}", args.join(" "));
        std::process::exit(2);
    }

    let listener = TcpListener::bind(&bind).unwrap_or_else(|error| {
        eprintln!("failed to bind {bind}: {error}");
        std::process::exit(1);
    });
    eprintln!("alharmony-ops service listening on {bind} with {workers} workers");

    let (tx, rx) = mpsc::channel::<TcpStream>();
    let rx = Arc::new(Mutex::new(rx));
    for _ in 0..workers {
        let rx = Arc::clone(&rx);
        thread::spawn(move || loop {
            let stream = match rx.lock().expect("worker receiver poisoned").recv() {
                Ok(stream) => stream,
                Err(_) => return,
            };
            handle_connection(stream);
        });
    }

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                if tx.send(stream).is_err() {
                    break;
                }
            }
            Err(error) => eprintln!("accept failed: {error}"),
        }
    }
    std::process::exit(0);
}

fn handle_connection(mut stream: TcpStream) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(5)));
    for _ in 0..1_000_000_u32 {
        let Some(request) = read_http_header(&mut stream) else {
            return;
        };
        let close_after_response = request_wants_close(&request);
        let (status, body) = route_request(&request);
        let reason = match status {
            200 => "OK",
            400 => "Bad Request",
            404 => "Not Found",
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
        if stream.write_all(response.as_bytes()).is_err() {
            return;
        }
        if close_after_response {
            return;
        }
    }
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

fn route_request(request: &str) -> (u16, String) {
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
        return (
            200,
            concat!(
                "{\n",
                "  \"schema\": \"agentlab.harmony_ops.service_status.v1\",\n",
                "  \"ok\": true,\n",
                "  \"service\": \"alharmony-ops\",\n",
                "  \"receiptSchema\": \"agentlab.harmony_ops.receipt.v1\"\n",
                "}\n"
            )
            .to_string(),
        );
    }
    let (path, query) = split_target(target);
    let params = parse_query(query);
    if let Some(operation) = path.strip_prefix("/v1/ops/") {
        return match dispatch_http(operation, &params) {
            Ok(receipt) => (200, receipt.to_json_pretty()),
            Err(message) => service_error(400, "badOperationRequest", &message),
        };
    }
    if let Some(operation) = path.strip_prefix("/v1/batch/") {
        return match dispatch_batch_http(operation, &params) {
            Ok(body) => (200, body),
            Err(message) => service_error(400, "badBatchRequest", &message),
        };
    }
    service_error(404, "notFound", "unknown endpoint")
}

fn dispatch_batch_http(
    operation: &str,
    params: &BTreeMap<String, String>,
) -> Result<String, String> {
    let count = params
        .get("n")
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| (1..=100_000).contains(value))
        .unwrap_or(1);
    let started = Instant::now();
    let mut ok_count = 0_usize;
    let mut last = None;
    for _ in 0..count {
        let receipt = dispatch_http(operation, params)?;
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

fn dispatch_http(operation: &str, params: &BTreeMap<String, String>) -> Result<Receipt, String> {
    match operation {
        "harmony.env.status" => Ok(env_status(param_path(params, "harmonyHome").as_deref())),
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
            Ok(project_create_plan(&root, bundle, label))
        }
        "harmony.project.verify" => {
            let root = required_param_path(params, "projectRoot")?;
            Ok(project_verify(&root))
        }
        "harmony.ohpm.install" => {
            let root = required_param_path(params, "projectRoot")?;
            let harmony = required_param_path(params, "harmonyHome")?;
            Ok(ohpm_install_plan(&root, &harmony))
        }
        "harmony.build.debug" => {
            let root = required_param_path(params, "projectRoot")?;
            let harmony = required_param_path(params, "harmonyHome")?;
            Ok(build_debug_plan(&root, &harmony))
        }
        "harmony.artifact.inspect" => {
            let artifact = required_param_path(params, "artifact")?;
            Ok(artifact_inspect(&artifact))
        }
        _ => Err(format!("unknown operation: {operation}")),
    }
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
    (
        status,
        format!(
            "{{\n  \"schema\": \"agentlab.harmony_ops.service_error.v1\",\n  \"ok\": false,\n  \"error\": {{\n    \"code\": \"{}\",\n    \"message\": \"{}\"\n  }}\n}}\n",
            json_escape(code),
            json_escape(message)
        ),
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
         serve [--bind 127.0.0.1:19731] [--workers N]\n\
         env-status [--harmony-home DIR]\n\
         project-create-plan --project-root DIR [--bundle-name NAME] [--app-label LABEL]\n\
         project-verify --project-root DIR\n\
         ohpm-install-plan --project-root DIR --harmony-home DIR\n\
         build-debug-plan --project-root DIR --harmony-home DIR\n\
         artifact-inspect --artifact FILE\n\n\
         service endpoints: GET /v1/ops/<operation>?projectRoot=...&harmonyHome=...&artifact=...
GET /v1/batch/<operation>?n=<count>&projectRoot=...&harmonyHome=...&artifact=..."
    );
    std::process::exit(code);
}
