//! Prepare bounded, read-only cross-scope source context from an exact knowledge cut.
use crate::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
    process::Command,
};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn read(path: &Path) -> Result<Vec<u8>, String> {
    need(path.is_absolute(), "context input path must be absolute")?;
    for p in path.ancestors() {
        need(
            !fs::symlink_metadata(p)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "context input symlink rejected",
        )?;
    }
    let size = fs::metadata(path).map_err(|e| e.to_string())?.len();
    need(size <= 16 * 1024 * 1024, "context input exceeds budget")?;
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    need(
        bytes.len() <= 16 * 1024 * 1024,
        "context input grew beyond budget",
    )?;
    Ok(bytes)
}
fn relative(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.contains(['\\', '\0', '\n', '\r'])
        && path
            .split('/')
            .all(|v| !v.is_empty() && v != "." && v != "..")
}
fn owns(scope: &Value, path: &str) -> bool {
    let prefix = |boundary: &str| path == boundary || path.starts_with(&format!("{boundary}/"));
    if let Some(selectors) = scope["ownershipSelectors"].as_array() {
        selectors.iter().any(|s| match s["type"].as_str() {
            Some("prefix") => s["path"].as_str().is_some_and(prefix),
            Some("files") => s["paths"]
                .as_array()
                .is_some_and(|p| p.iter().any(|v| v == path)),
            _ => false,
        })
    } else {
        scope["pathBoundary"].as_str().is_some_and(|b| {
            if b == "." {
                !path.contains('/')
            } else {
                prefix(b)
            }
        })
    }
}
fn git(source: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let output = Command::new("git")
        .arg("-c")
        .arg("core.fsmonitor=false")
        .arg("--literal-pathspecs")
        .args(args)
        .current_dir(source)
        .env("GIT_OPTIONAL_LOCKS", "0")
        .env("GIT_NO_LAZY_FETCH", "1")
        .output()
        .map_err(|e| e.to_string())?;
    need(output.status.success(), "context Git query failed")?;
    Ok(output.stdout)
}

/// No semantic qualification, Agent execution, edit grant or authority write occurs here.
pub fn prepare(
    base: &Path,
    source: &Path,
    repository_id: &str,
    paths: &[String],
) -> Result<Value, String> {
    need(
        source.is_absolute() && source.is_dir(),
        "context source must be an absolute checkout",
    )?;
    need(
        !paths.is_empty() && paths.len() <= 32,
        "context requires 1..32 selected paths",
    )?;
    let selected: BTreeSet<_> = paths.iter().collect();
    need(
        selected.len() == paths.len() && paths.iter().all(|p| relative(p)),
        "context paths duplicate or unsafe",
    )?;
    let cut_bytes = read(&base.join("maintainer-knowledge-cut.json"))?;
    let cut: Value = serde_json::from_slice(&cut_bytes).map_err(|e| e.to_string())?;
    let authority = cut["tableGitAuthority"]["revision"].as_str().unwrap_or("");
    need(
        cut["schema"] == "agentlab.maintainer_knowledge_cut.v1"
            && cut["automaticPromotion"] == false
            && cut.get("staging").is_none()
            && authority.len() == 40
            && authority
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
        "context requires a committed fixed knowledge cut",
    )?;
    let mut tables = BTreeMap::new();
    let mut inputs = Vec::new();
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
        let bytes = read(&base.join(file))?;
        need(
            cut["tables"][key]["path"] == file && cut["tables"][key]["sha256"] == digest(&bytes),
            "context table digest differs",
        )?;
        let mut rows = BTreeMap::new();
        for line in std::str::from_utf8(&bytes)
            .map_err(|e| e.to_string())?
            .lines()
            .filter(|v| !v.trim().is_empty())
        {
            let row: Value = serde_json::from_str(line).map_err(|e| e.to_string())?;
            let id = row["id"]
                .as_str()
                .filter(|s| !s.is_empty())
                .ok_or("context row id missing")?
                .to_owned();
            need(rows.insert(id, row).is_none(), "context duplicate row id")?;
        }
        tables.insert(key, rows);
        inputs.push((file, bytes));
    }
    let repos = cut["repositories"]
        .as_array()
        .ok_or("context repositories absent")?;
    let matches: Vec<_> = repos.iter().filter(|r| r["id"] == repository_id).collect();
    need(
        matches.len() == 1,
        "context repository absent or duplicated",
    )?;
    let repository = matches[0];
    let revision = repository["revision"]
        .as_str()
        .ok_or("context source revision absent")?;
    need(
        revision.len() == 40
            && revision
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
        "context source revision invalid",
    )?;
    let head = git(source, &["rev-parse", "HEAD"])?;
    need(
        std::str::from_utf8(&head)
            .map_err(|e| e.to_string())?
            .trim()
            == revision,
        "context checkout revision differs",
    )?;
    need(
        git(source, &["status", "--porcelain"])?.is_empty(),
        "context checkout must be clean",
    )?;
    let origin = git(source, &["remote", "get-url", "origin"])?;
    need(
        std::str::from_utf8(&origin)
            .map_err(|e| e.to_string())?
            .trim()
            == repository["repository"].as_str().unwrap_or(""),
        "context source origin differs",
    )?;
    let mut entries = Vec::new();
    let mut owners = BTreeSet::new();
    let mut total = 0usize;
    for path in selected {
        let scopes: Vec<_> = tables["maintainerScopeSkills"]
            .values()
            .filter(|s| s["repositoryId"] == repository_id && owns(s, path))
            .collect();
        need(
            scopes.len() == 1,
            "context source requires exactly one owning scope",
        )?;
        let scope = scopes[0];
        need(
            scope["sourceRevision"] == revision && scope["repository"] == repository["repository"],
            "context owning scope source differs",
        )?;
        let tree = git(source, &["ls-tree", "-z", revision, "--", path])?;
        let tree = std::str::from_utf8(&tree).map_err(|e| e.to_string())?;
        let rows: Vec<_> = tree.split('\0').filter(|s| !s.is_empty()).collect();
        need(
            rows.len() == 1,
            "context selected source absent or not a regular file",
        )?;
        let (meta, returned_path) = rows[0]
            .split_once('\t')
            .ok_or("context tree entry malformed")?;
        let fields: Vec<_> = meta.split(' ').collect();
        need(
            fields.len() == 3
                && ["100644", "100755"].contains(&fields[0])
                && fields[1] == "blob"
                && returned_path == path,
            "context source symlink, directory or submodule rejected",
        )?;
        let oid = fields[2];
        let size_bytes = git(source, &["cat-file", "-s", oid])?;
        let size: usize = std::str::from_utf8(&size_bytes)
            .map_err(|e| e.to_string())?
            .trim()
            .parse::<usize>()
            .map_err(|e| e.to_string())?;
        need(
            size <= 64 * 1024 && total + size <= 256 * 1024,
            "context source byte budget exceeded",
        )?;
        let bytes = git(source, &["cat-file", "blob", oid])?;
        need(bytes.len() == size, "context source byte length differs")?;
        let content = std::str::from_utf8(&bytes).map_err(|_| "context source must be UTF-8")?;
        total += size;
        owners.insert(
            scope["id"]
                .as_str()
                .ok_or("context owning scope id absent")?
                .to_owned(),
        );
        entries.push(
            json!({"path":path,"gitBlobOid":oid,"sha256":digest(&bytes),"byteCount":size,
            "ownerScopeSkillId":scope["id"],"access":"read-only","contentUtf8":content}),
        );
    }
    need(
        git(source, &["rev-parse", "HEAD"])? == head
            && git(source, &["status", "--porcelain"])?.is_empty(),
        "context checkout changed during preparation",
    )?;
    need(
        read(&base.join("maintainer-knowledge-cut.json"))? == cut_bytes,
        "context knowledge changed during preparation",
    )?;
    for (file, bytes) in inputs {
        need(
            read(&base.join(file))? == bytes,
            "context table changed during preparation",
        )?;
    }
    Ok(
        json!({"schema":"agentlab.case_construction_context_packet.v1", "repository":repository,
        "knowledgeCutSha256":digest(&cut_bytes),"tableGitRevision":authority,"ownerScopeSkillIds":owners,
        "selectedFiles":entries,"selectedByteCount":total,"selectionPolicy":"operator-explicit-paths",
        "automaticPromotion":false,"authorityWritePerformed":false,"semanticQualified":false,
        "executionQualified":false,"grantsEditablePaths":false,
        "boundary":"Exact read-only source context only. Owner IDs route focused analysis; they do not establish semantic truth, source authenticity, an approved host, operation readiness or case qualification. Bind later accepted facts and successor inputs separately."}),
    )
}
