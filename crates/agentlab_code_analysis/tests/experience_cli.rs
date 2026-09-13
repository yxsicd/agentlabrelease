use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
fn rows(p: &Path) -> Vec<Value> {
    fs::read_to_string(p)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect()
}
#[test]
fn validates_negative_variant_and_promotes_only_explicit_verified_lesson() {
    let root = std::env::temp_dir().join(format!(
        "al-experience-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let fixture = repo.join("examples/knowledge-seed/experience/fixture");
    let binary = env!("CARGO_BIN_EXE_agentlab-experience");
    let calibration = root.join("calibration");
    assert!(Command::new(binary)
        .args(["calibrate"])
        .args([
            fixture.join("DelayedLoadingView.ets"),
            fixture.join("source.json"),
            repo.join("examples/knowledge-seed/flywheel/loading.js"),
            calibration.clone()
        ])
        .output()
        .unwrap()
        .status
        .success());
    let instance = root.join("instance");
    fs::create_dir(&instance).unwrap();
    fs::write(instance.join("tool_calls.jsonl"),format!("{}\n",json!({"id":"reported-error","isError":true,"authority":"participant-adapter","result":{"content":"a complete error"}}))).unwrap();
    fs::write(instance.join("checks.jsonl"),format!("{}\n",json!({"id":"known-delay","check":"allKnownDelays","passed":false,"runId":"run","phaseId":"parent-turn-2"}))).unwrap();
    let analysis = root.join("analysis.json");
    fs::write(
        &analysis,
        json!({"request":{"bindings":[{"revision":"input-cut"}]},"result":{"rows":[[]]},"outcomeRequest":{"bindings":[{"revision":"input-cut"}],"sql":"query"},"outcomeResult":{"rows":[[]]}})
            .to_string(),
    )
    .unwrap();
    let experience = root.join("experience");
    assert!(Command::new(binary)
        .arg("observe")
        .args([
            instance,
            analysis,
            calibration.join("calibration.json"),
            experience.clone()
        ])
        .output()
        .unwrap()
        .status
        .success());
    let lessons = rows(&experience.join("experiment_lessons.jsonl"));
    assert!(lessons
        .iter()
        .any(|r| r["status"] == "observed" && r["attribution"] == "unknown"));
    assert!(lessons.iter().any(|r| r["kind"] == "assessed-check-failure"
        && r["status"] == "observed"
        && r["checkId"] == "known-delay"));
    let knowledge = root.join("knowledge");
    fs::create_dir(&knowledge).unwrap();
    for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        fs::write(knowledge.join(format!("{name}.jsonl")), "").unwrap();
    }
    let promoted = root.join("promoted");
    assert!(Command::new(binary)
        .arg("promote")
        .args([experience.clone(), knowledge.clone(), promoted.clone()])
        .arg("loading-reappearance-cancels-old-timer")
        .output()
        .unwrap()
        .status
        .success());
    assert_eq!(
        rows(&promoted.join("program_facts.jsonl"))[0]["qualification"],
        "isolated timer/breakpoint scheduler; not HAP or UI"
    );
    assert!(!Command::new(binary)
        .arg("promote")
        .args([experience.clone(), knowledge.clone(), root.join("bad")])
        .arg("tool-error-reported-error")
        .output()
        .unwrap()
        .status
        .success());
    let mut broken: Value =
        serde_json::from_slice(&fs::read(calibration.join("calibration.json")).unwrap()).unwrap();
    broken["variants"]["wrong-cancel"]["pass"] = json!(true);
    let bad_calibration = root.join("bad-calibration.json");
    fs::write(&bad_calibration, broken.to_string()).unwrap();
    let rejected = root.join("rejected");
    assert!(Command::new(binary)
        .arg("observe")
        .args([
            root.join("instance"),
            root.join("analysis.json"),
            bad_calibration,
            rejected.clone()
        ])
        .output()
        .unwrap()
        .status
        .success());
    assert!(!Command::new(binary)
        .arg("promote")
        .args([rejected, knowledge, root.join("bad-negative")])
        .arg("loading-reappearance-cancels-old-timer")
        .output()
        .unwrap()
        .status
        .success());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn utility_lessons_promote_their_own_identity_and_scope() {
    let root = std::env::temp_dir().join(format!(
        "al-utility-experience-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&root).unwrap();
    let binary = env!("CARGO_BIN_EXE_agentlab-experience");
    let instance = root.join("instance");
    fs::create_dir(&instance).unwrap();
    for name in ["tool_calls", "checks"] {
        fs::write(instance.join(format!("{name}.jsonl")), "").unwrap();
    }
    let analysis = root.join("analysis.json");
    fs::write(
        &analysis,
        json!({"request":{"bindings":[{"revision":"input-cut"}]},"result":{"rows":[]}}).to_string(),
    )
    .unwrap();
    let knowledge = root.join("knowledge");
    fs::create_dir(&knowledge).unwrap();
    for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        fs::write(knowledge.join(format!("{name}.jsonl")), "").unwrap();
    }
    for scenario in ["debounce", "image-url"] {
        let response = Command::new(binary)
            .args(["contract", scenario])
            .output()
            .unwrap();
        assert!(response.status.success());
        let contract: Value = serde_json::from_slice(&response.stdout).unwrap();
        let variants: serde_json::Map<String, Value> = contract["expected"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(name, expected)| {
                (
                    name.clone(),
                    json!({"pass":expected,"checks":{"retained-behavior":true}}),
                )
            })
            .collect();
        let calibration = root.join(format!("{scenario}.json"));
        fs::write(
            &calibration,
            json!({"sourceRevision":"source-cut","lesson":contract,"variants":variants})
                .to_string(),
        )
        .unwrap();
        let experience = root.join(format!("{scenario}-experience"));
        assert!(Command::new(binary)
            .arg("observe")
            .args([
                instance.clone(),
                analysis.clone(),
                calibration.clone(),
                experience.clone()
            ])
            .output()
            .unwrap()
            .status
            .success());
        let validation_rows = rows(&experience.join("lesson_validations.jsonl"));
        assert_eq!(
            validation_rows
                .iter()
                .filter(|r| r["kind"] == "variant-verdict")
                .count(),
            4
        );
        let evidence_rows = rows(&experience.join("lesson_evidence.jsonl"));
        assert_eq!(
            evidence_rows
                .iter()
                .filter(
                    |r| r["kind"] == "calibration-check-observation" && r["observedPass"] == true
                )
                .count(),
            4
        );
        let output = root.join(format!("{scenario}-promotion"));
        assert!(Command::new(binary)
            .arg("promote")
            .args([experience.clone(), knowledge.clone(), output.clone()])
            .arg(contract["id"].as_str().unwrap())
            .output()
            .unwrap()
            .status
            .success());
        let facts = rows(&output.join("program_facts.jsonl"));
        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0]["id"], contract["factId"]);
        assert_eq!(facts[0]["scope"], contract["scope"]);
        assert_ne!(facts[0]["id"], "lesson-loading-lifecycle");
        let mut rejected: Value = serde_json::from_slice(&fs::read(&calibration).unwrap()).unwrap();
        let negative = if scenario == "debounce" {
            "wrong-window"
        } else {
            "wrong-dispatch"
        };
        rejected["variants"][negative]["pass"] = json!(true);
        fs::write(&calibration, rejected.to_string()).unwrap();
        let failure = root.join(format!("{scenario}-rejected"));
        assert!(Command::new(binary)
            .arg("observe")
            .args([
                instance.clone(),
                analysis.clone(),
                calibration.clone(),
                failure.clone()
            ])
            .output()
            .unwrap()
            .status
            .success());
        assert!(!Command::new(binary)
            .arg("promote")
            .args([
                failure,
                knowledge.clone(),
                root.join(format!("{scenario}-bad-promotion"))
            ])
            .arg(contract["id"].as_str().unwrap())
            .output()
            .unwrap()
            .status
            .success());
    }
}
