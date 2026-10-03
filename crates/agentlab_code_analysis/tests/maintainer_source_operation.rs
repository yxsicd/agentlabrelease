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
fn frozen_runtime_preserves_module_bindings_and_refuses_implicit_imports() {
    let (dir, _) = loop_fixture();
    let recipe: Value =
        serde_json::from_slice(&fs::read(dir.join("recipe-0.json")).unwrap()).unwrap();
    let node = recipe["controls"][0]["command"]["program"]
        .as_str()
        .unwrap();
    let source_root = dir.join("runtime-source");
    fs::create_dir(&source_root).unwrap();
    let compiler_path = std::env::var("AGENTLAB_RUNTIME_TEST_COMPILER").unwrap_or_default();
    let source = if compiler_path.is_empty() {
        "const seam=require('explicit-seam'); let count=0; exports.run=()=>({count:++count, value:seam.fetch()});"
    } else {
        "import * as seam from 'explicit-seam'; let count:number=0; export function run(){return {count:++count, value:seam.fetch()};}"
    };
    fs::write(source_root.join("unit.ts"), source).unwrap();
    let manifest = json!({"files":[{"path":"unit.ts","sha256":digest(source.as_bytes()),"content":source}],
        "controls":[{"id":"baseline","edits":[]},{"id":"wrong","edits":[{"path":"unit.ts","before":"seam.fetch()","after":"'$&'"}]}]});
    let runtime = dir.join("runtime.cjs");
    fs::write(
        &runtime,
        format!(
            "const manifest={manifest};\n{}",
            include_str!("../src/source_design_runtime.cjs")
        ),
    )
    .unwrap();
    // Identity compiler double isolates CommonJS plumbing; real compiler qualification
    // is a separate experiment, not inferred from this fixture.
    let script = r#"
const assert=require('assert');
const compiler=process.argv[3] ? require(process.argv[3]) :
 {ScriptTarget:{ES2020:1},ScriptKind:{TS:1},ModuleKind:{CommonJS:1},DiagnosticCategory:{Error:1},
 createSourceFile:()=>({parseDiagnostics:[]}),transpileModule:t=>({outputText:t,diagnostics:[]})};
const runtime=require(process.argv[1])(process.argv[2],'baseline',compiler);
let calls=0;const seams={'explicit-seam':{fetch(){calls++;return 7}}};
const a=runtime.loadModule('unit.ts',seams),b=runtime.loadModule('unit.ts',seams);
assert.equal(a.run().count,1);assert.equal(a.run().count,2);assert.equal(b.run().count,1);assert.equal(calls,3);
assert.throws(()=>runtime.loadModule('unit.ts',{}),/unbound import/);
assert.throws(()=>runtime.loadModule('unit.ts',seams,{exports:{}}),/reserved module binding/);
const wrong=require(process.argv[1])(process.argv[2],'wrong',compiler);
assert.equal(wrong.loadModule('unit.ts',seams).run().value,'$&');assert.equal(calls,3);
console.log('module-plumbing-pass');
"#;
    let result = Command::new(node)
        .arg("-e")
        .arg(script)
        .arg(&runtime)
        .arg(&source_root)
        .arg(&compiler_path)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&result.stdout).trim(),
        "module-plumbing-pass"
    );
}

#[test]
fn contained_pi_turns_preserve_history_and_refuse_missing_or_replaced_sessions() {
    let code = r#"
import importlib.util, json, os, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('participant',os.environ['PARTICIPANT_SCRIPT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);state=root/'state';state.mkdir();evidence=root/'evidence';evidence.mkdir()
    workspace=root/'workspace';workspace.mkdir()
    p=module.Participant.__new__(module.Participant)
    p.state=state;p.evidence=evidence;p.binary='/synthetic/pi';p.model='fixture'
    p.implementation='pi';p.reasoning_effort=None;p.server=SimpleNamespace(server_port=12345)
    observed=[]
    def run(command,project,env,label,lifecycle,**options):
        # Reproduce pinned Pi startup migration of agent-root JSONL files.
        for old in state.glob('*.jsonl'):
            target=state/'sessions/--workspace--'/old.name;target.parent.mkdir(parents=True,exist_ok=True)
            old.rename(target)
        path=Path(command[command.index('--session')+1])
        old=path.read_bytes() if path.exists() else b''
        observed.append(old)
        header={'type':'session','id':'stable-session','cwd':'/workspace'}
        if not old: old=(json.dumps(header)+'\n').encode()
        path.write_bytes(old+(json.dumps({'type':'message','message':{'role':'user','content':command[-1]}})+'\n').encode())
        (evidence/f'{label}-events.jsonl').write_text(json.dumps(header)+'\n')
        return {'complete':True}
    p._run_turn=run
    with patch.dict(os.environ,{'AGENTLAB_PARTICIPANT_RUNTIME_CONFIG':'synthetic',
        'AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT':str(root/'receipts'),'DOCKER_CONFIG':str(root/'docker')}):
        p.turn('first',workspace,prompt='pinned-source-context',require_completed_tool_call=False,transport_retry_limit=0)
        p.turn('correction',workspace,prompt='exact-validator-feedback',require_completed_tool_call=False,transport_retry_limit=0)
        assert b'pinned-source-context' in observed[1]
        path=state/'sessions/operator/pi-session.jsonl'
        original=path.read_bytes()
        receipt=json.loads((evidence/'correction-lifecycle.json').read_bytes())['sessionContinuity']
        assert receipt['qualified'] and receipt['sessionIdBefore']==receipt['sessionIdAfter']=='stable-session'
        for damage in ['missing','identity']:
            if damage=='missing':path.unlink()
            else:path.write_text(json.dumps({'type':'session','id':'replacement'})+'\n')
            try:p.turn(damage,workspace,prompt='must-not-dispatch',transport_retry_limit=0)
            except RuntimeError as error:assert 'before dispatch' in str(error)
            else:raise AssertionError('damaged history dispatched')
            assert len(observed)==2
            path.write_bytes(original)
        def reset(*args,**kwargs):
            path.write_text(json.dumps({'type':'session','id':'replacement'})+'\n')
            (evidence/'reset-events.jsonl').write_text(json.dumps({'type':'session','id':'replacement'})+'\n')
        p._run_turn=reset
        try:p.turn('reset',workspace,prompt='feedback',transport_retry_limit=0)
        except RuntimeError as error:assert 'continuity failed' in str(error)
        else:raise AssertionError('silent session reset qualified')
        assert not json.loads((evidence/'reset-lifecycle.json').read_bytes())['sessionContinuity']['qualified']
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

#[test]
fn constructor_native_retry_policy_rejects_drift_and_project_overrides() {
    let code = r#"
import importlib.util,json,os,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('author',os.environ['AUTHOR_SCRIPT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as d:
    root=Path(d);state=root/'state';workspace=root/'workspace';evidence=root/'evidence'
    workspace.mkdir();evidence.mkdir()
    raw=module.freeze_pi_retry_policy(state,workspace,evidence)
    assert json.loads(raw)=={'retry':{'enabled':False,'maxRetries':0,'provider':{'maxRetries':0}}}
    module.require_pi_retry_policy(state,workspace,raw)
    def refused():
        try:module.require_pi_retry_policy(state,workspace,raw)
        except ValueError:pass
        else:raise AssertionError('policy override accepted')
    (state/'settings.json').write_text('{"retry":{"enabled":true}}');refused()
    (state/'settings.json').write_bytes(raw)
    (workspace/'.pi').mkdir();override=workspace/'.pi/settings.json'
    override.write_text('{"retry":{"provider":{"maxRetries":3}}}');refused()
    override.unlink();override.symlink_to(root/'absent');refused()
    override.unlink()
    try:module.freeze_pi_retry_policy(state,workspace,evidence)
    except FileExistsError:pass
    else:raise AssertionError('existing configuration overwritten')
    assert (state/'settings.json').read_bytes()==raw
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
fn bounded_design_correction_retains_failures_and_stops_on_drift_or_partial_transport() {
    let code = r#"
import importlib.util,json,os,subprocess,tempfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('author',os.environ['AUTHOR_SCRIPT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Participant:
    def __init__(self,evidence,complete=True,stop='stop',oversized=False):self.evidence=evidence;self.labels=[];self.complete=complete;self.stop=stop;self.oversized=oversized
    def turn(self,label,workspace,**options):
        self.labels.append(label)
        assert options['transport_retry_limit']==0 and options['tool_call_limit']==1
        gateway=self.evidence/'gateway';gateway.mkdir(exist_ok=True)
        (gateway/f'{len(self.labels):04d}.status.json').write_text(json.dumps(dict(status=200,
            outcome='completed' if self.complete else 'incomplete_stream',semanticComplete=self.complete,
            upstreamEof=self.complete,streamError=None,clientDisconnected=False)))
        return {'content':'x'*65537 if self.oversized else json.dumps({'schema':'agentlab.source_recipe_design.v1' if scenario=='legacy' else 'agentlab.source_recipe_design.v2','iteration':len(self.labels)}),'message':{'stopReason':self.stop}}
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    for scenario in ['recover','exhaust','drift','partial','truncated','oversized','legacy']:
        output=root/scenario;output.mkdir();evidence=output/'evidence';evidence.mkdir()
        participant=Participant(evidence,complete=scenario!='partial',stop='length' if scenario=='truncated' else 'stop',oversized=scenario=='oversized')
        commands=[]
        def gate(command,**kwargs):
            commands.append(command)
            if scenario=='recover' and len(commands)==2:
                Path(command[command.index('--output')+1]).write_text('{"semanticQualified":false}')
                return subprocess.CompletedProcess(command,0,b'',b'')
            error='recipe design request no longer reproduces' if scenario=='drift' else 'recipe design edit in control ref at arbitrary/source must match exactly once; observed 0'
            return subprocess.CompletedProcess(command,1,b'',('Error: '+json.dumps(error)).encode())
        with patch.object(module.subprocess,'run',side_effect=gate):
            try:
                selected,content=module.construct_design(participant,output,evidence,output,root/'request.json',Path('/fixture/gate'),'original bounded prompt','none',1)
            except ValueError:
                assert scenario!='recover'
            else:
                assert scenario=='recover'
                assert selected.read_text()==content and json.loads(content)['iteration']==2
        expected=2 if scenario in ('recover','exhaust','legacy') else 1
        assert len(participant.labels)==expected
        assert len(commands)==(0 if scenario in ('partial','truncated','oversized','legacy') else expected)
        assert not (output/'design.json').exists() or scenario=='recover'
        if scenario not in ('partial','truncated','oversized'):
            report=json.loads((output/'design-attempts.json').read_bytes())
            assert len(report['attempts'])==expected and report['attempts'][0]['accepted'] is False
            assert (output/'design-attempt-0.json').exists()
            if scenario=='recover':assert report['attempts'][1]['accepted'] is True
        assert 'source-recipe-author' not in participant.labels
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
    revision_path = root/'revision.json'
    revision_packet = {'parentProposalOriginal':json.dumps({'scopeSkillId':'arbitrary-scope'}),
                       'reviewOriginal':json.dumps({'findings':[{'id':'grounded-feedback'}]})}
    revision_path.write_text(json.dumps(revision_packet))
    parent_design=root/'parent-design.json'
    parent_design.write_text('{"schema":"agentlab.source_recipe_design.v2"}')
    design_feedback=root/'design-feedback.json'
    design_feedback.write_text('{"findings":[{"id":"grounded-design-review"}]}')
    for index, extra, effort, deadline, thinking in [(0, [], 'low', 180, None),
        (1, ['--reasoning-effort','high','--gateway-timeout-seconds','120'], 'high',120,None),
        (2, ['--reasoning-effort','default'], None,180,None),
        (3, ['--reasoning-effort','default','--thinking-type','disabled','--response-format','json-object'],None,180,'disabled'),
        (4, ['--api','openai-responses','--reasoning-effort','none','--response-format','json-object'],'none',180,None),
        (5, ['--revision-request',str(revision_path)],'low',180,None),
        (6, ['--design-first'],'low',180,None),
        (7, ['--max-output-tokens','8192'],'low',180,None),
        (8, ['--design-first','--design-only'],'low',180,None),
        (9, ['--design-first','--design-only','--parent-design',str(parent_design),
             '--design-review-feedback',str(design_feedback)],'low',180,None)]:
        seen = {}
        class FakeParticipant:
            def __init__(self, evidence, state, binary, gateway, model, **options):
                seen['constructor'] = options
                self.evidence = evidence
            def turn(self, label, workspace, **options):
                policy=json.loads((workspace.parent/'participant-state/settings.json').read_bytes())
                assert policy['retry']['enabled'] is False
                assert policy['retry']['maxRetries']==0 and policy['retry']['provider']['maxRetries']==0
                seen['turn'] = options
                seen.setdefault('labels',[]).append(label)
                gateway = self.evidence/'gateway'
                gateway.mkdir(exist_ok=True)
                (gateway/f'{len(seen["labels"]):04d}.status.json').write_text(json.dumps(dict(status=200,
                    outcome='completed',semanticComplete=True,upstreamEof=True,
                    streamError=None,clientDisconnected=False)))
                content=json.dumps({'schema':'agentlab.source_recipe_design.v2'}) if label.startswith('source-recipe-design') else '{}'
                return {'content':content,'message':{'stopReason':'stop'}}
            def close(self): seen['closed'] = True
        fake_spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _:None))
        env = dict(AGENTLAB_PARTICIPANT_RUNTIME_CONFIG=str(root/'config.json'),
            AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT=str(root/'receipts'),
            AGENTLAB_LM_GATEWAY_URL='https://gateway.invalid',AGENTLAB_MODEL='arbitrary',
            AGENTLAB_PROVIDER_ROUTE='arbitrary')
        argv = ['author','--request',str(request),'--output',str(root/str(index)),
                '--gate','/unexecuted-fixture-gate','--pi','/unexecuted-fixture-pi',*extra]
        def successful_gate(command,**_):
            if '--validate-source-recipe-design' in command:
                Path(command[command.index('--output')+1]).write_text('{"semanticQualified":false}')
            return subprocess.CompletedProcess([],0,b'',b'')
        with patch.dict(os.environ,env), patch.object(sys,'argv',argv), \
             patch.object(module.importlib.util,'spec_from_file_location',return_value=fake_spec), \
             patch.object(module.importlib.util,'module_from_spec',return_value=SimpleNamespace(Participant=FakeParticipant)), \
             patch.object(module.subprocess,'run',side_effect=successful_gate) as stage:
            module.main()
        assert seen['constructor']['gateway_timeout_seconds'] == deadline
        assert seen['constructor']['max_output_tokens']==(8192 if index==7 else 16384)
        assert seen['constructor']['thinking_type'] == thinking
        assert seen['constructor']['response_format'] == ('json_object' if index in (3,4) else None)
        assert seen['constructor']['api'] == ('openai-responses' if index==4 else 'openai-completions')
        assert seen['turn']['reasoning_effort'] == effort
        assert seen['turn']['transport_retry_limit'] == 0
        assert seen['closed'] is True
        assert stage.call_count == (2 if index in (5,6,9) else 1)
        if index in (8,9):
            assert seen['labels']==['source-recipe-design']
            receipt=json.loads((root/str(index)/'design-capture.json').read_bytes())
            assert receipt['reviewRequired'] is True and receipt['semanticQualified'] is False
            assert receipt['verifierGenerationPerformed'] is False
            assert receipt['executionPerformed'] is False
            assert not (root/str(index)/'proposal.json').exists()
            assert '--validate-source-recipe-design' in stage.call_args[0][0]
            if index==9:
                assert '--validate-source-design-review' in stage.call_args_list[0][0][0]
                assert 'grounded-design-review' in seen['turn']['prompt']
                assert json.loads((root/str(index)/'parent-design.json').read_bytes())==json.loads(parent_design.read_bytes())
            continue
        if index==6:
            assert seen['labels']==['source-recipe-design','source-recipe-author']
            assert '--validate-source-recipe-design' in stage.call_args_list[0][0][0]
            assert '--design' in stage.call_args[0][0]
            assert (root/str(index)/'evidence/design-0-generation-completion.json').exists()
        if index==5:
            assert '--check-source-recipe-revision' in stage.call_args_list[0][0][0]
            assert json.loads((root/str(index)/'revision-request.json').read_bytes()) == revision_packet
        assert '--stage-source-recipe-proposal' in stage.call_args[0][0]
        assert json.loads((root/str(index)/'proposal.json').read_bytes()) == {}
    argv = ['author','--request',str(request),'--output',str(root/'invalid-design-only'),
            '--gate','/unexecuted-fixture-gate','--pi','/unexecuted-fixture-pi','--design-only']
    with patch.object(sys,'argv',argv), patch.object(module.importlib.util,'spec_from_file_location') as dispatch:
        try: module.main()
        except SystemExit as failure: assert failure.code==2
        else: raise AssertionError('Unpaired design-only dispatch was accepted')
        dispatch.assert_not_called()
        assert not (root/'invalid-design-only').exists()
    argv = ['author','--request',str(request),'--output',str(root/'rejected-revision'),
            '--gate','/unexecuted-fixture-gate','--pi','/unexecuted-fixture-pi',
            '--revision-request',str(revision_path)]
    failure = subprocess.CompletedProcess([],1,b'',b'revision context drift')
    with patch.dict(os.environ,env), patch.object(sys,'argv',argv), \
         patch.object(module.subprocess,'run',return_value=failure), \
         patch.object(module.importlib.util,'spec_from_file_location') as dispatch:
        try: module.main()
        except subprocess.CalledProcessError: pass
        else: raise AssertionError('rejected revision dispatched')
        dispatch.assert_not_called()
    assert not (root/'rejected-revision/proposal.json').exists()
    argv = ['author','--request',str(request),'--output',str(root/'rejected-design'),
            '--gate','/unexecuted-fixture-gate','--pi','/unexecuted-fixture-pi','--design-first']
    with patch.dict(os.environ,env), patch.object(sys,'argv',argv), \
         patch.object(module.importlib.util,'spec_from_file_location',return_value=fake_spec), \
         patch.object(module.importlib.util,'module_from_spec',return_value=SimpleNamespace(Participant=FakeParticipant)), \
         patch.object(module.subprocess,'run',return_value=failure):
        seen={}
        try: module.main()
        except (subprocess.CalledProcessError,ValueError): pass
        else: raise AssertionError('rejected design continued')
        assert seen['labels']==['source-recipe-design'] and seen['closed'] is True
    assert not (root/'rejected-design/proposal.json').exists()
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
                f'http://127.0.0.1:{server.server_port}','arbitrary-model',thinking_type=thinking,
                response_format='json_object' if index==2 else None)
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
            if index==2: assert actual['response_format'] == {'type':'json_object'}
            else: assert 'response_format' not in actual
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

#[test]
fn explicit_output_budget_reaches_wire_and_preserves_shared_defaults() {
    let code = r#"
import http.server, importlib.util, json, os, tempfile, threading, urllib.request
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('participant',os.environ['PARTICIPANT_SCRIPT'])
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
received=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        body=b'data: [DONE]\n\n'
        self.send_response(200); self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
try:
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'AGENTLAB_LM_GATEWAY_KEY':'synthetic-only'}):
        root=Path(directory)
        for api in ('openai-completions','openai-responses'):
            for limit in (None,8192,16384):
                evidence=root/f'{api}-{limit}'; evidence.mkdir()
                p=module.Participant(evidence,evidence/'state','/bin/true',
                    f'http://127.0.0.1:{server.server_port}','arbitrary-model',api=api,max_output_tokens=limit)
                try:
                    models=json.loads((evidence/'state/models.json').read_bytes())
                    assert models['providers']['agentlab-ci']['models'][0]['maxTokens']==(limit or 8192)
                    receipt=json.loads((evidence/'participant.json').read_bytes())
                    assert receipt['providerMaxOutputTokens']==limit
                    payload={'model':'ignored','stream':True,'max_tokens':11,'max_completion_tokens':12,'max_output_tokens':13}
                    req=urllib.request.Request(f'http://127.0.0.1:{p.server.server_port}'+p.api_path,
                        data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+p.local_proxy_token})
                    with urllib.request.urlopen(req,timeout=5) as response: response.read()
                    actual=json.loads((evidence/'gateway/0001.upstream-request.json').read_bytes())
                    assert actual==received[-1]
                    fields={k:v for k,v in actual.items() if k in ('max_tokens','max_completion_tokens','max_output_tokens')}
                    expected={k:v for k,v in payload.items() if k.startswith('max_')} if limit is None else {
                        'max_output_tokens' if api=='openai-responses' else 'max_tokens':limit}
                    assert fields==expected,(fields,expected)
                finally: p.close()
        for invalid in (True,False,0,8192.0,'16384',8193,32768):
            try:module.Participant(root,root/'invalid','/bin/true','http://localhost','arbitrary',max_output_tokens=invalid)
            except ValueError:pass
            else:raise AssertionError('invalid token policy accepted')
finally:
    server.shutdown(); server.server_close(); thread.join()
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

#[test]
fn native_responses_preserves_wire_isolation_and_rejects_incomplete_or_rate_limited_streams() {
    let code = r#"
import http.server, importlib.util, json, os, tempfile, threading, urllib.request, urllib.error
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('participant',os.environ['PARTICIPANT_SCRIPT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
terminal = {}
received = []
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        received.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
        body=('data: '+json.dumps(terminal)+'\n\ndata: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
cases=[({'type':'response.completed','response':{'status':'completed'}},True,'completed'),
       ({'type':'response.incomplete','response':{'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}}},False,'stream_error'),
       ({'type':'error','error':{'code':'rate_limit_exceeded'}},False,'stream_error'),
       ({'type':'response.failed','response':{'status':'failed','error':{'code':'failed'}}},False,'stream_error'),
       ({'type':'response.created','response':{'status':'in_progress'}},False,'incomplete_stream'),
       ({'type':'response.completed','response':{'status':'incomplete'}},False,'incomplete_stream')]
try:
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        for index,(terminal,complete,outcome) in enumerate(cases):
            evidence=root/str(index);evidence.mkdir()
            with patch.dict(os.environ,{'AGENTLAB_LM_GATEWAY_KEY':'synthetic-external-key',
                'AGENTLAB_PARTICIPANT_RUNTIME_CONFIG':str(root/'config.json')}):
                p=module.Participant(evidence,root/f'state-{index}','/bin/true',
                    f'http://127.0.0.1:{server.server_port}','arbitrary',api='openai-responses',
                    reasoning_effort='none',response_format='json_object')
            try:
                headers={'Authorization':'Bearer '+p.local_proxy_token}
                wrong=urllib.request.Request(f'http://127.0.0.1:{p.server.server_port}/v1/chat/completions',data=b'{}',headers=headers)
                try: urllib.request.urlopen(wrong,timeout=5)
                except urllib.error.HTTPError as error:
                    assert error.code==404;error.close()
                else: raise AssertionError('cross-protocol isolated route admitted')
                body={'input':'exact input','stream':True,'reasoning':{'summary':'auto'},'text':{'verbosity':'low'}}
                request=urllib.request.Request(f'http://127.0.0.1:{p.server.server_port}/v1/responses',data=json.dumps(body).encode(),headers=headers)
                with urllib.request.urlopen(request,timeout=5) as response: response.read()
            finally:p.close()
            assert received[-1][0]=='/v1/responses'
            wire=received[-1][1]
            assert wire['input']=='exact input' and wire['reasoning']=={'summary':'auto','effort':'none'}
            assert wire['text']=={'verbosity':'low','format':{'type':'json_object'}}
            assert 'reasoning_effort' not in wire and 'response_format' not in wire
            receipt=json.loads((evidence/'gateway/0001.status.json').read_bytes())
            assert receipt['upstreamEof'] is True
            assert receipt['semanticComplete']==complete and receipt['outcome']==outcome,receipt
            models=json.loads((root/f'state-{index}/models.json').read_bytes())
            assert models['providers']['agentlab-ci']['api']=='openai-responses'
            assert models['providers']['agentlab-ci']['apiKey']!='synthetic-external-key'
        for options in [{'api':'invented'},{'api':'openai-responses','thinking_type':'disabled'},
                        {'api':'openai-responses','implementation':'mini-swe-agent'}]:
            try:module.Participant(root,root/'invalid','/bin/true','http://localhost','arbitrary',**options)
            except ValueError:pass
            else:raise AssertionError('unsupported API policy accepted')
finally:server.shutdown();server.server_close();thread.join()
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
    loop_fixture_with_source_context(extra.then_some(b"{\"metadata\":true}".as_slice()))
}

fn loop_fixture_with_source_context(context: Option<&[u8]>) -> (PathBuf, Value) {
    let extra = context.is_some();
    let (dir, mut first, _, mut recipe) = fixture();
    let source = dir.join("source");
    fs::create_dir(source.join("other")).unwrap();
    fs::write(source.join("other/state.json"), b"{\"value\":1}").unwrap();
    if let Some(bytes) = context {
        fs::write(source.join("src/unloaded.json"), bytes).unwrap();
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
fn source_author_context_keeps_large_scopes_bounded_and_binary_files_unloaded() {
    for bytes in [vec![b'x'; 129 * 1024], vec![0xff, 0xfe]] {
        let (dir, _) = loop_fixture_with_source_context(Some(&bytes));
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
        let request = agentlab_code_analysis::maintainer_source_recipe_author::prepare(
            &dir.join("knowledge"),
            &dir.join("source"),
            "arbitrary",
            &serde_json::to_vec(&policy).unwrap(),
        )
        .unwrap();
        assert!(request["sourceFiles"][0]["content"].is_string());
        assert!(request["sourceFiles"][1]["content"].is_null());
        assert_eq!(request["sourceFiles"][1]["sha256"], digest(&bytes));
        assert_eq!(request["reviewed"], false);
        assert_eq!(request["closedLoopQualified"], false);
        fs::remove_dir_all(dir).unwrap();
    }
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
    assert_eq!(request["sourceFiles"][1]["content"], "{\"metadata\":true}");
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
    let body = request["sourceFiles"][0]["content"].as_str().unwrap();
    let design = json!({"schema":"agentlab.source_recipe_design.v1","scopeSkillId":"scope-arbitrary",
        "invariant":"Preserve the selected state value.","limitations":["No runtime proof","No semantic approval"],
        "scenarios":[{"id":"state","initialState":{"value":1},"inputs":{"operation":"read"},"expectedObservations":{"value":1}}],
        "checks":[{"id":"value","pointer":"/state/value","expected":1}],
        "controls":[
            {"id":"baseline","role":"baseline","expectedFailedCheckIds":[],"edits":[]},
            {"id":"reference","role":"reference","expectedFailedCheckIds":[],"edits":[{"path":"src/state.json","before":body,"after":format!("{body}\n")}]},
            {"id":"alternative","role":"reference","expectedFailedCheckIds":[],"edits":[{"path":"src/state.json","before":body,"after":format!("{body}\t")}]},
            {"id":"wrong","role":"wrong","expectedFailedCheckIds":["value"],"edits":[{"path":"src/state.json","before":body,"after":"{\"value\":0}"}]}]});
    let design_bytes = serde_json::to_vec(&design).unwrap();
    let checked = author::design(&request_bytes, &design_bytes).unwrap();
    // Control IDs share the executor grammar; scenario/check identifiers do not.
    for id in [
        "".to_owned(),
        "ref_bad".into(),
        "ref/bad".into(),
        "ref bad".into(),
        "参考".into(),
        "a".repeat(65),
    ] {
        let mut invalid = design.clone();
        invalid["controls"][1]["id"] = json!(id);
        assert!(author::design(&request_bytes, &serde_json::to_vec(&invalid).unwrap()).is_err());
        let mut invalid = proposal.clone();
        invalid["contract"]["controls"][1]["id"] = json!(id);
        let output = dir.join("invalid-id-stage");
        assert!(author::stage(
            &request_bytes,
            &serde_json::to_vec(&invalid).unwrap(),
            &output
        )
        .is_err());
        assert!(!output.exists());
    }
    for id in ["A1-valid".to_owned(), "a".repeat(64)] {
        let mut valid = design.clone();
        valid["controls"][1]["id"] = json!(id);
        assert!(author::design(&request_bytes, &serde_json::to_vec(&valid).unwrap()).is_ok());
        let mut valid = proposal.clone();
        valid["contract"]["controls"][1]["id"] = json!(id);
        author::stage(
            &request_bytes,
            &serde_json::to_vec(&valid).unwrap(),
            &dir.join(format!("valid-id-{id}")),
        )
        .unwrap();
    }
    let mut flexible = design.clone();
    flexible["scenarios"][0]["id"] = json!("state_case");
    flexible["checks"][0]["id"] = json!("value_check");
    flexible["checks"][0]["pointer"] = json!("/state_case/value");
    flexible["controls"][3]["expectedFailedCheckIds"] = json!(["value_check"]);
    assert!(author::design(&request_bytes, &serde_json::to_vec(&flexible).unwrap()).is_ok());
    assert_eq!(checked["semanticQualified"], false);
    assert_eq!(checked["executionPerformed"], false);
    assert_eq!(checked["controls"][1]["edits"][0]["matchCount"], 1);
    let design_bytes = serde_json::to_vec(&design).unwrap();
    let review = json!({"schema":"agentlab.source_recipe_design_review.v1",
        "parentRequestSha256":digest(&request_bytes),"parentDesignSha256":digest(&design_bytes),
        "reviewed":true,"verdict":"revise","reviewer":"independent-fixture-review","automaticPromotion":false,
        "findings":[{"id":"source-shape","sourcePaths":["src/state.json"],
            "observed":"Draft needs an independent shape review.","requiredChange":"Match actual source return values."}]});
    let admission = author::design_review(
        &request_bytes,
        &design_bytes,
        &serde_json::to_vec(&review).unwrap(),
    )
    .unwrap();
    assert_eq!(admission["semanticQualified"], false);
    assert_eq!(admission["revisionRequested"], true);
    for field in [
        "parentRequestSha256",
        "parentDesignSha256",
        "reviewed",
        "verdict",
        "automaticPromotion",
    ] {
        let mut bad = review.clone();
        bad[field] = json!("forged");
        assert!(author::design_review(
            &request_bytes,
            &design_bytes,
            &serde_json::to_vec(&bad).unwrap()
        )
        .is_err());
    }
    for path in ["other/state.json", "src/missing.json", "../src/state.json"] {
        let mut bad = review.clone();
        bad["findings"][0]["sourcePaths"] = json!([path]);
        assert!(author::design_review(
            &request_bytes,
            &design_bytes,
            &serde_json::to_vec(&bad).unwrap()
        )
        .is_err());
    }
    let mut changed_request = request.clone();
    changed_request["source"]["revision"] = json!("0".repeat(40));
    assert!(author::design_review(
        &serde_json::to_vec(&changed_request).unwrap(),
        &design_bytes,
        &serde_json::to_vec(&review).unwrap()
    )
    .is_err());
    let mut seam_design = design.clone();
    seam_design["schema"] = json!("agentlab.source_recipe_design.v2");
    seam_design["scenarios"][0]["inputs"]["seams"] = json!({
        "independent": {"outcomes":[{"kind":"return","value":{"value":1}},
            {"kind":"resolve","value":2}],"repeatLast":true},
        "failure": {"outcomes":[{"kind":"throw","value":{"code":3}},
            {"kind":"reject","value":{"code":4}}],"repeatLast":false},
        "undefined": {"outcomes":[{"kind":"return-undefined"},
            {"kind":"resolve-undefined"}],"repeatLast":true}
    });
    let seam_design_bytes = serde_json::to_vec(&seam_design).unwrap();
    assert!(author::design(&request_bytes, &seam_design_bytes).is_ok());
    for index in 0..8 {
        let mut bad = seam_design.clone();
        match index {
            0 => bad["scenarios"][0]["inputs"]
                .as_object_mut()
                .unwrap()
                .remove("seams"),
            1 => Some(std::mem::replace(
                &mut bad["scenarios"][0]["inputs"]["seams"]["independent"]["repeatLast"],
                json!(1),
            )),
            2 => Some(std::mem::replace(
                &mut bad["scenarios"][0]["inputs"]["seams"]["independent"]["outcomes"],
                json!([]),
            )),
            3 => Some(std::mem::replace(
                &mut bad["scenarios"][0]["inputs"]["seams"]["independent"]["outcomes"][0],
                json!({"kind":"return"}),
            )),
            4 => Some(std::mem::replace(
                &mut bad["scenarios"][0]["inputs"]["seams"]["independent"]["outcomes"][0],
                json!({"kind":"mustNotBeCalled"}),
            )),
            5 => Some(std::mem::replace(
                &mut bad["scenarios"][0]["inputs"]["seams"]["undefined"]["outcomes"][0],
                json!({"kind":"return-undefined","value":null}),
            )),
            6 => Some(std::mem::replace(
                &mut bad["schema"],
                json!("agentlab.source_recipe_design.v3"),
            )),
            _ => Some(std::mem::replace(
                &mut bad["scenarios"][0]["inputs"]["seams"]["independent"],
                json!({"outcomes":[{"kind":"return","value":null}],"repeatLast":true,"expectedCallCount":0}),
            )),
        };
        assert!(
            author::design(&request_bytes, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "accepted ambiguous seam {index}"
        );
    }
    let mut seam_proposal = proposal.clone();
    seam_proposal["contract"]["checks"] = design["checks"].clone();
    let seam_stage = dir.join("seam-stage");
    author::stage_with_design(
        &request_bytes,
        &serde_json::to_vec(&seam_proposal).unwrap(),
        &seam_design_bytes,
        &seam_stage,
    )
    .unwrap();
    let seam_probe = r#"
const assert=require('assert');
const runtime=require(process.argv[1])(process.argv[2],'baseline',null);
(async()=>{
  const a=runtime.createSeams('state'), b=runtime.createSeams('state');
  const input={value:1}; const returned=a.functions.independent(input);
  returned.value=99; input.value=99;
  assert.deepStrictEqual(a.observations(),[{seam:'independent',args:[{value:1}]}]);
  assert.deepStrictEqual(b.functions.independent(),{value:1});
  assert.strictEqual(await a.functions.independent(),2);
  assert.strictEqual(await a.functions.independent(),2);
  assert.throws(()=>a.functions.failure(),e=>e.code===3);
  await assert.rejects(a.functions.failure(),e=>e.code===4);
  assert.throws(()=>a.functions.failure(),/exhausted/);
  assert.throws(()=>a.assertWithinBudget(),/exhausted/);
  assert.strictEqual(b.functions.undefined(),undefined);
  assert.strictEqual(await b.functions.undefined(),undefined);
  b.assertWithinBudget();
  assert.throws(()=>runtime.createSeams('unknown'),/unknown/);
  const circular={}; circular.self=circular;
  assert.throws(()=>b.functions.independent(circular));
  assert.throws(()=>b.assertWithinBudget(),/non-JSON/);
  const fresh=runtime.createSeams('state');
  for(let i=0;i<1024;i++) await fresh.functions.independent();
  assert.throws(()=>fresh.functions.independent(),/call budget/);
  assert.throws(()=>fresh.assertWithinBudget(),/call budget/);
})().catch(e=>{console.error(e);process.exitCode=1});
"#;
    let seam_result = Command::new(&node)
        .arg("-e")
        .arg(seam_probe)
        .arg(seam_stage.join("design-runtime.cjs"))
        .arg(dir.join("source"))
        .output()
        .unwrap();
    assert!(
        seam_result.status.success(),
        "{}",
        String::from_utf8_lossy(&seam_result.stderr)
    );
    assert_eq!(
        fs::read_to_string(dir.join("source/src/state.json")).unwrap(),
        body
    );
    for index in 0..9 {
        let mut bad = design.clone();
        match index {
            0 => bad["controls"][1]["edits"][0]["before"] = json!("nonexistent indentation"),
            1 => bad["controls"][1]["edits"][0]["before"] = json!("\""),
            2 => bad["controls"][1]["edits"][0]["after"] = json!(body),
            3 => bad["controls"][2]["edits"] = bad["controls"][1]["edits"].clone(),
            4 => bad["controls"][1]["edits"][0]["path"] = json!("src/unloaded.json"),
            5 => bad["controls"][1]["edits"][0]["path"] = json!("other/state.json"),
            6 => bad["checks"][0]["expected"] = json!(2),
            7 => bad["checks"][0]["pointer"] = json!("/state/value/length"),
            _ => bad["controls"][3]["expectedFailedCheckIds"] = json!([]),
        }
        assert!(
            author::design(&request_bytes, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "accepted bad design {index}"
        );
    }
    let designed_stage = dir.join("designed-stage");
    assert!(author::stage_with_design(
        &request_bytes,
        &proposal_bytes,
        &design_bytes,
        &designed_stage
    )
    .is_err());
    assert!(!designed_stage.exists());
    let mut designed_proposal = proposal.clone();
    designed_proposal["contract"]["checks"] = design["checks"].clone();
    author::stage_with_design(
        &request_bytes,
        &serde_json::to_vec(&designed_proposal).unwrap(),
        &design_bytes,
        &designed_stage,
    )
    .unwrap();
    assert_eq!(
        fs::read(designed_stage.join("design.json")).unwrap(),
        design_bytes
    );
    // The generic helper applies the frozen source edits, not Agent-recreated edits.
    let runtime_path = designed_stage.join("design-runtime.cjs");
    let runtime_bytes = fs::read(&runtime_path).unwrap();
    let run_runtime = |control: &str, script: &str| {
        Command::new(&node)
            .arg("-e")
            .arg(script)
            .arg(&runtime_path)
            .arg(dir.join("source"))
            .arg(control)
            .output()
            .unwrap()
    };
    let observe = "const r=require(process.argv[1])(process.argv[2],process.argv[3],null); console.log(JSON.parse(r.source('src/state.json')).value)";
    for (control, expected) in [
        ("baseline", "1"),
        ("reference", "1"),
        ("alternative", "1"),
        ("wrong", "0"),
    ] {
        let result = run_runtime(control, observe);
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(String::from_utf8_lossy(&result.stdout).trim(), expected);
    }
    assert!(!run_runtime("unknown", observe).status.success());
    assert!(!run_runtime("baseline", "require(process.argv[1])(process.argv[2],process.argv[3],null).source('src/unloaded.json')").status.success());
    assert_eq!(
        fs::read_to_string(dir.join("source/src/state.json")).unwrap(),
        body
    );
    fs::write(dir.join("source/src/state.json"), "{\"value\":2}").unwrap();
    assert!(!run_runtime("baseline", observe).status.success());
    fs::write(dir.join("source/src/state.json"), body).unwrap();
    fs::write(
        &runtime_path,
        b"module.exports=()=>({source:()=>'{\"value\":1}'})",
    )
    .unwrap();
    let tampered_runtime_output = dir.join("tampered-runtime-approval.json");
    assert!(author::approve(
        &designed_stage,
        &digest(&fs::read(designed_stage.join("proposal.json")).unwrap()),
        true,
        &tampered_runtime_output
    )
    .is_err());
    assert!(!tampered_runtime_output.exists());
    fs::write(&runtime_path, &runtime_bytes).unwrap();
    let validation_path = designed_stage.join("design-validation.json");
    let original_validation = fs::read(&validation_path).unwrap();
    let mut changed_validation = original_validation.clone();
    changed_validation.push(b' ');
    fs::write(&validation_path, &changed_validation).unwrap();
    let changed_output = dir.join("tampered-design-approval.json");
    assert!(author::approve(
        &designed_stage,
        &digest(&fs::read(designed_stage.join("proposal.json")).unwrap()),
        true,
        &changed_output
    )
    .is_err());
    assert!(!changed_output.exists());
    fs::write(&validation_path, &original_validation).unwrap();
    let feedback = json!({"schema":"agentlab.source_recipe_review_feedback.v1",
        "parentRequestSha256":digest(&request_bytes),"parentProposalSha256":digest(&proposal_bytes),
        "reviewed":true,"reviewer":"independent-fixture-review","verdict":"revise","automaticPromotion":false,
        "findings":[{"id":"distinct-references","sourcePaths":["src/state.json"],
            "observed":"Both reference IDs run unchanged behavior.",
            "requiredChange":"Exercise independently implemented valid alternatives."}]});
    let feedback_bytes = serde_json::to_vec(&feedback).unwrap();
    let revision = author::revision(
        &request_bytes,
        &request_bytes,
        &proposal_bytes,
        &feedback_bytes,
    )
    .unwrap();
    let revision_bytes = serde_json::to_vec(&revision).unwrap();
    let admitted = author::check_revision(&request_bytes, &revision_bytes).unwrap();
    assert_eq!(admitted["revisionPacketSha256"], digest(&revision_bytes));
    assert_eq!(admitted["executionPerformed"], false);
    for field in [
        "parentRequestSha256",
        "parentProposalSha256",
        "reviewed",
        "verdict",
        "automaticPromotion",
    ] {
        let mut bad = feedback.clone();
        bad[field] = json!("forged");
        assert!(author::revision(
            &request_bytes,
            &request_bytes,
            &proposal_bytes,
            &serde_json::to_vec(&bad).unwrap()
        )
        .is_err());
    }
    for path in ["other/state.json", "src/missing.json", "../src/state.json"] {
        let mut bad = feedback.clone();
        bad["findings"][0]["sourcePaths"] = json!([path]);
        assert!(author::revision(
            &request_bytes,
            &request_bytes,
            &proposal_bytes,
            &serde_json::to_vec(&bad).unwrap()
        )
        .is_err());
    }
    let mut drift = request.clone();
    drift["source"]["revision"] = json!("drift");
    let drift_bytes = serde_json::to_vec(&drift).unwrap();
    let mut rebound = feedback.clone();
    rebound["parentRequestSha256"] = json!(digest(&drift_bytes));
    assert!(author::revision(
        &request_bytes,
        &drift_bytes,
        &proposal_bytes,
        &serde_json::to_vec(&rebound).unwrap()
    )
    .is_err());
    let mut tampered = revision.clone();
    tampered["revisionIndex"] = json!(2);
    assert!(
        author::check_revision(&request_bytes, &serde_json::to_vec(&tampered).unwrap()).is_err()
    );
    tampered = revision.clone();
    tampered["parentProposalOriginal"] = json!("{}");
    assert!(
        author::check_revision(&request_bytes, &serde_json::to_vec(&tampered).unwrap()).is_err()
    );
    assert!(author::revision(
        &request_bytes,
        &revision_bytes,
        &proposal_bytes,
        &feedback_bytes
    )
    .is_err());
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
    for (index, control) in [
        json!({"id":"reference","role":"valid implementation","expectedFailedCheckIds":[]}),
        json!({"id":"reference","role":"reference","expectedFailedCheckIds":true}),
        json!({"id":"reference","role":"reference","expectedFailedCheckIds":[1]}),
        json!({"id":"reference","role":"reference","expectedFailedCheckIds":[],"description":"extra"}),
    ]
    .into_iter()
    .enumerate()
    {
        let mut invalid = proposal.clone();
        invalid["contract"]["controls"][1] = control;
        let rejected_stage = dir.join(format!("invalid-control-stage-{index}"));
        let error = author::stage(
            &request_bytes,
            &serde_json::to_vec(&invalid).unwrap(),
            &rejected_stage,
        )
        .unwrap_err();
        assert!(error.contains("role (baseline/reference/wrong)"), "{error}");
        assert!(!rejected_stage.exists());
    }
    for index in 0..5 {
        let mut invalid = proposal.clone();
        match index {
            0 => invalid["contract"]["controls"][1]["id"] = json!("baseline"),
            1 => invalid["contract"]["controls"][3]["expectedFailedCheckIds"] = json!(["unknown"]),
            2 => {
                invalid["contract"]["controls"][3]["expectedFailedCheckIds"] =
                    json!(["value", "value"])
            }
            3 => {
                invalid["contract"]["checks"] = json!([
                {"id":"value","pointer":"/value","expected":1},
                {"id":"value","pointer":"/value","expected":1}])
            }
            _ => invalid["contract"]["controls"][1]["expectedFailedCheckIds"] = json!(["value"]),
        }
        let output = dir.join(format!("invalid-bound-contract-{index}"));
        assert!(author::stage(
            &request_bytes,
            &serde_json::to_vec(&invalid).unwrap(),
            &output
        )
        .is_err());
        assert!(
            !output.exists(),
            "invalid static contract created staging files: {index}"
        );
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
    let mut anchor_only = request.clone();
    anchor_only["sourceFiles"][1]["content"] = Value::Null;
    assert!(author::stage(
        &serde_json::to_vec(&anchor_only).unwrap(),
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
fn frozen_seams_observe_changed_source_branch_and_unchanged_earlier_exception() {
    let (dir, _) = loop_fixture();
    fs::create_dir_all(dir.join("source")).unwrap();
    let source = "const {first,second}=require('./external');exports.run=async()=>{try{const allowed=first();if(allowed){return await second();}return null;}catch(e){return e.code;}};";
    fs::write(dir.join("source/body.js"), source).unwrap();
    let manifest = json!({"files":[{"path":"body.js","content":source,"sha256":digest(source.as_bytes())}],
        "controls":[{"id":"baseline","edits":[]},
            {"id":"inverted","edits":[{"path":"body.js","before":"if(allowed)","after":"if(!allowed)"}]}],
        "scenarios":[
            {"id":"disabled","inputs":{"seams":{
                "first":{"outcomes":[{"kind":"return","value":false}],"repeatLast":true},
                "second":{"outcomes":[{"kind":"resolve","value":3}],"repeatLast":true}}}},
            {"id":"earlier-exception","inputs":{"seams":{
                "first":{"outcomes":[{"kind":"throw","value":{"code":17}}],"repeatLast":true},
                "second":{"outcomes":[{"kind":"resolve","value":3}],"repeatLast":true}}}}]});
    let helper = dir.join("runtime.cjs");
    fs::write(
        &helper,
        format!(
            "const manifest = {manifest};\n{}",
            include_str!("../src/source_design_runtime.cjs")
        ),
    )
    .unwrap();
    let script = r#"
const assert=require('assert'),create=require(process.argv[1]);
// CommonJS fixture needs no translation; this compiler tests module plumbing only.
const compiler={ScriptTarget:{ES2020:0},ScriptKind:{TS:0},ModuleKind:{CommonJS:0},
  DiagnosticCategory:{Error:1},createSourceFile(){return {parseDiagnostics:[]}},
  transpileModule(text){return {outputText:text,diagnostics:[]}}};
async function observe(control,scenario){
  const r=create(process.argv[2],control,compiler),s=r.createSeams(scenario);
  const module=r.loadModule('body.js',{'./external':{first:s.functions.first,second:s.functions.second}});
  const value=await module.run();s.assertWithinBudget();return {value,calls:s.observations()};
}
(async()=>{
  const baseline=await observe('baseline','disabled');
  const wrong=await observe('inverted','disabled');
  assert.strictEqual(baseline.value,null);assert.strictEqual(wrong.value,3);
  assert.deepStrictEqual(baseline.calls,[{seam:'first',args:[]}]);
  assert.deepStrictEqual(wrong.calls,[{seam:'first',args:[]},{seam:'second',args:[]}]);
  const early=await observe('baseline','earlier-exception');
  const unchanged=await observe('inverted','earlier-exception');
  assert.deepStrictEqual(early,unchanged);assert.strictEqual(early.value,17);
  assert.deepStrictEqual(early.calls,[{seam:'first',args:[]}]);
})().catch(e=>{console.error(e);process.exitCode=1});
"#;
    let result = Command::new("node")
        .arg("-e")
        .arg(script)
        .arg(helper)
        .arg(dir.join("source"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        fs::read_to_string(dir.join("source/body.js")).unwrap(),
        source
    );
}

#[test]
fn business_selects_fresh_operation_without_promoting_candidate_or_borrowing_recipe() {
    let (dir, mut catalog) = loop_fixture();
    let knowledge = dir.join("knowledge");
    let cut_path = knowledge.join("maintainer-knowledge-cut.json");
    let mut cut: Value = serde_json::from_slice(&fs::read(&cut_path).unwrap()).unwrap();
    let inventory = b"arbitrary\n";
    fs::write(knowledge.join("source-set.txt"), inventory).unwrap();
    cut["sourceSetSha256"] = json!(digest(inventory));
    cut["tableGitAuthority"]["repo"] = json!("fixture-knowledge");
    let cut_bytes = serde_json::to_vec_pretty(&cut).unwrap();
    fs::write(&cut_path, &cut_bytes).unwrap();
    catalog["knowledgeCutSha256"] = json!(digest(&cut_bytes));
    let state = json!({"schema":"agentlab.flywheel_business_state.v1","automaticPromotion":false,
        "repositoryId":"arbitrary","sourceRevision":cut["repositories"][0]["revision"],
        "knowledge":{"directory":knowledge,"cutSha256":digest(&cut_bytes),"revision":cut["tableGitAuthority"]["revision"]},
        "guidanceMode":"reviewed-bootstrap","bootstrapReview":{"reviewed":true,"knowledgeCutSha256":digest(&cut_bytes)}});
    let execute = |name: &str, catalog: &Value, conflicting: bool| {
        let catalog_bytes = serde_json::to_vec(catalog).unwrap();
        let catalog_path = dir.join(format!("{name}-catalog.json"));
        fs::write(&catalog_path, &catalog_bytes).unwrap();
        let mut input = state.clone();
        input["operationCatalog"] = json!({"path":catalog_path,"sha256":digest(&catalog_bytes)});
        if conflicting {
            input["operationExecution"] = json!({});
        }
        let bytes = serde_json::to_vec(&input).unwrap();
        let path = dir.join(format!("{name}-state.json"));
        fs::write(&path, &bytes).unwrap();
        let output = dir.join(name);
        fs::create_dir(&output).unwrap();
        let request = json!({"schema":"agentlab.flywheel_stage_request.v1","round":0,
            "stage":"maintenance-verification","automaticPromotion":false,
            "inputState":{"path":path,"sha256":digest(&bytes)}});
        let result = agentlab_code_analysis::maintainer_flywheel_business::run(
            &serde_json::to_vec(&request).unwrap(),
            &output,
        )
        .unwrap();
        let report: Value =
            serde_json::from_slice(&fs::read(output.join("business/report.json")).unwrap())
                .unwrap();
        (result, report, output)
    };
    let (result, report, _) = execute("selected", &catalog, false);
    assert_eq!(result["status"], "completed", "{report}");
    assert_eq!(report["automaticSelectionPerformed"], true);
    assert_eq!(report["freshOperationExecuted"], true);
    assert_eq!(report["selection"]["productiveOperationRounds"], 1);
    assert_eq!(report["selection"]["authorityWritePerformed"], false);
    assert_eq!(report["selection"]["closedLoopQualified"], false);
    assert_eq!(report["qualificationScope"]["sourceMaintenance"], true);
    assert_eq!(report["qualificationScope"]["runtime"], false);
    assert!(PathBuf::from(report["operationKnowledgeCandidate"].as_str().unwrap()).exists());
    assert_eq!(fs::read(&cut_path).unwrap(), cut_bytes);
    for (name, field, value) in [
        ("foreign", "repositorySelector", json!("foreign")),
        ("stale", "knowledgeCutSha256", json!("0".repeat(64))),
    ] {
        let mut bad = catalog.clone();
        bad[field] = value;
        let (result, _, output) = execute(name, &bad, false);
        assert_eq!(result["status"], "rejected");
        assert!(!output
            .join("business/selected-operation/iteration-1/capture")
            .exists());
    }
    let (result, _, output) = execute("conflicting", &catalog, true);
    assert_eq!(result["status"], "rejected");
    assert!(!output.join("business/selected-operation").exists());
    catalog["entries"] = json!([catalog["entries"][1].clone()]);
    let (result, report, output) = execute("missing", &catalog, false);
    assert_eq!(result["status"], "review-required");
    assert_eq!(report["freshOperationExecuted"], false);
    assert_eq!(
        report["selection"]["gap"]["code"],
        "selected-source-operation-recipe-required"
    );
    assert!(!output
        .join("business/selected-operation/iteration-1/capture")
        .exists());
    assert_eq!(fs::read(&cut_path).unwrap(), cut_bytes);
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
