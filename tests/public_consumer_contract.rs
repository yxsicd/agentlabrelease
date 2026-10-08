//! Standalone Rust behavioral checks: rustc --test tests/public_consumer_contract.rs.
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "agentlab-consumer-rust-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn docker(&self, body: &str) {
        use std::os::unix::fs::PermissionsExt;
        let file = self.0.join("docker");
        fs::write(&file, format!("#!/bin/sh\n{body}\n")).unwrap();
        fs::set_permissions(&file, fs::Permissions::from_mode(0o700)).unwrap();
    }
    fn run(&self, script: &str, args: &[&str]) -> Output {
        Command::new("/bin/bash")
            .arg(script)
            .args(args)
            .env("PATH", format!("{}:/usr/bin:/bin", self.0.display()))
            .env("HOME", &self.0)
            .output()
            .unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        // Exact test-owned directory only, never a user installation.
        fs::remove_dir_all(&self.0).unwrap();
    }
}
const INVENTORY: &str = "scripts/agentlab-resource-inventory.sh";
const INSTALL: &str = "scripts/agentlab-composition-install.sh";

#[test]
fn help_needs_no_docker_and_has_no_footprint() {
    let f = Fixture::new();
    let before = fs::read_dir(&f.0).unwrap().count();
    for script in [INVENTORY, INSTALL] {
        let out = f.run(script, &["--help"]);
        assert!(out.status.success());
    }
    assert_eq!(before, fs::read_dir(&f.0).unwrap().count());
}
#[test]
fn inventory_rejects_execution_request() {
    let f = Fixture::new();
    assert_eq!(f.run(INVENTORY, &["--execute"]).status.code(), Some(2));
    assert_eq!(fs::read_dir(&f.0).unwrap().count(), 0);
}
#[test]
fn inventory_preserves_docker_failure() {
    let f = Fixture::new();
    f.docker("exit 17");
    let out = f.run(INVENTORY, &[]);
    assert_eq!(out.status.code(), Some(17));
    assert!(out.stdout.is_empty());
}
#[test]
fn malformed_identity_stops_before_inspection() {
    let f = Fixture::new();
    f.docker(
        "case \"$1\" in version) exit 0;; ps) echo --privileged;; *) echo UNSAFE; exit 31;; esac",
    );
    let out = f.run(INVENTORY, &[]);
    assert_eq!(out.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&out.stderr).contains("invalid Docker identity"));
    assert!(!String::from_utf8_lossy(&out.stdout).contains("UNSAFE"));
}
#[test]
fn inventory_uses_only_bounded_read_surfaces() {
    let f = Fixture::new();
    let id = "a".repeat(64);
    f.docker(&format!(
        "case \"$1\" in\nversion) exit 0;;\nps) echo {id};;\ncontainer) case \"$*\" in *Config.Env*|*'json .}}'*) exit 32;; esac; echo '{{\"kind\":\"container\",\"id\":\"{id}\"}}';;\nvolume) [ \"$2\" = ls ] || exit 33; echo '{{\"kind\":\"volume-candidate\",\"ownershipVerified\":false}}';;\n*) exit 34;;\nesac"
    ));
    let out = f.run(INVENTORY, &[]);
    assert!(out.status.success(), "{:?}", out);
    let text = String::from_utf8(out.stdout).unwrap();
    assert_eq!(text.lines().count(), 3);
    assert!(text.contains("\"deletionAuthorized\":false"));
    assert!(text.contains("\"ownershipVerified\":false"));
}
#[test]
fn unsafe_roots_rejected_before_acquisition() {
    let f = Fixture::new();
    f.docker("echo DOCKER_INVOKED; exit 39");
    let home = f.0.to_str().unwrap();
    for root in [
        "/",
        "relative",
        home,
        "/tmp",
        "/usr",
        "/tmp/quote\"bad",
        "/tmp/back\\slash",
        "/tmp/new\nline",
        "/tmp/tab\tpath",
        "/tmp/a/../b",
        "/tmp/a/./b",
        "/tmp//b",
    ] {
        let out = f.run(INSTALL, &["online", "--root", root]);
        assert_eq!(out.status.code(), Some(2), "{root:?}");
        assert!(!String::from_utf8_lossy(&out.stdout).contains("DOCKER_INVOKED"));
    }
}
#[test]
fn symlink_install_root_is_rejected() {
    use std::os::unix::fs::symlink;
    let f = Fixture::new();
    let link = f.0.join("alias");
    symlink(&f.0, &link).unwrap();
    assert_eq!(
        f.run(INSTALL, &["online", "--root", link.to_str().unwrap()])
            .status
            .code(),
        Some(2)
    );
    let child = link.join("child");
    assert_eq!(
        f.run(INSTALL, &["online", "--root", child.to_str().unwrap()])
            .status
            .code(),
        Some(2)
    );
    assert!(!f.0.join("bin").exists());
}
#[test]
fn unsafe_cache_root_is_rejected_before_docker() {
    let f = Fixture::new();
    f.docker("echo DOCKER_INVOKED; exit 39");
    let out = f.run(
        INSTALL,
        &[
            "online",
            "--root",
            "/home/example/agentlab-test",
            "--cache-dir",
            "/",
        ],
    );
    assert_eq!(out.status.code(), Some(2));
    assert!(!String::from_utf8_lossy(&out.stdout).contains("DOCKER_INVOKED"));
}
#[test]
fn unknown_install_action_never_selects_legacy_path() {
    let f = Fixture::new();
    assert_eq!(f.run(INSTALL, &["online-install"]).status.code(), Some(2));
    assert!(!Path::new(&f.0).join("bin").exists());
}
