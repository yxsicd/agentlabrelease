#![cfg(unix)]
use agentlab_code_analysis::{
    digest,
    maintainer_operation_evidence::{compare_round, prepare_fact},
    maintainer_skill_flywheel::assess_with_receipts,
    maintainer_source_operation::{execute, qualify, recorded},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .canonicalize()
        .unwrap()
}

#[test]
fn source_recipe_operator_prepares_strict_runtime_receipt_directory() {
    let directory = std::env::temp_dir().join(format!(
        "source-recipe-runtime-root-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let receipt_root = directory.join("operator/runtime-receipts");
    let code = r#"
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location('recipe_author', os.environ['AUTHOR_SCRIPT'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'])
assert not root.exists()
assert module.prepare_runtime_receipt_root() == root.resolve(strict=True)
marker = root / 'retained-receipt.json'
marker.write_bytes(b'original-runtime-receipt')
assert module.prepare_runtime_receipt_root() == root.resolve(strict=True)
assert marker.read_bytes() == b'original-runtime-receipt'
del os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT']
try:
    module.prepare_runtime_receipt_root()
except KeyError:
    pass
else:
    raise AssertionError('missing operator configuration was accepted')
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "AUTHOR_SCRIPT",
            root().join("scripts/run-source-recipe-author.py"),
        )
        .env("AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT", &receipt_root)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(receipt_root.is_dir());
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn source_recipe_completion_rejects_partial_gateway_even_with_process_success() {
    let directory = std::env::temp_dir().join(format!(
        "source-recipe-completion-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&directory).unwrap();
    let code = r#"
import hashlib, importlib.util, json, os
from pathlib import Path
spec = importlib.util.spec_from_file_location('recipe_author', os.environ['AUTHOR_SCRIPT'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(os.environ['TEST_EVIDENCE'])
(root/'gateway').mkdir()
status_path = root/'gateway/0001.status.json'
good = dict(status=200, outcome='completed', semanticComplete=True, upstreamEof=True,
            upstreamDeadlineExceeded=False, streamError=None, clientDisconnected=False)
def check(status, accepted):
    if status is not None:
        status_path.write_text(json.dumps(status))
    try:
        module.require_complete_gateway_capture(root)
    except ValueError as error:
        assert not accepted, str(error)
    else:
        assert accepted, 'incomplete capture passed'
    report = json.loads((root/'construction-completion.json').read_bytes())
    assert report['complete'] == accepted
    assert report['automaticPromotion'] is False and report['authorityWritePerformed'] is False
    if status is not None:
        assert report['gatewayExchanges'][0]['sha256'] == hashlib.sha256(status_path.read_bytes()).hexdigest()
check(None, False)
check(good, True)
for change in [dict(semanticComplete=False), dict(upstreamEof=False),
               dict(upstreamDeadlineExceeded=True), dict(clientDisconnected=True),
               dict(streamError={'message':'failed'}), dict(status=500),
               dict(outcome='upstream_deadline_exceeded')]:
    check(dict(good, **change), False)
check(dict(good, upstreamEof=False, semanticComplete=False,
           outcome='upstream_deadline_exceeded', upstreamDeadlineExceeded=True), False)
check(good, True)
(root/'gateway/0002.status.json').write_text(json.dumps(dict(good, semanticComplete=False)))
check(good, False)
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "AUTHOR_SCRIPT",
            root().join("scripts/run-source-recipe-author.py"),
        )
        .env("TEST_EVIDENCE", &directory)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    fs::remove_dir_all(directory).unwrap();
}

#[test]
fn source_recipe_dispatch_uses_explicit_constructor_limits_without_retry() {
    let code = r#"
import importlib.util, json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
spec = importlib.util.spec_from_file_location('recipe_author', os.environ['AUTHOR_SCRIPT'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    request = root/'request.json'
    request.write_text(json.dumps(dict(schema='agentlab.source_recipe_author_request.v1',
        scope={'id':'arbitrary-scope'}, source={}, sourceFiles=[], semanticFacts=[],
        selectedGap={}, policy={'methodDependencies':[]})))
    for index, extra, effort, deadline, thinking in [(0, [], 'low', 180, None),
        (1, ['--reasoning-effort','high','--gateway-timeout-seconds','120'], 'high',120,None),
        (2, ['--reasoning-effort','default'], None,180,None),
        (3, ['--reasoning-effort','default','--thinking-type','disabled'],None,180,'disabled')]:
        seen = {}
        class FakeParticipant:
            def __init__(self, evidence, state, binary, gateway, model, **options):
                seen['constructor'] = options
                self.evidence = evidence
            def turn(self, label, workspace, **options):
                seen['turn'] = options
                gateway = self.evidence/'gateway'
                gateway.mkdir()
                (gateway/'0001.status.json').write_text(json.dumps(dict(status=200,
                    outcome='completed',semanticComplete=True,upstreamEof=True,
                    streamError=None,clientDisconnected=False)))
                return {'content':'{}','message':{'stopReason':'stop'}}
            def close(self): seen['closed'] = True
        fake_spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _:None))
        env = dict(AGENTLAB_PARTICIPANT_RUNTIME_CONFIG=str(root/'config.json'),
            AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT=str(root/'receipts'),
            AGENTLAB_LM_GATEWAY_URL='https://gateway.invalid',AGENTLAB_MODEL='arbitrary',
            AGENTLAB_PROVIDER_ROUTE='arbitrary')
        argv = ['author','--request',str(request),'--output',str(root/str(index)),
                '--gate','/unexecuted-fixture-gate','--pi','/unexecuted-fixture-pi',*extra]
        with patch.dict(os.environ,env), patch.object(sys,'argv',argv), \
             patch.object(module.importlib.util,'spec_from_file_location',return_value=fake_spec), \
             patch.object(module.importlib.util,'module_from_spec',return_value=SimpleNamespace(Participant=FakeParticipant)), \
             patch.object(module.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'',b'')) as stage:
            module.main()
        assert seen['constructor']['gateway_timeout_seconds'] == deadline
        assert seen['constructor']['thinking_type'] == thinking
        assert seen['turn']['reasoning_effort'] == effort
        assert seen['turn']['transport_retry_limit'] == 0
        assert seen['closed'] is True
        assert stage.call_count == 1
        assert '--stage-source-recipe-proposal' in stage.call_args[0][0]
        assert json.loads((root/str(index)/'proposal.json').read_bytes()) == {}
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "AUTHOR_SCRIPT",
            root().join("scripts/run-source-recipe-author.py"),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn source_recipe_rejects_token_truncation_even_after_clean_gateway_eof() {
    let code = r#"
import importlib.util, json, os, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location('recipe_author', os.environ['AUTHOR_SCRIPT'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for stop in [None, 'length', 'toolUse', 'aborted', 'error', 'stop']:
        result = {'content':'{}', 'message':{'stopReason':stop}}
        try:
            module.require_completed_generation(result, root)
        except ValueError:
            assert stop != 'stop'
        else:
            assert stop == 'stop'
        report = json.loads((root/'generation-completion.json').read_bytes())
        assert report['complete'] == (stop == 'stop')
        assert report['stopReason'] == stop
        assert report['authorityWritePerformed'] is False
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "AUTHOR_SCRIPT",
            root().join("scripts/run-source-recipe-author.py"),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

#[test]
fn explicit_thinking_policy_reaches_actual_proxy_wire_without_changing_defaults() {
    let code = r#"
import http.server, importlib.util, json, os, tempfile, threading, urllib.request
from pathlib import Path
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('participant', os.environ['PARTICIPANT_SCRIPT'])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
received = []
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        body = b'data: [DONE]\n\n'
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread = threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
try:
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'AGENTLAB_LM_GATEWAY_KEY':'synthetic-only'}):
        root = Path(directory)
        for index, thinking in enumerate([None,'enabled','disabled']):
            evidence = root/str(index); evidence.mkdir()
            participant = module.Participant(evidence,root/f'state-{index}','/bin/true',
                f'http://127.0.0.1:{server.server_port}','arbitrary-model',thinking_type=thinking)
            try:
                request = urllib.request.Request(f'http://127.0.0.1:{participant.server.server_port}/v1/chat/completions',
                    data=json.dumps({'model':'ignored','stream':True}).encode(),
                    headers={'Authorization':'Bearer '+participant.local_proxy_token})
                with urllib.request.urlopen(request,timeout=5) as response: response.read()
            finally: participant.close()
            actual = json.loads((evidence/'gateway/0001.upstream-request.json').read_bytes())
            assert actual == received[-1]
            assert 'reasoning_effort' not in actual
            if thinking is None: assert 'thinking' not in actual
            else: assert actual['thinking'] == {'type':thinking}
        try:
            module.Participant(root,root/'invalid','/bin/true','http://localhost','arbitrary',thinking_type='invented')
        except ValueError: pass
        else: raise AssertionError('invalid thinking policy accepted')
finally:
    server.shutdown();server.server_close();thread.join()
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "PARTICIPANT_SCRIPT",
            root().join("examples/real-code-agent/participant.py"),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
fn fixture() -> (PathBuf, Value, Value, Value) {
    static SEQUENCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let dir = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "source-operation-{}-{}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&dir).unwrap();
    fs::create_dir(dir.join("source")).unwrap();
    fs::create_dir(dir.join("source/src")).unwrap();
    let source = dir.join("source");
    fs::write(source.join("src/state.json"), b"{\"value\":1}").unwrap();
    fs::write(source.join("oracle.js"),"const fs=require('fs'); const original=JSON.parse(fs.readFileSync(process.argv[2])); const mode=process.argv[3]; if(mode==='error') { console.error('original-error'); process.exit(7); } console.log(JSON.stringify({value:mode==='wrong'?0:original.value,pass:mode==='wrong'}));\n").unwrap();
    let git = |a: &[&str]| {
        let r = Command::new("git")
            .args(a)
            .current_dir(&source)
            .output()
            .unwrap();
        assert!(r.status.success());
        String::from_utf8(r.stdout).unwrap().trim().to_owned()
    };
    git(&["init"]);
    git(&["config", "user.name", "Fixture"]);
    git(&["config", "user.email", "fixture@example.invalid"]);
    git(&[
        "remote",
        "add",
        "origin",
        "https://example.invalid/arbitrary.git",
    ]);
    git(&["add", "src/state.json", "oracle.js"]);
    git(&["commit", "-m", "fixture"]);
    let revision = git(&["rev-parse", "HEAD"]);
    let blob = git(&["rev-parse", "HEAD:src/state.json"]);
    let rows = fs::read_to_string(
        root().join("examples/maintainer-knowledge-gate/first-four/maintainer_scope_skills.jsonl"),
    )
    .unwrap();
    let mut skill = rows
        .lines()
        .map(|s| serde_json::from_str::<Value>(s).unwrap())
        .find(|s| s["id"] == "skill-scope-code-workshop-common-ui-state-contracts")
        .unwrap();
    skill["id"] = json!("scope-arbitrary");
    skill["repositoryId"] = json!("arbitrary");
    skill["repository"] = json!("https://example.invalid/arbitrary.git");
    skill["sourceRevision"] = json!(revision);
    skill["sourceTreeOid"] = json!(git(&["rev-parse", "HEAD^{tree}"]));
    skill["pathBoundary"] = json!("src");
    skill["ownershipSelectors"] = Value::Null;
    skill["trackedFileCount"] = json!(1);
    skill["sourceFileCount"] = json!(1);
    skill["evidence"] = json!([{"path":"src/state.json","gitBlobOid":blob}]);
    skill["responsibility"] = json!("Maintain the bounded fixture state contract.");
    let fact = json!({"id":"semantic-arbitrary","kind":"semantic-contract","repositoryId":"arbitrary","sourceRevision":revision,"scopeSkillIds":["scope-arbitrary"],
        "dimensions":["responsibility","boundary","relations","behavior"],"evidence":skill["evidence"]});
    fs::write(
        dir.join("scopes.jsonl"),
        serde_json::to_vec(&skill).unwrap(),
    )
    .unwrap();
    fs::write(dir.join("facts.jsonl"), serde_json::to_vec(&fact).unwrap()).unwrap();
    fs::create_dir(dir.join("receipts")).unwrap();
    let before = assess_with_receipts(
        &dir.join("scopes.jsonl"),
        Some(&dir.join("facts.jsonl")),
        1,
        None,
        Some(&dir.join("receipts")),
    )
    .unwrap();
    let result = Command::new("sh")
        .args(["-c", "command -v node"])
        .output()
        .unwrap();
    assert!(result.status.success());
    let node = String::from_utf8(result.stdout).unwrap().trim().to_owned();
    let command = |mode: &str| json!({"program":node,"programSha256":digest(&fs::read(&node).unwrap()),"args":[source.join("oracle.js"),"src/state.json",mode],"cwd":".","timeoutMs":30_000});
    let recipe = json!({"schema":"agentlab.maintainer_source_operation_recipe.v1","reviewed":true,"automaticPromotion":false,"operationKind":"source-only","scopeSkillId":skill["id"],
        "source":{"repositoryId":skill["repositoryId"],"repository":skill["repository"],"revision":revision},
        "sourceInputs":[{"path":"src/state.json","gitBlobOid":blob,"sha256":digest(&fs::read(source.join("src/state.json")).unwrap())}],
        "methodInputs":[{"path":source.join("oracle.js"),"sha256":digest(&fs::read(source.join("oracle.js")).unwrap())}],
        "checks":[{"id":"value","pointer":"/value","expected":1}],
        "controls":[{"id":"baseline","role":"baseline","command":command("baseline"),"expectedFailedCheckIds":[]},
            {"id":"reference","role":"reference","command":command("reference"),"expectedFailedCheckIds":[]},
            {"id":"wrong","role":"wrong","command":command("wrong"),"expectedFailedCheckIds":["value"]}]});
    (dir, skill, before, recipe)
}
fn run(dir: &Path, before: &Value, recipe: &Value, name: &str) -> Result<Value, String> {
    execute(
        &dir.join("scopes.jsonl"),
        &dir.join("facts.jsonl"),
        &dir.join("receipts"),
        &serde_json::to_vec(before).unwrap(),
        &serde_json::to_vec(recipe).unwrap(),
        &dir.join("source"),
        &dir.join(name),
    )
}
#[test]
fn pinned_large_method_dependencies_are_portable_but_bounded() {
    let (dir, skill, before, mut recipe) = fixture();
    let dependency = dir.join("compiler-dependency.bin");
    let bytes = vec![b'x'; 5 * 1024 * 1024];
    fs::write(&dependency, &bytes).unwrap();
    recipe["methodInputs"].as_array_mut().unwrap().push(json!({
        "path":dependency,"sha256":digest(&bytes)
    }));
    run(&dir, &before, &recipe, "large-capture").unwrap();
    let execution_bytes = fs::read(dir.join("large-capture/execution-receipt.json")).unwrap();
    let qualification = qualify(&dir.join("large-capture"), &digest(&execution_bytes)).unwrap();
    assert_eq!(
        recorded(&qualification, &skill).unwrap()["status"],
        "verified"
    );
    assert_eq!(
        fs::read(dir.join("large-capture/method-1.original")).unwrap(),
        bytes
    );
    fs::write(&dependency, vec![b'x'; 17 * 1024 * 1024]).unwrap();
    recipe["methodInputs"][1]["sha256"] = json!(digest(&fs::read(&dependency).unwrap()));
    assert!(run(&dir, &before, &recipe, "oversized-file").is_err());
    assert!(!dir.join("oversized-file").exists());
    // Individually legal dependencies must not exceed the total retained budget.
    recipe["methodInputs"].as_array_mut().unwrap().truncate(1);
    for (i, mib) in [12, 12, 9].into_iter().enumerate() {
        let path = dir.join(format!("dependency-{i}.bin"));
        let bytes = vec![b'y'; mib * 1024 * 1024];
        fs::write(&path, &bytes).unwrap();
        recipe["methodInputs"]
            .as_array_mut()
            .unwrap()
            .push(json!({"path":path,"sha256":digest(&bytes)}));
    }
    assert!(run(&dir, &before, &recipe, "oversized-total").is_err());
    assert!(!dir.join("oversized-total").exists());
    // The receiving verifier applies the same file bound to retained originals.
    fs::write(
        dir.join("large-capture/method-1.original"),
        vec![b'x'; 17 * 1024 * 1024],
    )
    .unwrap();
    assert!(qualify(&dir.join("large-capture"), &digest(&execution_bytes)).is_err());
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn real_controls_recompute_checks_and_advance_only_the_bound_scope() {
    let (dir, skill, before, recipe) = fixture();
    let execution = run(&dir, &before, &recipe, "capture").unwrap();
    assert_eq!(execution["qualified"], false);
    let execution_bytes = fs::read(dir.join("capture/execution-receipt.json")).unwrap();
    let qualification = qualify(&dir.join("capture"), &digest(&execution_bytes)).unwrap();
    let check = recorded(&qualification, &skill).unwrap();
    assert_eq!(check["status"], "verified");
    assert_eq!(check["controls"][2]["failedCheckIds"], json!(["value"]));
    assert_eq!(qualification["qualificationScope"]["runtime"], false);
    let bytes = serde_json::to_vec_pretty(&qualification).unwrap();
    fs::write(dir.join("receipts/source.json"), &bytes).unwrap();
    let operation = prepare_fact(
        &skill,
        json!({"path":"source.json","sha256":digest(&bytes)}),
        &dir.join("receipts"),
    )
    .unwrap();
    assert_eq!(operation["kind"], "source-maintenance-verification");
    assert!(operation["id"]
        .as_str()
        .unwrap()
        .starts_with("operation-source-"));
    let original = fs::read_to_string(dir.join("facts.jsonl")).unwrap();
    fs::write(
        dir.join("candidate.jsonl"),
        format!("{original}\n{}", serde_json::to_string(&operation).unwrap()),
    )
    .unwrap();
    let before_bytes = serde_json::to_vec(&before).unwrap();
    let after = assess_with_receipts(
        &dir.join("scopes.jsonl"),
        Some(&dir.join("candidate.jsonl")),
        2,
        Some(&digest(&before_bytes)),
        Some(&dir.join("receipts")),
    )
    .unwrap();
    let transition = compare_round(
        &before_bytes,
        &serde_json::to_vec(&after).unwrap(),
        &["scope-arbitrary".into()],
    )
    .unwrap();
    assert_eq!(transition["maintenanceReadyDelta"], 1);
    // Producer pass is deliberately false for accepted controls and true for wrong.
    // Tampered raw data, borrowed identity and stronger capabilities still reject.
    fs::write(dir.join("capture/reference.stdout"), b"{\"value\":0}").unwrap();
    assert!(qualify(&dir.join("capture"), &digest(&execution_bytes)).is_err());
    let mut borrowed = skill.clone();
    borrowed["id"] = json!("another");
    assert!(recorded(&qualification, &borrowed).is_err());
    borrowed = skill.clone();
    borrowed["buildEntrypoints"] = json!(["build.sh"]);
    assert!(recorded(&qualification, &borrowed).is_err());
    let mut changed = qualification.clone();
    changed["recipe"]["checks"][0]["expected"] = json!(0);
    assert!(recorded(&changed, &skill).is_err());
    fs::remove_dir_all(dir).unwrap();
}
#[test]
fn unreviewed_stale_and_failed_controls_never_qualify_or_overwrite() {
    let (dir, _, before, recipe) = fixture();
    let mut bad = recipe.clone();
    bad["reviewed"] = json!(false);
    assert!(run(&dir, &before, &bad, "unreviewed").is_err());
    assert!(!dir.join("unreviewed").exists());
    bad = recipe.clone();
    bad["sourceInputs"][0]["sha256"] = json!("0".repeat(64));
    assert!(run(&dir, &before, &bad, "stale").is_err());
    assert!(!dir.join("stale").exists());
    bad = recipe.clone();
    bad["controls"][1]["command"]["args"][2] = json!("error");
    assert!(run(&dir, &before, &bad, "failed").is_err());
    let bytes = fs::read(dir.join("failed/execution-receipt.json")).unwrap();
    let result: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(result["status"], "failed");
    assert_eq!(result["captures"][1]["exitCode"], 7);
    assert_eq!(
        fs::read(dir.join("failed/reference.stderr")).unwrap(),
        b"original-error\n"
    );
    assert!(qualify(&dir.join("failed"), &digest(&bytes)).is_err());
    assert!(run(&dir, &before, &recipe, "failed").is_err());
    assert_eq!(
        fs::read(dir.join("failed/execution-receipt.json")).unwrap(),
        bytes
    );
    fs::remove_dir_all(dir).unwrap();
}

fn loop_fixture() -> (PathBuf, Value) {
    loop_fixture_with_extra_source(false)
}

fn loop_fixture_with_extra_source(extra: bool) -> (PathBuf, Value) {
    let (dir, mut first, _, mut recipe) = fixture();
    let source = dir.join("source");
    fs::create_dir(source.join("other")).unwrap();
    fs::write(source.join("other/state.json"), b"{\"value\":1}").unwrap();
    if extra {
        fs::write(source.join("src/unloaded.json"), b"{\"metadata\":true}").unwrap();
    }
    for args in [
        vec!["add", "other/state.json", "src"],
        vec!["commit", "-m", "second responsibility"],
    ] {
        assert!(Command::new("git")
            .current_dir(&source)
            .args(args)
            .status()
            .unwrap()
            .success());
    }
    let git = |args: &[&str]| {
        String::from_utf8(
            Command::new("git")
                .current_dir(&source)
                .args(args)
                .output()
                .unwrap()
                .stdout,
        )
        .unwrap()
        .trim()
        .to_owned()
    };
    let revision = git(&["rev-parse", "HEAD"]);
    first["sourceRevision"] = json!(revision);
    first["sourceTreeOid"] = json!(git(&["rev-parse", "HEAD^{tree}"]));
    if extra {
        first["trackedFileCount"] = json!(2);
        first["sourceFileCount"] = json!(2);
    }
    let mut second = first.clone();
    second["id"] = json!("scope-second");
    second["pathBoundary"] = json!("other");
    second["trackedFileCount"] = json!(1);
    second["sourceFileCount"] = json!(1);
    second["evidence"] = json!([{"path":"other/state.json","gitBlobOid":git(&["rev-parse","HEAD:other/state.json"])}]);
    let knowledge = dir.join("knowledge");
    fs::create_dir(&knowledge).unwrap();
    fs::create_dir(knowledge.join("assessments")).unwrap();
    fs::create_dir(knowledge.join("operation-evidence")).unwrap();
    fs::write(
        knowledge.join("maintainer_scope_skills.jsonl"),
        format!("{}\n{}\n", first, second),
    )
    .unwrap();
    let facts: Vec<Value> = [&first, &second]
        .iter()
        .enumerate()
        .map(|(i, s)| {
            json!({"id":format!("semantic-{i}"),
        "repositoryId":"arbitrary","sourceRevision":revision,"scopeSkillIds":[s["id"]],
        "dimensions":["responsibility","boundary","relations","behavior"],"evidence":s["evidence"]})
        })
        .collect();
    fs::write(
        knowledge.join("program_facts.jsonl"),
        format!("{}\n{}\n", facts[0], facts[1]),
    )
    .unwrap();
    for name in ["maintainer_skills", "evaluation_cases"] {
        fs::write(knowledge.join(format!("{name}.jsonl")), b"").unwrap();
    }
    let before = assess_with_receipts(
        &knowledge.join("maintainer_scope_skills.jsonl"),
        Some(&knowledge.join("program_facts.jsonl")),
        1,
        None,
        Some(&knowledge.join("operation-evidence")),
    )
    .unwrap();
    assert_eq!(before["totals"]["semanticReadyCount"], 2);
    let before_bytes = serde_json::to_vec_pretty(&before).unwrap();
    fs::write(knowledge.join("assessments/before.json"), &before_bytes).unwrap();
    fs::write(
        knowledge.join("maintainer_skill_refresh_rounds.jsonl"),
        serde_json::to_vec(&json!({"id":"baseline","roundIndex":1,
        "assessment":{"path":"assessments/before.json","sha256":digest(&before_bytes)}}))
        .unwrap(),
    )
    .unwrap();
    let mut tables = serde_json::Map::new();
    for (key, name) in [
        ("maintainerSkills", "maintainer_skills"),
        ("maintainerScopeSkills", "maintainer_scope_skills"),
        ("programFacts", "program_facts"),
        (
            "maintainerSkillRefreshRounds",
            "maintainer_skill_refresh_rounds",
        ),
        ("evaluationCases", "evaluation_cases"),
    ] {
        let filename = format!("{name}.jsonl");
        tables.insert(
            key.into(),
            json!({"path":filename,"sha256":digest(&fs::read(knowledge.join(filename)).unwrap())}),
        );
    }
    let cut = json!({"schema":"agentlab.maintainer_knowledge_cut.v1","tables":tables,
        "repositories":[{"id":"arbitrary","repository":first["repository"],"revision":revision}],
        "tableGitAuthority":{"revision":"f".repeat(40)},"automaticPromotion":false});
    let cut_bytes = serde_json::to_vec_pretty(&cut).unwrap();
    fs::write(knowledge.join("maintainer-knowledge-cut.json"), &cut_bytes).unwrap();
    recipe["source"]["revision"] = json!(revision);
    let mut other = recipe.clone();
    other["scopeSkillId"] = second["id"].clone();
    other["sourceInputs"][0]["path"] = json!("other/state.json");
    for control in other["controls"].as_array_mut().unwrap() {
        control["command"]["args"][1] = json!("other/state.json");
    }
    let mut entries = Vec::new();
    for (index, r) in [recipe, other].iter().enumerate() {
        let bytes = serde_json::to_vec_pretty(r).unwrap();
        let path = dir.join(format!("recipe-{index}.json"));
        fs::write(&path, &bytes).unwrap();
        entries.push(
            json!({"scopeSkillId":r["scopeSkillId"],"sourceWorktree":source,
            "recipe":{"path":path,"sha256":digest(&bytes)}}),
        );
    }
    (
        dir,
        json!({"schema":"agentlab.reviewed_source_operation_catalog.v1","reviewed":true,
        "automaticPromotion":false,"knowledgeCutSha256":digest(&cut_bytes),"repositorySelector":"arbitrary","entries":entries}),
    )
}

#[test]
fn authored_recipe_is_gap_selected_unreviewed_and_only_executes_after_exact_review() {
    use agentlab_code_analysis::maintainer_source_recipe_author as author;
    let (dir, catalog) = loop_fixture_with_extra_source(true);
    let original: Value =
        serde_json::from_slice(&fs::read(dir.join("recipe-0.json")).unwrap()).unwrap();
    let node = fs::canonicalize(
        original["controls"][0]["command"]["program"]
            .as_str()
            .unwrap(),
    )
    .unwrap();
    let policy = json!({"schema":"agentlab.source_recipe_author_policy.v1","automaticPromotion":false,
        "program":node,"programSha256":digest(&fs::read(&node).unwrap()),"methodDependencies":[]});
    let request = author::prepare(
        &dir.join("knowledge"),
        &dir.join("source"),
        "arbitrary",
        &serde_json::to_vec(&policy).unwrap(),
    )
    .unwrap();
    assert_eq!(request["scope"]["id"], "scope-arbitrary");
    assert_eq!(request["sourceFiles"].as_array().unwrap().len(), 2);
    assert_eq!(request["sourceFiles"][0]["path"], "src/state.json");
    assert_eq!(request["sourceFiles"][1]["content"], Value::Null);
    let proposal = json!({"schema":"agentlab.source_recipe_author_proposal.v1","scopeSkillId":"scope-arbitrary",
        "sourcePaths":["src/state.json"],"verifierSource":"const fs=require('fs'),path=require('path');const n=JSON.parse(fs.readFileSync(path.join(process.argv[2],'src/state.json'))).value; console.log(JSON.stringify({value:process.argv[3]==='wrong'?0:n}));",
        "rationale":"Exercise actual source state and independent wrong output.","limitations":["No platform runtime","One scoped contract only"],
        "contract":{"checks":[{"id":"value","pointer":"/value","expected":1}],"controls":[
            {"id":"baseline","role":"baseline","expectedFailedCheckIds":[]},
            {"id":"reference","role":"reference","expectedFailedCheckIds":[]},
            {"id":"alternative","role":"reference","expectedFailedCheckIds":[]},
            {"id":"wrong","role":"wrong","expectedFailedCheckIds":["value"]}]}});
    let request_bytes = serde_json::to_vec(&request).unwrap();
    let proposal_bytes = serde_json::to_vec(&proposal).unwrap();
    let stage = dir.join("author-stage");
    for (index, checks) in [
        json!(["value"]),
        json!([{"id":"value","pointer":"/value"}]),
        json!([{"id":"value","pointer":"/value","expected":1,"pass":true}]),
    ]
    .into_iter()
    .enumerate()
    {
        let mut invalid = proposal.clone();
        invalid["contract"]["checks"] = checks;
        let rejected_stage = dir.join(format!("invalid-check-stage-{index}"));
        let error = author::stage(
            &request_bytes,
            &serde_json::to_vec(&invalid).unwrap(),
            &rejected_stage,
        )
        .unwrap_err();
        assert!(
            error.contains("exactly id, pointer and expected"),
            "{error}"
        );
        assert!(!rejected_stage.exists());
    }
    let receipt = author::stage(&request_bytes, &proposal_bytes, &stage).unwrap();
    assert_eq!(receipt["executionPerformed"], false);
    let unreviewed = fs::read(stage.join("unreviewed-recipe.json")).unwrap();
    let before = fs::read(dir.join("knowledge/assessments/before.json")).unwrap();
    assert!(execute(
        &dir.join("knowledge/maintainer_scope_skills.jsonl"),
        &dir.join("knowledge/program_facts.jsonl"),
        &dir.join("knowledge/operation-evidence"),
        &before,
        &unreviewed,
        &dir.join("source"),
        &dir.join("untrusted-execution")
    )
    .is_err());
    assert!(!dir.join("untrusted-execution").exists());
    assert!(author::approve(
        &stage,
        &digest(&proposal_bytes),
        false,
        &dir.join("not-reviewed.json")
    )
    .is_err());
    assert!(author::approve(
        &stage,
        &"0".repeat(64),
        true,
        &dir.join("wrong-review.json")
    )
    .is_err());
    author::approve(
        &stage,
        &digest(&proposal_bytes),
        true,
        &dir.join("reviewed.json"),
    )
    .unwrap();
    let reviewed = fs::read(dir.join("reviewed.json")).unwrap();
    execute(
        &dir.join("knowledge/maintainer_scope_skills.jsonl"),
        &dir.join("knowledge/program_facts.jsonl"),
        &dir.join("knowledge/operation-evidence"),
        &before,
        &reviewed,
        &dir.join("source"),
        &dir.join("authored-capture"),
    )
    .unwrap();
    let execution = fs::read(dir.join("authored-capture/execution-receipt.json")).unwrap();
    qualify(&dir.join("authored-capture"), &digest(&execution)).unwrap();
    assert!(author::stage(&request_bytes, &proposal_bytes, &stage).is_err());
    fs::write(stage.join("controls.cjs"), b"tampered").unwrap();
    assert!(author::approve(
        &stage,
        &digest(&proposal_bytes),
        true,
        &dir.join("changed-method.json")
    )
    .is_err());
    let mut bad = proposal.clone();
    bad["sourcePaths"] = json!(["src/unloaded.json"]);
    assert!(author::stage(
        &request_bytes,
        &serde_json::to_vec(&bad).unwrap(),
        &dir.join("unloaded-stage")
    )
    .is_err());
    assert!(!dir.join("unloaded-stage").exists());
    bad = proposal.clone();
    bad["sourcePaths"] = json!(["other/state.json"]);
    assert!(author::stage(
        &request_bytes,
        &serde_json::to_vec(&bad).unwrap(),
        &dir.join("unowned-stage")
    )
    .is_err());
    assert!(!dir.join("unowned-stage").exists());
    let mut bad = request.clone();
    bad["sourceFiles"][0]["content"] = json!("forged");
    assert!(author::stage(
        &serde_json::to_vec(&bad).unwrap(),
        &proposal_bytes,
        &dir.join("forged-stage")
    )
    .is_err());
    assert!(!dir.join("forged-stage").exists());
    assert_eq!(catalog["repositorySelector"], "arbitrary");
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn reviewed_loop_replans_distinct_scopes_and_retains_portable_parent_chain() {
    let (dir, catalog) = loop_fixture();
    let output = dir.join("loop");
    let report = agentlab_code_analysis::maintainer_source_operation_loop::execute(
        &dir.join("knowledge"),
        &serde_json::to_vec(&catalog).unwrap(),
        3,
        &output,
    )
    .unwrap();
    assert_eq!(report["productiveOperationRounds"], 2);
    assert_eq!(report["status"], "review-required");
    assert_ne!(
        report["rounds"][0]["scopeSkillId"],
        report["rounds"][1]["scopeSkillId"]
    );
    assert_eq!(
        report["rounds"][1]["beforeAssessmentSha256"],
        report["rounds"][0]["afterAssessmentSha256"]
    );
    assert_eq!(report["rounds"][1]["after"]["maintenanceReadyCount"], 2);
    assert_eq!(report["authorityWritePerformed"], false);
    assert_eq!(report["closedLoopQualified"], false);
    let final_cut = PathBuf::from(report["finalCandidateSnapshot"].as_str().unwrap());
    let latest =
        agentlab_code_analysis::maintainer_flywheel_plan::latest_assessment(&final_cut).unwrap();
    let recorded: Value =
        serde_json::from_slice(&fs::read(latest["assessmentPath"].as_str().unwrap()).unwrap())
            .unwrap();
    fs::remove_dir_all(output.join("iteration-1")).unwrap();
    fs::remove_dir_all(dir.join("source")).unwrap();
    let reproduced = assess_with_receipts(
        &final_cut.join("maintainer_scope_skills.jsonl"),
        Some(&final_cut.join("program_facts.jsonl")),
        recorded["roundIndex"].as_u64().unwrap(),
        recorded["parentAssessmentSha256"].as_str(),
        Some(&final_cut.join("operation-evidence")),
    )
    .unwrap();
    assert_eq!(recorded, reproduced);
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn reviewed_loop_refuses_drift_and_missing_selected_recipe_without_substitution() {
    let (dir, mut catalog) = loop_fixture();
    let original_catalog = catalog.clone();
    let execute = |catalog: &Value, name: &str| {
        agentlab_code_analysis::maintainer_source_operation_loop::execute(
            &dir.join("knowledge"),
            &serde_json::to_vec(catalog).unwrap(),
            2,
            &dir.join(name),
        )
    };
    let mut bad = catalog.clone();
    bad["reviewed"] = json!(false);
    assert!(execute(&bad, "unreviewed").is_err());
    assert!(!dir.join("unreviewed").exists());
    bad = catalog.clone();
    bad["knowledgeCutSha256"] = json!("0".repeat(64));
    assert!(execute(&bad, "stale-cut").is_err());
    assert!(!dir.join("stale-cut").exists());
    bad = catalog.clone();
    bad["entries"][0]["recipe"]["sha256"] = json!("0".repeat(64));
    assert!(execute(&bad, "stale-recipe").is_err());
    assert!(!dir.join("stale-recipe").exists());
    // Even when another scope has a reviewed recipe, it cannot replace the
    // deterministic selected gap. Keep that scope and missing recipe visible.
    catalog["entries"] = json!([catalog["entries"][1].clone()]);
    let stopped = execute(&catalog, "missing").unwrap();
    assert_eq!(stopped["status"], "review-required");
    assert_eq!(stopped["productiveOperationRounds"], 0);
    assert_eq!(
        stopped["gap"]["code"],
        "selected-source-operation-recipe-required"
    );
    assert!(!dir.join("missing/iteration-1/capture").exists());
    assert!(execute(&catalog, "missing").is_err());
    catalog = original_catalog.clone();
    catalog["entries"] = json!([catalog["entries"][0].clone()]);
    let partial = execute(&catalog, "partial").unwrap();
    assert_eq!(partial["productiveOperationRounds"], 1);
    assert_eq!(partial["status"], "review-required");
    assert!(!dir.join("partial/iteration-2/capture").exists());
    assert_eq!(partial["authorityWritePerformed"], false);
    catalog = original_catalog;
    let recipe_path = PathBuf::from(catalog["entries"][0]["recipe"]["path"].as_str().unwrap());
    let mut recipe: Value = serde_json::from_slice(&fs::read(&recipe_path).unwrap()).unwrap();
    recipe["controls"][1]["command"]["args"][2] = json!("error");
    let bytes = serde_json::to_vec_pretty(&recipe).unwrap();
    fs::write(&recipe_path, &bytes).unwrap();
    catalog["entries"][0]["recipe"]["sha256"] = json!(digest(&bytes));
    let failed = execute(&catalog, "failed-loop").unwrap();
    assert_eq!(failed["status"], "failed");
    assert_eq!(failed["productiveOperationRounds"], 0);
    assert_eq!(failed["finalCandidateSnapshot"], Value::Null);
    assert_eq!(
        fs::read(dir.join("failed-loop/iteration-1/capture/reference.stderr")).unwrap(),
        b"original-error\n"
    );
    assert!(dir.join("failed-loop/loop-receipt.json").is_file());
    fs::remove_dir_all(dir).unwrap();
}
