use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
fn write(path: &Path, value: Value) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, serde_json::to_vec(&value).unwrap()).unwrap();
}
fn rows(path: &Path) -> Vec<Value> {
    fs::read(path)
        .unwrap()
        .split(|b| *b == b'\n')
        .filter(|s| !s.is_empty())
        .map(|s| serde_json::from_slice(s).unwrap())
        .collect()
}
#[test]
fn separates_assets_restores_context_and_keeps_raw_evidence() {
    let root = std::env::temp_dir().join(format!(
        "al-asset-model-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let seed = root.join("seed");
    fs::create_dir_all(&seed).unwrap();
    for (table, row) in [
        (
            "maintainer_skills",
            json!({"id":"skill","factIds":["static","result"],"body":"maintenance","evaluationGuidance":{"latestSummaryId":"run-result"}}),
        ),
        (
            "program_facts",
            json!({"id":"static","kind":"symbol","name":"f"}),
        ),
        (
            "evaluation_cases",
            json!({"id":"case","kind":"task","demands":["fix"],"calibration":{"baseline":{"pass":false,"raw":"complete baseline"},"reference":{"pass":true}},"status":"previous-run-qualified"}),
        ),
    ] {
        fs::write(seed.join(format!("{table}.jsonl")), format!("{row}\n")).unwrap();
    }
    let mut f = fs::OpenOptions::new()
        .append(true)
        .open(seed.join("program_facts.jsonl"))
        .unwrap();
    use std::io::Write;
    writeln!(
        f,
        "{}",
        json!({"id":"result","kind":"assessment-finding","producerRun":"run","passed":false})
    )
    .unwrap();
    let e = root.join("evidence");
    write(
        &e.join("summary.json"),
        json!({"sourceRevision":"source","ok":true,"phases":{"turn-1":{"build":true,"behavior":{"pass":true,"checks":{"accepted":true}}}}}),
    );
    write(
        &e.join("frozen-task.json"),
        json!({"id":"case","demands":["fix"]}),
    );
    write(
        &e.join("parent-agent/turn-1-lifecycle.json"),
        json!({"label":"turn-1","startedAt":"2026-01-01T00:00:00Z","endedAt":"2026-01-01T00:01:00Z"}),
    );
    for (ordinal, text) in [(1, "old\u{2028}text"), (2, "new text")] {
        let g = e.join("parent-agent/gateway");
        write(
            &g.join(format!("{ordinal:04}.status.json")),
            json!({"startedAt":format!("2026-01-01T00:00:0{ordinal}Z"),"endedAt":"2026-01-01T00:00:10Z","status":200,"durationMs":10,"outcome":"completed"}),
        );
        let req = json!({"model":"model","messages":[{"role":"user","content":text}],"tools":[]});
        write(&g.join(format!("{ordinal:04}.request.json")), req.clone());
        write(&g.join(format!("{ordinal:04}.upstream-request.json")), req);
        fs::write(
            g.join(format!("{ordinal:04}.response")),
            "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\ndata: [DONE]\n",
        )
        .unwrap();
    }
    let events = [
        json!({"type":"message_start","message":{"role":"assistant"}}),
        json!({"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"hello","partial":{"content":"huge repeated snapshot"}},"message":{"content":"huge repeated snapshot"}}),
        json!({"type":"message_end","message":{"role":"assistant","content":"hello"}}),
        json!({"type":"tool_execution_start","toolCallId":"call","toolName":"bash","args":{"command":"git"}}),
        json!({"type":"tool_execution_end","toolCallId":"call","toolName":"bash","isError":true,"result":{"content":"git missing"}}),
    ];
    fs::write(
        e.join("parent-agent/turn-1-events.jsonl"),
        events.iter().map(|r| format!("{r}\n")).collect::<String>(),
    )
    .unwrap();
    for name in ["first", "second"] {
        assert!(Command::new(env!("CARGO_BIN_EXE_agentlab-asset-model"))
            .args([
                seed.to_str().unwrap(),
                root.join(name).to_str().unwrap(),
                "https://example/raw.tar.zst",
                &format!("run={}", e.display())
            ])
            .output()
            .unwrap()
            .status
            .success());
    }
    let output = root.join("first");
    let skills = rows(&output.join("knowledge/maintainer_skills.jsonl"));
    assert!(skills[0].get("evaluationGuidance").is_none());
    assert_eq!(skills[0]["factIds"], json!(["static"]));
    let feedback = rows(&output.join("instances/construction/skill_feedback.jsonl"));
    assert_eq!(
        feedback[0]["feedback"]["evaluationGuidance"]["latestSummaryId"],
        "run-result"
    );
    assert_eq!(
        rows(&output.join("instances/construction/construction_records.jsonl")).len(),
        2
    );
    let cases = rows(&output.join("knowledge/evaluation_cases.jsonl"));
    assert!(cases[0].get("calibration").is_none());
    assert!(cases[0].get("status").is_none());
    assert_eq!(
        cases[0]["calibrationContract"]["variantExpectations"]["reference"],
        true
    );
    let records = rows(&output.join("instances/construction/construction_records.jsonl"));
    assert!(records
        .iter()
        .any(|r| r["record"]["calibration"]["baseline"]["raw"] == "complete baseline"));
    let instance = output.join("instances/run");
    assert_eq!(rows(&instance.join("message_contents.jsonl")).len(), 2);
    assert_eq!(rows(&instance.join("context_versions.jsonl")).len(), 4);
    assert_eq!(
        rows(&instance.join("context_changes.jsonl"))
            .iter()
            .filter(|r| r["kind"] == "replace")
            .count(),
        2
    );
    let stream = rows(&instance.join("message_stream.jsonl"));
    assert_eq!(stream[0]["delta"]["delta"], "hello");
    assert!(stream[0]["delta"].get("partial").is_none());
    let tool = rows(&instance.join("tool_calls.jsonl"));
    assert_eq!(tool[0]["arguments"]["command"], "git");
    assert_eq!(tool[0]["result"]["content"], "git missing");
    assert_eq!(tool[0]["status"], "completed-error");
    assert!(!instance.join("assessment-file-part.jsonl").exists());
    for entry in fs::read_dir(&instance).unwrap() {
        let p = entry.unwrap().path();
        assert_eq!(
            fs::read(&p).unwrap(),
            fs::read(
                root.join("second/instances/run")
                    .join(p.file_name().unwrap())
            )
            .unwrap()
        );
    }
    assert!(Command::new(env!("CARGO_BIN_EXE_agentlab-asset-model"))
        .args([
            output.join("knowledge").to_str().unwrap(),
            root.join("reusable-repeat").to_str().unwrap(),
            "https://example/raw.tar.zst"
        ])
        .output()
        .unwrap()
        .status
        .success());
    for name in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        assert_eq!(
            fs::read(output.join(format!("knowledge/{name}.jsonl"))).unwrap(),
            fs::read(root.join(format!("reusable-repeat/knowledge/{name}.jsonl"))).unwrap()
        );
    }
    fs::remove_dir_all(root).unwrap();
}
