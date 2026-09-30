use agentlab_code_analysis::{
    digest,
    maintainer_skill_flywheel::{assess, assess_with_receipts},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-maintainer-skill-flywheel-{}-{}-{}",
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

fn jsonl(path: &Path, rows: &[Value]) {
    let text = rows
        .iter()
        .map(|row| serde_json::to_string(row).unwrap() + "\n")
        .collect::<String>();
    fs::write(path, text).unwrap();
}

fn rows_from_file(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

fn scope(id: &str, repository_id: &str) -> Value {
    json!({
        "schema":"agentlab.maintainer_scope_skill.v1",
        "id":id,
        "skillLayer":"instance",
        "stage":"repository-scope",
        "ownershipPlane":"target-operations",
        "assetClass":"reusable-knowledge",
        "status":"source-supported",
        "repositoryId":repository_id,
        "repository":format!("https://example.invalid/{repository_id}.git"),
        "sourceRevision":"1".repeat(40),
        "sourceTreeOid":"2".repeat(40),
        "strategy":"generic-source-boundary",
        "kind":"source-component",
        "pathBoundary":"src",
        "responsibility":"Maintain the source component and its external contract.",
        "documentedTitle":null,
        "documentedPurpose":null,
        "trackedFileCount":1,
        "sourceFileCount":1,
        "codeLineCount":10,
        "testFileCount":0,
        "languages":{"generic":1},
        "externalDependencyCount":0,
        "externalDependencies":[],
        "buildEntrypoints":[],
        "testEntrypoints":[],
        "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}],
        "coverage":"all tracked files under this leaf boundary are assigned exactly once",
        "automaticPromotion":false
    })
}

fn complete_fact(id: &str, repository_id: &str, skill_id: &str) -> Value {
    json!({
        "id":id,
        "kind":"semantic-contract",
        "repositoryId":repository_id,
        "sourceRevision":"1".repeat(40),
        "scopeSkillIds":[skill_id],
        "dimensions":["responsibility","boundary","relations","behavior","operation"],
        "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}]
    })
}

fn build_receipt() -> Value {
    let attempt = |id: &str| {
        json!({
            "cleanBuild":true,"exitCode":0,"durationMs":100,"artifact":"out/library.har",
            "artifactBytes":123,"artifactSha256":"a".repeat(64),
            "canonicalMemberSha256":"b".repeat(64),"memberCount":3,"buildLogSha256":"c".repeat(64),
            "executionAuthority":{"routeDecision":"peer_direct","targetPeerId":"generic-peer","operationId":id}
        })
    };
    json!({
        "schema":"agentlab.maintainer_scope_build_qualification.v1", "status":"qualified", "automaticPromotion":false,
        "source":{"repositoryId":"arbitrary","repository":"https://example.invalid/arbitrary.git","revision":"1".repeat(40),"cleanBefore":true,"cleanAfter":true},
        "scope":{"scopeSkillIds":["scope"],"lane":"build-only","module":"library","target":"default","scopeSpecificBinding":true},
        "toolchain":{"sdkRelease":"fixture-sdk","hvigorVersion":"fixture-build","ohpmVersion":"fixture-deps"},
        "dependencyPreparation":{"status":"successful","exitCode":0,"durationMs":100,"lockSha256":"d".repeat(64)},
        "build":{"status":"successful","task":"assembleHar","command":["builder","--no-type-check","assembleHar"],"canonicalContentReproducible":true,"rawArchiveReproducible":true,"attempts":[attempt("run-one"),attempt("run-two")]},
        "qualificationScope":{"moduleBuild":true,"runtime":false,"tests":false,"performance":false},
        "limitations":["Controlled fixture; no real execution or runtime qualification."]
    })
}

#[test]
fn next_round_planner_routes_gaps_without_claiming_closed_loop() {
    use agentlab_code_analysis::maintainer_flywheel_plan::plan;
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let skill = scope("scope", "arbitrary");
    jsonl(&scopes, &[skill.clone()]);
    jsonl(&facts, &[]);
    let run = |lanes: &[&str]| {
        plan(
            &scopes,
            Some(&facts),
            &root,
            1,
            None,
            &lanes.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            4,
            80,
        )
        .unwrap()
    };
    let blocked = run(&[]);
    assert_eq!(blocked["decision"], "capability-blocked");
    assert_eq!(blocked["summary"]["capabilityBlocked"], 1);
    assert_eq!(blocked["scopes"][0]["capabilityGap"], "semantic-refresh");
    let semantic = run(&["semantic-refresh"]);
    assert_eq!(semantic["nextLane"], "semantic-refresh");
    assert_eq!(semantic["selectedScopeIds"], json!(["scope"]));
    let mut fact = complete_fact("semantic", "arbitrary", "scope");
    fact["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&facts, &[fact.clone()]);
    let operation = run(&["semantic-refresh", "operation-verification"]);
    assert_eq!(operation["nextLane"], "operation-verification");
    assert_eq!(operation["scopes"][0]["maturity"], "L2-semantic-ready");
    // A legacy operation claim or a missing receipt cannot skip this lane.
    fact["dimensions"] = json!([
        "responsibility",
        "boundary",
        "relations",
        "behavior",
        "operation"
    ]);
    jsonl(&facts, &[fact.clone()]);
    assert_eq!(
        run(&["operation-verification"])["nextLane"],
        "operation-verification"
    );
    let bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &bytes).unwrap();
    fact["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
    jsonl(&facts, &[fact]);
    let ready = run(&["operation-verification"]);
    assert_eq!(ready["summary"]["knowledgeReady"], 1);
    assert_eq!(ready["decision"], "downstream-validation-required");
    assert_eq!(ready["closedLoopQualified"], false);
    assert_eq!(ready["automaticPromotion"], false);
    assert_eq!(ready["authorityWritePerformed"], false);
    assert_eq!(ready, run(&["operation-verification"]));
    let output = root.join("next-plan.json");
    let command = || {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--plan-next-round",
                "--scope-skills",
                scopes.to_str().unwrap(),
                "--program-facts",
                facts.to_str().unwrap(),
                "--operation-receipts-root",
                root.to_str().unwrap(),
                "--round-index",
                "1",
                "--available-lane",
                "operation-verification",
                "--batch-size",
                "4",
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    assert!(command().status.success());
    let bytes = fs::read(&output).unwrap();
    assert_eq!(serde_json::from_slice::<Value>(&bytes).unwrap(), ready);
    assert!(!command().status.success());
    assert_eq!(fs::read(&output).unwrap(), bytes);
    fs::write(root.join("build.json"), b"tampered").unwrap();
    assert_eq!(
        run(&["operation-verification"])["nextLane"],
        "operation-verification"
    );
    for lanes in [
        vec!["unknown".into()],
        vec!["semantic-refresh".into(), "semantic-refresh".into()],
    ] {
        assert!(plan(&scopes, Some(&facts), &root, 1, None, &lanes, 1, 80).is_err());
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn next_round_plan_accounts_for_every_scope_and_isolates_batches() {
    use agentlab_code_analysis::maintainer_flywheel_plan::plan;
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let mut rows = vec![
        scope("zeta", "arbitrary"),
        scope("alpha", "arbitrary"),
        scope("foreign", "other"),
    ];
    let mut large = scope("large", "arbitrary");
    large["sourceFileCount"] = json!(81);
    large["trackedFileCount"] = json!(81);
    rows.push(large);
    let mut root_scope = scope("root", "arbitrary");
    root_scope["pathBoundary"] = json!(".");
    rows.push(root_scope);
    let mut stale = scope("repair", "arbitrary");
    stale["sourceRevision"] = Value::Null;
    rows.push(stale);
    jsonl(&scopes, &rows);
    let available = vec!["semantic-refresh".into()];
    let report = plan(&scopes, None, &root, 1, None, &available, 4, 80).unwrap();
    assert_eq!(report["summary"]["scopeCount"], 6);
    assert_eq!(report["summary"]["capabilityBlocked"], 2);
    assert_eq!(report["selectedScopeIds"], json!(["alpha", "zeta"]));
    assert_eq!(report["nextLane"], "semantic-refresh");
    let items = report["scopes"].as_array().unwrap();
    assert_eq!(
        items.iter().find(|row| row["skillId"] == "large").unwrap()["nextLane"],
        "scope-decomposition"
    );
    assert_eq!(
        items.iter().find(|row| row["skillId"] == "repair").unwrap()["nextLane"],
        "inventory-repair"
    );
    rows.reverse();
    jsonl(&scopes, &rows);
    let reordered = plan(&scopes, None, &root, 1, None, &available, 4, 80).unwrap();
    assert_eq!(reordered["scopes"], report["scopes"]);
    assert_eq!(reordered["selectedScopeIds"], report["selectedScopeIds"]);
    // Even same repository/lane cannot batch a different source revision.
    rows.iter_mut().find(|row| row["id"] == "zeta").unwrap()["sourceRevision"] =
        json!("9".repeat(40));
    jsonl(&scopes, &rows);
    let different = plan(&scopes, None, &root, 1, None, &available, 4, 80).unwrap();
    assert_eq!(different["selectedScopeIds"], json!(["alpha"]));
    assert!(plan(&scopes, None, &root, 1, None, &available, 0, 80).is_err());
    assert!(plan(&scopes, None, &root, 1, None, &available, 4, 0).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn productive_rounds_retain_inherited_receipts_without_original_machine() {
    use agentlab_code_analysis::{
        maintainer_operation_evidence::prepare_fact, maintainer_operation_stage::stage,
    };
    let root = temp_root();
    let mut base = root.join("base");
    fs::create_dir_all(base.join("assessments")).unwrap();
    let scope_rows = [
        scope("alpha", "arbitrary"),
        scope("beta", "arbitrary"),
        scope("gamma", "arbitrary"),
    ];
    jsonl(&base.join("maintainer_scope_skills.jsonl"), &scope_rows);
    let mut facts = scope_rows
        .iter()
        .map(|skill| {
            let id = skill["id"].as_str().unwrap();
            let mut fact = complete_fact(&format!("semantic-{id}"), "arbitrary", id);
            fact["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
            fact
        })
        .collect::<Vec<_>>();
    jsonl(&base.join("program_facts.jsonl"), &facts);
    jsonl(&base.join("maintainer_skills.jsonl"), &[]);
    jsonl(&base.join("evaluation_cases.jsonl"), &[]);
    fs::write(base.join("maintainer-knowledge-cut.json"), b"{}\n").unwrap();
    let mut receipts = root.join("original-machine");
    fs::create_dir(&receipts).unwrap();
    let mut before = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        1,
        None,
        Some(&receipts),
    )
    .unwrap();
    let bytes = serde_json::to_vec(&before).unwrap();
    fs::write(base.join("assessments/parent.json"), &bytes).unwrap();
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &[json!({
            "id":"parent", "roundIndex":1, "coverage":{},
            "assessment":{"path":"assessments/parent.json","sha256":digest(&bytes)}
        })],
    );
    for (index, skill) in scope_rows.iter().enumerate() {
        let id = skill["id"].as_str().unwrap();
        let mut receipt = build_receipt();
        receipt["scope"]["scopeSkillIds"] = json!([id]);
        let receipt_bytes = serde_json::to_vec(&receipt).unwrap();
        let name = format!("{id}.json");
        fs::write(receipts.join(&name), &receipt_bytes).unwrap();
        facts.push(
            prepare_fact(
                skill,
                json!({"path":name,"sha256":digest(&receipt_bytes)}),
                &receipts,
            )
            .unwrap(),
        );
        let candidate = root.join(format!("candidate-{index}.jsonl"));
        jsonl(&candidate, &facts);
        let before_bytes = serde_json::to_vec(&before).unwrap();
        let after = assess_with_receipts(
            &base.join("maintainer_scope_skills.jsonl"),
            Some(&candidate),
            index as u64 + 2,
            Some(&digest(&before_bytes)),
            Some(&receipts),
        )
        .unwrap();
        let before_path = root.join("before.json");
        let after_path = root.join("after.json");
        fs::write(&before_path, &before_bytes).unwrap();
        fs::write(&after_path, serde_json::to_vec(&after).unwrap()).unwrap();
        let output = root.join(format!("stage-{index}"));
        let manifest = stage(
            &base,
            &candidate,
            &before_path,
            &after_path,
            &receipts,
            &[id.to_owned()],
            &format!("round-{index}"),
            false,
            &output,
        )
        .unwrap();
        assert_eq!(
            manifest["operationEvidence"]["receipts"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            manifest["operationEvidence"]["inheritedReceipts"]
                .as_array()
                .unwrap()
                .len(),
            index
        );
        assert_eq!(manifest["automaticPromotion"], false);
        let portable = assess_with_receipts(
            &output.join("maintainer_scope_skills.jsonl"),
            Some(&output.join("program_facts.jsonl")),
            index as u64 + 2,
            Some(&digest(&before_bytes)),
            Some(&output.join("operation-evidence")),
        )
        .unwrap();
        assert_eq!(portable, after);
        assert_eq!(portable["totals"]["maintenanceReadyCount"], index + 1);
        if index > 0 {
            let saved = fs::read(receipts.join("alpha.json")).unwrap();
            fs::write(receipts.join("alpha.json"), b"tampered").unwrap();
            let rejected = root.join(format!("rejected-{index}"));
            assert!(stage(
                &base,
                &candidate,
                &before_path,
                &after_path,
                &receipts,
                &[id.to_owned()],
                &format!("bad-{index}"),
                false,
                &rejected
            )
            .is_err());
            assert!(!rejected.exists());
            fs::write(receipts.join("alpha.json"), saved).unwrap();
        }
        // The next worker receives only the portable bundle plus its new
        // receipt; the previous worker's receipt directory no longer exists.
        let next_receipts = root.join(format!("worker-{}", index + 1));
        fs::create_dir(&next_receipts).unwrap();
        for row in manifest["operationEvidence"]["receipts"]
            .as_array()
            .unwrap()
            .iter()
            .chain(
                manifest["operationEvidence"]["inheritedReceipts"]
                    .as_array()
                    .unwrap(),
            )
        {
            let path = row["path"].as_str().unwrap();
            fs::copy(
                output.join(path),
                next_receipts.join(path.strip_prefix("operation-evidence/").unwrap()),
            )
            .unwrap();
        }
        fs::remove_dir_all(&receipts).unwrap();
        receipts = next_receipts;
        base = output;
        before = after;
    }
    fs::remove_dir_all(&receipts).unwrap();
    let report = assess_with_receipts(
        &base.join("maintainer_scope_skills.jsonl"),
        Some(&base.join("program_facts.jsonl")),
        4,
        before["parentAssessmentSha256"].as_str(),
        Some(&base.join("operation-evidence")),
    )
    .unwrap();
    assert_eq!(report, before);
    assert_eq!(report["totals"]["maintenanceReadyCount"], 3);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_cli_prepares_repeatable_candidate_cut_and_advances_one_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(
        &scopes,
        &[
            scope("scope", "arbitrary"),
            scope("unselected", "arbitrary"),
        ],
    );
    let mut semantic = complete_fact("semantic", "arbitrary", "scope");
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    jsonl(&facts, &[semantic]);
    let original = fs::read(&facts).unwrap();
    let receipt_bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &receipt_bytes).unwrap();
    let before = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(before["totals"]["maintenanceReadyCount"], 0);
    let prepare = |output: &Path, receipt_sha: &str| {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--scope-skills",
                scopes.to_str().unwrap(),
                "--program-facts",
                facts.to_str().unwrap(),
                "--prepare-operation-fact",
                "scope",
                "--operation-receipts-root",
                root.to_str().unwrap(),
                "--operation-receipt",
                "build.json",
                "--operation-receipt-sha256",
                receipt_sha,
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    let candidate = root.join("candidate.jsonl");
    let success = prepare(&candidate, &digest(&receipt_bytes));
    assert!(
        success.status.success(),
        "{}",
        String::from_utf8_lossy(&success.stderr)
    );
    assert_eq!(fs::read(&facts).unwrap(), original);
    assert_eq!(rows_from_file(&candidate).len(), 2);
    let parent = digest(&serde_json::to_vec(&before).unwrap());
    let after =
        assess_with_receipts(&scopes, Some(&candidate), 2, Some(&parent), Some(&root)).unwrap();
    assert_eq!(after["totals"]["semanticReadyCount"], 1);
    assert_eq!(after["totals"]["maintenanceReadyCount"], 1);
    assert_eq!(after["automaticPromotion"], false);
    let selected = vec!["scope".to_owned()];
    let before_bytes = serde_json::to_vec(&before).unwrap();
    let after_bytes = serde_json::to_vec(&after).unwrap();
    let result = agentlab_code_analysis::maintainer_operation_evidence::compare_round(
        &before_bytes,
        &after_bytes,
        &selected,
    )
    .unwrap();
    assert_eq!(result["decision"], "review-proposed-operation-knowledge");
    assert_eq!(result["maintenanceReadyDelta"], 1);
    let base = root.join("base");
    fs::create_dir(&base).unwrap();
    fs::create_dir(base.join("assessments")).unwrap();
    fs::copy(&scopes, base.join("maintainer_scope_skills.jsonl")).unwrap();
    fs::copy(&facts, base.join("program_facts.jsonl")).unwrap();
    jsonl(
        &base.join("maintainer_skills.jsonl"),
        &[json!({"id":"process"})],
    );
    jsonl(&base.join("evaluation_cases.jsonl"), &[]);
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &[json!({
            "id":"parent", "roundIndex":4, "coverage":{"trackedFileCount":2},
            "assessment":{"path":"assessments/parent.json","sha256":digest(&before_bytes)}
        })],
    );
    fs::write(base.join("maintainer-knowledge-cut.json"), b"{}\n").unwrap();
    fs::write(base.join("assessments/parent.json"), &before_bytes).unwrap();
    let before_file = root.join("before.json");
    let after_file = root.join("after.json");
    fs::write(&before_file, &before_bytes).unwrap();
    fs::write(&after_file, &after_bytes).unwrap();
    let stage = |output: &Path, candidate: &Path, after: &Path| {
        std::process::Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .args([
                "--stage-operation-round",
                "--base",
                base.to_str().unwrap(),
                "--program-facts",
                candidate.to_str().unwrap(),
                "--before",
                before_file.to_str().unwrap(),
                "--after",
                after.to_str().unwrap(),
                "--operation-receipts-root",
                root.to_str().unwrap(),
                "--selected-scope",
                "scope",
                "--run-id",
                "generic-run",
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    let staged = root.join("stage");
    let response = stage(&staged, &candidate, &after_file);
    assert!(
        response.status.success(),
        "{}",
        String::from_utf8_lossy(&response.stderr)
    );
    assert_eq!(
        fs::read(staged.join("program_facts.jsonl")).unwrap(),
        fs::read(&candidate).unwrap()
    );
    for table in [
        "maintainer_skills",
        "maintainer_scope_skills",
        "evaluation_cases",
    ] {
        assert_eq!(
            fs::read(staged.join(format!("{table}.jsonl"))).unwrap(),
            fs::read(base.join(format!("{table}.jsonl"))).unwrap()
        );
    }
    let rounds = rows_from_file(&staged.join("maintainer_skill_refresh_rounds.jsonl"));
    assert_eq!(rounds.len(), 2);
    assert_eq!(
        rounds.iter().find(|r| r["roundIndex"] == 5).unwrap()["automaticPromotion"],
        false
    );
    assert!(!stage(&staged, &candidate, &after_file).status.success());
    let operation = rows_from_file(&candidate)
        .into_iter()
        .find(|row| row["dimensions"] == json!(["operation"]))
        .unwrap();
    let portable_root = staged.join("operation-evidence");
    assert_eq!(
        fs::read(portable_root.join("build.json")).unwrap(),
        receipt_bytes
    );
    fs::remove_file(root.join("build.json")).unwrap();
    assert!(
        agentlab_code_analysis::maintainer_operation_evidence::verify(
            &operation,
            &scope("scope", "arbitrary"),
            &portable_root
        )
        .is_ok()
    );
    fs::write(portable_root.join("build.json"), b"tampered").unwrap();
    assert!(
        agentlab_code_analysis::maintainer_operation_evidence::verify(
            &operation,
            &scope("scope", "arbitrary"),
            &portable_root
        )
        .is_err()
    );
    fs::write(portable_root.join("build.json"), &receipt_bytes).unwrap();
    fs::write(root.join("build.json"), &receipt_bytes).unwrap();
    let forged = root.join("forged.json");
    let mut forged_report = after.clone();
    forged_report["nextRoundObjectives"] = json!([]);
    fs::write(&forged, serde_json::to_vec(&forged_report).unwrap()).unwrap();
    let rejected_stage = root.join("rejected-stage");
    assert!(!stage(&rejected_stage, &candidate, &forged).status.success());
    assert!(!rejected_stage.exists());
    let mut legacy_parent = before.clone();
    legacy_parent["standard"]["operationEvidencePolicy"] = json!("legacy-explicit-claim");
    let legacy_bytes = serde_json::to_vec(&legacy_parent).unwrap();
    fs::write(base.join("assessments/parent.json"), &legacy_bytes).unwrap();
    let mut parent_rows = rows_from_file(&base.join("maintainer_skill_refresh_rounds.jsonl"));
    parent_rows[0]["assessment"]["sha256"] = json!(digest(&legacy_bytes));
    jsonl(
        &base.join("maintainer_skill_refresh_rounds.jsonl"),
        &parent_rows,
    );
    assert!(!stage(&rejected_stage, &candidate, &after_file)
        .status
        .success());
    assert!(!rejected_stage.exists());
    agentlab_code_analysis::maintainer_operation_stage::stage(
        &base,
        &candidate,
        &before_file,
        &after_file,
        &root,
        &selected,
        "explicit-rebaseline",
        true,
        &rejected_stage,
    )
    .unwrap();
    let migrated = rows_from_file(&rejected_stage.join("maintainer_skill_refresh_rounds.jsonl"));
    let latest = migrated.iter().find(|row| row["roundIndex"] == 5).unwrap();
    assert_eq!(latest["baselineReassessment"]["performed"], true);
    assert_eq!(
        latest["baselineReassessment"]["countsAsMaturityGain"],
        false
    );
    let changed_facts = root.join("changed-facts.jsonl");
    let mut changed = rows_from_file(&candidate);
    let semantic = changed.iter_mut().find(|r| r["id"] == "semantic").unwrap();
    semantic["interpretation"] = json!("unrelated semantic mutation");
    jsonl(&changed_facts, &changed);
    assert!(!stage(&rejected_stage, &changed_facts, &after_file)
        .status
        .success());
    assert_eq!(fs::read(&facts).unwrap(), original);
    for (pointer, value) in [
        ("/parentAssessmentSha256", json!("0".repeat(64))),
        ("/roundIndex", json!(7)),
        (
            "/standard/operationEvidencePolicy",
            json!("legacy-explicit-claim"),
        ),
        ("/totals/semanticReadyCount", json!(2)),
        ("/totals/maintenanceReadyCount", json!(2)),
        ("/inputs/scopeSkillsSha256", json!("0".repeat(64))),
        ("/skills/0/sourceRevision", json!("9".repeat(40))),
        ("/skills/1/maturity", json!("L3-maintenance-ready")),
    ] {
        let mut invalid = after.clone();
        *invalid.pointer_mut(pointer).unwrap() = value;
        assert!(
            agentlab_code_analysis::maintainer_operation_evidence::compare_round(
                &before_bytes,
                &serde_json::to_vec(&invalid).unwrap(),
                &selected
            )
            .is_err(),
            "{pointer}"
        );
    }
    let no_change = assess_with_receipts(
        &scopes,
        Some(&candidate),
        3,
        Some(&digest(&after_bytes)),
        Some(&root),
    )
    .unwrap();
    let replay_result = agentlab_code_analysis::maintainer_operation_evidence::compare_round(
        &after_bytes,
        &serde_json::to_vec(&no_change).unwrap(),
        &selected,
    )
    .unwrap();
    assert_eq!(replay_result["decision"], "no-change");
    assert_eq!(replay_result["maintenanceReadyDelta"], 0);
    let replay = root.join("replay.jsonl");
    assert!(prepare(&replay, &digest(&receipt_bytes)).status.success());
    assert_eq!(fs::read(&candidate).unwrap(), fs::read(&replay).unwrap());
    assert!(!prepare(&candidate, &digest(&receipt_bytes))
        .status
        .success());
    let rejected = root.join("rejected.jsonl");
    assert!(!prepare(&rejected, &"0".repeat(64)).status.success());
    assert!(!rejected.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_operation_receipts_close_only_content_verified_build_gaps() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary")]);
    let mut fact = complete_fact("fact", "arbitrary", "scope");
    jsonl(&facts, &[fact.clone()]);
    let unverified = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(unverified["skills"][0]["maturity"], "L2-semantic-ready");
    assert_eq!(
        unverified["gapCounts"]["MS-OPERATION-RECEIPT-UNVERIFIED"],
        1
    );
    let bytes = serde_json::to_vec(&build_receipt()).unwrap();
    fs::write(root.join("build.json"), &bytes).unwrap();
    fact["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
    jsonl(&facts, &[fact.clone()]);
    let verified = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(verified["skills"][0]["maturity"], "L3-maintenance-ready");
    assert_eq!(
        verified["standard"]["operationEvidencePolicy"],
        "verified-receipt-content"
    );
    assert_eq!(
        verified["skills"][0]["operationEvidenceChecks"]["fact"]["typeChecking"],
        "not-qualified"
    );
    assert_eq!(
        verified["skills"][0]["operationEvidenceChecks"]["fact"]["qualificationScope"]["runtime"],
        false
    );
    assert_eq!(
        verified,
        assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap()
    );
    fact["operationEvidence"]["sha256"] = json!("e".repeat(64));
    jsonl(&facts, &[fact]);
    let tampered = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
    assert_eq!(tampered["skills"][0]["maturity"], "L2-semantic-ready");
    assert_eq!(
        tampered["skills"][0]["operationEvidenceChecks"]["fact"]["reason"],
        "operation receipt digest mismatch"
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_receipt_rejects_failed_stale_borrowed_and_overclaimed_operations() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary")]);
    for (pointer, value) in [
        ("/status", json!("blocked")),
        ("/schema", json!("unsupported-runtime-schema")),
        ("/source/revision", json!("9".repeat(40))),
        ("/source/repositoryId", json!("another-repository")),
        ("/source/cleanAfter", json!(false)),
        ("/scope/scopeSkillIds", json!(["sibling"])),
        ("/scope/lane", json!("runtime")),
        ("/toolchain/sdkRelease", Value::Null),
        ("/dependencyPreparation/exitCode", json!(1)),
        ("/build/attempts/1/exitCode", json!(1)),
        (
            "/build/attempts/1/executionAuthority/operationId",
            json!("run-one"),
        ),
        (
            "/build/attempts/1/canonicalMemberSha256",
            json!("f".repeat(64)),
        ),
        ("/build/rawArchiveReproducible", json!(false)),
        ("/qualificationScope/runtime", json!(true)),
        ("/qualificationScope/tests", json!(true)),
        ("/qualificationScope/performance", json!(true)),
        ("/limitations", json!([])),
    ] {
        let mut receipt = build_receipt();
        *receipt.pointer_mut(pointer).unwrap() = value;
        let bytes = serde_json::to_vec(&receipt).unwrap();
        fs::write(root.join("build.json"), &bytes).unwrap();
        let mut fact = complete_fact("fact", "arbitrary", "scope");
        fact["operationEvidence"] = json!({"path":"build.json","sha256":digest(&bytes)});
        jsonl(&facts, &[fact]);
        let report = assess_with_receipts(&scopes, Some(&facts), 1, None, Some(&root)).unwrap();
        assert_eq!(
            report["skills"][0]["maturity"], "L2-semantic-ready",
            "{pointer}"
        );
        assert_eq!(
            report["skills"][0]["operationEvidenceChecks"]["fact"]["status"], "rejected",
            "{pointer}"
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn strict_receipt_rejects_traversal_missing_files_and_symlinks() {
    let root = temp_root();
    let skill = scope("scope", "arbitrary");
    for path in ["../outside.json", "/absolute.json", "missing.json"] {
        let mut fact = complete_fact("fact", "arbitrary", "scope");
        fact["operationEvidence"] = json!({"path":path,"sha256":"a".repeat(64)});
        assert!(
            agentlab_code_analysis::maintainer_operation_evidence::verify(&fact, &skill, &root)
                .is_err()
        );
    }
    #[cfg(unix)]
    {
        fs::write(
            root.join("real.json"),
            serde_json::to_vec(&build_receipt()).unwrap(),
        )
        .unwrap();
        std::os::unix::fs::symlink(root.join("real.json"), root.join("link.json")).unwrap();
        let mut fact = complete_fact("fact", "arbitrary", "scope");
        fact["operationEvidence"] = json!({"path":"link.json","sha256":"a".repeat(64)});
        assert!(
            agentlab_code_analysis::maintainer_operation_evidence::verify(&fact, &skill, &root)
                .unwrap_err()
                .contains("symlink")
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn stale_or_missing_source_identity_cannot_advance_any_dimension() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    for revision in [json!("9".repeat(40)), Value::Null, json!("main")] {
        let mut fact = complete_fact("fact", "arbitrary-repository", "scope");
        fact["sourceRevision"] = revision;
        jsonl(&facts, &[fact]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["totals"]["programBoundCount"], 0);
        assert_eq!(report["totals"]["semanticReadyCount"], 0);
        assert_eq!(report["totals"]["maintenanceReadyCount"], 0);
        assert_eq!(report["skills"][0]["provenDimensions"], json!([]));
        assert_eq!(
            report["skills"][0]["rejectedEvidenceBindings"][0]["reason"],
            "source-revision-mismatch"
        );
        assert_eq!(report["gapCounts"]["MS-EVIDENCE-IDENTITY-MISMATCH"], 1);
    }
    jsonl(
        &facts,
        &[complete_fact("fact", "arbitrary-repository", "scope")],
    );
    let refreshed = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(refreshed["decision"], "ready");
    assert_eq!(
        refreshed["skills"][0]["rejectedEvidenceBindings"],
        json!([])
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn inherited_cross_repository_or_stale_facts_are_not_semantic_proof() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    let mut anchor = complete_fact("anchor", "arbitrary-repository", "scope");
    anchor["dimensions"] = json!(["boundary"]);
    for (repository, revision) in [
        ("different-repository", "1".repeat(40)),
        ("arbitrary-repository", "9".repeat(40)),
    ] {
        let mut inherited = complete_fact("inherited", repository, "scope");
        inherited["sourceRevision"] = json!(revision);
        inherited["scopeSkillIds"] = json!([]);
        inherited["evidence"] = json!([]);
        inherited["evidenceFactIds"] = json!(["anchor"]);
        jsonl(&facts, &[anchor.clone(), inherited]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["totals"]["semanticReadyCount"], 0);
        assert_eq!(
            report["skills"][0]["evidenceBindings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            report["skills"][0]["rejectedEvidenceBindings"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn implicit_operation_binding_never_qualifies_a_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("scope", "arbitrary-repository")]);
    let mut semantic = complete_fact("semantic", "arbitrary-repository", "scope");
    semantic["dimensions"] = json!(["responsibility", "boundary", "relations", "behavior"]);
    for inherit in [false, true] {
        let mut operation = complete_fact("operation", "arbitrary-repository", "scope");
        operation["dimensions"] = json!(["operation"]);
        operation["scopeSkillIds"] = json!([]);
        if inherit {
            operation["evidence"] = json!([]);
            operation["evidenceFactIds"] = json!(["semantic"]);
        }
        jsonl(&facts, &[semantic.clone(), operation.clone()]);
        let report = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(report["skills"][0]["maturity"], "L2-semantic-ready");
        let binding = report["skills"][0]["evidenceBindings"]
            .as_array()
            .unwrap()
            .iter()
            .find(|row| row["factId"] == "operation")
            .unwrap();
        assert_eq!(binding["dimensions"], json!([]));
        operation["scopeSkillIds"] = json!(["scope"]);
        jsonl(&facts, &[semantic.clone(), operation]);
        let qualified = assess(&scopes, Some(&facts), 1, None).unwrap();
        assert_eq!(qualified["skills"][0]["maturity"], "L3-maintenance-ready");
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn generic_evidence_rounds_advance_arbitrary_repositories_without_name_rules() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(
        &scopes,
        &[
            scope("skill-scope-alpha-src", "alpha-library"),
            scope("skill-scope-beta-src", "beta-service"),
        ],
    );

    let first = assess(&scopes, None, 1, None).unwrap();
    assert_eq!(first["decision"], "continue");
    assert_eq!(first["totals"]["structuralReadyCount"], 2);
    assert_eq!(first["totals"]["programBoundCount"], 0);
    assert_eq!(first["totals"]["semanticReadyCount"], 0);
    assert_eq!(first["totals"]["maintenanceReadyCount"], 0);

    jsonl(
        &facts,
        &[
            complete_fact(
                "fact-alpha-contract",
                "alpha-library",
                "skill-scope-alpha-src",
            ),
            complete_fact("fact-beta-contract", "beta-service", "skill-scope-beta-src"),
        ],
    );
    let first_bytes = serde_json::to_vec_pretty(&first).unwrap();
    let parent = digest(&first_bytes);
    let second = assess(&scopes, Some(&facts), 2, Some(&parent)).unwrap();
    assert_eq!(second["decision"], "ready");
    assert_eq!(second["totals"]["programBoundCount"], 2);
    assert_eq!(second["totals"]["semanticReadyCount"], 2);
    assert_eq!(second["totals"]["maintenanceReadyCount"], 2);
    assert!(second["repositories"]
        .as_array()
        .unwrap()
        .iter()
        .all(|repository| repository["readyForCaseGeneration"] == true));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn operation_maturity_requires_explicit_revision_bound_dimension() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("skill-scope-alpha-src", "alpha-library")]);
    jsonl(
        &facts,
        &[
            json!({
                "id":"fact-alpha-semantic",
                "kind":"semantic-contract",
                "repositoryId":"alpha-library",
                "sourceRevision":"1".repeat(40),
                "scopeSkillIds":["skill-scope-alpha-src"],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/main.generic","gitBlobOid":"3".repeat(40)}]
            }),
            json!({
                "id":"fact-alpha-blocked-build-preflight",
                "kind":"build-test-entrypoint",
                "repositoryId":"alpha-library",
                "sourceRevision":"1".repeat(40),
                "scopeSkillIds":["skill-scope-alpha-src"],
                "evidence":[{"path":"qualification.json","sha256":"4".repeat(64)}]
            }),
        ],
    );
    let blocked = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(blocked["totals"]["semanticReadyCount"], 1);
    assert_eq!(blocked["totals"]["maintenanceReadyCount"], 0);
    assert_eq!(blocked["skills"][0]["maturity"], "L2-semantic-ready");
    assert!(blocked["skills"][0]["gaps"]
        .as_array()
        .unwrap()
        .iter()
        .any(|gap| gap["code"] == "MS-OPERATION-EVIDENCE-MISSING"));

    let mut rows = rows_from_file(&facts);
    rows.push(json!({
        "id":"verification-alpha-runtime",
        "kind":"runtime-verification",
        "repositoryId":"alpha-library",
        "sourceRevision":"1".repeat(40),
        "scopeSkillIds":["skill-scope-alpha-src"],
        "dimensions":["operation"],
        "evidence":[{"path":"qualified-runtime.json","sha256":"5".repeat(64)}]
    }));
    jsonl(&facts, &rows);
    let qualified = assess(&scopes, Some(&facts), 1, None).unwrap();
    assert_eq!(qualified["totals"]["maintenanceReadyCount"], 1);
    assert_eq!(qualified["skills"][0]["maturity"], "L3-maintenance-ready");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn composite_selectors_bind_exact_owned_paths_and_reject_shared_anchor_siblings() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    let mut one = scope("skill-scope-arbitrary-one", "arbitrary");
    one["ownershipSelectors"] = json!([
        {"type":"prefix","path":"src/one"},
        {"type":"files","paths":["src/root.generic"]}
    ]);
    one["evidence"] = json!([{"path":"src/one/main.generic","gitBlobOid":"3".repeat(40)}]);
    let mut two = scope("skill-scope-arbitrary-two", "arbitrary");
    two["ownershipSelectors"] = json!([{"type":"prefix","path":"src/two"}]);
    two["evidence"] = json!([{"path":"src/two/main.generic","gitBlobOid":"4".repeat(40)}]);
    jsonl(&scopes, &[one, two]);
    jsonl(
        &facts,
        &[
            json!({
                "id":"fact-one", "kind":"semantic-contract", "repositoryId":"arbitrary",
                "sourceRevision":"1".repeat(40), "scopeSkillIds":[],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/root.generic","gitBlobOid":"5".repeat(40)}]
            }),
            json!({
                "id":"fact-two", "kind":"semantic-contract", "repositoryId":"arbitrary",
                "sourceRevision":"1".repeat(40), "scopeSkillIds":[],
                "dimensions":["responsibility","boundary","relations","behavior"],
                "evidence":[{"path":"src/two/main.generic","gitBlobOid":"4".repeat(40)}]
            }),
        ],
    );
    let assessment = assess(&scopes, Some(&facts), 1, None).unwrap();
    let rows = assessment["skills"].as_array().unwrap();
    let first = rows
        .iter()
        .find(|row| row["skillId"] == "skill-scope-arbitrary-one")
        .unwrap();
    let second = rows
        .iter()
        .find(|row| row["skillId"] == "skill-scope-arbitrary-two")
        .unwrap();
    assert_eq!(first["checks"]["programEvidenceBound"], true);
    assert_eq!(second["checks"]["programEvidenceBound"], true);
    assert_eq!(first["evidenceBindings"][0]["factId"], "fact-one");
    assert_eq!(second["evidenceBindings"][0]["factId"], "fact-two");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn legacy_virtual_boundaries_retain_v1_identity_compatibility() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let mut legacy = scope("skill-scope-arbitrary-support", "arbitrary");
    legacy["pathBoundary"] = json!("src/_support");
    legacy["evidence"] = json!([{
        "path":"src/build-profile.json5", "gitBlobOid":"3".repeat(40)
    }]);
    jsonl(&scopes, &[legacy]);
    let assessment = assess(&scopes, None, 1, None).unwrap();
    assert_eq!(assessment["totals"]["structuralReadyCount"], 1);
    assert_eq!(assessment["skills"][0]["checks"]["identityReady"], true);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn explicit_fact_binding_cannot_name_a_missing_or_cross_repository_scope() {
    let root = temp_root();
    let scopes = root.join("scopes.jsonl");
    let facts = root.join("facts.jsonl");
    jsonl(&scopes, &[scope("skill-scope-alpha-src", "alpha-library")]);
    jsonl(
        &facts,
        &[complete_fact(
            "fact-beta-contract",
            "beta-service",
            "skill-scope-alpha-src",
        )],
    );
    let error = assess(&scopes, Some(&facts), 1, None).unwrap_err();
    assert!(error.contains("crosses repository boundary"));
    fs::remove_dir_all(root).unwrap();
}
