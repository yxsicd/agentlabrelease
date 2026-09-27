use agentlab_code_analysis::digest;
use serde_json::{json, Value};
use std::{collections::BTreeSet, env, fs, path::PathBuf};

const PACKET_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_packet.v1";
const ANSWERS_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_answers.v1";
const DECISION_SCHEMA: &str = "agentlab.purchase_data_ohostest_review.v1";
const GATE_SCHEMA: &str = "agentlab.purchase_data_ohostest_review_gate.v1";

const QUESTION_IDS: &[&str] = &[
    "exact-lineage",
    "production-seam-preservation",
    "guard-and-field-correctness",
    "ohostest-discrimination",
    "failure-observability",
    "boundary-honesty",
];

const RISK_IDS: &[&str] = &[
    "self-authored-candidate",
    "signature-verification-outside-test-seam",
    "live-vendor-iap-service-unexecuted",
    "x86-emulator-not-real-device",
    "performance-power-thermal-uncalibrated",
    "semantic-and-behavior-oracle-review-pending",
];

const VERDICTS: &[&str] = &[
    "approve-for-upstream-publication",
    "reject-candidate",
    "defer-for-more-evidence",
];

const GATE_BOUNDARY: &str = "Approval authorizes publication of only the exact reviewed patch. It does not approve a case contract. The published upstream revision must be rebound and reexecuted before semantic, behavior-Oracle, performance and case-qualification gates continue.";

struct Input {
    bytes: Vec<u8>,
    value: Value,
}

impl Input {
    fn load(path: PathBuf, label: &str) -> Result<Self, String> {
        let metadata = fs::symlink_metadata(&path)
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

fn valid_sha(value: &str) -> bool {
    value.len() == 64
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

fn exact_strings(value: &Value, expected: &[&str], label: &str) -> Result<(), String> {
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

fn validate_packet(packet: &Value) -> Result<(), String> {
    same(
        string(packet, "schema", "review packet")?,
        PACKET_SCHEMA,
        "review packet schema",
    )?;
    same(
        string(packet, "status", "review packet")?,
        "independent-source-review-required",
        "review packet status",
    )?;
    same(
        string(packet, "nextGate", "review packet")?,
        "authenticated-independent-source-review-on-trusted-main",
        "review packet next gate",
    )?;
    same(
        string(&packet["candidateAuthor"], "email", "candidate author")?,
        "agentlab-evidence@localhost",
        "candidate author identity",
    )?;
    for key in [
        "publishedToUpstream",
        "independentReviewVerified",
        "behaviorOracleVerified",
        "performanceCalibrated",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(packet, key, false, "review packet")?;
    }
    if packet["execution"]["testCount"].as_u64() != Some(7)
        || packet["execution"]["passed"].as_u64() != Some(7)
        || packet["execution"]["failure"].as_u64() != Some(0)
        || packet["execution"]["error"].as_u64() != Some(0)
        || packet["execution"]["ignore"].as_u64() != Some(0)
    {
        return Err("review packet execution counts differ".into());
    }
    exact_bool(
        &packet["execution"],
        "worktreeCleanBeforeBuild",
        true,
        "review packet execution",
    )?;
    exact_bool(
        &packet["execution"],
        "worktreeCleanAfterExecution",
        true,
        "review packet execution",
    )?;
    let patch_sha = string(&packet["artifacts"]["patch"], "sha256", "candidate patch")?;
    if !valid_sha(patch_sha) || packet["artifacts"]["patch"]["byteLength"].as_u64() == Some(0) {
        return Err("candidate patch identity is invalid".into());
    }
    exact_strings(&packet["risks"], RISK_IDS, "review packet risks")?;
    exact_strings(
        &packet["reviewDecisionContract"]["answers"],
        &["yes", "no", "unknown"],
        "review answers",
    )?;
    exact_strings(
        &packet["reviewDecisionContract"]["verdicts"],
        VERDICTS,
        "review verdicts",
    )?;
    let questions = packet["reviewDecisionContract"]["questions"]
        .as_array()
        .ok_or_else(|| "review questions must be an array".to_owned())?;
    let question_ids: BTreeSet<&str> = questions
        .iter()
        .map(|row| {
            string(row, "id", "review question").and_then(|id| {
                let question = string(row, "question", "review question")?;
                if question.len() < 20 {
                    return Err("review question is too short".into());
                }
                Ok(id)
            })
        })
        .collect::<Result<_, _>>()?;
    let expected: BTreeSet<&str> = QUESTION_IDS.iter().copied().collect();
    if questions.len() != QUESTION_IDS.len() || question_ids != expected {
        return Err("review question inventory differs".into());
    }
    Ok(())
}

fn validate_patch_artifact(packet: &Value, repository_root: PathBuf) -> Result<(), String> {
    let relative = string(&packet["artifacts"]["patch"], "path", "candidate patch")?;
    if !relative.starts_with("release/qualifications/")
        || relative.starts_with('/')
        || relative.split('/').any(|component| component == "..")
    {
        return Err("candidate patch path is outside retained qualifications".into());
    }
    let path = repository_root.join(relative);
    let metadata = fs::symlink_metadata(&path)
        .map_err(|error| format!("cannot inspect retained candidate patch: {error}"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err("retained candidate patch must be a regular file".into());
    }
    let bytes =
        fs::read(path).map_err(|error| format!("cannot read retained candidate patch: {error}"))?;
    same(
        &digest(&bytes),
        string(&packet["artifacts"]["patch"], "sha256", "candidate patch")?,
        "retained candidate patch digest",
    )?;
    if packet["artifacts"]["patch"]["byteLength"].as_u64() != Some(bytes.len() as u64) {
        return Err("retained candidate patch byte length differs".into());
    }
    Ok(())
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
            return Err("review response id is invalid".into());
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
    let ids: Vec<&str> = normalized
        .iter()
        .filter_map(|row| row["id"].as_str())
        .collect();
    let mut expected = QUESTION_IDS.to_vec();
    expected.sort_unstable();
    if ids != expected {
        return Err("review answers must cover every question exactly".into());
    }
    Ok(normalized)
}

fn validate_verdict(verdict: &str, responses: &[Value]) -> Result<(), String> {
    if !VERDICTS.contains(&verdict) {
        return Err("source-review verdict is invalid".into());
    }
    let answers: BTreeSet<&str> = responses
        .iter()
        .filter_map(|row| row["answer"].as_str())
        .collect();
    match verdict {
        "approve-for-upstream-publication" if answers == BTreeSet::from(["yes"]) => Ok(()),
        "reject-candidate" if answers.contains("no") => Ok(()),
        "defer-for-more-evidence" if answers.contains("unknown") && !answers.contains("no") => {
            Ok(())
        }
        "approve-for-upstream-publication" => {
            Err("approval requires every source-review answer to be yes".into())
        }
        "reject-candidate" => Err("rejection requires at least one no answer".into()),
        _ => Err("deferral requires unknown answers and no rejection".into()),
    }
}

fn decide(values: &std::collections::BTreeMap<String, String>) -> Result<Value, String> {
    let packet = Input::load(path(values, "--packet")?, "review packet")?;
    validate_packet(&packet.value)?;
    validate_patch_artifact(&packet.value, path(values, "--repository-root")?)?;
    let expected_sha = value(values, "--expected-packet-sha256")?;
    if !valid_sha(expected_sha) || packet.sha256() != expected_sha {
        return Err("expected review packet digest differs".into());
    }
    let answers = Input::load(path(values, "--answers")?, "review answers")?;
    let responses = normalize_answers(&answers.value)?;
    let reviewer = value(values, "--reviewer")?.trim();
    if !valid_reviewer(reviewer) {
        return Err("source reviewer identity is invalid".into());
    }
    let acknowledged: BTreeSet<&str> = value(values, "--acknowledged-risk-ids")?
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .collect();
    let expected_risks: BTreeSet<&str> = RISK_IDS.iter().copied().collect();
    if acknowledged != expected_risks {
        return Err("source reviewer must acknowledge every risk exactly".into());
    }
    let verdict = value(values, "--verdict")?;
    validate_verdict(verdict, &responses)?;
    let rationale = value(values, "--rationale")?.trim();
    if !(20..=2000).contains(&rationale.len()) {
        return Err("source-review decision rationale is invalid".into());
    }
    Ok(json!({
        "schema": DECISION_SCHEMA,
        "packetSha256": packet.sha256(),
        "candidateId": packet.value["candidateId"],
        "sourceRepository": packet.value["sourceRepository"],
        "baseRevision": packet.value["baseRevision"],
        "candidateRevision": packet.value["candidateRevision"],
        "patchSha256": packet.value["artifacts"]["patch"]["sha256"],
        "candidateAuthor": packet.value["candidateAuthor"],
        "reviewer": reviewer,
        "responses": responses,
        "acknowledgedRiskIds": acknowledged.into_iter().collect::<Vec<_>>(),
        "verdict": verdict,
        "rationale": rationale,
        "allowsUpstreamPublication": verdict == "approve-for-upstream-publication",
        "allowsCaseContract": false,
        "automaticPromotion": false
    }))
}

fn validate_decision(packet: &Input, decision: &Value) -> Result<(), String> {
    validate_packet(&packet.value)?;
    same(
        string(decision, "schema", "source-review decision")?,
        DECISION_SCHEMA,
        "source-review decision schema",
    )?;
    same(
        string(decision, "packetSha256", "source-review decision")?,
        &packet.sha256(),
        "source-review packet digest",
    )?;
    for key in [
        "candidateId",
        "sourceRepository",
        "baseRevision",
        "candidateRevision",
    ] {
        same(
            string(decision, key, "source-review decision")?,
            string(&packet.value, key, "review packet")?,
            &format!("source-review {key}"),
        )?;
    }
    same(
        string(decision, "patchSha256", "source-review decision")?,
        string(
            &packet.value["artifacts"]["patch"],
            "sha256",
            "candidate patch",
        )?,
        "source-review patch digest",
    )?;
    if decision["candidateAuthor"] != packet.value["candidateAuthor"] {
        return Err("source-review candidate author differs".into());
    }
    let reviewer = string(decision, "reviewer", "source-review decision")?;
    if !valid_reviewer(reviewer) {
        return Err("source reviewer is not an authenticated GitHub actor".into());
    }
    let rationale = string(decision, "rationale", "source-review decision")?.trim();
    if !(20..=2000).contains(&rationale.len()) {
        return Err("source-review decision rationale is invalid".into());
    }
    let responses = normalize_answers(&json!({
        "schema": ANSWERS_SCHEMA,
        "responses": decision["responses"]
    }))?;
    if Value::Array(responses.clone()) != decision["responses"] {
        return Err("source-review responses are not normalized".into());
    }
    let verdict = string(decision, "verdict", "source-review decision")?;
    validate_verdict(verdict, &responses)?;
    exact_strings(
        &decision["acknowledgedRiskIds"],
        RISK_IDS,
        "acknowledged source-review risks",
    )?;
    exact_bool(
        decision,
        "allowsUpstreamPublication",
        verdict == "approve-for-upstream-publication",
        "source-review decision",
    )?;
    exact_bool(
        decision,
        "allowsCaseContract",
        false,
        "source-review decision",
    )?;
    exact_bool(
        decision,
        "automaticPromotion",
        false,
        "source-review decision",
    )?;
    Ok(())
}

fn compile(values: &std::collections::BTreeMap<String, String>) -> Result<Value, String> {
    let packet = Input::load(path(values, "--packet")?, "review packet")?;
    let decision = Input::load(path(values, "--decision")?, "source-review decision")?;
    validate_patch_artifact(&packet.value, path(values, "--repository-root")?)?;
    validate_decision(&packet, &decision.value)?;
    let verdict = string(&decision.value, "verdict", "source-review decision")?;
    let approved = verdict == "approve-for-upstream-publication";
    let status = match verdict {
        "approve-for-upstream-publication" => {
            "independent-source-review-approved-upstream-publication-only"
        }
        "reject-candidate" => "independent-source-review-rejected",
        _ => "independent-source-review-deferred",
    };
    Ok(json!({
        "schema": GATE_SCHEMA,
        "status": status,
        "packetSha256": packet.sha256(),
        "decisionSha256": decision.sha256(),
        "candidateId": packet.value["candidateId"],
        "sourceRepository": packet.value["sourceRepository"],
        "baseRevision": packet.value["baseRevision"],
        "candidateRevision": packet.value["candidateRevision"],
        "patchSha256": packet.value["artifacts"]["patch"]["sha256"],
        "reviewer": decision.value["reviewer"],
        "verdict": verdict,
        "reviewCompleted": true,
        "independentReviewApproved": approved,
        "allowsUpstreamPublication": approved,
        "requiresExactUpstreamRevisionReexecution": approved,
        "behaviorOracleVerified": false,
        "performanceCalibrated": false,
        "allowsCaseContract": false,
        "automaticPromotion": false,
        "boundary": GATE_BOUNDARY,
        "nextGate": if approved {
            "publish-exact-patch-and-reexecute-exact-upstream-revision"
        } else {
            "candidate-revision-or-review-evidence-change"
        }
    }))
}

fn validate_gate(packet: &Input, decision: &Input, gate: &Input) -> Result<(), String> {
    validate_decision(packet, &decision.value)?;
    same(
        string(&gate.value, "schema", "source-review gate")?,
        GATE_SCHEMA,
        "source-review gate schema",
    )?;
    same(
        string(&gate.value, "packetSha256", "source-review gate")?,
        &packet.sha256(),
        "source-review gate packet digest",
    )?;
    same(
        string(&gate.value, "decisionSha256", "source-review gate")?,
        &decision.sha256(),
        "source-review gate decision digest",
    )?;
    for key in [
        "candidateId",
        "sourceRepository",
        "baseRevision",
        "candidateRevision",
    ] {
        same(
            string(&gate.value, key, "source-review gate")?,
            string(&packet.value, key, "source-review packet")?,
            &format!("source-review gate {key}"),
        )?;
    }
    same(
        string(&gate.value, "patchSha256", "source-review gate")?,
        string(
            &packet.value["artifacts"]["patch"],
            "sha256",
            "candidate patch",
        )?,
        "source-review gate patch digest",
    )?;
    for key in ["reviewer", "verdict"] {
        same(
            string(&gate.value, key, "source-review gate")?,
            string(&decision.value, key, "source-review decision")?,
            &format!("source-review gate {key}"),
        )?;
    }
    let approved = decision.value["verdict"] == "approve-for-upstream-publication";
    let expected_status = if approved {
        "independent-source-review-approved-upstream-publication-only"
    } else if decision.value["verdict"] == "reject-candidate" {
        "independent-source-review-rejected"
    } else {
        "independent-source-review-deferred"
    };
    same(
        string(&gate.value, "status", "source-review gate")?,
        expected_status,
        "source-review gate status",
    )?;
    let expected_next_gate = if approved {
        "publish-exact-patch-and-reexecute-exact-upstream-revision"
    } else {
        "candidate-revision-or-review-evidence-change"
    };
    same(
        string(&gate.value, "nextGate", "source-review gate")?,
        expected_next_gate,
        "source-review gate next gate",
    )?;
    same(
        string(&gate.value, "boundary", "source-review gate")?,
        GATE_BOUNDARY,
        "source-review gate boundary",
    )?;
    for key in ["independentReviewApproved", "allowsUpstreamPublication"] {
        exact_bool(&gate.value, key, approved, "source-review gate")?;
    }
    exact_bool(&gate.value, "reviewCompleted", true, "source-review gate")?;
    exact_bool(
        &gate.value,
        "requiresExactUpstreamRevisionReexecution",
        approved,
        "source-review gate",
    )?;
    for key in [
        "behaviorOracleVerified",
        "performanceCalibrated",
        "allowsCaseContract",
        "automaticPromotion",
    ] {
        exact_bool(&gate.value, key, false, "source-review gate")?;
    }
    Ok(())
}

fn value<'a>(
    values: &'a std::collections::BTreeMap<String, String>,
    key: &str,
) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}

fn path(values: &std::collections::BTreeMap<String, String>, key: &str) -> Result<PathBuf, String> {
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

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| "missing command".to_owned())?;
    let mut values = std::collections::BTreeMap::new();
    while let Some(flag) = args.next() {
        let argument = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        values.insert(flag, argument);
    }
    match command.as_str() {
        "decide" => {
            let output = path(&values, "--output")?;
            write_output(output, &decide(&values)?)
        }
        "compile" => {
            let output = path(&values, "--output")?;
            write_output(output, &compile(&values)?)
        }
        "validate" => {
            let packet = Input::load(path(&values, "--packet")?, "review packet")?;
            let decision = Input::load(path(&values, "--decision")?, "source-review decision")?;
            let gate = Input::load(path(&values, "--gate")?, "source-review gate")?;
            validate_patch_artifact(&packet.value, path(&values, "--repository-root")?)?;
            validate_gate(&packet, &decision, &gate)
        }
        _ => Err(format!("unsupported command: {command}")),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("purchase-data OHOS Test source review invalid: {error}");
        std::process::exit(1);
    }
}
