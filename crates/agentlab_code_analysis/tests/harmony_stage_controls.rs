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
        let root = std::env::temp_dir().join(format!(
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
            "tableGitAuthority":{"repo":format!("fixture-knowledge-{repository}"),"revision":"a".repeat(40)},"tables":{}});
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
