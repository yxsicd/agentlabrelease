use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    repositories: Vec<PathBuf>,
}

impl Fixture {
    fn new() -> Self {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "agentlab-multi-repo-{}-{stamp}-{}",
            std::process::id(),
            FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        Self {
            root,
            repositories: Vec::new(),
        }
    }

    fn repository(&mut self, name: &str, files: &[(&str, &str)]) -> (PathBuf, String) {
        let root = self.root.join(name);
        fs::create_dir_all(&root).unwrap();
        git(&root, &["init", "-q"]);
        for (path, body) in files {
            let target = root.join(path);
            fs::create_dir_all(target.parent().unwrap()).unwrap();
            fs::write(target, body).unwrap();
        }
        git(&root, &["add", "."]);
        git(
            &root,
            &[
                "-c",
                "user.name=Multi repo test",
                "-c",
                "user.email=multi@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
        );
        let revision = git_output(&root, &["rev-parse", "HEAD"]);
        self.repositories.push(root.clone());
        (root, revision)
    }

    fn run(&self, manifest: &Value, name: &str) -> std::process::Output {
        let manifest_path = self.root.join(format!("{name}.json"));
        let output_path = self.root.join(format!("{name}-output"));
        fs::write(&manifest_path, serde_json::to_vec_pretty(manifest).unwrap()).unwrap();
        Command::new(env!("CARGO_BIN_EXE_agentlab-multi-repo-analysis"))
            .arg(manifest_path)
            .arg(output_path)
            .output()
            .unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
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

fn git_output(root: &Path, args: &[&str]) -> String {
    let result = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .unwrap();
    assert!(result.status.success());
    String::from_utf8(result.stdout).unwrap().trim().to_owned()
}

fn rows(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

#[test]
fn exact_three_repository_graph_drives_recursive_difficulty_candidates() {
    let mut fixture = Fixture::new();
    let (contracts, contracts_revision) = fixture.repository(
        "contracts",
        &[(
            "src/contracts.ts",
            "export interface Contract { id: string }",
        )],
    );
    let (service, service_revision) = fixture.repository(
        "service",
        &[(
            "src/service.ts",
            "import { Contract } from '@demo/contracts'; export function load(): Contract { return { id: '1' }; }",
        )],
    );
    let (app, app_revision) = fixture.repository(
        "app",
        &[
            (
                "src/feature.ts",
                "import { load } from '@demo/service'; export function feature() { return load(); }",
            ),
            (
                "src/main.ets",
                "import { feature } from './feature'; import missing from './missing'; feature();",
            ),
        ],
    );
    let manifest = json!({
        "schema":"agentlab.multi_repo_manifest.v1",
        "repositories":[
            {"id":"app","repository":"fixture://app","root":app,"revision":app_revision},
            {"id":"contracts","repository":"fixture://contracts","root":contracts,"revision":contracts_revision},
            {"id":"service","repository":"fixture://service","root":service,"revision":service_revision}
        ],
        "moduleBindings":{
            "@demo/contracts":{"repositoryId":"contracts","path":"src/contracts.ts"},
            "@demo/service":{"repositoryId":"service","path":"src/service.ts"}
        }
    });
    let first = fixture.run(&manifest, "first");
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    let receipt: Value = serde_json::from_slice(&first.stdout).unwrap();
    assert_eq!(receipt["crossRepositoryEdges"], 2);
    assert_eq!(receipt["moduleDependencyEdges"], 3);
    assert_eq!(receipt["unresolvedModuleReferences"], 1);
    assert_eq!(receipt["sourceSetSha256"].as_str().unwrap().len(), 64);
    let facts = rows(&fixture.root.join("first-output/workspace_facts.jsonl"));
    assert_eq!(
        facts
            .iter()
            .filter(|row| row["kind"] == "module-dependency")
            .count(),
        3
    );
    assert!(facts.iter().any(|row| {
        row["kind"] == "module-reference"
            && row["specifier"] == "@demo/contracts"
            && row["resolution"] == "resolved"
            && row["targetRepositoryId"] == "contracts"
    }));
    assert!(facts.iter().any(|row| {
        row["kind"] == "module-dependency"
            && row["sourceIdentity"]
                .as_str()
                .unwrap()
                .starts_with("git:fixture://")
            && row["targetIdentity"]
                .as_str()
                .unwrap()
                .starts_with("git:fixture://")
    }));
    let difficulty: Value = serde_json::from_slice(
        &fs::read(fixture.root.join("first-output/difficulty_candidates.json")).unwrap(),
    )
    .unwrap();
    let contracts_impact = difficulty["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| {
            row["dimensionId"] == "multi-repository-change-impact"
                && row["seed"]["repositoryId"] == "contracts"
        })
        .unwrap();
    assert_eq!(contracts_impact["affectedRepositoryCount"], 3);
    assert_eq!(contracts_impact["maxDependencyDepth"], 3);
    assert_eq!(contracts_impact["verificationContract"]["caseReady"], false);
    assert!(difficulty["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|row| {
            row["dimensionId"] == "unresolved-module-boundary"
                && row["seed"]["specifier"] == "./missing"
        }));

    // Dirty and untracked workspace bytes are not analysis authority.
    fs::write(
        fixture.repositories[2].join("src/feature.ts"),
        "broken dirty bytes ???",
    )
    .unwrap();
    fs::write(
        fixture.repositories[2].join("src/untracked.ts"),
        "unexpected();",
    )
    .unwrap();
    let second = fixture.run(&manifest, "second");
    assert!(second.status.success());
    assert_eq!(
        fs::read(fixture.root.join("first-output/workspace_facts.jsonl")).unwrap(),
        fs::read(fixture.root.join("second-output/workspace_facts.jsonl")).unwrap()
    );
    assert_eq!(
        fs::read(fixture.root.join("first-output/difficulty_candidates.json")).unwrap(),
        fs::read(
            fixture
                .root
                .join("second-output/difficulty_candidates.json")
        )
        .unwrap()
    );

    // Moving the exact object databases changes the local manifest receipt but
    // not portable facts or difficulty evidence.
    let mut relocated = manifest.clone();
    for entry in relocated["repositories"].as_array_mut().unwrap() {
        let id = entry["id"].as_str().unwrap();
        let original = PathBuf::from(entry["root"].as_str().unwrap());
        let target = fixture.root.join(format!("relocated-{id}"));
        let result = Command::new("git")
            .arg("clone")
            .arg("-q")
            .arg(original)
            .arg(&target)
            .output()
            .unwrap();
        assert!(result.status.success());
        entry["root"] = json!(target);
    }
    let third = fixture.run(&relocated, "relocated");
    assert!(third.status.success());
    assert_eq!(
        fs::read(fixture.root.join("first-output/workspace_facts.jsonl")).unwrap(),
        fs::read(fixture.root.join("relocated-output/workspace_facts.jsonl")).unwrap()
    );
    assert_eq!(
        fs::read(fixture.root.join("first-output/difficulty_candidates.json")).unwrap(),
        fs::read(
            fixture
                .root
                .join("relocated-output/difficulty_candidates.json")
        )
        .unwrap()
    );
}

#[test]
fn manifest_refuses_symbolic_revisions_and_missing_bound_targets() {
    let mut fixture = Fixture::new();
    let (one, revision_one) = fixture.repository("one", &[("one.ts", "export const one = 1;")]);
    let (two, revision_two) = fixture.repository("two", &[("two.ts", "export const two = 2;")]);
    let symbolic = json!({
        "schema":"agentlab.multi_repo_manifest.v1",
        "repositories":[
            {"id":"one","repository":"fixture://one","root":one,"revision":"HEAD"},
            {"id":"two","repository":"fixture://two","root":two,"revision":revision_two}
        ]
    });
    let result = fixture.run(&symbolic, "symbolic");
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("40-character Git revision"));

    let absent = json!({
        "schema":"agentlab.multi_repo_manifest.v1",
        "repositories":[
            {"id":"one","repository":"fixture://one","root":fixture.repositories[0],"revision":revision_one},
            {"id":"two","repository":"fixture://two","root":fixture.repositories[1],"revision":revision_two}
        ],
        "moduleBindings":{"@absent":{"repositoryId":"two","path":"absent.ts"}}
    });
    let result = fixture.run(&absent, "absent");
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("absent at pinned revision"));
}

#[test]
fn shared_external_module_contract_becomes_non_ready_multi_repo_candidate() {
    let mut fixture = Fixture::new();
    let (one, revision_one) = fixture.repository(
        "one",
        &[(
            "src/first.ets",
            "import { router } from '@kit.ArkUI'; export function first() { return router; }",
        )],
    );
    let (two, revision_two) = fixture.repository(
        "two",
        &[(
            "src/second.ets",
            "import { router } from '@kit.ArkUI'; export function second() { return router; }",
        )],
    );
    let manifest = json!({
        "schema":"agentlab.multi_repo_manifest.v1",
        "repositories":[
            {"id":"one","repository":"fixture://one","root":one,"revision":revision_one},
            {"id":"two","repository":"fixture://two","root":two,"revision":revision_two}
        ]
    });
    let result = fixture.run(&manifest, "shared-external");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let receipt: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(receipt["sharedExternalModuleContracts"], 1);
    let difficulty: Value = serde_json::from_slice(
        &fs::read(
            fixture
                .root
                .join("shared-external-output/difficulty_candidates.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let candidate = difficulty["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["relationType"] == "shared-external-module-contract")
        .unwrap();
    assert_eq!(candidate["seed"]["specifier"], "@kit.ArkUI");
    assert_eq!(candidate["affectedRepositoryCount"], 2);
    assert_eq!(candidate["affectedFiles"].as_array().unwrap().len(), 2);
    assert_eq!(candidate["evidenceIds"].as_array().unwrap().len(), 2);
    assert_eq!(candidate["verificationContract"]["caseReady"], false);
    assert_eq!(candidate["automaticPromotion"], false);
}

#[test]
fn non_utf8_source_is_audited_without_aborting_the_source_set() {
    let mut fixture = Fixture::new();
    let (one, _) = fixture.repository(
        "one",
        &[(
            "src/one.ts",
            "import broken from './non_utf8'; export const one = broken;",
        )],
    );
    fs::write(one.join("src/non_utf8.ets"), [0xff, 0xfe, b'A']).unwrap();
    git(&one, &["add", "."]);
    git(
        &one,
        &[
            "-c",
            "user.name=Multi repo test",
            "-c",
            "user.email=multi@example.invalid",
            "commit",
            "-qm",
            "add non utf8 source",
        ],
    );
    let revision_one = git_output(&one, &["rev-parse", "HEAD"]);
    let (two, revision_two) = fixture.repository("two", &[("src/two.ts", "export const two = 2;")]);
    let manifest = json!({
        "schema":"agentlab.multi_repo_manifest.v1",
        "repositories":[
            {"id":"one","repository":"fixture://one","root":one,"revision":revision_one},
            {"id":"two","repository":"fixture://two","root":two,"revision":revision_two}
        ]
    });
    let result = fixture.run(&manifest, "non-utf8");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let receipt: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(receipt["unsupportedSources"], 1);
    let unsupported = rows(
        &fixture
            .root
            .join("non-utf8-output/unsupported_sources.jsonl"),
    );
    assert_eq!(unsupported.len(), 1);
    assert_eq!(unsupported[0]["repositoryId"], "one");
    assert_eq!(unsupported[0]["path"], "src/non_utf8.ets");
    assert_eq!(unsupported[0]["reason"], "non-utf8-source");
    assert_eq!(unsupported[0]["invalidUtf8AtByte"], 0);
    let facts = rows(&fixture.root.join("non-utf8-output/workspace_facts.jsonl"));
    assert!(facts.iter().any(|row| {
        row["kind"] == "module-reference"
            && row["specifier"] == "./non_utf8"
            && row["resolution"] == "unresolved"
            && row["resolutionReason"] == "relative-target-unsupported-source"
    }));
}
