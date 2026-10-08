//! Local, network-free contract checks, not URL/archive acquisition acceptance.
//! Set AGENTLAB_SOURCE_PROBE to the binary compiled from this public cut.
use std::{
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};
static NEXT: AtomicUsize = AtomicUsize::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "agentlab-source-material-contract-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn run(&self, request: &[u8]) -> std::process::Output {
        let file = self.0.join("request.json");
        fs::write(&file, request).unwrap();
        let before = fs::read_dir(&self.0).unwrap().count();
        let out = Command::new(
            std::env::var_os("AGENTLAB_SOURCE_PROBE").expect("build the public source probe first"),
        )
        .args(["--validate-material-request"])
        .arg(&file)
        .current_dir(&self.0)
        .output()
        .unwrap();
        assert_eq!(fs::read(&file).unwrap(), request);
        assert_eq!(fs::read_dir(&self.0).unwrap().count(), before);
        out
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
const LIMITS: &str = r#""limits":{"acquisitionBytes":1000,"expandedBytes":2000,"fileBytes":1000,"entries":20,"depth":8,"durationSeconds":30}"#;
fn request(source: &str) -> Vec<u8> {
    format!(r#"{{"schema":"agentlab.source_material_request.v1","repositoryId":"example-target","source":{source},{LIMITS}}}"#).into_bytes()
}
#[test]
fn both_material_kinds_only_validate_declarations_without_importing() {
    let f = Fixture::new();
    for source in [
        r#"{"kind":"git-http","url":"https://example.org/team/repo.git"}"#,
        r#"{"kind":"archive","locator":{"kind":"artifact","artifactId":"uploaded-example"},"format":"zip","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","bytes":12}"#,
    ] {
        let out = f.run(&request(source));
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        assert_eq!(String::from_utf8(out.stdout).unwrap(), concat!(
            "{\"acquisitionCompleted\":false,\"contractValid\":true,\"coverage\":\"request-contract-only\",",
            "\"extractionCompleted\":false,\"schema\":\"agentlab.source_material_contract_validation.v1\",",
            "\"sessionImported\":false,\"sourceBytesVerified\":false}\n"));
        assert!(out.stderr.is_empty());
    }
}
#[test]
fn rejection_does_not_echo_credential_or_unknown_field_values() {
    let f = Fixture::new();
    for source in [
        r#"{"kind":"git-http","url":"https://user:do-not-echo-example-secret@example.org/repo"}"#,
        r#"{"kind":"git-http","url":"https://example.org/repo","token":"do-not-echo-example-secret"}"#,
    ] {
        let out = f.run(&request(source));
        assert!(!out.status.success());
        assert!(out.stdout.is_empty());
        assert!(!String::from_utf8_lossy(&out.stderr).contains("do-not-echo-example-secret"));
        assert!(!out.stderr.is_empty());
    }
}
#[test]
fn oversized_request_is_rejected_before_json_decoding() {
    let out = Fixture::new().run(&vec![b' '; 32 * 1024 + 1]);
    assert!(!out.status.success());
    assert!(out.stdout.is_empty());
    assert!(String::from_utf8_lossy(&out.stderr).contains("material request byte limit exceeded"));
}

#[cfg(unix)]
#[test]
fn non_regular_inputs_are_rejected_without_following_links_or_waiting_for_a_writer() {
    use std::{
        os::unix::fs::symlink,
        process::Stdio,
        time::{Duration, Instant},
    };
    let f = Fixture::new();
    let original = f.0.join("original.json");
    fs::write(
        &original,
        request(r#"{"kind":"git-http","url":"https://example.org/repo"}"#),
    )
    .unwrap();
    let link = f.0.join("link.json");
    symlink(&original, &link).unwrap();
    let fifo = f.0.join("request.fifo");
    assert!(Command::new("mkfifo")
        .arg(&fifo)
        .status()
        .unwrap()
        .success());
    for path in [&link, &fifo, &f.0] {
        let mut child = Command::new(std::env::var_os("AGENTLAB_SOURCE_PROBE").unwrap())
            .arg("--validate-material-request")
            .arg(path)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            if child.try_wait().unwrap().is_some() {
                break;
            }
            if Instant::now() >= deadline {
                child.kill().unwrap();
                child.wait().unwrap();
                panic!("request file admission blocked");
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let out = child.wait_with_output().unwrap();
        assert!(!out.status.success());
        assert!(out.stdout.is_empty());
        assert!(String::from_utf8_lossy(&out.stderr)
            .contains("material request must be a regular file"));
    }
    assert!(fs::symlink_metadata(&link)
        .unwrap()
        .file_type()
        .is_symlink());
    assert_eq!(fs::read_dir(&f.0).unwrap().count(), 3);
}
