//! Independent captured-byte checks. No execution, source edits, or authority writes.
use crate::digest;
use flate2::bufread::GzDecoder;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    io::Read,
    path::{Component, Path},
};

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn relative(value: &str) -> bool {
    !value.is_empty()
        && Path::new(value)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
fn read(root: &Path, path: &str, budget: u64) -> Result<Vec<u8>, String> {
    require(relative(path), "qualification path escapes root")?;
    let mut full = root.to_owned();
    for component in Path::new(path).components() {
        full.push(component);
        require(
            !fs::symlink_metadata(&full)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "qualification symlink rejected",
        )?;
    }
    let metadata = fs::metadata(&full).map_err(|e| e.to_string())?;
    require(
        metadata.is_file() && metadata.len() <= budget,
        "qualification input budget exceeded",
    )?;
    let mut bytes = Vec::new();
    fs::File::open(full)
        .map_err(|e| e.to_string())?
        .take(budget + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    require(
        bytes.len() as u64 <= budget,
        "qualification input grew beyond budget",
    )?;
    Ok(bytes)
}
fn input(root: &Path, path: &str, expected: &Value) -> Result<(Vec<u8>, Value), String> {
    let bytes = read(root, path, 16 * 1024 * 1024)?;
    require(
        expected.as_str() == Some(digest(&bytes).as_str()),
        "qualification input digest mismatch",
    )?;
    let value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    Ok((bytes, value))
}

/// All members, including directories, using the existing tuple algorithm.
/// Never extracts archive paths onto the filesystem.
pub fn canonical_har(bytes: &[u8]) -> Result<Value, String> {
    require(
        bytes.len() <= 128 * 1024 * 1024,
        "qualification compressed archive budget exceeded",
    )?;
    let decoder = GzDecoder::new(bytes).take(256 * 1024 * 1024 + 1);
    let mut archive = tar::Archive::new(decoder);
    let mut members = Vec::new();
    let mut names = BTreeSet::new();
    for entry in archive.entries().map_err(|e| e.to_string())? {
        let mut entry = entry.map_err(|e| e.to_string())?;
        require(
            members.len() < 10000,
            "qualification archive member budget exceeded",
        )?;
        let name = entry
            .path()
            .map_err(|e| e.to_string())?
            .to_str()
            .ok_or("archive path is not UTF-8")?
            .to_owned();
        require(
            !name.is_empty()
                && Path::new(&name)
                    .components()
                    .all(|c| matches!(c, Component::Normal(_) | Component::CurDir)),
            "qualification archive path unsafe",
        )?;
        require(
            names.insert(name.clone()),
            "qualification archive has duplicate members",
        )?;
        let kind = entry.header().entry_type();
        require(
            kind.is_file() || kind.is_dir(),
            "qualification archive links or special members unsupported",
        )?;
        let size = entry.size();
        require(
            size <= 32 * 1024 * 1024,
            "qualification archive member too large",
        )?;
        let mut hash = Sha256::new();
        let mut consumed = 0;
        let mut buffer = [0u8; 8192];
        loop {
            let count = entry.read(&mut buffer).map_err(|e| e.to_string())?;
            if count == 0 {
                break;
            }
            consumed += count as u64;
            hash.update(&buffer[..count]);
        }
        require(
            consumed == size && (kind.is_file() || size == 0),
            "qualification archive member truncated or directory nonempty",
        )?;
        let content_sha = if kind.is_file() {
            format!("{:x}", hash.finalize())
        } else {
            String::new()
        };
        members.push(json!([
            name,
            format!("{:02x}", kind.as_byte()),
            size,
            content_sha,
            ""
        ]));
    }
    require(!members.is_empty(), "qualification archive empty")?;
    let mut decoder = archive.into_inner();
    let mut tail = [0u8; 8192];
    loop {
        let count = decoder.read(&mut tail).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        require(
            tail[..count].iter().all(|b| *b == 0),
            "qualification archive trailing payload unsupported",
        )?;
    }
    require(
        decoder.limit() > 0,
        "qualification archive expanded budget exceeded",
    )?;
    require(
        decoder.into_inner().into_inner().is_empty(),
        "qualification trailing compressed payload unsupported",
    )?;
    members.sort_by(|a, b| a[0].as_str().cmp(&b[0].as_str()));
    Ok(
        json!({"algorithm":"sha256-json-member-tuples-v1", "memberCount":members.len(),
        "sha256":digest(&serde_json::to_vec(&members).map_err(|e| e.to_string())?)}),
    )
}

/// Qualify a retained local executor capture, not a peer-execution receipt.
pub fn qualify(root: &Path, execution_sha: &str, module_root: &str) -> Result<Value, String> {
    let metadata = fs::symlink_metadata(root).map_err(|e| e.to_string())?;
    require(
        metadata.is_dir() && !metadata.file_type().is_symlink(),
        "qualification root invalid",
    )?;
    require(relative(module_root), "qualification module root invalid")?;
    let (original, execution) = input(root, "execution-receipt.json", &json!(execution_sha))?;
    require(
        execution["schema"] == "agentlab.maintainer_operation_execution.v1"
            && execution["status"] == "successful"
            && execution["qualified"] == false
            && execution["authorityWritePerformed"] == false
            && execution["automaticPromotion"] == false
            && execution["sourceCleanAfter"] == true,
        "qualification execution failed or overclaimed",
    )?;
    let (_, recipe) = input(root, "input-recipe.json", &execution["recipeSha256"])?;
    let (_, plan) = input(root, "input-plan.json", &execution["selectionPlanSha256"])?;
    let (_, before) = input(
        root,
        "input-before.json",
        &execution["beforeAssessmentSha256"],
    )?;
    require(
        recipe["schema"] == "agentlab.maintainer_build_operation_recipe.v1"
            && recipe["source"] == execution["source"]
            && recipe["scopeSkillId"] == execution["scopeSkillId"]
            && recipe["lane"] == "build-only"
            && recipe["cleanBuild"] == true
            && recipe["automaticPromotion"] == false,
        "qualification recipe identity invalid",
    )?;
    require(
        plan["schema"] == "agentlab.maintainer_flywheel_next_plan.v1"
            && before["schema"] == "agentlab.maintainer_skill_assessment.v1"
            && plan["decision"] == "propose-next-batch"
            && plan["automaticPromotion"] == false
            && plan["authorityWritePerformed"] == false
            && plan["closedLoopQualified"] == false
            && plan["assessment"] == before
            && plan["nextLane"] == "operation-verification"
            && plan["selectedScopeIds"] == json!([execution["scopeSkillId"]])
            && plan["policy"]["availableOperationKinds"] == json!(["build-only"]),
        "qualification plan identity invalid",
    )?;
    let scopes = plan["scopes"]
        .as_array()
        .ok_or("qualification scopes missing")?;
    let selected = scopes
        .iter()
        .filter(|s| s["skillId"] == execution["scopeSkillId"])
        .collect::<Vec<_>>();
    require(selected.len() == 1, "qualification scope ambiguous")?;
    let scope = selected[0];
    require(
        scope["selected"] == true
            && scope["operationKind"] == "build-only"
            && scope["repositoryId"] == execution["source"]["repositoryId"]
            && scope["repository"] == execution["source"]["repository"]
            && scope["sourceRevision"] == execution["source"]["revision"],
        "qualification scope source mismatch",
    )?;
    let owned = |path: &str| {
        relative(path) && (path == module_root || path.starts_with(&format!("{module_root}/")))
    };
    if let Some(selectors) = scope["ownershipSelectors"].as_array() {
        require(!selectors.is_empty(), "qualification ownership empty")?;
        for selector in selectors {
            match selector["type"].as_str() {
                Some("prefix") => require(
                    selector["path"].as_str().is_some_and(owned),
                    "qualification module does not cover scope",
                )?,
                Some("files") => require(
                    selector["paths"].as_array().is_some_and(|a| {
                        !a.is_empty() && a.iter().all(|p| p.as_str().is_some_and(owned))
                    }),
                    "qualification module does not cover scope",
                )?,
                _ => return Err("qualification ownership selector unsupported".into()),
            }
        }
    } else {
        require(
            scope["pathBoundary"].as_str().is_some_and(owned),
            "qualification module does not cover scope",
        )?;
    }
    let captures = execution["captures"]
        .as_array()
        .ok_or("qualification captures missing")?;
    let probes = recipe["probes"]
        .as_array()
        .ok_or("qualification probes missing")?;
    require(
        !probes.is_empty() && probes.len() <= 4 && captures.len() == probes.len() + 3,
        "qualification capture count invalid",
    )?;
    let mut identities = BTreeSet::new();
    let mut logs = Vec::new();
    for (index, capture) in captures.iter().enumerate() {
        let (label, command) = if index < probes.len() {
            (format!("probe-{index}"), &probes[index])
        } else if index == probes.len() {
            ("dependency".into(), &recipe["dependencyPreparation"])
        } else {
            (format!("build-{}", index - probes.len()), &recipe["build"])
        };
        require(
            capture["label"] == label
                && capture["command"] == *command
                && capture["status"] == "successful"
                && capture["termination"] == "completed"
                && capture["exitCode"] == 0
                && capture["durationMs"].as_u64().is_some_and(|v| v > 0)
                && capture["pid"].as_u64().is_some_and(|v| v > 0)
                && identities.insert(capture["pid"].as_u64().unwrap()),
            "qualification failed, partial or reused process capture",
        )?;
        for stream in ["stdout", "stderr"] {
            let log = &capture[stream];
            let expected_path = format!("{label}.{stream}");
            require(
                log["complete"] == true && log["path"] == expected_path,
                "qualification incomplete log",
            )?;
            let bytes = read(root, &expected_path, 64 * 1024 * 1024)?;
            require(
                log["sha256"].as_str() == Some(digest(&bytes).as_str())
                    && log["bytes"].as_u64() == Some(bytes.len() as u64),
                "qualification log bytes mismatch",
            )?;
            logs.push(json!({"path":expected_path,"bytes":bytes.len(),"sha256":digest(&bytes)}));
        }
    }
    let args = recipe["build"]["args"]
        .as_array()
        .ok_or("qualification build command missing")?;
    require(
        args.iter().any(|a| a == "clean") && args.iter().any(|a| a == "assembleHar"),
        "qualification HAR task or clean missing",
    )?;
    let artifacts = execution["artifacts"]
        .as_array()
        .filter(|a| a.len() == 2)
        .ok_or("qualification requires two artifacts")?;
    let mut checked = Vec::new();
    for (index, artifact) in artifacts.iter().enumerate() {
        let name = format!("attempt-{}.artifact", index + 1);
        require(
            artifact["attempt"] == index + 1
                && artifact["retainedPath"] == name
                && artifact["sourcePath"] == recipe["artifact"]
                && artifact["sourcePath"].as_str().is_some_and(owned),
            "qualification artifact identity mismatch",
        )?;
        let bytes = read(root, &name, 128 * 1024 * 1024)?;
        require(
            !bytes.is_empty()
                && artifact["bytes"].as_u64() == Some(bytes.len() as u64)
                && artifact["sha256"].as_str() == Some(digest(&bytes).as_str()),
            "qualification artifact bytes mismatch",
        )?;
        checked.push(json!({"attempt":index+1,"rawSha256":digest(&bytes),"artifactBytes":bytes.len(),"canonical":canonical_har(&bytes)?}));
    }
    require(
        checked[0]["canonical"] == checked[1]["canonical"],
        "qualification canonical member mismatch",
    )?;
    Ok(
        json!({"schema":"agentlab.maintainer_scope_build_capture_qualification.v1","status":"qualified",
        "automaticPromotion":false,"authorityWritePerformed":false,"source":execution["source"],
        "scopeSkillId":execution["scopeSkillId"],"moduleRoot":module_root,"executionReceiptSha256":digest(&original),
        "recipeSha256":execution["recipeSha256"],"selectionPlanSha256":execution["selectionPlanSha256"],
        "artifacts":checked,"logs":logs,"rawArchiveReproducible":checked[0]["rawSha256"] == checked[1]["rawSha256"],
        "qualificationScope":{"moduleBuild":true,"runtime":false,"tests":false,"performance":false,"typeChecking":false},
        "verificationBoundary":"Independent retained log/artifact byte readback; source cleanliness, module mapping and command authorship remain producer/operator assertions, not authenticated proof.",
        "limitations":["Build-only HAR qualification; no runtime, tests, performance, power or thermal claim.",
            "Retained Unix PIDs are capture identities, not remote AgentWeb operation identities.",
            "No Skills promotion or live authority write; a separate recorded-receipt adapter and reassessment are still required."]}),
    )
}
