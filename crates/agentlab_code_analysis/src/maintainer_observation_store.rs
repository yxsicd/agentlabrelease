//! Observation-only, revision-fenced import planning and exact committed readback.
//! Transport and producer authentication remain explicit external boundaries.
use crate::{digest, maintainer_behavior_checks::observation_assets};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Component, Path},
};
type Tables = BTreeMap<String, BTreeMap<String, Value>>;
#[path = "maintainer_observation_archive.rs"]
mod archive;
fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn file(root: &Path, name: &str) -> Result<Vec<u8>, String> {
    let path = root.join(name);
    for ancestor in path.ancestors() {
        need(
            !fs::symlink_metadata(ancestor)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "observation input symlink",
        )?;
    }
    let meta = fs::metadata(&path).map_err(|e| e.to_string())?;
    need(
        meta.is_file() && meta.len() <= 32 * 1024 * 1024,
        "observation file budget exceeded",
    )?;
    fs::read(path).map_err(|e| e.to_string())
}
fn oid(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        s.len() == 40
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}
fn uuid(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        s.len() == 36
            && s.bytes().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    b == b'-'
                } else {
                    b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
                }
            })
    })
}
fn stable_uuid(bytes: &[u8]) -> String {
    let sha = digest(bytes);
    format!(
        "{}-{}-4{}-8{}-{}",
        &sha[..8],
        &sha[8..12],
        &sha[13..16],
        &sha[17..20],
        &sha[20..32]
    )
}
fn source(root: &Path) -> Result<(Tables, Value), String> {
    let candidate = file(root, "candidate.json")?;
    // Presence includes dangling symlinks: malformed inputs must not silently
    // select a different producer format.
    let present = |name: &str| -> Result<bool, String> {
        match fs::symlink_metadata(root.join(name)) {
            Ok(_) => Ok(true),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
            Err(e) => Err(e.to_string()),
        }
    };
    let source_suite = present("source-suite-inputs.json")?;
    let (expected, mut binding) = if source_suite {
        need(
            !present("behavior-contract.json")? && !present("behavior-capture.json")?,
            "observation capture formats ambiguous",
        )?;
        let inventory = file(root, "source-suite-inputs.json")?;
        let review = if present("lesson-review.json")? {
            Some(file(root, "lesson-review.json")?)
        } else {
            None
        };
        let analysis_bytes = file(root, "analysis_records.jsonl")?;
        let analyses: Vec<Value> = analysis_bytes
            .split(|b| *b == b'\n')
            .filter(|l| !l.iter().all(u8::is_ascii_whitespace))
            .map(serde_json::from_slice)
            .collect::<Result<_, _>>()
            .map_err(|e| e.to_string())?;
        need(
            analyses.len() == 1,
            "observation source suite analyzer ambiguous",
        )?;
        let analysis = &analyses[0];
        need(
            analysis["kind"] == "raw-source-suite-reconstruction"
                && analysis["code"] == "maintainer_source_suite_lesson::assets",
            "observation source suite analyzer unsupported",
        )?;
        let consumer = analysis["consumerSourceSha256"]
            .as_str()
            .ok_or("observation source suite projection absent")?;
        let tables =
            crate::maintainer_source_suite_lesson::assets(root, review.as_deref(), Some(consumer))?;
        (
            tables,
            json!({"captureKind":"source-suite","candidateSha256":digest(&candidate),
            "inputInventorySha256":digest(&inventory),"reviewSha256":review.as_deref().map(digest),
            "projectionRevalidation":{"declaredOriginalConsumerSha256":consumer,
                "currentConsumerSha256":crate::maintainer_source_suite_lesson::current_consumer_digest(),
                "originalProducerAuthenticated":false,"currentSemanticReconstructionRequired":true}}),
        )
    } else {
        need(
            !present("lesson-review.json")?,
            "reviewed behavior lesson import unsupported",
        )?;
        let contract = file(root, "behavior-contract.json")?;
        let capture = file(root, "behavior-capture.json")?;
        (
            observation_assets(&candidate, &contract, &capture)?,
            json!({"candidateSha256":digest(&candidate),"contractSha256":digest(&contract),"captureSha256":digest(&capture)}),
        )
    };
    let manifest_bytes = file(root, "export.json")?;
    let manifest: Value = serde_json::from_slice(&manifest_bytes).map_err(|e| e.to_string())?;
    need(
        manifest["schema"] == "agentlab.asset_exchange.v1"
            && manifest["assetClass"] == "evaluation-instance",
        "observation manifest differs",
    )?;
    let metas = manifest["tables"]
        .as_object()
        .ok_or("observation tables absent")?;
    need(
        metas.len() == expected.len() && expected.keys().all(|name| metas.contains_key(name)),
        "observation export contains unowned or missing tables",
    )?;
    for (name, rows) in &expected {
        let bytes = file(root, &format!("{name}.jsonl"))?;
        need(
            metas[name]["sha256"] == digest(&bytes) && metas[name]["rowCount"] == rows.len(),
            "observation table digest or count differs",
        )?;
        let mut actual = BTreeMap::new();
        for line in bytes
            .split(|b| *b == b'\n')
            .filter(|l| !l.iter().all(u8::is_ascii_whitespace))
        {
            let row: Value = serde_json::from_slice(line).map_err(|e| e.to_string())?;
            let id = row["id"]
                .as_str()
                .ok_or("observation row id missing")?
                .to_owned();
            need(
                actual.insert(id, row).is_none(),
                "observation duplicate row",
            )?;
        }
        need(
            &actual == rows,
            "observation rows differ from raw reconstruction",
        )?;
    }
    binding["manifestSha256"] = json!(digest(&manifest_bytes));
    Ok((expected, binding))
}
fn snapshot(
    value: &Value,
    repo: &Value,
    revision: &Value,
    prefix: &Value,
    names: &Tables,
) -> Result<Tables, String> {
    need(
        value["schema"] == "agentlab.observation_store_snapshot.v1"
            && value["repository"] == *repo
            && value["revision"] == *revision
            && value["tablePrefix"] == *prefix
            && oid(revision),
        "observation snapshot identity differs",
    )?;
    let tables = value["tables"]
        .as_object()
        .ok_or("observation snapshot tables missing")?;
    need(
        tables.len() == names.len(),
        "observation snapshot table set differs",
    )?;
    let mut result = Tables::new();
    for name in names.keys() {
        let table = tables.get(name).ok_or("observation remote table missing")?;
        need(
            table["revision"] == *revision
                && table["dirty"] == false
                && table["truncated"] == false,
            "observation remote snapshot incomplete or dirty",
        )?;
        let rows = table["rows"]
            .as_array()
            .filter(|r| r.len() <= 1000)
            .ok_or("observation remote row budget exceeded")?;
        let mut by_id = BTreeMap::new();
        for item in rows {
            let key = item["key"]
                .as_str()
                .ok_or("observation remote key missing")?
                .to_owned();
            need(
                item["row"]["id"] == key && by_id.insert(key, item["row"].clone()).is_none(),
                "observation remote key conflict",
            )?;
        }
        result.insert(name.clone(), by_id);
    }
    Ok(result)
}
/// Existing tables only: no provisioning, upserts, deletes or knowledge writes.
pub fn plan(root: &Path, remote: &[u8], destination: &[u8]) -> Result<Value, String> {
    let (mut local, mut source_binding) = source(root)?;
    let destination: Value = serde_json::from_slice(destination).map_err(|e| e.to_string())?;
    if let Some(selected) = destination.get("preserveRawFiles") {
        need(
            selected.is_boolean(),
            "observation raw preservation selection invalid",
        )?;
        if selected == true {
            need(
                source_binding["captureKind"] == "source-suite",
                "raw preservation currently requires reconstructed source suite",
            )?;
            let (rows, binding) = archive::prepare(root, &local)?;
            local.insert("raw_archive_chunks".into(), rows);
            source_binding["rawArchive"] = binding;
        }
    }
    need(
        destination["schema"] == "agentlab.observation_store_destination.v1"
            && destination["reviewed"] == true
            && destination["automaticPromotion"] == false,
        "observation destination unreviewed",
    )?;
    let repo = destination["repository"]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or("observation repository missing")?;
    need(
        destination["knowledgeRepository"]
            .as_str()
            .is_some_and(|s| !s.is_empty() && s != repo),
        "observation destination must differ from knowledge repository",
    )?;
    need(
        oid(&destination["expectedRevision"]) && uuid(&destination["transactionId"]),
        "observation revision or transaction identity invalid",
    )?;
    let prefix = destination["tablePrefix"]
        .as_str()
        .ok_or("observation table prefix missing")?;
    need(
        prefix.ends_with('/')
            && Path::new(prefix)
                .components()
                .all(|c| matches!(c, Component::Normal(_))),
        "observation table prefix escapes destination",
    )?;
    let remote: Value = serde_json::from_slice(remote).map_err(|e| e.to_string())?;
    let mut expected = snapshot(
        &remote,
        &destination["repository"],
        &destination["expectedRevision"],
        &destination["tablePrefix"],
        &local,
    )?;
    let mut groups = Vec::new();
    let mut inserted = 0;
    for (name, rows) in &local {
        let existing = expected.get_mut(name).unwrap();
        let mut operations = Vec::new();
        for (key, row) in rows {
            if let Some(before) = existing.get(key) {
                need(
                    before == row,
                    "observation stable row conflict; overwrite forbidden",
                )?;
            } else {
                operations.push(json!({"op":"insert","operation_id":stable_uuid(&serde_json::to_vec(&json!([destination["transactionId"],name,key,row])).unwrap()),"key":key,"row":row}));
                existing.insert(key.clone(), row.clone());
                inserted += 1;
            }
        }
        if !operations.is_empty() {
            groups.push(json!({"path":format!("{prefix}{name}"),"operations":operations}));
        }
    }
    if destination["preserveRawFiles"] == true {
        need(
            serde_json::to_vec(&groups)
                .map_err(|e| e.to_string())?
                .len()
                <= 1024 * 1024,
            "observation raw archive single transaction budget exceeded",
        )?;
    }
    Ok(
        json!({"schema":"agentlab.observation_store_plan.v1","source":source_binding,"destination":destination,
        "insertedRows":inserted,"expectedTables":expected,"automaticPromotion":false,
        "transaction":if inserted==0 {Value::Null} else {json!({"repo":repo,"topic_id":"main","expected_revision":destination["expectedRevision"],
            "transaction_id":destination["transactionId"],"idempotency_key":destination["transactionId"],"actor":null,"tables":groups,
            "message":"Persist independently reconstructed operational observations; no knowledge promotion"})}}),
    )
}
/// Verify complete prior rows plus new rows, not merely selected insert receipts.
pub fn verify(
    root: &Path,
    plan_bytes: &[u8],
    receipt_bytes: &[u8],
    remote_bytes: &[u8],
    baseline_bytes: &[u8],
) -> Result<Value, String> {
    let plan: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
    need(
        plan["schema"] == "agentlab.observation_store_plan.v1"
            && plan["automaticPromotion"] == false,
        "observation plan invalid",
    )?;
    let rebuilt = self::plan(
        root,
        baseline_bytes,
        &serde_json::to_vec(&plan["destination"]).map_err(|e| e.to_string())?,
    )?;
    need(
        rebuilt == plan,
        "observation plan differs from original baseline reconstruction",
    )?;
    let (mut local, mut binding) = source(root)?;
    let raw_preserved = plan["destination"]["preserveRawFiles"] == true;
    if raw_preserved {
        let (rows, raw_binding) = archive::prepare(root, &local)?;
        local.insert("raw_archive_chunks".into(), rows);
        binding["rawArchive"] = raw_binding;
    }
    need(
        binding == plan["source"],
        "observation source changed after planning",
    )?;
    let receipt: Value = serde_json::from_slice(receipt_bytes).map_err(|e| e.to_string())?;
    need(
        oid(&receipt["revision"])
            && receipt["conflicts"]
                .as_array()
                .is_some_and(|a| a.is_empty()),
        "observation transaction unconfirmed or conflicted",
    )?;
    if !plan["transaction"].is_null() {
        need(
            receipt["repo"] == plan["destination"]["repository"]
                && receipt["previous_revision"] == plan["destination"]["expectedRevision"]
                && (receipt["outcome"] == "applied" || receipt["outcome"] == "idempotent_replay"),
            "observation transaction receipt identity differs",
        )?;
    }
    let remote: Value = serde_json::from_slice(remote_bytes).map_err(|e| e.to_string())?;
    let observed = snapshot(
        &remote,
        &plan["destination"]["repository"],
        &receipt["revision"],
        &plan["destination"]["tablePrefix"],
        &local,
    )?;
    let expected: Tables =
        serde_json::from_value(plan["expectedTables"].clone()).map_err(|e| e.to_string())?;
    need(
        observed == expected,
        "observation committed rows differ; prior rows must be preserved",
    )?;
    if raw_preserved {
        archive::reconstruct(&binding["rawArchive"], &observed["raw_archive_chunks"])?;
    }
    if plan["transaction"].is_null() {
        need(
            receipt["revision"] == plan["destination"]["expectedRevision"],
            "observation no-change advanced revision",
        )?;
    }
    Ok(
        json!({"schema":"agentlab.observation_store_readback.v1","repository":plan["destination"]["repository"],"revision":receipt["revision"],
        "planSha256":digest(plan_bytes),"allRowsExact":true,"noChange":plan["transaction"].is_null(),"insertedRows":plan["insertedRows"],
        "rowSelection":{"kind":"runId","runId":local["runs"].keys().next()},
        "remoteRawBytesPreserved":raw_preserved,"reusableKnowledgeChanged":false,"nextRoundConsumed":false,"qualified":false,"automaticPromotion":false}),
    )
}

/// Describe the native-selected archive without exposing file bodies in context.
pub fn archive_descriptor(root: &Path) -> Result<Value, String> {
    let (tables, binding) = source(root)?;
    need(
        binding["captureKind"] == "source-suite",
        "raw archive requires reconstructed source suite",
    )?;
    let (rows, raw) = archive::prepare(root, &tables)?;
    Ok(json!({"definition":archive::definition(),"rawArchive":raw,"rowCount":rows.len()}))
}

/// Restore only validated immutable remote bytes into an exclusively new directory.
/// This does not authenticate the plan or claim a remote revision was freshly read.
pub fn recover(plan_bytes: &[u8], remote_bytes: &[u8], out: &Path) -> Result<Value, String> {
    let plan: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
    let remote: Value = serde_json::from_slice(remote_bytes).map_err(|e| e.to_string())?;
    need(
        plan["schema"] == "agentlab.observation_store_plan.v1"
            && plan["destination"]["preserveRawFiles"] == true
            && plan["automaticPromotion"] == false,
        "archive recovery plan invalid",
    )?;
    let expected: Tables =
        serde_json::from_value(plan["expectedTables"].clone()).map_err(|e| e.to_string())?;
    let observed = snapshot(
        &remote,
        &plan["destination"]["repository"],
        &remote["revision"],
        &plan["destination"]["tablePrefix"],
        &expected,
    )?;
    need(
        observed == expected,
        "archive recovery rows differ from planned complete snapshot",
    )?;
    let files = archive::reconstruct(
        &plan["source"]["rawArchive"],
        observed
            .get("raw_archive_chunks")
            .ok_or("archive table absent")?,
    )?;
    write_files(&files, out)?;
    Ok(
        json!({"schema":"agentlab.observation_export_recovery.v1","repository":remote["repository"],"revision":remote["revision"],
        "archiveId":plan["source"]["rawArchive"]["archiveId"],"fileCount":files.len(),"allFileBytesVerified":true,
        "remoteAuthenticated":false,"qualified":false,"automaticPromotion":false}),
    )
}

fn write_files(files: &BTreeMap<String, Vec<u8>>, out: &Path) -> Result<(), String> {
    for parent in out
        .parent()
        .ok_or("archive output parent absent")?
        .ancestors()
    {
        if !parent.as_os_str().is_empty() {
            need(
                !fs::symlink_metadata(parent)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink(),
                "archive output parent symlink",
            )?;
        }
    }
    fs::create_dir(out).map_err(|e| e.to_string())?;
    for (name, bytes) in files {
        let target = out.join(name);
        fs::create_dir_all(target.parent().unwrap()).map_err(|e| e.to_string())?;
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(target)
            .map_err(|e| e.to_string())?
            .write_all(bytes)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Bind publication metadata only after original reconstruction and full committed
/// transaction readback. Preserve the byte-exact original manifest separately.
pub fn bind_committed_export(
    root: &Path,
    plan_bytes: &[u8],
    receipt_bytes: &[u8],
    remote_bytes: &[u8],
    baseline_bytes: &[u8],
    out: &Path,
) -> Result<Value, String> {
    let verification = verify(
        root,
        plan_bytes,
        receipt_bytes,
        remote_bytes,
        baseline_bytes,
    )?;
    need(
        verification["remoteRawBytesPreserved"] == true,
        "committed export requires complete raw preservation",
    )?;
    let plan: Value = serde_json::from_slice(plan_bytes).map_err(|e| e.to_string())?;
    let remote: Value = serde_json::from_slice(remote_bytes).map_err(|e| e.to_string())?;
    let rows: Tables =
        serde_json::from_value(plan["expectedTables"].clone()).map_err(|e| e.to_string())?;
    // verify above has already compared every remote row at receipt.revision.
    let observed = snapshot(
        &remote,
        &remote["repository"],
        &remote["revision"],
        &remote["tablePrefix"],
        &rows,
    )?;
    let mut files = archive::reconstruct(
        &plan["source"]["rawArchive"],
        &observed["raw_archive_chunks"],
    )?;
    let original = files
        .get("export.json")
        .ok_or("committed original manifest absent")?
        .clone();
    need(
        !files.contains_key("original-export.json"),
        "committed original manifest name collision",
    )?;
    let mut manifest: Value = serde_json::from_slice(&original).map_err(|e| e.to_string())?;
    manifest["repository"] = remote["repository"].clone();
    manifest["revision"] = remote["revision"].clone();
    manifest["tablePrefix"] = remote["tablePrefix"].clone();
    let provenance = json!({"schema":"agentlab.observation_committed_export_binding.v1",
        "originalManifestSha256":digest(&original),"archiveId":plan["source"]["rawArchive"]["archiveId"],
        "planSha256":digest(plan_bytes),"commitReceiptSha256":digest(receipt_bytes),
        "committedReadbackSha256":digest(remote_bytes),"baselineReadbackSha256":digest(baseline_bytes),
        "allRowsExact":true,"allOriginalFileBytesPreserved":true,"remoteAuthenticated":false,
        "qualified":false,"automaticPromotion":false});
    manifest["committedBinding"] = provenance.clone();
    files.insert("original-export.json".into(), original);
    files.insert(
        "export.json".into(),
        serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?,
    );
    write_files(&files, out)?;
    Ok(
        json!({"schema":"agentlab.observation_committed_export.v1","repository":remote["repository"],
        "revision":remote["revision"],"tablePrefix":remote["tablePrefix"],"binding":provenance,
        "activeKnowledgeChanged":false,"qualified":false,"automaticPromotion":false}),
    )
}
