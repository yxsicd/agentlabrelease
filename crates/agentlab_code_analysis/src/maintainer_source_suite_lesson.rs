//! Preserve original source-suite evidence through the ordinary experience tables.
//! A reviewed interpretation is neither reviewer authentication nor case admission.
use crate::{asset_exchange::Tables, digest, maintainer_source_diagnostic as diagnostic};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key]
        .as_str()
        .filter(|s| !s.trim().is_empty() && s.len() <= 8192)
        .ok_or_else(|| format!("source suite lesson {key} absent or oversized"))
}
fn load(root: &Path, name: &str) -> Result<Value, String> {
    serde_json::from_slice(&diagnostic::read(&root.join(name), 4 * 1024 * 1024)?)
        .map_err(|e| e.to_string())
}
fn consumer() -> String {
    digest(
        &[
            include_bytes!("maintainer_source_suite_lesson.rs").as_slice(),
            include_bytes!("maintainer_source_diagnostic.rs").as_slice(),
        ]
        .concat(),
    )
}

/// Exact bounded evidence selection; do not copy Agent homes or gateway credentials.
fn inputs(stage: &Path, suite: &Path) -> Result<BTreeMap<String, Vec<u8>>, String> {
    let report = diagnostic::reconstruct_suite(stage, suite)?;
    let mut files = BTreeMap::new();
    for name in [
        "stage-receipt.json",
        "request.json",
        "proposal.json",
        "design.json",
        "design-runtime.cjs",
        "controls.cjs",
    ] {
        files.insert(
            format!("source-stage/{name}"),
            diagnostic::read(&stage.join(name), 4 * 1024 * 1024)?,
        );
    }
    files.insert(
        "source-suite/result.json".into(),
        diagnostic::read(&suite.join("result.json"), 128 * 1024)?,
    );
    for i in 0..report["controls"].as_array().unwrap().len() {
        let directory = suite.join(format!("control-{i}"));
        for name in [
            "intent.json",
            "request.json",
            "support.json",
            "descriptor.json",
            "feedback.json",
        ] {
            files.insert(
                format!("source-suite/control-{i}/{name}"),
                diagnostic::read(&directory.join(name), 4 * 1024 * 1024)?,
            );
        }
        let captures = fs::read_dir(&directory)
            .map_err(|e| e.to_string())?
            .map(|e| e.map(|e| e.file_name().to_string_lossy().into_owned()))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| e.to_string())?;
        let capture = captures
            .iter()
            .find(|n| n.starts_with("contained-input-"))
            .ok_or("source suite capture missing")?;
        for name in [
            "request.json",
            "process.json",
            "worker-stdout.log",
            "worker-stderr.log",
        ] {
            files.insert(
                format!("source-suite/control-{i}/{capture}/{name}"),
                diagnostic::read(&directory.join(capture).join(name), 1024 * 1024)?,
            );
        }
    }
    need(
        files.values().map(Vec::len).sum::<usize>() <= 32 * 1024 * 1024,
        "source suite aggregate evidence budget",
    )?;
    Ok(files)
}

/// Reconstruct the original format before rendering any analytical interpretation.
pub fn assets(
    root: &Path,
    review: Option<&[u8]>,
    historical_consumer: Option<&str>,
) -> Result<Tables, String> {
    let stage = root.join("source-stage");
    let suite = root.join("source-suite");
    let files = inputs(&stage, &suite)?;
    let inventory_bytes = diagnostic::read(&root.join("source-suite-inputs.json"), 128 * 1024)?;
    let inventory: Value = serde_json::from_slice(&inventory_bytes).map_err(|e| e.to_string())?;
    let expected = inventory_for(&files);
    need(
        inventory == expected,
        "source suite evidence inventory differs",
    )?;
    let report = diagnostic::reconstruct_suite(&stage, &suite)?;
    let request = load(&stage, "request.json")?;
    let scope = &request["scope"];
    let scope_bytes = serde_json::to_vec(scope).map_err(|e| e.to_string())?;
    need(
        diagnostic::read(&root.join("candidate.json"), 256 * 1024)? == scope_bytes
            && scope["id"] == load(&stage, "proposal.json")?["scopeSkillId"]
            && scope["repositoryId"] == request["source"]["repositoryId"]
            && scope["sourceRevision"] == request["source"]["revision"],
        "source suite original scope differs",
    )?;
    text(scope, "id")?;
    text(scope, "repositoryId")?;
    text(scope, "sourceRevision")?;
    let design = load(&stage, "design.json")?;
    let review_bytes = review.unwrap_or(b"null");
    need(
        review_bytes.len() <= 128 * 1024,
        "source suite review budget",
    )?;
    let reviewed: Value = serde_json::from_slice(review_bytes).map_err(|e| e.to_string())?;
    if review.is_some() {
        let original: BTreeMap<String, String> = request["sourceFiles"]
            .as_array()
            .ok_or("source suite source inventory absent")?
            .iter()
            .filter_map(|f| {
                Some((
                    f["path"].as_str()?.to_owned(),
                    f["content"].as_str()?.to_owned(),
                ))
            })
            .collect();
        let mut variants = BTreeSet::new();
        variants.insert(digest(
            &serde_json::to_vec(&original).map_err(|e| e.to_string())?,
        ));
        for control in design["controls"]
            .as_array()
            .ok_or("source suite control inventory absent")?
        {
            let edits = control["edits"]
                .as_array()
                .ok_or("source suite control edits absent")?;
            if control["role"] == "baseline" {
                need(edits.is_empty(), "source suite baseline source changed")?;
                continue;
            }
            need(
                !edits.is_empty(),
                "source suite nonbaseline source unchanged",
            )?;
            let mut changed = original.clone();
            for edit in edits {
                let body = changed
                    .get_mut(text(edit, "path")?)
                    .ok_or("source suite edit outside loaded source")?;
                let before = text(edit, "before")?;
                let after = edit["after"]
                    .as_str()
                    .ok_or("source suite replacement absent")?;
                need(
                    before != after && body.matches(before).count() == 1,
                    "source suite edit ambiguous or unchanged",
                )?;
                *body = body.replacen(before, after, 1);
            }
            need(
                variants.insert(digest(
                    &serde_json::to_vec(&changed).map_err(|e| e.to_string())?,
                )),
                "source suite duplicate source variant",
            )?;
        }
        need(
            report["controls"].as_array().unwrap().iter().all(|c| {
                let failed = c["observedFailedCheckIds"].as_array().unwrap();
                if c["controlRole"] == "wrong" {
                    !failed.is_empty()
                } else {
                    failed.is_empty()
                }
            }),
            "source suite positive-negative semantic observations absent",
        )?;
        need(reviewed["schema"] == "agentlab.source_suite_lesson_review.v1"
            && reviewed["reviewed"] == true && reviewed["verdict"] == "accept"
            && reviewed["automaticPromotion"] == false
            && reviewed["unresolvedFindings"] == json!([])
            && report["status"] == "declarations-matched", "source suite lesson requires resolved independent review and matched complete controls")?;
        for (key, value) in [
            ("scopeSha256", json!(digest(&scope_bytes))),
            (
                "requestSha256",
                json!(digest(&files["source-stage/request.json"])),
            ),
            ("designSha256", report["designSha256"].clone()),
            ("proposalSha256", report["proposalSha256"].clone()),
            ("suiteResultSha256", report["suiteResultSha256"].clone()),
            ("inputInventorySha256", json!(digest(&inventory_bytes))),
        ] {
            need(
                reviewed[key] == value,
                "source suite lesson review binding differs",
            )?;
        }
        for key in [
            "id",
            "scope",
            "reviewerId",
            "phenomenon",
            "cause",
            "change",
            "factId",
            "skillId",
            "body",
        ] {
            text(&reviewed, key)?;
        }
        need(
            reviewed["factId"] != reviewed["skillId"] && reviewed["skillStage"] == "calibration",
            "source suite lesson targets or stage invalid",
        )?;
        for (key, declared) in [
            ("checkReviews", &design["checks"]),
            ("scenarioReviews", &design["scenarios"]),
            ("controlReviews", &design["controls"]),
        ] {
            let rows = reviewed[key]
                .as_array()
                .ok_or("source suite complete semantic review absent")?;
            let ids: BTreeSet<_> = declared
                .as_array()
                .ok_or("source suite design inventory absent")?
                .iter()
                .map(|r| r["id"].as_str().unwrap())
                .collect();
            let mut seen = BTreeSet::new();
            for row in rows {
                let id = text(row, "id")?;
                need(
                    ids.contains(id) && seen.insert(id) && row["accepted"] == true,
                    "source suite semantic review omitted, duplicate or rejected",
                )?;
                text(row, "rationale")?;
                if key == "controlReviews" {
                    need(
                        row["exercisedByScenarioIds"].as_array().is_some_and(|s| {
                            !s.is_empty()
                                && s.iter().all(|id| {
                                    design["scenarios"]
                                        .as_array()
                                        .unwrap()
                                        .iter()
                                        .any(|r| r["id"] == *id)
                                })
                        }),
                        "source suite control exercise review absent",
                    )?;
                }
                let evidence = row["sourceEvidence"]
                    .as_array()
                    .filter(|a| !a.is_empty() && a.len() <= 8)
                    .ok_or("source suite semantic source evidence absent")?;
                for e in evidence {
                    let path = text(e, "path")?;
                    let quote = text(e, "quote")?;
                    need(
                        request["sourceFiles"].as_array().is_some_and(|files| {
                            files.iter().any(|f| {
                                f["path"] == path
                                    && f["content"].as_str().is_some_and(|s| s.contains(quote))
                            })
                        }),
                        "source suite review quote outside original source",
                    )?;
                }
            }
            need(seen == ids, "source suite semantic review incomplete")?;
        }
        need(
            design["controls"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|c| c["role"] == "wrong")
                .count()
                >= 2,
            "source suite lesson needs two distinct wrong controls",
        )?;
    }
    let current = consumer();
    let consumer = historical_consumer.unwrap_or(&current);
    need(
        consumer.len() == 64
            && consumer
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
        "source suite projection identity invalid",
    )?;
    let run = format!(
        "source-suite-{}",
        digest(&serde_json::to_vec(&json!([inventory, consumer])).map_err(|e| e.to_string())?)
    );
    let evidence = format!("{run}-lesson-{}", digest(review_bytes));
    let validation = format!("{evidence}-validation");
    let qualification = json!({"boundary":"reviewed interpretation of independently reconstructed source-suite controls",
        "harmonyBuildQualified":false,"harmonyRuntimeQualified":false,"uiQualified":false,"caseQualified":false,
        "producerAuthenticated":false,"reviewerAuthenticated":false,"learningBenefitVerified":false});
    let mut tables = Tables::new();
    let mut put = |table: &str, mut row: Value| {
        row["assetClass"] = json!("evaluation-instance");
        row["runId"] = json!(run);
        tables
            .entry(table.into())
            .or_default()
            .insert(row["id"].as_str().unwrap().into(), row);
    };
    put(
        "runs",
        json!({"id":run,"kind":"recorded-source-control-suite","sourceScopeId":scope["id"],
        "repositoryId":scope["repositoryId"],"sourceRevision":scope["sourceRevision"],"suiteResultSha256":report["suiteResultSha256"],
        "qualified":false,"automaticPromotion":false}),
    );
    put(
        "analysis_records",
        json!({"id":format!("{run}-feedback"),"kind":"raw-source-suite-reconstruction",
        "code":"maintainer_source_suite_lesson::assets","consumerSourceSha256":consumer,
        "inputSha256":digest(&inventory_bytes),"result":report}),
    );
    let mut expected = serde_json::Map::new();
    let mut control_ids = Vec::new();
    for (i, c) in report["controls"].as_array().unwrap().iter().enumerate() {
        let id = format!("{run}-control-{i}");
        let variant = format!("{}-{i}", text(c, "controlId")?);
        let passed = c["observedFailedCheckIds"].as_array().unwrap().is_empty();
        expected.insert(variant.clone(), json!(passed));
        control_ids.push(id.clone());
        put(
            "calibration_controls",
            json!({"id":id,"variant":variant,"role":c["controlRole"],
            "recovery":i==design["controls"].as_array().unwrap().len(),"completed":true,"observedVerdict":if passed {"accept"} else {"reject"},
            "capturePath":format!("source-suite/control-{i}"),"captureSha256":c["processSha256"],"stdoutSha256":c["stdoutSha256"]}),
        );
        for check in c["checks"].as_array().unwrap() {
            put(
                "checks",
                json!({"id":format!("{id}-check-{}",digest(text(check,"id")?.as_bytes())),"controlId":id,
                "variant":variant,"check":check["id"],"passed":check["passed"],"authority":"independently-reconstructed-frozen-check"}),
            );
        }
    }
    if review.is_some() {
        let promotion = json!({"id":reviewed["id"],"scope":reviewed["scope"],"phenomenon":reviewed["phenomenon"],
            "cause":reviewed["cause"],"change":reviewed["change"],"factId":reviewed["factId"],"skillId":reviewed["skillId"],
            "body":reviewed["body"],"skillStage":reviewed["skillStage"],"expected":expected,"qualification":qualification});
        put(
            "experiment_lessons",
            json!({"id":reviewed["id"],"kind":"calibrated-method-lesson","status":"verified",
            "scope":reviewed["scope"],"phenomenon":reviewed["phenomenon"],"cause":reviewed["cause"],"change":reviewed["change"],
            "repositoryId":scope["repositoryId"],"sourceRevision":scope["sourceRevision"],"analysisId":format!("{run}-feedback"),
            "evidenceIds":[evidence],"validationIds":[validation],"targetIds":[reviewed["factId"],reviewed["skillId"]],
            "promotionContract":promotion,"attribution":"explicit-reviewed-interpretation-of-reconstructed-controls",
            "reviewerId":reviewed["reviewerId"],"reviewSha256":digest(review_bytes),"automaticPromotion":false,"qualified":false}),
        );
        put(
            "lesson_evidence",
            json!({"id":evidence,"lessonId":reviewed["id"],"kind":"reconstructed-source-suite-controls",
            "capturePath":"source-suite-inputs.json","captureSha256":digest(&inventory_bytes),
            "reviewPath":"lesson-review.json","reviewSha256":digest(review_bytes),"controlIds":control_ids}),
        );
        put(
            "lesson_validations",
            json!({"id":validation,"lessonId":reviewed["id"],"kind":"positive-negative-calibration",
            "passed":true,"scope":reviewed["scope"],"evidenceId":evidence,"expected":expected,"qualification":qualification,
            "reviewSha256":digest(review_bytes)}),
        );
    }
    for (name, bytes) in files.iter().map(|(n, b)| (n.as_str(), b.as_slice())).chain(
        [("lesson-review.json", review_bytes)]
            .into_iter()
            .filter(|_| review.is_some()),
    ) {
        put(
            "evidence_files",
            json!({"id":format!("{run}-file-{}-{}",digest(name.as_bytes()),digest(bytes)),"path":name,"sha256":digest(bytes),"bytes":bytes.len()}),
        );
    }
    for (name, bytes) in [
        ("candidate.json", scope_bytes.as_slice()),
        ("source-suite-inputs.json", inventory_bytes.as_slice()),
    ] {
        put(
            "evidence_files",
            json!({"id":format!("{run}-file-{}-{}",digest(name.as_bytes()),digest(bytes)),
            "path":name,"sha256":digest(bytes),"bytes":bytes.len()}),
        );
    }
    Ok(tables)
}

fn inventory_for(files: &BTreeMap<String, Vec<u8>>) -> Value {
    json!({"schema":"agentlab.source_suite_inputs.v1","files":files.iter().map(|(path,bytes)|
        json!({"path":path,"sha256":digest(bytes),"bytes":bytes.len()})).collect::<Vec<_>>()})
}

/// Exclusive operational snapshot; a review may add a lesson but never active knowledge.
pub fn export(
    stage: &Path,
    suite: &Path,
    review: Option<&[u8]>,
    out: &Path,
) -> Result<Value, String> {
    let files = inputs(stage, suite)?;
    let inventory = inventory_for(&files);
    for parent in out
        .parent()
        .ok_or("source suite output parent absent")?
        .ancestors()
    {
        if !parent.as_os_str().is_empty() {
            need(
                !fs::symlink_metadata(parent)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink(),
                "source suite output symlink",
            )?;
        }
    }
    fs::create_dir(out).map_err(|e| e.to_string())?;
    for (name, bytes) in &files {
        let path = out.join(name);
        fs::create_dir_all(path.parent().unwrap()).map_err(|e| e.to_string())?;
        fs::write(path, bytes).map_err(|e| e.to_string())?;
    }
    fs::write(
        out.join("source-suite-inputs.json"),
        serde_json::to_vec(&inventory).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let request: Value =
        serde_json::from_slice(&files["source-stage/request.json"]).map_err(|e| e.to_string())?;
    fs::write(
        out.join("candidate.json"),
        serde_json::to_vec(&request["scope"]).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if let Some(review) = review {
        fs::write(out.join("lesson-review.json"), review).map_err(|e| e.to_string())?;
    }
    let tables = assets(out, review, None)?;
    Ok(crate::asset_exchange::export(
        out,
        "evaluation-instance",
        &tables,
    ))
}

pub fn current_consumer_digest() -> String {
    consumer()
}
