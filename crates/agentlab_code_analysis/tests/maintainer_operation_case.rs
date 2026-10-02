use agentlab_code_analysis::{
    digest,
    maintainer_operation_case::{prepare, shadow_request},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
};

const SCOPE: &str = "skill-scope-code-workshop-common-persistence-telemetry";
const SEMANTIC: &str = "agent-analysis-rdb-preference-telemetry-pipeline";
const OPERATION: &str =
    "operation-source-59ec37d6a455b3d674aa971f90316b5967297dace95ef17d3655860275be9956";
fn fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("examples/maintainer-knowledge-gate/first-four")
        .canonicalize()
        .unwrap()
}
fn copy_tree(source: &Path, dest: &Path) {
    fs::create_dir(dest).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&entry.path(), &dest.join(entry.file_name()));
        } else {
            fs::copy(entry.path(), dest.join(entry.file_name())).unwrap();
        }
    }
}
fn isolated() -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let dir = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "operation-case-{}-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    copy_tree(&fixture(), &dir);
    dir
}
fn recut(dir: &Path, key: &str, file: &str) {
    let path = dir.join("maintainer-knowledge-cut.json");
    let mut cut: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    cut["tables"][key]["sha256"] = json!(digest(&fs::read(dir.join(file)).unwrap()));
    fs::write(path, serde_json::to_vec(&cut).unwrap()).unwrap();
}
#[test]
fn admitted_operation_produces_repeatable_unqualified_construction_inputs() {
    let base = fixture();
    let first = prepare(&base, SCOPE, SEMANTIC, OPERATION).unwrap();
    assert_eq!(first, prepare(&base, SCOPE, SEMANTIC, OPERATION).unwrap());
    assert_eq!(first["status"], "construction-inputs-only");
    for flag in [
        "automaticPromotion",
        "authorityWritePerformed",
        "formalCaseQualified",
        "caseCalibrationInherited",
    ] {
        assert_eq!(first[flag], false);
    }
    assert_eq!(first["operationVerification"]["status"], "verified");
    assert_eq!(first["semanticFact"]["id"], SEMANTIC);
    assert!(first["nextRequirements"].as_array().unwrap().len() >= 6);
}

#[test]
fn constructor_translation_reverifies_bytes_and_preserves_operation_origin() {
    let base = fixture();
    let packet = prepare(&base, SCOPE, SEMANTIC, OPERATION).unwrap();
    let bytes = serde_json::to_vec(&packet).unwrap();
    let request = shadow_request(&base, &bytes, "harmony-emulator").unwrap();
    assert_eq!(request["operationInputsSha256"], digest(&bytes));
    assert!(request.get("loopReceiptSha256").is_none());
    assert_eq!(request["fact"], packet["semanticFact"]);
    assert_eq!(request["policy"]["caseCalibrationInherited"], false);
    assert_eq!(
        request,
        shadow_request(&base, &bytes, "harmony-emulator").unwrap()
    );
    assert!(shadow_request(&base, &bytes, "physical-device").is_err());
    let mut forged = packet.clone();
    forged["operationVerification"]["status"] = json!("unverified");
    assert!(shadow_request(
        &base,
        &serde_json::to_vec(&forged).unwrap(),
        "harmony-emulator"
    )
    .unwrap_err()
    .contains("differ"));
}
#[test]
fn staging_or_changed_table_is_not_admitted_knowledge() {
    let dir = isolated();
    let path = dir.join("maintainer-knowledge-cut.json");
    let original = fs::read(&path).unwrap();
    let mut cut: Value = serde_json::from_slice(&original).unwrap();
    cut["staging"] = json!({"reviewed":true});
    fs::write(&path, serde_json::to_vec(&cut).unwrap()).unwrap();
    assert!(prepare(&dir, SCOPE, SEMANTIC, OPERATION)
        .unwrap_err()
        .contains("committed"));
    fs::write(&path, original).unwrap();
    fs::write(dir.join("evaluation_cases.jsonl"), b"{}\n").unwrap();
    assert!(prepare(&dir, SCOPE, SEMANTIC, OPERATION)
        .unwrap_err()
        .contains("digest"));
}
#[test]
fn operation_cannot_replace_semantics_or_borrow_another_scope() {
    assert!(prepare(&fixture(), SCOPE, OPERATION, OPERATION)
        .unwrap_err()
        .contains("analysis"));
    assert!(prepare(
        &fixture(),
        "skill-scope-code-workshop-common-ui-state-contracts",
        SEMANTIC,
        OPERATION
    )
    .unwrap_err()
    .contains("binding"));
}
#[test]
fn duplicate_or_source_mismatched_facts_fail_even_after_rehash() {
    let dir = isolated();
    let path = dir.join("program_facts.jsonl");
    let original = fs::read_to_string(&path).unwrap();
    let row = original
        .lines()
        .find(|l| serde_json::from_str::<Value>(l).unwrap()["id"] == SEMANTIC)
        .unwrap();
    fs::write(&path, format!("{original}{row}\n")).unwrap();
    recut(&dir, "programFacts", "program_facts.jsonl");
    assert!(prepare(&dir, SCOPE, SEMANTIC, OPERATION)
        .unwrap_err()
        .contains("duplicate"));
    let changed = original
        .lines()
        .map(|l| {
            let mut row: Value = serde_json::from_str(l).unwrap();
            if row["id"] == SEMANTIC {
                row["sourceRevision"] = json!("0".repeat(40));
            }
            serde_json::to_string(&row).unwrap() + "\n"
        })
        .collect::<String>();
    fs::write(&path, changed).unwrap();
    recut(&dir, "programFacts", "program_facts.jsonl");
    assert!(prepare(&dir, SCOPE, SEMANTIC, OPERATION)
        .unwrap_err()
        .contains("binding"));
}
#[test]
fn missing_operation_capture_and_relative_roots_fail_closed() {
    let dir = isolated();
    let receipt = prepare(&dir, SCOPE, SEMANTIC, OPERATION).unwrap()["operationVerification"]
        ["receiptPath"]
        .as_str()
        .unwrap()
        .to_owned();
    fs::rename(
        dir.join("operation-evidence").join(&receipt),
        dir.join("retained-receipt.json"),
    )
    .unwrap();
    assert!(prepare(&dir, SCOPE, SEMANTIC, OPERATION).is_err());
    assert!(prepare(
        Path::new("examples/maintainer-knowledge-gate/first-four"),
        SCOPE,
        SEMANTIC,
        OPERATION
    )
    .unwrap_err()
    .contains("absolute"));
}
