use agentlab_code_analysis::{digest, maintainer_construction_context::prepare};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

struct Fixture {
    root: PathBuf,
    source: PathBuf,
    knowledge: PathBuf,
    revision: String,
}
fn git(root: &Path, args: &[&str]) -> String {
    let result = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    String::from_utf8(result.stdout).unwrap().trim().into()
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "agentlab-context-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let source = root.join("source");
        let knowledge = root.join("knowledge");
        fs::create_dir_all(source.join("pkg/tests")).unwrap();
        fs::create_dir_all(&knowledge).unwrap();
        fs::write(source.join("build.cfg"), "library-output=true\n").unwrap();
        fs::write(source.join("large.cfg"), vec![b'a'; 65537]).unwrap();
        fs::write(source.join("binary.cfg"), [0xff, 0xfe]).unwrap();
        fs::write(source.join("pkg/main.rs"), "pub fn value() -> u8 { 1 }\n").unwrap();
        fs::write(
            source.join("pkg/tests/check.rs"),
            "#[test] fn template() { assert!(true); }\n",
        )
        .unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink("main.rs", source.join("pkg/link.rs")).unwrap();
        git(&source, &["init", "-q"]);
        git(&source, &["config", "user.name", "Fixture"]);
        git(
            &source,
            &["config", "user.email", "fixture@example.invalid"],
        );
        git(
            &source,
            &[
                "remote",
                "add",
                "origin",
                "https://example.invalid/arbitrary.git",
            ],
        );
        git(&source, &["add", "."]);
        git(&source, &["commit", "-qm", "baseline"]);
        let revision = git(&source, &["rev-parse", "HEAD"]);
        let scope = |id: &str, boundary: &str| json!({"id":id,"repositoryId":"arbitrary","repository":"https://example.invalid/arbitrary.git","sourceRevision":revision,"pathBoundary":boundary});
        // Explicit selectors allow disjoint responsibilities without claiming siblings.
        let mut implementation = scope("implementation", "pkg");
        implementation["ownershipSelectors"] =
            json!([{"type":"files","paths":["pkg/main.rs","pkg/link.rs"]}]);
        let rows = [
            scope("root", "."),
            implementation,
            scope("verification", "pkg/tests"),
        ];
        fs::write(
            knowledge.join("maintainer_scope_skills.jsonl"),
            rows.iter()
                .map(|r| serde_json::to_string(r).unwrap() + "\n")
                .collect::<String>(),
        )
        .unwrap();
        for file in [
            "maintainer_skills.jsonl",
            "program_facts.jsonl",
            "maintainer_skill_refresh_rounds.jsonl",
            "evaluation_cases.jsonl",
        ] {
            fs::write(knowledge.join(file), b"").unwrap();
        }
        let mut tables = serde_json::Map::new();
        for (key, file) in [
            ("maintainerSkills", "maintainer_skills.jsonl"),
            ("maintainerScopeSkills", "maintainer_scope_skills.jsonl"),
            ("programFacts", "program_facts.jsonl"),
            (
                "maintainerSkillRefreshRounds",
                "maintainer_skill_refresh_rounds.jsonl",
            ),
            ("evaluationCases", "evaluation_cases.jsonl"),
        ] {
            tables.insert(
                key.into(),
                json!({"path":file,"sha256":digest(&fs::read(knowledge.join(file)).unwrap())}),
            );
        }
        fs::write(knowledge.join("maintainer-knowledge-cut.json"),serde_json::to_vec(&json!({"schema":"agentlab.maintainer_knowledge_cut.v1","automaticPromotion":false,"tableGitAuthority":{"revision":"a".repeat(40)},"tables":tables,"repositories":[{"id":"arbitrary","repository":"https://example.invalid/arbitrary.git","revision":revision}]})).unwrap()).unwrap();
        Self {
            root,
            source,
            knowledge,
            revision,
        }
    }
    fn scopes(&self, change: impl FnOnce(&mut Vec<Value>)) {
        let path = self.knowledge.join("maintainer_scope_skills.jsonl");
        let mut rows: Vec<Value> = fs::read_to_string(&path)
            .unwrap()
            .lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .collect();
        change(&mut rows);
        let bytes = rows
            .iter()
            .map(|r| serde_json::to_string(r).unwrap() + "\n")
            .collect::<String>();
        fs::write(&path, &bytes).unwrap();
        let cut_path = self.knowledge.join("maintainer-knowledge-cut.json");
        let mut cut: Value = serde_json::from_slice(&fs::read(&cut_path).unwrap()).unwrap();
        cut["tables"]["maintainerScopeSkills"]["sha256"] = json!(digest(bytes.as_bytes()));
        fs::write(cut_path, serde_json::to_vec(&cut).unwrap()).unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}

#[test]
fn exact_cross_scope_context_is_repeatable_readonly_and_does_not_grant_edits() {
    let f = Fixture::new();
    let paths = vec![
        "pkg/tests/check.rs".into(),
        "build.cfg".into(),
        "pkg/main.rs".into(),
    ];
    let before = fs::read(f.knowledge.join("maintainer-knowledge-cut.json")).unwrap();
    let first = prepare(&f.knowledge, &f.source, "arbitrary", &paths).unwrap();
    let mut reversed = paths.clone();
    reversed.reverse();
    assert_eq!(
        first,
        prepare(&f.knowledge, &f.source, "arbitrary", &reversed).unwrap()
    );
    assert_eq!(
        first["ownerScopeSkillIds"],
        json!(["implementation", "root", "verification"])
    );
    assert_eq!(first["repository"]["revision"], f.revision);
    for e in first["selectedFiles"].as_array().unwrap() {
        let bytes = fs::read(f.source.join(e["path"].as_str().unwrap())).unwrap();
        assert_eq!(e["sha256"], digest(&bytes));
        assert_eq!(e["contentUtf8"], std::str::from_utf8(&bytes).unwrap());
        assert_eq!(e["access"], "read-only");
    }
    for key in [
        "automaticPromotion",
        "authorityWritePerformed",
        "semanticQualified",
        "executionQualified",
        "grantsEditablePaths",
    ] {
        assert_eq!(first[key], false);
    }
    assert_eq!(
        before,
        fs::read(f.knowledge.join("maintainer-knowledge-cut.json")).unwrap()
    );
    assert!(git(&f.source, &["status", "--porcelain"]).is_empty());
}

#[test]
fn unsafe_missing_unowned_overlapping_and_stale_context_is_rejected() {
    for scenario in [
        "empty",
        "duplicate",
        "traversal",
        "absolute",
        "missing",
        "directory",
        "unowned",
        "overlap",
        "stale",
        "duplicate-row",
        "dirty",
        "origin",
        "revision",
        "digest",
        "symlink",
        "budget",
        "utf8",
        "too-many",
    ] {
        let f = Fixture::new();
        let mut paths: Vec<String> = vec!["pkg/main.rs".into()];
        match scenario {
            "empty" => paths.clear(),
            "duplicate" => paths.push(paths[0].clone()),
            "traversal" => paths = vec!["pkg/../build.cfg".into()],
            "absolute" => paths = vec!["/build.cfg".into()],
            "missing" => paths = vec!["pkg/absent.rs".into()],
            "directory" => paths = vec!["pkg/tests".into()],
            "unowned" => f.scopes(|s| {
                s.remove(1);
            }),
            "overlap" => f.scopes(|s| {
                let mut row = s[1].clone();
                row["id"] = json!("another");
                s.push(row);
            }),
            "stale" => f.scopes(|s| s[1]["sourceRevision"] = json!("b".repeat(40))),
            "duplicate-row" => f.scopes(|s| s.push(s[1].clone())),
            "dirty" => {
                fs::write(f.source.join("pkg/main.rs"), "changed").unwrap();
            }
            "origin" => {
                git(
                    &f.source,
                    &[
                        "remote",
                        "set-url",
                        "origin",
                        "https://example.invalid/other.git",
                    ],
                );
            }
            "revision" => {
                git(&f.source, &["commit", "--allow-empty", "-qm", "other"]);
            }
            "digest" => {
                fs::write(f.knowledge.join("program_facts.jsonl"), "{}\n").unwrap();
            }
            "symlink" => paths = vec!["pkg/link.rs".into()],
            "budget" => paths = vec!["large.cfg".into()],
            "utf8" => paths = vec!["binary.cfg".into()],
            "too-many" => paths = (0..33).map(|n| format!("file-{n}")).collect(),
            _ => unreachable!(),
        }
        assert!(
            prepare(&f.knowledge, &f.source, "arbitrary", &paths).is_err(),
            "{scenario}"
        );
    }
}

#[test]
fn context_cli_refuses_to_replace_a_retained_packet() {
    let f = Fixture::new();
    let output = f.root.join("packet.json");
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--prepare-construction-context")
            .arg("--knowledge")
            .arg(&f.knowledge)
            .arg("--source-worktree")
            .arg(&f.source)
            .args([
                "--repository",
                "arbitrary",
                "--context-path",
                "build.cfg",
                "--output",
            ])
            .arg(&output)
            .output()
            .unwrap()
    };
    assert!(run().status.success());
    let bytes = fs::read(&output).unwrap();
    assert!(!run().status.success());
    assert_eq!(bytes, fs::read(output).unwrap());
}
