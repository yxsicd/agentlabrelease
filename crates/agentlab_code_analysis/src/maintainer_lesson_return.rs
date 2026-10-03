//! Committed reviewed-lesson return, after ordinary admission reconstruction.
//! No remote writes or producer authentication; retained readbacks are compared
//! to the complete reconstructed stage, never trusted as status-only receipts.
use crate::digest;
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::Path};

const TABLES: [(&str, &str); 5] = [
    ("maintainerSkills", "maintainer_skills"),
    ("maintainerScopeSkills", "maintainer_scope_skills"),
    ("programFacts", "program_facts"),
    (
        "maintainerSkillRefreshRounds",
        "maintainer_skill_refresh_rounds",
    ),
    ("evaluationCases", "evaluation_cases"),
];
fn need(ok: bool, error: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(error.into())
    }
}
fn read(root: &Path, relative: &str) -> Result<Vec<u8>, String> {
    let path = root.join(relative);
    for ancestor in path.ancestors() {
        need(
            !fs::symlink_metadata(ancestor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "lesson return input symlink",
        )?;
    }
    let meta = fs::metadata(&path).map_err(|e| e.to_string())?;
    need(
        meta.is_file() && meta.len() <= 32 * 1024 * 1024,
        "lesson return file budget",
    )?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    need(
        bytes.len() <= 32 * 1024 * 1024,
        "lesson return file grew beyond budget",
    )?;
    Ok(bytes)
}
fn load(root: &Path, relative: &str) -> Result<Value, String> {
    serde_json::from_slice(&read(root, relative)?).map_err(|e| e.to_string())
}
fn rows(bytes: &[u8]) -> Result<BTreeMap<String, Value>, String> {
    let mut result = BTreeMap::new();
    for line in bytes
        .split(|b| *b == b'\n')
        .filter(|l| !l.iter().all(u8::is_ascii_whitespace))
    {
        let row: Value = serde_json::from_slice(line).map_err(|e| e.to_string())?;
        let id = row["id"]
            .as_str()
            .filter(|id| !id.trim().is_empty())
            .ok_or("lesson return row id absent")?
            .to_owned();
        need(
            result.insert(id, row).is_none(),
            "lesson return duplicate row",
        )?;
    }
    Ok(result)
}
fn oid(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        s.len() == 40
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}
fn remote(
    table: &Value,
    revision: &Value,
    wrapped: bool,
) -> Result<BTreeMap<String, Value>, String> {
    let items = table["rows"]
        .as_array()
        .filter(|r| r.len() <= 1000)
        .ok_or("lesson return remote rows absent or over budget")?;
    need(
        table["revision"] == *revision
            && table["dirty"] == false
            && table["truncated"] == false
            && table["row_count"] == items.len()
            && table["returned_count"] == items.len(),
        "lesson return remote snapshot incomplete or dirty",
    )?;
    let mut result = BTreeMap::new();
    for item in items {
        need(item["deleted"] != true, "lesson return deleted row")?;
        let row = if wrapped {
            &item["row"]["payload"]
        } else {
            &item["row"]
        };
        let id = item["key"]
            .as_str()
            .ok_or("lesson return remote key absent")?;
        need(
            row["id"] == id && result.insert(id.to_owned(), row.clone()).is_none(),
            "lesson return remote key conflict",
        )?;
    }
    Ok(result)
}

/// Caller must first reconstruct `stage` through maintainer_lesson_admission::stage.
/// This gate connects that reviewed result to captured committed authority and
/// preserves original assessed bytes and portable evidence in the next cut.
pub(crate) fn verify(
    stage: &Path,
    source: &Path,
    next: &Path,
    capture: &[u8],
) -> Result<Value, String> {
    need(
        capture.len() <= 32 * 1024 * 1024,
        "lesson return capture budget",
    )?;
    let evidence: Value = serde_json::from_slice(capture).map_err(|e| e.to_string())?;
    let staged_cut = load(stage, "maintainer-knowledge-cut.json")?;
    let next_bytes = read(next, "maintainer-knowledge-cut.json")?;
    let next_cut: Value = serde_json::from_slice(&next_bytes).map_err(|e| e.to_string())?;
    let repo = &staged_cut["tableGitAuthority"]["repo"];
    let before = &staged_cut["tableGitAuthority"]["revision"];
    let revision = &next_cut["tableGitAuthority"]["revision"];
    need(
        evidence["schema"] == "agentlab.reviewed_lesson_committed_readback.v1"
            && evidence["knowledgeRepository"] == *repo
            && evidence["previousRevision"] == *before
            && evidence["revision"] == *revision
            && oid(before)
            && oid(revision)
            && revision != before,
        "lesson return authority identity differs or unchanged",
    )?;
    need(
        next_cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && next_cut["automaticPromotion"] == false
            && next_cut["tableGitAuthority"]["repo"] == *repo
            && next_cut.get("staging").is_none(),
        "lesson return is not a committed knowledge cut",
    )?;
    // A live status bracket binds the fixed readbacks. Historical commit receipts
    // are retained separately; neither is authenticated by this byte-level gate.
    for name in ["before", "after"] {
        need(
            evidence[name]["revision"] == *revision && evidence[name]["dirty"] == false,
            "lesson return live authority bracket drifted",
        )?;
    }
    let mut expected_cut = staged_cut.clone();
    expected_cut
        .as_object_mut()
        .ok_or("lesson return stage cut invalid")?
        .remove("staging");
    expected_cut["tableGitAuthority"] = next_cut["tableGitAuthority"].clone();
    need(
        expected_cut == next_cut,
        "lesson return changed source or cut policy",
    )?;
    let tables = evidence["tables"]
        .as_object()
        .ok_or("lesson return table set absent")?;
    need(
        tables.len() == TABLES.len(),
        "lesson return table set differs",
    )?;
    let mut counts = BTreeMap::new();
    for (key, table) in TABLES {
        let filename = format!("{table}.jsonl");
        let bytes = read(stage, &filename)?;
        need(
            next_cut["tables"][key] == json!({"path":filename,"sha256":digest(&bytes)})
                && read(next, &filename)? == bytes,
            "lesson return assessed table bytes changed",
        )?;
        let expected = rows(&bytes)?;
        need(
            remote(&tables[table], revision, true)? == expected,
            "lesson return committed knowledge rows differ",
        )?;
        counts.insert(table, expected.len());
    }
    // Copying just JSONLs cannot qualify a usable next knowledge cut. Keep the
    // assessment, source inventory and every inherited operation receipt exact.
    let manifest = load(stage, "stage-manifest.json")?;
    let assessment = manifest["assessment"]
        .as_str()
        .ok_or("lesson return assessment absent")?;
    need(
        read(next, assessment)? == read(stage, assessment)?,
        "lesson return assessment bytes changed",
    )?;
    need(
        read(next, "source-set.txt")? == read(stage, "source-set.txt")?,
        "lesson return source inventory changed",
    )?;
    for item in manifest["operationEvidence"]["inheritedReceipts"]
        .as_array()
        .ok_or("lesson return inherited receipts absent")?
    {
        let path = item["path"]
            .as_str()
            .ok_or("lesson return receipt path absent")?;
        need(
            read(next, path)? == read(stage, path)?,
            "lesson return inherited evidence changed",
        )?;
    }
    let export = load(source, "export.json")?;
    let source_evidence = &evidence["lessonSource"];
    need(
        source_evidence["repository"] == export["repository"]
            && source_evidence["revision"] == export["revision"]
            && source_evidence["tablePrefix"] == export["tablePrefix"]
            && oid(&export["revision"]),
        "lesson return operational source identity differs",
    )?;
    let source_tables = export["tables"]
        .as_object()
        .ok_or("lesson return source manifest absent")?;
    need(
        source_evidence["tables"]
            .as_object()
            .is_some_and(|t| t.len() == source_tables.len()),
        "lesson return source table set differs",
    )?;
    for name in source_tables.keys() {
        need(
            remote(&source_evidence["tables"][name], &export["revision"], false)?
                == rows(&read(source, &format!("{name}.jsonl"))?)?,
            "lesson return committed lesson rows differ",
        )?;
    }
    Ok(
        json!({"schema":"agentlab.reviewed_lesson_return_verification.v1","committedReadbackVerified":true,
        "knowledgeRepository":repo,"previousRevision":before,"revision":revision,
        "knowledgeCutSha256":digest(&next_bytes),"readbackSha256":digest(capture),"tables":counts,
        "sourceReadbackVerified":true,"authorityWritePerformed":false,"remoteCaptureAuthenticated":false,
        "formalCaseQualified":false,"guidanceConsumed":false,"learningBenefitVerified":false,"qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn save(root: &Path, name: &str, value: &Value) {
        fs::write(root.join(name), serde_json::to_vec(value).unwrap()).unwrap();
    }
    fn fixture() -> (std::path::PathBuf, Value) {
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "lesson-return-{}-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        for name in ["stage", "source", "next"] {
            fs::create_dir(root.join(name)).unwrap();
        }
        let before = "a".repeat(40);
        let revision = "b".repeat(40);
        let mut cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1","automaticPromotion":false,
            "tableGitAuthority":{"repo":"arbitrary-knowledge","revision":before},"tables":{},
            "staging":{"mode":"reviewed-lesson-admission"}});
        let mut readback = json!({"schema":"agentlab.reviewed_lesson_committed_readback.v1",
            "knowledgeRepository":"arbitrary-knowledge","previousRevision":before,"revision":revision,
            "before":{"revision":revision,"dirty":false},"after":{"revision":revision,"dirty":false},
            "tables":{},"lessonSource":{"repository":"arbitrary-operations","revision":before,"tablePrefix":"data/","tables":{}}});
        for (key, table) in TABLES {
            let row = json!({"id":table,"nested":{"unchanged":true}});
            let bytes = serde_json::to_vec(&row).unwrap();
            let filename = format!("{table}.jsonl");
            fs::write(root.join("stage").join(&filename), &bytes).unwrap();
            fs::write(root.join("next").join(&filename), &bytes).unwrap();
            cut["tables"][key] = json!({"path":filename,"sha256":digest(&bytes)});
            readback["tables"][table] = json!({"revision":revision,"dirty":false,"truncated":false,
                "row_count":1,"returned_count":1,"rows":[{"key":table,"row":{"payload":row}}]});
        }
        save(&root.join("stage"), "maintainer-knowledge-cut.json", &cut);
        cut.as_object_mut().unwrap().remove("staging");
        cut["tableGitAuthority"]["revision"] = json!(revision);
        save(&root.join("next"), "maintainer-knowledge-cut.json", &cut);
        save(
            &root.join("stage"),
            "stage-manifest.json",
            &json!({"assessment":"assessment.json","operationEvidence":{"inheritedReceipts":[{"path":"receipt.json"}]}}),
        );
        for name in ["source-set.txt", "assessment.json", "receipt.json"] {
            fs::write(root.join("stage").join(name), b"exact retained bytes").unwrap();
            fs::write(root.join("next").join(name), b"exact retained bytes").unwrap();
        }
        save(
            &root.join("source"),
            "export.json",
            &json!({"repository":"arbitrary-operations","revision":before,"tablePrefix":"data/","tables":{"experiment_lessons":{}}}),
        );
        let row = json!({"id":"lesson","status":"verified"});
        save(&root.join("source"), "experiment_lessons.jsonl", &row);
        readback["lessonSource"]["tables"]["experiment_lessons"] = json!({"revision":before,"dirty":false,
            "truncated":false,"row_count":1,"returned_count":1,"rows":[{"key":"lesson","row":row}]});
        (root, readback)
    }
    #[test]
    fn committed_rows_and_portable_bytes_are_verified_without_qualification() {
        let (root, evidence) = fixture();
        let result = verify(
            &root.join("stage"),
            &root.join("source"),
            &root.join("next"),
            &serde_json::to_vec(&evidence).unwrap(),
        )
        .unwrap();
        assert_eq!(result["committedReadbackVerified"], true);
        for key in [
            "authorityWritePerformed",
            "remoteCaptureAuthenticated",
            "formalCaseQualified",
            "guidanceConsumed",
            "learningBenefitVerified",
            "qualified",
        ] {
            assert_eq!(result[key], false);
        }
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn drift_partial_readbacks_and_foreign_lessons_cannot_advance() {
        let (root, evidence) = fixture();
        for (path, value) in [
            ("/after/revision", json!("c".repeat(40))),
            ("/before/dirty", json!(true)),
            ("/tables/program_facts/truncated", json!(true)),
            ("/tables/program_facts/row_count", json!(2)),
            (
                "/tables/program_facts/rows/0/row/payload/nested/unchanged",
                json!(false),
            ),
            ("/lessonSource/revision", json!("c".repeat(40))),
            (
                "/lessonSource/tables/experiment_lessons/rows/0/row/status",
                json!("observed"),
            ),
        ] {
            let mut wrong = evidence.clone();
            *wrong.pointer_mut(path).unwrap() = value;
            assert!(
                verify(
                    &root.join("stage"),
                    &root.join("source"),
                    &root.join("next"),
                    &serde_json::to_vec(&wrong).unwrap()
                )
                .is_err(),
                "{path}"
            );
        }
        for name in [
            "source-set.txt",
            "assessment.json",
            "receipt.json",
            "program_facts.jsonl",
        ] {
            let path = root.join("next").join(name);
            let original = fs::read(&path).unwrap();
            fs::write(&path, b"changed").unwrap();
            assert!(
                verify(
                    &root.join("stage"),
                    &root.join("source"),
                    &root.join("next"),
                    &serde_json::to_vec(&evidence).unwrap()
                )
                .is_err(),
                "{name}"
            );
            fs::write(&path, original).unwrap();
        }
        fs::remove_dir_all(root).unwrap();
    }
}
