use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn repository() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap()
        .to_path_buf()
}

fn temp_root() -> PathBuf {
    let root = std::env::temp_dir().join(format!(
        "agentlab-case-state-{}-{}-{}",
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

fn write(path: &Path, value: &Value) {
    let mut bytes = serde_json::to_vec_pretty(value).unwrap();
    bytes.push(b'\n');
    fs::write(path, bytes).unwrap();
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn canonical_digest(value: &Value) -> String {
    digest(&serde_json::to_vec(value).unwrap())
}

fn file_binding(root: &Path, path: &Path) -> Value {
    let bytes = fs::read(path).unwrap();
    json!({
        "path": path.strip_prefix(root).unwrap().to_string_lossy(),
        "byteLength": bytes.len(),
        "sha256": digest(&bytes)
    })
}

fn write_blind_cut(root: &Path, node: &Value) -> Value {
    let node_id = node["nodeId"].as_str().unwrap();
    let cut_root = root.join("blind-cuts").join(node_id);
    let participant_path = cut_root.join("participant/manifest.json");
    let evaluator_path = cut_root.join("evaluator/manifest.json");
    let receipt_path = cut_root.join("cut-receipt.json");
    fs::create_dir_all(participant_path.parent().unwrap()).unwrap();
    fs::create_dir_all(evaluator_path.parent().unwrap()).unwrap();
    let task_path = cut_root.join("participant/task.json");
    let oracle_path = cut_root.join("evaluator/oracle.mjs");
    let reference_path = cut_root.join("evaluator/reference.patch");
    fs::write(&task_path, format!("task:{node_id}\n")).unwrap();
    fs::write(&oracle_path, format!("oracle:{node_id}\n")).unwrap();
    fs::write(&reference_path, format!("reference:{node_id}\n")).unwrap();
    let task_bytes = fs::read(&task_path).unwrap();
    let oracle_bytes = fs::read(&oracle_path).unwrap();
    let reference_bytes = fs::read(&reference_path).unwrap();
    write(
        &participant_path,
        &json!({
            "schema": "agentlab.blind_case_participant_bundle.v1",
            "cutId": format!("{node_id}-blind-v1"),
            "caseId": node["caseId"],
            "methodRevision": "1".repeat(40),
            "sourceSetSha256": node["sourceSetSha256"],
            "files": [{
                "path": "task.json",
                "role": "task",
                "sha256": digest(&task_bytes),
                "bytes": task_bytes.len()
            }],
            "constraints": {"networkPolicy": "controlled"}
        }),
    );
    write(
        &evaluator_path,
        &json!({
            "schema": "agentlab.blind_case_evaluator_bundle.v1",
            "cutId": format!("{node_id}-blind-v1"),
            "caseId": node["caseId"],
            "methodRevision": "1".repeat(40),
            "sourceSetSha256": node["sourceSetSha256"],
            "participantManifestSha256": digest(&fs::read(&participant_path).unwrap()),
            "files": [
                {
                    "path": "oracle.mjs",
                    "role": "oracle",
                    "sha256": digest(&oracle_bytes),
                    "bytes": oracle_bytes.len()
                },
                {
                    "path": "reference.patch",
                    "role": "reference",
                    "sha256": digest(&reference_bytes),
                    "bytes": reference_bytes.len()
                }
            ]
        }),
    );
    write(
        &receipt_path,
        &json!({
            "schema": "agentlab.blind_case_cut_receipt.v1",
            "cutId": format!("{node_id}-blind-v1"),
            "caseId": node["caseId"],
            "methodRevision": "1".repeat(40),
            "sourceSetSha256": node["sourceSetSha256"],
            "participantBundle": {
                "manifestSha256": digest(&fs::read(&participant_path).unwrap())
            },
            "evaluatorBundle": {
                "manifestSha256": digest(&fs::read(&evaluator_path).unwrap())
            },
            "boundary": {
                "physicallySeparatedRoots": true,
                "participantManifestContainsEvaluatorInventory": false
            },
            "freshness": {"eligibleForBlindPilot": true},
            "automaticPromotion": false
        }),
    );
    json!({
        "nodeId": node_id,
        "cutReceipt": file_binding(root, &receipt_path),
        "participantManifest": file_binding(root, &participant_path),
        "evaluatorManifest": file_binding(root, &evaluator_path)
    })
}

fn write_edge_qualification(
    root: &Path,
    graph_path: &Path,
    case_path: &Path,
    receipt_path: &Path,
    evidence_path: &Path,
) {
    fs::write(
        evidence_path,
        b"independent restore postconditions passed\n",
    )
    .unwrap();
    let graph = read(graph_path);
    let case = read(case_path);
    let graph_bytes = fs::read(graph_path).unwrap();
    let case_bytes = fs::read(case_path).unwrap();
    let edge = graph["edges"].as_array().unwrap().last().unwrap();
    let evidence_bytes = fs::read(evidence_path).unwrap();
    let agent_context_mode = match edge["forkPolicy"]["agent"].as_str().unwrap() {
        "fresh-agent" => "fresh",
        "preserve-native" => "native-preserved",
        "replace-agent" => "replaced",
        "semantic-transfer" => "semantic-transfer",
        _ => unreachable!(),
    };
    let identity = digest(format!("{}\0{}", digest(&graph_bytes), digest(&case_bytes)).as_bytes());
    write(
        receipt_path,
        &json!({
            "schema": "agentlab.case_edge_qualification.v1",
            "status": "qualified",
            "qualificationId": format!("case-edge-qualification-{}", &identity[..20]),
            "graph": {
                "graphId": graph["graphId"],
                "sha256": digest(&graph_bytes)
            },
            "edge": {
                "edgeId": edge["edgeId"],
                "fromNodeId": edge["fromNodeId"],
                "toNodeId": edge["toNodeId"],
                "derivationSha256": edge["derivation"]["sha256"]
            },
            "qualifiedCase": {
                "caseId": case["id"],
                "sourceSetSha256": case["sourceSetSha256"],
                "evaluationCaseSha256": digest(&case_bytes)
            },
            "forkPolicy": edge["forkPolicy"],
            "verification": {
                "authority": "independent-harness-restore-verification",
                "parentCutStateExposed": true,
                "parentPostCutChangesExcluded": true,
                "childContinuesIndependently": true,
                "workspacePolicySatisfied": true,
                "agentContextMode": agent_context_mode,
                "nativeSessionRestoreQualified": edge["forkPolicy"]["requiresNativeSessionQualification"],
                "evidence": [{
                    "path": evidence_path.strip_prefix(root).unwrap().to_string_lossy(),
                    "byteLength": evidence_bytes.len(),
                    "sha256": digest(&evidence_bytes)
                }]
            },
            "automaticPromotion": false
        }),
    );
}

struct Fixture {
    root: PathBuf,
    case: PathBuf,
    plan: PathBuf,
    summary: PathBuf,
    decision: PathBuf,
    initial: PathBuf,
    final_state: PathBuf,
    workspace: PathBuf,
    transcript: PathBuf,
    native: PathBuf,
    state: PathBuf,
    feedback: PathBuf,
    derivation: PathBuf,
    graph: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let root = temp_root();
        let case = root.join("case.json");
        let plan = root.join("plan.json");
        let summary = root.join("run/summary.json");
        let decision = root.join("run/decision-package.json");
        let initial = root.join("run/initial-source-state.json");
        let final_state = root.join("run/final-source-state.json");
        let workspace = root.join("run/workspace");
        let transcript = root.join("run/participant-protocol.json");
        let native = root.join("run/participant-state/pi-session.jsonl");
        let state = root.join("run/case-execution-state.json");
        let feedback = root.join("assessment-feedback-candidates.json");
        let derivation = root.join("case-derivation.json");
        let graph = root.join("case-model-graph.json");
        fs::create_dir_all(workspace.join("repo/src")).unwrap();
        fs::create_dir_all(native.parent().unwrap()).unwrap();
        fs::write(
            workspace.join("repo/src/lib.rs"),
            b"pub fn value() -> u8 { 2 }\n",
        )
        .unwrap();
        fs::write(&native, b"{\"type\":\"session\",\"id\":\"thread-one\"}\n").unwrap();
        write(&transcript, &json!({"events": [{"stageId": "turn-1"}]}));

        let file = workspace.join("repo/src/lib.rs");
        let bytes = fs::read(&file).unwrap();
        let mode = fs::metadata(&file).unwrap().permissions().mode() & 0o7777;
        let tree = json!({
            "repo/src/lib.rs": {
                "sha256": digest(&bytes),
                "byteLength": bytes.len(),
                "unixMode": mode,
            }
        });
        write(&initial, &tree);
        write(&final_state, &tree);
        write(
            &case,
            &json!({
                "schema": "agentlab.multi_repo_evaluation_case.v1",
                "status": "frozen-calibrated",
                "id": "case-one",
                "sourceSetSha256": "a".repeat(64),
                "calibration": {"qualified": true},
                "oracle": {"authority": "independent-executable-oracle"},
                "automaticPromotion": false,
            }),
        );
        write(
            &plan,
            &json!({
                "schema": "agentlab.participant_experiment_plan.v1",
                "status": "predeclared-before-attempts",
                "caseId": "case-one",
                "sourceSetSha256": "a".repeat(64),
                "evaluationCaseSha256": digest(&fs::read(&case).unwrap()),
                "participantProfiles": [
                    {"ordinal": 0, "participantId": "participant-a", "model": "model-a"}
                ],
                "executionProtocol": {
                    "agentImplementation": "pi",
                    "agentPackage": "@mariozechner/pi-coding-agent",
                    "agentPackageVersion": "0.73.1",
                    "runtimeImageId": format!("sha256:{}", "b".repeat(64)),
                    "sessionPolicy": "fresh-per-attempt-persistent-across-case-stages"
                },
                "automaticPromotion": false,
            }),
        );
        let stages = json!([{
            "stageId": "turn-1",
            "participantCompleted": true,
            "oraclePass": false,
            "scopeValid": true
        }]);
        write(
            &summary,
            &json!({
                "schema": "agentlab.multi_repo_assessment_summary.v1",
                "taskId": "case-one",
                "sourceSetSha256": "a".repeat(64),
                "participantId": "participant-a",
                "assessmentStatus": "assessed",
                "infrastructureAvailable": true,
                "subjectTaskSucceeded": false,
                "stages": stages,
                "initialWorkspaceSha256": canonical_digest(&tree),
                "finalWorkspaceSha256": canonical_digest(&tree)
            }),
        );
        write(
            &decision,
            &json!({
                "schema": "agentlab.harness_decision_package.v1",
                "taskId": "case-one",
                "sourceSetSha256": "a".repeat(64),
                "participantId": "participant-a",
                "assessmentStatus": "assessed",
                "infrastructureAvailable": true,
                "subjectTaskSucceeded": false,
                "phaseVerdicts": stages,
                "automaticPromotion": false
            }),
        );
        Self {
            root,
            case,
            plan,
            summary,
            decision,
            initial,
            final_state,
            workspace,
            transcript,
            native,
            state,
            feedback,
            derivation,
            graph,
        }
    }

    fn compose(&self, include_native: bool) -> Output {
        let mut command = Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"));
        command.args([
            "compose",
            "--root",
            self.root.to_str().unwrap(),
            "--case",
            self.case.to_str().unwrap(),
            "--experiment-plan",
            self.plan.to_str().unwrap(),
            "--attempt-summary",
            self.summary.to_str().unwrap(),
            "--decision-package",
            self.decision.to_str().unwrap(),
            "--initial-state",
            self.initial.to_str().unwrap(),
            "--final-state",
            self.final_state.to_str().unwrap(),
            "--workspace",
            self.workspace.to_str().unwrap(),
            "--event-log",
            self.transcript.to_str().unwrap(),
            "--attempt-id",
            "tier-00-1",
            "--output",
            self.state.to_str().unwrap(),
        ]);
        if include_native {
            command.args(["--native-session", self.native.to_str().unwrap()]);
        }
        command.output().unwrap()
    }

    fn write_feedback(&self) {
        write(
            &self.feedback,
            &json!({
                "schema": "agentlab.assessment_feedback_candidates.v1",
                "caseId": "case-one",
                "sourceSetSha256": "a".repeat(64),
                "candidates": [{
                    "id": "feedback-one",
                    "dimensionId": "assessed-agent-stage-failure",
                    "stageId": "turn-1",
                    "failureMode": "oracle-failed",
                    "mechanism": "oracle-failed at frozen stage turn-1",
                    "observations": [{
                        "attemptId": "tier-00-1",
                        "participantId": "participant-a",
                        "decisionPackageSha256": digest(&fs::read(&self.decision).unwrap())
                    }],
                    "verificationContract": {"caseReady": false},
                    "automaticPromotion": false
                }],
                "policy": {"automaticPromotion": false}
            }),
        );
    }

    fn derive(&self, mode: &str) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"))
            .args([
                "derive",
                "--root",
                self.root.to_str().unwrap(),
                "--state",
                self.state.to_str().unwrap(),
                "--feedback",
                self.feedback.to_str().unwrap(),
                "--candidate-id",
                "feedback-one",
                "--mode",
                mode,
                "--output",
                self.derivation.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn graph(
        &self,
        parent_case: &Path,
        derivation: &Path,
        prior: Option<&Path>,
        output: &Path,
    ) -> Output {
        let mut command = Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"));
        command.args([
            "graph",
            "--root",
            self.root.to_str().unwrap(),
            "--parent-case",
            parent_case.to_str().unwrap(),
            "--derivation",
            derivation.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
        ]);
        if let Some(prior) = prior {
            command.args(["--graph", prior.to_str().unwrap()]);
        }
        command.output().unwrap()
    }

    fn qualify(
        &self,
        graph: &Path,
        qualified_case: &Path,
        receipt: &Path,
        output: &Path,
    ) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"))
            .args([
                "qualify",
                "--root",
                self.root.to_str().unwrap(),
                "--graph",
                graph.to_str().unwrap(),
                "--qualified-case",
                qualified_case.to_str().unwrap(),
                "--edge-qualification",
                receipt.to_str().unwrap(),
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn freeze_path(&self, graph: &Path, path_inputs: &Path, output: &Path) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"))
            .args([
                "freeze-path",
                "--root",
                self.root.to_str().unwrap(),
                "--graph",
                graph.to_str().unwrap(),
                "--path-inputs",
                path_inputs.to_str().unwrap(),
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn predeclare_path(&self, path_plan: &Path, matrix: &Path, output: &Path) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"))
            .args([
                "predeclare-path",
                "--root",
                self.root.to_str().unwrap(),
                "--path-plan",
                path_plan.to_str().unwrap(),
                "--participant-matrix",
                matrix.to_str().unwrap(),
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn qualify_dispatch(&self, dispatch: &Path, receipt: &Path, output: &Path) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"))
            .args([
                "qualify-dispatch",
                "--root",
                self.root.to_str().unwrap(),
                "--dispatch-plan",
                dispatch.to_str().unwrap(),
                "--dispatch-qualification",
                receipt.to_str().unwrap(),
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }

    fn record_attempt(&self, qualified: &Path, input: &Path, output: &Path) -> Output {
        Command::new(env!("CARGO_BIN_EXE_agentlab-case-state"))
            .args([
                "record-attempt",
                "--root",
                self.root.to_str().unwrap(),
                "--qualified-dispatch",
                qualified.to_str().unwrap(),
                "--attempt-input",
                input.to_str().unwrap(),
                "--output",
                output.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }
}

#[test]
fn composes_digest_bound_state_without_changing_existing_contracts() {
    let fixture = Fixture::new();
    let result = fixture.compose(true);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let state = read(&fixture.state);
    assert_eq!(state["schema"], "agentlab.case_execution_state.v1");
    assert_eq!(state["execution"]["outcome"], "fail");
    assert_eq!(
        state["agent"]["context"]["mode"],
        "native-session-candidate"
    );
    assert_eq!(
        state["restoreCapabilities"]["profile"],
        "native-continuation-candidate"
    );
    assert_eq!(state["verification"]["agentContextRestoreVerified"], false);
    assert_eq!(state["automaticPromotion"], false);
    assert_eq!(
        state["workspace"]["capturedTree"]["treeSha256"],
        read(&fixture.summary)["finalWorkspaceSha256"]
    );
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn rejects_plan_that_does_not_bind_exact_case_bytes() {
    let fixture = Fixture::new();
    let mut plan = read(&fixture.plan);
    plan["evaluationCaseSha256"] = json!("f".repeat(64));
    write(&fixture.plan, &plan);
    let result = fixture.compose(false);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("evaluation case digest differs"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
#[cfg(unix)]
fn rejects_symlinked_evidence_input() {
    use std::os::unix::fs::symlink;

    let fixture = Fixture::new();
    let real_plan = fixture.root.join("real-plan.json");
    fs::rename(&fixture.plan, &real_plan).unwrap();
    symlink(&real_plan, &fixture.plan).unwrap();
    let result = fixture.compose(false);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("regular non-symlink file"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn creates_review_required_same_agent_derivation_without_promoting_case() {
    let fixture = Fixture::new();
    assert!(fixture.compose(true).status.success());
    fixture.write_feedback();
    let result = fixture.derive("same-agent-continuation");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let derivation = read(&fixture.derivation);
    assert_eq!(derivation["schema"], "agentlab.case_derivation.v1");
    assert_eq!(derivation["status"], "review-required");
    assert_eq!(derivation["forkPolicy"]["agent"], "preserve-native");
    assert_eq!(
        derivation["forkPolicy"]["requiresNativeSessionQualification"],
        true
    );
    assert_eq!(
        derivation["qualification"]["agentContextRequalified"],
        false
    );
    assert_eq!(derivation["childCase"]["caseReady"], false);
    assert!(derivation["childCase"]["candidateCaseId"]
        .as_str()
        .unwrap()
        .starts_with("case-candidate-"));
    assert_eq!(derivation["automaticPromotion"], false);
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn models_a_qualified_intermediate_case_before_extending_the_difficulty_chain() {
    let fixture = Fixture::new();
    assert!(fixture.compose(true).status.success());
    fixture.write_feedback();
    assert!(fixture.derive("fresh-agent-continuation").status.success());
    let first = fixture.graph(&fixture.case, &fixture.derivation, None, &fixture.graph);
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    let first_graph = read(&fixture.graph);
    assert_eq!(first_graph["summary"]["maximumDepth"], 1);
    assert_eq!(first_graph["summary"]["maximumQualifiedDepth"], 0);
    assert_eq!(first_graph["summary"]["longHorizonReady"], false);

    let first_derivation = read(&fixture.derivation);
    let intermediate_id = first_derivation["childCase"]["candidateCaseId"]
        .as_str()
        .unwrap();
    let intermediate_case = fixture.root.join("qualified-intermediate-case.json");
    let mut qualified = read(&fixture.case);
    qualified["id"] = json!("qualified-child-case");
    qualified["difficultyId"] = json!("analysis-difficulty-two");
    qualified["sourceSetSha256"] = json!("c".repeat(64));
    qualified["lineage"] = json!({
        "feedbackAnalysisCut": {"feedbackCandidateId": "feedback-one"}
    });
    write(&intermediate_case, &qualified);

    let unqualified_extension = fixture.root.join("unqualified-extension.json");
    let qualification = fixture.root.join("first-edge-qualification.json");
    let qualification_evidence = fixture.root.join("first-edge-verification.log");
    write_edge_qualification(
        &fixture.root,
        &fixture.graph,
        &intermediate_case,
        &qualification,
        &qualification_evidence,
    );
    let qualified_graph = fixture.root.join("qualified-first-graph.json");
    let qualified_result = fixture.qualify(
        &fixture.graph,
        &intermediate_case,
        &qualification,
        &qualified_graph,
    );
    assert!(
        qualified_result.status.success(),
        "{}",
        String::from_utf8_lossy(&qualified_result.stderr)
    );
    let qualified_first = read(&qualified_graph);
    assert_eq!(qualified_first["summary"]["maximumQualifiedDepth"], 1);
    assert_eq!(
        qualified_first["qualification"]["allEdgesRestoreQualified"],
        true
    );
    assert_eq!(qualified_first["summary"]["longHorizonReady"], false);
    fs::write(&qualification_evidence, b"tampered restore evidence\n").unwrap();
    let tampered_output = fixture.root.join("tampered-qualified-graph.json");
    let tampered = fixture.qualify(
        &fixture.graph,
        &intermediate_case,
        &qualification,
        &tampered_output,
    );
    assert!(!tampered.status.success());
    assert!(String::from_utf8_lossy(&tampered.stderr).contains("declared binding"));

    let second_derivation = fixture.root.join("second-derivation.json");
    write(
        &second_derivation,
        &json!({
            "schema": "agentlab.case_derivation.v1",
            "status": "review-required",
            "parentCase": {
                "caseId": "qualified-child-case",
                "sourceSetSha256": "c".repeat(64),
                "evaluationCaseSha256": digest(&fs::read(&intermediate_case).unwrap())
            },
            "childCase": {
                "candidateCaseId": "case-candidate-22222222222222222222",
                "status": "candidate",
                "requestedRestoreProfile": "source-continuation",
                "caseReady": false
            },
            "difficulty": {
                "candidateId": "feedback-two",
                "dimensionId": "assessed-agent-stage-failure",
                "stageId": "turn-2",
                "failureMode": "oracle-failure",
                "mechanism": "second independently observed difficulty",
                "evidenceAttemptId": "tier-01-1"
            },
            "forkPolicy": {
                "agent": "fresh-agent",
                "workspace": "restore-captured-tree",
                "requiresNativeSessionQualification": false
            },
            "automaticPromotion": false
        }),
    );
    let rejected = fixture.graph(
        &intermediate_case,
        &second_derivation,
        Some(&fixture.graph),
        &unqualified_extension,
    );
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("edge receipt before extension"));

    let extended = fixture.root.join("extended-case-model-graph.json");
    let result = fixture.graph(
        &intermediate_case,
        &second_derivation,
        Some(&qualified_graph),
        &extended,
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let graph = read(&extended);
    assert_eq!(graph["summary"]["maximumDepth"], 2);
    assert_eq!(graph["summary"]["maximumQualifiedDepth"], 1);
    assert_eq!(graph["summary"]["qualifiedNodeCount"], 2);
    assert_eq!(graph["summary"]["longHorizonReady"], false);
    assert!(graph["nodes"].as_array().unwrap().iter().any(|node| {
        node["caseId"] == "qualified-child-case"
            && node["provisionalCaseId"] == intermediate_id
            && node["kind"] == "derived-qualified-case"
    }));

    let final_case = fixture.root.join("qualified-final-case.json");
    let mut final_value = read(&fixture.case);
    final_value["id"] = json!("qualified-grandchild-case");
    final_value["difficultyId"] = json!("feedback-two");
    final_value["sourceSetSha256"] = json!("d".repeat(64));
    write(&final_case, &final_value);
    let final_qualification = fixture.root.join("second-edge-qualification.json");
    let final_evidence = fixture.root.join("second-edge-verification.log");
    write_edge_qualification(
        &fixture.root,
        &extended,
        &final_case,
        &final_qualification,
        &final_evidence,
    );
    let ready_graph = fixture.root.join("ready-case-model-graph.json");
    let ready_result = fixture.qualify(&extended, &final_case, &final_qualification, &ready_graph);
    assert!(
        ready_result.status.success(),
        "{}",
        String::from_utf8_lossy(&ready_result.stderr)
    );
    let ready = read(&ready_graph);
    assert_eq!(ready["summary"]["maximumQualifiedDepth"], 2);
    assert_eq!(ready["summary"]["longHorizonReady"], true);
    assert_eq!(
        ready["summary"]["readyPathNodeIds"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(ready["nextGate"], "select-qualified-path-for-execution");

    let branch_derivation = fixture.root.join("branch-derivation.json");
    let mut branch = read(&second_derivation);
    branch["parentCase"] = json!({
        "caseId": "case-one",
        "sourceSetSha256": "a".repeat(64),
        "evaluationCaseSha256": digest(&fs::read(&fixture.case).unwrap())
    });
    branch["childCase"]["candidateCaseId"] = json!("case-candidate-33333333333333333333");
    branch["difficulty"]["candidateId"] = json!("feedback-branch");
    write(&branch_derivation, &branch);
    let branched_graph = fixture.root.join("branched-ready-case-model-graph.json");
    let branch_result = fixture.graph(
        &fixture.case,
        &branch_derivation,
        Some(&ready_graph),
        &branched_graph,
    );
    assert!(
        branch_result.status.success(),
        "{}",
        String::from_utf8_lossy(&branch_result.stderr)
    );
    let branched = read(&branched_graph);
    assert_eq!(branched["summary"]["longHorizonReady"], true);
    assert_eq!(
        branched["summary"]["readyPathNodeIds"],
        ready["summary"]["readyPathNodeIds"]
    );
    assert_eq!(branched["qualification"]["allNodesScenarioAuthored"], false);

    let terminal = branched["summary"]["readyPathNodeIds"][0].as_str().unwrap();
    let mut path_nodes: Vec<&Value> = branched["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|node| node["executable"] == true && node["depth"].as_u64().unwrap() <= 2)
        .collect();
    path_nodes.sort_by_key(|node| node["depth"].as_u64().unwrap());
    let blind_cuts: Vec<Value> = path_nodes
        .iter()
        .map(|node| write_blind_cut(&fixture.root, node))
        .collect();
    let path_inputs = fixture.root.join("case-path-inputs.json");
    write(
        &path_inputs,
        &json!({
            "schema": "agentlab.case_path_inputs.v1",
            "graph": {
                "graphId": branched["graphId"],
                "sha256": digest(&fs::read(&branched_graph).unwrap())
            },
            "terminalNodeId": terminal,
            "blindCuts": blind_cuts,
            "automaticPromotion": false
        }),
    );
    let path_plan = fixture.root.join("case-path-execution-plan.json");
    let freeze = fixture.freeze_path(&branched_graph, &path_inputs, &path_plan);
    assert!(
        freeze.status.success(),
        "{}",
        String::from_utf8_lossy(&freeze.stderr)
    );
    let plan = read(&path_plan);
    assert_eq!(plan["schema"], "agentlab.case_path_execution_plan.v1");
    assert_eq!(plan["difficultyDepth"], 2);
    assert_eq!(plan["stages"].as_array().unwrap().len(), 3);
    assert!(plan["stages"][0]["incomingTransition"].is_null());
    assert_eq!(
        plan["stages"][1]["incomingTransition"]["forkPolicy"]["agent"],
        "fresh-agent"
    );
    assert_eq!(plan["qualification"]["readyForExecution"], false);
    assert_eq!(plan["automaticPromotion"], false);

    let adapter = fixture.root.join("runtime/participant-adapter.mjs");
    let driver = fixture.root.join("runtime/participant-driver.mjs");
    let environment_lock = fixture.root.join("runtime/environment.lock.json");
    fs::create_dir_all(adapter.parent().unwrap()).unwrap();
    fs::write(&adapter, b"export const adapter = 'v1';\n").unwrap();
    fs::write(&driver, b"export const driver = 'v1';\n").unwrap();
    fs::write(&environment_lock, b"{\"runtime\":\"frozen\"}\n").unwrap();
    let matrix = fixture.root.join("case-path-participant-matrix.json");
    write(
        &matrix,
        &json!({
            "schema": "agentlab.case_path_participant_matrix.v1",
            "status": "predeclared-before-attempts",
            "pathPlan": {
                "planId": plan["planId"],
                "sha256": digest(&fs::read(&path_plan).unwrap())
            },
            "methodRevision": "2".repeat(40),
            "trialsPerCell": 3,
            "agentConfigurations": [
                {
                    "agentConfigId": "agent-pi",
                    "implementation": "pi",
                    "package": "@mariozechner/pi-coding-agent",
                    "packageVersion": "0.73.1",
                    "adapter": file_binding(&fixture.root, &adapter),
                    "driver": file_binding(&fixture.root, &driver),
                    "sessionPolicy": "fresh-per-trial-path-transitions-bound"
                },
                {
                    "agentConfigId": "agent-reference",
                    "implementation": "reference-agent",
                    "package": "agentlab-reference-agent",
                    "packageVersion": "1.0.0",
                    "adapter": file_binding(&fixture.root, &adapter),
                    "driver": file_binding(&fixture.root, &driver),
                    "sessionPolicy": "fresh-per-trial-path-transitions-bound"
                }
            ],
            "modelConfigurations": [
                {
                    "modelConfigId": "model-a",
                    "providerRoute": "gateway-a",
                    "model": "model-a",
                    "thinkingMode": "off",
                    "reasoningEffort": null,
                    "samplingPolicy": "provider-default-stochastic-repeated-trials"
                },
                {
                    "modelConfigId": "model-b",
                    "providerRoute": "gateway-a",
                    "model": "model-b",
                    "thinkingMode": "off",
                    "reasoningEffort": null,
                    "samplingPolicy": "provider-default-stochastic-repeated-trials"
                }
            ],
            "environmentConfigurations": [{
                "environmentConfigId": "env-linux-x64",
                "runtimeImageId": format!("sha256:{}", "3".repeat(64)),
                "architecture": "x86_64",
                "environmentLock": file_binding(&fixture.root, &environment_lock)
            }],
            "cells": [
                {
                    "ordinal": 0,
                    "participantId": "participant-pi-model-a",
                    "agentConfigId": "agent-pi",
                    "modelConfigId": "model-a",
                    "environmentConfigId": "env-linux-x64"
                },
                {
                    "ordinal": 1,
                    "participantId": "participant-pi-model-b",
                    "agentConfigId": "agent-pi",
                    "modelConfigId": "model-b",
                    "environmentConfigId": "env-linux-x64"
                },
                {
                    "ordinal": 2,
                    "participantId": "participant-reference-model-b",
                    "agentConfigId": "agent-reference",
                    "modelConfigId": "model-b",
                    "environmentConfigId": "env-linux-x64"
                }
            ],
            "comparisonPairs": [
                {
                    "leftParticipantId": "participant-pi-model-a",
                    "rightParticipantId": "participant-pi-model-b",
                    "changedDimension": "model"
                },
                {
                    "leftParticipantId": "participant-pi-model-b",
                    "rightParticipantId": "participant-reference-model-b",
                    "changedDimension": "agent"
                }
            ],
            "automaticPromotion": false
        }),
    );
    let dispatch_plan = fixture.root.join("case-path-dispatch-plan.json");
    let predeclare = fixture.predeclare_path(&path_plan, &matrix, &dispatch_plan);
    assert!(
        predeclare.status.success(),
        "{}",
        String::from_utf8_lossy(&predeclare.stderr)
    );
    let dispatch = read(&dispatch_plan);
    assert_eq!(dispatch["schema"], "agentlab.case_path_dispatch_plan.v1");
    assert_eq!(dispatch["stageCount"], 3);
    assert_eq!(dispatch["cellCount"], 3);
    assert_eq!(dispatch["expectedAttemptCount"], 9);
    assert_eq!(dispatch["expectedStageExecutionCount"], 27);
    assert_eq!(dispatch["qualification"]["readyForDispatch"], false);
    assert_eq!(dispatch["automaticPromotion"], false);

    let qualification_path = fixture.root.join("case-path-dispatch-qualification.json");
    let mut qualified_cells = Vec::new();
    for cell in dispatch["cells"].as_array().unwrap() {
        let participant = cell["participantId"].as_str().unwrap();
        let runtime = fixture
            .root
            .join(format!("runtime-evidence/{participant}.json"));
        let blind = fixture
            .root
            .join(format!("blind-dispatch-evidence/{participant}.json"));
        fs::create_dir_all(runtime.parent().unwrap()).unwrap();
        fs::create_dir_all(blind.parent().unwrap()).unwrap();
        fs::write(
            &runtime,
            format!("{{\"participant\":\"{participant}\",\"runtime\":\"started\"}}\n"),
        )
        .unwrap();
        fs::write(
            &blind,
            format!("{{\"participant\":\"{participant}\",\"blind\":\"isolated\"}}\n"),
        )
        .unwrap();
        qualified_cells.push(json!({
            "participantId": participant,
            "environmentConfigId": cell["environmentConfigId"],
            "runtimeImageId": format!("sha256:{}", "3".repeat(64)),
            "runtimeEvidence": file_binding(&fixture.root, &runtime),
            "blindDispatchEvidence": file_binding(&fixture.root, &blind),
            "verification": {
                "portableRuntimeStarted": true,
                "currentStageParticipantBundleOnly": true,
                "evaluatorBundleOutsideParticipant": true,
                "networkPolicyEnforced": true,
                "freshTrialBoundaryVerified": true
            }
        }));
    }
    write(
        &qualification_path,
        &json!({
            "schema": "agentlab.case_path_dispatch_qualification.v1",
            "status": "qualified",
            "authority": "independent-harness-runtime-and-blind-dispatch",
            "dispatchPlan": {
                "dispatchPlanId": dispatch["dispatchPlanId"],
                "sha256": digest(&fs::read(&dispatch_plan).unwrap())
            },
            "methodRevision": dispatch["methodRevision"],
            "cells": qualified_cells,
            "automaticPromotion": false
        }),
    );
    let qualified_dispatch = fixture.root.join("case-path-qualified-dispatch.json");
    let qualification =
        fixture.qualify_dispatch(&dispatch_plan, &qualification_path, &qualified_dispatch);
    assert!(
        qualification.status.success(),
        "{}",
        String::from_utf8_lossy(&qualification.stderr)
    );
    let qualified_value = read(&qualified_dispatch);
    assert_eq!(
        qualified_value["schema"],
        "agentlab.case_path_qualified_dispatch.v1"
    );
    assert_eq!(qualified_value["qualification"]["readyForDispatch"], true);
    assert_eq!(qualified_value["automaticPromotion"], false);

    let attempt_root = fixture.root.join("attempts/attempt-1");
    fs::create_dir_all(&attempt_root).unwrap();
    let mut attempt_stages = Vec::new();
    for ordinal in 0..2 {
        let pre = attempt_root.join(format!("stage-{ordinal}-pre.json"));
        let post = attempt_root.join(format!("stage-{ordinal}-post.json"));
        let check = attempt_root.join(format!("stage-{ordinal}-check.json"));
        fs::write(
            &pre,
            format!("{{\"stage\":{ordinal},\"moment\":\"pre\"}}\n"),
        )
        .unwrap();
        fs::write(
            &post,
            format!("{{\"stage\":{ordinal},\"moment\":\"post\"}}\n"),
        )
        .unwrap();
        fs::write(
            &check,
            format!("{{\"stage\":{ordinal},\"oracle\":\"pass\"}}\n"),
        )
        .unwrap();
        let transition = if ordinal == 0 {
            Value::Null
        } else {
            let path = attempt_root.join("stage-1-transition.json");
            fs::write(&path, b"{\"restore\":\"passed\"}\n").unwrap();
            file_binding(&fixture.root, &path)
        };
        let resource = if ordinal == 0 {
            json!({"status": "not-measured", "dimensions": [], "metricsEvidence": null})
        } else {
            let metrics = attempt_root.join("stage-1-metrics.json");
            fs::write(&metrics, b"{\"performance\":\"regressed\"}\n").unwrap();
            json!({
                "status": "violation",
                "dimensions": ["performance"],
                "metricsEvidence": file_binding(&fixture.root, &metrics)
            })
        };
        attempt_stages.push(json!({
            "ordinal": ordinal,
            "nodeId": plan["stages"][ordinal]["nodeId"],
            "caseId": plan["stages"][ordinal]["caseId"],
            "preState": file_binding(&fixture.root, &pre),
            "postState": file_binding(&fixture.root, &post),
            "transitionEvidence": transition,
            "functionalVerdict": "pass",
            "checks": [{
                "checkId": format!("oracle-stage-{ordinal}"),
                "verdict": "pass",
                "evidence": file_binding(&fixture.root, &check)
            }],
            "resourceObservation": resource
        }));
    }
    let attempt_input = fixture.root.join("case-path-attempt-input.json");
    write(
        &attempt_input,
        &json!({
            "schema": "agentlab.case_path_attempt_input.v1",
            "status": "completed",
            "qualifiedDispatch": {
                "qualifiedDispatchId": qualified_value["qualifiedDispatchId"],
                "sha256": digest(&fs::read(&qualified_dispatch).unwrap())
            },
            "attemptId": "participant-pi-model-a-trial-1",
            "participantId": "participant-pi-model-a",
            "trialOrdinal": 1,
            "stages": attempt_stages,
            "automaticPromotion": false
        }),
    );
    let attempt_record = fixture.root.join("case-path-attempt-record.json");
    let recorded = fixture.record_attempt(&qualified_dispatch, &attempt_input, &attempt_record);
    assert!(
        recorded.status.success(),
        "{}",
        String::from_utf8_lossy(&recorded.stderr)
    );
    let record = read(&attempt_record);
    assert_eq!(record["schema"], "agentlab.case_path_attempt_record.v1");
    assert_eq!(record["status"], "assessed-failure");
    assert_eq!(record["overallVerdict"], "fail");
    assert_eq!(record["executedStageCount"], 2);
    assert_eq!(
        record["nextDifficultyCandidate"]["failureClass"],
        "resource"
    );
    assert_eq!(record["nextDifficultyCandidate"]["caseReady"], false);
    assert_eq!(record["automaticPromotion"], false);

    let invalid_matrix = fixture.root.join("invalid-participant-matrix.json");
    let mut invalid = read(&matrix);
    invalid["comparisonPairs"][0]["changedDimension"] = json!("agent");
    write(&invalid_matrix, &invalid);
    let invalid_dispatch = fixture.root.join("invalid-dispatch-plan.json");
    let rejected_matrix = fixture.predeclare_path(&path_plan, &invalid_matrix, &invalid_dispatch);
    assert!(!rejected_matrix.status.success());
    assert!(
        String::from_utf8_lossy(&rejected_matrix.stderr).contains("exactly its declared dimension")
    );

    let forged_path_plan = fixture.root.join("forged-case-path-plan.json");
    let mut forged_plan = read(&path_plan);
    forged_plan["qualification"]["readyForExecution"] = json!(true);
    write(&forged_path_plan, &forged_plan);
    let forged_matrix = fixture.root.join("forged-path-participant-matrix.json");
    let mut forged_matrix_value = read(&matrix);
    forged_matrix_value["pathPlan"]["sha256"] =
        json!(digest(&fs::read(&forged_path_plan).unwrap()));
    write(&forged_matrix, &forged_matrix_value);
    let forged_dispatch = fixture.root.join("forged-dispatch-plan.json");
    let rejected_plan =
        fixture.predeclare_path(&forged_path_plan, &forged_matrix, &forged_dispatch);
    assert!(!rejected_plan.status.success());
    assert!(String::from_utf8_lossy(&rejected_plan.stderr)
        .contains("execution plan qualification is invalid"));

    fs::write(
        fixture
            .root
            .join("blind-cuts")
            .join(path_nodes[0]["nodeId"].as_str().unwrap())
            .join("participant/unbound.txt"),
        b"must not enter participant bundle\n",
    )
    .unwrap();
    let leaked_plan = fixture.root.join("leaked-case-path-plan.json");
    let leaked = fixture.freeze_path(&branched_graph, &path_inputs, &leaked_plan);
    assert!(!leaked.status.success());
    assert!(String::from_utf8_lossy(&leaked.stderr).contains("outside its manifest"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn same_agent_derivation_fails_without_native_session_capture() {
    let fixture = Fixture::new();
    assert!(fixture.compose(false).status.success());
    fixture.write_feedback();
    let result = fixture.derive("same-agent-continuation");
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("captured native session"));
    fs::remove_dir_all(fixture.root).unwrap();
}

#[test]
fn schemas_are_strict_and_match_tool_outputs() {
    let root = repository();
    for (path, expected) in [
        (
            "schemas/case-execution-state.schema.json",
            "agentlab.case_execution_state.v1",
        ),
        (
            "schemas/case-derivation.schema.json",
            "agentlab.case_derivation.v1",
        ),
        (
            "schemas/case-model-graph.schema.json",
            "agentlab.case_model_graph.v1",
        ),
        (
            "schemas/case-edge-qualification.schema.json",
            "agentlab.case_edge_qualification.v1",
        ),
        (
            "schemas/case-path-inputs.schema.json",
            "agentlab.case_path_inputs.v1",
        ),
        (
            "schemas/case-path-execution-plan.schema.json",
            "agentlab.case_path_execution_plan.v1",
        ),
        (
            "schemas/case-path-participant-matrix.schema.json",
            "agentlab.case_path_participant_matrix.v1",
        ),
        (
            "schemas/case-path-dispatch-plan.schema.json",
            "agentlab.case_path_dispatch_plan.v1",
        ),
        (
            "schemas/case-path-dispatch-qualification.schema.json",
            "agentlab.case_path_dispatch_qualification.v1",
        ),
        (
            "schemas/case-path-qualified-dispatch.schema.json",
            "agentlab.case_path_qualified_dispatch.v1",
        ),
        (
            "schemas/case-path-attempt-input.schema.json",
            "agentlab.case_path_attempt_input.v1",
        ),
        (
            "schemas/case-path-attempt-record.schema.json",
            "agentlab.case_path_attempt_record.v1",
        ),
    ] {
        let schema = read(&root.join(path));
        assert_eq!(schema["additionalProperties"], false);
        assert_eq!(schema["properties"]["schema"]["const"], expected);
        assert_eq!(schema["properties"]["automaticPromotion"]["const"], false);
    }
}

#[test]
fn assessed_campaign_keeps_state_and_derivation_as_shadow_sidecars() {
    let workflow =
        fs::read_to_string(repository().join(".github/workflows/multi-repo-assessed-campaign.yml"))
            .unwrap();
    assert!(workflow.contains("Compose digest-bound execution states in shadow mode"));
    assert!(workflow.contains("Propose execution-state derived cases in shadow mode"));
    assert!(workflow.contains("--bin agentlab-case-state"));
    assert!(workflow.contains("agentlab-case-state compose"));
    assert!(workflow.contains("agentlab-case-state derive"));
    assert!(workflow.contains("agentlab-case-state graph"));
    assert!(workflow.contains("--mode fresh-agent-continuation"));
    assert!(workflow.matches("continue-on-error: true").count() >= 2);
    assert!(workflow.contains("${{ env.AGENTLAB_ROOT }}/"));
}
