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
    let analysis = root.join("analysis.json");
    fs::write(
        &analysis,
        json!({"request":{"bindings":[{"revision":"input-cut"}]},"result":{"rows":[[]]}})
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
