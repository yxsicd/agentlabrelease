use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};

const PACKET_SCHEMA: &str = "agentlab.purchase_data_integrated_review_packet.v1";
const ANSWERS_SCHEMA: &str = "agentlab.purchase_data_integrated_review_answers.v1";
const DECISION_SCHEMA: &str = "agentlab.purchase_data_integrated_review_decision.v1";
const GATE_SCHEMA: &str = "agentlab.purchase_data_integrated_review_gate.v1";

const QUESTION_IDS: &[&str] = &[
    "cross-repository-semantic-coherence",
    "source-patch-preservation",
    "functional-oracle-discrimination",
    "runtime-mapping-scope",
    "case-performance-discrimination",
    "residual-boundary-honesty",
];

const RISK_IDS: &[&str] = &[
    "independent-semantic-review-pending",
    "self-authored-source-candidate",
    "cordova-runtime-source-seam-only",
    "live-vendor-iap-unexecuted",
    "x86-emulator-not-real-device",
    "controlled-performance-variants-not-agent-evaluation",
    "absolute-power-thermal-unavailable",
    "upstream-source-unpublished",
];

const ATTACHMENT_IDS: &[&str] = &[
    "behavior-oracle-calibration",
    "behavior-oracle-plan",
    "case-performance-qualification",
    "functional-mutation-qualification",
    "performance-detector-qualification",
    "profile-qualification",
    "runtime-oracle-bridge",
    "semantic-review-packet",
    "source-review-packet",
];

const ROLES: &[&str] = &["semantic", "oracle"];
const VERDICTS: &[&str] = &[
    "approve-for-next-calibration-gate",
    "reject-candidate",
    "defer-for-more-evidence",
];

const APPROVED_BOUNDARY: &str = "Two distinct authenticated reviewers approved the exact current-evidence packet. This authorizes only publication of the exact reviewed source patch, upstream revision rebinding and subsequent unseen Agent cohort evaluation. It does not publish source, verify the full cross-repository behavior Oracle, qualify Cordova runtime, live vendor IAP, real-device or absolute power/thermal behavior, authorize a case contract, convert controlled calibration variants into Agent runs, or promote automatically.";
const NON_APPROVED_BOUNDARY: &str = "Two distinct authenticated review decisions were retained for the exact current-evidence packet, but they did not unanimously approve advancement. No source publication, upstream rebinding, unseen Agent cohort evaluation, case contract or automatic promotion is authorized.";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: &Path, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(path)
            .map_err(|error| format!("cannot inspect {label}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("{label} must be a regular file"));
        }
        let bytes = fs::read(path).map_err(|error| format!("cannot read {label}: {error}"))?;
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|error| format!("cannot parse {label}: {error}"))?;
        if !value.is_object() {
            return Err(format!("{label} must be a JSON object"));
        }
        Ok(Self { bytes, value })
    }

    fn sha256(&self) -> String {
        digest(&self.bytes)
    }
}

fn string<'a>(value: &'a Value, key: &str, label: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .filter(|item| !item.is_empty())
        .ok_or_else(|| format!("{label} {key} is absent"))
}

fn same(actual: &str, expected: &str, label: &str) -> Result<(), String> {
    if actual != expected {
        return Err(format!("{label} differs"));
    }
    Ok(())
}

fn exact_bool(value: &Value, key: &str, expected: bool, label: &str) -> Result<(), String> {
    if value[key].as_bool() != Some(expected) {
        return Err(format!("{label} {key} differs"));
    }
    Ok(())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn valid_revision(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn valid_reviewer(value: &str) -> bool {
    value.starts_with("github:")
        && value.len() > "github:".len()
        && value.len() <= 200
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_.:@/-".contains(&byte))
}

fn exact_string_set(value: &Value, expected: &[&str], label: &str) -> Result<(), String> {
    let rows = value
        .as_array()
        .ok_or_else(|| format!("{label} must be an array"))?;
    let actual: BTreeSet<&str> = rows
        .iter()
        .map(|row| {
            row.as_str()
                .ok_or_else(|| format!("{label} must contain strings"))
        })
        .collect::<Result<_, _>>()?;
    let expected: BTreeSet<&str> = expected.iter().copied().collect();
    if rows.len() != expected.len() || actual != expected {
        return Err(format!("{label} differs"));
    }
    Ok(())
}

fn object_ids<'a>(value: &'a Value, label: &str) -> Result<BTreeSet<&'a str>, String> {
    value
        .as_array()
        .ok_or_else(|| format!("{label} must be an array"))?
        .iter()
        .map(|row| string(row, "id", label))
        .collect()
}

fn validate_packet(packet: &Value) -> Result<(), String> {
    same(
        string(packet, "schema", "integrated packet")?,
        PACKET_SCHEMA,
        "integrated packet schema",
    )?;
    same(
        string(packet, "status", "integrated packet")?,
        "current-evidence-bound-independent-dual-review-required",
        "integrated packet status",
    )?;
    same(
        string(packet, "nextGate", "integrated packet")?,
        "authenticated-distinct-semantic-and-oracle-reviewers-then-upstream-publication-rebinding-and-unseen-agent-cohort-evaluation",
        "integrated packet next gate",
    )?;
    for key in [
        "semanticAlignmentVerified",
        "independentSourceReviewCompleted",
        "independentOracleReviewCompleted",
        "behaviorOracleVerified",
        "cordovaRuntimeCalibrated",
        "liveVendorIapExecuted",
        "realDeviceExecuted",
        "absolutePowerThermalQualified",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(packet, key, false, "integrated packet")?;
    }
    exact_bool(
        packet,
        "relativePerformanceDetectorCalibrated",
        true,
        "integrated packet",
    )?;
    for key in [
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "performanceCalibrated",
    ] {
        exact_bool(packet, key, true, "integrated packet")?;
    }

    let lineage = &packet["sourceLineage"];
    for key in ["analysisSourceSetSha256", "runtimeSourceSetSha256"] {
        if !valid_sha256(string(lineage, key, "integrated source lineage")?) {
            return Err(format!("integrated source lineage {key} is invalid"));
        }
    }
    for key in ["baseRevision", "candidateRevision"] {
        if !valid_revision(string(lineage, key, "integrated source lineage")?) {
            return Err(format!("integrated source lineage {key} is invalid"));
        }
    }

    let contract = &packet["reviewDecisionContract"];
    same(
        string(contract, "reviewerIdentityAuthority", "review contract")?,
        "authenticated-github-actor-on-trusted-main",
        "review identity authority",
    )?;
    if contract["minimumDistinctReviewerCount"].as_u64() != Some(2) {
        return Err("review contract minimumDistinctReviewerCount differs".into());
    }
    for key in [
        "semanticAndOracleReviewerMustDiffer",
        "reviewersMustDifferFromCandidateAuthor",
        "approvalRequiresEveryAnswerYes",
    ] {
        exact_bool(contract, key, true, "review contract")?;
    }
    exact_string_set(
        &contract["answers"],
        &["yes", "no", "unknown"],
        "review answers",
    )?;
    exact_string_set(&contract["verdicts"], VERDICTS, "review verdicts")?;
    let questions = contract["questions"]
        .as_array()
        .ok_or_else(|| "review questions must be an array".to_owned())?;
    let question_ids = object_ids(&contract["questions"], "review question")?;
    let expected_questions: BTreeSet<&str> = QUESTION_IDS.iter().copied().collect();
    if questions.len() != QUESTION_IDS.len() || question_ids != expected_questions {
        return Err("review question inventory differs".into());
    }
    for question in questions {
        if string(question, "question", "review question")?.len() < 20 {
            return Err("review question is too short".into());
        }
    }

    let risks = packet["risks"]
        .as_array()
        .ok_or_else(|| "review risks must be an array".to_owned())?;
    let risk_ids = object_ids(&packet["risks"], "review risk")?;
    let expected_risks: BTreeSet<&str> = RISK_IDS.iter().copied().collect();
    if risks.len() != RISK_IDS.len() || risk_ids != expected_risks {
        return Err("review risk inventory differs".into());
    }
    for risk in risks {
        if string(risk, "statement", "review risk")?.len() < 20 {
            return Err("review risk statement is too short".into());
        }
    }

    let attachments = packet["evidenceAttachments"]
        .as_object()
        .ok_or_else(|| "evidenceAttachments must be an object".to_owned())?;
    let actual_ids: BTreeSet<&str> = attachments.keys().map(String::as_str).collect();
    let expected_ids: BTreeSet<&str> = ATTACHMENT_IDS.iter().copied().collect();
    if attachments.len() != ATTACHMENT_IDS.len() || actual_ids != expected_ids {
        return Err("integrated attachment inventory differs".into());
    }
    for (id, attachment) in attachments {
        let path = string(attachment, "path", "evidence attachment")?;
        if path.starts_with('/') || path.split('/').any(|part| part == ".." || part.is_empty()) {
            return Err(format!("evidence attachment path is invalid: {id}"));
        }
        if !valid_sha256(string(attachment, "sha256", "evidence attachment")?)
            || attachment["byteLength"].as_u64() == Some(0)
            || string(attachment, "schema", "evidence attachment")?.is_empty()
        {
            return Err(format!("evidence attachment identity is invalid: {id}"));
        }
    }
    Ok(())
}

fn validate_attachments(packet: &Value, root: &Path) -> Result<Value, String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("cannot resolve qualification root: {error}"))?;
    let attachments = packet["evidenceAttachments"]
        .as_object()
        .ok_or_else(|| "evidenceAttachments must be an object".to_owned())?;
    let mut source_author = None;
    for id in ATTACHMENT_IDS {
        let attachment = &attachments[*id];
        let relative = string(attachment, "path", "evidence attachment")?;
        let path = root.join(relative);
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| format!("cannot inspect evidence attachment {id}: {error}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err(format!("evidence attachment must be a regular file: {id}"));
        }
        let resolved = path
            .canonicalize()
            .map_err(|error| format!("cannot resolve evidence attachment {id}: {error}"))?;
        if !resolved.starts_with(&root) {
            return Err(format!(
                "evidence attachment leaves qualification root: {id}"
            ));
        }
        let input = Input::load(&resolved, &format!("evidence attachment {id}"))?;
        same(
            &input.sha256(),
            string(attachment, "sha256", "evidence attachment")?,
            &format!("evidence attachment digest {id}"),
        )?;
        if attachment["byteLength"].as_u64() != Some(input.bytes.len() as u64) {
            return Err(format!("evidence attachment byte length differs: {id}"));
        }
        same(
            string(&input.value, "schema", "evidence attachment")?,
            string(attachment, "schema", "evidence attachment")?,
            &format!("evidence attachment schema {id}"),
        )?;
        if let Some(expected_status) = attachment["status"].as_str() {
            same(
                string(&input.value, "status", "evidence attachment")?,
                expected_status,
                &format!("evidence attachment status {id}"),
            )?;
        }
        if *id == "source-review-packet" {
            let author = input.value["candidateAuthor"].clone();
            if !author.is_object()
                || string(&author, "authority", "candidate author").is_err()
                || string(&author, "name", "candidate author").is_err()
                || string(&author, "email", "candidate author").is_err()
            {
                return Err("source candidate author is invalid".into());
            }
            source_author = Some(author);
        }
    }
    source_author.ok_or_else(|| "source candidate author is absent".to_owned())
}

fn normalize_answers(value: &Value) -> Result<Vec<Value>, String> {
    same(
        string(value, "schema", "review answers")?,
        ANSWERS_SCHEMA,
        "review answers schema",
    )?;
    let rows = value["responses"]
        .as_array()
        .ok_or_else(|| "review responses must be an array".to_owned())?;
    let mut normalized = Vec::new();
    for row in rows {
        let object = row
            .as_object()
            .ok_or_else(|| "review response must be an object".to_owned())?;
        if object.len() != 3
            || !object.contains_key("id")
            || !object.contains_key("answer")
            || !object.contains_key("rationale")
        {
            return Err("review response fields differ".into());
        }
        let id = string(row, "id", "review response")?;
        if !QUESTION_IDS.contains(&id) {
            return Err(format!("review response id is invalid: {id}"));
        }
        let answer = string(row, "answer", "review response")?;
        if !["yes", "no", "unknown"].contains(&answer) {
            return Err(format!("review response answer is invalid: {id}"));
        }
        let rationale = string(row, "rationale", "review response")?.trim();
        if !(20..=2000).contains(&rationale.len()) {
            return Err(format!("review response rationale is invalid: {id}"));
        }
        normalized.push(json!({"id": id, "answer": answer, "rationale": rationale}));
    }
    normalized.sort_by(|left, right| left["id"].as_str().cmp(&right["id"].as_str()));
    let actual: Vec<&str> = normalized
        .iter()
        .filter_map(|row| row["id"].as_str())
        .collect();
    let mut expected = QUESTION_IDS.to_vec();
    expected.sort_unstable();
    if actual != expected {
        return Err("review answers must cover every question exactly".into());
    }
    Ok(normalized)
}

fn validate_verdict(verdict: &str, responses: &[Value]) -> Result<(), String> {
    if !VERDICTS.contains(&verdict) {
        return Err("integrated-review verdict is invalid".into());
    }
    let answers: BTreeSet<&str> = responses
        .iter()
        .filter_map(|row| row["answer"].as_str())
        .collect();
    match verdict {
        "approve-for-next-calibration-gate" if answers == BTreeSet::from(["yes"]) => Ok(()),
        "reject-candidate" if answers.contains("no") => Ok(()),
        "defer-for-more-evidence" if answers.contains("unknown") && !answers.contains("no") => {
            Ok(())
        }
        "approve-for-next-calibration-gate" => {
            Err("approval requires every integrated-review answer to be yes".into())
        }
        "reject-candidate" => Err("rejection requires at least one no answer".into()),
        _ => Err("deferral requires unknown answers and no rejection".into()),
    }
}

fn decide(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let packet = Input::load(&path(values, "--packet")?, "integrated packet")?;
    validate_packet(&packet.value)?;
    let candidate_author =
        validate_attachments(&packet.value, &path(values, "--qualification-root")?)?;
    let expected = value(values, "--expected-packet-sha256")?;
    if !valid_sha256(expected) || packet.sha256() != expected {
        return Err("expected integrated packet digest differs".into());
    }
    let role = value(values, "--role")?;
    if !ROLES.contains(&role) {
        return Err("integrated-review role is invalid".into());
    }
    let reviewer = value(values, "--reviewer")?.trim();
    if !valid_reviewer(reviewer) {
        return Err("integrated reviewer identity is invalid".into());
    }
    if candidate_author["authority"] == "authenticated-github-actor-on-trusted-main"
        && candidate_author["name"].as_str() == Some(reviewer)
    {
        return Err("integrated reviewer must differ from candidate author".into());
    }
    let answers = Input::load(&path(values, "--answers")?, "review answers")?;
    let responses = normalize_answers(&answers.value)?;
    let acknowledged: BTreeSet<&str> = value(values, "--acknowledged-risk-ids")?
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .collect();
    let expected_risks: BTreeSet<&str> = RISK_IDS.iter().copied().collect();
    if acknowledged != expected_risks {
        return Err("integrated reviewer must acknowledge every risk exactly".into());
    }
    let verdict = value(values, "--verdict")?;
    validate_verdict(verdict, &responses)?;
    let rationale = value(values, "--rationale")?.trim();
    if !(20..=2000).contains(&rationale.len()) {
        return Err("integrated-review decision rationale is invalid".into());
    }
    Ok(json!({
        "schema": DECISION_SCHEMA,
        "role": role,
        "packetSha256": packet.sha256(),
        "semanticCandidateId": packet.value["semanticCandidateId"],
        "runtimeCandidateId": packet.value["runtimeCandidateId"],
        "sourceLineage": packet.value["sourceLineage"],
        "candidateAuthor": candidate_author,
        "reviewer": reviewer,
        "responses": responses,
        "acknowledgedRiskIds": acknowledged.into_iter().collect::<Vec<_>>(),
        "verdict": verdict,
        "rationale": rationale,
        "approvedForNextCalibrationGate": verdict == "approve-for-next-calibration-gate",
        "allowsCaseContract": false,
        "automaticPromotion": false
    }))
}

fn validate_decision(
    packet: &Input,
    decision: &Value,
    expected_role: &str,
    candidate_author: &Value,
) -> Result<(), String> {
    same(
        string(decision, "schema", "integrated decision")?,
        DECISION_SCHEMA,
        "integrated decision schema",
    )?;
    same(
        string(decision, "role", "integrated decision")?,
        expected_role,
        "integrated decision role",
    )?;
    same(
        string(decision, "packetSha256", "integrated decision")?,
        &packet.sha256(),
        "integrated decision packet digest",
    )?;
    for key in ["semanticCandidateId", "runtimeCandidateId"] {
        same(
            string(decision, key, "integrated decision")?,
            string(&packet.value, key, "integrated packet")?,
            &format!("integrated decision {key}"),
        )?;
    }
    if decision["sourceLineage"] != packet.value["sourceLineage"] {
        return Err("integrated decision source lineage differs".into());
    }
    if decision["candidateAuthor"] != *candidate_author {
        return Err("integrated decision candidate author differs".into());
    }
    let reviewer = string(decision, "reviewer", "integrated decision")?;
    if !valid_reviewer(reviewer) {
        return Err("integrated decision reviewer is invalid".into());
    }
    let rationale = string(decision, "rationale", "integrated decision")?.trim();
    if !(20..=2000).contains(&rationale.len()) {
        return Err("integrated decision rationale is invalid".into());
    }
    let responses = normalize_answers(&json!({
        "schema": ANSWERS_SCHEMA,
        "responses": decision["responses"]
    }))?;
    if decision["responses"] != Value::Array(responses.clone()) {
        return Err("integrated decision responses are not normalized".into());
    }
    let verdict = string(decision, "verdict", "integrated decision")?;
    validate_verdict(verdict, &responses)?;
    exact_string_set(
        &decision["acknowledgedRiskIds"],
        RISK_IDS,
        "acknowledged integrated risks",
    )?;
    exact_bool(
        decision,
        "approvedForNextCalibrationGate",
        verdict == "approve-for-next-calibration-gate",
        "integrated decision",
    )?;
    for key in ["allowsCaseContract", "automaticPromotion"] {
        exact_bool(decision, key, false, "integrated decision")?;
    }
    Ok(())
}

fn gate_status(semantic_verdict: &str, oracle_verdict: &str) -> (&'static str, bool) {
    if semantic_verdict == "approve-for-next-calibration-gate"
        && oracle_verdict == "approve-for-next-calibration-gate"
    {
        (
            "independent-dual-review-approved-next-calibration-only",
            true,
        )
    } else if semantic_verdict == "reject-candidate" || oracle_verdict == "reject-candidate" {
        ("independent-dual-review-rejected", false)
    } else {
        ("independent-dual-review-deferred", false)
    }
}

fn compile(values: &BTreeMap<String, String>) -> Result<Value, String> {
    let packet = Input::load(&path(values, "--packet")?, "integrated packet")?;
    validate_packet(&packet.value)?;
    let candidate_author =
        validate_attachments(&packet.value, &path(values, "--qualification-root")?)?;
    let semantic = Input::load(&path(values, "--semantic-decision")?, "semantic decision")?;
    let oracle = Input::load(&path(values, "--oracle-decision")?, "oracle decision")?;
    validate_decision(&packet, &semantic.value, "semantic", &candidate_author)?;
    validate_decision(&packet, &oracle.value, "oracle", &candidate_author)?;
    let semantic_reviewer = string(&semantic.value, "reviewer", "semantic decision")?;
    let oracle_reviewer = string(&oracle.value, "reviewer", "oracle decision")?;
    if semantic_reviewer.eq_ignore_ascii_case(oracle_reviewer) {
        return Err("semantic and Oracle reviewers must be distinct".into());
    }
    let semantic_verdict = string(&semantic.value, "verdict", "semantic decision")?;
    let oracle_verdict = string(&oracle.value, "verdict", "oracle decision")?;
    let (status, approved) = gate_status(semantic_verdict, oracle_verdict);
    Ok(json!({
        "schema": GATE_SCHEMA,
        "status": status,
        "packetSha256": packet.sha256(),
        "semanticDecisionSha256": semantic.sha256(),
        "oracleDecisionSha256": oracle.sha256(),
        "semanticCandidateId": packet.value["semanticCandidateId"],
        "runtimeCandidateId": packet.value["runtimeCandidateId"],
        "sourceLineage": packet.value["sourceLineage"],
        "candidateAuthor": candidate_author,
        "reviewers": [
            {"role": "semantic", "identity": semantic_reviewer, "verdict": semantic_verdict},
            {"role": "oracle", "identity": oracle_reviewer, "verdict": oracle_verdict}
        ],
        "distinctAuthenticatedReviewerCount": 2,
        "semanticReviewCompleted": true,
        "oracleReviewCompleted": true,
        "semanticAlignmentVerified": approved,
        "independentSourceReviewCompleted": approved,
        "independentOracleReviewCompleted": approved,
        "allowsExactPatchPublication": approved,
        "requiresUpstreamRevisionReexecution": approved,
        "allowsDistinctCasePerformanceCalibration": false,
        "allowsUnseenAgentCohortEvaluation": approved,
        "behaviorOracleVerified": false,
        "cordovaRuntimeCalibrated": false,
        "liveVendorIapExecuted": false,
        "realDeviceExecuted": false,
        "relativePerformanceDetectorCalibrated": true,
        "distinctBaselineReferenceWrongCaseCalibrationComplete": true,
        "performanceCalibrated": true,
        "absolutePowerThermalQualified": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": if approved { APPROVED_BOUNDARY } else { NON_APPROVED_BOUNDARY },
        "nextGate": if approved {
            "publish-exact-reviewed-patch-rebind-upstream-revision-and-run-unseen-agent-cohort-evaluation"
        } else {
            "candidate-evidence-or-review-decision-change"
        }
    }))
}

fn validate_gate(
    packet: &Input,
    semantic: &Input,
    oracle: &Input,
    gate: &Value,
    candidate_author: &Value,
) -> Result<(), String> {
    validate_decision(packet, &semantic.value, "semantic", candidate_author)?;
    validate_decision(packet, &oracle.value, "oracle", candidate_author)?;
    let semantic_reviewer = string(&semantic.value, "reviewer", "semantic decision")?;
    let oracle_reviewer = string(&oracle.value, "reviewer", "oracle decision")?;
    if semantic_reviewer.eq_ignore_ascii_case(oracle_reviewer) {
        return Err("semantic and Oracle reviewers must be distinct".into());
    }
    same(
        string(gate, "schema", "integrated gate")?,
        GATE_SCHEMA,
        "integrated gate schema",
    )?;
    same(
        string(gate, "packetSha256", "integrated gate")?,
        &packet.sha256(),
        "integrated gate packet digest",
    )?;
    same(
        string(gate, "semanticDecisionSha256", "integrated gate")?,
        &semantic.sha256(),
        "integrated gate semantic decision digest",
    )?;
    same(
        string(gate, "oracleDecisionSha256", "integrated gate")?,
        &oracle.sha256(),
        "integrated gate Oracle decision digest",
    )?;
    for key in ["semanticCandidateId", "runtimeCandidateId"] {
        same(
            string(gate, key, "integrated gate")?,
            string(&packet.value, key, "integrated packet")?,
            &format!("integrated gate {key}"),
        )?;
    }
    if gate["sourceLineage"] != packet.value["sourceLineage"] {
        return Err("integrated gate source lineage differs".into());
    }
    if gate["candidateAuthor"] != *candidate_author {
        return Err("integrated gate candidate author differs".into());
    }
    if gate["distinctAuthenticatedReviewerCount"].as_u64() != Some(2) {
        return Err("integrated gate distinct reviewer count differs".into());
    }
    let reviewers = gate["reviewers"]
        .as_array()
        .ok_or_else(|| "integrated gate reviewers must be an array".to_owned())?;
    let expected_reviewers = json!([
        {"role": "semantic", "identity": semantic_reviewer, "verdict": semantic.value["verdict"]},
        {"role": "oracle", "identity": oracle_reviewer, "verdict": oracle.value["verdict"]}
    ]);
    if reviewers.len() != 2 || gate["reviewers"] != expected_reviewers {
        return Err("integrated gate reviewer lineage differs".into());
    }
    let semantic_verdict = string(&semantic.value, "verdict", "semantic decision")?;
    let oracle_verdict = string(&oracle.value, "verdict", "oracle decision")?;
    let (expected_status, approved) = gate_status(semantic_verdict, oracle_verdict);
    same(
        string(gate, "status", "integrated gate")?,
        expected_status,
        "integrated gate status",
    )?;
    same(
        string(gate, "boundary", "integrated gate")?,
        if approved {
            APPROVED_BOUNDARY
        } else {
            NON_APPROVED_BOUNDARY
        },
        "integrated gate boundary",
    )?;
    same(
        string(gate, "nextGate", "integrated gate")?,
        if approved {
            "publish-exact-reviewed-patch-rebind-upstream-revision-and-run-unseen-agent-cohort-evaluation"
        } else {
            "candidate-evidence-or-review-decision-change"
        },
        "integrated gate next gate",
    )?;
    for key in ["semanticReviewCompleted", "oracleReviewCompleted"] {
        exact_bool(gate, key, true, "integrated gate")?;
    }
    for key in [
        "semanticAlignmentVerified",
        "independentSourceReviewCompleted",
        "independentOracleReviewCompleted",
        "allowsExactPatchPublication",
        "requiresUpstreamRevisionReexecution",
        "allowsUnseenAgentCohortEvaluation",
    ] {
        exact_bool(gate, key, approved, "integrated gate")?;
    }
    exact_bool(
        gate,
        "relativePerformanceDetectorCalibrated",
        true,
        "integrated gate",
    )?;
    exact_bool(
        gate,
        "allowsDistinctCasePerformanceCalibration",
        false,
        "integrated gate",
    )?;
    for key in [
        "distinctBaselineReferenceWrongCaseCalibrationComplete",
        "performanceCalibrated",
    ] {
        exact_bool(gate, key, true, "integrated gate")?;
    }
    for key in [
        "behaviorOracleVerified",
        "cordovaRuntimeCalibrated",
        "liveVendorIapExecuted",
        "realDeviceExecuted",
        "absolutePowerThermalQualified",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(gate, key, false, "integrated gate")?;
    }
    Ok(())
}

fn value<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn path(values: &BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(value(values, key)?))
}

fn write_output(path: PathBuf, value: &Value) -> Result<(), String> {
    if path.exists() {
        return Err("refusing to overwrite output".into());
    }
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    bytes.push(b'\n');
    fs::write(path, bytes).map_err(|error| format!("cannot write output: {error}"))
}

fn parse_values(args: impl Iterator<Item = String>) -> Result<BTreeMap<String, String>, String> {
    let mut values = BTreeMap::new();
    let mut args = args;
    while let Some(flag) = args.next() {
        let argument = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), argument).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    Ok(values)
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| "missing command".to_owned())?;
    let values = parse_values(args)?;
    match command.as_str() {
        "decide" => write_output(path(&values, "--output")?, &decide(&values)?),
        "compile" => write_output(path(&values, "--output")?, &compile(&values)?),
        "validate" => {
            let packet = Input::load(&path(&values, "--packet")?, "integrated packet")?;
            validate_packet(&packet.value)?;
            let candidate_author =
                validate_attachments(&packet.value, &path(&values, "--qualification-root")?)?;
            let semantic =
                Input::load(&path(&values, "--semantic-decision")?, "semantic decision")?;
            let oracle = Input::load(&path(&values, "--oracle-decision")?, "oracle decision")?;
            let gate = Input::load(&path(&values, "--gate")?, "integrated gate")?;
            validate_gate(&packet, &semantic, &oracle, &gate.value, &candidate_author)
        }
        _ => Err(format!("unsupported command: {command}")),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data integrated review invalid: {error}");
        std::process::exit(1);
    }
}
