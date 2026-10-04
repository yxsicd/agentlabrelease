use agentlab_code_analysis::{
    digest,
    maintainer_guidance::{
        bind, bind_source_recipe, consumption, source_recipe_completion, source_recipe_consumption,
        source_recipe_target, stage_proposal,
    },
};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

struct Fixture {
    root: PathBuf,
    selection: Value,
}
static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn source_request(f: &Fixture, repo: &str) -> (Value, Value) {
    let mut selection = f.selection.clone();
    selection["sourceRecipeTarget"] = json!({"scopeSkillId":"scope-source","sourcePaths":["src/Thing.ets"],
        "demand":"Calibrate one source-grounded mechanism with valid and wrong controls."});
    let content = "export class Thing { value=0; }";
    let request = json!({"schema":"agentlab.source_recipe_author_request.v1","automaticPromotion":false,"reviewed":false,
        "knowledgeCutSha256":selection["knowledgeCutSha256"],"authorityRevision":selection["knowledgeRevision"],
        "source":{"repositoryId":repo,"revision":"a".repeat(40)},
        "scope":{"id":"scope-source","repositoryId":repo,"sourceRevision":"a".repeat(40)},
        "sourceFiles":[{"path":"src/Thing.ets","content":content,"sha256":digest(content.as_bytes())}]});
    (request, selection)
}

#[test]
fn source_guidance_is_cut_and_target_bound_for_two_unrelated_repositories() {
    for repo in ["portable-source-one", "independent-source-two"] {
        let f = Fixture::new(repo);
        let (request, selection) = source_request(&f, repo);
        let checked = |r: &Value, s: &Value| {
            bind_source_recipe(
                &f.root,
                &serde_json::to_vec(r).unwrap(),
                &serde_json::to_vec(s).unwrap(),
            )
        };
        let packet = checked(&request, &selection).unwrap();
        assert_eq!(
            packet["sourceRecipeBinding"]["target"],
            selection["sourceRecipeTarget"]
        );
        assert_eq!(packet["agentConsumptionVerified"], false);
        let proposal = json!({"scopeSkillId":"scope-source","sourcePaths":["src/Thing.ets"]});
        assert!(source_recipe_target(&packet, &serde_json::to_vec(&proposal).unwrap()).is_ok());
        let omitted = json!({"scopeSkillId":"scope-source","sourcePaths":["src/Other.ets"]});
        assert!(source_recipe_target(&packet, &serde_json::to_vec(&omitted).unwrap()).is_err());
        let mut moved = proposal.clone();
        moved["scopeSkillId"] = json!("other-scope");
        assert!(source_recipe_target(&packet, &serde_json::to_vec(&moved).unwrap()).is_err());
        for (pointer, value) in [
            ("/authorityRevision", json!("0".repeat(40))),
            ("/knowledgeCutSha256", json!("0".repeat(64))),
            ("/source/repositoryId", json!("borrowed-repository")),
            ("/scope/id", json!("other-scope")),
            ("/sourceFiles/0/content", Value::Null),
            ("/sourceFiles/0/sha256", json!("0".repeat(64))),
        ] {
            let mut changed = request.clone();
            *changed.pointer_mut(pointer).unwrap() = value;
            assert!(checked(&changed, &selection).is_err());
        }
        for paths in [
            json!([]),
            json!(["../Thing.ets"]),
            json!(["src/Unknown.ets"]),
            json!(["src/Thing.ets", "src/Thing.ets"]),
        ] {
            let mut changed = selection.clone();
            changed["sourceRecipeTarget"]["sourcePaths"] = paths;
            assert!(checked(&request, &changed).is_err());
        }
        let mut changed = selection.clone();
        changed["sourceRecipeTarget"]["demand"] = json!("");
        assert!(checked(&request, &changed).is_err());
    }
}

#[test]
fn source_guidance_consumption_rebinds_inputs_and_preserves_original_capture_layout() {
    let f = Fixture::new("source-wire-fixture");
    let (request, selection) = source_request(&f, "source-wire-fixture");
    let request_bytes = serde_json::to_vec(&request).unwrap();
    let selection_bytes = serde_json::to_vec(&selection).unwrap();
    let packet = bind_source_recipe(&f.root, &request_bytes, &selection_bytes).unwrap();
    let packet_bytes = serde_json::to_vec(&packet).unwrap();
    let evidence = f.root.join("source-evidence");
    fs::create_dir(&evidence).unwrap();
    let retained = evidence.join("source-guidance-knowledge");
    fs::create_dir(&retained).unwrap();
    for name in [
        "maintainer-knowledge-cut.json",
        "maintainer_skills.jsonl",
        "program_facts.jsonl",
        "maintainer_scope_skills.jsonl",
        "maintainer_skill_refresh_rounds.jsonl",
        "evaluation_cases.jsonl",
    ] {
        fs::copy(f.root.join(name), retained.join(name)).unwrap();
    }
    fs::write(
        evidence.join("source-guidance-author-request.json"),
        &request_bytes,
    )
    .unwrap();
    fs::write(
        evidence.join("source-guidance-selection.json"),
        &selection_bytes,
    )
    .unwrap();
    let prompt = format!("Source constructor instructions\n{packet}\n");
    fs::write(evidence.join("source-recipe-author-prompt.txt"), &prompt).unwrap();
    let row = &packet["guidance"][0];
    let intent = json!({"schema":"agentlab.maintainer_guidance_prompt_intent.v1","guidanceMode":"guided",
        "authorRequestSha256":digest(&request_bytes),"promptSha256":digest(prompt.as_bytes()),
        "knowledgeAuthority":packet["knowledgeAuthority"],"participantBudgetSeconds":240,"transportRetryLimit":0,
        "participantIdentity":{"model":"fixture-model","providerRoute":"fixture-route"},
        "selectedSkills":[{"id":row["skill"]["id"],"rowSha256":row["rowSha256"],"bodySha256":row["bodySha256"]}]});
    fs::write(
        evidence.join("source-recipe-author-guidance-consumption-intent.json"),
        serde_json::to_vec(&intent).unwrap(),
    )
    .unwrap();
    let final_bytes = serde_json::to_vec(&json!({"role":"assistant","stopReason":"stop"})).unwrap();
    fs::write(
        evidence.join("source-recipe-author-final-assistant-message.json"),
        &final_bytes,
    )
    .unwrap();
    let lifecycle = json!({"label":"source-recipe-author","captureAuthority":"operator","exitCode":0,"timedOut":false,
        "finalAssistantMessagePresent":true,"finalAssistantMessageSha256":digest(&final_bytes),
        "participantBudgetSeconds":240,"participantBudgetScope":"native-process-watchdog","transportRetryLimit":0});
    fs::write(
        evidence.join("source-recipe-author-lifecycle.json"),
        serde_json::to_vec(&lifecycle).unwrap(),
    )
    .unwrap();
    let gateway = evidence.join("gateway");
    fs::create_dir(&gateway).unwrap();
    let wire = json!({"model":"fixture-model","providerId":"fixture-route","stream":true,
        "messages":[{"role":"user","content":prompt}]});
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&wire).unwrap(),
    )
    .unwrap();
    let response = b"data: {\"choices\":[{\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n";
    fs::write(gateway.join("0001.response"), response).unwrap();
    let status = json!({"exchangeId":"0001","status":200,"durationMs":1,"upstreamEof":true,"semanticComplete":true,
        "outcome":"completed","streamError":null,"responseBytes":response.len()});
    fs::write(
        gateway.join("0001.status.json"),
        serde_json::to_vec(&status).unwrap(),
    )
    .unwrap();
    let receipt = source_recipe_consumption(&evidence, &packet_bytes).unwrap();
    assert_eq!(receipt["agentConsumptionVerified"], true);
    assert_eq!(receipt["learningBenefitVerified"], false);
    assert!(!evidence.join("author-calibration-lifecycle.json").exists());
    let mut budget_drift = lifecycle.clone();
    budget_drift["participantBudgetSeconds"] = json!(420);
    fs::write(
        evidence.join("source-recipe-author-lifecycle.json"),
        serde_json::to_vec(&budget_drift).unwrap(),
    )
    .unwrap();
    assert!(source_recipe_completion(&evidence, &packet_bytes)
        .unwrap_err()
        .contains("budget differs"));
    fs::write(
        evidence.join("source-recipe-author-lifecycle.json"),
        serde_json::to_vec(&lifecycle).unwrap(),
    )
    .unwrap();
    let incomplete_final =
        serde_json::to_vec(&json!({"role":"assistant","stopReason":"length"})).unwrap();
    let mut rehashed_lifecycle = lifecycle.clone();
    rehashed_lifecycle["finalAssistantMessageSha256"] = json!(digest(&incomplete_final));
    fs::write(
        evidence.join("source-recipe-author-final-assistant-message.json"),
        &incomplete_final,
    )
    .unwrap();
    fs::write(
        evidence.join("source-recipe-author-lifecycle.json"),
        serde_json::to_vec(&rehashed_lifecycle).unwrap(),
    )
    .unwrap();
    assert!(source_recipe_completion(&evidence, &packet_bytes)
        .unwrap_err()
        .contains("normally"));
    fs::write(
        evidence.join("source-recipe-author-final-assistant-message.json"),
        &final_bytes,
    )
    .unwrap();
    fs::write(
        evidence.join("source-recipe-author-lifecycle.json"),
        serde_json::to_vec(&lifecycle).unwrap(),
    )
    .unwrap();
    let revision_label = "source-recipe-author-format-revision-1";
    fs::write(
        evidence.join(format!("{revision_label}-guidance-consumption-intent.json")),
        serde_json::to_vec(&intent).unwrap(),
    )
    .unwrap();
    assert!(
        source_recipe_completion(&evidence, &packet_bytes).is_err(),
        "partial revision cannot borrow the completed first turn"
    );
    fs::write(
        evidence.join(format!("{revision_label}-prompt.txt")),
        &prompt,
    )
    .unwrap();
    fs::write(
        evidence.join(format!("{revision_label}-final-assistant-message.json")),
        &final_bytes,
    )
    .unwrap();
    let mut revision_lifecycle = lifecycle.clone();
    revision_lifecycle["label"] = json!(revision_label);
    fs::write(
        evidence.join(format!("{revision_label}-lifecycle.json")),
        serde_json::to_vec(&revision_lifecycle).unwrap(),
    )
    .unwrap();
    assert_eq!(
        source_recipe_completion(&evidence, &packet_bytes).unwrap()["completedTurnLabel"],
        revision_label
    );
    for suffix in [
        "guidance-consumption-intent.json",
        "prompt.txt",
        "final-assistant-message.json",
        "lifecycle.json",
    ] {
        fs::remove_file(evidence.join(format!("{revision_label}-{suffix}"))).unwrap();
    }
    let unguided_prompt = format!(
        "Same source instructions\n{}",
        packet["sourceRecipeBinding"]["target"]
    );
    let mut unguided_intent = intent.clone();
    unguided_intent["guidanceMode"] = json!("unguided");
    unguided_intent["promptSha256"] = json!(digest(unguided_prompt.as_bytes()));
    unguided_intent["selectedSkills"] = json!([]);
    fs::write(
        evidence.join("source-recipe-author-prompt.txt"),
        &unguided_prompt,
    )
    .unwrap();
    fs::write(
        evidence.join("source-recipe-author-guidance-consumption-intent.json"),
        serde_json::to_vec(&unguided_intent).unwrap(),
    )
    .unwrap();
    let mut unguided_wire = wire.clone();
    unguided_wire["messages"][0]["content"] = json!(unguided_prompt);
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&unguided_wire).unwrap(),
    )
    .unwrap();
    let baseline = source_recipe_completion(&evidence, &packet_bytes).unwrap();
    assert_eq!(baseline["authorCompletionVerified"], true);
    assert_eq!(baseline["agentConsumptionVerified"], false);
    assert!(source_recipe_consumption(&evidence, &packet_bytes).is_err());
    unguided_wire["messages"]
        .as_array_mut()
        .unwrap()
        .push(json!({"role":"user","content":packet.to_string()}));
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&unguided_wire).unwrap(),
    )
    .unwrap();
    assert!(source_recipe_completion(&evidence, &packet_bytes).is_err());
    fs::write(evidence.join("source-recipe-author-prompt.txt"), &prompt).unwrap();
    fs::write(
        evidence.join("source-recipe-author-guidance-consumption-intent.json"),
        serde_json::to_vec(&intent).unwrap(),
    )
    .unwrap();
    let mut changed = wire.clone();
    changed["messages"][0]["content"] = json!("only a Skill hash");
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&changed).unwrap(),
    )
    .unwrap();
    assert!(source_recipe_consumption(&evidence, &packet_bytes).is_err());
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&wire).unwrap(),
    )
    .unwrap();
    fs::write(gateway.join("0001.response"), b"data: {}\n\n").unwrap();
    assert!(source_recipe_consumption(&evidence, &packet_bytes).is_err());
    fs::write(gateway.join("0001.response"), response).unwrap();
    let mut changed = request.clone();
    changed["scope"]["id"] = json!("borrowed-scope");
    fs::write(
        evidence.join("source-guidance-author-request.json"),
        serde_json::to_vec(&changed).unwrap(),
    )
    .unwrap();
    assert!(source_recipe_consumption(&evidence, &packet_bytes).is_err());
    // All exchanges in this test are fixtures, not real model consumption.
}

#[test]
fn source_constructor_cli_and_real_prompt_helper_keep_equal_task_and_private_free_treatments() {
    let f = Fixture::new("source-prompt-producer");
    let (request, selection) = source_request(&f, "source-prompt-producer");
    fs::write(
        f.root.join("request.json"),
        serde_json::to_vec(&request).unwrap(),
    )
    .unwrap();
    fs::write(
        f.root.join("selection.json"),
        serde_json::to_vec(&selection).unwrap(),
    )
    .unwrap();
    let output = f.root.join("source-packet.json");
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .arg("--bind-source-recipe-guidance")
            .arg("--knowledge")
            .arg(&f.root)
            .arg("--author-request")
            .arg(f.root.join("request.json"))
            .arg("--guidance-request")
            .arg(f.root.join("selection.json"))
            .arg("--output")
            .arg(&output)
            .output()
            .unwrap()
    };
    assert!(run().status.success());
    let original = fs::read(&output).unwrap();
    assert!(!run().status.success());
    assert_eq!(fs::read(&output).unwrap(), original);
    let code = r#"
import importlib.util,json,os,sys,hashlib
from pathlib import Path
spec=importlib.util.spec_from_file_location('source_author',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=Path(sys.argv[2]);packet=json.loads((root/'source-packet.json').read_bytes())
adapter_path=Path(sys.argv[1]).resolve().parents[1]/'examples/real-code-agent/participant.py'
adapter_spec=importlib.util.spec_from_file_location('native_participant',adapter_path)
adapter=importlib.util.module_from_spec(adapter_spec);adapter_spec.loader.exec_module(adapter)
budget=adapter.Participant.process_budget_seconds(300)
assert budget==420 and adapter.Participant.process_budget_seconds(240)==420
assert adapter.Participant.process_budget_seconds()==420 and adapter.Participant.process_budget_seconds(600)==660
guided=root/'guided';unguided=root/'unguided';guided.mkdir();unguided.mkdir()
g=m.guidance_prompt('fixed complete source context',packet,'guided',guided,'source-recipe-author',None,budget)
u=m.guidance_prompt('fixed complete source context',packet,'unguided',unguided,'source-recipe-author',None,budget)
target=packet['sourceRecipeBinding']['target'];body=packet['guidance'][0]['skill']['body']
assert json.dumps(target,ensure_ascii=False) in g and json.dumps(target,ensure_ascii=False) in u
assert body in g and body not in u
assert json.loads(g.splitlines()[-1])==packet
for directory,prompt,mode in [(guided,g,'guided'),(unguided,u,'unguided')]:
 intent=json.loads((directory/'source-recipe-author-guidance-consumption-intent.json').read_bytes())
 assert intent['promptSha256']==hashlib.sha256(prompt.encode()).hexdigest()
 assert intent['guidanceMode']==mode and intent['participantBudgetSeconds']==budget and intent['transportRetryLimit']==0
 assert intent['agentConsumptionVerified'] is False and intent['learningBenefitVerified'] is False
 assert bool(intent['selectedSkills'])==(mode=='guided')
 assert intent['authorRequestSha256']==packet['sourceRecipeBinding']['authorRequestSha256']
native=root/'native';native.mkdir()
p=adapter.Participant.__new__(adapter.Participant);p.evidence=native;p.implementation='pi'
lifecycle={'timedOut':False}
event={'type':'message_end','message':{'role':'assistant','stopReason':'stop','content':[{'type':'text','text':'fixture only'}]}}
result=p._run_turn([sys.executable,'-c','print('+repr(json.dumps(event))+')'],native,{},'budget-fixture',lifecycle,
 timeout_seconds=budget,require_completed_tool_call=False)
assert result['content']=='fixture only' and lifecycle['exitCode']==0
assert lifecycle['participantBudgetSeconds']==budget and lifecycle['participantBudgetScope']=='native-process-watchdog'
class CapturingParticipant:
 process_budget_seconds=staticmethod(adapter.Participant.process_budget_seconds)
 gateway_timeout_seconds=240
 def __init__(self,evidence):self.evidence=evidence;self.labels=[]
 def turn(self,label,workspace,**options):
  self.labels.append(label)
  intent=json.loads((self.evidence/(label+'-guidance-consumption-intent.json')).read_bytes())
  assert options['wall_time_limit_seconds']==300 and options['transport_retry_limit']==0
  assert intent['participantBudgetSeconds']==self.process_budget_seconds(options['wall_time_limit_seconds'])==420
  gateway=self.evidence/'gateway';gateway.mkdir(exist_ok=True)
  (gateway/f'{len(self.labels):04d}.status.json').write_text(json.dumps(dict(status=200,
   outcome='completed',semanticComplete=True,upstreamEof=True,streamError=None,clientDisconnected=False)))
  return {'content':'```json\n{}\n```' if len(self.labels)==1 else '{}','message':{'stopReason':'stop'}}
for mode in ['guided','unguided']:
 output=root/('constructor-'+mode);output.mkdir();workspace=output/'workspace';workspace.mkdir();evidence=output/'evidence';evidence.mkdir()
 retry=m.freeze_pi_retry_policy(output/'participant-state',workspace,evidence)
 p=CapturingParticipant(evidence)
 assert m.construct_proposal(p,workspace,evidence,output,'fixed source',None,1,retry,guidance=packet,guidance_mode=mode)=={}
 assert p.labels==['source-recipe-author','source-recipe-author-format-revision-1']
 assert (output/'proposal-attempt-0.txt').read_text()=='```json\n{}\n```'
assert m.guidance_prompt('ordinary unmodified path',None,'guided',guided,'unused',None,240)=='ordinary unmodified path'
try:m.guidance_prompt('must-not-overwrite',packet,'guided',guided,'source-recipe-author',None,240)
except FileExistsError:pass
else:raise AssertionError('existing intent overwritten')
"#;
    let result = Command::new("python3")
        .arg("-c")
        .arg(code)
        .arg(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../scripts/run-source-recipe-author.py"),
        )
        .arg(&f.root)
        .env("AGENTLAB_MODEL", "fixture-model")
        .env("AGENTLAB_PROVIDER_ROUTE", "fixture-route")
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn published_rating_guidance_rebinds_committed_rows_without_claiming_consumption() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let knowledge = repo.join("examples/maintainer-knowledge-gate/first-four");
    let guidance = repo.join("examples/maintainer-knowledge-gate/reviewed-guidance");
    let selection = fs::read(guidance.join("rating-convert-selection-b5a07f1b.json")).unwrap();
    let published: Value =
        serde_json::from_slice(&fs::read(guidance.join("rating-convert-b5a07f1b.json")).unwrap())
            .unwrap();
    let packet = bind(&knowledge, &selection).unwrap();
    assert_eq!(packet, published);
    assert_eq!(packet["guidance"].as_array().unwrap().len(), 1);
    assert_eq!(packet["agentConsumptionVerified"], false);
    assert_eq!(packet["learningBenefitVerified"], false);
    assert_eq!(packet["authorityWritePerformed"], false);
    assert_eq!(packet["guidance"][0]["skill"]["stage"], "calibration");
    assert!(!packet["guidance"][0]["skill"]["body"]
        .as_str()
        .unwrap()
        .is_empty());
    for change in ["cut", "stage", "source", "row"] {
        let mut changed: Value = serde_json::from_slice(&selection).unwrap();
        match change {
            "cut" => changed["knowledgeRevision"] = json!("0".repeat(40)),
            "stage" => changed["stage"] = json!("repository-analysis"),
            "source" => changed["sources"][0]["sourceRevision"] = json!("0".repeat(40)),
            "row" => changed["skills"][0]["rowSha256"] = json!("0".repeat(64)),
            _ => unreachable!(),
        }
        assert!(bind(&knowledge, &serde_json::to_vec(&changed).unwrap()).is_err());
    }
}

#[test]
fn published_successor_cut_binds_new_lesson_without_rewriting_historical_guidance() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let knowledge = repo
        .join("examples/maintainer-knowledge-gate/cuts/4bba501a1dffbdbeef05b759584fef70b090f292");
    let selection = fs::read(repo.join("examples/maintainer-knowledge-gate/reviewed-guidance/rating-convert-source-recipe-selection-4bba501a.json")).unwrap();
    let packet = bind(&knowledge, &selection).unwrap();
    assert_eq!(packet["guidance"].as_array().unwrap().len(), 1);
    assert_eq!(
        packet["guidance"][0]["skill"]["id"],
        "skill-rating-convert-string-corpus-37156735569"
    );
    assert_eq!(packet["agentConsumptionVerified"], false);
    assert_eq!(packet["learningBenefitVerified"], false);
    assert!(bind(
        &repo.join("examples/maintainer-knowledge-gate/first-four"),
        &selection
    )
    .is_err());
}

#[test]
fn published_automatic_review_lesson_binds_new_cut_and_preserves_frozen_method() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let knowledge = repo
        .join("examples/maintainer-knowledge-gate/cuts/f41c1bdfa145bacbe28f445e35707c0b2b1772ec");
    let selection = fs::read(repo.join("examples/maintainer-knowledge-gate/reviewed-guidance/rating-convert-source-review-selection-f41c1bdf.json")).unwrap();
    let packet = bind(&knowledge, &selection).unwrap();
    assert_eq!(packet["guidance"].as_array().unwrap().len(), 1);
    let skill = &packet["guidance"][0]["skill"];
    assert_eq!(
        skill["id"],
        "skill-source-suite-fa345f866f5bd480ceacac93157aefa424bbadf7a755160c998fdd3246c26059"
    );
    assert_eq!(skill["stage"], "calibration");
    assert_eq!(
        skill["methodRevision"],
        "37cfa0ce1ec6fcfa8c775b33255e8ba7010c9b3d"
    );
    assert_eq!(
        skill["methodDigest"],
        "5c98fb3bbc7a3cbbdf793dfb3835af88185867421cc2974caa642a5b35824982"
    );
    assert_eq!(
        skill["lessonSource"]["revision"],
        "edbcd54848c6e1e9868d25ac7a347d17c0899168"
    );
    for flag in [
        "agentConsumptionVerified",
        "learningBenefitVerified",
        "authorityWritePerformed",
    ] {
        assert_eq!(packet[flag], false);
    }
    let old = repo
        .join("examples/maintainer-knowledge-gate/cuts/4bba501a1dffbdbeef05b759584fef70b090f292");
    assert!(bind(&old, &selection).is_err());
    let mut changed: Value = serde_json::from_slice(&selection).unwrap();
    changed["skills"][0]["rowSha256"] = json!("0".repeat(64));
    assert!(bind(&knowledge, &serde_json::to_vec(&changed).unwrap()).is_err());
}

#[test]
fn reviewed_real_repair_seed_preserves_original_bytes_and_execution_limits() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples/maintainer-knowledge-gate/reviewed-guidance");
    let bytes = fs::read(root.join("abilitystage-agent-repaired-controls.json")).unwrap();
    let review: Value = serde_json::from_slice(
        &fs::read(root.join("abilitystage-agent-repaired-controls-review.json")).unwrap(),
    )
    .unwrap();
    let contract: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(digest(&bytes), review["reviewedContractSha256"]);
    let original = String::from_utf8(bytes)
        .unwrap()
        .replace("\"reviewed\": true", "\"reviewed\": false");
    assert_eq!(
        digest(original.as_bytes()),
        review["originalProposalSha256"]
    );
    assert_eq!(contract["reviewed"], true);
    assert_eq!(review["onlyReviewFlagChanged"], true);
    for key in ["candidateId", "candidateSha256", "sourceRevision"] {
        assert_eq!(contract[key], review[key]);
    }
    for key in [
        "semanticExecutionVerified",
        "learningBenefitVerified",
        "caseQualified",
        "harmonyRuntimeQualified",
        "automaticPromotion",
        "reviewerAuthenticated",
    ] {
        assert_eq!(review[key], false);
    }
    assert_eq!(review["executionApprovedWithinReviewScope"], true);
    // This checks published review provenance, not the claimed real run or behavior.
}

#[test]
fn bounded_author_repair_uses_real_gates_and_preserves_rejections() {
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    for mode in [
        "success",
        "exhausted",
        "source-drift",
        "wire-failure",
        "prior-drift",
        "zero",
        "identity-drift",
        "review-drift",
        "request-drift",
        "guidance-drift",
        "unguided-success",
        "unguided-exhausted",
        "unguided-wire-failure",
        "unguided-source-drift",
        "budget-drift",
        "unguided-budget-drift",
        "transport-budget-drift",
        "unguided-transport-budget-drift",
        "transport-retry-sidecar",
        "unguided-transport-retry-sidecar",
        "transport-retry-symlink",
        "unguided-transport-retry-symlink",
        "semantic-success",
        "unguided-semantic-success",
        "semantic-exhausted",
        "unguided-semantic-exhausted",
        "semantic-infrastructure",
        "semantic-zero",
        "unguided-semantic-zero",
        "extra-fields",
        "unguided-extra-fields",
    ] {
        let f = Fixture::new("portable-repair-source");
        let packet = f.bind(&f.selection).unwrap();
        fs::write(
            f.root.join("packet.json"),
            serde_json::to_vec(&packet).unwrap(),
        )
        .unwrap();
        let mut sources = Vec::new();
        let semantic = mode.contains("semantic-");
        let files = if semantic {
            vec![("module.json5", r#"{"module":{"srcEntry":"./Stage.ets"}}"#),
                ("Stage.ets", "const {AbilityStage}=require('@kit.AbilityKit');exports.default=class extends AbilityStage {onCreate(){console.info('created');const app=this.context.getApplicationContext();app.on('environment',{onConfigurationUpdated(c){console.info('config: '+JSON.stringify(c));}});console.info('registered');}onDestroy(){console.info('destroyed');}}"),
                ("Alternate.ets", "const {AbilityStage}=require('@kit.AbilityKit');exports.default=class extends AbilityStage {};")]
        } else {
            vec![
                ("module.json5", "entry=Stage"),
                ("Stage.ets", "on('environment')"),
            ]
        };
        for (path, raw) in files {
            fs::write(f.root.join(path), raw).unwrap();
            let oid = Command::new("git")
                .arg("hash-object")
                .arg(f.root.join(path))
                .output()
                .unwrap();
            assert!(oid.status.success());
            sources.push(
                json!({"repositoryId":"portable-repair-source","revision":"a".repeat(40),
                "path":path,"workspacePath":path,"sha256":digest(raw.as_bytes()),"bytes":raw.len(),
                "gitBlobOid":String::from_utf8(oid.stdout).unwrap().trim()}),
            );
        }
        let mut request = json!({"schema":"agentlab.stage_calibration_authoring_request.v1","automaticPromotion":false,
            "stageContext":{"candidateId":"portable-candidate","candidateSha256":"b".repeat(64),"sourceRevision":"a".repeat(40),"modulePath":"module.json5"},
            "sources":sources,"maintainerGuidance":packet});
        if mode.starts_with("unguided-") {
            request
                .as_object_mut()
                .unwrap()
                .remove("maintainerGuidance");
            request["guidanceMode"] = json!("unguided");
        }
        fs::write(
            f.root.join("authoring-request.json"),
            serde_json::to_vec(&request).unwrap(),
        )
        .unwrap();
        let result = Command::new("python3").current_dir(&f.root).args(["-c", r#"
import importlib.util,json,sys,hashlib,types
from pathlib import Path
spec=importlib.util.spec_from_file_location('author',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
mode=sys.argv[2].removeprefix('unguided-');raw=Path('authoring-request.json').read_bytes();request=json.loads(raw)
semantic=mode.startswith('semantic-');mode=mode.removeprefix('semantic-')
extra_fields=mode=='extra-fields';mode='success' if extra_fields else mode
proposal={**request['stageContext'],'schema':'agentlab.harmony_stage_control_contract.v1','reviewed':False,
 'createMarker':'created','destroyMarker':'destroyed','registrationMarker':'registered','configurationPrefix':'config: ','eventName':'environment',
 'configurations':[{'id':'initial','language':'en','colorMode':0},{'id':'language','language':'zh','colorMode':0},{'id':'color','language':'zh','colorMode':1}],
 'variants':[{'id':'entry','path':'module.json5','from':'Stage','to':'Alternate','expectedFailedChecks':['stage-created']},
 {'id':'event','path':'Stage.ets','from':'environment','to':'wrong','expectedFailedChecks':['application-environment-registration']}]}
count=0
class Participant:
 def __init__(self,evidence,*args,**kwargs):
  self.evidence=evidence;self.model='fixture-model';self.route='fixture-route';self.implementation='pi';self.reasoning_effort=None
 def close(self):pass
 def turn(self,label,workspace,prompt,transport_retry_limit):
  global count
  count+=1;out=Path('draft' if count==1 else 'draft-repair');out.mkdir()
  assert transport_retry_limit==0
  value=json.loads(json.dumps(proposal))
  if not semantic and not extra_fields and (count==1 or mode=='exhausted'):value['configurations'][0]['id']='stage-created'
  if extra_fields and count==1:
   value['notes']={'untrusted':'extra author explanation'}
   value['configurations'][-1]['language']=value['configurations'][0]['language']
  if semantic and (count==1 or mode=='exhausted'):value['configurationPrefix']='wrong-prefix: '
  if semantic and mode=='infrastructure':value['variants'][1]['to']="environment';throw Error('unsupported')//"
  if semantic and count==2:
   assert 'stage semantic controls rejected:' in prompt and 'failedChecks' in prompt and 'config: ' in prompt
  if mode=='identity-drift':value['candidateId']='different-candidate'
  if mode=='review-drift':value['reviewed']=True
  (out/'proposed-stage-contract.json').write_text(json.dumps(value))
  e=self.evidence;(e/'author-calibration-prompt.txt').write_text(prompt)
  final=b'{"role":"assistant","content":[]}'
  (e/'author-calibration-final-assistant-message.json').write_bytes(final)
  (e/'author-calibration-lifecycle.json').write_text(json.dumps({'label':'author-calibration','captureAuthority':'operator','exitCode':0,'timedOut':False,
   'participantBudgetSeconds':419 if mode=='budget-drift' else 420,'participantBudgetScope':'native-process-watchdog',
   'transportRetryLimit':1 if mode=='transport-budget-drift' else transport_retry_limit,
   'finalAssistantMessagePresent':True,'finalAssistantMessageSha256':hashlib.sha256(final).hexdigest()}))
  if mode=='transport-retry-sidecar':(e/'author-calibration-transport-retry.json').write_text('{}')
  if mode=='transport-retry-symlink':(e/'author-calibration-transport-retry.json').symlink_to('missing-retry.json')
  g=e/'gateway';g.mkdir();(g/'0001.upstream-request.json').write_text(json.dumps({'model':self.model,'providerId':self.route,'stream':True,'messages':[{'role':'user','content':[{'type':'text','text':prompt}]}]}))
  response=b'data: {"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
  (g/'0001.response').write_bytes(response)
  (g/'0001.status.json').write_text(json.dumps({'exchangeId':'0001','status':200,'durationMs':1,'upstreamEof':True,'semanticComplete':mode!='wire-failure',
   'outcome':'completed','streamError':None,'responseBytes':len(response)}))
  if mode=='source-drift' and count==1:Path('Stage.ets').write_text('changed source')
  if mode=='request-drift' and count==1:Path('authoring-request.json').write_text('{}')
  if mode=='guidance-drift' and count==1:Path('packet.json').write_text('{}')
  if mode=='prior-drift' and count==2:Path('draft/proposed-stage-contract.json').write_text('{}')
module=types.SimpleNamespace(Participant=Participant)
prompt=m.stage_prompt(request,Path('draft'))+m.guidance_prompt(request)
m.run_author(module,'fixture-pi',request,raw,prompt,Path.cwd()/'participant-evidence',Path('state'))
first=Path('draft/proposed-stage-contract.json').read_bytes()
try:
 m.require_stage_identity(json.loads(first),request['stageContext'])
 m.validate_and_repair(module,'fixture-pi',request,raw,Path('authoring-request.json'),Path('draft'))
except (ValueError,RuntimeError) as error:
 assert mode!='success',str(error)+' '+''.join(p.read_text() for p in Path('participant-evidence').glob('*stderr.log'))
 if mode=='prior-drift':assert 'previous rejected attempt changed' in str(error)
else:assert mode=='success'
assert count==(2 if mode in ('success','exhausted','prior-drift') else 1),count
if mode!='prior-drift':assert Path('draft/proposed-stage-contract.json').read_bytes()==first
if mode in ('success','exhausted','prior-drift'):
 assert Path('participant-evidence/rejected-proposal.json').read_bytes()==first
 assert Path('participant-evidence-repair/gateway/0001.response').exists()
 manifest=json.loads(Path('authoring-attempts.json').read_bytes())
 assert manifest['nativeSessionRestored'] is False and manifest['automaticPromotion'] is False
 assert manifest['transportRetryLimit']==0 and manifest['maximumParticipantBudgetSeconds']==840
 assert manifest['latestAttempt']=='repair'
 if mode!='prior-drift':assert manifest['attempts'][-1]['proposalChangedFromRejected'] == (mode=='success')
if mode=='success':
 assert [a['validatorExitCode'] for a in manifest['attempts']]==([0,0] if semantic else [1,0])
 if semantic:
  assert [a['semanticSeamCalibrationPassed'] for a in manifest['attempts']]==[False,True]
  assert json.loads(Path('participant-evidence/semantic-diagnostic.json').read_bytes())['diagnosticOnly'] is True
 assert manifest['attempts'][0]['proposalSha256']==hashlib.sha256(first).hexdigest()
 assert json.loads(Path('participant-evidence-repair/content-validation.json').read_bytes())['semanticExecutionVerified'] is False
 if request.get('guidanceMode')=='unguided':
  assert not Path('participant-evidence/guidance-prompt.txt').exists()
  assert not Path('participant-evidence-repair/guidance-consumption-intent.json').exists()
  receipt=json.loads(Path('participant-evidence-repair/completion-validation.json').read_bytes())
  assert receipt['authorCompletionVerified'] is True and receipt['guidanceProvided'] is False
  assert receipt['guidanceAbsenceVerified'] is False and receipt['learningBenefitVerified'] is False
  assert receipt['implicitTransportRetryDisabledVerified'] is True and receipt['transportRetryLimit']==0
  import os
  for index,change in enumerate(({'guidanceMode':'guided'},{'maintainerGuidance':{}})):
   changed={**request,**change};path=Path('changed-request-'+str(index)+'.json');path.write_text(json.dumps(changed))
   output=Path('must-not-exist-'+str(index)+'.json')
   result=m.gate(Path(os.environ['AGENTLAB_FLYWHEEL_TOOL']),Path('participant-evidence-repair'),'changed-'+str(index),
    ['--verify-author-completion','--participant-evidence','participant-evidence-repair','--author-request',str(path),'--output',str(output)])
   assert result.returncode!=0 and not output.exists()
# This is an adapter fixture with actual Rust gates, not real Agent learning evidence.
"#]).arg(repo.join("examples/multi-repo-case/pi-calibration-author.py")).arg(mode)
            .env("AGENTLAB_FLYWHEEL_TOOL", env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .env("AGENTLAB_GUIDANCE_PACKET_PATH", f.root.join("packet.json"))
            .env("AGENTLAB_AUTHOR_REPAIR_LIMIT", if mode.ends_with("zero") { "0" } else { "1" })
            .env("AGENTLAB_LM_GATEWAY_URL", "http://fixture.invalid")
            .env("AGENTLAB_AUTHOR_SEMANTIC_CONTROLS", if semantic { "true" } else { "false" })
            .env("AGENTLAB_STAGE_DIAGNOSTIC_SCRIPT", repo.join("scripts/calibrate-harmony-stage-controls.cjs"))
            .env_remove("AGENTLAB_STAGE_COMPILER")
            .output().unwrap();
        assert!(
            result.status.success(),
            "{mode}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
}

#[test]
fn stage_proposal_binds_real_replacements_and_rejects_string_modes_and_source_drift() {
    let f = Fixture::new("arbitrary-stage-proposal");
    let mut sources = Vec::new();
    for (path, raw) in [
        ("module.json5", "{\"module\":{\"srcEntry\":\"./Stage.js\"}}"),
        ("Stage.js", "owner.on('environment', callback);"),
        ("Alternate.js", "alternate stage"),
    ] {
        fs::write(f.root.join(path), raw).unwrap();
        sources.push(json!({"path":path,"workspacePath":path,"revision":"a".repeat(40),"sha256":digest(raw.as_bytes()),"bytes":raw.len()}));
    }
    let context = json!({"candidateId":"arbitrary-candidate","candidateSha256":"b".repeat(64),"sourceRevision":"a".repeat(40),"modulePath":"module.json5"});
    let request = json!({"schema":"agentlab.stage_calibration_authoring_request.v1","automaticPromotion":false,"stageContext":context,"sources":sources});
    let request_bytes = serde_json::to_vec(&request).unwrap();
    let proposal = json!({"schema":"agentlab.harmony_stage_control_contract.v1","reviewed":false,
        "candidateId":"arbitrary-candidate","candidateSha256":"b".repeat(64),"sourceRevision":"a".repeat(40),"modulePath":"module.json5",
        "createMarker":"created","destroyMarker":"destroyed","registrationMarker":"registered","configurationPrefix":"config: ","eventName":"environment",
        "configurations":[{"id":"initial","language":"en","colorMode":0},{"id":"language","language":"zh","colorMode":0},{"id":"color","language":"zh","colorMode":1}],
        "variants":[{"id":"entry","path":"module.json5","from":"./Stage.js","to":"./Alternate.js","expectedFailedChecks":["stage-created"]},
            {"id":"event","path":"Stage.js","from":"'environment'","to":"'wrong'","expectedFailedChecks":["application-environment-registration"]}]});
    let validate =
        |p: &Value| stage_proposal(&f.root, &request_bytes, &serde_json::to_vec(p).unwrap());
    let receipt = validate(&proposal).unwrap();
    assert_eq!(receipt["proposalContentValid"], true);
    assert_eq!(receipt["semanticExecutionVerified"], false);
    let mut extra = proposal.clone();
    extra["notes"] = json!({"explanation":"untrusted extra field"});
    assert_eq!(
        validate(&extra).unwrap_err(),
        "stage proposal fields differ"
    );
    extra["candidateId"] = json!("other");
    assert_eq!(
        validate(&extra).unwrap_err(),
        "stage proposal identity differs"
    );
    extra["reviewed"] = json!(true);
    assert_eq!(
        validate(&extra).unwrap_err(),
        "stage proposal schema or review boundary differs"
    );
    for (pointer, value) in [
        ("/configurations/0/colorMode", json!("light")),
        ("/variants/0/to", json!("./Stage.js")),
        ("/variants/1/from", json!("Stage.js")),
        ("/variants/1/expectedFailedChecks", json!([])),
        ("/reviewed", json!(true)),
        ("/candidateId", json!("other")),
    ] {
        let mut changed = proposal.clone();
        *changed.pointer_mut(pointer).unwrap() = value;
        assert!(validate(&changed).is_err(), "must reject {pointer}");
    }
    fs::write(f.root.join("Stage.js"), "changed source").unwrap();
    assert!(validate(&proposal)
        .unwrap_err()
        .contains("source bytes changed"));
}

impl Fixture {
    fn new(repo: &str) -> Self {
        let root = std::env::temp_dir().join(format!(
            "agentlab-guidance-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        let source = "a".repeat(40);
        let lineage = json!({"repository":"operations-repo","revision":"c".repeat(40),"lessonId":"lesson-mechanism","tablePrefix":"data/","lessonFileDigest":"d".repeat(64)});
        let provenance = json!({"repositoryId":repo,"sourceRevision":source,"methodRevision":"b".repeat(40),
            "methodDigest":"e".repeat(64),"sourceLessonId":"lesson-mechanism","sourceLessonExportDigest":"d".repeat(64),"lessonSource":lineage});
        let mut skill = provenance.clone();
        for (key, value) in json!({"id":"reviewed-method","body":"Observe every declared phase and require intended wrong variants to fail; startup alone is not configuration delivery.",
            "role":"maintenance","stage":"calibration","objectId":"lesson-mechanism","factIds":["reviewed-fact"],
            "ownershipPlane":"target-operations","automaticPromotion":false}).as_object().unwrap() {
            skill[key] = value.clone();
        }
        let mut fact = provenance;
        fact["id"] = json!("reviewed-fact");
        fact["qualification"] = json!({"caseQualified":false,"harmonyRuntimeQualified":false});
        let mut cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1","automaticPromotion":false,
            "tableGitAuthority":{"repo":"knowledge-repo","revision":"f".repeat(40)},
            "repositories":[{"id":repo,"revision":source}],"tables":{}});
        for (name, file, rows) in [
            (
                "maintainerSkills",
                "maintainer_skills.jsonl",
                vec![skill.clone()],
            ),
            ("programFacts", "program_facts.jsonl", vec![fact]),
            (
                "maintainerScopeSkills",
                "maintainer_scope_skills.jsonl",
                vec![],
            ),
            (
                "maintainerSkillRefreshRounds",
                "maintainer_skill_refresh_rounds.jsonl",
                vec![],
            ),
            ("evaluationCases", "evaluation_cases.jsonl", vec![]),
        ] {
            let bytes: Vec<u8> = rows
                .iter()
                .flat_map(|r| {
                    let mut b = serde_json::to_vec(r).unwrap();
                    b.push(b'\n');
                    b
                })
                .collect();
            fs::write(root.join(file), &bytes).unwrap();
            cut["tables"][name] = json!({"path":file,"sha256":digest(&bytes)});
        }
        let cut_bytes = serde_json::to_vec(&cut).unwrap();
        fs::write(root.join("maintainer-knowledge-cut.json"), &cut_bytes).unwrap();
        let selection = json!({"schema":"agentlab.maintainer_guidance_selection.v1","automaticPromotion":false,
            "knowledgeCutSha256":digest(&cut_bytes),"knowledgeRevision":"f".repeat(40),"stage":"calibration",
            "sources":[{"repositoryId":repo,"sourceRevision":source}],
            "skills":[{"id":"reviewed-method","objectId":"lesson-mechanism","rowSha256":digest(&serde_json::to_vec(&skill).unwrap()),
                "applicabilityReason":"The selected task exercises the same declared configuration lifecycle mechanism."}]});
        Self { root, selection }
    }
    fn bind(&self, selection: &Value) -> Result<Value, String> {
        bind(&self.root, &serde_json::to_vec(selection).unwrap())
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}

#[test]
fn behavior_guidance_requires_exact_reviewed_source_stage_and_committed_cut() {
    let f = Fixture::new("independent-subject");
    let bytes = serde_json::to_vec(&f.selection).unwrap();
    let bind = |repo: &str, revision: &str, stage: &str| {
        agentlab_code_analysis::maintainer_behavior_loop::bind_guidance(
            &f.root, &bytes, repo, revision, stage,
        )
    };
    assert_eq!(
        bind("independent-subject", &"a".repeat(40), "calibration").unwrap()
            ["learningBenefitVerified"],
        false
    );
    assert!(bind("other-subject", &"a".repeat(40), "calibration").is_err());
    assert!(bind("independent-subject", &"b".repeat(40), "calibration").is_err());
    assert!(bind("independent-subject", &"a".repeat(40), "evaluation").is_err());
    fs::write(f.root.join("program_facts.jsonl"), b"changed").unwrap();
    assert!(bind("independent-subject", &"a".repeat(40), "calibration").is_err());
}

#[test]
fn stage_author_prompt_binds_frozen_context_without_claiming_review_or_runtime() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let status = Command::new("python3")
        .current_dir(root)
        .args(["-c", r#"
import importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('author','examples/multi-repo-case/pi-calibration-author.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
context={'candidateId':'arbitrary-candidate','candidateSha256':'a'*64,'sourceRevision':'b'*40,'modulePath':'arbitrary-module/src/main/module.json5'}
prompt=module.stage_prompt({'stageContext':context},Path('draft'))
assert json.dumps(context,sort_keys=True) in prompt
assert 'reviewed=false' in prompt and 'proposed-stage-contract.json' in prompt
assert 'not actual Harmony framework' in prompt and 'at least two distinct meaningful wrong variants' in prompt
assert 'another supplied existing stage' in prompt and 'one dimension per transition' in prompt
assert 'Do not execute authored code' in prompt
assert 'source-surface.json' not in prompt
"#])
        .status().unwrap();
    assert!(status.success());
}

#[test]
fn recorded_wire_requires_full_prompt_exact_guidance_and_raw_semantic_completion() {
    let f = Fixture::new("arbitrary-wire-source");
    let packet = f.bind(&f.selection).unwrap();
    let packet_bytes = serde_json::to_vec(&packet).unwrap();
    let prompt = format!("Stage authoring instructions\n{}\n", packet);
    fs::write(f.root.join("guidance-prompt.txt"), &prompt).unwrap();
    fs::write(f.root.join("author-calibration-prompt.txt"), &prompt).unwrap();
    let row = &packet["guidance"][0];
    let intent = json!({"schema":"agentlab.maintainer_guidance_prompt_intent.v1",
        "promptSha256":digest(prompt.as_bytes()),"knowledgeAuthority":packet["knowledgeAuthority"],
        "participantIdentity":{"model":"fixture-model","providerRoute":"fixture-route","implementation":"pi"},
        "selectedSkills":[{"id":row["skill"]["id"],"rowSha256":row["rowSha256"],"bodySha256":row["bodySha256"]}]});
    fs::write(
        f.root.join("guidance-consumption-intent.json"),
        serde_json::to_vec(&intent).unwrap(),
    )
    .unwrap();
    let final_bytes = serde_json::to_vec(&json!({"role":"assistant","stopReason":"stop","content":[{"type":"text","text":"fixture only"}]})).unwrap();
    fs::write(
        f.root
            .join("author-calibration-final-assistant-message.json"),
        &final_bytes,
    )
    .unwrap();
    let lifecycle = json!({"label":"author-calibration","captureAuthority":"operator","exitCode":0,"timedOut":false,
        "finalAssistantMessagePresent":true,"finalAssistantMessageSha256":digest(&final_bytes)});
    fs::write(
        f.root.join("author-calibration-lifecycle.json"),
        serde_json::to_vec(&lifecycle).unwrap(),
    )
    .unwrap();
    let gateway = f.root.join("gateway");
    fs::create_dir(&gateway).unwrap();
    let wire = json!({"model":"fixture-model","providerId":"fixture-route","stream":true,
        "messages":[{"role":"user","content":[{"type":"text","text":prompt}]}]});
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&wire).unwrap(),
    )
    .unwrap();
    let response = b"data: {\"choices\":[{\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n";
    fs::write(gateway.join("0001.response"), response).unwrap();
    let status = json!({"exchangeId":"0001","status":200,"durationMs":1,"upstreamEof":true,"semanticComplete":true,
        "outcome":"completed","streamError":null,"responseBytes":response.len()});
    fs::write(
        gateway.join("0001.status.json"),
        serde_json::to_vec(&status).unwrap(),
    )
    .unwrap();
    let receipt = consumption(&f.root, &packet_bytes).unwrap();
    assert_eq!(receipt["agentConsumptionVerified"], true);
    assert_eq!(receipt["learningBenefitVerified"], false);
    assert_eq!(receipt["producerAuthenticated"], false);
    assert_eq!(receipt["caseQualified"], false);
    let guided_request =
        json!({"guidanceMode":"guided","maintainerGuidance":packet,"taskDemand":"unchanged task"});
    let guided_bytes = serde_json::to_vec(&guided_request).unwrap();
    let mut bound_intent = intent.clone();
    bound_intent["requestSha256"] = json!(digest(&guided_bytes));
    bound_intent["participantBudgetSeconds"] = json!(120);
    bound_intent["transportRetryLimit"] = json!(0);
    let mut bound_lifecycle = lifecycle.clone();
    bound_lifecycle["participantBudgetSeconds"] = json!(120);
    bound_lifecycle["participantBudgetScope"] = json!("native-process-watchdog");
    bound_lifecycle["transportRetryLimit"] = json!(0);
    fs::write(
        f.root.join("author-calibration-lifecycle.json"),
        serde_json::to_vec(&bound_lifecycle).unwrap(),
    )
    .unwrap();
    fs::write(
        f.root.join("guidance-consumption-intent.json"),
        serde_json::to_vec(&bound_intent).unwrap(),
    )
    .unwrap();
    let bound =
        agentlab_code_analysis::maintainer_guidance::guided_completion(&f.root, &guided_bytes)
            .unwrap();
    assert_eq!(bound["requestSha256"], digest(&guided_bytes));
    assert_eq!(bound["learningBenefitVerified"], false);
    let mut borrowed = guided_request.clone();
    borrowed["taskDemand"] = json!("different task");
    assert!(
        agentlab_code_analysis::maintainer_guidance::guided_completion(
            &f.root,
            &serde_json::to_vec(&borrowed).unwrap()
        )
        .is_err()
    );
    fs::write(
        f.root.join("guidance-consumption-intent.json"),
        serde_json::to_vec(&intent).unwrap(),
    )
    .unwrap();
    fs::write(
        f.root.join("author-calibration-lifecycle.json"),
        serde_json::to_vec(&lifecycle).unwrap(),
    )
    .unwrap();
    let mut unexpected_reasoning = wire.clone();
    unexpected_reasoning["reasoning_effort"] = json!("high");
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&unexpected_reasoning).unwrap(),
    )
    .unwrap();
    assert!(consumption(&f.root, &packet_bytes)
        .unwrap_err()
        .contains("provider reasoning"));
    let mut low_intent = intent.clone();
    low_intent["participantIdentity"]["providerReasoningEffort"] = json!("low");
    unexpected_reasoning["reasoning_effort"] = json!("low");
    fs::write(
        f.root.join("guidance-consumption-intent.json"),
        serde_json::to_vec(&low_intent).unwrap(),
    )
    .unwrap();
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&unexpected_reasoning).unwrap(),
    )
    .unwrap();
    assert_eq!(
        consumption(&f.root, &packet_bytes).unwrap()["completedGuidanceExchanges"][0]
            ["providerReasoningEffort"],
        "low"
    );
    fs::write(
        f.root.join("guidance-consumption-intent.json"),
        serde_json::to_vec(&intent).unwrap(),
    )
    .unwrap();
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&wire).unwrap(),
    )
    .unwrap();
    fs::write(
        gateway.join("0002.upstream-request.json"),
        serde_json::to_vec(&wire).unwrap(),
    )
    .unwrap();
    fs::write(gateway.join("0002.response"), b"data: {\"choices\":[]}\n\n").unwrap();
    let mut later = status.clone();
    later["exchangeId"] = json!("0002");
    later["semanticComplete"] = json!(false);
    later["upstreamEof"] = json!(false);
    later["outcome"] = json!("upstream_deadline_exceeded");
    fs::write(
        gateway.join("0002.status.json"),
        serde_json::to_vec(&later).unwrap(),
    )
    .unwrap();
    assert!(
        consumption(&f.root, &packet_bytes)
            .unwrap_err()
            .contains("final exchange"),
        "completed prefix and exit zero cannot qualify an interrupted final exchange"
    );
    for name in [
        "0002.upstream-request.json",
        "0002.response",
        "0002.status.json",
    ] {
        fs::remove_file(gateway.join(name)).unwrap();
    }
    let mut missing = wire.clone();
    missing["messages"][0]["content"][0]["text"] = json!("only the Skill id, not the body");
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&missing).unwrap(),
    )
    .unwrap();
    assert!(consumption(&f.root, &packet_bytes).is_err());
    fs::write(
        gateway.join("0001.upstream-request.json"),
        serde_json::to_vec(&wire).unwrap(),
    )
    .unwrap();
    let incomplete = b"data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n";
    fs::write(gateway.join("0001.response"), incomplete).unwrap();
    let mut forged = status.clone();
    forged["responseBytes"] = json!(incomplete.len());
    fs::write(
        gateway.join("0001.status.json"),
        serde_json::to_vec(&forged).unwrap(),
    )
    .unwrap();
    assert!(
        consumption(&f.root, &packet_bytes).is_err(),
        "self-rehashed producer completion must not substitute for raw terminal frames"
    );
    // The accepted wire above is a fixture; it is not a real model consumption receipt.
}

#[test]
fn explicit_guidance_rejects_stage_source_row_object_and_cut_drift() {
    let f = Fixture::new("arbitrary-repo-one");
    let packet = f.bind(&f.selection).unwrap();
    assert_eq!(
        packet["guidance"][0]["facts"][0]["qualification"]["caseQualified"],
        false
    );
    assert_eq!(packet["agentConsumptionVerified"], false);
    assert_eq!(packet["learningBenefitVerified"], false);
    assert_eq!(packet["remoteCommitAuthenticated"], false);
    assert_eq!(packet, f.bind(&f.selection).unwrap());
    for (pointer, value) in [
        ("/stage", json!("semantic-analysis")),
        ("/sources/0/sourceRevision", json!("0".repeat(40))),
        ("/sources/0/repositoryId", json!("different-repo")),
        ("/skills/0/rowSha256", json!("0".repeat(64))),
        ("/skills/0/objectId", json!("unrelated-mechanism")),
        ("/skills/0/applicabilityReason", json!("")),
        ("/knowledgeRevision", json!("0".repeat(40))),
        ("/knowledgeCutSha256", json!("0".repeat(64))),
        ("/automaticPromotion", json!(true)),
    ] {
        let mut bad = f.selection.clone();
        *bad.pointer_mut(pointer).unwrap() = value;
        assert!(f.bind(&bad).is_err(), "accepted changed {pointer}");
    }
    let mut bad = f.selection.clone();
    bad["skills"]
        .as_array_mut()
        .unwrap()
        .push(f.selection["skills"][0].clone());
    assert!(f.bind(&bad).is_err());
    fs::write(f.root.join("evaluation_cases.jsonl"), b"{}\n").unwrap();
    assert!(f.bind(&f.selection).is_err());
}

#[test]
fn actual_cli_and_author_prompt_preserve_body_provenance_and_limits_for_two_identities() {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_owned();
    for repo in ["arbitrary-repo-one", "arbitrary-repo-two"] {
        let f = Fixture::new(repo);
        let input = f.root.join("selection.json");
        let output = f.root.join("packet.json");
        fs::write(&input, serde_json::to_vec(&f.selection).unwrap()).unwrap();
        let command = || {
            Command::new(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
                .args(["--bind-maintainer-guidance", "--knowledge"])
                .arg(&f.root)
                .arg("--guidance-request")
                .arg(&input)
                .arg("--output")
                .arg(&output)
                .output()
                .unwrap()
        };
        assert!(command().status.success());
        let bytes = fs::read(&output).unwrap();
        assert!(!command().status.success());
        assert_eq!(fs::read(&output).unwrap(), bytes);
        let packet: Value = serde_json::from_slice(&bytes).unwrap();
        let request = json!({"sources":[{"repositoryId":repo,"revision":"a".repeat(40)}],"maintainerGuidance":packet});
        let request_path = f.root.join("author-request.json");
        fs::write(&request_path, serde_json::to_vec(&request).unwrap()).unwrap();
        let code = "import importlib.util,json,sys; s=importlib.util.spec_from_file_location('a',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.guidance_prompt(json.load(open(sys.argv[2]))))";
        let prompt = Command::new("python3")
            .arg("-c")
            .arg(code)
            .arg(repo_root.join("examples/multi-repo-case/pi-calibration-author.py"))
            .arg(&request_path)
            .output()
            .unwrap();
        assert!(
            prompt.status.success(),
            "{}",
            String::from_utf8_lossy(&prompt.stderr)
        );
        let prompt = String::from_utf8(prompt.stdout).unwrap();
        assert!(prompt.contains(
            request["maintainerGuidance"]["guidance"][0]["skill"]["body"]
                .as_str()
                .unwrap()
        ));
        assert!(prompt.contains("operations-repo"));
        assert!(prompt.contains("caseQualified\": false"));
        // Prompt assembly is not proof that a real Agent received or learned it.
        let mut forged = request.clone();
        forged["maintainerGuidance"]["guidance"][0]["skill"]["body"] = json!("forged body");
        fs::write(&request_path, serde_json::to_vec(&forged).unwrap()).unwrap();
        let rejected = Command::new("python3")
            .arg("-c")
            .arg(code)
            .arg(repo_root.join("examples/multi-repo-case/pi-calibration-author.py"))
            .arg(&request_path)
            .output()
            .unwrap();
        assert!(!rejected.status.success());
    }
}

#[test]
fn actual_authoring_producer_binds_complete_inputs_and_refuses_unrelated_sources() {
    let f = Fixture::new("arbitrary-author-source");
    let selection = f.root.join("selection.json");
    fs::write(&selection, serde_json::to_vec(&f.selection).unwrap()).unwrap();
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_owned();
    let code = r#"
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(sys.argv[1]).parent))
s=importlib.util.spec_from_file_location('author',sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
root=Path(sys.argv[2]);workspace=root/'producer-workspace';workspace.mkdir()
args=SimpleNamespace(guidance_knowledge=root,guidance_selection=root/'selection.json',flywheel_tool=Path(sys.argv[3]))
rows=[{'repositoryId':'arbitrary-author-source','revision':'a'*40}]
packet=m.bind_guidance(args,rows,workspace)
assert packet['guidance'][0]['skill']['body']
assert packet['agentConsumptionVerified'] is False
assert (workspace/'guidance-knowledge'/'maintainer_skills.jsonl').read_bytes()==(root/'maintainer_skills.jsonl').read_bytes()
try:m.bind_guidance(args,[{'repositoryId':'unrelated','revision':'a'*40}],workspace)
except m.AuthoringError:pass
else:raise AssertionError('unrelated authoring source accepted')
args.flywheel_tool=None
try:m.bind_guidance(args,rows,workspace)
except m.AuthoringError:pass
else:raise AssertionError('incomplete authority inputs accepted')
print('real Rust producer binding and source rejection passed; no model execution')
"#;
    let result = Command::new("python3")
        .arg("-c")
        .arg(code)
        .arg(root.join("scripts/run-multi-repo-calibration-authoring.py"))
        .arg(&f.root)
        .arg(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn guided_authoring_pipeline_rebinds_retained_cut_and_rejects_tampering() {
    let f = Fixture::new("contracts");
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_owned();
    let code = r#"
import importlib.util,json,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
repo=Path(sys.argv[1]);root=Path(sys.argv[2]);tool=Path(sys.argv[3])
sys.path.insert(0,str(repo/'scripts'))
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
test=module('fixtures',repo/'tests/test_multi_repo_calibration_authoring.py')
fixture=root/'multi';fixture.mkdir()
selection,difficulty,manifest,facts=test.MultiRepoCalibrationAuthoringTests().fixture(fixture)
revision=next(r['revision'] for r in json.load(open(manifest))['repositories'] if r['id']=='contracts')
cut=json.load(open(root/'maintainer-knowledge-cut.json'))
for name,file in [('maintainerSkills','maintainer_skills.jsonl'),('programFacts','program_facts.jsonl')]:
 row=json.loads((root/file).read_text());row['sourceRevision']=revision
 raw=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode();(root/file).write_bytes(raw)
 cut['tables'][name]['sha256']=hashlib.sha256(raw).hexdigest()
cut['repositories'][0]['revision']=revision
cutbytes=json.dumps(cut,sort_keys=True,separators=(',',':')).encode();(root/'maintainer-knowledge-cut.json').write_bytes(cutbytes)
skill=json.loads((root/'maintainer_skills.jsonl').read_text())
request={'schema':'agentlab.maintainer_guidance_selection.v1','automaticPromotion':False,
 'knowledgeCutSha256':hashlib.sha256(cutbytes).hexdigest(),'knowledgeRevision':'f'*40,'stage':'calibration',
 'sources':[{'repositoryId':'contracts','sourceRevision':revision}],
 'skills':[{'id':'reviewed-method','objectId':'lesson-mechanism','rowSha256':hashlib.sha256(json.dumps(skill,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'applicabilityReason':'Explicit test applicability; not real cross-repository acceptance.'}]}
(root/'guidance-selection.json').write_text(json.dumps(request))
m=module('author',repo/'scripts/run-multi-repo-calibration-authoring.py')
args=SimpleNamespace(selection=selection,difficulty=difficulty,manifest=manifest,facts=facts,
 participant=repo/'examples/multi-repo-case/mock-calibration-author.py',participant_id='mock-guided-control',
 method_revision='d'*40,output=root/'guided-output',guidance_knowledge=root,
 guidance_selection=root/'guidance-selection.json',flywheel_tool=tool,
 localization=None,localization_proposal=None,localization_review=None,semantic_packet=None,semantic_decision=None,semantic_gate=None)
receipt=m.run(args);assert receipt['status']=='review-required'
assert m.validate_output(args.output,tool)==receipt
try:m.validate_output(args.output)
except m.AuthoringError:pass
else:raise AssertionError('guided verification accepted without Rust rebinding')
(args.output/'workspace/guidance-knowledge/program_facts.jsonl').write_text('{}\n')
try:m.validate_output(args.output,tool)
except m.AuthoringError:pass
else:raise AssertionError('retained fact tampering accepted')
print('full guided mock pipeline and independent rejection passed; no real model or generalization claim')
"#;
    let result = Command::new("python3")
        .arg("-c")
        .arg(code)
        .arg(&root)
        .arg(&f.root)
        .arg(env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
