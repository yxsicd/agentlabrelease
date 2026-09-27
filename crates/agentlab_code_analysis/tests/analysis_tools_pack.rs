use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-analysis-tools-pack-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    root
}

fn binary_names() -> Vec<String> {
    let source =
        fs::read_to_string(repository().join("crates/agentlab_code_analysis/Cargo.toml")).unwrap();
    let mut after_bin = false;
    let mut names = Vec::new();
    for line in source.lines() {
        if line == "[[bin]]" {
            after_bin = true;
        } else if after_bin && line.starts_with("name = \"") {
            names.push(
                line.trim_start_matches("name = \"")
                    .trim_end_matches('"')
                    .to_owned(),
            );
            after_bin = false;
        }
    }
    names.sort();
    names
}

fn fake_elf(name: &str) -> Vec<u8> {
    let mut bytes = vec![0u8; 64];
    bytes[..4].copy_from_slice(b"\x7fELF");
    bytes[4] = 2;
    bytes[5] = 1;
    bytes[18..20].copy_from_slice(&62u16.to_le_bytes());
    bytes.extend_from_slice(name.as_bytes());
    bytes
}

fn fixture() -> (PathBuf, PathBuf) {
    let root = temp_root();
    let binaries = root.join("binaries");
    fs::create_dir(&binaries).unwrap();
    for name in binary_names() {
        fs::write(binaries.join(&name), fake_elf(&name)).unwrap();
    }
    (root, binaries)
}

fn run(binary_dir: &Path, output: &Path) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_agentlab-analysis-tools-pack"))
        .args([
            "--binary-dir",
            binary_dir.to_str().unwrap(),
            "--source-revision",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--version",
            "aaaaaaaa",
            "--output",
            output.to_str().unwrap(),
        ])
        .current_dir(repository())
        .output()
        .unwrap()
}

fn self_check(root: &Path) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_agentlab-analysis-tools-pack"))
        .args(["--self-check-root", root.to_str().unwrap()])
        .current_dir(repository())
        .output()
        .unwrap()
}

fn extract(archive: &Path, output: &Path) {
    fs::create_dir_all(output).unwrap();
    let tar = output.with_extension("tar");
    assert!(Command::new("zstd")
        .args(["-q", "-d", "-f"])
        .arg(archive)
        .arg("-o")
        .arg(&tar)
        .status()
        .unwrap()
        .success());
    assert!(Command::new("tar")
        .args(["-xf", tar.to_str().unwrap(), "-C", output.to_str().unwrap()])
        .status()
        .unwrap()
        .success());
    fs::remove_file(tar).unwrap();
}

#[cfg(unix)]
fn executable_install(tool_body: &str) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let root = temp_root();
    let bin = root.join("payload/bin");
    fs::create_dir_all(&bin).unwrap();
    let controller = env!("CARGO_BIN_EXE_agentlab-analysis-tools-pack");
    let mut inventory = Vec::new();
    for name in binary_names() {
        let path = bin.join(&name);
        if name == "agentlab-analysis-tools-pack" {
            fs::copy(controller, &path).unwrap();
        } else {
            let body = if name == "agentlab-source-probe" {
                tool_body
            } else {
                "#!/bin/sh\nexit 0\n"
            };
            fs::write(&path, body).unwrap();
        }
        let mut permissions = fs::metadata(&path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&path, permissions).unwrap();
        let bytes = fs::read(&path).unwrap();
        inventory.push(json!({
            "name": name,
            "path": format!("payload/bin/{name}"),
            "bytes": bytes.len(),
            "sha256": digest(&bytes)
        }));
    }
    let payload_bytes: u64 = inventory
        .iter()
        .map(|row| row["bytes"].as_u64().unwrap())
        .sum();
    let mut files = vec![json!({
        "mode": 0o755,
        "path": "bin",
        "size": 0,
        "type": "directory"
    })];
    files.extend(inventory.iter().map(|row| {
        json!({
            "mode": 0o755,
            "path": format!("bin/{}", row["name"].as_str().unwrap()),
            "sha256": row["sha256"],
            "size": row["bytes"],
            "type": "file"
        })
    }));
    let manifest = json!({
        "schema": "agentlab.capability_pack.v1",
        "analysisToolsSchema": "agentlab.analysis_tools_pack_manifest.v1",
        "packId": "analysis-tools",
        "version": "aaaaaaaa",
        "sourceRevision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "sourceGitSha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "platform": "linux-x64",
        "mountTarget": "/agentlab-analysis-tools",
        "optional": true,
        "payloadPrefix": "payload/",
        "sourceDateEpoch": 0,
        "entryCount": files.len(),
        "logicalBytes": payload_bytes,
        "files": files,
        "buildProfile": "release-static-musl-v1",
        "binaryCount": inventory.len(),
        "binaries": inventory
    });
    fs::write(
        root.join("manifest.json"),
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    root
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn archive_name() -> &'static str {
    "agentlab-pack-analysis-tools-aaaaaaaa-linux-x64.tar.zst"
}

#[test]
fn builds_byte_identical_independent_candidate_component() {
    let (root, binaries) = fixture();
    let first = root.join("first");
    let second = root.join("second");
    for output in [&first, &second] {
        let result = run(&binaries, output);
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
    for name in [
        archive_name(),
        "agentlab-pack-analysis-tools-aaaaaaaa-linux-x64.tar.zst.json",
        "analysis-tools-aaaaaaaa-linux-x64.json",
        "manifest.json",
    ] {
        assert_eq!(
            fs::read(first.join(name)).unwrap(),
            fs::read(second.join(name)).unwrap()
        );
    }
    let manifest = read(&first.join("manifest.json"));
    assert_eq!(manifest["schema"], "agentlab.capability_pack.v1");
    assert_eq!(
        manifest["analysisToolsSchema"],
        "agentlab.analysis_tools_pack_manifest.v1"
    );
    assert_eq!(manifest["packId"], "analysis-tools");
    assert_eq!(manifest["entryCount"], binary_names().len() + 1);
    assert_eq!(
        manifest["files"].as_array().unwrap().len(),
        binary_names().len() + 1
    );
    assert_eq!(manifest["binaryCount"], binary_names().len());
    assert_eq!(manifest["buildProfile"], "release-static-musl-v1");
    let tar = root.join("archive.tar");
    assert!(Command::new("zstd")
        .args(["-q", "-d", "-f"])
        .arg(first.join(archive_name()))
        .arg("-o")
        .arg(&tar)
        .status()
        .unwrap()
        .success());
    let members = Command::new("tar")
        .args(["-tf", tar.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(members.status.success());
    let members: Vec<_> = String::from_utf8(members.stdout)
        .unwrap()
        .lines()
        .map(str::to_owned)
        .collect();
    assert!(!members.iter().any(|line| line == "payload/"));
    assert_eq!(
        members
            .iter()
            .filter(|line| line.starts_with("payload/bin/agentlab-"))
            .count(),
        binary_names().len()
    );
    let archived_manifest = Command::new("tar")
        .args(["-xOf", tar.to_str().unwrap(), "manifest.json"])
        .output()
        .unwrap();
    assert!(archived_manifest.status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&archived_manifest.stdout).unwrap(),
        manifest
    );
    let update = read(&first.join("analysis-tools-aaaaaaaa-linux-x64.json"));
    assert_eq!(update["component"], "pack:analysis-tools");
    assert_eq!(update["graphNode"]["upgradePolicy"], "independent");
    assert_eq!(
        update["graphNode"]["provides"]["agentlab.analysis-tools"],
        1
    );
    assert_eq!(update["value"]["required"], false);
    assert_eq!(update["assets"].as_array().unwrap().len(), 2);
    let receipt: Value =
        serde_json::from_slice(&run(&binaries, &root.join("third")).stdout).unwrap();
    assert_eq!(receipt["status"], "candidate-component-built-not-published");
    assert_eq!(receipt["automaticPublication"], false);
    assert_eq!(receipt["automaticPromotion"], false);

    let installed = root.join("installed");
    extract(&first.join(archive_name()), &installed);
    let checked = self_check(&installed);
    assert!(
        checked.status.success(),
        "{}",
        String::from_utf8_lossy(&checked.stderr)
    );
    let checked: Value = serde_json::from_slice(&checked.stdout).unwrap();
    assert_eq!(
        checked["schema"],
        "agentlab.analysis_tools_runtime_probe.v1"
    );
    assert_eq!(checked["status"], "passed");
    assert_eq!(checked["binaryCount"], binary_names().len());
    assert_eq!(
        checked["binaries"].as_array().unwrap().len(),
        binary_names().len()
    );
    assert_eq!(checked["automaticPromotion"], false);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn self_check_rejects_installed_binary_drift() {
    let (root, binaries) = fixture();
    let output = root.join("output");
    let result = run(&binaries, &output);
    assert!(result.status.success());
    let installed = root.join("installed");
    extract(&output.join(archive_name()), &installed);
    let path = installed.join("payload/bin/agentlab-source-probe");
    let mut bytes = fs::read(&path).unwrap();
    let last = bytes.last_mut().unwrap();
    *last ^= 1;
    fs::write(&path, bytes).unwrap();
    let checked = self_check(&installed);
    assert!(!checked.status.success());
    assert!(String::from_utf8_lossy(&checked.stderr)
        .contains("installed binary sha256 mismatch: agentlab-source-probe"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn self_check_rejects_extra_installed_binary() {
    let (root, binaries) = fixture();
    let output = root.join("output");
    assert!(run(&binaries, &output).status.success());
    let installed = root.join("installed");
    extract(&output.join(archive_name()), &installed);
    fs::write(
        installed.join("payload/bin/unmanifested-tool"),
        b"unexpected",
    )
    .unwrap();
    let checked = self_check(&installed);
    assert!(!checked.status.success());
    assert!(String::from_utf8_lossy(&checked.stderr)
        .contains("installed bin directory does not match the required inventory"));
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn installed_controller_dispatches_allowlisted_tool_and_writes_bound_receipt() {
    let root = executable_install(
        "#!/bin/sh\nprintf 'child:%s:%s\\n' \"$1\" \"$2\"\nprintf 'child-error\\n' >&2\nexit 0\n",
    );
    let receipt = root.join("execution-receipt.json");
    let output = Command::new(root.join("payload/bin/agentlab-analysis-tools-pack"))
        .args([
            "--execute",
            "agentlab-source-probe",
            "--receipt",
            receipt.to_str().unwrap(),
            "--",
            "alpha",
            "beta",
        ])
        .output()
        .unwrap();
    assert!(output.status.success());
    assert_eq!(output.stdout, b"child:alpha:beta\n");
    assert_eq!(output.stderr, b"child-error\n");
    let value = read(&receipt);
    assert_eq!(value["schema"], "agentlab.analysis_tools_execution.v1");
    assert_eq!(value["status"], "passed");
    assert_eq!(value["tool"], "agentlab-source-probe");
    assert_eq!(value["argumentCount"], 2);
    assert_eq!(value["exitCode"], 0);
    assert_eq!(value["automaticPromotion"], false);
    assert_eq!(
        value["argumentsSha256"],
        digest(&serde_json::to_vec(&["alpha", "beta"]).unwrap())
    );
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn installed_controller_propagates_failure_and_refuses_receipt_overwrite() {
    let root = executable_install("#!/bin/sh\nexit 7\n");
    let receipt = root.join("execution-receipt.json");
    let controller = root.join("payload/bin/agentlab-analysis-tools-pack");
    let first = Command::new(&controller)
        .args([
            "--execute",
            "agentlab-source-probe",
            "--receipt",
            receipt.to_str().unwrap(),
            "--",
        ])
        .output()
        .unwrap();
    assert_eq!(first.status.code(), Some(7));
    let value = read(&receipt);
    assert_eq!(value["status"], "failed");
    assert_eq!(value["exitCode"], 7);
    let before = fs::read(&receipt).unwrap();
    let second = Command::new(&controller)
        .args([
            "--execute",
            "agentlab-source-probe",
            "--receipt",
            receipt.to_str().unwrap(),
            "--",
        ])
        .output()
        .unwrap();
    assert_eq!(second.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&second.stderr).contains("cannot create execution receipt"));
    assert_eq!(fs::read(&receipt).unwrap(), before);
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn installed_controller_rejects_unlisted_tool_before_creating_receipt() {
    let root = executable_install("#!/bin/sh\nexit 0\n");
    let receipt = root.join("execution-receipt.json");
    let output = Command::new(root.join("payload/bin/agentlab-analysis-tools-pack"))
        .args([
            "--execute",
            "unlisted-tool",
            "--receipt",
            receipt.to_str().unwrap(),
            "--",
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("tool is not in the installed inventory")
    );
    assert!(!receipt.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_missing_binary_and_removes_partial_output() {
    let (root, binaries) = fixture();
    fs::remove_file(binaries.join("agentlab-source-probe")).unwrap();
    let output = root.join("output");
    let result = run(&binaries, &output);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("cannot inspect binary"));
    assert!(!output.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_non_linux_x86_64_binary() {
    let (root, binaries) = fixture();
    fs::write(binaries.join("agentlab-source-probe"), b"not-an-elf").unwrap();
    let result = run(&binaries, &root.join("output"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("binary is not Linux x86-64 ELF: agentlab-source-probe"));
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn rejects_symlinked_binary() {
    use std::os::unix::fs::symlink;

    let (root, binaries) = fixture();
    let path = binaries.join("agentlab-source-probe");
    let target = root.join("source-probe-target");
    fs::rename(&path, &target).unwrap();
    symlink(&target, &path).unwrap();
    let result = run(&binaries, &root.join("output"));
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("binary must be a regular file: agentlab-source-probe"));
    fs::remove_dir_all(root).unwrap();
}
