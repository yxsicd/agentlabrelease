use agentlab_code_analysis::{digest, maintainer_behavior_checks::verify};
use serde_json::{json, Value};

fn fixture() -> (Value, Value) {
    let mut contract = json!({"schema":"agentlab.frozen_behavior_checks.v1","candidateId":"generic-task","candidateSha256":"a".repeat(64),"sourceRevision":"b".repeat(40),"originalSourceSha256":digest(b"baseline"),"methodSha256":"c".repeat(64),"compilerSha256":"d".repeat(64),"runtime":"test-runtime","workerDeadlineMs":1000,"checks":[{"id":"preserve","input":{"response":false},"expected":[1,"retained"]},{"id":"success","input":null,"expected":{"cleared":true}}],"controls":[],"automaticPromotion":false});
    let mut workers = Vec::new();
    let mut controls = Vec::new();
    for (id, role, failure) in [
        ("baseline", "baseline", Some("preserve")),
        ("valid-a", "accepted", None),
        ("valid-b", "accepted", None),
        ("wrong-a", "wrong", Some("preserve")),
        ("wrong-b", "wrong", Some("success")),
    ] {
        controls.push(json!({"id":id,"role":role,"submittedSourceSha256":digest(id.as_bytes()),"expectedFailedCheckIds":failure.map(|id| vec![id]).unwrap_or_default()}));
        let raw = json!({"id":id,"submittedSource":id,"submittedSourceSha256":digest(id.as_bytes()),"originalSourceSha256":digest(b"baseline"),"observations":contract["checks"].as_array().unwrap().iter().map(|check|json!({"id":check["id"],"input":check["input"],"actual":if failure==check["id"].as_str() {json!("wrong")} else {check["expected"].clone()},"expected":"producer cannot override contract","passed":true})).collect::<Vec<_>>()});
        let stdout = serde_json::to_string(&raw).unwrap();
        workers.push(json!({"id":id,"execution":{"stdoutSha256":digest(stdout.as_bytes()),"stdout":stdout,"exitCode":0,"timedOut":false,"durationMs":10}}));
    }
    contract["controls"] = json!(controls);
    let capture = json!({"schema":"agentlab.behavior_worker_capture.v1","contractSha256":digest(&serde_json::to_vec(&contract).unwrap()),"candidateId":contract["candidateId"],"candidateSha256":contract["candidateSha256"],"sourceRevision":contract["sourceRevision"],"methodSha256":contract["methodSha256"],"compilerSha256":contract["compilerSha256"],"runtime":contract["runtime"],"workers":workers});
    (contract, capture)
}
fn check(contract: &Value, capture: &Value) -> Result<Value, String> {
    verify(
        &serde_json::to_vec(contract).unwrap(),
        &serde_json::to_vec(capture).unwrap(),
    )
}
fn modify(capture: &mut Value, worker: usize, edit: impl FnOnce(&mut Value)) {
    let execution = &mut capture["workers"][worker]["execution"];
    let mut raw: Value = serde_json::from_str(execution["stdout"].as_str().unwrap()).unwrap();
    edit(&mut raw);
    let stdout = serde_json::to_string(&raw).unwrap();
    execution["stdoutSha256"] = json!(digest(stdout.as_bytes()));
    execution["stdout"] = json!(stdout);
}

#[test]
fn reconstructs_mixed_json_checks_without_trusting_producer_boolean_or_expected() {
    let (contract, capture) = fixture();
    let feedback = check(&contract, &capture).unwrap();
    assert_eq!(feedback["nextAction"], "execute-agent-attempt");
    assert_eq!(
        feedback["controls"][0]["failedCheckIds"],
        json!(["preserve"])
    );
    assert_eq!(feedback["qualified"], false);
    assert_eq!(feedback["producerAuthenticated"], false);
}

#[test]
fn distinguishes_valid_control_and_surviving_wrong_control_failures() {
    let (contract, mut capture) = fixture();
    modify(&mut capture, 1, |raw| {
        raw["observations"][0]["actual"] = json!(false)
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-valid-controls"
    );
    let (_, mut capture) = fixture();
    modify(&mut capture, 3, |raw| {
        raw["observations"][0]["actual"] = json!([1, "retained"])
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-oracle-or-wrong-controls"
    );
}

#[test]
fn infrastructure_or_incomplete_capture_never_counts_as_behavior_failure() {
    for scenario in [
        "exit",
        "timeout",
        "deadline",
        "stdout",
        "missing",
        "duplicate",
        "input",
        "source",
    ] {
        let (contract, mut capture) = fixture();
        match scenario {
            "exit" => capture["workers"][3]["execution"]["exitCode"] = json!(1),
            "timeout" => capture["workers"][3]["execution"]["timedOut"] = json!(true),
            "deadline" => capture["workers"][3]["execution"]["durationMs"] = json!(1001),
            "stdout" => capture["workers"][3]["execution"]["stdoutSha256"] = json!("0".repeat(64)),
            "missing" => modify(&mut capture, 3, |raw| {
                raw["observations"].as_array_mut().unwrap().pop();
            }),
            "duplicate" => modify(&mut capture, 3, |raw| {
                raw["observations"][1] = raw["observations"][0].clone();
            }),
            "input" => modify(&mut capture, 3, |raw| {
                raw["observations"][1]
                    .as_object_mut()
                    .unwrap()
                    .remove("input");
            }),
            _ => modify(&mut capture, 3, |raw| {
                raw["submittedSource"] = json!("swapped source")
            }),
        }
        assert!(check(&contract, &capture).is_err(), "{scenario}");
    }
}

#[test]
fn rejects_changed_contract_identity_and_duplicate_valid_sources() {
    let (mut contract, capture) = fixture();
    contract["checks"][0]["expected"] = json!("new expected after execution");
    assert!(check(&contract, &capture).is_err());
    let (contract, mut capture) = fixture();
    capture["runtime"] = json!("other-runtime");
    assert!(check(&contract, &capture).is_err());
    let (mut contract, mut capture) = fixture();
    contract["controls"][2]["submittedSourceSha256"] =
        contract["controls"][1]["submittedSourceSha256"].clone();
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&contract).unwrap()));
    assert!(check(&contract, &capture).is_err());
}

#[test]
fn agent_outcomes_retain_every_frozen_check_and_select_behavioral_repair() {
    let (mut contract, mut capture) = fixture();
    contract["controls"].as_array_mut().unwrap().push(json!({"id":"agent","role":"agent-attempt","submittedSourceSha256":digest(b"agent subject"),"expectedFailedCheckIds":[]}));
    let mut worker = capture["workers"][1].clone();
    worker["id"] = json!("agent");
    capture["workers"].as_array_mut().unwrap().push(worker);
    modify(&mut capture, 5, |raw| {
        raw["id"] = json!("agent");
        raw["submittedSource"] = json!("agent subject");
        raw["submittedSourceSha256"] = json!(digest(b"agent subject"));
    });
    capture["contractSha256"] = json!(digest(&serde_json::to_vec(&contract).unwrap()));
    let success = check(&contract, &capture).unwrap();
    assert_eq!(success["nextAction"], "review-agent-outcome");
    assert_eq!(success["qualified"], false);
    modify(&mut capture, 5, |raw| {
        raw["observations"][1]["actual"] = json!({"cleared":false})
    });
    assert_eq!(
        check(&contract, &capture).unwrap()["nextAction"],
        "repair-agent-behavior"
    );
    modify(&mut capture, 5, |raw| {
        raw["observations"].as_array_mut().unwrap().pop();
    });
    assert!(check(&contract, &capture).is_err());
}

#[cfg(unix)]
fn loop_fixture(failing_executor: bool, repeat: bool) -> (Vec<u8>, Vec<u8>, Vec<u8>) {
    let (contract, capture) = fixture();
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    let capture_bytes = serde_json::to_vec(&capture).unwrap();
    let command = |script: String| json!({"program":"/bin/sh","programSha256":digest(&std::fs::read("/bin/sh").unwrap()),"args":["-c",script,"adapter","{request}"],"cwd":".","timeoutMs":1000});
    let raw = |number: usize, source: &str, failed: bool| {
        serde_json::to_string(&json!({"id":format!("agent-attempt-{number}"),"submittedSource":source,"submittedSourceSha256":digest(source.as_bytes()),"originalSourceSha256":contract["originalSourceSha256"],"observations":contract["checks"].as_array().unwrap().iter().map(|c| json!({"id":c["id"],"input":c["input"],"actual":if failed && c["id"]=="preserve" {json!("wrong")} else {c["expected"].clone()}})).collect::<Vec<_>>()})).unwrap()
    };
    let participant = if repeat {
        "printf '%s' '{\"submittedSource\":\"bad subject\"}'".into()
    } else {
        "case \"$1\" in *attempt-0*) printf '%s' '{\"submittedSource\":\"bad subject\"}';; *) printf '%s' '{\"submittedSource\":\"valid-a\"}';; esac".into()
    };
    let executor = if failing_executor {
        "exit 9".into()
    } else {
        format!(
            "case \"$1\" in *attempt-0*) printf '%s' '{}';; *) printf '%s' '{}';; esac",
            raw(0, "bad subject", true),
            raw(1, "valid-a", false)
        )
    };
    let recipe = json!({"schema":"agentlab.behavior_loop_recipe.v1","reviewed":true,"automaticPromotion":false,"contractSha256":digest(&contract_bytes),"captureSha256":digest(&capture_bytes),"taskDemand":"Preserve data on failure and clear on success.","maximumAttempts":2,"immutableInputs":[],"participantCommand":command(participant),"executorCommand":command(executor)});
    (
        contract_bytes,
        capture_bytes,
        serde_json::to_vec(&recipe).unwrap(),
    )
}

#[cfg(unix)]
fn loop_output(label: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "agentlab-behavior-loop-{label}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[test]
#[cfg(unix)]
fn real_subprocess_loop_delivers_failed_feedback_then_rechecks_repaired_subject() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let out = loop_output("repair");
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out,
    )
    .unwrap();
    assert_eq!(result["status"], "recorded-attempt-passed");
    assert_eq!(result["attempts"].as_array().unwrap().len(), 2);
    assert_eq!(result["attempts"][0]["nextAction"], "repair-agent-behavior");
    let repair: Value = serde_json::from_slice(
        &std::fs::read(out.join("attempt-1/participant-request.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(repair["submittedSource"], "bad subject");
    assert_eq!(repair["feedback"]["nextAction"], "repair-agent-behavior");
    assert_eq!(
        result["latestFeedback"]["nextAction"],
        "review-agent-outcome"
    );
    assert_eq!(result["participantAuthenticated"], false);
    assert_eq!(result["qualified"], false);
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out
    )
    .is_err());
}

#[test]
#[cfg(unix)]
fn loop_stops_infrastructure_and_suppresses_identical_failed_subject() {
    let (contract, capture, recipe) = loop_fixture(true, false);
    let out = loop_output("infrastructure");
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract, &capture, &recipe, &out
    )
    .unwrap_err()
    .contains("infrastructure"));
    assert!(!out.join("attempt-1").exists());
    assert!(out.join("attempt-0/executor.json").is_file());
    let (contract, capture, recipe) = loop_fixture(false, true);
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &recipe,
        &loop_output("repeat"),
    )
    .unwrap();
    assert_eq!(result["status"], "unchanged-attempt-suppressed");
    assert_eq!(result["attempts"].as_array().unwrap().len(), 1);
}

#[test]
#[cfg(unix)]
fn participant_cannot_rewrite_frozen_checks_before_executor_dispatch() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    recipe["participantCommand"]["args"][1] = json!(
        "printf corrupt > ../frozen-contract.json; printf '%s' '{\"submittedSource\":\"valid-a\"}'"
    );
    let out = loop_output("tamper");
    let error = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap_err();
    assert!(error.contains("immutable input changed"));
    assert!(out.join("attempt-0/participant.json").is_file());
    assert!(!out.join("attempt-0/executor.json").exists());
}

#[test]
#[cfg(unix)]
fn nested_gateway_capture_is_retained_and_later_mutation_is_rejected() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    let original = recipe["participantCommand"]["args"][1]
        .as_str()
        .unwrap()
        .to_owned();
    recipe["participantCommand"]["args"][1]=json!(format!("mkdir -p participant-evidence/gateway; printf capture > participant-evidence/gateway/1.capture; {original}"));
    let out = loop_output("nested");
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap();
    assert_eq!(result["status"], "recorded-attempt-passed");
    assert_eq!(
        std::fs::read(out.join("attempt-0/participant-evidence/gateway/1.capture")).unwrap(),
        b"capture"
    );
    recipe["participantCommand"]["args"][1]=json!(format!("mkdir -p participant-evidence/gateway; printf capture > participant-evidence/gateway/1.capture; case \"$1\" in *attempt-1*) printf changed > ../attempt-0/participant-evidence/gateway/1.capture;; esac; {original}"));
    let out = loop_output("nested-tamper");
    let error = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out,
    )
    .unwrap_err();
    assert!(error.contains("immutable input changed"));
    assert!(!out.join("attempt-1/executor.json").exists());
}

#[test]
#[cfg(unix)]
fn participant_environment_is_explicit_and_never_inherited_by_executor() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    let previous = std::env::var_os("AGENTLAB_MODEL");
    std::env::set_var("AGENTLAB_MODEL", "controller-test");
    recipe["participantEnvironmentNames"] = json!(["AGENTLAB_MODEL"]);
    let participant = recipe["participantCommand"]["args"][1].as_str().unwrap();
    recipe["participantCommand"]["args"][1] = json!(format!(
        "test \"$AGENTLAB_MODEL\" = controller-test || exit 44; {participant}"
    ));
    let executor = recipe["executorCommand"]["args"][1].as_str().unwrap();
    recipe["executorCommand"]["args"][1] = json!(format!(
        "test -z \"${{AGENTLAB_MODEL+x}}\" || exit 43; {executor}"
    ));
    let result = agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &loop_output("environment"),
    );
    match previous {
        Some(value) => std::env::set_var("AGENTLAB_MODEL", value),
        None => std::env::remove_var("AGENTLAB_MODEL"),
    }
    assert_eq!(result.unwrap()["status"], "recorded-attempt-passed");
    recipe["participantEnvironmentNames"] = json!(["UNREVIEWED_SECRET"]);
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &loop_output("bad-environment")
    )
    .unwrap_err()
    .contains("not allowed"));
}

#[test]
#[cfg(unix)]
fn required_participant_completion_rejects_plain_subprocess_before_behavior_execution() {
    let (contract, capture, recipe) = loop_fixture(false, false);
    let mut recipe: Value = serde_json::from_slice(&recipe).unwrap();
    recipe["participantCompletionRequired"] = json!(true);
    let out = loop_output("completion");
    assert!(agentlab_code_analysis::maintainer_behavior_loop::execute(
        &contract,
        &capture,
        &serde_json::to_vec(&recipe).unwrap(),
        &out
    )
    .is_err());
    assert!(out.join("attempt-0/participant.json").is_file());
    assert!(!out.join("attempt-0/executor.json").exists());
}

#[test]
fn pi_adapter_protocol_fixture_binds_request_capture_submission_and_watchdog() {
    for guided in [false, true] {
        let out = loop_output_for_adapter();
        std::fs::create_dir(&out).unwrap();
        let mut request = json!({"schema":"agentlab.behavior_participant_request.v1","guidanceMode":"unguided","submittedSource":"baseline","taskDemand":"repair task","automaticPromotion":false});
        if guided {
            let skill =
                json!({"id":"fixture-skill","body":"Retain ownership until the declared release."});
            request["guidanceMode"] = json!("guided");
            request["maintainerGuidance"] = json!({"schema":"agentlab.maintainer_guidance_packet.v1",
            "knowledgeAuthority":{"repo":"fixture-knowledge","revision":"a".repeat(40)},
            "guidance":[{"skill":skill,"rowSha256":digest(&serde_json::to_vec(&skill).unwrap()),
                "bodySha256":digest(skill["body"].as_str().unwrap().as_bytes())}],"automaticPromotion":false});
        }
        let bytes = serde_json::to_vec(&request).unwrap();
        std::fs::write(out.join("request.json"), &bytes).unwrap();
        let adapter = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../examples/real-code-agent/behavior-participant.py");
        let result=std::process::Command::new("python3").current_dir(&out).args(["-c",r#"
import importlib.util,importlib.abc,json,sys,hashlib,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('behavior',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class FakeParticipant:
 def __init__(self,evidence,state,binary,gateway,model,route,reasoning_effort,gateway_timeout_seconds):
  assert gateway_timeout_seconds==60
  receipts=Path(os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT']).resolve(strict=True)
  assert receipts.is_dir() and receipts== (evidence/'runtime').resolve(strict=True)
  assert not list(receipts.iterdir())
  self.evidence=evidence;self.model=model;self.route=route;self.implementation='pi';self.reasoning_effort=None
 def _run_turn(self,*args,**kwargs): assert kwargs['timeout_seconds']==120
 def turn(self,label,workspace,prompt,tool_call_limit,transport_retry_limit):
  assert tool_call_limit==12 and transport_retry_limit==0
  self._run_turn()
  (workspace/'submitted-source.txt').write_text('valid-a')
  e=self.evidence;(e/'author-calibration-prompt.txt').write_text(prompt)
  final=b'{"role":"assistant","content":[]}'
  (e/'author-calibration-final-assistant-message.json').write_bytes(final)
  (e/'author-calibration-lifecycle.json').write_text(json.dumps({'label':label,'captureAuthority':'operator','exitCode':0,'timedOut':False,
   'participantBudgetSeconds':120,'participantBudgetScope':'native-process-watchdog','transportRetryLimit':0,
   'finalAssistantMessagePresent':True,'finalAssistantMessageSha256':hashlib.sha256(final).hexdigest()}))
  g=e/'gateway';g.mkdir()
  (g/'0001.upstream-request.json').write_text(json.dumps({'model':self.model,'providerId':self.route,'stream':True,'messages':[{'role':'user','content':prompt}]}))
  response=b'data: {"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
  (g/'0001.response').write_bytes(response)
  (g/'0001.status.json').write_text(json.dumps({'exchangeId':'0001','status':200,'durationMs':1,'upstreamEof':True,'semanticComplete':True,'outcome':'completed','streamError':None,'responseBytes':len(response)}))
 def close(self):pass
class Loader(importlib.abc.Loader):
 def create_module(self,spec):return None
 def exec_module(self,module):module.Participant=FakeParticipant
m.importlib.util.spec_from_file_location=lambda name,path:importlib.util.spec_from_loader(name,Loader())
sys.argv=['adapter','request.json'];m.main()
"#]).arg(adapter).env("AGENTLAB_PI_BINARY","fixture-pi").env("AGENTLAB_LM_GATEWAY_URL","http://fixture.invalid").env("AGENTLAB_MODEL","fixture-model").env("AGENTLAB_PROVIDER_ROUTE","fixture-route").env("AGENTLAB_PARTICIPANT_RUNTIME_CONFIG","fixture-runtime-config").output().unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let output: Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(output["submittedSource"], "valid-a");
        assert_eq!(
            std::fs::read(out.join("participant-evidence/behavior-submitted-source.txt")).unwrap(),
            b"valid-a"
        );
        let completion = if guided {
            agentlab_code_analysis::maintainer_guidance::guided_completion(
                &out.join("participant-evidence"),
                &bytes,
            )
        } else {
            agentlab_code_analysis::maintainer_guidance::completion(
                &out.join("participant-evidence"),
                &bytes,
            )
        }
        .unwrap();
        if guided {
            assert_eq!(completion["agentConsumptionVerified"], true);
            assert!(agentlab_code_analysis::maintainer_guidance::completion(
                &out.join("participant-evidence"),
                &bytes
            )
            .is_err());
        } else {
            assert_eq!(completion["authorCompletionVerified"], true);
        }
        assert_eq!(completion["participantBudgetSeconds"], 120);
        assert_eq!(completion["producerAuthenticated"], false);
    }
}

fn loop_output_for_adapter() -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "agentlab-behavior-adapter-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ))
}

#[test]
fn contained_worker_rejects_unreviewed_or_changed_input_before_runtime() {
    let script = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/run-contained-behavior-worker.py");
    for (label, reviewed, source_sha, image, message) in [
        (
            "unreviewed",
            false,
            digest(b"source"),
            "invalid",
            "not reviewed",
        ),
        (
            "changed",
            true,
            "0".repeat(64),
            "invalid",
            "submitted source differs",
        ),
        (
            "image",
            true,
            digest(b"source"),
            "invalid",
            "exact local ID",
        ),
    ] {
        let dir = loop_output_for_adapter();
        std::fs::create_dir(&dir).unwrap();
        let dir = dir.canonicalize().unwrap();
        std::fs::write(dir.join("descriptor.json"),serde_json::to_vec(&json!({"schema":"agentlab.contained_behavior_executor.v1","reviewed":reviewed,"automaticPromotion":false,"imageId":image})).unwrap()).unwrap();
        std::fs::write(dir.join("request.json"),serde_json::to_vec(&json!({"schema":"agentlab.behavior_executor_request.v1","submittedSource":"source","submittedSourceSha256":source_sha})).unwrap()).unwrap();
        let result = std::process::Command::new("python3")
            .arg(&script)
            .arg(dir.join("descriptor.json"))
            .arg(dir.join("request.json"))
            .current_dir(&dir)
            .output()
            .unwrap();
        assert!(!result.status.success(), "{label}");
        assert!(
            String::from_utf8_lossy(&result.stderr).contains(message),
            "{label}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(std::fs::read_dir(dir).unwrap().count(), 2);
    }
}

#[test]
fn lifecycle_worker_executes_owned_zero_id_recreation_and_retry_behavior() {
    let repository = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let profile: Value = serde_json::from_slice(&std::fs::read(repository.join(
        "examples/maintainer-knowledge-gate/reviewed-behavior/environment-lifecycle-demand.json",
    )).unwrap()).unwrap();
    let dir = loop_output_for_adapter();
    std::fs::create_dir(&dir).unwrap();
    let compiler = dir.join("compiler.cjs");
    // JavaScript-only protocol fixture, not TypeScript/Harmony qualification.
    let compiler_bytes = b"module.exports={ModuleKind:{CommonJS:1},ScriptTarget:{ES2022:9},DiagnosticCategory:{Error:1},flattenDiagnosticMessageText(message){return message},transpileModule(source){return{outputText:source,diagnostics:source.includes('SYNTAX_REJECTED')?[{category:1,code:1128,file:{text:source},start:source.length-1,length:1,messageText:'Declaration or statement expected.'}]:source.includes('UNBOUND_COMPILER')?[{category:1,code:5107,messageText:'Compiler configuration error'}]:[]}}};";
    std::fs::write(&compiler, compiler_bytes).unwrap();
    let mut support = profile["supportFields"].clone();
    support["compilerSha256"] = json!(digest(compiler_bytes));
    std::fs::write(
        dir.join("support.json"),
        serde_json::to_vec(&support).unwrap(),
    )
    .unwrap();
    let valid = r#"// [Start myAbility_start]
exports.default = class extends require('@kit.AbilityKit').AbilityStage {
  id;
  onCreate() {
    if (this.id !== undefined) return;
    try {
      this.id = this.context.getApplicationContext().on('environment', {
        onConfigurationUpdated(config) { console.info('envCallback onConfigurationUpdated success: '+JSON.stringify(config)); },
        onMemoryLevel(level) { console.info('onMemoryLevel level: '+level); }
      });
    } catch (error) {}
  }
  onDestroy() {
    if (this.id !== undefined) {
      this.context.getApplicationContext().off('environment', this.id);
      this.id = undefined;
    }
  }
};
// [End myAbility_start]
"#;
    for (id, source, intended_failure) in [
        ("valid", valid.to_string(), None),
        (
            "syntax-rejected",
            format!("{valid}// SYNTAX_REJECTED\n}}"),
            Some("destroy-zero"),
        ),
        (
            "unbound-compiler",
            format!("{valid}// UNBOUND_COMPILER"),
            Some("destroy-zero"),
        ),
        (
            "zero-skipped",
            valid.replace("if (this.id !== undefined) {", "if (this.id) {"),
            Some("destroy-zero"),
        ),
        (
            "stale-owner",
            valid.replace("this.id = undefined;", "this.id = this.id;"),
            Some("recreate-positive"),
        ),
        (
            "duplicate",
            valid.replace(
                "if (this.id !== undefined) return;",
                "/* no duplicate guard */",
            ),
            Some("repeat-create-zero"),
        ),
    ] {
        let checks: Vec<_> = profile["checks"]
            .as_array()
            .unwrap()
            .iter()
            .map(|check| json!({"id":check["id"],"input":check["input"]}))
            .collect();
        let request = json!({"schema":"agentlab.behavior_executor_request.v1","id":id,
            "originalSourceSha256":digest(valid.as_bytes()),"submittedSource":source,
            "submittedSourceSha256":digest(source.as_bytes()),"checks":checks});
        let request_path = dir.join(format!("{id}.json"));
        std::fs::write(&request_path, serde_json::to_vec(&request).unwrap()).unwrap();
        let result = std::process::Command::new("node")
            .arg(repository.join("scripts/environment-lifecycle-worker.cjs"))
            .arg(request_path)
            .arg(dir.join("support.json"))
            .arg(&compiler)
            .output()
            .unwrap();
        if id == "unbound-compiler" {
            assert!(!result.status.success());
            assert!(String::from_utf8_lossy(&result.stderr).contains("Unbound compiler diagnostic"));
            assert!(result.stdout.is_empty());
            continue;
        }
        assert!(
            result.status.success(),
            "{id}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        let actual: Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(actual["id"], id);
        assert_eq!(
            actual["submittedSourceSha256"],
            request["submittedSourceSha256"]
        );
        assert_eq!(
            actual["observations"].as_array().unwrap().len(),
            checks.len()
        );
        let mut failed = Vec::new();
        for (expected, observed) in profile["checks"]
            .as_array()
            .unwrap()
            .iter()
            .zip(actual["observations"].as_array().unwrap())
        {
            assert_eq!(observed["input"], expected["input"]);
            if observed["actual"] != expected["expected"] {
                failed.push(expected["id"].as_str().unwrap());
            }
        }
        match intended_failure {
            None => assert!(failed.is_empty(), "{failed:?}"),
            Some(check) => assert!(failed.contains(&check), "{id}: {failed:?}"),
        }
        if id == "syntax-rejected" {
            assert_eq!(failed.len(), checks.len());
            for observed in actual["observations"].as_array().unwrap() {
                assert_eq!(observed["actual"]["sourceRejected"], true);
                assert_eq!(observed["actual"]["diagnostics"][0]["code"], 1128);
            }
        }
    }
}
