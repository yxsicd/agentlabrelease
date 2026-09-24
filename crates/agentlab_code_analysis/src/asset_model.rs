//! Analysis-oriented asset exchange. Raw files remain byte-exact instance evidence.
mod asset_exchange;
use asset_exchange::*;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
const DETACHED: &[&str] = &[
    "evaluationGuidance",
    "evaluationEvidenceIds",
    "evaluationEvidenceRefs",
    "compilationGuidance",
    "compilationEvidenceIds",
    "compilationSummaryId",
    "latestCompilationQualificationId",
    "buildQualified",
    "fullSourceBuildQualified",
    "sliceBuildQualified",
    "formalSessionFSQualified",
    "uiRenderingQualified",
    "fullTaskQualified",
    "subjectAgentRun",
    "sliceCompilationQualified",
];
fn knowledge(source: &Path) -> (Tables, Tables) {
    let mut reusable = Tables::new();
    let mut execution = Tables::new();
    let mut retained = BTreeSet::new();
    for table in ["maintainer_skills", "program_facts", "evaluation_cases"] {
        reusable.entry(table.into()).or_default();
        for mut row in rows(&source.join(format!("{table}.jsonl"))) {
            let original = row.clone();
            let id = row["id"].as_str().unwrap().to_owned();
            if row.get("producerRun").is_some() {
                put(
                    &mut execution,
                    "construction_records",
                    json!({"id":format!("{table}-{id}"),"assetClass":"evaluation-instance","sourceTable":table,"runId":row["producerRun"],"kind":row["kind"],"record":original}),
                );
                continue;
            }
            if row["kind"] == "oracle" && row.get("result").is_some() {
                let result = row.as_object_mut().unwrap().remove("result").unwrap();
                put(
                    &mut execution,
                    "construction_records",
                    json!({"id":format!("oracle-result-{id}"),"assetClass":"evaluation-instance","sourceTable":table,"knowledgeId":id,"kind":"oracle-calibration-result","sourceRevision":row["sourceRevision"],"record":result}),
                );
            }
            if row["kind"] == "calibration" {
                let result = row.as_object_mut().unwrap().remove("calibration").unwrap();
                let expectations: Map<String, Value> = result
                    .as_object()
                    .unwrap()
                    .keys()
                    .map(|variant| (variant.clone(), json!(variant == "reference")))
                    .collect();
                row["kind"] = json!("calibration-contract");
                row["variantExpectations"] = json!(expectations);
                row.as_object_mut().unwrap().remove("buildQualified");
                row.as_object_mut().unwrap().remove("status");
                put(
                    &mut execution,
                    "construction_records",
                    json!({"id":format!("calibration-result-{id}"),"assetClass":"evaluation-instance","sourceTable":table,"knowledgeId":id,"kind":"case-calibration-result","record":original}),
                );
            }
            if row["kind"] == "task" && row.get("calibration").is_some() {
                let result = row.as_object_mut().unwrap().remove("calibration").unwrap();
                let expectations: Map<String, Value> = result
                    .as_object()
                    .unwrap()
                    .keys()
                    .map(|variant| (variant.clone(), json!(variant == "reference")))
                    .collect();
                row["calibrationContract"] = json!({"variantExpectations":expectations});
                row.as_object_mut().unwrap().remove("status");
                put(
                    &mut execution,
                    "construction_records",
                    json!({"id":format!("task-calibration-result-{id}"),"assetClass":"evaluation-instance","sourceTable":table,"knowledgeId":id,"kind":"task-calibration-result","record":original}),
                );
            }
            let mut detached = Map::new();
            for key in DETACHED {
                if let Some(v) = row.as_object_mut().unwrap().remove(*key) {
                    detached.insert((*key).into(), v);
                }
            }
            if !detached.is_empty() {
                put(
                    &mut execution,
                    "skill_feedback",
                    json!({"id":format!("{table}-{id}"),"assetClass":"evaluation-instance","sourceTable":table,"knowledgeId":id,"feedback":detached,"originalRow":original}),
                );
            }
            if let Some(body) = row.get_mut("body") {
                if let Some(text) = body.as_str() {
                    let paragraphs: Vec<&str> = text
                        .split("\n\n")
                        .filter(|p| !p.starts_with("When present, read compilationEvidenceIds"))
                        .collect();
                    let note="Read operational qualification and run feedback from separate evaluation-instance tables; this reusable Skill does not carry latest-run state.";
                    let cleaned = paragraphs.join("\n\n");
                    *body = json!(if cleaned.ends_with(note) {
                        cleaned
                    } else {
                        format!("{cleaned}\n\n{note}")
                    });
                }
            }
            row["assetClass"] = json!("reusable-knowledge");
            retained.insert(id);
            put(&mut reusable, table, row);
        }
    }
    for row in reusable.get_mut("maintainer_skills").unwrap().values_mut() {
        if let Some(ids) = row.get_mut("factIds").and_then(Value::as_array_mut) {
            ids.retain(|id| retained.contains(id.as_str().unwrap()));
        }
    }
    (reusable, execution)
}
fn json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}
fn relative(path: &Path, root: &Path) -> String {
    path.strip_prefix(root)
        .unwrap()
        .to_string_lossy()
        .replace('\\', "/")
}
fn files(root: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    for entry in fs::read_dir(root).unwrap() {
        let p = entry.unwrap().path();
        if p.is_dir() {
            out.extend(files(&p));
        } else {
            out.push(p);
        }
    }
    out.sort();
    out
}
fn phase_for(path: &str) -> String {
    path.rsplit('/')
        .next()
        .unwrap()
        .trim_end_matches("-events.jsonl")
        .into()
}

fn harmony_instance(root: &Path, run: &str, archive: &str, result: Value) -> Tables {
    let policy_bound = result["schema"] == "agentlab.harmony_emulator_case_result.v3";
    let hap_sha256 = result["hapSha256"]
        .as_str()
        .expect("Harmony emulator result requires hapSha256");
    assert!(
        hap_sha256.len() == 64
            && hap_sha256
                .bytes()
                .all(|value| value.is_ascii_hexdigit() && !value.is_ascii_uppercase()),
        "Harmony emulator hapSha256 must be lowercase SHA-256"
    );
    assert_eq!(
        result["sourceIdentity"],
        format!("artifact-sha256:{hap_sha256}"),
        "Harmony emulator sourceIdentity must bind the exact HAP"
    );
    assert_eq!(
        result["powerThermalAuthority"], "unavailable_on_emulator",
        "Harmony emulator result must not claim power or thermal authority"
    );
    let mut tables = Tables::new();
    for name in [
        "runs",
        "device_assessments",
        "performance_assessments",
        "checks",
        "evidence_files",
    ] {
        tables.entry(name.into()).or_default();
    }
    let functional_passed = result["status"] == "passed";
    let oracle_passed = result["oracleStatus"] == "passed";
    put(
        &mut tables,
        "runs",
        json!({
            "id":run,
            "assetClass":"evaluation-instance",
            "runId":run,
            "taskId":result["taskId"],
            "sourceIdentity":result["sourceIdentity"],
            "summary":result.clone()
        }),
    );
    put(
        &mut tables,
        "device_assessments",
        json!({
            "id":format!("{run}-harmony-emulator"),
            "assetClass":"evaluation-instance",
            "runId":run,
            "taskId":result["taskId"],
            "sourceIdentity":result["sourceIdentity"],
            "scenarioId":result["scenarioId"],
            "scenarioSha256":result["scenarioSha256"],
            "hapSha256":result["hapSha256"],
            "functionalPassed":functional_passed,
            "oraclePassed":oracle_passed,
            "assessmentStatus":result["assessmentStatus"],
            "infrastructureAvailable":result["infrastructureAvailable"],
            "subjectTaskSucceeded":result["subjectTaskSucceeded"],
            "failureClass":result["failureClass"],
            "profileCollected":result["profileStatus"] == "collected",
            "profileRunId":result["profileRunId"],
            "environmentIdentity":result["environmentIdentity"],
            "performancePolicyId":result["performancePolicyId"],
            "performancePolicySha256":result["performancePolicySha256"],
            "profileWorkloadId":result["profileWorkloadId"],
            "profileWorkloadSha256":result["profileWorkloadSha256"],
            "powerThermalAuthority":result["powerThermalAuthority"],
            "authority":"operator-owned-device-runner"
        }),
    );
    for (check, passed) in [
        ("functional-case-completed", functional_passed),
        ("ui-oracle-completed", oracle_passed),
        (
            "smartperf-proxy-collected",
            result["profileStatus"] == "collected",
        ),
    ] {
        put(
            &mut tables,
            "checks",
            json!({
                "id":format!("{run}-{check}"),
                "assetClass":"evaluation-instance",
                "runId":run,
                "phaseLabel":"harmony-emulator",
                "check":check,
                "passed":passed,
                "authority":"operator-owned-device-runner"
            }),
        );
    }
    let performance = root.join("smartperf-summary.json");
    assert!(
        result["profileSummaryStatus"] != "normalized" || performance.exists(),
        "normalized SmartPerf result is missing smartperf-summary.json"
    );
    if performance.exists() {
        assert_eq!(result["profileSummaryStatus"], "normalized");
        let summary = json(&performance);
        assert!(
            summary["schema"] == "agentlab.smartperf_summary.v1"
                || summary["schema"] == "agentlab.smartperf_summary.v2",
            "unsupported SmartPerf summary schema"
        );
        assert_eq!(summary["taskId"], result["taskId"]);
        assert_eq!(summary["sourceIdentity"], result["sourceIdentity"]);
        if !result["profileRunId"].is_null() {
            assert_eq!(summary["runId"], result["profileRunId"]);
        }
        if !result["environmentIdentity"].is_null() {
            assert_eq!(
                summary["environmentIdentity"],
                result["environmentIdentity"]
            );
        }
        assert_eq!(
            summary["authority"]["absolutePowerThermal"],
            "unavailable-on-emulator"
        );
        if policy_bound {
            assert_eq!(summary["schema"], "agentlab.smartperf_summary.v2");
            let policy_path = root.join("performance-policy.json");
            let workload_path = root.join("profile-workload.tsv");
            assert!(
                policy_path.exists(),
                "policy-bound result is missing performance-policy.json"
            );
            assert!(
                workload_path.exists(),
                "policy-bound result is missing profile-workload.tsv"
            );
            let policy = json(&policy_path);
            assert_eq!(policy["schema"], "agentlab.harmony_performance_policy.v1");
            assert_eq!(policy["id"], result["performancePolicyId"]);
            assert_eq!(
                hash(&fs::read(&policy_path).unwrap()),
                result["performancePolicySha256"]
            );
            assert_eq!(
                hash(&fs::read(&workload_path).unwrap()),
                result["profileWorkloadSha256"]
            );
            assert_eq!(
                summary["performancePolicy"]["id"],
                result["performancePolicyId"]
            );
            assert_eq!(
                summary["performancePolicy"]["sha256"],
                result["performancePolicySha256"]
            );
            assert_eq!(
                summary["profileWorkload"]["id"],
                result["profileWorkloadId"]
            );
            assert_eq!(
                summary["profileWorkload"]["sha256"],
                result["profileWorkloadSha256"]
            );
        }
        put(
            &mut tables,
            "performance_assessments",
            json!({
                "id":format!("{run}-smartperf"),
                "assetClass":"evaluation-instance",
                "runId":run,
                "taskId":result["taskId"],
                "sourceIdentity":result["sourceIdentity"],
                "environmentIdentity":summary["environmentIdentity"],
                "sampleCount":summary["sampleCount"],
                "profileValid":summary["profileValid"],
                "canonicalMetrics":summary["canonicalMetrics"],
                "performancePolicy":summary["performancePolicy"],
                "profileWorkload":summary["profileWorkload"],
                "metricAvailability":summary["metricAvailability"],
                "authority":summary["authority"],
                "evidencePath":"smartperf-summary.json"
            }),
        );
        put(
            &mut tables,
            "checks",
            json!({
                "id":format!("{run}-smartperf-summary-normalized"),
                "assetClass":"evaluation-instance",
                "runId":run,
                "phaseLabel":"harmony-emulator",
                "check":"smartperf-summary-normalized",
                "passed":summary["profileValid"] == true,
                "authority":"operator-owned-performance-normalizer"
            }),
        );
    }
    let checks = root.join("ui-checks.tsv");
    let mut ui_check_verdicts = Vec::new();
    if checks.exists() {
        for (line_number, line) in fs::read_to_string(&checks).unwrap().lines().enumerate() {
            let fields: Vec<&str> = line.splitn(4, '\t').collect();
            assert_eq!(
                fields.len(),
                4,
                "Malformed ui-checks.tsv line {}",
                line_number + 1
            );
            assert!(
                matches!(fields[1], "true" | "false"),
                "Malformed UI check outcome on line {}",
                line_number + 1
            );
            ui_check_verdicts.push(fields[1] == "true");
            put(
                &mut tables,
                "checks",
                json!({
                    "id":format!("{run}-{}",fields[0]),
                    "assetClass":"evaluation-instance",
                    "runId":run,
                    "phaseLabel":"harmony-emulator-ui",
                    "check":fields[0],
                    "passed":fields[1] == "true",
                    "kind":fields[2],
                    "expected":fields[3],
                    "authority":"operator-owned-ui-oracle"
                }),
            );
        }
    }
    if result["assessmentStatus"] == "assessed" {
        assert_eq!(result["infrastructureAvailable"], true);
        assert!(result["subjectTaskSucceeded"].is_boolean());
        assert!(
            !ui_check_verdicts.is_empty(),
            "assessed Harmony emulator result requires retained UI checks"
        );
        let aggregate = ui_check_verdicts.iter().all(|value| *value);
        assert_eq!(
            result["subjectTaskSucceeded"], aggregate,
            "Harmony emulator verdict must match retained UI checks"
        );
        assert_eq!(
            oracle_passed, aggregate,
            "Harmony emulator Oracle status must match retained UI checks"
        );
        assert_eq!(
            functional_passed, aggregate,
            "Harmony emulator status must match retained UI checks"
        );
    } else {
        assert_eq!(result["assessmentStatus"], "infrastructure-unavailable");
        assert_eq!(result["infrastructureAvailable"], false);
        assert!(result["subjectTaskSucceeded"].is_null());
    }
    for path in files(root) {
        let rel = relative(&path, root);
        let raw = fs::read(&path).unwrap();
        let file_id = hash(format!("{run}:{rel}").as_bytes());
        put(
            &mut tables,
            "evidence_files",
            json!({
                "id":file_id,
                "assetClass":"evaluation-instance",
                "runId":run,
                "path":rel,
                "sha256":hash(&raw),
                "byteCount":raw.len(),
                "archiveUri":archive,
                "archivePath":format!("raw/{run}/{rel}"),
                "storage":"external-instance-evidence"
            }),
        );
    }
    tables
}

fn instance(root: &Path, run: &str, archive: &str) -> Tables {
    let result_path = root.join("result.json");
    if result_path.exists() {
        let result = json(&result_path);
        if result["schema"] == "agentlab.harmony_emulator_case_result.v2"
            || result["schema"] == "agentlab.harmony_emulator_case_result.v3"
        {
            return harmony_instance(root, run, archive, result);
        }
    }
    let mut t = Tables::new();
    for name in [
        "tool_calls",
        "context_versions",
        "message_contents",
        "context_changes",
        "checks",
    ] {
        t.entry(name.into()).or_default();
    }
    let summary = json(&root.join("summary.json"));
    let task = json(&root.join("frozen-task.json"));
    let mut run_summary = summary.clone();
    run_summary.as_object_mut().unwrap().remove("phases");
    put(
        &mut t,
        "runs",
        json!({"id":run,"assetClass":"evaluation-instance","runId":run,"taskId":task["id"],"sourceRevision":summary["sourceRevision"],"summary":run_summary,"frozenTask":task}),
    );
    let paths = files(root);
    let mut phases = Vec::new();
    for p in &paths {
        if p.to_string_lossy().ends_with("-lifecycle.json") {
            let r = json(p);
            let rel = relative(p, root);
            let participant = rel.split('/').next().unwrap();
            let label = r["label"].as_str().unwrap();
            let phase_id = format!("{participant}-{label}");
            phases.push((participant.to_owned(), phase_id.clone(), r.clone()));
            put(
                &mut t,
                "phases",
                json!({"id":phase_id,"assetClass":"evaluation-instance","runId":run,"attemptId":participant,"phaseId":phase_id,"label":label,"startedAt":r["startedAt"],"endedAt":r["endedAt"],"lifecycle":r,"authority":"supervisor-lifecycle"}),
            );
        }
    }
    let mut requests = Vec::new();
    for p in &paths {
        let rel = relative(p, root);
        let raw = fs::read(p).unwrap();
        let file_id = hash(rel.as_bytes());
        put(
            &mut t,
            "evidence_files",
            json!({"id":file_id,"assetClass":"evaluation-instance","runId":run,"path":rel,"sha256":hash(&raw),"byteCount":raw.len(),"archiveUri":archive,"archivePath":format!("raw/{run}/{rel}"),"storage":"external-instance-evidence"}),
        );
        if rel.contains("/gateway/") && rel.ends_with(".status.json") {
            let status: Value = serde_json::from_slice(&raw).unwrap();
            let participant = rel.split('/').next().unwrap();
            let ordinal = rel.rsplit('/').next().unwrap().split('.').next().unwrap();
            let id = format!("{participant}-{ordinal}");
            let phase = phases
                .iter()
                .filter(|(a, _, r)| {
                    a == participant
                        && r["startedAt"].as_str() <= status["startedAt"].as_str()
                        && status["startedAt"].as_str() <= r["endedAt"].as_str()
                })
                .collect::<Vec<_>>();
            let phase_id = if phase.len() == 1 {
                Some(phase[0].1.as_str())
            } else {
                None
            };
            let req = p.with_file_name(format!("{ordinal}.request.json"));
            let request = json(&req);
            let upstream = p.with_file_name(format!("{ordinal}.upstream-request.json"));
            let mut params = request.clone();
            params.as_object_mut().unwrap().remove("messages");
            params.as_object_mut().unwrap().remove("tools");
            let response_path = p.with_file_name(format!("{ordinal}.response"));
            let response_raw = fs::read(&response_path).unwrap_or_default();
            let mut semantic_complete = false;
            let mut stream_error = Value::Null;
            for line in response_raw.split(|b| *b == b'\n') {
                if let Some(data) = line.strip_prefix(b"data:") {
                    let data = String::from_utf8_lossy(data);
                    if data.trim() == "[DONE]" {
                        semantic_complete = true;
                    } else if let Ok(event) = serde_json::from_str::<Value>(data.trim()) {
                        semantic_complete |= event["choices"].as_array().is_some_and(|choices| {
                            choices.iter().any(|c| c["finish_reason"].is_string())
                        });
                        if !event["error"].is_null() {
                            stream_error = event["error"].clone();
                        }
                    }
                }
            }
            let completion = if request["stream"] == true {
                if !stream_error.is_null() {
                    "stream_error"
                } else if semantic_complete {
                    "completed"
                } else {
                    "incomplete_stream"
                }
            } else {
                status["outcome"].as_str().unwrap_or("unknown")
            };
            put(
                &mut t,
                "llm_requests",
                json!({"id":id,"assetClass":"evaluation-instance","runId":run,"attemptId":participant,"requestId":id,"phaseId":phase_id,"ordinal":ordinal.parse::<u64>().unwrap(),"model":request["model"],"startedAt":status["startedAt"],"endedAt":status["endedAt"],"status":status["status"],"wallMs":status["durationMs"].as_f64().map(|x|x.round() as i64),"parameters":params,"outcome":completion,"transportOutcome":status["outcome"],"semanticComplete":semantic_complete,"streamError":stream_error,"responseByteCount":response_raw.len(),"statusFileId":file_id,"authority":"controlled-gateway"}),
            );
            for (direction, wire) in [
                ("participant", request),
                (
                    "upstream",
                    if upstream.exists() {
                        json(&upstream)
                    } else {
                        Value::Null
                    },
                ),
            ] {
                if wire.is_null() {
                    continue;
                }
                requests.push((
                    participant.to_owned(),
                    direction.to_owned(),
                    id.clone(),
                    phase_id.map(str::to_owned),
                    status["startedAt"].as_str().unwrap().to_owned(),
                    wire,
                ));
            }
        }
        if rel.contains("/gateway/") && rel.ends_with(".response") {
            let participant = rel.split('/').next().unwrap();
            let ordinal = rel.rsplit('/').next().unwrap().split('.').next().unwrap();
            let request_id = format!("{participant}-{ordinal}");
            for (line, data) in raw.split(|b| *b == b'\n').enumerate() {
                if let Some(data) = data.strip_prefix(b"data:") {
                    let frame: Value = serde_json::from_slice(data).unwrap_or_else(
                        |_| json!({"wireText":String::from_utf8_lossy(data).trim()}),
                    );
                    put(
                        &mut t,
                        "llm_response_events",
                        json!({"id":format!("{request_id}-{line}"),"assetClass":"evaluation-instance","runId":run,"attemptId":participant,"requestId":request_id,"ordinal":line,"fileId":file_id,"frame":frame,"authority":"controlled-gateway"}),
                    );
                }
            }
        }
        if rel.ends_with("-events.jsonl") {
            let participant = rel.split('/').next().unwrap();
            let phase = phase_for(&rel);
            let phase_id = format!("{participant}-{phase}");
            let mut message_seq = 0;
            let mut message_id = String::new();
            for (line, event) in BufReader::new(File::open(p).unwrap())
                .split(b'\n')
                .enumerate()
            {
                let event = event.unwrap();
                if event.iter().all(u8::is_ascii_whitespace) {
                    continue;
                }
                let event: Value = serde_json::from_slice(&event).unwrap();
                let base = json!({"assetClass":"evaluation-instance","runId":run,"attemptId":participant,"phaseId":phase_id,"fileId":file_id,"lineNumber":line+1,"authority":"participant-adapter"});
                match event["type"].as_str().unwrap() {
                    "message_start" => {
                        message_seq += 1;
                        message_id = format!("{phase_id}-message-{message_seq}");
                    }
                    "message_end" => {
                        if message_id.is_empty() {
                            message_seq += 1;
                            message_id = format!("{phase_id}-message-{message_seq}");
                        }
                        let mut row = base.clone();
                        row["id"] = json!(format!("{phase_id}-final-{line}"));
                        row["messageId"] = json!(message_id);
                        row["role"] = event["message"]["role"].clone();
                        row["message"] = event["message"].clone();
                        put(&mut t, "native_messages", row);
                    }
                    "message_update" => {
                        let mut delta = event["assistantMessageEvent"].clone();
                        delta.as_object_mut().unwrap().remove("partial");
                        let mut row = base.clone();
                        row["id"] = json!(format!("{phase_id}-stream-{line}"));
                        row["messageId"] = json!(message_id);
                        row["ordinal"] = json!(line);
                        row["kind"] = delta["type"].clone();
                        row["delta"] = delta;
                        put(&mut t, "message_stream", row);
                    }
                    "tool_execution_start" | "tool_execution_end" | "tool_execution_update" => {
                        let tool = event["toolCallId"].as_str().unwrap();
                        let mut row = base.clone();
                        row["id"] = json!(format!("{phase_id}-tool-{line}"));
                        row["toolCallId"] = json!(format!("{participant}-{tool}"));
                        row["nativeToolCallId"] = json!(tool);
                        row["toolName"] = event["toolName"].clone();
                        row["kind"] = event["type"].clone();
                        row["arguments"] = event["args"].clone();
                        row["result"] = event["result"].clone();
                        row["isError"] = event["isError"].clone();
                        let mut details = event;
                        for key in [
                            "type",
                            "toolCallId",
                            "toolName",
                            "args",
                            "result",
                            "isError",
                        ] {
                            details.as_object_mut().unwrap().remove(key);
                        }
                        row["details"] = details;
                        put(&mut t, "tool_events", row);
                    }
                    _ => {
                        let mut row = base;
                        row["id"] = json!(format!("{phase_id}-event-{line}"));
                        row["kind"] = event["type"].clone();
                        row["event"] = event;
                        put(&mut t, "agent_events", row);
                    }
                }
            }
        }
        if rel.ends_with("-oracle.stdout.json") {
            let oracle: Value = serde_json::from_slice(&raw).unwrap();
            let analyses: Vec<&Value> = oracle
                .get("sourceAnalysis")
                .into_iter()
                .chain(
                    oracle
                        .get("sourceAnalyses")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten(),
                )
                .collect();
            for (index, analysis) in analyses.iter().enumerate() {
                let analysis_id = if oracle.get("sourceAnalyses").is_some() {
                    format!("{file_id}-{index}")
                } else {
                    file_id.clone()
                };
                put(
                    &mut t,
                    "source_analyses",
                    json!({"id":analysis_id,"assetClass":"evaluation-instance","runId":run,"fileId":file_id,"sourceRevision":analysis["sourceCut"],"observedSourceCut":analysis["sourceCut"],"grammar":analysis["grammar"],"grammarDigest":analysis["grammarDigest"],"syntaxHasErrors":analysis["syntaxHasErrors"]}),
                );
                for fact in analysis["rows"].as_array().unwrap() {
                    let mut row = fact.clone();
                    row["id"] = json!(format!("{analysis_id}-{}", fact["id"].as_str().unwrap()));
                    row["sourceAnalysisId"] = json!(analysis_id);
                    row["assetClass"] = json!("evaluation-instance");
                    row["runId"] = json!(run);
                    put(&mut t, "source_facts", row);
                }
            }
        }
    }
    requests.sort_by(|a, b| (&a.4, &a.0, &a.1, &a.2).cmp(&(&b.4, &b.0, &b.1, &b.2)));
    let mut previous: BTreeMap<(String, String), String> = BTreeMap::new();
    let mut bodies: BTreeMap<(String, String), Vec<String>> = BTreeMap::new();
    for (sequence, (attempt, direction, request_id, phase_id, started_at, wire)) in
        requests.iter().enumerate()
    {
        let key = (attempt.clone(), direction.clone());
        let version = format!("{request_id}-{direction}");
        let mut ids = Vec::new();
        for (ordinal, message) in wire["messages"].as_array().unwrap().iter().enumerate() {
            let content_id = hash(&serde_json::to_vec(message).unwrap());
            ids.push(content_id.clone());
            put(
                &mut t,
                "message_contents",
                json!({"id":content_id,"assetClass":"evaluation-instance","runId":run,"role":message["role"],"message":message}),
            );
            if let Some(calls) = message["tool_calls"].as_array() {
                for (call_ordinal, call) in calls.iter().enumerate() {
                    put(
                        &mut t,
                        "llm_tool_calls",
                        json!({"id":format!("{version}-{ordinal}-{call_ordinal}"),"assetClass":"evaluation-instance","runId":run,"attemptId":attempt,"requestId":request_id,"contextVersionId":version,"messageId":content_id,"toolCallId":format!("{attempt}-{}",call["id"].as_str().unwrap()),"toolName":call["function"]["name"],"argumentsText":call["function"]["arguments"],"arguments":call["function"]["arguments"].as_str().and_then(|s|serde_json::from_str::<Value>(s).ok()),"direction":direction}),
                    );
                }
            }
            let logical = format!("{attempt}-{direction}-{ordinal}");
            let before = bodies.get(&key).and_then(|v| v.get(ordinal));
            if before != Some(&content_id) {
                put(
                    &mut t,
                    "context_changes",
                    json!({"id":format!("{version}-{ordinal}"),"assetClass":"evaluation-instance","runId":run,"attemptId":attempt,"requestId":request_id,"contextVersionId":version,"logicalMessageId":logical,"ordinal":ordinal,"kind":if before.is_some(){"replace"}else{"add"},"beforeMessageId":before,"afterMessageId":content_id}),
                );
            }
        }
        if let Some(old) = bodies.get(&key) {
            for (ordinal, before) in old.iter().enumerate().skip(ids.len()) {
                put(
                    &mut t,
                    "context_changes",
                    json!({"id":format!("{version}-{ordinal}"),"assetClass":"evaluation-instance","runId":run,"attemptId":attempt,"requestId":request_id,"contextVersionId":version,"logicalMessageId":format!("{attempt}-{direction}-{ordinal}"),"ordinal":ordinal,"kind":"remove","beforeMessageId":before,"afterMessageId":null}),
                );
            }
        }
        put(
            &mut t,
            "context_versions",
            json!({"id":version,"assetClass":"evaluation-instance","runId":run,"attemptId":attempt,"requestId":request_id,"phaseId":phase_id,"direction":direction,"sequence":sequence,"startedAt":started_at,"previousVersionId":previous.get(&key),"messageIds":ids}),
        );
        for (ordinal, tool) in wire["tools"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .enumerate()
        {
            put(
                &mut t,
                "request_tools",
                json!({"id":format!("{version}-{ordinal}"),"assetClass":"evaluation-instance","runId":run,"requestId":request_id,"contextVersionId":version,"ordinal":ordinal,"toolName":tool["function"]["name"],"definition":tool}),
            );
        }
        previous.insert(key.clone(), version);
        bodies.insert(key, ids);
    }
    let mut executions: BTreeMap<String, Value> = BTreeMap::new();
    if let Some(events) = t.get("tool_events") {
        let mut ordered: Vec<&Value> = events.values().collect();
        ordered.sort_by_key(|e| e["lineNumber"].as_u64().unwrap());
        for event in ordered {
            let id = event["toolCallId"].as_str().unwrap();
            let entry=executions.entry(id.into()).or_insert_with(||json!({"id":id,"assetClass":"evaluation-instance","runId":run,"attemptId":event["attemptId"],"phaseId":event["phaseId"],"toolCallId":id,"nativeToolCallId":event["nativeToolCallId"],"toolName":event["toolName"],"authority":"participant-adapter"}));
            match event["kind"].as_str().unwrap() {
                "tool_execution_start" => {
                    entry["arguments"] = event["arguments"].clone();
                    entry["startEventId"] = event["id"].clone();
                    entry["status"] = json!("started");
                }
                "tool_execution_end" => {
                    entry["result"] = event["result"].clone();
                    entry["endEventId"] = event["id"].clone();
                    entry["isError"] = event["isError"].clone();
                    entry["status"] = json!(if event["isError"] == true {
                        "completed-error"
                    } else {
                        "completed"
                    });
                }
                _ => {}
            }
        }
    }
    for row in executions.into_values() {
        put(&mut t, "tool_calls", row);
    }
    for attempt in ["parent-agent", "fork-agent"]
        .into_iter()
        .filter(|a| root.join(a).is_dir())
    {
        put(
            &mut t,
            "attempts",
            json!({"id":attempt,"assetClass":"evaluation-instance","runId":run,"role":"assessed-agent","parentAttemptId":if attempt=="fork-agent"{Some("parent-agent")}else{None},"forkScope":if attempt=="fork-agent"{Some("selected-source-only")}else{None},"formalSessionFSQualified":false}),
        );
    }
    for (phase, result) in summary["phases"].as_object().unwrap() {
        let label = phase.strip_suffix("-launch-error").unwrap_or(phase);
        let phase_id = phase_reference(&t, label);
        if !result.is_object() {
            let timed_out = phase_id
                .as_ref()
                .and_then(|id| t.get("phases")?.get(id))
                .is_some_and(|row| row["lifecycle"]["timedOut"] == true);
            put(
                &mut t,
                "phase_failures",
                json!({"id":phase,"assetClass":"evaluation-instance","runId":run,"phaseId":phase_id,"phaseLabel":label,"kind":if timed_out {"participant-budget-timeout"} else {"participant-launch-error"},"message":result.as_str().map(str::to_owned).unwrap_or_else(|| result.to_string()),"authority":"supervisor-lifecycle"}),
            );
            continue;
        }
        put(
            &mut t,
            "assessments",
            json!({"id":phase,"assetClass":"evaluation-instance","runId":run,"phaseId":phase_id,"phaseLabel":label,"buildPassed":result["build"],"behaviorPassed":result["behavior"]["pass"],"sourceCut":result["sourceCut"]}),
        );
        if let Some(checks) = result["behavior"]["checks"].as_object() {
            for (check, passed) in checks {
                put(
                    &mut t,
                    "checks",
                    json!({"id":format!("{phase}-{check}"),"assetClass":"evaluation-instance","runId":run,"phaseId":phase_id,"phaseLabel":label,"check":check,"passed":passed}),
                );
            }
        }
    }
    for p in &paths {
        let rel = relative(p, root);
        if rel.ends_with("/source-cut.json") {
            let cut = json(p);
            put(
                &mut t,
                "workspace_cuts",
                json!({"id":rel,"assetClass":"evaluation-instance","runId":run,"scope":"selected-source-only","cut":cut}),
            );
        }
    }
    if root.join("binary-publication.json").exists() {
        for binary in json(&root.join("binary-publication.json"))
            .as_array()
            .unwrap()
        {
            put(
                &mut t,
                "artifacts",
                json!({"id":binary["sha256"],"assetClass":"evaluation-instance","sha256":binary["sha256"],"bytes":binary["bytes"]}),
            );
            let label = binary["label"].as_str().unwrap();
            let phase = label.strip_suffix("-build").unwrap_or(label);
            let phase_id = phase_reference(&t, phase);
            let occurrence = hash(
                serde_json::to_vec(&json!([run, label, binary["uri"]]))
                    .unwrap()
                    .as_slice(),
            );
            put(
                &mut t,
                "artifact_publications",
                json!({"id":occurrence,"assetClass":"evaluation-instance","runId":run,"phaseId":phase_id,"phaseLabel":phase,"label":label,"artifactId":binary["sha256"],"uri":binary["uri"]}),
            );
        }
    }
    t
}
fn phase_reference(t: &Tables, label: &str) -> Option<String> {
    let mut matches = t
        .get("phases")?
        .values()
        .filter(|row| row["label"].as_str() == Some(label));
    let id = matches.next()?["id"].as_str()?.to_owned();
    if matches.next().is_some() {
        None
    } else {
        Some(id)
    }
}
fn main() {
    let args: Vec<String> = std::env::args().collect();
    assert!(
        args.len() >= 4,
        "agentlab-asset-model KNOWLEDGE OUTPUT RAW_ARCHIVE_URI [RUN=EVIDENCE ...]"
    );
    let out = Path::new(&args[2]);
    assert!(!out.exists(), "Use a new output directory");
    let (knowledge, construction) = knowledge(Path::new(&args[1]));
    let mut manifest = json!({"schema":"agentlab.asset_catalog.v1","knowledge":export(&out.join("knowledge"),"reusable-knowledge",&knowledge),"construction":export(&out.join("instances/construction"),"evaluation-instance",&construction),"instances":{}});
    for arg in &args[4..] {
        let (run, root) = arg.split_once('=').unwrap();
        let tables = instance(Path::new(root), run, &args[3]);
        manifest["instances"][run] = export(
            &out.join(format!("instances/{run}")),
            "evaluation-instance",
            &tables,
        );
    }
    let mut file = File::create(out.join("catalog.json")).unwrap();
    file.write_all(&serde_json::to_vec_pretty(&manifest).unwrap())
        .unwrap();
    println!("{}", serde_json::to_string(&manifest).unwrap());
}
