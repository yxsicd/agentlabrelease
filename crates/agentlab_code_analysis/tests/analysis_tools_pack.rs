use serde_json::Value;
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
    assert_eq!(
        String::from_utf8(members.stdout)
            .unwrap()
            .lines()
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
