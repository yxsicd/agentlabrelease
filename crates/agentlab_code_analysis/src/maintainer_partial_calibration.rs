//! Scoped recorded-observation readback. Never changes formal qualification.
use crate::{digest, maintainer_downstream};
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path},
};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Profile {
    schema: String,
    reviewed: bool,
    candidate_id: String,
    candidate_sha256: String,
    source_revision: String,
    construction_plan_sha256: String,
    target_peer_id: String,
    runtime_identity: Value,
    phases: Vec<Phase>,
    controls: Vec<Control>,
    remaining_controls: Vec<Remaining>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Phase {
    id: String,
    checks: Vec<Check>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Check {
    id: String,
    selector: Selector,
    expected: Value,
}
#[derive(Deserialize)]
#[serde(tag = "adapter", rename_all = "kebab-case", deny_unknown_fields)]
enum Selector {
    JsonPointer {
        pointer: String,
    },
    AttributeTree {
        owner: Value,
        node: Value,
        field: String,
    },
    HypiumNativeTest {
        class: String,
        test: String,
    },
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Control {
    id: String,
    role: String,
    #[serde(default)]
    owner_attributes: Option<Value>,
    expected_failed_check_ids: Vec<String>,
    observations: Vec<Observation>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Observation {
    phase: String,
    path: String,
    envelope_sha256: String,
    raw_sha256: String,
    byte_length: usize,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Remaining {
    id: String,
    description: String,
}

fn need(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
fn identifier(s: &str) -> Result<(), String> {
    need(
        !s.trim().is_empty() && s.len() <= 256,
        "partial identifier absent or too long",
    )
}
fn sha(s: &str) -> Result<(), String> {
    need(
        s.len() == 64
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "partial digest invalid",
    )
}
fn matching(attributes: &Value, selector: &Value) -> Result<bool, String> {
    let fields = selector
        .as_object()
        .filter(|x| !x.is_empty())
        .ok_or("partial selector must be a nonempty object")?;
    need(
        fields
            .values()
            .all(|v| v.is_string() || v.is_boolean() || v.is_number()),
        "partial selector values must be scalar",
    )?;
    Ok(fields.iter().all(|(k, v)| attributes.get(k) == Some(v)))
}
fn tree(root: &Value) -> Result<Vec<&Value>, String> {
    let mut stack = vec![(root, 0usize)];
    let mut result = Vec::new();
    while let Some((node, depth)) = stack.pop() {
        need(
            depth <= 128 && result.len() < 10000,
            "partial tree exceeds bound",
        )?;
        need(
            node["attributes"].is_object(),
            "partial tree attributes missing",
        )?;
        let children = node["children"]
            .as_array()
            .ok_or("partial tree children missing")?;
        stack.extend(children.iter().rev().map(|n| (n, depth + 1)));
        result.push(node);
    }
    Ok(result)
}
fn observe(
    raw: &Value,
    selector: &Selector,
    owner_attributes: Option<&Value>,
) -> Result<Value, String> {
    match selector {
        Selector::HypiumNativeTest { class, test } => {
            need(
                owner_attributes.is_none(),
                "partial Hypium adapter does not accept owner attributes",
            )?;
            identifier(class)?;
            identifier(test)?;
            let results = hypium_results(raw)?;
            results
                .get(&(class.clone(), test.clone()))
                .cloned()
                .map(Value::String)
                .ok_or("partial Hypium test absent".into())
        }
        Selector::JsonPointer { pointer } => {
            need(
                owner_attributes.is_none(),
                "partial pointer adapter does not accept owner attributes",
            )?;
            need(
                pointer.is_empty() || pointer.starts_with('/'),
                "partial JSON pointer invalid",
            )?;
            raw.pointer(pointer)
                .cloned()
                .ok_or("partial JSON pointer absent".into())
        }
        Selector::AttributeTree { owner, node, field } => {
            identifier(field)?;
            let mut owner = owner.clone();
            if let Some(bindings) = owner_attributes {
                matching(&Value::Null, bindings)?;
                let fields = owner
                    .as_object_mut()
                    .ok_or("partial owner selector invalid")?;
                for (key, value) in bindings.as_object().unwrap() {
                    need(
                        fields.get(key).is_none_or(|old| old == value),
                        "partial control owner conflicts with shared selector",
                    )?;
                    fields.insert(key.clone(), value.clone());
                }
            }
            // Validate both selectors even when no matching owner is found.
            matching(&Value::Null, &owner)?;
            matching(&Value::Null, node)?;
            let owners = tree(raw)?
                .into_iter()
                .filter_map(|n| {
                    matching(&n["attributes"], &owner)
                        .ok()
                        .filter(|x| *x)
                        .map(|_| n)
                })
                .collect::<Vec<_>>();
            need(owners.len() == 1, "partial page owner absent or ambiguous")?;
            let nodes = tree(owners[0])?
                .into_iter()
                .filter_map(|n| {
                    matching(&n["attributes"], node)
                        .ok()
                        .filter(|x| *x)
                        .map(|_| n)
                })
                .collect::<Vec<_>>();
            need(nodes.len() == 1, "partial observable absent or ambiguous")?;
            nodes[0]["attributes"]
                .get(field)
                .cloned()
                .ok_or("partial observable field absent".into())
        }
    }
}

// Supported lane: completed, non-skipped Hypium tests using native status
// codes 1/start, 0/pass and -2/assertion failure. Other codes are not kills.
fn hypium_results(raw: &Value) -> Result<BTreeMap<(String, String), String>, String> {
    need(
        raw["exitCode"].as_i64() == Some(0) && raw["timedOut"] == false,
        "partial Hypium process interrupted",
    )?;
    need(raw["stderr"].is_string(), "partial Hypium stderr absent")?;
    let stdout = raw["stdout"]
        .as_str()
        .ok_or("partial Hypium stdout absent")?;
    let mut fields = BTreeMap::<String, String>::new();
    let mut pending = BTreeMap::new();
    let mut results = BTreeMap::<(String, String), String>::new();
    let mut ordinals = BTreeSet::new();
    let mut announced_total = None;
    let mut summary = None;
    let mut final_code = None;
    for line in stdout.lines().map(str::trim) {
        need(
            !line.starts_with("OHOS_REPORT_ALL_RESULT:")
                && !line.starts_with("OHOS_REPORT_ALL_CODE:"),
            "partial Hypium aggregate report lane unsupported",
        )?;
        if let Some(value) = line.strip_prefix("OHOS_REPORT_STATUS: ") {
            if let Some((key, value)) = value.split_once('=') {
                fields.insert(key.into(), value.into());
            }
        } else if let Some(value) = line.strip_prefix("OHOS_REPORT_STATUS_CODE: ") {
            need(summary.is_none(), "partial Hypium status follows summary")?;
            let code: i64 = value
                .parse()
                .map_err(|_| "partial Hypium status code invalid")?;
            need(
                matches!(code, 1 | 0 | -2),
                "partial Hypium unsupported/error status",
            )?;
            let class = fields
                .get("class")
                .ok_or("partial Hypium class absent")?
                .clone();
            let test = fields
                .get("test")
                .ok_or("partial Hypium test absent")?
                .clone();
            identifier(&class)?;
            identifier(&test)?;
            let number = |key| -> Result<usize, String> {
                fields
                    .get(key)
                    .ok_or("partial Hypium inventory absent")?
                    .parse()
                    .map_err(|_| "partial Hypium inventory invalid".into())
            };
            let total = number("numtests")?;
            let current = number("current")?;
            need(
                total > 0 && total <= 1024 && current > 0 && current <= total,
                "partial Hypium inventory outside bound",
            )?;
            need(
                announced_total.is_none_or(|n| n == total),
                "partial Hypium inventory changed",
            )?;
            announced_total = Some(total);
            let key = (class, test);
            if code == 1 {
                need(
                    !results.contains_key(&key)
                        && pending.insert(key, current).is_none()
                        && ordinals.insert(current),
                    "partial Hypium duplicate test start",
                )?;
            } else {
                need(
                    pending.remove(&key) == Some(current),
                    "partial Hypium completion lacks matching start",
                )?;
                need(
                    results
                        .insert(key, if code == 0 { "passed" } else { "failed" }.into())
                        .is_none(),
                    "partial Hypium duplicate completion",
                )?;
            }
            fields.clear();
        } else if let Some(value) = line.strip_prefix("OHOS_REPORT_RESULT: stream=Tests run: ") {
            need(summary.is_none(), "partial Hypium duplicate summary")?;
            let mut counts = Vec::new();
            let mut parts = value.split(", ");
            counts.push(
                parts
                    .next()
                    .ok_or("partial Hypium summary absent")?
                    .parse::<usize>()
                    .map_err(|_| "partial Hypium summary invalid")?,
            );
            for label in ["Failure: ", "Error: ", "Pass: ", "Ignore: "] {
                counts.push(
                    parts
                        .next()
                        .and_then(|p| p.strip_prefix(label))
                        .ok_or("partial Hypium summary invalid")?
                        .parse::<usize>()
                        .map_err(|_| "partial Hypium summary invalid")?,
                );
            }
            need(
                parts.next().is_none() && pending.is_empty(),
                "partial Hypium unfinished inventory",
            )?;
            summary = Some(counts);
        } else if let Some(value) = line.strip_prefix("OHOS_REPORT_CODE: ") {
            need(
                summary.is_some() && final_code.is_none(),
                "partial Hypium final code absent/duplicated/out of order",
            )?;
            final_code = Some(
                value
                    .parse::<i64>()
                    .map_err(|_| "partial Hypium final code invalid")?,
            );
        }
    }
    let counts = summary.ok_or("partial Hypium final summary absent")?;
    let failures = results.values().filter(|s| s.as_str() == "failed").count();
    need(
        counts[0] > 0
            && Some(counts[0]) == announced_total
            && counts[0] == results.len()
            && counts[0] == ordinals.len()
            && counts[1] == failures
            && counts[2] == 0
            && counts[4] == 0
            && counts[3] == results.len() - failures,
        "partial Hypium native counts inconsistent or error/ignored tests present",
    )?;
    need(
        final_code == Some(if failures == 0 { 0 } else { -1 }),
        "partial Hypium final code contradicts outcomes",
    )?;
    Ok(results)
}
fn read(root: &Path, observation: &Observation) -> Result<Vec<u8>, String> {
    let relative = Path::new(&observation.path);
    need(
        !relative.as_os_str().is_empty()
            && relative
                .components()
                .all(|x| matches!(x, Component::Normal(_))),
        "partial path unsafe",
    )?;
    let mut current = root.to_path_buf();
    need(
        !fs::symlink_metadata(&current)
            .map_err(|e| e.to_string())?
            .file_type()
            .is_symlink(),
        "partial root is symlink",
    )?;
    for part in relative.components() {
        current.push(part.as_os_str());
        need(
            !fs::symlink_metadata(&current)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink(),
            "partial path is symlink",
        )?;
    }
    let meta = fs::metadata(&current).map_err(|e| e.to_string())?;
    need(
        meta.is_file() && meta.len() <= 2 * 1024 * 1024,
        "partial capture is not a bounded regular file",
    )?;
    fs::read(current).map_err(|e| e.to_string())
}

/// The reviewed profile interprets retained observations, not implementation
/// identity or producer authenticity. Formal gate actions are copied unchanged.
pub fn plan(
    readiness: &[u8],
    profile: &[u8],
    root: &Path,
    previous: Option<&[u8]>,
) -> Result<Value, String> {
    need(
        profile.len() <= 2 * 1024 * 1024,
        "partial profile exceeds bound",
    )?;
    let formal = maintainer_downstream::plan(readiness, None)?;
    let p: Profile = serde_json::from_slice(profile).map_err(|e| e.to_string())?;
    need(
        p.schema == "agentlab.partial_calibration_profile.v1" && p.reviewed,
        "partial profile unreviewed or unsupported",
    )?;
    for (actual, expected) in [
        (&p.candidate_id, &formal["candidateId"]),
        (&p.candidate_sha256, &formal["candidateSha256"]),
        (&p.source_revision, &formal["sourceRevision"]),
        (
            &p.construction_plan_sha256,
            &formal["constructionPlanSha256"],
        ),
    ] {
        need(
            expected.as_str() == Some(actual.as_str()),
            "partial candidate/source/plan binding differs",
        )?;
    }
    identifier(&p.target_peer_id)?;
    for s in [&p.candidate_sha256, &p.construction_plan_sha256] {
        sha(s)?;
    }
    need(
        p.runtime_identity
            .as_object()
            .is_some_and(|o| !o.is_empty()),
        "partial runtime identity absent",
    )?;
    need(
        !p.phases.is_empty()
            && p.phases.len() <= 16
            && p.controls.len() <= 16
            && !p.controls.is_empty()
            && p.remaining_controls.len() <= 32,
        "partial profile size invalid",
    )?;
    let mut phase_ids = BTreeSet::new();
    let mut check_ids = BTreeSet::new();
    for phase in &p.phases {
        identifier(&phase.id)?;
        need(phase_ids.insert(&phase.id), "partial phase duplicated")?;
        need(
            !phase.checks.is_empty() && phase.checks.len() <= 64,
            "partial checks missing or excessive",
        )?;
        for check in &phase.checks {
            identifier(&check.id)?;
            need(
                check_ids.insert(format!("{}/{}", phase.id, check.id)),
                "partial check duplicated",
            )?;
        }
    }
    let mut control_ids = BTreeSet::new();
    let mut signatures = BTreeSet::new();
    let mut accepted = 0;
    let mut wrong = 0;
    let mut conclusions = Vec::new();
    let mut owned_captures = Vec::new();
    let mut capture_files = Vec::new();
    let mut checks = Vec::new();
    let mut total_bytes = 0;
    for control in &p.controls {
        identifier(&control.id)?;
        need(
            control_ids.insert(&control.id),
            "partial control duplicated",
        )?;
        need(
            control.role == "accepted" || control.role == "wrong",
            "partial control role unknown",
        )?;
        let expected = control
            .expected_failed_check_ids
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        need(
            expected.len() == control.expected_failed_check_ids.len()
                && expected.is_subset(&check_ids),
            "partial expected failures duplicated or unknown",
        )?;
        need(
            (control.role == "accepted" && expected.is_empty())
                || (control.role == "wrong" && !expected.is_empty()),
            "partial role contradicts expected failures",
        )?;
        need(
            control.observations.len() == phase_ids.len(),
            "partial control phases incomplete",
        )?;
        let mut seen = BTreeSet::new();
        let mut failed = BTreeSet::new();
        let mut signature = Vec::new();
        for observation in &control.observations {
            need(
                seen.insert(&observation.phase),
                "partial observation phase duplicated",
            )?;
            let phase = p
                .phases
                .iter()
                .find(|x| x.id == observation.phase)
                .ok_or("partial observation phase unknown")?;
            sha(&observation.raw_sha256)?;
            sha(&observation.envelope_sha256)?;
            let envelope_bytes = read(root, observation)?;
            need(
                digest(&envelope_bytes) == observation.envelope_sha256,
                "partial envelope digest differs",
            )?;
            let envelope: Value =
                serde_json::from_slice(&envelope_bytes).map_err(|e| e.to_string())?;
            need(
                envelope["ok"] == true
                    && envelope["result"]["ok"] == true
                    && envelope["targetPeerId"] == p.target_peer_id
                    && matches!(
                        envelope["routeDecision"].as_str(),
                        Some("peer_direct" | "upstream_local_peer")
                    ),
                "partial capture target or read failed",
            )?;
            let content = envelope["result"]["content"]
                .as_str()
                .ok_or("partial raw content absent")?;
            total_bytes += content.len();
            need(
                total_bytes <= 32 * 1024 * 1024,
                "partial raw content budget exceeded",
            )?;
            need(
                content.len() == observation.byte_length
                    && envelope["result"]["size"].as_u64() == Some(content.len() as u64)
                    && digest(content.as_bytes()) == observation.raw_sha256,
                "partial raw digest or length differs",
            )?;
            let raw: Value = serde_json::from_str(content).map_err(|e| e.to_string())?;
            for check in &phase.checks {
                let actual = observe(&raw, &check.selector, control.owner_attributes.as_ref())?;
                let id = format!("{}/{}", phase.id, check.id);
                let passed = actual == check.expected;
                if !passed {
                    failed.insert(id.clone());
                }
                checks.push(json!({"controlId":control.id,"phase":phase.id,"checkId":id,"actual":actual,"expected":check.expected,"passed":passed}));
            }
            signature.push(json!([phase.id, observation.raw_sha256]));
            owned_captures.push(json!({"controlId":control.id,"phase":phase.id,"rawSha256":observation.raw_sha256,"bytes":observation.byte_length}));
            capture_files.push(json!({"controlId":control.id,"phase":phase.id,"path":observation.path,
                "envelopeSha256":observation.envelope_sha256,"rawSha256":observation.raw_sha256,"byteLength":observation.byte_length}));
        }
        signature.sort_by_key(Value::to_string);
        need(
            signatures.insert(digest(
                &serde_json::to_vec(&signature).map_err(|e| e.to_string())?,
            )),
            "partial duplicate control capture",
        )?;
        let matched = failed == expected;
        if matched && control.role == "accepted" {
            accepted += 1;
        }
        if matched && control.role == "wrong" {
            wrong += 1;
        }
        conclusions.push(json!({"id":control.id,"declaredRole":control.role,"ownerAttributes":control.owner_attributes,"expectedFailedCheckIds":expected,"failedCheckIds":failed,"matchesReviewedExpectation":matched}));
    }
    let compatible = conclusions
        .iter()
        .all(|c| c["matchesReviewedExpectation"] == true);
    let mut remaining_ids = BTreeSet::new();
    let mut actions = Vec::new();
    for item in &p.remaining_controls {
        identifier(&item.id)?;
        identifier(&item.description)?;
        need(
            remaining_ids.insert(&item.id),
            "partial remaining control duplicated",
        )?;
        actions.push(json!({"kind":"complete-scoped-calibration-control","id":item.id,"description":item.description,
            "runtimeIdentity":p.runtime_identity,"executionAuthorized":false}));
    }
    let readiness_value: Value = serde_json::from_slice(readiness).map_err(|e| e.to_string())?;
    let required_wrong = readiness_value["checks"]["wrongVariantCalibration"]["requiredCount"]
        .as_u64()
        .unwrap();
    if compatible && accepted == 0 {
        actions.push(json!({"kind":"complete-scoped-accepted-control","runtimeIdentity":p.runtime_identity,"executionAuthorized":false}));
    }
    if compatible && wrong < required_wrong {
        actions.push(json!({"kind":"complete-scoped-wrong-controls","requiredCount":required_wrong,"observedCount":wrong,
            "runtimeIdentity":p.runtime_identity,"executionAuthorized":false}));
    }
    if !compatible {
        actions = vec![
            json!({"kind":"repair-scoped-observation-calibration","executionAuthorized":false}),
        ];
    } else if actions.is_empty() {
        actions.push(
            json!({"kind":"review-scoped-observation-admission","executionAuthorized":false}),
        );
    }
    // Selector/expectation changes are new work, transport metadata is not.
    let profile_value: Value = serde_json::from_slice(profile).map_err(|e| e.to_string())?;
    if formal["actions"]
        .as_array()
        .is_some_and(|a| a.iter().any(|x| x["kind"] == "focused-knowledge-refresh"))
    {
        actions = formal["actions"].as_array().unwrap().clone();
    }
    let consumer_sha = digest(include_bytes!("maintainer_partial_calibration.rs"));
    let owned = json!({"consumerSha256":consumer_sha,"candidateSha256":p.candidate_sha256,"sourceRevision":p.source_revision,
        "constructionPlanSha256":p.construction_plan_sha256,"targetPeerId":p.target_peer_id,
        "phaseContract":profile_value["phases"],
        "runtimeIdentity":p.runtime_identity,"captures":owned_captures,"checks":checks,"controls":conclusions,
        "scopedActions":actions,"formalGateStateSha256":formal["gateStateSha256"]});
    let owned_sha = digest(&serde_json::to_vec(&owned).map_err(|e| e.to_string())?);
    let mut unchanged = false;
    if let Some(bytes) = previous {
        let previous: Value = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
        need(
            previous["schema"] == "agentlab.partial_calibration_feedback_plan.v1"
                && previous["candidateId"] == p.candidate_id
                && previous["candidateSha256"] == p.candidate_sha256
                && previous["automaticPromotion"] == false
                && previous["qualified"] == false
                && previous["authorityWritePerformed"] == false
                && previous["agentExecutionPerformed"] == false
                && previous["producerAuthenticated"] == false
                && previous["implementationMutationVerified"] == false
                && previous["runtimeIdentityAttested"] == false,
            "partial previous feedback invalid",
        )?;
        let previous_sha = previous["ownedWorkSha256"]
            .as_str()
            .ok_or("partial previous work digest absent")?;
        sha(previous_sha)?;
        need(
            previous["ownedWork"].is_object()
                && digest(&serde_json::to_vec(&previous["ownedWork"]).map_err(|e| e.to_string())?)
                    == previous_sha,
            "partial previous owned work digest differs",
        )?;
        if previous["ownedWorkSha256"] == owned_sha {
            need(
                previous["ownedWork"] == owned
                    && previous["scopedActions"] == Value::Array(actions.clone())
                    && previous["formalGateActions"] == formal["actions"],
                "partial previous owned work differs",
            )?;
            unchanged = true;
        }
    }
    Ok(
        json!({"schema":"agentlab.partial_calibration_feedback_plan.v1",
        "candidateId":p.candidate_id,"candidateSha256":p.candidate_sha256,
        "sourceRevision":p.source_revision,"profileSha256":digest(profile),
        "consumerSha256":consumer_sha,"captureFiles":capture_files,
        "readinessSha256":digest(readiness),"ownedWorkSha256":owned_sha,"ownedWork":owned,
        "status":if unchanged {"awaiting-new-evidence"} else {"scoped-followup-planned"},
        "schedulingAllowed":!unchanged,"scopedControlsConsistent":compatible,
        "acceptedObservationControlCount":accepted,"rejectedObservationControlCount":wrong,
        "scopedActions":actions,"formalGateActions":formal["actions"],
        "formalGateStateSha256":formal["gateStateSha256"],
        "qualified":false,"automaticPromotion":false,"authorityWritePerformed":false,
        "agentExecutionPerformed":false,"producerAuthenticated":false,
        "implementationMutationVerified":false,"runtimeIdentityAttested":false,
        "verificationBoundary":"reviewed recorded-observation content only; no build/source-mutation authentication, runtime substitution, formal qualification or execution"}),
    )
}
