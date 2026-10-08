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
        Self(path.canonicalize().unwrap())
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
const MCPGIT_INSTALL: &str = "scripts/agentlab-mcpgit-prod-install.sh";

#[test]
fn verified_public_executable_is_container_readable_without_writable_bits() {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let f = Fixture::new();
    fs::set_permissions(&f.0, fs::Permissions::from_mode(0o700)).unwrap();
    let executable = f.0.join("public-controller");
    let bytes = b"immutable verified public code, not credentials\n";
    fs::write(&executable, bytes).unwrap();
    fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
    let before = fs::metadata(&executable).unwrap();
    let script = fs::read_to_string(INSTALL).unwrap();
    let body = script
        .split("prepare_public_executable() {\n")
        .nth(1)
        .unwrap()
        .split("\n}")
        .next()
        .unwrap();
    assert_eq!(
        script
            .matches("prepare_public_executable \"${temporary}\"")
            .count(),
        2,
        "online and offline must prepare the verified executable identically"
    );
    let result = Command::new("/bin/bash")
        .args([
            "-ceu",
            &format!(
                "prepare_public_executable() {{\n{body}\n}}\nprepare_public_executable \"$1\""
            ),
            "gate",
        ])
        .arg(&executable)
        .output()
        .unwrap();
    assert!(result.status.success());
    let after = fs::metadata(&executable).unwrap();
    assert_eq!(after.mode() & 0o777, 0o555);
    assert_eq!(
        (after.uid(), after.gid(), after.ino()),
        (before.uid(), before.gid(), before.ino())
    );
    assert_eq!(fs::read(&executable).unwrap(), bytes);
    assert_eq!(fs::metadata(&f.0).unwrap().mode() & 0o777, 0o700);
}

#[test]
fn inspect_is_no_footprint_and_rejects_untrusted_control_without_execution() {
    use std::os::unix::fs::PermissionsExt;
    let f = Fixture::new();
    f.docker("[ \"$1\" = version ] || exit 45");
    let uname = f.0.join("uname");
    fs::write(
        &uname,
        "#!/bin/sh\ncase \"$1\" in -s) echo Linux;; -m) echo x86_64;; *) exit 46;; esac\n",
    )
    .unwrap();
    fs::set_permissions(&uname, fs::Permissions::from_mode(0o700)).unwrap();
    let root = f.0.join("instance");
    let before = fs::read_dir(&f.0).unwrap().count();
    let missing = f.run(INSTALL, &["inspect", "--root", root.to_str().unwrap()]);
    assert_eq!(missing.status.code(), Some(2));
    assert!(!root.exists());
    assert_eq!(before, fs::read_dir(&f.0).unwrap().count());
    fs::create_dir_all(root.join("bin")).unwrap();
    let control = root.join("bin/agentlabctl");
    fs::write(&control, "#!/bin/sh\necho UNTRUSTED_EXECUTED\n").unwrap();
    fs::set_permissions(&control, fs::Permissions::from_mode(0o700)).unwrap();
    let rejected = f.run(INSTALL, &["inspect", "--root", root.to_str().unwrap()]);
    assert_eq!(rejected.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("unexpected agentlabctl identity"));
    assert!(!String::from_utf8_lossy(&rejected.stdout).contains("UNTRUSTED_EXECUTED"));
    assert!(!root.join("receipts").exists() && !root.join("cache").exists());
}

#[test]
fn published_demo_hashes_without_optional_file_digest_api() {
    let f = Fixture::new();
    let file = f.0.join("artifact");
    fs::write(&file, b"abc").unwrap();
    let out = Command::new("python3")
        .args(["-c", "import hashlib,pathlib,runpy,sys; hashlib.file_digest=lambda *args: (_ for _ in ()).throw(RuntimeError('optional API must not be called')); module=runpy.run_path('examples/run.py'); print(module['sha256'](pathlib.Path(sys.argv[1])))"])
        .arg(file)
        .output().unwrap();
    assert!(out.status.success(), "{:?}", out);
    assert_eq!(
        String::from_utf8(out.stdout).unwrap().trim(),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
}

#[test]
fn release_gate_rejects_whole_context_keys_and_legacy_fallback() {
    let code = r#"
import json,pathlib,runpy,sys
original=pathlib.Path.read_text
def altered(self,*args,**kwargs):
    text=original(self,*args,**kwargs)
    if self == pathlib.Path.cwd() / 'manifest.json':
        value=json.loads(text)
        if sys.argv[1]=='context': value['defaultParticipant']['context']='whole-supervisor-conversation'
        elif sys.argv[1]=='key': value['defaultParticipant']['independentProviderKeyRequired']=True
        else: value['acceptance']['legacyFallback']=True
        return json.dumps(value)
    return text
pathlib.Path.read_text=altered
runpy.run_path('scripts/validate-release.py')
"#;
    for mutation in ["context", "key", "legacy"] {
        let out = Command::new("python3")
            .args(["-c", code, mutation])
            .output()
            .unwrap();
        assert!(
            !out.status.success(),
            "invalid contract accepted: {mutation}"
        );
        assert!(String::from_utf8_lossy(&out.stderr).contains("AssertionError"));
    }
}

#[test]
fn network_policy_refuses_fixed_subnets_missing_inventory_and_shared_renumbering() {
    let code = r#"
import json,pathlib,runpy,sys
original=pathlib.Path.read_text
def altered(self,*args,**kwargs):
    text=original(self,*args,**kwargs)
    if self == pathlib.Path.cwd() / 'manifest.json':
        value=json.loads(text); policy=value['newInstanceNetwork']
        mutation=sys.argv[1]
        if mutation=='fixed': policy['selection']='fixed-192.168.237.0/24'
        elif mutation=='inventory': policy['inventory'].remove('dns-resolvers')
        elif mutation=='wsl': policy['wslHostRoutesRequired']=False
        elif mutation=='public-range': policy['fallbackPrivateIPv4Range']='192.0.0.0/8'
        elif mutation=='replace-existing': policy['existingNetwork']='always-replace'
        elif mutation=='migration': policy['existingNetworkMigration']='automatic'
        else: policy['provisioningQualified']=True
        return json.dumps(value)
    return text
pathlib.Path.read_text=altered
runpy.run_path('scripts/validate-release.py')
"#;
    for mutation in [
        "fixed",
        "inventory",
        "wsl",
        "public-range",
        "replace-existing",
        "migration",
        "qualification",
    ] {
        let out = Command::new("python3")
            .args(["-c", code, mutation])
            .output()
            .unwrap();
        assert!(
            !out.status.success(),
            "invalid network policy accepted: {mutation}"
        );
        // Assert the intended gate, not an unrelated checksum failure.
        assert!(String::from_utf8_lossy(&out.stderr)
            .contains("AssertionError: new-instance-network-policy"));
    }
}

#[test]
fn help_needs_no_docker_and_has_no_footprint() {
    let f = Fixture::new();
    let before = fs::read_dir(&f.0).unwrap().count();
    for script in [INVENTORY, INSTALL, MCPGIT_INSTALL] {
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
        for (script, action) in [(INSTALL, "online"), (MCPGIT_INSTALL, "install")] {
            let out = f.run(script, &[action, "--root", root]);
            assert_eq!(out.status.code(), Some(2), "{script}: {root:?}");
            assert!(!String::from_utf8_lossy(&out.stdout).contains("DOCKER_INVOKED"));
        }
    }
}
#[test]
fn symlink_install_root_is_rejected() {
    use std::os::unix::fs::symlink;
    let f = Fixture::new();
    let link = f.0.join("alias");
    symlink(&f.0, &link).unwrap();
    let child = link.join("child");
    for (script, action) in [(INSTALL, "online"), (MCPGIT_INSTALL, "install")] {
        for root in [&link, &child] {
            assert_eq!(
                f.run(script, &[action, "--root", root.to_str().unwrap()])
                    .status
                    .code(),
                Some(2)
            );
        }
    }
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
