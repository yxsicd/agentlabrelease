use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
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
        "agentlab-component-introduce-{}-{}-{}",
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

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn update(provides: Value) -> Value {
    json!({
        "schema": "agentlab.component_update.v1",
        "component": "pack:analysis-tools",
        "sourceRevision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "value": {
            "archiveSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "artifact": "./agentlab-pack-analysis-tools-aaaaaaaaaaaa-linux-x64.tar.zst",
            "descriptor": "./agentlab-pack-analysis-tools-aaaaaaaaaaaa-linux-x64.tar.zst.json",
            "enabled": true,
            "mountTarget": "/agentlab-analysis-tools",
            "packId": "analysis-tools",
            "platform": "linux-x64",
            "required": false,
            "slot": "analysis-tools",
            "version": "aaaaaaaaaaaa",
            "volume": "vol-agentlab-pack-analysis-tools-aaaaaaaaaaaa-linux-x64-bbbbbbbbbbbb"
        },
        "graphNode": {
            "binding": {"kind": "pack-slot", "slot": "analysis-tools"},
            "id": "component-analysis-tools",
            "platform": "linux-x64",
            "provides": provides,
            "requires": {},
            "upgradePolicy": "independent",
            "version": "aaaaaaaaaaaa"
        },
        "assets": [
            {
                "url": "./agentlab-pack-analysis-tools-aaaaaaaaaaaa-linux-x64.tar.zst",
                "bytes": 11,
                "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            },
            {
                "url": "./agentlab-pack-analysis-tools-aaaaaaaaaaaa-linux-x64.tar.zst.json",
                "bytes": 12,
                "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
            }
        ]
    })
}

fn write_update(root: &Path, value: &Value) -> PathBuf {
    let path = root.join("analysis-tools-update.json");
    fs::write(&path, serde_json::to_vec_pretty(value).unwrap()).unwrap();
    path
}

fn immutable_url() -> &'static str {
    "https://github.com/yxsicd/agentlabrelease/releases/download/analysis-tools-aaaaaaaaaaaa-linux-x64/analysis-tools-aaaaaaaaaaaa-linux-x64.json"
}

fn run(publication: &Path, lock: &Path, update: &Path, update_url: &str, output: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agentlab-component-introduce"))
        .args([
            "--base-publication",
            publication.to_str().unwrap(),
            "--base-lock",
            lock.to_str().unwrap(),
            "--component-update",
            update.to_str().unwrap(),
            "--component-update-url",
            update_url,
            "--tag",
            "candidate-analysis-tools-aaaaaaaaaaaa-linux-x64",
            "--output",
            output.to_str().unwrap(),
        ])
        .current_dir(repository())
        .output()
        .unwrap()
}

fn base_paths() -> (PathBuf, PathBuf) {
    let base = repository().join("release/channels/aldev");
    (
        base.join("publication.json"),
        base.join("environment-lock.json"),
    )
}

fn assert_existing_composition_validator_accepts(directory: &Path) {
    let script = r#"
import importlib.util, json, pathlib, sys
repository = pathlib.Path(sys.argv[1])
candidate = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('validator', repository / 'scripts/validate-composition-release.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
raw = (candidate / 'environment-lock.json').read_bytes()
validator.validate(json.loads((candidate / 'publication.json').read_bytes()), json.loads(raw), raw)
"#;
    let result = Command::new("python3")
        .args([
            "-c",
            script,
            repository().to_str().unwrap(),
            directory.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn introduces_optional_slot_without_rebuilding_or_changing_existing_components() {
    let root = temp_root();
    let update_path = write_update(&root, &update(json!({"agentlab.analysis-tools": 1})));
    let (base_publication_path, base_lock_path) = base_paths();
    let first = root.join("first");
    let second = root.join("second");
    for output in [&first, &second] {
        let result = run(
            &base_publication_path,
            &base_lock_path,
            &update_path,
            immutable_url(),
            output,
        );
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
    for name in [
        "environment-lock.json",
        "publication.json",
        "component-introduction.json",
    ] {
        assert_eq!(
            fs::read(first.join(name)).unwrap(),
            fs::read(second.join(name)).unwrap()
        );
    }
    assert_existing_composition_validator_accepts(&first);

    let base_publication = read(&base_publication_path);
    let base_lock = read(&base_lock_path);
    let publication = read(&first.join("publication.json"));
    let lock_bytes = fs::read(first.join("environment-lock.json")).unwrap();
    let lock: Value = serde_json::from_slice(&lock_bytes).unwrap();
    let receipt = read(&first.join("component-introduction.json"));
    let base_components = base_lock["components"].as_array().unwrap();
    let components = lock["components"].as_array().unwrap();
    assert_eq!(&components[..base_components.len()], base_components);
    assert_eq!(components.len(), base_components.len() + 1);
    assert_eq!(components.last().unwrap()["slot"], "analysis-tools");
    assert_eq!(components.last().unwrap()["required"], false);
    assert_eq!(lock["images"], base_lock["images"]);
    assert_eq!(lock["sourceRevision"], base_lock["sourceRevision"]);
    assert_eq!(
        lock["componentGraph"]["resolvedContracts"]["linux-x64"]["agentlab.analysis-tools"],
        1
    );
    assert_eq!(publication["environmentLockSha256"], digest(&lock_bytes));
    assert_eq!(
        publication["sourceRevision"],
        base_publication["sourceRevision"]
    );
    assert_eq!(publication["status"], "candidate");
    assert_eq!(publication["activated"], false);
    assert!(publication["gates"]
        .as_object()
        .unwrap()
        .values()
        .all(|value| value == "not_run"));
    let base_assets = base_publication["assets"].as_array().unwrap();
    let assets = publication["assets"].as_array().unwrap();
    assert_eq!(&assets[..base_assets.len()], base_assets);
    assert_eq!(assets.len(), base_assets.len() + 2);
    assert!(assets[base_assets.len()]["url"]
        .as_str()
        .unwrap()
        .starts_with("https://github.com/yxsicd/agentlabrelease/releases/download/analysis-tools-aaaaaaaaaaaa-linux-x64/"));
    assert_eq!(receipt["rebuildComponents"], false);
    assert_eq!(receipt["automaticPromotion"], false);
    assert_eq!(receipt["component"], "pack:analysis-tools");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_mutable_release_and_cleans_output() {
    let root = temp_root();
    let update_path = write_update(&root, &update(json!({"agentlab.analysis-tools": 1})));
    let (publication, lock) = base_paths();
    let output = root.join("output");
    let result = run(
        &publication,
        &lock,
        &update_path,
        "https://github.com/yxsicd/agentlabrelease/releases/download/aldev/update.json",
        &output,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("mutable channel tag"));
    assert!(!output.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_immutable_but_non_source_derived_release_identity() {
    let root = temp_root();
    let update_path = write_update(&root, &update(json!({"agentlab.analysis-tools": 1})));
    let (publication, lock) = base_paths();
    let output = root.join("output");
    let result = run(
        &publication,
        &lock,
        &update_path,
        "https://github.com/yxsicd/agentlabrelease/releases/download/unrelated-tag/update.json",
        &output,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("not source-derived"));
    assert!(!output.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_duplicate_slot_after_first_coordinated_introduction() {
    let root = temp_root();
    let update_path = write_update(&root, &update(json!({"agentlab.analysis-tools": 1})));
    let (base_publication, base_lock) = base_paths();
    let first = root.join("first");
    assert!(run(
        &base_publication,
        &base_lock,
        &update_path,
        immutable_url(),
        &first,
    )
    .status
    .success());
    let second = root.join("second");
    let result = run(
        &first.join("publication.json"),
        &first.join("environment-lock.json"),
        &update_path,
        immutable_url(),
        &second,
    );
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("component slot already exists; use independent upgrade"));
    assert!(!second.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn rejects_duplicate_contract_provider_without_partial_candidate() {
    let root = temp_root();
    let update_path = write_update(&root, &update(json!({"agentlab.runtime": 2})));
    let (publication, lock) = base_paths();
    let output = root.join("output");
    let result = run(&publication, &lock, &update_path, immutable_url(), &output);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr)
        .contains("duplicate contract provider: agentlab.runtime"));
    assert!(!output.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn publication_workflow_keeps_component_candidate_and_activation_as_separate_authorities() {
    let workflow =
        fs::read_to_string(repository().join(".github/workflows/analysis-tools-component.yml"))
            .unwrap();
    let component_upgrade =
        fs::read_to_string(repository().join(".github/workflows/component-upgrade.yml")).unwrap();
    let public_smoke =
        fs::read_to_string(repository().join("scripts/ci-public-install-deploy-smoke.sh")).unwrap();
    let analysis_workflow =
        fs::read_to_string(repository().join(".github/workflows/multi-repo-analysis.yml")).unwrap();
    let component_install_action = fs::read_to_string(
        repository().join(".github/actions/install-analysis-tools-component/action.yml"),
    )
    .unwrap();
    let semantic_review = fs::read_to_string(
        repository().join(".github/workflows/purchase-data-integrated-semantic-review.yml"),
    )
    .unwrap();
    let oracle_review = fs::read_to_string(
        repository().join(".github/workflows/purchase-data-integrated-oracle-review.yml"),
    )
    .unwrap();
    assert!(workflow.contains("publish_composition_candidate:"));
    assert!(workflow.contains("[[ \"$EXPECTED_REVISION\" == \"$GITHUB_SHA\" ]]"));
    assert!(workflow.contains("validator.remote_assets(assets)"));
    assert!(workflow.contains("assert set(published) == {path.name for path in local_files}"));
    assert!(workflow.contains("exact immutable component already exists"));
    assert!(workflow.contains("cmp \"$file\" \"$RUNNER_TEMP/coordinated-readback/"));
    assert!(workflow.contains("\"automaticPromotion\": False"));
    assert!(workflow.contains("receipt[\"candidateMetadataPublished\"] = True"));
    assert!(workflow
        .contains("gh release create \"$tag\" \"$RUNNER_TEMP/coordinated-candidate/\"*.json"));
    let component_publish = workflow
        .find("Publish once under a source-derived immutable tag")
        .unwrap();
    let remote_verification = workflow
        .find("Verify the published component and complete the reference-only candidate")
        .unwrap();
    let candidate_publish = workflow
        .find("Publish reference-only coordinated candidate metadata")
        .unwrap();
    assert!(component_publish < remote_verification && remote_verification < candidate_publish);
    assert!(component_upgrade.contains("pack:analysis-tools"));
    assert!(workflow.contains("--execute agentlab-analysis-tools-pack"));
    assert!(workflow.contains("Verify compatibility with the current public controller"));
    assert!(workflow.contains("pack inspect \"$archive\""));
    assert!(workflow.contains("pack verify \"$archive\""));
    assert!(workflow.contains("runtime-self-check.json"));
    assert!(workflow.contains("runtime-execution-receipt.json"));
    assert!(public_smoke.contains("agentlab.analysis_tools_installed_execution.v1"));
    assert!(public_smoke
        .contains("--entrypoint \"${analysis_mount}/payload/bin/agentlab-analysis-tools-pack\""));
    assert!(
        public_smoke.contains("\"${runtime_reference}\" --execute agentlab-analysis-tools-pack")
    );
    assert!(public_smoke.contains("analysis-tools-execution-receipt.json"));
    assert!(public_smoke.contains("\"status\":\"not-selected\""));
    assert!(analysis_workflow.contains("analysis_component_revision:"));
    assert!(analysis_workflow.contains("analysis_composition_lock_sha256:"));
    assert!(analysis_workflow.contains("uses: ./.github/actions/install-analysis-tools-component"));
    assert!(analysis_workflow.contains("--execute agentlab-multi-repo-analysis"));
    assert!(analysis_workflow.contains("analysis-tools-execution.json"));
    assert!(!analysis_workflow.contains(
        "cargo build --locked -p agentlab_code_analysis --bin agentlab-multi-repo-analysis"
    ));
    assert!(component_install_action.contains("AGENTLAB_SUBJECT_ONLY=true"));
    assert!(!component_install_action.contains("AGENTLAB_INSTALL_ONLY=true"));
    assert!(component_install_action.contains("componentPayloadsUploaded\"] is False"));
    assert!(component_install_action.contains("automaticPromotion\": False"));
    assert!(component_install_action.contains("docker\", \"image\", \"inspect"));
    assert!(component_install_action.contains("installed[\"componentSourceRevision\"] == revision"));
    assert!(analysis_workflow.contains("analysis-component-install-probe.json"));
    for review in [&semantic_review, &oracle_review] {
        assert!(review.contains("analysis_component_revision:"));
        assert!(review.contains("analysis_composition_lock_sha256:"));
        assert!(review.contains("uses: ./.github/actions/install-analysis-tools-component"));
        assert!(review.contains("--execute agentlab-purchase-data-integrated-review"));
        assert!(!review.contains(
            "cargo build --locked --release -p agentlab_code_analysis --bin agentlab-purchase-data-integrated-review"
        ));
    }
    assert!(semantic_review.contains("analysis-execution/semantic-decision.json"));
    assert!(semantic_review.contains("analysis-component-install-probe.json"));
    assert!(oracle_review.contains("analysis-execution/gate-validate.json"));
    assert!(oracle_review.contains("analysis-component-install-probe.json"));
}
