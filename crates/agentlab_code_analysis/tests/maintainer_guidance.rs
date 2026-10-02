use agentlab_code_analysis::{
    digest,
    maintainer_guidance::{bind, consumption, stage_proposal},
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
    ] {
        let f = Fixture::new("portable-repair-source");
        let packet = f.bind(&f.selection).unwrap();
        fs::write(
            f.root.join("packet.json"),
            serde_json::to_vec(&packet).unwrap(),
        )
        .unwrap();
        let mut sources = Vec::new();
        for (path, raw) in [
            ("module.json5", "entry=Stage"),
            ("Stage.ets", "on('environment')"),
        ] {
            fs::write(f.root.join(path), raw).unwrap();
            sources.push(json!({"repositoryId":"portable-repair-source","revision":"a".repeat(40),
                "path":path,"workspacePath":path,"sha256":digest(raw.as_bytes()),"bytes":raw.len()}));
        }
        let request = json!({"schema":"agentlab.stage_calibration_authoring_request.v1","automaticPromotion":false,
            "stageContext":{"candidateId":"portable-candidate","candidateSha256":"b".repeat(64),"sourceRevision":"a".repeat(40),"modulePath":"module.json5"},
            "sources":sources,"maintainerGuidance":packet});
        fs::write(
            f.root.join("authoring-request.json"),
            serde_json::to_vec(&request).unwrap(),
        )
        .unwrap();
        let result = Command::new("python3").current_dir(&f.root).args(["-c", r#"
import importlib.util,json,sys,hashlib,types
from pathlib import Path
spec=importlib.util.spec_from_file_location('author',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
mode=sys.argv[2];raw=Path('authoring-request.json').read_bytes();request=json.loads(raw)
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
 def turn(self,label,workspace,prompt):
  global count
  count+=1;out=Path('draft' if count==1 else 'draft-repair');out.mkdir()
  value=json.loads(json.dumps(proposal))
  if count==1 or mode=='exhausted':value['configurations'][0]['id']='stage-created'
  if mode=='identity-drift':value['candidateId']='different-candidate'
  if mode=='review-drift':value['reviewed']=True
  (out/'proposed-stage-contract.json').write_text(json.dumps(value))
  e=self.evidence;(e/'author-calibration-prompt.txt').write_text(prompt)
  final=b'{"role":"assistant","content":[]}'
  (e/'author-calibration-final-assistant-message.json').write_bytes(final)
  (e/'author-calibration-lifecycle.json').write_text(json.dumps({'label':'author-calibration','captureAuthority':'operator','exitCode':0,'timedOut':False,
   'finalAssistantMessagePresent':True,'finalAssistantMessageSha256':hashlib.sha256(final).hexdigest()}))
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
try:m.validate_and_repair(module,'fixture-pi',request,raw,Path('authoring-request.json'),Path('draft'))
except (ValueError,RuntimeError) as error:
 assert mode!='success',str(error)+' '+str(list(Path('participant-evidence').glob('*stderr.log')) and Path('participant-evidence/consumption-stderr.log').read_text())
 if mode=='prior-drift':assert 'previous rejected attempt changed' in str(error)
else:assert mode=='success'
assert count==(2 if mode in ('success','exhausted','prior-drift') else 1),count
if mode!='prior-drift':assert Path('draft/proposed-stage-contract.json').read_bytes()==first
if mode in ('success','exhausted','prior-drift'):
 assert Path('participant-evidence/rejected-proposal.json').read_bytes()==first
 assert Path('participant-evidence-repair/gateway/0001.response').exists()
 manifest=json.loads(Path('authoring-attempts.json').read_bytes())
 assert manifest['nativeSessionRestored'] is False and manifest['automaticPromotion'] is False
 assert manifest['latestAttempt']=='repair'
if mode=='success':
 assert [a['validatorExitCode'] for a in manifest['attempts']]==[1,0]
 assert manifest['attempts'][0]['proposalSha256']==hashlib.sha256(first).hexdigest()
 assert json.loads(Path('participant-evidence-repair/content-validation.json').read_bytes())['semanticExecutionVerified'] is False
# This is an adapter fixture with actual Rust gates, not real Agent learning evidence.
"#]).arg(repo.join("examples/multi-repo-case/pi-calibration-author.py")).arg(mode)
            .env("AGENTLAB_FLYWHEEL_TOOL", env!("CARGO_BIN_EXE_agentlab-maintainer-skill-flywheel"))
            .env("AGENTLAB_GUIDANCE_PACKET_PATH", f.root.join("packet.json"))
            .env("AGENTLAB_AUTHOR_REPAIR_LIMIT", if mode == "zero" { "0" } else { "1" })
            .env("AGENTLAB_LM_GATEWAY_URL", "http://fixture.invalid")
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
