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
        && !path.contains(':')
        && path
            .split('/')
            .all(|v| !v.is_empty() && v != "." && v != "..")
}

/// Explicit construction edit selections, separate from read-only context.
/// This binds scope ownership and source preconditions, not semantic readiness
/// or permission to execute edits. Successor admission must consume this packet.
pub fn prepare_edit_boundary(
    base: &Path,
    source: &Path,
    repository_id: &str,
    selection_bytes: &[u8],
) -> Result<Value, String> {
    need(
        selection_bytes.len() <= 64 * 1024,
        "edit selection exceeds budget",
    )?;
    let selection: Value = serde_json::from_slice(selection_bytes).map_err(|e| e.to_string())?;
    need(
        selection["schema"] == "agentlab.case_edit_selection.v1",
        "edit selection schema differs",
    )?;
    let edits = selection["edits"]
        .as_array()
        .ok_or("edit selections absent")?;
    need(
        !edits.is_empty() && edits.len() <= 32,
        "edit selection requires 1..32 paths",
    )?;
    let mut paths = BTreeSet::new();
    let mut anchors = BTreeSet::new();
    for edit in edits {
        let path = edit["path"].as_str().ok_or("edit path absent")?;
        let anchor = edit["anchorPath"].as_str().ok_or("edit anchor absent")?;
        need(
            relative(path) && relative(anchor) && paths.insert(path),
            "edit path unsafe or duplicate",
        )?;
        need(
            ["modify", "create"].contains(&edit["mode"].as_str().unwrap_or("")),
            "edit mode unsupported",
        )?;
        need(
            edit["ownerScopeSkillId"]
                .as_str()
                .is_some_and(|s| !s.is_empty()),
            "edit owner absent",
        )?;
        need(
            edit["reason"]
                .as_str()
                .is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 1000),
            "edit reason absent or oversized",
        )?;
        if edit["mode"] == "modify" {
            need(
                path == anchor,
                "modified file must be its own exact source anchor",
            )?;
        }
        anchors.insert(anchor.to_owned());
    }
    let anchors: Vec<_> = anchors.into_iter().collect();
    let context = prepare(base, source, repository_id, &anchors)?;
    let scope_bytes = read(&base.join("maintainer_scope_skills.jsonl"))?;
    let scopes: Vec<Value> = std::str::from_utf8(&scope_bytes)
        .map_err(|e| e.to_string())?
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(serde_json::from_str)
        .collect::<Result<_, _>>()
        .map_err(|e| e.to_string())?;
    let revision = context["repository"]["revision"].as_str().unwrap();
    let mut entries = Vec::new();
    for edit in edits {
        let path = edit["path"].as_str().unwrap();
        let anchor = context["selectedFiles"]
            .as_array()
            .unwrap()
            .iter()
            .find(|f| f["path"] == edit["anchorPath"])
            .ok_or("edit anchor not loaded")?;
        let owners: Vec<_> = scopes
            .iter()
            .filter(|s| s["repositoryId"] == repository_id && owns(s, path))
            .collect();
        need(
            owners.len() == 1,
            "edit target requires exactly one owning scope",
        )?;
        let owner = owners[0];
        need(
            owner["id"] == edit["ownerScopeSkillId"] && anchor["ownerScopeSkillId"] == owner["id"],
            "edit target or anchor owner differs",
        )?;
        need(
            owner["sourceRevision"] == revision
                && owner["repository"] == context["repository"]["repository"],
            "edit target source differs",
        )?;
        let mut expected = json!({"kind":"existing-regular-blob","gitBlobOid":anchor["gitBlobOid"],"sha256":anchor["sha256"]});
        if edit["mode"] == "create" {
            // Check every tracked ancestor: a missing leaf below a symlink,
            // submodule or file is not a valid new source location.
            let parts: Vec<_> = path.split('/').collect();
            for n in 1..=parts.len() {
                let prefix = parts[..n].join("/");
                let tree = git(source, &["ls-tree", "-z", revision, "--", &prefix])?;
                if n == parts.len() {
                    need(tree.is_empty(), "created edit path already tracked")?;
                } else if !tree.is_empty() {
                    let text = std::str::from_utf8(&tree).map_err(|e| e.to_string())?;
                    need(
                        text.starts_with("040000 tree "),
                        "created edit path has non-directory ancestor",
                    )?;
                }
            }
            // Ignored/untracked files are not visible in the committed Tree.
            for (n, prefix) in (1..=parts.len()).map(|n| (n, parts[..n].join("/"))) {
                match fs::symlink_metadata(source.join(prefix)) {
                    Ok(meta) => need(
                        n < parts.len() && meta.is_dir() && !meta.file_type().is_symlink(),
                        "created edit path obstructed in checkout",
                    )?,
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                    Err(e) => return Err(e.to_string()),
                }
            }
            expected = json!({"kind":"absent-at-source-revision"});
        }
        entries.push(
            json!({"path":path,"mode":edit["mode"],"ownerScopeSkillId":owner["id"],
            "anchorPath":edit["anchorPath"],"anchorGitBlobOid":anchor["gitBlobOid"],
            "reason":edit["reason"],"precondition":expected}),
        );
    }
    entries.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    need(
        prepare(base, source, repository_id, &anchors)? == context
            && read(&base.join("maintainer_scope_skills.jsonl"))? == scope_bytes,
        "edit source or knowledge changed during preparation",
    )?;
    Ok(json!({"schema":"agentlab.case_edit_boundary_packet.v1",
        "repository":context["repository"],"knowledgeCutSha256":context["knowledgeCutSha256"],
        "tableGitRevision":context["tableGitRevision"],"selectionSha256":digest(selection_bytes),
        "selectionUtf8":std::str::from_utf8(selection_bytes).map_err(|e| e.to_string())?,
        "sourceContext":context,"edits":entries,"status":"bound-construction-edit-selection",
        "grantsEditablePaths":false,"automaticPromotion":false,"authorityWritePerformed":false,
        "formalCaseQualified":false,"calibrationInherited":false,
        "boundary":"Operator-selected scope-owned construction paths only; not executable edit authority. Bind this packet to a successor request and independently qualify host, oracle and controls before execution."}))
}

/// Consumers reconstruct against the pinned checkout and knowledge cut; a
/// self-declared packet hash or embedded owner context is not sufficient.
pub fn validate_edit_boundary(
    base: &Path,
    source: &Path,
    packet_bytes: &[u8],
) -> Result<Value, String> {
    need(
        packet_bytes.len() <= 1024 * 1024,
        "edit boundary packet exceeds budget",
    )?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    let repository = packet["repository"]["id"]
        .as_str()
        .ok_or("edit packet repository absent")?;
    let selection = packet["selectionUtf8"]
        .as_str()
        .ok_or("edit packet original selection absent")?;
    let expected = prepare_edit_boundary(base, source, repository, selection.as_bytes())?;
    need(
        packet == expected,
        "edit boundary packet differs from reconstructed source selection",
    )?;
    Ok(
        json!({"schema":"agentlab.case_edit_boundary_validation.v1", "packetSha256":digest(packet_bytes),
        "editCount":expected["edits"].as_array().unwrap().len(),"status":"bound-construction-edit-selection",
        "grantsEditablePaths":false,"formalCaseQualified":false,"automaticPromotion":false}),
    )
}
/// Bind planned construction paths without pretending absent targets are source
/// facts. The original packet is independently reconstructed before use.
pub fn bind_candidate_paths(
    base: &Path,
    source: &Path,
    packet_bytes: &[u8],
    candidate_bytes: &[u8],
) -> Result<Value, String> {
    need(
        candidate_bytes.len() <= 1024 * 1024,
        "path-binding candidate exceeds budget",
    )?;
    let validation = validate_edit_boundary(base, source, packet_bytes)?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    let candidate: Value = serde_json::from_slice(candidate_bytes).map_err(|e| e.to_string())?;
    need(
        candidate["schema"] == "agentlab.shadow_case_candidate.v1"
            && candidate["automaticPromotion"] == false
            && candidate["status"] == "shadow-proposal",
        "path-binding candidate schema/status differs",
    )?;
    need(
        candidate["repositoryId"] == packet["repository"]["id"]
            && candidate["sourceRevision"] == packet["repository"]["revision"]
            && candidate["knowledgeCutSha256"] == packet["knowledgeCutSha256"]
            && candidate["lineage"]["editBoundarySha256"] == digest(packet_bytes),
        "path-binding candidate source/knowledge/selection differs",
    )?;
    let paths = candidate["editablePaths"]
        .as_array()
        .ok_or("path-binding editable paths absent")?;
    need(
        !paths.is_empty() && paths.len() <= 32,
        "path-binding editable path count invalid",
    )?;
    let owners = candidate["scopeSkillIds"]
        .as_array()
        .ok_or("path-binding candidate owners absent")?;
    let edits = packet["edits"].as_array().unwrap();
    let mut seen = BTreeSet::new();
    let mut bindings = Vec::new();
    for path in paths {
        let name = path.as_str().ok_or("path-binding editable path invalid")?;
        need(
            relative(name) && seen.insert(name),
            "path-binding path unsafe or duplicate",
        )?;
        let edit = edits
            .iter()
            .find(|e| e["path"] == *path)
            .ok_or("path-binding path not selected")?;
        need(
            owners.contains(&edit["ownerScopeSkillId"]),
            "path-binding owner absent from candidate",
        )?;
        bindings.push(json!({"path":name,"mode":edit["mode"],"ownerScopeSkillId":edit["ownerScopeSkillId"],
            "anchorPath":edit["anchorPath"],"anchorGitBlobOid":edit["anchorGitBlobOid"],"precondition":edit["precondition"],
            "constructionSelectionBound":true,"targetSourceExists":edit["mode"] == "modify"}));
    }
    Ok(
        json!({"schema":"agentlab.case_construction_path_binding.v1",
        "candidateId":candidate["id"],"candidateSha256":digest(&serde_json::to_vec(&candidate).map_err(|e| e.to_string())?),
        "sourceRevision":candidate["sourceRevision"],"knowledgeCutSha256":candidate["knowledgeCutSha256"],
        "editBoundarySha256":digest(packet_bytes),"validation":validation,"paths":bindings,
        "qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,
        "grantsEditablePaths":false,"calibrationInherited":false,
        "boundary":"Source-verified construction selection only. Created targets remain absent source, not facts. No implementation, semantic, build, runtime, calibration or case admission."}),
    )
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

/// Reconsume read-only context against source and knowledge authority. Embedded
/// hashes, source text and owners are claims until the whole packet is rebuilt.
pub fn validate_context(base: &Path, source: &Path, packet_bytes: &[u8]) -> Result<Value, String> {
    need(
        packet_bytes.len() <= 1024 * 1024,
        "context packet exceeds budget",
    )?;
    let packet: Value = serde_json::from_slice(packet_bytes).map_err(|e| e.to_string())?;
    let repository = packet["repository"]["id"]
        .as_str()
        .ok_or("context packet repository absent")?;
    let files = packet["selectedFiles"]
        .as_array()
        .ok_or("context packet files absent")?;
    let paths = files
        .iter()
        .map(|file| {
            file["path"]
                .as_str()
                .map(str::to_owned)
                .ok_or("context packet path absent".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let expected = prepare(base, source, repository, &paths)?;
    need(
        packet == expected,
        "context packet differs from reconstructed source and knowledge",
    )?;
    Ok(
        json!({"schema":"agentlab.case_construction_context_validation.v1",
        "packetSha256":digest(packet_bytes),"knowledgeCutSha256":expected["knowledgeCutSha256"],
        "tableGitRevision":expected["tableGitRevision"],"repository":expected["repository"],
        "selectedFileCount":paths.len(),"ownerScopeSkillIds":expected["ownerScopeSkillIds"],
        "sourceGitBindingVerified":true,"knowledgeBindingVerified":true,
        "grantsEditablePaths":false,"executionPerformed":false,"authorityWritePerformed":false,
        "semanticQualified":false,"executionQualified":false,"automaticPromotion":false}),
    )
}

/// No semantic qualification, Agent execution, edit grant or authority write occurs here.
pub fn prepare(
    base: &Path,
    source: &Path,
    repository_id: &str,
    paths: &[String],
) -> Result<Value, String> {
    prepare_internal(base, source, repository_id, paths, false)
}

/// Bind acquisition candidates without reading missing promised Blob contents.
/// This is not a consumable context packet or permission for implicit fetches.
pub fn prepare_object_plan(
    base: &Path,
    source: &Path,
    repository_id: &str,
    paths: &[String],
) -> Result<Value, String> {
    prepare_internal(base, source, repository_id, paths, true)
}

pub fn validate_object_plan(
    base: &Path,
    source: &Path,
    plan_bytes: &[u8],
) -> Result<Value, String> {
    need(
        plan_bytes.len() <= 1024 * 1024,
        "context object plan exceeds budget",
    )?;
    let plan: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
    let repository = plan["repository"]["id"]
        .as_str()
        .ok_or("object plan repository absent")?;
    let paths = plan["selectedFiles"]
        .as_array()
        .ok_or("object plan files absent")?
        .iter()
        .map(|file| {
            file["path"]
                .as_str()
                .map(str::to_owned)
                .ok_or("object plan path absent".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let expected = prepare_object_plan(base, source, repository, &paths)?;
    need(
        plan == expected,
        "object plan differs from reconstructed source and knowledge",
    )?;
    Ok(
        json!({"schema":"agentlab.case_context_object_plan_validation.v1",
        "planSha256":digest(plan_bytes),"repository":expected["repository"],
        "knowledgeCutSha256":expected["knowledgeCutSha256"],"tableGitRevision":expected["tableGitRevision"],
        "selectedFileCount":paths.len(),"sourceTreeBindingVerified":true,"knowledgeBindingVerified":true,
        "contentVerified":false,"networkPerformed":false,"grantsEditablePaths":false,
        "authorityWritePerformed":false,"automaticPromotion":false}),
    )
}

fn prepare_internal(
    base: &Path,
    source: &Path,
    repository_id: &str,
    paths: &[String],
    object_plan: bool,
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
        if object_plan {
            owners.insert(
                scope["id"]
                    .as_str()
                    .ok_or("context owning scope id absent")?
                    .to_owned(),
            );
            entries.push(json!({"path":path,"gitBlobOid":oid,
                "ownerScopeSkillId":scope["id"],"access":"read-only"}));
            continue;
        }
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
    let mut owner_knowledge = Vec::new();
    let mut knowledge_bytes = 0usize;
    for owner in owners.iter().filter(|_| !object_plan) {
        let mut analysis_facts = Vec::new();
        let mut excluded = Vec::new();
        for fact in tables["programFacts"].values().filter(|fact| {
            fact["kind"] == "analysis"
                && fact["scopeSkillIds"]
                    .as_array()
                    .is_some_and(|ids| ids.iter().any(|id| id == owner))
        }) {
            let evidence = fact["evidence"].as_array();
            let matched = evidence
                .map(|rows| {
                    rows.iter()
                        .filter(|row| {
                            entries.iter().any(|entry| {
                                entry["path"] == row["path"]
                                    && entry["gitBlobOid"] == row["gitBlobOid"]
                            })
                        })
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if fact["repositoryId"] != repository_id
                || fact["sourceRevision"] != revision
                || matched.is_empty()
            {
                excluded.push(json!({"factId":fact["id"],"reason":"source-identity-or-selected-Blob-binding-missing"}));
                continue;
            }
            let bytes = serde_json::to_vec(fact).map_err(|e| e.to_string())?;
            knowledge_bytes += bytes.len();
            need(
                bytes.len() <= 64 * 1024
                    && knowledge_bytes <= 256 * 1024
                    && analysis_facts.len() < 8,
                "context analysis fact budget exceeded",
            )?;
            let unloaded = evidence
                .unwrap()
                .iter()
                .filter(|row| !matched.contains(row))
                .map(|row| row["path"].clone())
                .collect::<Vec<_>>();
            analysis_facts.push(json!({"fact":fact,"factValueSha256":digest(&bytes),
                "selectedEvidenceMatched":matched,"unloadedEvidencePaths":unloaded,
                "allFactEvidenceLoaded":unloaded.is_empty(),"semanticRequalified":false}));
        }
        owner_knowledge.push(json!({"scopeSkill":tables["maintainerScopeSkills"][owner],
            "analysisFacts":analysis_facts,"excludedAnalysisFacts":excluded}));
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
    if object_plan {
        return Ok(json!({"schema":"agentlab.case_context_object_plan.v1",
            "repository":repository,"knowledgeCutSha256":digest(&cut_bytes),
            "tableGitRevision":authority,"ownerScopeSkillIds":owners,"selectedFiles":entries,
            "maximumSelectedFiles":32,"maximumContentFileBytes":65536,
            "maximumContentTotalBytes":262144,"selectionPolicy":"operator-explicit-paths",
            "contentVerified":false,"networkPerformed":false,"grantsEditablePaths":false,
            "authorityWritePerformed":false,"automaticPromotion":false,
            "boundary":"Exact regular Tree Blobs and unique owners only. Acquire objects in a separate bounded stage, then reconstruct the offline context packet. Content budgets apply after acquisition; this plan does not enforce network byte limits or qualify semantics, execution or cases."}));
    }
    Ok(
        json!({"schema":"agentlab.case_construction_context_packet.v2", "repository":repository,
        "knowledgeCutSha256":digest(&cut_bytes),"tableGitRevision":authority,"ownerScopeSkillIds":owners,
        "selectedFiles":entries,"selectedByteCount":total,"selectionPolicy":"operator-explicit-paths",
        "ownerKnowledge":owner_knowledge,"selectedAnalysisFactBytes":knowledge_bytes,
        "automaticPromotion":false,"authorityWritePerformed":false,"semanticQualified":false,
        "executionQualified":false,"grantsEditablePaths":false,
        "boundary":"Exact read-only source and committed owner-scope analysis context only. Preserve original fact limitations and unloaded evidence; selected Blob matches do not requalify semantics, source authenticity, an approved host, operation readiness or case qualification. Reuse applicable knowledge before refreshing it. Bind later accepted facts and successor inputs separately."}),
    )
}
