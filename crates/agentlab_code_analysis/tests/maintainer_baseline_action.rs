use std::path::Path;
use std::process::Command;

#[test]
fn one_shot_constructor_records_exact_normalized_prompt_before_dispatch() {
    let code = r#"
import hashlib,importlib.util,json,os,tempfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('author',os.environ['AUTHOR_SCRIPT'])
author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);evidence=root/'evidence';evidence.mkdir();workspace=root/'workspace';workspace.mkdir()
    original='\nExact source prompt\n\t';request=b'{"schema":"original request"}';sent=[]
    class Participant:
        gateway_timeout_seconds=180
        @staticmethod
        def process_budget_seconds(wall_limit):assert wall_limit==240;return 420
        def turn(self,label,workspace,**options):
            intent=json.loads((evidence/(label+'-completion-intent.json')).read_bytes())
            assert (evidence/(label+'-completion-prompt-original.txt')).read_bytes()==original.encode()
            assert intent['promptOriginalSha256']==hashlib.sha256(original.encode()).hexdigest()
            assert intent['promptSha256']==hashlib.sha256(options['prompt'].encode()).hexdigest()
            assert intent['authorRequestSha256']==hashlib.sha256(request).hexdigest()
            assert intent['participantBudgetSeconds']==420 and intent['transportRetryLimit']==0
            assert intent['participantIdentity']==dict(model='fixture',providerRoute='route',providerReasoningEffort='low')
            assert options['prompt']=='Exact source prompt' and options['transport_retry_limit']==0
            sent.append(options['prompt']);return dict(content='{"value":7}',message={'stopReason':'stop'})
    def complete(path):(path/'construction-completion.json').write_text('{}')
    with patch.dict(os.environ,AGENTLAB_MODEL='fixture',AGENTLAB_PROVIDER_ROUTE='route'),patch.object(author,'require_pi_retry_policy'),patch.object(author,'require_complete_gateway_capture',side_effect=complete):
        result=author.construct_proposal(Participant(),workspace,evidence,root,original,'low',0,b'policy',completion_request_bytes=request)
    assert result=={'value':7} and sent==['Exact source prompt']
print('one-shot constructor normalized prompt and native budget intent retained before dispatch')
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "AUTHOR_SCRIPT",
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../scripts/run-source-recipe-author.py"),
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
fn baseline_action_retains_exact_inputs_and_routes_existing_downstream_gates() {
    let code = r#"
import argparse,importlib.util,json,os,stat,subprocess,tempfile,textwrap,warnings,zipfile
from pathlib import Path
from unittest.mock import patch
repo=Path(os.environ['REPOSITORY_ROOT'])
def load(name):
    spec=importlib.util.spec_from_file_location(name,repo/'scripts'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
acquisition=load('acquire-source-suite-review-input.py')
preparation=load('prepare-baseline-continuation-action.py')
required=['successor-request.json','successor-enrollment.json',
    'agent/proposal-stage/request.json','agent/proposal-stage/proposal.json',
    'agent/proposal-stage/design.json','agent/proposal-stage/stage-receipt.json',
    'agent/proposal-stage/controls.cjs','baseline-diagnostic/intent.json',
    'baseline-diagnostic/request.json','baseline-diagnostic/descriptor.json',
    'baseline-diagnostic/support.json','baseline-diagnostic/contained-input-original/process.json',
    'baseline-diagnostic/contained-input-original/worker-stdout.log',
    'baseline-diagnostic/contained-input-original/worker-stderr.log']
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    for scenario in ['good','missing','duplicate','traversal','symlink','two-processes','oversize']:
        archive=root/(scenario+'.zip');out=root/('selected-'+scenario)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
                for name in required:
                    if scenario=='missing' and name.endswith('/support.json'):continue
                    bundle.writestr(name,'original '+name)
                bundle.writestr('agent/participant-state/auth.json','excluded private state')
                if scenario=='duplicate':bundle.writestr(required[0],'duplicate')
                if scenario=='traversal':bundle.writestr('agent/participant-state/../../escape','unsafe unselected')
                if scenario=='symlink':
                    entry=zipfile.ZipInfo('agent/proposal-stage/link');entry.create_system=3
                    entry.external_attr=(stat.S_IFLNK|0o777)<<16;bundle.writestr(entry,'../escape')
                if scenario=='two-processes':bundle.writestr('baseline-diagnostic/contained-input-other/process.json','{}')
                if scenario=='oversize':bundle.writestr('agent/proposal-stage/large',b'x'*(4*1024*1024+1))
        try:acquisition.extract_observations(archive,out,baseline=True)
        except ValueError:assert scenario!='good' and not out.exists()
        else:
            assert scenario=='good' and not (out/'agent/participant-state').exists()
            for name in required:assert (out/name).read_text()=='original '+name
    # Exercise real preparation routing, with only network/native execution mocked.
    for scenario in ['good','request-drift','native-reject','unknown-envelope']:
        case=root/scenario;case.mkdir();(case/'gate').write_text('fixture')
        (case/'request').write_text('original request')
        envelope=dict(schema='agentlab.baseline_continuation_action_enrollment.v1',parentRun='123',
            parentArtifact='456',parentMethodRevision='a'*40,parentArchiveSha256='b'*64,
            continuationEnrollment={'schema':'native-owned-policy'})
        if scenario=='unknown-envelope':envelope['extra']=True
        (case/'enrollment').write_text(json.dumps(envelope))
        commands=[];acquired=[]
        def acquire(args):
            acquired.append(args);args.output.mkdir()
            retained=args.output/'baseline-inputs';stage=retained/'agent/proposal-stage';stage.mkdir(parents=True)
            (stage/'request.json').write_text('changed' if scenario=='request-drift' else 'original request')
            (retained/'baseline-diagnostic/contained-input-original').mkdir(parents=True)
            (retained/'successor-request.json').write_text('original successor')
            (retained/'successor-enrollment.json').write_text('original review')
            (args.output/'original-artifact.zip').write_bytes(b'original archive')
        def run(command,**kwargs):
            commands.append(command);assert kwargs['timeout']==60
            assert '--prepare-source-recipe-diagnostic-continuation' in command
            assert '--stage' in command and '--worker-capture' in command
            if scenario=='native-reject':raise subprocess.CalledProcessError(1,command)
            Path(command[command.index('--output')+1]).write_text('native packet')
        with patch.object(acquisition,'acquire',side_effect=acquire),patch.object(preparation,'module_from_spec',return_value=acquisition),patch.object(preparation,'spec_from_file_location') as spec,patch.object(preparation.subprocess,'run',side_effect=run):
            spec.return_value.loader.exec_module=lambda module:None
            args=argparse.Namespace(enrollment=case/'enrollment',output=case/'prepared',request=case/'request',gate=case/'gate',repository='arbitrary/repo')
            try:inputs=preparation.prepare(args)
            except (ValueError,subprocess.CalledProcessError):assert scenario!='good'
            else:
                assert scenario=='good' and inputs['parent_run']=='123' and inputs['parent_artifact']=='456'
                assert Path(inputs['successor_request']).read_text()=='original successor'
                assert (args.output/'local-claims').is_dir()
            if scenario in ['request-drift','unknown-envelope']:assert commands==[]
            if acquired:assert acquired[0].artifact_kind=='baseline'
            assert not any(c[0]=='gh' or '--pi' in c for c in commands)
    workflow=(repo/'.github/workflows/maintainer-source-recipe-author.yml').read_text()
    def body(name):
        section=workflow.split('      - name: '+name+'\n',1)[1].split('      - name:',1)[0]
        run=textwrap.dedent(section.split('        run: |\n',1)[1])
        return run.split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    knowledge=root/'knowledge';knowledge.mkdir();(knowledge/'maintainer-knowledge-cut.json').write_text('{}')
    env=dict(KNOWLEDGE=str(knowledge.relative_to(root)),REVISION_PARENT_RUN='',
        REVISION_FEEDBACK=json.dumps(envelope if scenario=='good' else {k:v for k,v in envelope.items() if k!='extra'}),
        CONSTRUCTION_DESIGN_FIRST='false',CONSTRUCTION_DESIGN_REVISIONS='0',CONSTRUCTION_CODE_REVISIONS='0',
        CONSTRUCTION_GATEWAY_TIMEOUT='180',CONSTRUCTION_CODE_GATEWAY_TIMEOUT='inherit',CONSTRUCTION_MAX_OUTPUT_TOKENS='16384',
        CONSTRUCTION_API='openai-completions',CONSTRUCTION_THINKING_TYPE='default',CONSTRUCTION_RESPONSE_FORMAT='default',
        AGENTLAB_SOURCE_GUIDANCE_SELECTION='',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(root/'outputs'),GITHUB_ENV=str(root/'env'))
    original=Path.cwd();os.chdir(root)
    try:
        with patch.dict(os.environ,env):exec(compile(body('Validate explicit revision input pairing'),'input-mode','exec'),{})
        assert 'baseline_continuation=true' in (root/'outputs').read_text()
        assert 'reviewed_successor=false' in (root/'outputs').read_text()
        for key,value in [('GITHUB_RUN_ATTEMPT','2'),('CONSTRUCTION_DESIGN_FIRST','true'),('CONSTRUCTION_CODE_REVISIONS','1'),('REVISION_PARENT_RUN','123')]:
            with patch.dict(os.environ,dict(env,**{key:value})):
                try:exec(compile(body('Validate explicit revision input pairing'),'input-mode','exec'),{})
                except AssertionError:pass
                else:raise AssertionError('Invalid continuation mode accepted: '+key)
    finally:os.chdir(original)
    for name in ['Diagnose unchanged generated verifier baseline in a separate container',
                 'Diagnose complete frozen control suite and fresh accepted-reference recovery']:
        section=workflow.split('      - name: '+name+'\n',1)[1].split('      - name:',1)[0]
        assert "steps.input_mode.outputs.baseline_continuation == 'true'" in section
    assert '--prepared-output' in body('Execute one durable baseline-feedback continuation')
    author=root/'recipe-author';retained=author/'retained-baseline';retained.mkdir(parents=True)
    bridge_inputs=dict(parent_run='123',parent_artifact='456',parent_method_revision='a'*40,
        parent_archive_sha256='b'*64,diagnostic_repair='native packet',
        successor_request='original successor',review_enrollment='original review',parent_archive='original archive')
    (retained/'bridge-inputs.json').write_text(json.dumps(bridge_inputs))
    with patch.dict(os.environ,RUNNER_TEMP=str(root),GITHUB_WORKSPACE=str(repo),GITHUB_REPOSITORY='arbitrary/repo',
        GITHUB_SHA='c'*40,CONSTRUCTION_REASONING_EFFORT='low'),patch.object(subprocess,'run') as dispatch:
        exec(compile(body('Execute one durable baseline-feedback continuation'),'dispatch-step','exec'),{})
    dispatch.assert_called_once();command=dispatch.call_args.args[0]
    assert command[:3]==['python3','scripts/run-baseline-continuation.py','--prepared-output']
    for key,value in bridge_inputs.items():assert command[command.index('--'+key.replace('_','-'))+1]==value
    assert command[command.index('--method-revision')+1]=='c'*40
    assert command[command.index('--source-git-checkout')+1]==str(root/'recipe-source')
    assert dispatch.call_args.kwargs['check'] is True
print('baseline Action selected originals, native preparation and existing downstream routing passed')
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "REPOSITORY_ROOT",
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
