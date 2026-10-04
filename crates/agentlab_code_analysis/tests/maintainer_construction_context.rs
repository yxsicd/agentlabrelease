use agentlab_code_analysis::{
    digest,
    maintainer_construction_context::{
        acquire_objects, bind_candidate_paths, prepare, prepare_edit_boundary, prepare_object_plan,
        validate_context, validate_edit_boundary, validate_object_plan,
    },
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

struct Fixture {
    root: PathBuf,
    source: PathBuf,
    knowledge: PathBuf,
    revision: String,
}
static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

#[cfg(unix)]
#[test]
fn fresh_partial_clone_fetches_only_bound_missing_context_without_materializing_paths() {
    let f = Fixture::new();
    git(&f.source, &["config", "uploadpack.allowFilter", "true"]);
    git(
        &f.source,
        &["config", "uploadpack.allowAnySHA1InWant", "true"],
    );
    let origin = format!("file://{}", f.source.display());
    f.scopes(|rows| {
        for row in rows {
            row["repository"] = json!(origin);
        }
    });
    let cut_path = f.knowledge.join("maintainer-knowledge-cut.json");
    let mut cut: Value = serde_json::from_slice(&fs::read(&cut_path).unwrap()).unwrap();
    cut["repositories"][0]["repository"] = json!(origin);
    fs::write(&cut_path, serde_json::to_vec(&cut).unwrap()).unwrap();
    let source = f.root.join("partial");
    git(
        &f.root,
        &[
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            &origin,
            source.to_str().unwrap(),
        ],
    );
    git(
        &source,
        &["sparse-checkout", "set", "--no-cone", "/pkg/main.rs"],
    );
    git(&source, &["checkout", "--detach", &f.revision]);
    let plan =
        prepare_object_plan(&f.knowledge, &source, "arbitrary", &["build.cfg".into()]).unwrap();
    assert!(prepare(&f.knowledge, &source, "arbitrary", &["build.cfg".into()]).is_err());
    assert!(!source.join("build.cfg").exists());
    // A single failed remote fetch retains evidence and no consumable packet.
    let parked = f.root.join("parked-origin");
    fs::rename(&f.source, &parked).unwrap();
    let failed = f.root.join("failed-acquisition");
    let result = acquire_objects(
        &f.knowledge,
        &source,
        &serde_json::to_vec(&plan).unwrap(),
        Path::new("/usr/bin/git"),
        &failed,
    );
    fs::rename(&parked, &f.source).unwrap();
    assert!(result.is_err());
    let receipt: Value =
        serde_json::from_slice(&fs::read(failed.join("acquisition.json")).unwrap()).unwrap();
    assert_eq!(receipt["maximumFetchAttempts"], 1);
    assert_eq!(receipt["process"]["status"], "failed");
    assert!(!failed.join("context.json").exists());
    assert!(failed.join("fetch.stderr").is_file());
    let out = f.root.join("partial-acquisition");
    let receipt = acquire_objects(
        &f.knowledge,
        &source,
        &serde_json::to_vec(&plan).unwrap(),
        Path::new("/usr/bin/git"),
        &out,
    )
    .unwrap();
    assert_eq!(receipt["networkRequested"], true);
    assert_eq!(receipt["process"]["exitCode"], 0);
    assert_eq!(
        receipt["missingBlobOids"],
        json!([plan["selectedFiles"][0]["gitBlobOid"]])
    );
    assert_eq!(receipt["offlineContextReconstructed"], true);
    assert!(!source.join("build.cfg").exists());
    assert!(git(&source, &["status", "--porcelain"]).is_empty());
    assert_eq!(git(&source, &["rev-parse", "HEAD"]), f.revision);
    assert!(validate_context(
        &f.knowledge,
        &source,
        &fs::read(out.join("context.json")).unwrap()
    )
    .is_ok());
}

#[cfg(unix)]
#[test]
fn acquisition_reuses_local_objects_and_retains_offline_budget_failure() {
    let f = Fixture::new();
    let plan =
        prepare_object_plan(&f.knowledge, &f.source, "arbitrary", &["build.cfg".into()]).unwrap();
    let bytes = serde_json::to_vec(&plan).unwrap();
    let out = f.root.join("acquired");
    let receipt = acquire_objects(
        &f.knowledge,
        &f.source,
        &bytes,
        Path::new("/usr/bin/git"),
        &out,
    )
    .unwrap();
    assert_eq!(receipt["networkRequested"], false);
    assert_eq!(receipt["offlineContextReconstructed"], true);
    let packet = fs::read(out.join("context.json")).unwrap();
    assert!(validate_context(&f.knowledge, &f.source, &packet).is_ok());
    assert!(acquire_objects(
        &f.knowledge,
        &f.source,
        &bytes,
        Path::new("/usr/bin/git"),
        &out
    )
    .is_err());
    assert_eq!(fs::read(out.join("context.json")).unwrap(), packet);
    let mut forged = plan.clone();
    forged["selectedFiles"][0]["gitBlobOid"] = json!("a".repeat(40));
    let rejected = f.root.join("forged-acquisition");
    assert!(acquire_objects(
        &f.knowledge,
        &f.source,
        &serde_json::to_vec(&forged).unwrap(),
        Path::new("/usr/bin/git"),
        &rejected
    )
    .is_err());
    assert!(!rejected.exists());
    let large =
        prepare_object_plan(&f.knowledge, &f.source, "arbitrary", &["large.cfg".into()]).unwrap();
    let rejected = f.root.join("budget-acquisition");
    assert!(acquire_objects(
        &f.knowledge,
        &f.source,
        &serde_json::to_vec(&large).unwrap(),
        Path::new("/usr/bin/git"),
        &rejected
    )
    .is_err());
    let receipt: Value =
        serde_json::from_slice(&fs::read(rejected.join("acquisition.json")).unwrap()).unwrap();
    assert_eq!(receipt["offlineContextReconstructed"], false);
    assert_eq!(receipt["networkRequested"], false);
    assert!(!rejected.join("context.json").exists());
    assert!(git(&f.source, &["status", "--porcelain"]).is_empty());
}

#[test]
fn object_plan_binds_tree_without_content_and_rejects_forged_authority() {
    let f = Fixture::new();
    let paths = vec!["build.cfg".to_owned()];
    let plan = prepare_object_plan(&f.knowledge, &f.source, "arbitrary", &paths).unwrap();
    let bytes = serde_json::to_vec(&plan).unwrap();
    let validate = |bytes: &[u8]| validate_object_plan(&f.knowledge, &f.source, bytes);
    assert_eq!(validate(&bytes).unwrap()["contentVerified"], false);
    assert!(validate_context(&f.knowledge, &f.source, &bytes).is_err());
    for field in ["gitBlobOid", "ownerScopeSkillId", "access"] {
        let mut forged = plan.clone();
        forged["selectedFiles"][0][field] = json!("forged");
        assert!(
            validate(&serde_json::to_vec(&forged).unwrap()).is_err(),
            "{field}"
        );
    }
    let mut forged = plan.clone();
    forged["contentVerified"] = json!(true);
    assert!(validate(&serde_json::to_vec(&forged).unwrap()).is_err());
    assert!(prepare_object_plan(
        &f.knowledge,
        &f.source,
        "arbitrary",
        &["pkg/link.rs".into()]
    )
    .is_err());
    // Simulate unavailable content without deleting evidence. Tree identity stays
    // available, while the ordinary consumer must still refuse missing bytes.
    let oid = plan["selectedFiles"][0]["gitBlobOid"].as_str().unwrap();
    let object = f
        .source
        .join(".git/objects")
        .join(&oid[..2])
        .join(&oid[2..]);
    let retained = f.root.join("retained-blob");
    fs::rename(&object, &retained).unwrap();
    assert!(prepare(&f.knowledge, &f.source, "arbitrary", &paths).is_err());
    assert_eq!(
        prepare_object_plan(&f.knowledge, &f.source, "arbitrary", &paths).unwrap(),
        plan
    );
    assert!(validate(&bytes).is_ok());
    fs::rename(retained, object).unwrap();
    assert!(prepare(&f.knowledge, &f.source, "arbitrary", &paths).is_ok());
    f.scopes(|scopes| scopes[0]["sourceRevision"] = json!("a".repeat(40)));
    assert!(validate(&bytes).is_err());
}
fn edit_selection() -> Value {
    json!({"schema":"agentlab.case_edit_selection.v1","edits":[
        {"path":"pkg/main.rs","anchorPath":"pkg/main.rs","mode":"modify","ownerScopeSkillId":"implementation","reason":"implement the behavior contract"},
        {"path":"pkg/tests/new.rs","anchorPath":"pkg/tests/check.rs","mode":"create","ownerScopeSkillId":"verification","reason":"add independent behavioral checks"}
    ]})
}

#[test]
fn candidate_construction_binding_preserves_absence_and_rejects_borrowed_inputs() {
    let f = Fixture::new();
    let packet = prepare_edit_boundary(
        &f.knowledge,
        &f.source,
        "arbitrary",
        &serde_json::to_vec(&edit_selection()).unwrap(),
    )
    .unwrap();
    let bytes = serde_json::to_vec(&packet).unwrap();
    let candidate = json!({"schema":"agentlab.shadow_case_candidate.v1",
        "id":"candidate","status":"shadow-proposal","automaticPromotion":false,
        "repositoryId":"arbitrary","sourceRevision":f.revision,
        "knowledgeCutSha256":packet["knowledgeCutSha256"],
        "lineage":{"editBoundarySha256":digest(&bytes)},
        "scopeSkillIds":["implementation","verification"],
        "editablePaths":["pkg/main.rs","pkg/tests/new.rs"]});
    let bind = |c: &Value| {
        bind_candidate_paths(
            &f.knowledge,
            &f.source,
            &bytes,
            &serde_json::to_vec(c).unwrap(),
        )
    };
    let result = bind(&candidate).unwrap();
    assert_eq!(result, bind(&candidate).unwrap());
    assert_eq!(result["paths"][0]["targetSourceExists"], true);
    assert_eq!(result["paths"][1]["targetSourceExists"], false);
    assert_eq!(
        result["paths"][1]["precondition"]["kind"],
        "absent-at-source-revision"
    );
    for field in [
        "qualified",
        "automaticPromotion",
        "authorityWritePerformed",
        "grantsEditablePaths",
        "calibrationInherited",
    ] {
        assert_eq!(result[field], false);
    }
    for scenario in [
        "source",
        "knowledge",
        "packet",
        "owner",
        "unselected",
        "duplicate",
    ] {
        let mut forged = candidate.clone();
        match scenario {
            "source" => forged["sourceRevision"] = json!("a".repeat(40)),
            "knowledge" => forged["knowledgeCutSha256"] = json!("b".repeat(64)),
            "packet" => forged["lineage"]["editBoundarySha256"] = json!("c".repeat(64)),
            "owner" => forged["scopeSkillIds"] = json!(["implementation"]),
            "unselected" => forged["editablePaths"] = json!(["pkg/tests/extra.rs"]),
            "duplicate" => forged["editablePaths"] = json!(["pkg/main.rs", "pkg/main.rs"]),
            _ => unreachable!(),
        }
        assert!(bind(&forged).is_err(), "{scenario}");
    }
    assert!(!f.source.join("pkg/tests/new.rs").exists());
    assert!(git(&f.source, &["status", "--porcelain"]).is_empty());
    let packet_path = f.root.join("edit-packet.json");
    let candidate_path = f.root.join("candidate.json");
    let output_path = f.root.join("path-binding.json");
    fs::write(&packet_path, &bytes).unwrap();
    fs::write(&candidate_path, serde_json::to_vec(&candidate).unwrap()).unwrap();
    let command = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--bind-construction-paths")
            .arg("--knowledge")
            .arg(&f.knowledge)
            .arg("--source-worktree")
            .arg(&f.source)
            .arg("--edit-boundary")
            .arg(&packet_path)
            .arg("--candidate")
            .arg(&candidate_path)
            .arg("--output")
            .arg(&output_path)
            .output()
            .unwrap()
    };
    let run = command();
    assert!(
        run.status.success(),
        "{}",
        String::from_utf8_lossy(&run.stderr)
    );
    let retained = fs::read(&output_path).unwrap();
    assert_eq!(serde_json::from_slice::<Value>(&retained).unwrap(), result);
    assert!(!command().status.success());
    assert_eq!(fs::read(&output_path).unwrap(), retained);
    fs::write(f.source.join("pkg/tests/new.rs"), "obstructed").unwrap();
    assert!(bind(&candidate).is_err());
}

#[test]
fn construction_edits_bind_exact_existing_and_new_paths_without_implicit_grants() {
    let f = Fixture::new();
    let selection = edit_selection();
    let bytes = serde_json::to_vec(&selection).unwrap();
    let packet = prepare_edit_boundary(&f.knowledge, &f.source, "arbitrary", &bytes).unwrap();
    assert_eq!(packet["selectionSha256"], digest(&bytes));
    assert_eq!(
        packet["selectionUtf8"],
        std::str::from_utf8(&bytes).unwrap()
    );
    assert_eq!(
        packet["edits"][0]["precondition"]["gitBlobOid"],
        git(&f.source, &["rev-parse", "HEAD:pkg/main.rs"])
    );
    assert_eq!(
        packet["edits"][1]["precondition"]["kind"],
        "absent-at-source-revision"
    );
    assert_eq!(packet["grantsEditablePaths"], false);
    assert_eq!(packet["calibrationInherited"], false);
    assert_eq!(
        packet,
        prepare_edit_boundary(&f.knowledge, &f.source, "arbitrary", &bytes).unwrap()
    );
    assert!(!f.source.join("pkg/tests/new.rs").exists());
    assert!(git(&f.source, &["status", "--porcelain"]).is_empty());
    let packet_bytes = serde_json::to_vec(&packet).unwrap();
    let validation = validate_edit_boundary(&f.knowledge, &f.source, &packet_bytes).unwrap();
    assert_eq!(validation["packetSha256"], digest(&packet_bytes));
    for field in [
        "knowledgeCutSha256",
        "selectionSha256",
        "grantsEditablePaths",
    ] {
        let mut forged = packet.clone();
        forged[field] = json!("forged");
        assert!(validate_edit_boundary(
            &f.knowledge,
            &f.source,
            &serde_json::to_vec(&forged).unwrap()
        )
        .is_err());
    }
    let mut widened = packet.clone();
    widened["edits"][1]["path"] = json!("pkg/tests/extra.rs");
    assert!(validate_edit_boundary(
        &f.knowledge,
        &f.source,
        &serde_json::to_vec(&widened).unwrap()
    )
    .is_err());
}

#[test]
fn edit_selection_rejects_borrowed_owners_exact_file_widening_and_obstructions() {
    for scenario in [
        "owner",
        "anchor-owner",
        "exact-widening",
        "duplicate",
        "traversal",
        "drive-path",
        "already-tracked",
        "modify-anchor",
        "mode",
        "ignored-target",
        "symlink-parent",
        "overlap",
        "stale",
        "foreign-repo",
    ] {
        let f = Fixture::new();
        let mut selection = edit_selection();
        match scenario {
            "owner" => selection["edits"][1]["ownerScopeSkillId"] = json!("implementation"),
            "anchor-owner" => selection["edits"][1]["anchorPath"] = json!("pkg/main.rs"),
            "exact-widening" => selection["edits"][1]["path"] = json!("pkg/new.rs"),
            "duplicate" => {
                let copy = selection["edits"][0].clone();
                selection["edits"].as_array_mut().unwrap().push(copy);
            }
            "traversal" => selection["edits"][1]["path"] = json!("pkg/tests/../new.rs"),
            "drive-path" => selection["edits"][1]["path"] = json!("C:/new.rs"),
            "already-tracked" => selection["edits"][1]["path"] = json!("pkg/tests/check.rs"),
            "modify-anchor" => selection["edits"][0]["anchorPath"] = json!("pkg/tests/check.rs"),
            "mode" => selection["edits"][1]["mode"] = json!("delete"),
            "ignored-target" => {
                git(&f.source, &["config", "core.excludesfile", "/dev/null"]);
                fs::write(f.source.join(".git/info/exclude"), "pkg/tests/new.rs\n").unwrap();
                fs::write(f.source.join("pkg/tests/new.rs"), "existing ignored data").unwrap();
            }
            "symlink-parent" => {
                #[cfg(unix)]
                {
                    fs::write(f.source.join(".git/info/exclude"), "pkg/tests/link\n").unwrap();
                    std::os::unix::fs::symlink("..", f.source.join("pkg/tests/link")).unwrap();
                    selection["edits"][1]["path"] = json!("pkg/tests/link/new.rs");
                }
                #[cfg(not(unix))]
                {
                    continue;
                }
            }
            "overlap" => f.scopes(|s| {
                let mut copy = s[2].clone();
                copy["id"] = json!("other");
                s.push(copy);
            }),
            "stale" => f.scopes(|s| s[2]["sourceRevision"] = json!("a".repeat(40))),
            "foreign-repo" => {
                selection["edits"][1]["ownerScopeSkillId"] = json!("unrelated-repo-owner")
            }
            _ => unreachable!(),
        }
        assert!(
            prepare_edit_boundary(
                &f.knowledge,
                &f.source,
                "arbitrary",
                &serde_json::to_vec(&selection).unwrap()
            )
            .is_err(),
            "{scenario}"
        );
        assert!(!f.source.join("pkg/tests/new.rs").exists() || scenario == "ignored-target");
    }
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
            "agentlab-context-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
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
fn readonly_context_consumer_reconstructs_all_claims_and_rejects_drift() {
    let f = Fixture::new();
    let packet = prepare(
        &f.knowledge,
        &f.source,
        "arbitrary",
        &["pkg/main.rs".into()],
    )
    .unwrap();
    let bytes = serde_json::to_vec_pretty(&packet).unwrap();
    let receipt = validate_context(&f.knowledge, &f.source, &bytes).unwrap();
    assert_eq!(receipt["packetSha256"], digest(&bytes));
    assert_eq!(receipt["sourceGitBindingVerified"], true);
    assert_eq!(receipt["knowledgeBindingVerified"], true);
    assert_eq!(receipt["grantsEditablePaths"], false);
    assert_eq!(receipt["executionPerformed"], false);
    for (pointer, value) in [
        ("/selectedFiles/0/contentUtf8", json!("invented")),
        ("/selectedFiles/0/sha256", json!("b".repeat(64))),
        ("/selectedFiles/0/ownerScopeSkillId", json!("root")),
        ("/selectedFiles/0/access", json!("editable")),
        ("/grantsEditablePaths", json!(true)),
        ("/knowledgeCutSha256", json!("b".repeat(64))),
        ("/tableGitRevision", json!("b".repeat(40))),
        ("/ownerKnowledge/0/scopeSkill/pathBoundary", json!(".")),
    ] {
        let mut changed = packet.clone();
        *changed.pointer_mut(pointer).unwrap() = value;
        assert!(
            validate_context(
                &f.knowledge,
                &f.source,
                &serde_json::to_vec(&changed).unwrap()
            )
            .is_err(),
            "{pointer}"
        );
    }
    let mut extra = packet.clone();
    extra["implicitImportsAllowed"] = json!(true);
    assert!(validate_context(
        &f.knowledge,
        &f.source,
        &serde_json::to_vec(&extra).unwrap()
    )
    .is_err());
    fs::write(f.source.join("pkg/main.rs"), "pub fn value() -> u8 { 2 }\n").unwrap();
    assert!(validate_context(&f.knowledge, &f.source, &bytes).is_err());
}

#[test]
fn context_validation_cli_binds_stdout_and_preserves_receipts_on_repeat() {
    let f = Fixture::new();
    let packet = prepare(&f.knowledge, &f.source, "arbitrary", &["build.cfg".into()]).unwrap();
    let input = f.root.join("context.json");
    let output = f.root.join("validation.json");
    fs::write(&input, serde_json::to_vec_pretty(&packet).unwrap()).unwrap();
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--validate-construction-context")
            .arg("--knowledge")
            .arg(&f.knowledge)
            .arg("--source-worktree")
            .arg(&f.source)
            .arg("--context-packet")
            .arg(&input)
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap()
    };
    let result = run();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let bytes = fs::read(&output).unwrap();
    assert_eq!(
        serde_json::from_slice::<Value>(&result.stdout).unwrap(),
        serde_json::from_slice::<Value>(&bytes).unwrap()
    );
    assert!(!run().status.success());
    assert_eq!(bytes, fs::read(&output).unwrap());
    // A previously valid packet cannot be reused after a knowledge projection changes.
    f.scopes(|scopes| scopes[0]["maintenanceContract"] = json!("changed owner guidance"));
    assert!(validate_context(&f.knowledge, &f.source, &fs::read(&input).unwrap()).is_err());
    assert_eq!(bytes, fs::read(output).unwrap());
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

#[test]
fn existing_owner_knowledge_is_carried_without_requalification_or_stale_borrowing() {
    let f = Fixture::new();
    let oid = git(&f.source, &["rev-parse", "HEAD:pkg/main.rs"]);
    let valid = json!({"id":"known-analysis","kind":"analysis","repositoryId":"arbitrary",
        "sourceRevision":f.revision,"scopeSkillIds":["implementation"],
        "evidence":[{"path":"pkg/main.rs","gitBlobOid":oid}],
        "interpretation":"Existing maintenance contract, not a new experiment.",
        "limitations":["No independent runtime execution has been performed."]});
    let mut stale = valid.clone();
    stale["id"] = json!("stale-analysis");
    stale["sourceRevision"] = json!("a".repeat(40));
    let mut wrong_blob = valid.clone();
    wrong_blob["id"] = json!("wrong-blob");
    wrong_blob["evidence"][0]["gitBlobOid"] = json!("b".repeat(40));
    let mut partial = valid.clone();
    partial["id"] = json!("partial-analysis");
    partial["evidence"].as_array_mut().unwrap().push(json!({"path":"pkg/tests/check.rs","gitBlobOid":git(&f.source,&["rev-parse","HEAD:pkg/tests/check.rs"])}));
    let rows = [valid.clone(), stale, wrong_blob, partial];
    let bytes = rows
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    fs::write(f.knowledge.join("program_facts.jsonl"), &bytes).unwrap();
    let cut_path = f.knowledge.join("maintainer-knowledge-cut.json");
    let mut cut: Value = serde_json::from_slice(&fs::read(&cut_path).unwrap()).unwrap();
    cut["tables"]["programFacts"]["sha256"] = json!(digest(bytes.as_bytes()));
    fs::write(cut_path, serde_json::to_vec(&cut).unwrap()).unwrap();
    let packet = prepare(
        &f.knowledge,
        &f.source,
        "arbitrary",
        &["pkg/main.rs".into()],
    )
    .unwrap();
    assert_eq!(
        packet["schema"],
        "agentlab.case_construction_context_packet.v2"
    );
    let knowledge = &packet["ownerKnowledge"][0];
    assert_eq!(knowledge["scopeSkill"]["id"], "implementation");
    let facts = knowledge["analysisFacts"].as_array().unwrap();
    assert_eq!(facts.len(), 2);
    assert_eq!(facts[0]["fact"], valid);
    assert_eq!(
        facts[0]["factValueSha256"],
        digest(&serde_json::to_vec(&valid).unwrap())
    );
    assert_eq!(facts[0]["allFactEvidenceLoaded"], true);
    assert_eq!(facts[0]["semanticRequalified"], false);
    assert_eq!(
        facts[1]["unloadedEvidencePaths"],
        json!(["pkg/tests/check.rs"])
    );
    assert_eq!(facts[1]["allFactEvidenceLoaded"], false);
    assert_eq!(
        knowledge["excludedAnalysisFacts"].as_array().unwrap().len(),
        2
    );
    assert_eq!(packet["authorityWritePerformed"], false);
}
