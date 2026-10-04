#![cfg(unix)]
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn git(root: &Path, args: &[&str]) -> String {
    let r = Command::new("git")
        .current_dir(root)
        .args(args)
        .output()
        .unwrap();
    assert!(r.status.success(), "{}", String::from_utf8_lossy(&r.stderr));
    String::from_utf8(r.stdout).unwrap().trim().into()
}
fn run(root: &Path, contract: &Value, label: &str) -> (bool, Value) {
    let input = root.join(format!("{label}.contract.json"));
    let output = root.join(format!("{label}.result.json"));
    fs::write(&input, serde_json::to_vec(contract).unwrap()).unwrap();
    let r = Command::new("node")
        .arg(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../scripts/calibrate-harmony-stage-controls.cjs"),
        )
        .arg("--contract")
        .arg(input)
        .arg("--source-repo")
        .arg(root)
        .arg("--output")
        .arg(&output)
        .output()
        .unwrap();
    let result = fs::read(&output)
        .ok()
        .map(|b| serde_json::from_slice(&b).unwrap())
        .unwrap_or(Value::Null);
    (r.status.success(), result)
}
#[test]
fn actual_stage_methods_discriminate_semantic_mutations_without_repository_constants() {
    for repository in ["arbitrary-owner-one", "different-owner-two"] {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "{repository}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(root.join("src/owner")).unwrap();
        fs::write(
            root.join("src/module.json5"),
            r#"{"module":{"srcEntry":"./owner/Owner.js"}}"#,
        )
        .unwrap();
        let code = r#"const {AbilityStage}=require('@kit.AbilityKit');exports.default=class Owner extends AbilityStage {
          onCreate(){console.info('created');let envCallback={onConfigurationUpdated(config){console.info('config: '+JSON.stringify(config));}};
          let app=this.context.getApplicationContext();let id=app.on('environment', envCallback);console.info('id: '+id);}
          onDestroy(){console.info('destroyed');}}
        "#;
        fs::write(root.join("src/owner/Owner.js"), code).unwrap();
        fs::write(root.join("src/owner/Alternate.js"), "const {AbilityStage}=require('@kit.AbilityKit');exports.default=class Alternate extends AbilityStage {};").unwrap();
        git(&root, &["init"]);
        git(&root, &["config", "user.name", "Fixture"]);
        git(&root, &["config", "user.email", "fixture@example.invalid"]);
        git(&root, &["add", "src"]);
        git(&root, &["commit", "-m", "stage fixture"]);
        let mut c = json!({"schema":"agentlab.harmony_stage_control_contract.v1","reviewed":true,
            "sourceRevision":git(&root,&["rev-parse","HEAD"]),"modulePath":"src/module.json5",
            "createMarker":"created","destroyMarker":"destroyed","registrationMarker":"id: ","configurationPrefix":"config: ","eventName":"environment",
            "configurations":[{"id":"initial","language":"en-US","colorMode":0},{"id":"language","language":"zh-CN","colorMode":0},{"id":"color","language":"zh-CN","colorMode":1}],
            "variants":[{"id":"entry","path":"src/module.json5","from":"./owner/Owner.js","to":"./owner/Alternate.js","expectedFailedChecks":["stage-created","language","color"]},
                {"id":"event","path":"src/owner/Owner.js","from":".on('environment', envCallback)","to":".on('typo', envCallback)","expectedFailedChecks":["application-environment-registration","language","color"]}]});
        let candidate = json!({"id":repository,"repositoryId":repository,"sourceRevision":c["sourceRevision"],
            "contextPaths":["src/module.json5"],"editablePaths":["src/owner/Owner.js"],
            "sourceSetSha256":"a".repeat(64),"knowledgeCutSha256":"b".repeat(64)});
        let candidate_sha =
            agentlab_code_analysis::digest(&serde_json::to_vec(&candidate).unwrap());
        c["candidateId"] = candidate["id"].clone();
        c["candidateSha256"] = json!(candidate_sha);
        let downstream = json!({"schema":"agentlab.maintainer_downstream_plan.v1","candidateId":repository,
            "candidateSha256":candidate_sha,"sourceRevision":candidate["sourceRevision"],"automaticPromotion":false,
            "sourceSetSha256":candidate["sourceSetSha256"],"knowledgeCutSha256":candidate["knowledgeCutSha256"],
            "actions":[{"id":"exact-runtime","kind":"qualify-exact-runtime-requirement","executionAuthorized":false}]});
        let consume = |contract: &Value, receipt: &Value, previous: Option<&[u8]>| {
            let bytes = serde_json::to_vec(receipt).unwrap();
            agentlab_code_analysis::maintainer_stage_feedback::plan(
                &serde_json::to_vec(&candidate).unwrap(),
                &serde_json::to_vec(&downstream).unwrap(),
                &serde_json::to_vec(contract).unwrap(),
                &bytes,
                &agentlab_code_analysis::digest(&bytes),
                previous,
            )
        };
        let (ok, r) = run(&root, &c, "actual");
        assert!(ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], true);
        assert_eq!(r["qualified"], false);
        assert_eq!(r["controls"][0]["verdict"], "accept");
        for control in r["controls"].as_array().unwrap().iter().skip(1) {
            assert_eq!(control["verdict"], "reject");
            assert_eq!(control["intendedFailureObserved"], true);
        }
        let first = consume(&c, &r, None).unwrap();
        // Retained-source replay uses the same bytes, without a Git fetch or a
        // rewritten commit identity. Unreviewed diagnostics cannot be admitted.
        let mut inventory = json!({"sources":[]});
        for file in [
            "src/module.json5",
            "src/owner/Owner.js",
            "src/owner/Alternate.js",
        ] {
            let bytes = fs::read(root.join(file)).unwrap();
            inventory["sources"].as_array_mut().unwrap().push(json!({
                "repositoryId":repository,"revision":c["sourceRevision"],"path":file,
                "workspacePath":file,"bytes":bytes.len(),
                "sha256":agentlab_code_analysis::digest(&bytes),
                "gitBlobOid":git(&root,&["hash-object",file])}));
        }
        let draft_path = root.join("diagnostic-draft.json");
        let mut draft = c.clone();
        draft["reviewed"] = json!(false);
        fs::write(&draft_path, serde_json::to_vec(&draft).unwrap()).unwrap();
        let binding_path = root.join("source-binding.json");
        let replay = |binding: &Value, label: &str, diagnostic: bool| {
            fs::write(&binding_path, serde_json::to_vec(binding).unwrap()).unwrap();
            let output = root.join(format!("{label}.replay.json"));
            let mut cmd = Command::new("node");
            cmd.arg(
                Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("../../scripts/calibrate-harmony-stage-controls.cjs"),
            )
            .arg("--contract")
            .arg(&draft_path)
            .arg("--source-binding")
            .arg(&binding_path)
            .arg("--source-workspace")
            .arg(&root)
            .arg("--output")
            .arg(&output);
            if diagnostic {
                cmd.arg("--diagnostic-unreviewed");
            }
            let status = cmd.output().unwrap();
            let receipt = fs::read(&output)
                .ok()
                .map(|b| serde_json::from_slice::<Value>(&b).unwrap());
            (status.status.success(), receipt)
        };
        let (ok, diagnostic) = replay(&inventory, "retained", true);
        assert!(ok);
        let diagnostic = diagnostic.unwrap();
        assert_eq!(diagnostic["semanticSeamCalibrationPassed"], true);
        assert_eq!(diagnostic["diagnosticOnly"], true);
        assert_eq!(diagnostic["contractReviewed"], false);
        assert_eq!(diagnostic["sourceAuthority"]["verifiedFiles"], 3);
        assert_eq!(
            diagnostic["sourceAuthority"]["revisionAuthenticated"],
            false
        );
        assert!(consume(&draft, &diagnostic, None).is_err());
        let mut disguised = r.clone();
        disguised["diagnosticOnly"] = json!(true);
        assert!(consume(&c, &disguised, None)
            .unwrap_err()
            .contains("diagnostic cannot enter"));
        assert!(!replay(&inventory, "no-explicit-diagnostic", false).0);
        for (index, pointer, value) in [
            (0, "/sources/0/revision", json!("0".repeat(40))),
            (1, "/sources/0/sha256", json!("0".repeat(64))),
            (2, "/sources/0/gitBlobOid", json!("0".repeat(40))),
            (3, "/sources/0/bytes", json!(1)),
            (4, "/sources/0/workspacePath", json!("../outside")),
        ] {
            let mut changed = inventory.clone();
            *changed.pointer_mut(pointer).unwrap() = value;
            assert!(!replay(&changed, &format!("binding-drift-{index}"), true).0);
        }
        let mut duplicate_inventory = inventory.clone();
        duplicate_inventory["sources"]
            .as_array_mut()
            .unwrap()
            .push(inventory["sources"][0].clone());
        assert!(!replay(&duplicate_inventory, "duplicate-binding", true).0);
        std::os::unix::fs::symlink(
            root.join("src/module.json5"),
            root.join("source-link.json5"),
        )
        .unwrap();
        let mut symlink_inventory = inventory.clone();
        symlink_inventory["sources"][0]["workspacePath"] = json!("source-link.json5");
        assert!(!replay(&symlink_inventory, "symlink-binding", true).0);
        let make_assets = |contract: &Value, receipt: &Value| {
            let bytes = serde_json::to_vec(receipt).unwrap();
            agentlab_code_analysis::maintainer_stage_feedback::assets(
                &serde_json::to_vec(&candidate).unwrap(),
                &serde_json::to_vec(&downstream).unwrap(),
                &serde_json::to_vec(contract).unwrap(),
                &bytes,
                &agentlab_code_analysis::digest(&bytes),
            )
        };
        let assets = make_assets(&c, &r).unwrap();
        assert_eq!(assets, make_assets(&c, &r).unwrap());
        assert_eq!(assets["calibration_controls"].len(), 3);
        assert_eq!(assets["evidence_files"].len(), 5);
        assert_eq!(assets["runs"].values().next().unwrap()["qualified"], false);
        assert!(assets["phase_failures"].is_empty());
        let review = json!({"schema":"agentlab.stage_lesson_review.v1","reviewed":true,
            "id":format!("lesson-{repository}"),"scope":"recorded-application-context-stage-seam",
            "reviewerId":"fixture-maintenance-review",
            "candidateSha256":first["candidateSha256"],"sourceRevision":first["sourceRevision"],
            "knowledgeCutSha256":first["knowledgeCutSha256"],"contractSha256":first["contractSha256"],
            "calibrationSha256":first["calibrationSha256"],
            "phenomenon":"Creation and registration must be separately observed",
            "cause":"Wrong entry or event severs the modeled configuration delivery path",
            "change":"Check actual source creation and application-context registration independently",
            "factId":format!("fact-{repository}"),"skillId":format!("skill-{repository}"),
            "body":"Execute positive and wrong-entry/wrong-event controls; qualify framework delivery separately."});
        let lesson_assets = |review: &Value, capture: &Value| {
            let raw = serde_json::to_vec(capture).unwrap();
            agentlab_code_analysis::maintainer_stage_feedback::lesson_assets(
                &serde_json::to_vec(&candidate).unwrap(),
                &serde_json::to_vec(&downstream).unwrap(),
                &serde_json::to_vec(&c).unwrap(),
                &raw,
                &agentlab_code_analysis::digest(&raw),
                &serde_json::to_vec(review).unwrap(),
            )
        };
        let lesson = lesson_assets(&review, &r).unwrap();
        assert_eq!(lesson, lesson_assets(&review, &r).unwrap());
        let row = lesson["experiment_lessons"].values().next().unwrap();
        assert_eq!(row["status"], "verified");
        assert_eq!(row["automaticPromotion"], false);
        assert_eq!(
            row["promotionContract"]["qualification"]["harmonyRuntimeQualified"],
            false
        );
        assert_eq!(lesson["evidence_files"].len(), 6);
        let mut stale = review.clone();
        stale["contractSha256"] = json!("e".repeat(64));
        assert!(lesson_assets(&stale, &r).is_err());
        let mut unreviewed = review.clone();
        unreviewed["reviewed"] = json!(false);
        assert!(lesson_assets(&unreviewed, &r).is_err());
        // Exercise the public CLI, not only the in-memory normalizer.
        let candidates_path = root.join("candidates.jsonl");
        let downstream_path = root.join("downstream.json");
        fs::write(&candidates_path, serde_json::to_vec(&candidate).unwrap()).unwrap();
        fs::write(&downstream_path, serde_json::to_vec(&downstream).unwrap()).unwrap();
        let raw_capture = fs::read(root.join("actual.result.json")).unwrap();
        let export_cli = |output: &Path, capture: &Path, sha: &str| {
            Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
                .arg("--export-stage-calibration")
                .arg("--candidates")
                .arg(&candidates_path)
                .arg("--candidate-id")
                .arg(repository)
                .arg("--downstream-plan")
                .arg(&downstream_path)
                .arg("--stage-contract")
                .arg(root.join("actual.contract.json"))
                .arg("--stage-calibration")
                .arg(capture)
                .arg("--calibration-sha256")
                .arg(sha)
                .arg("--output")
                .arg(output)
                .output()
                .unwrap()
        };
        let export_a = root.join("export-a");
        let export_b = root.join("export-b");
        let capture_path = root.join("actual.result.json");
        let raw_sha = agentlab_code_analysis::digest(&raw_capture);
        for output in [&export_a, &export_b] {
            let result = export_cli(output, &capture_path, &raw_sha);
            assert!(
                result.status.success(),
                "{}",
                String::from_utf8_lossy(&result.stderr)
            );
            let manifest: Value =
                serde_json::from_slice(&fs::read(output.join("export.json")).unwrap()).unwrap();
            assert_eq!(manifest["schema"], "agentlab.asset_exchange.v1");
            assert_eq!(manifest["assetClass"], "evaluation-instance");
            assert_eq!(
                manifest["tables"]["phase_failures"]["definition"]["fields"]["record"]["type"],
                "object"
            );
            assert_eq!(
                manifest["tables"]["calibration_controls"]["definition"]["fields"]
                    ["intendedFailureObserved"]["type"],
                "boolean"
            );
            for (name, meta) in manifest["tables"].as_object().unwrap() {
                let raw = fs::read(output.join(format!("{name}.jsonl"))).unwrap();
                assert_eq!(agentlab_code_analysis::digest(&raw), meta["sha256"]);
                assert_eq!(
                    raw.split(|b| *b == b'\n')
                        .filter(|line| !line.is_empty())
                        .count(),
                    meta["rowCount"].as_u64().unwrap() as usize
                );
            }
            let evidence = fs::read_to_string(output.join("evidence_files.jsonl")).unwrap();
            for line in evidence.lines() {
                let row: Value = serde_json::from_str(line).unwrap();
                let raw = fs::read(output.join(row["path"].as_str().unwrap())).unwrap();
                assert_eq!(agentlab_code_analysis::digest(&raw), row["sha256"]);
                assert_eq!(raw.len() as u64, row["bytes"].as_u64().unwrap());
            }
            assert_eq!(
                fs::read(output.join("stage-calibration.json")).unwrap(),
                raw_capture
            );
        }
        for entry in fs::read_dir(&export_a).unwrap() {
            let name = entry.unwrap().file_name();
            assert_eq!(
                fs::read(export_a.join(&name)).unwrap(),
                fs::read(export_b.join(&name)).unwrap()
            );
        }
        let before = fs::read(export_a.join("export.json")).unwrap();
        assert!(!export_cli(&export_a, &capture_path, &raw_sha)
            .status
            .success());
        assert_eq!(before, fs::read(export_a.join("export.json")).unwrap());
        let rejected = root.join("rejected-export");
        assert!(!export_cli(&rejected, &capture_path, &"0".repeat(64))
            .status
            .success());
        assert!(!rejected.exists());
        let mut cli_review = review.clone();
        cli_review["calibrationSha256"] = json!(raw_sha);
        let review_path = root.join("lesson-review.json");
        fs::write(&review_path, serde_json::to_vec(&cli_review).unwrap()).unwrap();
        let lesson_output = root.join("lesson-export");
        let result = Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--export-stage-lesson")
            .arg("--candidates")
            .arg(&candidates_path)
            .arg("--candidate-id")
            .arg(repository)
            .arg("--downstream-plan")
            .arg(&downstream_path)
            .arg("--stage-contract")
            .arg(root.join("actual.contract.json"))
            .arg("--stage-calibration")
            .arg(&capture_path)
            .arg("--calibration-sha256")
            .arg(&raw_sha)
            .arg("--lesson-review")
            .arg(&review_path)
            .arg("--output")
            .arg(&lesson_output)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(
            fs::read(lesson_output.join("lesson-review.json")).unwrap(),
            fs::read(&review_path).unwrap()
        );
        let manifest: Value =
            serde_json::from_slice(&fs::read(lesson_output.join("export.json")).unwrap()).unwrap();
        assert_eq!(manifest["tables"]["experiment_lessons"]["rowCount"], 1);
        assert_eq!(manifest["tables"]["evidence_files"]["rowCount"], 6);
        // The existing experience producer consumes the same lesson entities.
        let knowledge = root.join("empty-knowledge");
        fs::create_dir(&knowledge).unwrap();
        for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
            fs::write(knowledge.join(format!("{name}.jsonl")), b"").unwrap();
        }
        let promoted = root.join("promotion-candidate");
        let result = Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
            .arg("promote")
            .arg(&lesson_output)
            .arg(&knowledge)
            .arg(&promoted)
            .arg(review["id"].as_str().unwrap())
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let fact: Value =
            serde_json::from_slice(&fs::read(promoted.join("program_facts.jsonl")).unwrap())
                .unwrap();
        let skill: Value =
            serde_json::from_slice(&fs::read(promoted.join("maintainer_skills.jsonl")).unwrap())
                .unwrap();
        assert_eq!(fact["sourceLessonId"], review["id"]);
        assert_eq!(fact["qualification"]["caseQualified"], false);
        assert_eq!(skill["body"], review["body"]);
        assert_eq!(skill["ownershipPlane"], "target-operations");
        assert_eq!(skill["automaticPromotion"], false);
        assert_eq!(skill["sourceRevision"], c["sourceRevision"]);
        assert_eq!(skill["repositoryId"], candidate["repositoryId"]);
        assert_eq!(fact["repositoryId"], candidate["repositoryId"]);
        assert_eq!(
            fs::read(promoted.join("evaluation_cases.jsonl")).unwrap(),
            b""
        );
        // A colliding target cannot silently replace accepted knowledge, even
        // when its payload happens to match this candidate.
        let collision_output = root.join("collision-candidate");
        let result = Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
            .arg("promote")
            .arg(&lesson_output)
            .arg(&promoted)
            .arg(&collision_output)
            .arg(review["id"].as_str().unwrap())
            .output()
            .unwrap();
        assert!(!result.status.success());
        assert!(!collision_output.exists());
        assert!(String::from_utf8_lossy(&result.stderr).contains("target already exists"));
        let lessons_path = lesson_output.join("experiment_lessons.jsonl");
        let original_lessons = fs::read(&lessons_path).unwrap();
        let validations_path = lesson_output.join("lesson_validations.jsonl");
        let original_validations = fs::read(&validations_path).unwrap();
        for mode in ["empty-validations", "borrowed-validation"] {
            if mode == "empty-validations" {
                let mut invalid: Value = serde_json::from_slice(&original_lessons).unwrap();
                invalid["validationIds"] = json!([]);
                fs::write(&lessons_path, serde_json::to_vec(&invalid).unwrap()).unwrap();
            } else {
                fs::write(&lessons_path, &original_lessons).unwrap();
                let mut invalid: Value = serde_json::from_slice(&original_validations).unwrap();
                invalid["lessonId"] = json!("another-lesson");
                fs::write(&validations_path, serde_json::to_vec(&invalid).unwrap()).unwrap();
            }
            let rejected = root.join(mode);
            let result = Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
                .arg("promote")
                .arg(&lesson_output)
                .arg(&knowledge)
                .arg(&rejected)
                .arg(review["id"].as_str().unwrap())
                .output()
                .unwrap();
            assert!(!result.status.success());
            assert!(!rejected.exists());
        }
        fs::write(&lessons_path, &original_lessons).unwrap();
        fs::write(&validations_path, &original_validations).unwrap();
        // Admission consumes a committed source export plus a hash-bound baseline.
        // Commit labels here are fixture metadata, not remote persistence evidence.
        let mut committed = manifest.clone();
        committed["repository"] = json!(format!("fixture-instance-{repository}"));
        committed["revision"] = json!("f".repeat(40));
        committed["tablePrefix"] = json!("data/");
        fs::write(
            lesson_output.join("export.json"),
            serde_json::to_vec(&committed).unwrap(),
        )
        .unwrap();
        let fenced = root.join("fenced-proposal");
        assert!(Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
            .env("GITHUB_SHA", "e".repeat(40))
            .arg("promote")
            .arg(&lesson_output)
            .arg(&knowledge)
            .arg(&fenced)
            .arg(review["id"].as_str().unwrap())
            .output()
            .unwrap()
            .status
            .success());
        let base = root.join("admission-baseline");
        fs::create_dir(&base).unwrap();
        let mut cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1",
            "automaticPromotion":false,
            "repositories":[{"id":candidate["repositoryId"],"revision":candidate["sourceRevision"]}],
            "tableGitAuthority":{"repo":format!("fixture-knowledge-{repository}"),"revision":"a".repeat(40)},"tables":{}});
        fs::write(base.join("source-set.txt"), b"retained fixture inventory\n").unwrap();
        cut["sourceSetSha256"] = json!(agentlab_code_analysis::digest(
            &fs::read(base.join("source-set.txt")).unwrap()
        ));
        let mut round = json!({"id":"initial","schema":"agentlab.maintainer_skill_refresh_round.v1",
            "roundIndex":1,"ownershipPlane":"target-operations","automaticPromotion":false,
            "coverage":{"processSkillCount":0,"semanticReadyScopeCount":0,"maintenanceReadyScopeCount":0},
            "assessment":{"path":"existing-assessment.json","sha256":"d".repeat(64)},"tables":{}});
        for (key, table) in [
            ("maintainerSkills", "maintainer_skills"),
            ("programFacts", "program_facts"),
            ("maintainerScopeSkills", "maintainer_scope_skills"),
            ("evaluationCases", "evaluation_cases"),
        ] {
            let bytes = if table == "maintainer_scope_skills" {
                serde_json::to_vec(&json!({"id":"fixture-scope","repositoryId":candidate["repositoryId"],"sourceRevision":candidate["sourceRevision"]})).unwrap()
            } else {
                Vec::new()
            };
            let hash = agentlab_code_analysis::digest(&bytes);
            fs::write(base.join(format!("{table}.jsonl")), &bytes).unwrap();
            cut["tables"][key] = json!({"path":format!("{table}.jsonl"),"sha256":hash});
            let field = match table {
                "maintainer_skills" => "processSkillsSha256",
                "program_facts" => "programFactsSha256",
                _ => "scopeSkillsSha256",
            };
            if table != "evaluation_cases" {
                round["tables"][field] = json!(hash);
            }
        }
        let history_bytes = serde_json::to_vec(&round).unwrap();
        fs::write(
            base.join("maintainer_skill_refresh_rounds.jsonl"),
            &history_bytes,
        )
        .unwrap();
        cut["tables"]["maintainerSkillRefreshRounds"] = json!({"path":"maintainer_skill_refresh_rounds.jsonl","sha256":agentlab_code_analysis::digest(&history_bytes)});
        fs::write(
            base.join("maintainer-knowledge-cut.json"),
            serde_json::to_vec(&cut).unwrap(),
        )
        .unwrap();
        let prepare = || {
            agentlab_code_analysis::maintainer_lesson_admission::prepare(
                &base,
                &fenced,
                &lesson_output,
                review["id"].as_str().unwrap(),
                &"a".repeat(40),
            )
        };
        let plan = prepare().unwrap();
        let plan_output = root.join("admission-plan.json");
        let admission_cli = || {
            Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
                .arg("--prepare-lesson-admission")
                .arg("--knowledge")
                .arg(&base)
                .arg("--proposal")
                .arg(&fenced)
                .arg("--lesson-source")
                .arg(&lesson_output)
                .arg("--lesson-id")
                .arg(review["id"].as_str().unwrap())
                .arg("--expected-knowledge-revision")
                .arg("a".repeat(40))
                .arg("--output")
                .arg(&plan_output)
                .output()
                .unwrap()
        };
        let result = admission_cli();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let plan_bytes = fs::read(&plan_output).unwrap();
        assert_eq!(serde_json::from_slice::<Value>(&plan_bytes).unwrap(), plan);
        assert!(!admission_cli().status.success());
        assert_eq!(fs::read(&plan_output).unwrap(), plan_bytes);
        assert_eq!(plan, prepare().unwrap());
        assert_eq!(
            plan["repository"],
            format!("fixture-knowledge-{repository}")
        );
        assert_eq!(plan["tables"].as_object().unwrap().len(), 3);
        let refresh = &plan["tables"]["maintainer_skill_refresh_rounds"]["row"];
        assert_eq!(refresh["roundIndex"], 2);
        assert_eq!(refresh["assessment"], round["assessment"]);
        assert_eq!(refresh["coverage"]["maintenanceReadyScopeCount"], 0);
        assert_eq!(refresh["coverage"]["processSkillCount"], 1);
        assert_eq!(refresh["countsAsMaturityGain"], false);
        assert!(
            agentlab_code_analysis::maintainer_lesson_admission::prepare(
                &base,
                &fenced,
                &lesson_output,
                review["id"].as_str().unwrap(),
                &"b".repeat(40)
            )
            .is_err()
        );
        let proposed_skill_path = fenced.join("maintainer_skills.jsonl");
        let original_skill = fs::read(&proposed_skill_path).unwrap();
        let mut bad_skill: Value = serde_json::from_slice(&original_skill).unwrap();
        bad_skill["body"] = json!("unreviewed guidance");
        fs::write(
            &proposed_skill_path,
            serde_json::to_vec(&bad_skill).unwrap(),
        )
        .unwrap();
        assert!(prepare().is_err());
        fs::write(&proposed_skill_path, &original_skill).unwrap();
        let mut false_lesson: Value = serde_json::from_slice(&original_lessons).unwrap();
        false_lesson["promotionContract"]["qualification"]["caseQualified"] = json!(true);
        fs::write(&lessons_path, serde_json::to_vec(&false_lesson).unwrap()).unwrap();
        assert!(prepare().is_err());
        fs::write(&lessons_path, &original_lessons).unwrap();
        // Full staging independently rebinds the assessment input hashes without
        // increasing readiness. Use a real scope shape, with fixture identities.
        let publication = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../examples/maintainer-knowledge-gate/first-four");
        let mut scope: Value = serde_json::from_str(
            fs::read_to_string(publication.join("maintainer_scope_skills.jsonl"))
                .unwrap()
                .lines()
                .next()
                .unwrap(),
        )
        .unwrap();
        scope["id"] = json!("fixture-scope");
        scope["repositoryId"] = candidate["repositoryId"].clone();
        scope["sourceRevision"] = candidate["sourceRevision"].clone();
        let scope_bytes = serde_json::to_vec(&scope).unwrap();
        fs::write(base.join("maintainer_scope_skills.jsonl"), &scope_bytes).unwrap();
        fs::create_dir(base.join("operation-evidence")).unwrap();
        fs::create_dir(base.join("assessments")).unwrap();
        let before = agentlab_code_analysis::maintainer_skill_flywheel::assess_with_receipts(
            &base.join("maintainer_scope_skills.jsonl"),
            Some(&base.join("program_facts.jsonl")),
            1,
            None,
            Some(&base.join("operation-evidence")),
        )
        .unwrap();
        let before_bytes = serde_json::to_vec(&before).unwrap();
        fs::write(base.join("assessments/before.json"), &before_bytes).unwrap();
        round["assessment"] = json!({"path":"assessments/before.json","sha256":agentlab_code_analysis::digest(&before_bytes)});
        round["tables"]["scopeSkillsSha256"] = json!(agentlab_code_analysis::digest(&scope_bytes));
        let round_bytes = serde_json::to_vec(&round).unwrap();
        fs::write(
            base.join("maintainer_skill_refresh_rounds.jsonl"),
            &round_bytes,
        )
        .unwrap();
        cut["tables"]["maintainerScopeSkills"]["sha256"] =
            json!(agentlab_code_analysis::digest(&scope_bytes));
        cut["tables"]["maintainerSkillRefreshRounds"]["sha256"] =
            json!(agentlab_code_analysis::digest(&round_bytes));
        fs::write(
            base.join("maintainer-knowledge-cut.json"),
            serde_json::to_vec(&cut).unwrap(),
        )
        .unwrap();
        let staged = root.join("lesson-stage");
        let manifest = agentlab_code_analysis::maintainer_lesson_admission::stage(
            &base,
            &fenced,
            &lesson_output,
            review["id"].as_str().unwrap(),
            &"a".repeat(40),
            &staged,
        )
        .unwrap();
        // Exercise both native CLI gates with a fully reconstructed real lesson,
        // not a synthetic stage-status flag or mocked admission function.
        let query = |directory: &Path, name: &str, revision: &str, wrapped: bool| {
            let rows: Vec<Value> = fs::read_to_string(directory.join(format!("{name}.jsonl")))
                .unwrap()
                .lines()
                .filter(|line| !line.trim().is_empty())
                .map(|line| {
                    let row: Value = serde_json::from_str(line).unwrap();
                    let id = row["id"].clone();
                    json!({"key":id,"row":if wrapped {json!({"payload":row})} else {row}})
                })
                .collect();
            json!({"revision":revision,"dirty":false,"truncated":false,
                "row_count":rows.len(),"returned_count":rows.len(),"rows":rows})
        };
        let mut source_capture = json!({"schema":"agentlab.reviewed_lesson_source_readback.v1",
            "repository":committed["repository"],"revision":committed["revision"],
            "tablePrefix":committed["tablePrefix"],"tables":{}});
        for name in committed["tables"].as_object().unwrap().keys() {
            source_capture["tables"][name] = query(&lesson_output, name, &"f".repeat(40), false);
        }
        let source_path = root.join("source-readback.json");
        fs::write(&source_path, serde_json::to_vec(&source_capture).unwrap()).unwrap();
        let invoke = |mode: &str, capture: &Path, next: Option<&Path>, output: &Path| {
            let mut command =
                Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"));
            command
                .args([mode, "--knowledge"])
                .arg(&base)
                .arg("--proposal")
                .arg(&fenced)
                .arg("--lesson-source")
                .arg(&lesson_output)
                .args([
                    "--lesson-id",
                    review["id"].as_str().unwrap(),
                    "--expected-knowledge-revision",
                    &"a".repeat(40),
                ])
                .arg("--readback")
                .arg(capture)
                .arg("--output")
                .arg(output);
            if let Some(next) = next {
                command.arg("--committed-knowledge").arg(next);
            }
            command.output().unwrap()
        };
        let inventory_path = base.join("source-set.txt");
        let original_inventory = fs::read(&inventory_path).unwrap();
        fs::remove_file(&inventory_path).unwrap();
        let missing_inventory_output = root.join("rejected-missing-source-inventory");
        assert!(!invoke(
            "--verify-lesson-source-readback",
            &source_path,
            None,
            &missing_inventory_output
        )
        .status
        .success());
        assert!(!missing_inventory_output.exists());
        fs::write(&inventory_path, b"changed-source-inventory\n").unwrap();
        let changed_inventory_output = root.join("rejected-changed-source-inventory");
        assert!(!invoke(
            "--verify-lesson-source-readback",
            &source_path,
            None,
            &changed_inventory_output
        )
        .status
        .success());
        assert!(!changed_inventory_output.exists());
        fs::write(&inventory_path, original_inventory).unwrap();
        let preflight = invoke(
            "--verify-lesson-source-readback",
            &source_path,
            None,
            &root.join("source-return-stage"),
        );
        assert!(
            preflight.status.success(),
            "{}",
            String::from_utf8_lossy(&preflight.stderr)
        );
        let mut bad_source = source_capture.clone();
        bad_source["tables"] = json!({});
        fs::write(&source_path, serde_json::to_vec(&bad_source).unwrap()).unwrap();
        assert!(!invoke(
            "--verify-lesson-source-readback",
            &source_path,
            None,
            &root.join("rejected-source-return-stage")
        )
        .status
        .success());
        let next = root.join("committed-return-cut");
        assert!(Command::new("cp")
            .arg("-R")
            .arg(&staged)
            .arg(&next)
            .status()
            .unwrap()
            .success());
        let mut next_cut: Value =
            serde_json::from_slice(&fs::read(next.join("maintainer-knowledge-cut.json")).unwrap())
                .unwrap();
        next_cut.as_object_mut().unwrap().remove("staging");
        next_cut["tableGitAuthority"]["revision"] = json!("b".repeat(40));
        fs::write(
            next.join("maintainer-knowledge-cut.json"),
            serde_json::to_vec(&next_cut).unwrap(),
        )
        .unwrap();
        let mut return_capture = json!({"schema":"agentlab.reviewed_lesson_committed_readback.v1",
            "knowledgeRepository":cut["tableGitAuthority"]["repo"],
            "previousRevision":"a".repeat(40),"revision":"b".repeat(40),
            "before":{"revision":"b".repeat(40),"dirty":false},
            "after":{"revision":"b".repeat(40),"dirty":false},
            "tables":{},"lessonSource":source_capture});
        for name in [
            "maintainer_skills",
            "maintainer_scope_skills",
            "program_facts",
            "maintainer_skill_refresh_rounds",
            "evaluation_cases",
        ] {
            return_capture["tables"][name] = query(&next, name, &"b".repeat(40), true);
        }
        let capture_path = root.join("committed-return-readback.json");
        fs::write(&capture_path, serde_json::to_vec(&return_capture).unwrap()).unwrap();
        let returned = invoke(
            "--verify-committed-lesson-return",
            &capture_path,
            Some(&next),
            &root.join("committed-return-stage"),
        );
        assert!(
            returned.status.success(),
            "{}",
            String::from_utf8_lossy(&returned.stderr)
        );
        let receipt: Value = serde_json::from_slice(&returned.stdout).unwrap();
        assert_eq!(receipt["committedReadbackVerified"], true);
        assert_eq!(receipt["guidanceConsumed"], false);
        // Run the actual thin entrypoint, its constructor/discovery/person flow,
        // existing exporter and both native gates against an isolated local server.
        // This is transport integration, not a live authority or Agent experiment.
        let transport = r#"
import hashlib,http.server,json,pathlib,subprocess,sys,threading
root,base,proposal,source,tool,script=map(pathlib.Path,sys.argv[1:])
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
names=['maintainer_skills','maintainer_scope_skills','program_facts','maintainer_skill_refresh_rounds','evaluation_cases']
tables={name:[dict(key=row['id'],row_version=1,row=dict(payload=row,payloadSha256=hashlib.sha256(encoded(row)).hexdigest())) for row in map(json.loads,(base/(name+'.jsonl')).read_text().splitlines())] for name in names}
old,new='a'*40,'b'*40
revision=old;writes=0;trace=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        global revision,writes
        packet=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        name=packet['params']['name'];args=packet['params']['arguments'];trace.append(name)
        if name in ['service_metadata','skill_list']:value={}
        elif name=='skill_get':
            operations=['worktree_table_batch_transaction'] if args['skill_id']=='table.author' else ['table_status','table_query']
            value=dict(outcome='loaded',skill=dict(summary=dict(operation_names=operations,skill_version='fixture-v1')))
        elif name=='person_status':value=dict(selectable_persons=[dict(showname='Fixture',person_id='fixture-person')])
        elif name=='person_select':value=dict(outcome='person_context_validated')
        else:
            operation=args['operation'];a=args['arguments']
            assert args['caller_person_id']=='fixture-person'
            if operation=='table_status':result=dict(revision=revision,dirty=False)
            elif operation=='table_query':
                assert a['view']['revision']==revision
                rows=tables[a['path']];offset=a['offset'];page=rows[offset:offset+a['limit']]
                result=dict(revision=revision,dirty=False,rows=page,offset=offset,row_count=len(rows),matched_count=len(rows),returned_count=len(page),truncated=offset+len(page)<len(rows))
            else:
                assert name=='skill_run_write' and operation=='worktree_table_batch_transaction'
                assert writes==0 and a['expected_revision']==old
                for group in a['tables']:
                    for change in group['operations']:
                        assert change['op']=='insert'
                        tables[group['path']].append(dict(key=change['key'],row_version=1,row=change['row']))
                writes+=1;revision=new
                result=dict(previous_revision=old,revision=new,outcome='applied',conflicts=[])
            value=dict(outcome='executed',result=result)
        body=json.dumps(dict(jsonrpc='2.0',id=packet['id'],result=dict(structuredContent=value))).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
source_capture=json.loads((root/'source-readback.json').read_text())
source_capture['schema']='agentlab.observation_store_snapshot.v1'
export=json.loads((source/'export.json').read_text());source_capture['tables']={}
for table in export['tables']:
    rows=[dict(key=row['id'],row=row) for row in map(json.loads,(source/(table+'.jsonl')).read_text().splitlines())]
    source_capture['tables'][table]=dict(revision='f'*40,dirty=False,truncated=False,row_count=len(rows),returned_count=len(rows),rows=rows)
snapshot=root/'transport-source-snapshot.json';snapshot.write_text(json.dumps(source_capture))
credentials=root/'transport-private-fixture.env';credentials.write_text('MCPGIT_BASIC_USERNAME=fixture\nMCPGIT_BASIC_VERIFY=fixture\nMCPGIT_DEFAULT_PERSON_SHOWNAME=Fixture\n')
credentials.chmod(0o600)
skill=json.loads((proposal/'maintainer_skills.jsonl').read_text())
intent=dict(schema='agentlab.reviewed_guidance_continuation.v1',reviewed=True,automaticPromotion=False,
    baselineKnowledgeCutSha256=sha(base/'maintainer-knowledge-cut.json'),baselineKnowledgeRevision=old,
    stage=skill['stage'],sources=[dict(repositoryId=skill['repositoryId'],sourceRevision=skill['sourceRevision'])],
    skills=[dict(id=skill['id'],rowSha256=hashlib.sha256(encoded(skill)).hexdigest(),objectId=skill['objectId'],
                 applicabilityReason='Explicit fixture review of the original operation contract')])
intent_path=root/'reviewed-next-guidance.json';intent_path.write_text(json.dumps(intent))
request=dict(schema='agentlab.reviewed_knowledge_store_request.v1',reviewed=True,automaticPromotion=False,
    endpoint='http://127.0.0.1:'+str(server.server_port),knowledgeRepository=json.loads((base/'maintainer-knowledge-cut.json').read_text())['tableGitAuthority']['repo'],
    expectedKnowledgeRevision=old,knowledgeDirectory=str(base),proposalDirectory=str(proposal),lessonSourceDirectory=str(source),
    lessonId=json.loads((source/'experiment_lessons.jsonl').read_text())['id'],flywheelTool=str(tool),flywheelToolSha256=sha(tool),
    tablegitWriterSha256=sha(script.with_name('maintainer-skill-tablegit.py')),outputDirectory=str(root/'transport-return'),
    runId='fixture-return',githubRepository='fixture/transport',lessonSourceReadback=dict(path=str(snapshot),sha256=sha(snapshot)),
    nextGuidanceIntent=dict(path=str(intent_path),sha256=sha(intent_path)))
request_path=root/'transport-request.json';request_path.write_text(json.dumps(request))
try:
    result=subprocess.run([sys.executable,str(script),'--request',str(request_path),'--credentials',str(credentials)],capture_output=True,timeout=60)
    assert result.returncode==0,(result.stdout,result.stderr)
    outcome=json.loads((root/'transport-return/result.json').read_text())
    assert writes==1 and outcome['committedReadbackVerified'] and outcome['sourceReadbackVerified']
    assert outcome['automaticFiveStageLoopCompleted'] is False
    assert outcome['nextGuidanceBound'] is True
    selected=pathlib.Path(outcome['nextGuidanceSelection']['path'])
    assert sha(selected)==outcome['nextGuidanceSelection']['sha256']
    selection=json.loads(selected.read_text())
    assert selection['knowledgeRevision']==new and selection['skills']==intent['skills']
    packet=json.loads(pathlib.Path(outcome['nextGuidancePacket']['path']).read_text())
    assert packet['selectionSha256']==sha(selected) and packet['agentConsumptionVerified'] is False
    assert packet['guidance'][0]['skill']['id']==skill['id']
    returned=outcome['committedReturn']
    assert returned['guidanceSelection']==outcome['nextGuidanceSelection']
    assert returned['knowledge']['cutSha256']==selection['knowledgeCutSha256']
    assert returned['knowledge']['revision']==new and returned['reviewed'] is True
    assert returned['readback']['sha256']==sha(pathlib.Path(returned['readback']['path']))
    assert (root/'transport-return/committed-knowledge/source-set.txt').read_bytes()==(base/'source-set.txt').read_bytes()
    for name in names:
        assert (root/'transport-return/committed-knowledge'/(name+'.jsonl')).read_bytes()==(root/'transport-return/staged-admission'/(name+'.jsonl')).read_bytes()
    # A complete main invocation rejects missing operational rows before any MCP
    # discovery or transaction, rather than relying on the classmethod fixture.
    observed=len(trace);source_capture['tables']={};snapshot.write_text(json.dumps(source_capture))
    request['lessonSourceReadback']['sha256']=sha(snapshot)
    request['outputDirectory']=str(root/'transport-rejected-source')
    request_path.write_text(json.dumps(request))
    rejected=subprocess.run([sys.executable,str(script),'--request',str(request_path),'--credentials',str(credentials)],capture_output=True,timeout=60)
    assert rejected.returncode!=0 and writes==1 and len(trace)==observed
    assert not (root/'transport-rejected-source/result.json').exists()
    # Valid source but stale/unreviewed/wrong/omitted guidance cannot reach MCP.
    source_capture['tables']=json.loads((root/'transport-return/original-source-snapshot.json').read_text())['tables']
    snapshot.write_text(json.dumps(source_capture));request['lessonSourceReadback']['sha256']=sha(snapshot)
    for index,mode in enumerate(['unreviewed','stale-baseline','wrong-row','omitted-skill','wrong-stage','borrowed-source']):
        rejected_intent=json.loads(json.dumps(intent))
        if mode=='unreviewed':rejected_intent['reviewed']=False
        elif mode=='stale-baseline':rejected_intent['baselineKnowledgeCutSha256']='0'*64
        elif mode=='wrong-row':rejected_intent['skills'][0]['rowSha256']='0'*64
        elif mode=='omitted-skill':rejected_intent['skills'][0]['id']='other-skill'
        elif mode=='wrong-stage':rejected_intent['stage']='repository-analysis'
        else:rejected_intent['sources'][0]['repositoryId']='borrowed-repository'
        intent_path.write_text(json.dumps(rejected_intent));request['nextGuidanceIntent']['sha256']=sha(intent_path)
        request['outputDirectory']=str(root/('transport-rejected-guidance-'+str(index)))
        request_path.write_text(json.dumps(request))
        rejected=subprocess.run([sys.executable,str(script),'--request',str(request_path),'--credentials',str(credentials)],capture_output=True,timeout=60)
        assert rejected.returncode!=0 and writes==1 and len(trace)==observed,mode
finally:
    server.shutdown();server.server_close();thread.join()
"#;
        let integrated = Command::new("python3")
            .args(["-c", transport])
            .arg(root.canonicalize().unwrap())
            .arg(base.canonicalize().unwrap())
            .arg(fenced.canonicalize().unwrap())
            .arg(lesson_output.canonicalize().unwrap())
            .arg(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg(
                Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("../../scripts/commit-reviewed-knowledge.py"),
            )
            .output()
            .unwrap();
        assert!(
            integrated.status.success(),
            "{}",
            String::from_utf8_lossy(&integrated.stderr)
        );
        for (index, pointer) in ["/before/dirty", "/tables/program_facts/truncated"]
            .iter()
            .enumerate()
        {
            let mut bad = return_capture.clone();
            *bad.pointer_mut(pointer).unwrap() = json!(true);
            fs::write(&capture_path, serde_json::to_vec(&bad).unwrap()).unwrap();
            assert!(!invoke(
                "--verify-committed-lesson-return",
                &capture_path,
                Some(&next),
                &root.join(format!("rejected-return-{index}"))
            )
            .status
            .success());
        }
        let assessed: Value = serde_json::from_slice(
            &fs::read(staged.join(manifest["assessment"].as_str().unwrap())).unwrap(),
        )
        .unwrap();
        assert_eq!(assessed["totals"], before["totals"]);
        assert_eq!(
            assessed["inputs"]["programFactsSha256"],
            agentlab_code_analysis::digest(&fs::read(staged.join("program_facts.jsonl")).unwrap())
        );
        assert!(agentlab_code_analysis::maintainer_lesson_admission::stage(
            &base,
            &fenced,
            &lesson_output,
            review["id"].as_str().unwrap(),
            &"a".repeat(40),
            &staged
        )
        .is_err());
        let validator = "import importlib.util,pathlib,sys; s=importlib.util.spec_from_file_location('tablegit',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); f=m.operation_evidence_files(pathlib.Path(sys.argv[2])); assert 'operation-baseline.json' in f and f['source-set.txt']==b'retained fixture inventory\\n'";
        let validate = || {
            Command::new("python3")
                .arg("-c")
                .arg(validator)
                .arg(
                    Path::new(env!("CARGO_MANIFEST_DIR"))
                        .join("../../scripts/maintainer-skill-tablegit.py"),
                )
                .arg(&staged)
                .output()
                .unwrap()
        };
        let validated = validate();
        assert!(
            validated.status.success(),
            "{}",
            String::from_utf8_lossy(&validated.stderr)
        );
        let result_path = staged.join("operation-result.json");
        let mut false_result: Value =
            serde_json::from_slice(&fs::read(&result_path).unwrap()).unwrap();
        false_result["advancedScopeIds"] = json!(["fixture-scope"]);
        fs::write(&result_path, serde_json::to_vec(&false_result).unwrap()).unwrap();
        assert!(!validate().status.success());
        // Real publication rows are heterogeneous; empty fixtures miss this seam.
        let published = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../examples/maintainer-knowledge-gate/first-four");
        let merged = root.join("published-promotion-candidate");
        let result = Command::new(env!("CARGO_BIN_EXE_agentlab-experience"))
            .arg("promote")
            .arg(&lesson_output)
            .arg(&published)
            .arg(&merged)
            .arg(review["id"].as_str().unwrap())
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
            let read = |dir: &Path| -> Vec<Value> {
                fs::read_to_string(dir.join(format!("{name}.jsonl")))
                    .unwrap()
                    .lines()
                    .filter(|l| !l.is_empty())
                    .map(|l| serde_json::from_str(l).unwrap())
                    .collect()
            };
            let old = read(&published);
            let new = read(&merged);
            assert_eq!(
                new.len(),
                old.len() + usize::from(name != "evaluation_cases")
            );
            for row in old {
                assert!(new.contains(&row), "baseline row lost or changed");
            }
        }
        assert_eq!(
            assets["checks"].len(),
            r["controls"]
                .as_array()
                .unwrap()
                .iter()
                .map(|c| c["checks"].as_array().unwrap().len())
                .sum::<usize>()
        );
        assert_eq!(
            first["nextAction"],
            "review-and-admit-scoped-domain-calibration"
        );
        assert_eq!(first["killedSemanticVariantCount"], 2);
        assert_eq!(first["pendingFormalActions"], downstream["actions"]);
        let repeat = consume(&c, &r, Some(&serde_json::to_vec(&first).unwrap())).unwrap();
        assert_eq!(repeat["schedulingAllowed"], false);
        // Recorded runtime identity participates in scheduling even with equal checks.
        let mut runtime_changed = r.clone();
        runtime_changed["runtime"] = json!("v1.2.3");
        let replan = consume(
            &c,
            &runtime_changed,
            Some(&serde_json::to_vec(&first).unwrap()),
        )
        .unwrap();
        assert_eq!(replan["schedulingAllowed"], true);
        assert_ne!(replan["taskSha256"], first["taskSha256"]);
        let mut runtime_missing = r.clone();
        runtime_missing.as_object_mut().unwrap().remove("runtime");
        assert!(consume(&c, &runtime_missing, None)
            .unwrap_err()
            .contains("runtime absent"));
        let (ok, fresh) = run(&root, &c, "fresh");
        assert!(ok);
        let resume = |previous: &Value, capture: &Value| {
            let current = serde_json::to_vec(&fresh).unwrap();
            let prior = serde_json::to_vec(capture).unwrap();
            agentlab_code_analysis::maintainer_stage_feedback::resume(
                &serde_json::to_vec(&candidate).unwrap(),
                &serde_json::to_vec(&downstream).unwrap(),
                &serde_json::to_vec(&c).unwrap(),
                &current,
                &agentlab_code_analysis::digest(&current),
                &serde_json::to_vec(previous).unwrap(),
                &prior,
                &agentlab_code_analysis::digest(&prior),
            )
        };
        let resumed = resume(&first, &r).unwrap();
        assert_eq!(resumed["previousCaptureReconstructed"], true);
        assert_eq!(resumed["schedulingAllowed"], false);
        assert_eq!(resumed["pendingFormalActions"], downstream["actions"]);
        assert_eq!(resumed["qualified"], false);
        // History owns semantic scheduling, not today's formal requirement queue.
        let mut current_downstream = downstream.clone();
        current_downstream["actions"].as_array_mut().unwrap().push(json!({
            "id":"new-formal-demand","kind":"qualify-independent-oracle","executionAuthorized":false
        }));
        let fresh_bytes = serde_json::to_vec(&fresh).unwrap();
        let prior_bytes = serde_json::to_vec(&r).unwrap();
        let current_plan = agentlab_code_analysis::maintainer_stage_feedback::resume(
            &serde_json::to_vec(&candidate).unwrap(),
            &serde_json::to_vec(&current_downstream).unwrap(),
            &serde_json::to_vec(&c).unwrap(),
            &fresh_bytes,
            &agentlab_code_analysis::digest(&fresh_bytes),
            &serde_json::to_vec(&first).unwrap(),
            &prior_bytes,
            &agentlab_code_analysis::digest(&prior_bytes),
        )
        .unwrap();
        assert_eq!(
            current_plan["pendingFormalActions"],
            current_downstream["actions"]
        );
        assert_eq!(current_plan["schedulingAllowed"], false);
        let mut fabricated_plan = first.clone();
        fabricated_plan["taskSha256"] = json!("d".repeat(64));
        assert!(resume(&fabricated_plan, &r)
            .unwrap_err()
            .contains("contradicts retained capture"));
        let mut historical_plan = first.clone();
        historical_plan.as_object_mut().unwrap().remove("runtime");
        assert!(resume(&historical_plan, &r).is_err());
        let mut tampered = r.clone();
        tampered["controls"][1]["checks"][0]["passed"] = json!(true);
        let mut body = tampered["controls"][1].as_object().unwrap().clone();
        body.remove("workerExecution");
        let raw = serde_json::to_string(&Value::Object(body)).unwrap();
        tampered["controls"][1]["workerExecution"]["stdout"] = json!(raw);
        tampered["controls"][1]["workerExecution"]["stdoutSha256"] =
            json!(agentlab_code_analysis::digest(raw.as_bytes()));
        assert!(consume(&c, &tampered, None)
            .unwrap_err()
            .contains("raw observations"));
        assert!(resume(&first, &tampered)
            .unwrap_err()
            .contains("raw observations"));
        assert!(make_assets(&c, &tampered).is_err());
        assert!(lesson_assets(&review, &tampered).is_err());
        let mut missing = r.clone();
        missing["controls"].as_array_mut().unwrap().pop();
        assert!(consume(&c, &missing, None).is_err());
        let mut duplicate = r.clone();
        let extra = duplicate["controls"][1].clone();
        duplicate["controls"].as_array_mut().unwrap().push(extra);
        assert!(consume(&c, &duplicate, None).is_err());
        let mut borrowed = c.clone();
        borrowed["candidateSha256"] = json!("c".repeat(64));
        assert!(consume(&borrowed, &r, None).is_err());
        // Renaming an internal class while retaining its default export is not a semantic defect.
        let mut cosmetic = c.clone();
        cosmetic["variants"][1]["from"] = json!("class Owner");
        cosmetic["variants"][1]["to"] = json!("class Renamed");
        let (ok, r) = run(&root, &cosmetic, "cosmetic");
        assert!(ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        assert_eq!(r["controls"][2]["verdict"], "accept");
        assert_eq!(
            consume(&cosmetic, &r, None).unwrap()["nextAction"],
            "repair-domain-oracle-or-controls"
        );
        // Missing loader support is infrastructure failure, not a killed implementation.
        let mut unsupported = c.clone();
        unsupported["variants"][1]["from"] = json!("require('@kit.AbilityKit')");
        unsupported["variants"][1]["to"] = json!("require('unsupported-platform')");
        let (ok, r) = run(&root, &unsupported, "unsupported");
        assert!(!ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        assert_eq!(r["infrastructureFailure"]["id"], "event");
        let failed_assets = make_assets(&unsupported, &r).unwrap();
        assert_eq!(failed_assets["phase_failures"].len(), 1);
        assert_eq!(failed_assets["calibration_controls"].len(), 2);
        assert_eq!(
            consume(&unsupported, &r, None).unwrap()["nextAction"],
            "repair-domain-calibration-environment"
        );
        let mut ambiguous = c.clone();
        ambiguous["variants"][1]["from"] = json!("not-in-source");
        let (ok, r) = run(&root, &ambiguous, "absent");
        assert!(!ok);
        assert_eq!(r["semanticSeamCalibrationPassed"], false);
        let mut confounded = c.clone();
        confounded["configurations"][1]["colorMode"] = json!(1);
        let (ok, r) = run(&root, &confounded, "confounded");
        assert!(!ok);
        assert!(r.is_null());
        assert!(git(&root, &["diff", "--name-only", "HEAD", "--", "src"]).is_empty());
        fs::remove_dir_all(root).unwrap();
    }
}
