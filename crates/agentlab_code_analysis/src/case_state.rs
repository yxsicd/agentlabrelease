use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Component, Path, PathBuf};

const STATE_SCHEMA: &str = "agentlab.case_execution_state.v1";
const DERIVATION_SCHEMA: &str = "agentlab.case_derivation.v1";
const GRAPH_SCHEMA: &str = "agentlab.case_model_graph.v1";
const EDGE_QUALIFICATION_SCHEMA: &str = "agentlab.case_edge_qualification.v1";
const PATH_INPUTS_SCHEMA: &str = "agentlab.case_path_inputs.v1";
const PATH_PLAN_SCHEMA: &str = "agentlab.case_path_execution_plan.v1";
const PATH_MATRIX_SCHEMA: &str = "agentlab.case_path_participant_matrix.v1";
const PATH_DISPATCH_SCHEMA: &str = "agentlab.case_path_dispatch_plan.v1";
const PATH_DISPATCH_QUALIFICATION_SCHEMA: &str = "agentlab.case_path_dispatch_qualification.v1";
const PATH_QUALIFIED_DISPATCH_SCHEMA: &str = "agentlab.case_path_qualified_dispatch.v1";

struct Input {
    relative: String,
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(root: &Path, path: PathBuf, label: &str) -> Result<Self, String> {
        let source_metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !source_metadata.file_type().is_file() || source_metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular non-symlink file"));
        }
        let path = path
            .canonicalize()
            .map_err(|error| format!("cannot resolve {label}: {error}"))?;
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular non-symlink file"));
        }
        let relative = relative(root, &path, label)?;
        let bytes = fs::read(&path).map_err(|error| format!("cannot read {label}: {error}"))?;
        if bytes.is_empty() {
            return Err(format!("{label} must not be empty"));
        }
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("cannot parse {label}: {error}"))?;
        if !value.is_object() {
            return Err(format!("{label} must be a JSON object"));
        }
        Ok(Self {
            relative,
            bytes,
            value,
        })
    }

    fn binding(&self) -> Value {
        json!({
            "path": self.relative,
            "byteLength": self.bytes.len(),
            "sha256": digest(&self.bytes),
        })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }
}

fn relative(root: &Path, path: &Path, label: &str) -> Result<String, String> {
    path.strip_prefix(root)
        .map_err(|_| format!("{label} must stay below --root"))
        .map(|value| value.to_string_lossy().replace('\\', "/"))
        .and_then(|value| {
            if value.is_empty() || value.starts_with("../") {
                Err(format!("{label} has an invalid relative path"))
            } else {
                Ok(value)
            }
        })
}

fn regular_binding(root: &Path, path: PathBuf, label: &str) -> Result<Value, String> {
    let source_metadata =
        fs::symlink_metadata(&path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !source_metadata.file_type().is_file() || source_metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular non-symlink file"));
    }
    let path = path
        .canonicalize()
        .map_err(|error| format!("cannot resolve {label}: {error}"))?;
    let metadata =
        fs::symlink_metadata(&path).map_err(|error| format!("cannot inspect {label}: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!("{label} must be a regular non-symlink file"));
    }
    let bytes = fs::read(&path).map_err(|error| format!("cannot read {label}: {error}"))?;
    if bytes.is_empty() {
        return Err(format!("{label} must not be empty"));
    }
    Ok(json!({
        "path": relative(root, &path, label)?,
        "byteLength": bytes.len(),
        "sha256": digest(&bytes),
    }))
}

fn verify_declared_binding(root: &Path, binding: &Value, label: &str) -> Result<(), String> {
    let declared_path = text(binding, "path", label)?;
    let actual = regular_binding(root, root.join(declared_path), label)?;
    require(
        actual == *binding,
        format!("{label} bytes differ from declared binding"),
    )
}

fn load_declared_input(root: &Path, binding: &Value, label: &str) -> Result<Input, String> {
    verify_declared_binding(root, binding, label)?;
    Input::load(root, root.join(text(binding, "path", label)?), label)
}

fn validate_blind_inventory(
    root: &Path,
    manifest: &Input,
    allowed_roles: &[&str],
    label: &str,
) -> Result<BTreeSet<String>, String> {
    let bundle_root = root
        .join(&manifest.relative)
        .parent()
        .ok_or_else(|| format!("{label} has no bundle root"))?
        .to_path_buf();
    let files = manifest.value["files"]
        .as_array()
        .filter(|items| !items.is_empty())
        .ok_or_else(|| format!("{label} file inventory is absent"))?;
    let mut declared_paths = BTreeSet::new();
    let mut hashes = BTreeSet::new();
    for (index, file) in files.iter().enumerate() {
        let file_label = format!("{label} file {index}");
        let relative_path = text(file, "path", &file_label)?;
        let relative = Path::new(relative_path);
        require(
            !relative.is_absolute()
                && relative
                    .components()
                    .all(|component| matches!(component, Component::Normal(_))),
            format!("{file_label} path escapes its bundle"),
        )?;
        require(
            declared_paths.insert(relative_path.to_owned()),
            format!("{label} duplicates file path {relative_path}"),
        )?;
        let role = text(file, "role", &file_label)?;
        require(
            allowed_roles.contains(&role),
            format!("{file_label} role is not allowed"),
        )?;
        let actual = regular_binding(root, bundle_root.join(relative), &file_label)?;
        require(
            file["sha256"] == actual["sha256"]
                && file["bytes"].as_u64() == actual["byteLength"].as_u64(),
            format!("{file_label} bytes differ from manifest"),
        )?;
        hashes.insert(text(&actual, "sha256", &file_label)?.to_owned());
    }
    let mut observed_paths = BTreeSet::new();
    let mut stack = vec![bundle_root.clone()];
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory)
            .map_err(|error| format!("cannot read {label} directory: {error}"))?
        {
            let path = entry
                .map_err(|error| format!("cannot read {label} entry: {error}"))?
                .path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| format!("cannot inspect {label} entry: {error}"))?;
            if metadata.file_type().is_dir() {
                require(
                    !metadata.file_type().is_symlink(),
                    format!("{label} contains a symlink"),
                )?;
                stack.push(path);
            } else {
                require(
                    metadata.file_type().is_file() && !metadata.file_type().is_symlink(),
                    format!("{label} contains a non-regular entry"),
                )?;
                let relative = path
                    .strip_prefix(&bundle_root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                if relative != "manifest.json" {
                    observed_paths.insert(relative);
                }
            }
        }
    }
    require(
        observed_paths == declared_paths,
        format!("{label} contains files outside its manifest"),
    )?;
    Ok(hashes)
}

fn require(condition: bool, message: impl Into<String>) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(message.into())
    }
}

fn valid_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 200
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(byte, b'_' | b'.' | b':' | b'@' | b'/' | b'+' | b'-')
        })
}

fn text<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| format!("{label} {key} is absent"))
}

fn bool_or_null(value: &Value, key: &str, label: &str) -> Result<Option<bool>, String> {
    if value[key].is_null() {
        Ok(None)
    } else {
        value[key]
            .as_bool()
            .map(Some)
            .ok_or_else(|| format!("{label} {key} is not boolean or null"))
    }
}

fn canonical_sha256(value: &Value) -> Result<String, String> {
    serde_json::to_vec(value)
        .map(|bytes| digest(&bytes))
        .map_err(|error| error.to_string())
}

fn validate_workspace(
    root: &Path,
    workspace: PathBuf,
    final_state: &Value,
    expected_digest: &str,
) -> Result<Value, String> {
    let source_metadata = fs::symlink_metadata(&workspace)
        .map_err(|error| format!("cannot inspect workspace: {error}"))?;
    require(
        source_metadata.file_type().is_dir() && !source_metadata.file_type().is_symlink(),
        "workspace must be a non-symlink directory",
    )?;
    let workspace = workspace
        .canonicalize()
        .map_err(|error| format!("cannot resolve workspace: {error}"))?;
    require(workspace.is_dir(), "workspace must be a directory")?;
    let workspace_relative = relative(root, &workspace, "workspace")?;
    let rows = final_state
        .as_object()
        .ok_or_else(|| "final source state must be an object".to_owned())?;
    require(!rows.is_empty(), "final source state must not be empty")?;
    require(
        canonical_sha256(final_state)? == expected_digest,
        "final source state digest differs from assessment summary",
    )?;

    let mut observed = BTreeSet::new();
    let mut stack = vec![workspace.clone()];
    let mut total_bytes = 0_u64;
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory)
            .map_err(|error| format!("cannot read workspace directory: {error}"))?
        {
            let path = entry
                .map_err(|error| format!("cannot read workspace entry: {error}"))?
                .path();
            let metadata = fs::symlink_metadata(&path)
                .map_err(|error| format!("cannot inspect workspace entry: {error}"))?;
            if metadata.file_type().is_dir() {
                stack.push(path);
                continue;
            }
            require(
                metadata.file_type().is_file() && !metadata.file_type().is_symlink(),
                "captured workspace contains a non-regular entry",
            )?;
            let name = path
                .strip_prefix(&workspace)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            let expected = rows.get(&name).ok_or_else(|| {
                format!("workspace file {name} is absent from final source state")
            })?;
            let bytes = fs::read(&path)
                .map_err(|error| format!("cannot read workspace file {name}: {error}"))?;
            let mode = metadata.permissions().mode() & 0o7777;
            require(
                expected["sha256"].as_str() == Some(&digest(&bytes))
                    && expected["byteLength"].as_u64() == Some(bytes.len() as u64)
                    && expected["unixMode"].as_u64() == Some(mode as u64),
                format!("workspace file {name} differs from final source state"),
            )?;
            total_bytes += bytes.len() as u64;
            observed.insert(name);
        }
    }
    let expected_names: BTreeSet<String> = rows.keys().cloned().collect();
    require(
        observed == expected_names,
        "captured workspace file set differs from final source state",
    )?;
    Ok(json!({
        "path": workspace_relative,
        "fileCount": observed.len(),
        "byteLength": total_bytes,
        "treeSha256": expected_digest,
    }))
}

fn compose(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let case = Input::load(&root, required_path(values, "--case")?, "evaluation case")?;
    let plan = Input::load(
        &root,
        required_path(values, "--experiment-plan")?,
        "participant experiment plan",
    )?;
    let summary = Input::load(
        &root,
        required_path(values, "--attempt-summary")?,
        "attempt summary",
    )?;
    let decision = Input::load(
        &root,
        required_path(values, "--decision-package")?,
        "decision package",
    )?;
    let initial = Input::load(
        &root,
        required_path(values, "--initial-state")?,
        "initial source state",
    )?;
    let final_state = Input::load(
        &root,
        required_path(values, "--final-state")?,
        "final source state",
    )?;
    let attempt_id = required(values, "--attempt-id")?;

    require(
        case.value["schema"] == "agentlab.multi_repo_evaluation_case.v1",
        "unsupported evaluation case schema",
    )?;
    require(
        plan.value["schema"] == "agentlab.participant_experiment_plan.v1",
        "unsupported participant experiment plan schema",
    )?;
    require(
        summary.value["schema"] == "agentlab.multi_repo_assessment_summary.v1",
        "unsupported attempt summary schema",
    )?;
    require(
        decision.value["schema"] == "agentlab.harness_decision_package.v1",
        "unsupported decision package schema",
    )?;
    require(
        case.value["status"] == "frozen-calibrated" && case.value["automaticPromotion"] == false,
        "evaluation case is not frozen calibrated and non-promoting",
    )?;
    require(
        plan.value["status"] == "predeclared-before-attempts"
            && plan.value["automaticPromotion"] == false,
        "participant experiment plan is not frozen before attempts",
    )?;
    require(
        decision.value["automaticPromotion"] == false,
        "decision package can auto-promote",
    )?;

    let case_id = text(&case.value, "id", "evaluation case")?;
    let source_set = text(&case.value, "sourceSetSha256", "evaluation case")?;
    for (value, label) in [
        (&plan.value, "participant experiment plan"),
        (&summary.value, "attempt summary"),
        (&decision.value, "decision package"),
    ] {
        require(
            text(
                value,
                if label == "participant experiment plan" {
                    "caseId"
                } else {
                    "taskId"
                },
                label,
            )? == case_id,
            format!("{label} case identity differs"),
        )?;
        require(
            text(value, "sourceSetSha256", label)? == source_set,
            format!("{label} source set differs"),
        )?;
    }
    require(
        text(
            &plan.value,
            "evaluationCaseSha256",
            "participant experiment plan",
        )? == case.sha256(),
        "participant experiment plan evaluation case digest differs",
    )?;

    let participant_id = text(&summary.value, "participantId", "attempt summary")?;
    require(
        text(&decision.value, "participantId", "decision package")? == participant_id,
        "attempt summary and decision participant identities differ",
    )?;
    let profiles = plan.value["participantProfiles"]
        .as_array()
        .ok_or_else(|| "participant profiles are absent".to_owned())?;
    let participant_profile = profiles
        .iter()
        .find(|row| row["participantId"].as_str() == Some(participant_id))
        .ok_or_else(|| "attempt participant is absent from predeclared plan".to_owned())?;
    let protocol = &plan.value["executionProtocol"];

    let assessment_status = text(&summary.value, "assessmentStatus", "attempt summary")?;
    require(
        text(&decision.value, "assessmentStatus", "decision package")? == assessment_status,
        "attempt summary and decision assessment statuses differ",
    )?;
    let infrastructure = summary.value["infrastructureAvailable"]
        .as_bool()
        .ok_or_else(|| "attempt summary infrastructureAvailable is invalid".to_owned())?;
    require(
        decision.value["infrastructureAvailable"].as_bool() == Some(infrastructure),
        "attempt summary and decision infrastructure availability differs",
    )?;
    let succeeded = bool_or_null(&summary.value, "subjectTaskSucceeded", "attempt summary")?;
    require(
        bool_or_null(&decision.value, "subjectTaskSucceeded", "decision package")? == succeeded,
        "attempt summary and decision verdicts differ",
    )?;
    let stages = summary.value["stages"]
        .as_array()
        .ok_or_else(|| "attempt summary stages are absent".to_owned())?;
    require(!stages.is_empty(), "attempt summary has no stages")?;
    let completed = stages
        .iter()
        .filter(|stage| stage["participantCompleted"].as_bool() == Some(true))
        .count();
    let terminal_stage = stages.last().and_then(|stage| stage["stageId"].as_str());
    let outcome = if !infrastructure {
        "infrastructure-error"
    } else if succeeded == Some(true) {
        "pass"
    } else if stages
        .iter()
        .any(|stage| stage["oraclePass"].as_bool() == Some(true))
    {
        "partial"
    } else {
        "fail"
    };

    require(
        canonical_sha256(&initial.value)?
            == text(&summary.value, "initialWorkspaceSha256", "attempt summary")?,
        "initial source state digest differs from assessment summary",
    )?;
    let final_digest = text(&summary.value, "finalWorkspaceSha256", "attempt summary")?;
    let captured_tree = validate_workspace(
        &root,
        required_path(values, "--workspace")?,
        &final_state.value,
        final_digest,
    )?;

    let event_log = optional_path(values, "--event-log")
        .map(|path| regular_binding(&root, path, "participant event log"))
        .transpose()?;
    let native_session = optional_path(values, "--native-session")
        .map(|path| regular_binding(&root, path, "native participant session"))
        .transpose()?;
    let environment_lock = optional_path(values, "--environment-lock")
        .map(|path| regular_binding(&root, path, "environment lock"))
        .transpose()?;
    let sessionfs_snapshot = optional_path(values, "--sessionfs-snapshot")
        .map(|path| Input::load(&root, path, "SessionFS snapshot receipt"))
        .transpose()?;
    if let Some(snapshot) = &sessionfs_snapshot {
        require(
            snapshot.value["formalSessionFsSnapshot"] == true
                && snapshot.value["readyForControlledFork"] == true,
            "SessionFS snapshot receipt is not qualified for controlled fork",
        )?;
    }

    let (context_mode, context_capability) = if native_session.is_some() {
        ("native-session-candidate", "native-candidate-not-qualified")
    } else if event_log.is_some() {
        ("event-log", "event-log-replay")
    } else {
        ("fresh-only", "fresh-only")
    };
    let snapshot_qualified = sessionfs_snapshot.is_some();
    let restore_profile = if snapshot_qualified {
        "exact-workspace-fork"
    } else if native_session.is_some() {
        "native-continuation-candidate"
    } else {
        "source-continuation"
    };
    let identity = digest(
        format!(
            "{}\0{}\0{}\0{}\0{}",
            case.sha256(),
            plan.sha256(),
            summary.sha256(),
            decision.sha256(),
            attempt_id
        )
        .as_bytes(),
    );

    Ok(json!({
        "schema": STATE_SCHEMA,
        "status": "captured-evaluation-instance",
        "stateId": format!("execution-state-{}", &identity[..20]),
        "case": {
            "caseId": case_id,
            "sourceSetSha256": source_set,
            "evaluationCase": case.binding(),
        },
        "attempt": {
            "attemptId": attempt_id,
            "participantId": participant_id,
            "summary": summary.binding(),
            "decisionPackage": decision.binding(),
        },
        "execution": {
            "lifecycle": "closed",
            "outcome": outcome,
            "stageCount": stages.len(),
            "completedStageCount": completed,
            "terminalStageId": terminal_stage,
        },
        "agent": {
            "configuration": plan.binding(),
            "participantProfile": {
                "agentImplementation": text(protocol, "agentImplementation", "execution protocol")?,
                "agentPackage": text(protocol, "agentPackage", "execution protocol")?,
                "agentPackageVersion": text(protocol, "agentPackageVersion", "execution protocol")?,
                "model": text(participant_profile, "model", "participant profile")?,
                "sessionPolicy": text(protocol, "sessionPolicy", "execution protocol")?,
            },
            "context": {
                "mode": context_mode,
                "eventLog": event_log,
                "nativeSession": native_session,
                "nativeRestoreQualified": false,
            },
        },
        "workspace": {
            "initialState": initial.binding(),
            "finalState": final_state.binding(),
            "capturedTree": captured_tree,
            "sessionFsSnapshot": sessionfs_snapshot.as_ref().map(Input::binding),
            "sessionFsRestoreQualified": snapshot_qualified,
        },
        "environment": {
            "runtimeImageId": text(protocol, "runtimeImageId", "execution protocol")?,
            "environmentLock": environment_lock,
            "deviceState": "not-captured",
        },
        "verification": {
            "authority": "independent-harness-decision-package",
            "assessmentStatus": assessment_status,
            "infrastructureAvailable": infrastructure,
            "subjectTaskSucceeded": succeeded,
            "sourceStateBound": true,
            "agentContextRestoreVerified": false,
            "workspaceRestoreVerified": snapshot_qualified,
        },
        "restoreCapabilities": {
            "profile": restore_profile,
            "semantic": "case-stage-and-verdict",
            "agentConfiguration": "exact-plan-bound",
            "agentContext": context_capability,
            "workspace": if snapshot_qualified { "sessionfs-snapshot" } else { "captured-source-tree" },
            "environment": "participant-runtime-plan-bound",
            "verification": if snapshot_qualified { "workspace-requalified" } else { "captured" },
        },
        "visibility": {
            "participantEvaluatorSeparated": true,
            "operatorSecretsPersisted": false,
        },
        "automaticPromotion": false,
    }))
}

fn derive_case(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let state = Input::load(
        &root,
        required_path(values, "--state")?,
        "case execution state",
    )?;
    let feedback = Input::load(
        &root,
        required_path(values, "--feedback")?,
        "assessment feedback",
    )?;
    let candidate_id = required(values, "--candidate-id")?;
    let mode = required(values, "--mode")?;
    require(
        state.value["schema"] == STATE_SCHEMA,
        "unsupported execution state schema",
    )?;
    require(
        state.value["automaticPromotion"] == false,
        "execution state can auto-promote",
    )?;
    require(
        feedback.value["schema"] == "agentlab.assessment_feedback_candidates.v1",
        "unsupported assessment feedback schema",
    )?;
    require(
        feedback.value["policy"]["automaticPromotion"] == false,
        "assessment feedback can auto-promote",
    )?;
    require(
        feedback.value["caseId"] == state.value["case"]["caseId"]
            && feedback.value["sourceSetSha256"] == state.value["case"]["sourceSetSha256"],
        "feedback and execution state case identity differs",
    )?;
    let candidates = feedback.value["candidates"]
        .as_array()
        .ok_or_else(|| "assessment feedback candidates are absent".to_owned())?;
    let candidate = candidates
        .iter()
        .find(|row| row["id"].as_str() == Some(candidate_id))
        .ok_or_else(|| "selected feedback candidate is absent".to_owned())?;
    require(
        candidate["automaticPromotion"] == false
            && candidate["verificationContract"]["caseReady"] == false,
        "selected feedback candidate is already promotable",
    )?;
    let attempt_id = text(
        &state.value["attempt"],
        "attemptId",
        "execution state attempt",
    )?;
    let observation = candidate["observations"]
        .as_array()
        .and_then(|rows| {
            rows.iter()
                .find(|row| row["attemptId"].as_str() == Some(attempt_id))
        })
        .ok_or_else(|| "selected feedback candidate does not cite the source attempt".to_owned())?;
    require(
        observation["decisionPackageSha256"] == state.value["attempt"]["decisionPackage"]["sha256"],
        "feedback observation decision package differs from execution state",
    )?;
    let context_mode = text(&state.value["agent"]["context"], "mode", "agent context")?;
    let workspace_verified = state.value["verification"]["workspaceRestoreVerified"]
        .as_bool()
        .unwrap_or(false);
    let (agent_policy, workspace_policy, native_required, requested_profile) = match mode {
        "fresh-agent-continuation" => (
            "fresh-agent",
            "restore-captured-tree",
            false,
            "source-continuation",
        ),
        "same-agent-continuation" => {
            require(
                context_mode == "native-session-candidate",
                "same-agent continuation requires a captured native session",
            )?;
            (
                "preserve-native",
                if workspace_verified {
                    "restore-sessionfs-snapshot"
                } else {
                    "restore-captured-tree"
                },
                true,
                if workspace_verified {
                    "exact-workspace-fork"
                } else {
                    "native-continuation"
                },
            )
        }
        "replace-agent" => (
            "replace-agent",
            "restore-captured-tree",
            false,
            "source-continuation",
        ),
        "semantic-transfer" => (
            "semantic-transfer",
            "restore-captured-tree",
            false,
            "semantic-only",
        ),
        "minimal-reproduction" => (
            "fresh-agent",
            "minimize-from-captured-tree",
            false,
            "source-continuation",
        ),
        "compound-extension" => (
            "fresh-agent",
            "restore-captured-tree",
            false,
            "source-continuation",
        ),
        _ => return Err("unsupported derivation mode".into()),
    };
    let mut required_gates = vec![
        "maintainer-adjudication",
        "participant-evaluator-visibility-review",
        "independent-oracle-calibration",
        "source-state-restore-requalification",
    ];
    if native_required {
        required_gates.push("native-agent-session-compatibility-and-restore-qualification");
    }
    let identity = digest(
        format!(
            "{}\0{}\0{}\0{}",
            state.sha256(),
            feedback.sha256(),
            candidate_id,
            mode
        )
        .as_bytes(),
    );
    let candidate_case_id = format!("case-candidate-{}", &identity[..20]);
    Ok(json!({
        "schema": DERIVATION_SCHEMA,
        "status": "review-required",
        "derivationId": format!("case-derivation-{}", &identity[..20]),
        "sourceState": state.binding(),
        "parentCase": {
            "caseId": state.value["case"]["caseId"],
            "sourceSetSha256": state.value["case"]["sourceSetSha256"],
            "evaluationCaseSha256": state.value["case"]["evaluationCase"]["sha256"],
        },
        "feedback": feedback.binding(),
        "difficulty": {
            "candidateId": candidate_id,
            "dimensionId": candidate["dimensionId"],
            "stageId": candidate["stageId"],
            "failureMode": candidate["failureMode"],
            "mechanism": candidate["mechanism"],
            "evidenceAttemptId": attempt_id,
        },
        "derivationMode": mode,
        "forkPolicy": {
            "agent": agent_policy,
            "workspace": workspace_policy,
            "requiresNativeSessionQualification": native_required,
        },
        "childCase": {
            "candidateCaseId": candidate_case_id,
            "status": "candidate",
            "requestedRestoreProfile": requested_profile,
            "caseReady": false,
        },
        "visibility": {
            "participantBundleRequired": true,
            "evaluatorBundleRequired": true,
            "operatorBundleMustRemainPrivate": true,
        },
        "qualification": {
            "sourceStateCaptured": true,
            "sourceStateRequalified": workspace_verified,
            "agentContextCaptured": context_mode != "fresh-only",
            "agentContextRequalified": false,
            "required": required_gates,
        },
        "automaticPromotion": false,
        "nextGate": "maintainer-adjudication-and-independent-oracle-calibration",
    }))
}

fn validate_frozen_case(case: &Input, label: &str) -> Result<(), String> {
    require(
        case.value["schema"] == "agentlab.multi_repo_evaluation_case.v1",
        format!("unsupported {label} schema"),
    )?;
    require(
        case.value["status"] == "frozen-calibrated" && case.value["automaticPromotion"] == false,
        format!("{label} is not frozen calibrated and non-promoting"),
    )?;
    require(
        case.value["calibration"]["qualified"] == true,
        format!("{label} calibration is not qualified"),
    )?;
    require(
        case.value["oracle"]["authority"] == "independent-executable-oracle",
        format!("{label} has no independent executable Oracle"),
    )
}

fn graph_derived_fields(
    nodes: &[Value],
    edges: &[Value],
) -> Result<(Value, Value, &'static str), String> {
    let mut node_indexes = BTreeMap::new();
    let mut parent_node_ids = BTreeSet::new();
    let mut incoming_edges = BTreeMap::new();
    for (index, node) in nodes.iter().enumerate() {
        let node_id = text(node, "nodeId", "case model graph node")?;
        require(
            node_indexes.insert(node_id.to_owned(), index).is_none(),
            "case model graph duplicates a node",
        )?;
    }
    for (index, edge) in edges.iter().enumerate() {
        let from = text(edge, "fromNodeId", "case model graph edge")?;
        let to = text(edge, "toNodeId", "case model graph edge")?;
        parent_node_ids.insert(from.to_owned());
        require(
            incoming_edges.insert(to.to_owned(), index).is_none(),
            "case model graph node has multiple incoming edges",
        )?;
    }

    let mut leaf_ids: Vec<String> = node_indexes
        .keys()
        .filter(|node_id| !parent_node_ids.contains(*node_id))
        .cloned()
        .collect();
    leaf_ids.sort();
    let maximum_depth = nodes
        .iter()
        .filter_map(|node| node["depth"].as_u64())
        .max()
        .unwrap_or(0);
    let maximum_qualified_depth = nodes
        .iter()
        .filter(|node| node["executable"] == true)
        .filter_map(|node| node["depth"].as_u64())
        .max()
        .unwrap_or(0);
    let qualified_node_count = nodes
        .iter()
        .filter(|node| node["executable"] == true)
        .count();
    let mut ready_path_node_ids = Vec::new();
    for node_id in node_indexes.keys() {
        let terminal = &nodes[*node_indexes.get(node_id).unwrap()];
        if terminal["depth"].as_u64().unwrap_or(0) < 2 {
            continue;
        }
        let mut current = node_id.as_str();
        let mut ready = true;
        loop {
            let node = &nodes[*node_indexes.get(current).unwrap()];
            if node["executable"] != true {
                ready = false;
                break;
            }
            if node["depth"] == 0 {
                break;
            }
            let Some(edge_index) = incoming_edges.get(current) else {
                ready = false;
                break;
            };
            let edge = &edges[*edge_index];
            if edge["restoreQualified"] != true {
                ready = false;
                break;
            }
            current = text(edge, "fromNodeId", "case model graph edge")?;
        }
        if ready {
            ready_path_node_ids.push(node_id.clone());
        }
    }
    let all_nodes_authored = nodes.iter().all(|node| node["executable"] == true);
    let all_nodes_calibrated = nodes
        .iter()
        .all(|node| node["verification"]["independentOracleCalibrated"] == true);
    let all_edges_restore_qualified = edges.iter().all(|edge| edge["restoreQualified"] == true);
    let long_horizon_ready = !ready_path_node_ids.is_empty();
    let next_gate = if long_horizon_ready {
        "select-qualified-path-for-execution"
    } else {
        "qualify-derived-node-before-long-horizon-extension"
    };
    Ok((
        json!({
            "nodeCount": nodes.len(),
            "edgeCount": edges.len(),
            "maximumDepth": maximum_depth,
            "maximumQualifiedDepth": maximum_qualified_depth,
            "qualifiedNodeCount": qualified_node_count,
            "leafNodeIds": leaf_ids,
            "readyPathNodeIds": ready_path_node_ids,
            "longHorizonReady": long_horizon_ready,
        }),
        json!({
            "allNodesScenarioAuthored": all_nodes_authored,
            "allNodesIndependentlyCalibrated": all_nodes_calibrated,
            "allEdgesRestoreQualified": all_edges_restore_qualified,
            "required": [
                "maintainer-case-authoring",
                "independent-oracle-calibration-per-node",
                "restore-policy-requalification-per-edge",
                "blind-participant-evaluator-cut",
            ],
        }),
        next_gate,
    ))
}

fn validate_graph(value: &Value) -> Result<(), String> {
    require(
        value["schema"] == GRAPH_SCHEMA,
        "unsupported case model graph schema",
    )?;
    require(
        value["status"] == "review-required" && value["automaticPromotion"] == false,
        "case model graph is not review-required and non-promoting",
    )?;
    let nodes = value["nodes"]
        .as_array()
        .ok_or_else(|| "case model graph nodes are absent".to_owned())?;
    let edges = value["edges"]
        .as_array()
        .ok_or_else(|| "case model graph edges are absent".to_owned())?;
    require(!nodes.is_empty(), "case model graph has no nodes")?;
    let root_id = text(&value["rootCase"], "caseId", "case model graph root")?;
    let mut depths = BTreeMap::new();
    let mut case_ids = BTreeSet::new();
    for node in nodes {
        let node_id = text(node, "nodeId", "case model graph node")?;
        let case_id = text(node, "caseId", "case model graph node")?;
        text(node, "provisionalCaseId", "case model graph node")?;
        require(
            case_ids.insert(case_id),
            "case model graph duplicates a case identity",
        )?;
        let depth = node["depth"]
            .as_u64()
            .ok_or_else(|| "case model graph node depth is invalid".to_owned())?;
        require(
            depths.insert(node_id, depth).is_none(),
            "case model graph duplicates a node",
        )?;
        match text(node, "kind", "case model graph node")? {
            "root-qualified-case" | "derived-qualified-case" => {
                require(
                    node["case"].is_object(),
                    "qualified graph node has no case binding",
                )?;
                require(
                    node["executable"] == true,
                    "qualified graph node is not executable",
                )?;
                require(
                    node["verification"]["independentOracleCalibrated"] == true,
                    "qualified graph node lacks calibrated Oracle verification",
                )?;
            }
            "derived-candidate" => {
                require(
                    node["case"].is_null(),
                    "candidate graph node already binds a case",
                )?;
                require(
                    node["derivation"].is_object(),
                    "candidate graph node has no derivation",
                )?;
                require(
                    node["executable"] == false,
                    "candidate graph node is executable",
                )?;
                require(
                    node["verification"]["independentOracleCalibrated"] == false,
                    "candidate graph node claims calibrated Oracle verification",
                )?;
            }
            _ => return Err("case model graph node kind is invalid".into()),
        }
    }
    require(
        nodes
            .iter()
            .any(|node| node["caseId"].as_str() == Some(root_id) && node["depth"] == 0),
        "case model graph root node is absent",
    )?;
    let mut edge_ids = BTreeSet::new();
    let mut incoming: BTreeMap<String, u64> = BTreeMap::new();
    let mut incoming_restore = BTreeMap::new();
    for edge in edges {
        let edge_id = text(edge, "edgeId", "case model graph edge")?;
        require(
            edge_ids.insert(edge_id),
            "case model graph duplicates an edge",
        )?;
        let from = text(edge, "fromNodeId", "case model graph edge")?;
        let to = text(edge, "toNodeId", "case model graph edge")?;
        *incoming.entry(to.to_owned()).or_default() += 1;
        let from_depth = depths
            .get(from)
            .ok_or_else(|| "case model graph edge parent is absent".to_owned())?;
        let to_depth = depths
            .get(to)
            .ok_or_else(|| "case model graph edge child is absent".to_owned())?;
        require(
            *to_depth == *from_depth + 1,
            "case model graph edge does not advance exactly one depth",
        )?;
        let restore_qualified = edge["restoreQualified"]
            .as_bool()
            .ok_or_else(|| "case model graph edge restore qualification is invalid".to_owned())?;
        require(
            restore_qualified == edge["qualification"].is_object(),
            "case model graph edge qualification binding differs from its verdict",
        )?;
        incoming_restore.insert(to.to_owned(), restore_qualified);
    }
    require(
        edges.len() + 1 == nodes.len(),
        "case model graph must retain exactly one parent edge per derived node",
    )?;
    let root_node_id = nodes
        .iter()
        .find(|node| node["caseId"].as_str() == Some(root_id) && node["depth"] == 0)
        .and_then(|node| node["nodeId"].as_str())
        .unwrap();
    for node_id in depths.keys() {
        require(
            incoming.get(*node_id).copied().unwrap_or(0)
                == if *node_id == root_node_id { 0 } else { 1 },
            "case model graph node incoming-edge count differs",
        )?;
        if *node_id != root_node_id {
            let node = nodes
                .iter()
                .find(|node| node["nodeId"].as_str() == Some(node_id))
                .unwrap();
            require(
                node["executable"].as_bool() == incoming_restore.get(*node_id).copied(),
                "derived graph node executability differs from incoming-edge qualification",
            )?;
        }
    }
    let (summary, qualification, next_gate) = graph_derived_fields(nodes, edges)?;
    require(
        value["summary"] == summary
            && value["qualification"] == qualification
            && value["nextGate"] == next_gate,
        "case model graph derived summary differs",
    )
}

fn model_graph(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let parent_case = Input::load(
        &root,
        required_path(values, "--parent-case")?,
        "parent evaluation case",
    )?;
    let derivation = Input::load(
        &root,
        required_path(values, "--derivation")?,
        "case derivation",
    )?;
    validate_frozen_case(&parent_case, "parent evaluation case")?;
    require(
        derivation.value["schema"] == DERIVATION_SCHEMA
            && derivation.value["status"] == "review-required"
            && derivation.value["automaticPromotion"] == false,
        "case derivation is not review-required and non-promoting",
    )?;
    require(
        derivation.value["childCase"]["caseReady"] == false,
        "case derivation child already claims readiness",
    )?;
    let parent_case_id = text(&parent_case.value, "id", "parent evaluation case")?;
    let parent_source_set = text(
        &parent_case.value,
        "sourceSetSha256",
        "parent evaluation case",
    )?;
    require(
        derivation.value["parentCase"]["caseId"] == parent_case_id
            && derivation.value["parentCase"]["sourceSetSha256"] == parent_source_set
            && derivation.value["parentCase"]["evaluationCaseSha256"] == parent_case.sha256(),
        "case derivation does not bind the exact parent case",
    )?;
    let child_case_id = text(
        &derivation.value["childCase"],
        "candidateCaseId",
        "case derivation child",
    )?;
    let difficulty_id = text(
        &derivation.value["difficulty"],
        "candidateId",
        "case derivation difficulty",
    )?;

    let prior = optional_path(values, "--graph")
        .map(|path| Input::load(&root, path, "prior case model graph"))
        .transpose()?;
    let (root_case, mut nodes, mut edges, predecessor) = if let Some(graph) = &prior {
        validate_graph(&graph.value)?;
        (
            graph.value["rootCase"].clone(),
            graph.value["nodes"].as_array().unwrap().clone(),
            graph.value["edges"].as_array().unwrap().clone(),
            Some(graph.binding()),
        )
    } else {
        let root_node_id = format!("case-node-{}", &parent_case.sha256()[..20]);
        (
            json!({
                "caseId": parent_case_id,
                "sourceSetSha256": parent_source_set,
                "evaluationCase": parent_case.binding(),
            }),
            vec![json!({
                "nodeId": root_node_id,
                "caseId": parent_case_id,
                "provisionalCaseId": parent_case_id,
                "kind": "root-qualified-case",
                "status": "frozen-calibrated",
                "depth": 0,
                "sourceSetSha256": parent_source_set,
                "case": parent_case.binding(),
                "derivation": null,
                "difficultyCandidateId": null,
                "scenario": {"status": "exact-frozen-case"},
                "verification": {"independentOracleCalibrated": true},
                "executable": true,
            })],
            Vec::new(),
            None,
        )
    };

    let parent_index = nodes
        .iter()
        .position(|node| node["caseId"].as_str() == Some(parent_case_id))
        .or_else(|| {
            let feedback_candidate =
                parent_case.value["lineage"]["feedbackAnalysisCut"]["feedbackCandidateId"].as_str();
            nodes.iter().position(|node| {
                node["kind"] == "derived-candidate"
                    && node["difficultyCandidateId"].as_str() == feedback_candidate
            })
        })
        .ok_or_else(|| {
            "parent case and recursive feedback lineage are absent from prior graph".to_owned()
        })?;
    let parent_kind = text(&nodes[parent_index], "kind", "parent graph node")?;
    require(
        parent_kind != "derived-candidate",
        "parent graph node must be qualified with an edge receipt before extension",
    )?;
    let parent_case_sha256 = parent_case.sha256();
    require(
        nodes[parent_index]["case"]["sha256"].as_str() == Some(parent_case_sha256.as_str()),
        "parent graph node binds different case bytes",
    )?;
    require(
        !nodes.iter().any(|node| {
            node["caseId"].as_str() == Some(child_case_id)
                || node["provisionalCaseId"].as_str() == Some(child_case_id)
        }),
        "derived child case already exists in graph",
    )?;
    let parent_depth = nodes[parent_index]["depth"].as_u64().unwrap();
    let parent_node_id = text(&nodes[parent_index], "nodeId", "parent graph node")?.to_owned();
    let child_node_id = format!("case-node-{}", &derivation.sha256()[..20]);
    nodes.push(json!({
        "nodeId": child_node_id,
        "caseId": child_case_id,
        "provisionalCaseId": child_case_id,
        "kind": "derived-candidate",
        "status": "review-required",
        "depth": parent_depth + 1,
        "sourceSetSha256": null,
        "case": null,
        "derivation": derivation.binding(),
        "difficultyCandidateId": difficulty_id,
        "scenario": {"status": "difficulty-only-requires-authoring"},
        "verification": {"independentOracleCalibrated": false},
        "executable": false,
    }));
    let edge_identity = digest(
        format!(
            "{}\0{}\0{}",
            parent_node_id,
            child_node_id,
            derivation.sha256()
        )
        .as_bytes(),
    );
    edges.push(json!({
        "edgeId": format!("case-edge-{}", &edge_identity[..20]),
        "fromNodeId": parent_node_id,
        "toNodeId": child_node_id,
        "derivation": derivation.binding(),
        "difficulty": derivation.value["difficulty"],
        "forkPolicy": derivation.value["forkPolicy"],
        "qualification": null,
        "restoreQualified": false,
    }));
    let (summary, qualification, next_gate) = graph_derived_fields(&nodes, &edges)?;
    let graph_identity = digest(
        format!(
            "{}\0{}\0{}",
            root_case["evaluationCase"]["sha256"].as_str().unwrap(),
            prior.as_ref().map(Input::sha256).unwrap_or_default(),
            derivation.sha256()
        )
        .as_bytes(),
    );
    let value = json!({
        "schema": GRAPH_SCHEMA,
        "status": "review-required",
        "graphId": format!("case-model-graph-{}", &graph_identity[..20]),
        "rootCase": root_case,
        "predecessorGraph": predecessor,
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
        "qualification": qualification,
        "automaticPromotion": false,
        "nextGate": next_gate,
    });
    validate_graph(&value)?;
    Ok(value)
}

fn qualify_graph(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let graph = Input::load(
        &root,
        required_path(values, "--graph")?,
        "prior case model graph",
    )?;
    let qualified_case = Input::load(
        &root,
        required_path(values, "--qualified-case")?,
        "qualified evaluation case",
    )?;
    let receipt = Input::load(
        &root,
        required_path(values, "--edge-qualification")?,
        "edge qualification receipt",
    )?;
    validate_graph(&graph.value)?;
    validate_frozen_case(&qualified_case, "qualified evaluation case")?;
    require(
        receipt.value["schema"] == EDGE_QUALIFICATION_SCHEMA
            && receipt.value["status"] == "qualified"
            && receipt.value["automaticPromotion"] == false,
        "edge qualification receipt is not qualified and non-promoting",
    )?;
    let qualification_id = text(
        &receipt.value,
        "qualificationId",
        "edge qualification receipt",
    )?;
    require(
        qualification_id.len() == 44
            && qualification_id.starts_with("case-edge-qualification-")
            && qualification_id[24..]
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()),
        "edge qualification receipt identity is invalid",
    )?;
    require(
        receipt.value["verification"]["authority"] == "independent-harness-restore-verification"
            && receipt.value["verification"]["parentCutStateExposed"] == true
            && receipt.value["verification"]["parentPostCutChangesExcluded"] == true
            && receipt.value["verification"]["childContinuesIndependently"] == true
            && receipt.value["verification"]["workspacePolicySatisfied"] == true,
        "edge qualification receipt lacks independent restore postconditions",
    )?;
    require(
        receipt.value["graph"]["graphId"] == graph.value["graphId"]
            && receipt.value["graph"]["sha256"] == graph.sha256(),
        "edge qualification receipt does not bind the exact predecessor graph",
    )?;
    let case_id = text(&qualified_case.value, "id", "qualified evaluation case")?;
    let source_set = text(
        &qualified_case.value,
        "sourceSetSha256",
        "qualified evaluation case",
    )?;
    require(
        receipt.value["qualifiedCase"]["caseId"] == case_id
            && receipt.value["qualifiedCase"]["sourceSetSha256"] == source_set
            && receipt.value["qualifiedCase"]["evaluationCaseSha256"] == qualified_case.sha256(),
        "edge qualification receipt does not bind the exact qualified case",
    )?;

    let mut nodes = graph.value["nodes"].as_array().unwrap().clone();
    let mut edges = graph.value["edges"].as_array().unwrap().clone();
    let receipt_child = text(&receipt.value["edge"], "toNodeId", "edge qualification")?;
    let node_index = nodes
        .iter()
        .position(|node| node["nodeId"].as_str() == Some(receipt_child))
        .ok_or_else(|| "qualified child node is absent from graph".to_owned())?;
    require(
        nodes[node_index]["kind"] == "derived-candidate",
        "qualified child node is not a pending derived candidate",
    )?;
    let difficulty = nodes[node_index]["difficultyCandidateId"].as_str();
    let direct_difficulty = qualified_case.value["difficultyId"].as_str();
    let feedback_difficulty =
        qualified_case.value["lineage"]["feedbackAnalysisCut"]["feedbackCandidateId"].as_str();
    require(
        nodes[node_index]["provisionalCaseId"].as_str() == Some(case_id)
            || difficulty == direct_difficulty
            || difficulty == feedback_difficulty,
        "qualified case does not retain candidate or feedback lineage",
    )?;
    require(
        !nodes
            .iter()
            .enumerate()
            .any(|(index, node)| index != node_index && node["caseId"].as_str() == Some(case_id)),
        "qualified case identity collides with another graph node",
    )?;
    let edge_index = edges
        .iter()
        .position(|edge| edge["toNodeId"].as_str() == Some(receipt_child))
        .ok_or_else(|| "qualified child incoming edge is absent".to_owned())?;
    let edge = &edges[edge_index];
    require(
        receipt.value["edge"]["edgeId"] == edge["edgeId"]
            && receipt.value["edge"]["fromNodeId"] == edge["fromNodeId"]
            && receipt.value["edge"]["derivationSha256"] == edge["derivation"]["sha256"]
            && receipt.value["forkPolicy"] == edge["forkPolicy"],
        "edge qualification receipt does not bind the exact edge policy and derivation",
    )?;
    let agent_policy = text(&edge["forkPolicy"], "agent", "edge fork policy")?;
    let expected_context = match agent_policy {
        "fresh-agent" => "fresh",
        "preserve-native" => "native-preserved",
        "replace-agent" => "replaced",
        "semantic-transfer" => "semantic-transfer",
        _ => return Err("edge Agent fork policy is invalid".into()),
    };
    require(
        receipt.value["verification"]["agentContextMode"] == expected_context,
        "edge qualification Agent context mode differs from fork policy",
    )?;
    let native_required = edge["forkPolicy"]["requiresNativeSessionQualification"] == true;
    require(
        receipt.value["verification"]["nativeSessionRestoreQualified"] == native_required,
        "edge qualification native-session verdict differs from fork policy",
    )?;
    let evidence = receipt.value["verification"]["evidence"]
        .as_array()
        .filter(|items| !items.is_empty())
        .ok_or_else(|| "edge qualification receipt has no retained evidence binding".to_owned())?;
    for (index, binding) in evidence.iter().enumerate() {
        verify_declared_binding(
            &root,
            binding,
            &format!("edge qualification evidence {index}"),
        )?;
    }

    nodes[node_index]["caseId"] = json!(case_id);
    nodes[node_index]["kind"] = json!("derived-qualified-case");
    nodes[node_index]["status"] = json!("frozen-calibrated");
    nodes[node_index]["sourceSetSha256"] = json!(source_set);
    nodes[node_index]["case"] = qualified_case.binding();
    nodes[node_index]["scenario"] = json!({"status": "exact-frozen-case"});
    nodes[node_index]["verification"] = json!({"independentOracleCalibrated": true});
    nodes[node_index]["executable"] = json!(true);
    edges[edge_index]["qualification"] = receipt.binding();
    edges[edge_index]["restoreQualified"] = json!(true);
    let (summary, qualification, next_gate) = graph_derived_fields(&nodes, &edges)?;
    let identity = digest(
        format!(
            "{}\0{}\0{}",
            graph.sha256(),
            qualified_case.sha256(),
            receipt.sha256()
        )
        .as_bytes(),
    );
    let value = json!({
        "schema": GRAPH_SCHEMA,
        "status": "review-required",
        "graphId": format!("case-model-graph-{}", &identity[..20]),
        "rootCase": graph.value["rootCase"],
        "predecessorGraph": graph.binding(),
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
        "qualification": qualification,
        "automaticPromotion": false,
        "nextGate": next_gate,
    });
    validate_graph(&value)?;
    Ok(value)
}

fn freeze_path(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let graph = Input::load(&root, required_path(values, "--graph")?, "case model graph")?;
    let inputs = Input::load(
        &root,
        required_path(values, "--path-inputs")?,
        "case path inputs",
    )?;
    validate_graph(&graph.value)?;
    require(
        inputs.value["schema"] == PATH_INPUTS_SCHEMA && inputs.value["automaticPromotion"] == false,
        "case path inputs are not supported and non-promoting",
    )?;
    require(
        inputs.value["graph"]["graphId"] == graph.value["graphId"]
            && inputs.value["graph"]["sha256"] == graph.sha256(),
        "case path inputs do not bind the exact graph",
    )?;
    let terminal_node_id = text(&inputs.value, "terminalNodeId", "case path inputs")?;
    require(
        graph.value["summary"]["readyPathNodeIds"]
            .as_array()
            .is_some_and(|nodes| {
                nodes
                    .iter()
                    .any(|node| node.as_str() == Some(terminal_node_id))
            }),
        "selected terminal is not a qualified long-horizon path",
    )?;
    let nodes = graph.value["nodes"].as_array().unwrap();
    let edges = graph.value["edges"].as_array().unwrap();
    let node_indexes: BTreeMap<&str, usize> = nodes
        .iter()
        .enumerate()
        .map(|(index, node)| text(node, "nodeId", "case model graph node").map(|id| (id, index)))
        .collect::<Result<_, _>>()?;
    let incoming: BTreeMap<&str, usize> = edges
        .iter()
        .enumerate()
        .map(|(index, edge)| text(edge, "toNodeId", "case model graph edge").map(|id| (id, index)))
        .collect::<Result<_, _>>()?;
    let mut path_node_ids = Vec::new();
    let mut current = terminal_node_id;
    loop {
        let node = &nodes[*node_indexes
            .get(current)
            .ok_or_else(|| "selected path node is absent".to_owned())?];
        require(
            node["executable"] == true,
            "selected path contains a non-executable node",
        )?;
        path_node_ids.push(current.to_owned());
        if node["depth"] == 0 {
            break;
        }
        let edge = &edges[*incoming
            .get(current)
            .ok_or_else(|| "selected path transition is absent".to_owned())?];
        require(
            edge["restoreQualified"] == true && edge["qualification"].is_object(),
            "selected path contains an unqualified transition",
        )?;
        current = text(edge, "fromNodeId", "selected path transition")?;
    }
    path_node_ids.reverse();
    require(
        path_node_ids.len() >= 3,
        "selected path must contain at least two difficulty depths",
    )?;

    let rows = inputs.value["blindCuts"]
        .as_array()
        .ok_or_else(|| "case path blind cuts are absent".to_owned())?;
    let mut input_rows = BTreeMap::new();
    for row in rows {
        let node_id = text(row, "nodeId", "case path blind cut")?;
        require(
            input_rows.insert(node_id, row).is_none(),
            "case path inputs duplicate a node",
        )?;
    }
    require(
        input_rows.len() == path_node_ids.len()
            && path_node_ids
                .iter()
                .all(|id| input_rows.contains_key(id.as_str())),
        "case path blind-cut membership differs from selected path",
    )?;

    let mut stages = Vec::new();
    for (ordinal, node_id) in path_node_ids.iter().enumerate() {
        let node = &nodes[*node_indexes.get(node_id.as_str()).unwrap()];
        let row = input_rows[node_id.as_str()];
        let cut = load_declared_input(
            &root,
            &row["cutReceipt"],
            &format!("stage {ordinal} blind cut receipt"),
        )?;
        let participant = load_declared_input(
            &root,
            &row["participantManifest"],
            &format!("stage {ordinal} participant manifest"),
        )?;
        let evaluator = load_declared_input(
            &root,
            &row["evaluatorManifest"],
            &format!("stage {ordinal} evaluator manifest"),
        )?;
        let cut_root = Path::new(&cut.relative)
            .parent()
            .ok_or_else(|| format!("stage {ordinal} blind cut has no root"))?;
        require(
            Path::new(&participant.relative) == cut_root.join("participant/manifest.json")
                && Path::new(&evaluator.relative) == cut_root.join("evaluator/manifest.json"),
            format!("stage {ordinal} blind manifests are not physically separated siblings"),
        )?;
        require(
            cut.value["schema"] == "agentlab.blind_case_cut_receipt.v1"
                && participant.value["schema"] == "agentlab.blind_case_participant_bundle.v1"
                && evaluator.value["schema"] == "agentlab.blind_case_evaluator_bundle.v1",
            format!("stage {ordinal} blind cut schemas differ"),
        )?;
        let case_id = text(node, "caseId", "selected path node")?;
        let source_set = text(node, "sourceSetSha256", "selected path node")?;
        let cut_id = text(&cut.value, "cutId", "blind cut receipt")?;
        let method_revision = text(&cut.value, "methodRevision", "blind cut receipt")?;
        require(
            method_revision.len() == 40
                && method_revision
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()),
            format!("stage {ordinal} blind cut method revision is not exact"),
        )?;
        for (value, label) in [
            (&cut.value, "blind cut receipt"),
            (&participant.value, "participant manifest"),
            (&evaluator.value, "evaluator manifest"),
        ] {
            require(
                text(value, "caseId", label)? == case_id
                    && text(value, "sourceSetSha256", label)? == source_set
                    && text(value, "cutId", label)? == cut_id
                    && text(value, "methodRevision", label)? == method_revision,
                format!("stage {ordinal} blind cut identity differs from graph node"),
            )?;
        }
        require(
            cut.value["automaticPromotion"] == false
                && cut.value["boundary"]["physicallySeparatedRoots"] == true
                && cut.value["boundary"]["participantManifestContainsEvaluatorInventory"] == false
                && cut.value["freshness"]["eligibleForBlindPilot"] == true,
            format!("stage {ordinal} blind cut boundary is not structurally eligible"),
        )?;
        require(
            cut.value["participantBundle"]["manifestSha256"] == participant.sha256()
                && cut.value["evaluatorBundle"]["manifestSha256"] == evaluator.sha256()
                && evaluator.value["participantManifestSha256"] == participant.sha256(),
            format!("stage {ordinal} blind manifest lineage differs"),
        )?;
        let participant_files = participant.value["files"]
            .as_array()
            .ok_or_else(|| format!("stage {ordinal} participant file inventory is absent"))?;
        require(
            !participant_files.is_empty()
                && participant_files.iter().all(|file| {
                    matches!(
                        file["role"].as_str(),
                        Some("task" | "source" | "context" | "constraint")
                    )
                })
                && participant_files
                    .iter()
                    .all(|file| file["role"] != "oracle" && file["role"] != "reference"),
            format!("stage {ordinal} participant manifest exposes evaluator roles"),
        )?;
        let evaluator_files = evaluator.value["files"]
            .as_array()
            .ok_or_else(|| format!("stage {ordinal} evaluator file inventory is absent"))?;
        require(
            evaluator_files.iter().any(|file| file["role"] == "oracle")
                && evaluator_files
                    .iter()
                    .any(|file| file["role"] == "reference"),
            format!("stage {ordinal} evaluator manifest lacks Oracle or reference"),
        )?;
        let participant_hashes = validate_blind_inventory(
            &root,
            &participant,
            &["task", "source", "context", "constraint"],
            &format!("stage {ordinal} participant bundle"),
        )?;
        let evaluator_hashes = validate_blind_inventory(
            &root,
            &evaluator,
            &["oracle", "reference", "preservation", "review", "analysis"],
            &format!("stage {ordinal} evaluator bundle"),
        )?;
        require(
            participant_hashes.is_disjoint(&evaluator_hashes),
            format!("stage {ordinal} blind bundles contain byte-identical files"),
        )?;
        let transition = if ordinal == 0 {
            Value::Null
        } else {
            let edge = &edges[*incoming.get(node_id.as_str()).unwrap()];
            json!({
                "edgeId": edge["edgeId"],
                "fromNodeId": edge["fromNodeId"],
                "forkPolicy": edge["forkPolicy"],
                "qualification": edge["qualification"],
            })
        };
        stages.push(json!({
            "ordinal": ordinal,
            "nodeId": node_id,
            "caseId": case_id,
            "sourceSetSha256": source_set,
            "evaluationCase": node["case"],
            "blindCutReceipt": cut.binding(),
            "participantManifest": participant.binding(),
            "evaluatorManifest": evaluator.binding(),
            "incomingTransition": transition,
        }));
    }
    let plan_identity = digest(
        format!(
            "{}\0{}\0{}",
            graph.sha256(),
            inputs.sha256(),
            terminal_node_id
        )
        .as_bytes(),
    );
    Ok(json!({
        "schema": PATH_PLAN_SCHEMA,
        "status": "frozen-awaiting-dispatch-qualification",
        "planId": format!("case-path-plan-{}", &plan_identity[..20]),
        "graph": graph.binding(),
        "pathInputs": inputs.binding(),
        "terminalNodeId": terminal_node_id,
        "executionMode": "sequential-qualified-path",
        "difficultyDepth": path_node_ids.len() - 1,
        "stages": stages,
        "boundary": {
            "participantReceivesOnlyCurrentStageBundle": true,
            "evaluatorReceivesCurrentStageEvaluatorBundle": true,
            "edgeQualificationOutsideParticipant": true,
            "operatorEvidenceOutsideParticipant": true,
            "stageBundleIsolationRequiresRuntimeProof": true,
        },
        "qualification": {
            "graphLongHorizonReady": true,
            "allPathNodesExecutable": true,
            "allTransitionsRestoreQualified": true,
            "blindCutsStructurallyValidated": true,
            "runtimeIsolationQualified": false,
            "authenticatedBlindReviewQualified": false,
            "readyForExecution": false,
        },
        "automaticPromotion": false,
        "nextGate": "predeclare-agent-environment-and-qualify-blind-dispatch",
    }))
}

fn validate_frozen_path_plan(root: &Path, plan: &Value) -> Result<usize, String> {
    require(
        plan["schema"] == PATH_PLAN_SCHEMA
            && plan["status"] == "frozen-awaiting-dispatch-qualification"
            && plan["executionMode"] == "sequential-qualified-path"
            && plan["automaticPromotion"] == false,
        "case path execution plan is not frozen and non-promoting",
    )?;
    verify_declared_binding(root, &plan["graph"], "case path plan graph")?;
    verify_declared_binding(root, &plan["pathInputs"], "case path plan inputs")?;
    require(
        plan["boundary"]["participantReceivesOnlyCurrentStageBundle"] == true
            && plan["boundary"]["evaluatorReceivesCurrentStageEvaluatorBundle"] == true
            && plan["boundary"]["edgeQualificationOutsideParticipant"] == true
            && plan["boundary"]["operatorEvidenceOutsideParticipant"] == true
            && plan["boundary"]["stageBundleIsolationRequiresRuntimeProof"] == true,
        "case path execution plan boundary is invalid",
    )?;
    require(
        plan["qualification"]["graphLongHorizonReady"] == true
            && plan["qualification"]["allPathNodesExecutable"] == true
            && plan["qualification"]["allTransitionsRestoreQualified"] == true
            && plan["qualification"]["blindCutsStructurallyValidated"] == true
            && plan["qualification"]["runtimeIsolationQualified"] == false
            && plan["qualification"]["authenticatedBlindReviewQualified"] == false
            && plan["qualification"]["readyForExecution"] == false,
        "case path execution plan qualification is invalid",
    )?;
    let stages = plan["stages"]
        .as_array()
        .filter(|rows| rows.len() >= 3)
        .ok_or_else(|| "case path execution plan stages are invalid".to_owned())?;
    require(
        plan["difficultyDepth"].as_u64() == Some((stages.len() - 1) as u64),
        "case path execution plan difficulty depth differs from its stages",
    )?;
    let mut nodes = BTreeSet::new();
    let mut cases = BTreeSet::new();
    for (ordinal, stage) in stages.iter().enumerate() {
        require(
            stage["ordinal"].as_u64() == Some(ordinal as u64),
            "case path execution plan stage ordinals are not contiguous",
        )?;
        let node = text(stage, "nodeId", "case path execution stage")?;
        let case = text(stage, "caseId", "case path execution stage")?;
        let source_set = text(stage, "sourceSetSha256", "case path execution stage")?;
        require(
            nodes.insert(node)
                && cases.insert(case)
                && source_set.len() == 64
                && source_set
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()),
            "case path execution plan stage identity is invalid or duplicated",
        )?;
        for (key, label) in [
            ("evaluationCase", "evaluation case"),
            ("blindCutReceipt", "blind cut receipt"),
            ("participantManifest", "participant manifest"),
            ("evaluatorManifest", "evaluator manifest"),
        ] {
            verify_declared_binding(root, &stage[key], &format!("stage {ordinal} {label}"))?;
        }
        if ordinal == 0 {
            require(
                stage["incomingTransition"].is_null(),
                "root path stage must not have an incoming transition",
            )?;
        } else {
            let transition = &stage["incomingTransition"];
            require(
                transition.is_object()
                    && text(transition, "edgeId", "path transition").is_ok()
                    && text(transition, "fromNodeId", "path transition").is_ok()
                    && transition["forkPolicy"].is_object(),
                "non-root path stage lacks an exact incoming transition",
            )?;
            verify_declared_binding(
                root,
                &transition["qualification"],
                &format!("stage {ordinal} edge qualification"),
            )?;
        }
    }
    require(
        plan["terminalNodeId"].as_str() == stages.last().and_then(|stage| stage["nodeId"].as_str()),
        "case path terminal differs from its final stage",
    )?;
    Ok(stages.len())
}

fn predeclare_path(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let plan = Input::load(
        &root,
        required_path(values, "--path-plan")?,
        "case path execution plan",
    )?;
    let matrix = Input::load(
        &root,
        required_path(values, "--participant-matrix")?,
        "case path participant matrix",
    )?;
    let stage_count = validate_frozen_path_plan(&root, &plan.value)?;
    require(
        matrix.value["schema"] == PATH_MATRIX_SCHEMA
            && matrix.value["status"] == "predeclared-before-attempts"
            && matrix.value["automaticPromotion"] == false,
        "participant matrix is not predeclared and non-promoting",
    )?;
    require(
        matrix.value["pathPlan"]["planId"] == plan.value["planId"]
            && matrix.value["pathPlan"]["sha256"] == plan.sha256(),
        "participant matrix does not bind the exact path plan",
    )?;
    let method_revision = text(&matrix.value, "methodRevision", "participant matrix")?;
    require(
        method_revision.len() == 40
            && method_revision
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()),
        "participant matrix method revision is not exact",
    )?;
    let trials = matrix.value["trialsPerCell"]
        .as_u64()
        .filter(|value| [3, 5, 10, 20].contains(value))
        .ok_or_else(|| "participant matrix trials must be 3, 5, 10 or 20".to_owned())?;

    let agent_rows = matrix.value["agentConfigurations"]
        .as_array()
        .filter(|rows| (1..=8).contains(&rows.len()))
        .ok_or_else(|| "participant matrix Agent configurations are invalid".to_owned())?;
    let model_rows = matrix.value["modelConfigurations"]
        .as_array()
        .filter(|rows| (1..=8).contains(&rows.len()))
        .ok_or_else(|| "participant matrix model configurations are invalid".to_owned())?;
    let environment_rows = matrix.value["environmentConfigurations"]
        .as_array()
        .filter(|rows| (1..=8).contains(&rows.len()))
        .ok_or_else(|| "participant matrix environment configurations are invalid".to_owned())?;
    let mut agents = BTreeMap::new();
    for row in agent_rows {
        let id = text(row, "agentConfigId", "Agent configuration")?;
        require(
            valid_token(id) && agents.insert(id.to_owned(), row).is_none(),
            "Agent configuration identity is invalid or duplicated",
        )?;
        for key in [
            "implementation",
            "package",
            "packageVersion",
            "sessionPolicy",
        ] {
            require(
                valid_token(text(row, key, "Agent configuration")?),
                format!("Agent configuration {key} is invalid"),
            )?;
        }
        verify_declared_binding(&root, &row["adapter"], "Agent adapter")?;
        verify_declared_binding(&root, &row["driver"], "Agent driver")?;
    }
    let mut models = BTreeMap::new();
    for row in model_rows {
        let id = text(row, "modelConfigId", "model configuration")?;
        require(
            valid_token(id) && models.insert(id.to_owned(), row).is_none(),
            "model configuration identity is invalid or duplicated",
        )?;
        for key in ["providerRoute", "model", "thinkingMode", "samplingPolicy"] {
            require(
                valid_token(text(row, key, "model configuration")?),
                format!("model configuration {key} is invalid"),
            )?;
        }
        require(
            row["reasoningEffort"].is_null()
                || row["reasoningEffort"].as_str().is_some_and(valid_token),
            "model reasoning effort is invalid",
        )?;
    }
    let mut environments = BTreeMap::new();
    for row in environment_rows {
        let id = text(row, "environmentConfigId", "environment configuration")?;
        require(
            valid_token(id) && environments.insert(id.to_owned(), row).is_none(),
            "environment configuration identity is invalid or duplicated",
        )?;
        let image = text(row, "runtimeImageId", "environment configuration")?;
        require(
            image.len() == 71
                && image.starts_with("sha256:")
                && image[7..]
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()),
            "environment runtime image identity is invalid",
        )?;
        require(
            matches!(
                text(row, "architecture", "environment configuration")?,
                "x86_64" | "aarch64"
            ),
            "environment architecture is invalid",
        )?;
        verify_declared_binding(&root, &row["environmentLock"], "environment lock")?;
    }

    let cell_rows = matrix.value["cells"]
        .as_array()
        .filter(|rows| (3..=8).contains(&rows.len()))
        .ok_or_else(|| "participant matrix must contain three to eight cells".to_owned())?;
    let mut cells = BTreeMap::new();
    let mut tuples = BTreeSet::new();
    for (ordinal, row) in cell_rows.iter().enumerate() {
        require(
            row["ordinal"].as_u64() == Some(ordinal as u64),
            "participant matrix cell ordinals are not contiguous",
        )?;
        let participant = text(row, "participantId", "participant matrix cell")?;
        let agent = text(row, "agentConfigId", "participant matrix cell")?;
        let model = text(row, "modelConfigId", "participant matrix cell")?;
        let environment = text(row, "environmentConfigId", "participant matrix cell")?;
        require(
            valid_token(participant)
                && cells.insert(participant.to_owned(), row).is_none()
                && agents.contains_key(agent)
                && models.contains_key(model)
                && environments.contains_key(environment),
            "participant matrix cell identity or configuration reference is invalid",
        )?;
        require(
            tuples.insert((agent, model, environment)),
            "participant matrix duplicates a configuration tuple",
        )?;
    }
    let comparisons = matrix.value["comparisonPairs"]
        .as_array()
        .filter(|rows| !rows.is_empty())
        .ok_or_else(|| "participant matrix comparison pairs are absent".to_owned())?;
    let mut compared = BTreeSet::new();
    for row in comparisons {
        let left_id = text(row, "leftParticipantId", "comparison pair")?;
        let right_id = text(row, "rightParticipantId", "comparison pair")?;
        require(
            left_id != right_id,
            "comparison pair repeats one participant",
        )?;
        let left = cells
            .get(left_id)
            .ok_or_else(|| "comparison pair left participant is absent".to_owned())?;
        let right = cells
            .get(right_id)
            .ok_or_else(|| "comparison pair right participant is absent".to_owned())?;
        let differences = [
            ("agent", left["agentConfigId"] != right["agentConfigId"]),
            ("model", left["modelConfigId"] != right["modelConfigId"]),
            (
                "environment",
                left["environmentConfigId"] != right["environmentConfigId"],
            ),
        ];
        let changed: Vec<&str> = differences
            .iter()
            .filter_map(|(dimension, differs)| differs.then_some(*dimension))
            .collect();
        require(
            changed.len() == 1 && row["changedDimension"].as_str() == changed.first().copied(),
            "comparison pair does not change exactly its declared dimension",
        )?;
        compared.insert(left_id);
        compared.insert(right_id);
    }
    require(
        compared.len() == cells.len(),
        "participant matrix comparison pairs do not cover every cell",
    )?;
    let attempt_count = trials * cells.len() as u64;
    let identity = digest(format!("{}\0{}", plan.sha256(), matrix.sha256()).as_bytes());
    Ok(json!({
        "schema": PATH_DISPATCH_SCHEMA,
        "status": "predeclared-awaiting-runtime-qualification",
        "dispatchPlanId": format!("case-path-dispatch-{}", &identity[..20]),
        "pathPlan": plan.binding(),
        "participantMatrix": matrix.binding(),
        "methodRevision": method_revision,
        "stageCount": stage_count,
        "cellCount": cells.len(),
        "trialsPerCell": trials,
        "expectedAttemptCount": attempt_count,
        "expectedStageExecutionCount": attempt_count * stage_count as u64,
        "cells": cell_rows,
        "comparisonPairs": comparisons,
        "controlPolicy": {
            "comparisonPairsChangeExactlyOneDimension": true,
            "everyCellCoveredByComparison": true,
            "outcomeDataObservedBeforeFreeze": false,
        },
        "qualification": {
            "pathStructurallyQualified": true,
            "agentModelEnvironmentIdentitiesExact": true,
            "matrixPredeclaredBeforeAttempts": true,
            "portableRuntimeQualified": false,
            "blindDispatchQualified": false,
            "readyForDispatch": false,
        },
        "automaticPromotion": false,
        "nextGate": "qualify-portable-runtime-and-blind-dispatch-per-cell",
    }))
}

fn qualify_dispatch(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let root = required_path(values, "--root")?
        .canonicalize()
        .map_err(|error| format!("cannot resolve --root: {error}"))?;
    require(root.is_dir(), "--root must be a directory")?;
    let dispatch = Input::load(
        &root,
        required_path(values, "--dispatch-plan")?,
        "case path dispatch plan",
    )?;
    let receipt = Input::load(
        &root,
        required_path(values, "--dispatch-qualification")?,
        "case path dispatch qualification",
    )?;
    require(
        dispatch.value["schema"] == PATH_DISPATCH_SCHEMA
            && dispatch.value["status"] == "predeclared-awaiting-runtime-qualification"
            && dispatch.value["qualification"]["readyForDispatch"] == false
            && dispatch.value["automaticPromotion"] == false,
        "dispatch plan is not a predeclared non-promoting plan",
    )?;
    verify_declared_binding(&root, &dispatch.value["pathPlan"], "dispatch path plan")?;
    let matrix = load_declared_input(
        &root,
        &dispatch.value["participantMatrix"],
        "dispatch participant matrix",
    )?;
    require(
        matrix.value["schema"] == PATH_MATRIX_SCHEMA,
        "dispatch participant matrix schema differs",
    )?;
    require(
        receipt.value["schema"] == PATH_DISPATCH_QUALIFICATION_SCHEMA
            && receipt.value["status"] == "qualified"
            && receipt.value["authority"] == "independent-harness-runtime-and-blind-dispatch"
            && receipt.value["automaticPromotion"] == false,
        "dispatch qualification is not independent, qualified and non-promoting",
    )?;
    require(
        receipt.value["dispatchPlan"]["dispatchPlanId"] == dispatch.value["dispatchPlanId"]
            && receipt.value["dispatchPlan"]["sha256"] == dispatch.sha256()
            && receipt.value["methodRevision"] == dispatch.value["methodRevision"],
        "dispatch qualification does not bind the exact plan and method",
    )?;
    let environments: BTreeMap<&str, &Value> = matrix.value["environmentConfigurations"]
        .as_array()
        .ok_or_else(|| "participant matrix environments are absent".to_owned())?
        .iter()
        .map(|row| {
            text(row, "environmentConfigId", "environment configuration").map(|id| (id, row))
        })
        .collect::<Result<_, _>>()?;
    let cells = dispatch.value["cells"]
        .as_array()
        .filter(|rows| (3..=8).contains(&rows.len()))
        .ok_or_else(|| "dispatch plan cells are invalid".to_owned())?;
    let qualified = receipt.value["cells"]
        .as_array()
        .filter(|rows| rows.len() == cells.len())
        .ok_or_else(|| "dispatch qualification cell count differs".to_owned())?;
    let mut receipts = BTreeMap::new();
    for row in qualified {
        let participant = text(row, "participantId", "dispatch qualification cell")?;
        require(
            receipts.insert(participant, row).is_none(),
            "dispatch qualification duplicates a participant",
        )?;
    }
    for cell in cells {
        let participant = text(cell, "participantId", "dispatch cell")?;
        let row = receipts
            .get(participant)
            .ok_or_else(|| "dispatch qualification omits a participant".to_owned())?;
        let environment_id = text(cell, "environmentConfigId", "dispatch cell")?;
        let environment = environments
            .get(environment_id)
            .ok_or_else(|| "dispatch cell environment is absent from its matrix".to_owned())?;
        require(
            row["environmentConfigId"] == environment_id
                && row["runtimeImageId"] == environment["runtimeImageId"],
            "dispatch qualification runtime identity differs from its cell",
        )?;
        require(
            row["verification"]["portableRuntimeStarted"] == true
                && row["verification"]["currentStageParticipantBundleOnly"] == true
                && row["verification"]["evaluatorBundleOutsideParticipant"] == true
                && row["verification"]["networkPolicyEnforced"] == true
                && row["verification"]["freshTrialBoundaryVerified"] == true,
            "dispatch qualification lacks required runtime or blind boundary postconditions",
        )?;
        verify_declared_binding(
            &root,
            &row["runtimeEvidence"],
            &format!("participant {participant} runtime evidence"),
        )?;
        verify_declared_binding(
            &root,
            &row["blindDispatchEvidence"],
            &format!("participant {participant} blind dispatch evidence"),
        )?;
    }
    let identity = digest(format!("{}\0{}", dispatch.sha256(), receipt.sha256()).as_bytes());
    Ok(json!({
        "schema": PATH_QUALIFIED_DISPATCH_SCHEMA,
        "status": "qualified-ready-for-dispatch",
        "qualifiedDispatchId": format!("case-path-qualified-dispatch-{}", &identity[..20]),
        "dispatchPlan": dispatch.binding(),
        "dispatchQualification": receipt.binding(),
        "methodRevision": dispatch.value["methodRevision"],
        "stageCount": dispatch.value["stageCount"],
        "cellCount": dispatch.value["cellCount"],
        "trialsPerCell": dispatch.value["trialsPerCell"],
        "expectedAttemptCount": dispatch.value["expectedAttemptCount"],
        "expectedStageExecutionCount": dispatch.value["expectedStageExecutionCount"],
        "cells": dispatch.value["cells"],
        "qualification": {
            "pathStructurallyQualified": true,
            "matrixPredeclaredBeforeAttempts": true,
            "portableRuntimeQualifiedPerCell": true,
            "blindDispatchQualifiedPerCell": true,
            "readyForDispatch": true
        },
        "automaticPromotion": false,
        "nextGate": "execute-predeclared-attempts-and-record-stage-verdicts"
    }))
}

fn required<'a>(values: &'a BTreeMap<String, String>, flag: &str) -> Result<&'a str, String> {
    values
        .get(flag)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {flag}"))
}

fn required_path(values: &BTreeMap<String, String>, flag: &str) -> Result<PathBuf, String> {
    required(values, flag).map(PathBuf::from)
}

fn optional_path(values: &BTreeMap<String, String>, flag: &str) -> Option<PathBuf> {
    values.get(flag).map(PathBuf::from)
}

fn write_output(path: PathBuf, value: &Value) -> Result<(), String> {
    match fs::symlink_metadata(&path) {
        Ok(_) => return Err("refusing to overwrite output".into()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(format!("cannot inspect output: {error}")),
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create output directory: {error}"))?;
    }
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(path, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| {
        "expected compose, derive, graph, qualify, freeze-path, predeclare-path or qualify-dispatch".to_owned()
    })?;
    let mut values = BTreeMap::new();
    while let Some(flag) = args.next() {
        require(
            flag.starts_with("--"),
            format!("unexpected argument {flag}"),
        )?;
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        require(
            values.insert(flag.clone(), value).is_none(),
            format!("duplicate argument {flag}"),
        )?;
    }
    let output = required_path(&values, "--output")?;
    let value = match command.as_str() {
        "compose" => compose(&values)?,
        "derive" => derive_case(&values)?,
        "graph" => model_graph(&values)?,
        "qualify" => qualify_graph(&values)?,
        "freeze-path" => freeze_path(&values)?,
        "predeclare-path" => predeclare_path(&values)?,
        "qualify-dispatch" => qualify_dispatch(&values)?,
        _ => {
            return Err(
                "expected compose, derive, graph, qualify, freeze-path, predeclare-path or qualify-dispatch".into(),
            )
        }
    };
    write_output(output, &value)
}

fn main() {
    if let Err(error) = run() {
        eprintln!("AgentLab case state invalid: {error}");
        std::process::exit(1);
    }
}
