use serde_json::Value;
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
static NEXT_FIXTURE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
struct Fixture(std::path::PathBuf);
impl Fixture {
    fn new() -> Self {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "al-rust-ast-{}-{stamp}-{}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        git(&path, &["init", "-q"]);
        Self(path)
    }
    fn commit(&self) {
        git(&self.0, &["add", "."]);
        git(
            &self.0,
            &[
                "-c",
                "user.name=AST test",
                "-c",
                "user.email=ast@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
        );
    }
    fn run(&self, directory: &str) -> (Value, Vec<u8>) {
        let out = self.0.join(directory);
        let result = Command::new(env!("CARGO_BIN_EXE_agentlab-code-analysis"))
            .arg(&self.0)
            .arg(&out)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        (
            serde_json::from_slice(&result.stdout).unwrap(),
            fs::read(out.join("program_facts.jsonl")).unwrap(),
        )
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}
fn git(root: &Path, args: &[&str]) {
    let result = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
#[test]
fn committed_source_is_authority_and_export_is_byte_stable() {
    let fixture = Fixture::new();
    fs::write(fixture.0.join("Demo.ets"),"import {\n A\n} from './A';\n@Component struct Demo { build() { Column() { Text('ok') } } }").unwrap();
    fs::write(
        fixture.0.join("A.ts"),
        "export class A { run() { actual(); } }",
    )
    .unwrap();
    fixture.commit();
    let (before, bytes) = fixture.run("first-output");
    assert_eq!(before["files"], 2);
    assert_eq!(before["filesWithSyntaxErrors"], 0);
    fs::write(fixture.0.join("Demo.ets"), "dirty broken source ???").unwrap();
    fs::write(fixture.0.join("untracked.ets"), "class Unexpected {}").unwrap();
    let (after, repeated) = fixture.run("second-output");
    assert_eq!(before, after);
    assert_eq!(bytes, repeated);
    let facts: Vec<Value> = bytes
        .split(|b| *b == b'\n')
        .filter(|x| !x.is_empty())
        .map(|x| serde_json::from_slice(x).unwrap())
        .collect();
    assert!(facts
        .iter()
        .any(|r| r["kind"] == "module-reference" && r["specifier"] == "./A"));
    assert_eq!(before["sha256"], agentlab_code_analysis::digest(&bytes));
}
#[test]
fn syntax_failure_is_retained_without_claiming_full_qualification() {
    let fixture = Fixture::new();
    fs::write(fixture.0.join("Bad.ets"), "class { ???").unwrap();
    fixture.commit();
    let (receipt, bytes) = fixture.run("output");
    assert_eq!(receipt["filesWithSyntaxErrors"], 1);
    assert_eq!(receipt["syntaxClean"], false);
    assert_eq!(receipt["fullArkTSQualified"], false);
    assert!(bytes
        .split(|b| *b == b'\n')
        .filter(|x| !x.is_empty())
        .map(|x| serde_json::from_slice::<Value>(x).unwrap())
        .any(|r| r["kind"] == "parse-error"));
}
