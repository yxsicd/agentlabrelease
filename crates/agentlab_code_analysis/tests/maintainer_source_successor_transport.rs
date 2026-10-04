use std::path::Path;
use std::process::Command;

#[test]
fn baseline_continuation_transport_reserves_original_failure_not_enrollment_id() {
    let code = r#"
import argparse,hashlib,importlib.util,json,os,subprocess,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('transport',os.environ['CONTINUATION_SCRIPT'])
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
with tempfile.TemporaryDirectory() as temporary:
  for scenario in ['pass','prepared-pass','prepared-drift','producer-drift','archive-drift','native-stop','review-stop','live-stop','remote-refusal','author-failure','timeout','isolation-stop','completion-stop','post-stop']:
    root=Path(temporary)/scenario;root.mkdir();(root/'claims').mkdir();(root/'git').mkdir()
    for name in ['gate','pi','request','review-enrollment','config']:(root/name).write_text('{}')
    successor=dict(authorRequestOriginal='{}',targetDesignOriginal='{}')
    (root/'successor').write_text(json.dumps(successor))
    packet=dict(schema='agentlab.source_recipe_diagnostic_repair.v2',continuationEnrollmentOriginal='{"id":"first"}')
    members={
      'parentRequestOriginal':'agent/proposal-stage/request.json',
      'parentProposalOriginal':'agent/proposal-stage/proposal.json',
      'parentDesignOriginal':'agent/proposal-stage/design.json',
      'parentStageReceiptOriginal':'agent/proposal-stage/stage-receipt.json',
      'intentOriginal':'baseline-diagnostic/intent.json','executionRequestOriginal':'baseline-diagnostic/request.json',
      'descriptorOriginal':'baseline-diagnostic/descriptor.json','supportOriginal':'baseline-diagnostic/support.json',
      'processOriginal':'baseline-diagnostic/contained-input-fixture/process.json',
      'stdoutOriginal':'baseline-diagnostic/contained-input-fixture/worker-stdout.log',
      'stderrOriginal':'baseline-diagnostic/contained-input-fixture/worker-stderr.log'}
    for key in members:packet[key]='{}'
    with zipfile.ZipFile(root/'original.zip','w') as archive:
      for key,name in members.items():archive.writestr(name,packet[key])
      archive.writestr('successor-request.json',(root/'successor').read_bytes())
      archive.writestr('successor-enrollment.json',b'{}')
    original=(root/'original.zip').read_bytes();sha=hashlib.sha256(original).hexdigest()
    (root/'repair').write_text(json.dumps(packet))
    args=argparse.Namespace(output=root/'output',gate=root/'gate',pi=root/'pi',request=root/'request',
      diagnostic_repair=root/'repair',successor_request=root/'successor',review_enrollment=root/'review-enrollment',
      parent_archive=root/'original.zip',source_git_checkout=root/'git',claim_root=root/'claims',
      repository='owner/repo',method_revision='b'*40,parent_method_revision='a'*40,parent_run='1',
      parent_artifact='2',parent_archive_sha256=sha,reasoning_effort='low')
    args.prepared_output=scenario.startswith('prepared-')
    if args.prepared_output:
      args.output.mkdir()
      (args.output/'request.json').write_text('changed' if scenario=='prepared-drift' else '{}')
      (args.output/'runtime-validation.json').write_text('original Action-owned evidence')
    if scenario=='archive-drift':(root/'original.zip').write_bytes(original+b'changed')
    authors=[];reserved=set();posts=[];isolations=[]
    def run(command,**kwargs):
      if command[0]=='gh':
        if '/actions/runs/' in command[-1]:
          value=dict(id=1,status='completed',run_attempt=1,event='workflow_dispatch',head_branch='main',
            path='.github/workflows/maintainer-source-recipe-author.yml',head_sha='c'*40 if scenario=='producer-drift' else 'a'*40)
        elif '/actions/artifacts/' in command[-1]:
          value=dict(id=2,expired=False,name='unreviewed-source-recipe-1',workflow_run=dict(id=1),
            digest='sha256:'+sha,size_in_bytes=len(original))
        else:
          assert command[1:4]==['api','--method','POST']
          ref=next(x[4:] for x in command if x.startswith('ref='));posts.append(ref)
          if ref in reserved or scenario=='remote-refusal':return subprocess.CompletedProcess(command,1,b'',b'existing durable slot')
          reserved.add(ref);value=dict(ref=ref,object=dict(sha='b'*40))
        return subprocess.CompletedProcess(command,0,json.dumps(value).encode(),b'')
      out=Path(command[command.index('--output')+1])
      if any(str(x).endswith('prepare-reviewed-successor-action.py') for x in command):
        if scenario=='review-stop':return subprocess.CompletedProcess(command,1,b'',b'original review reject')
        out.mkdir();(out/'bridge-inputs.json').write_text(json.dumps({key:str(root/key) for key in
          ['source','quality_rubric','participant_evidence','review_response','review_feedback','successor_policy','source_git_checkout']}))
      elif '--check-source-recipe-diagnostic-repair' in command and scenario=='native-stop':
        return subprocess.CompletedProcess(command,1,b'',b'original diagnostic reject')
      elif '--validate-source-recipe-design' in command and scenario=='live-stop':
        return subprocess.CompletedProcess(command,1,b'',b'live source drift')
      elif '--check-source-reviewed-successor' in command and authors and scenario=='post-stop':
        return subprocess.CompletedProcess(command,1,b'',b'original review changed')
      elif '--verify-unguided-source-recipe-completion' in command and scenario=='completion-stop':
        return subprocess.CompletedProcess(command,1,b'',b'original wire rejected')
      elif any(str(x).endswith('run-source-recipe-author.py') for x in command):
        authors.append(command);assert kwargs['timeout']==600
        assert 'GH_TOKEN' not in kwargs['env'] and 'GITHUB_TOKEN' not in kwargs['env']
        assert command[command.index('--design-revisions')+1]=='0'
        assert command[command.index('--proposal-format-revisions')+1]=='0'
        assert '--diagnostic-repair' in command
        assert '--require-independent-completion' in command
        if scenario=='timeout':raise subprocess.TimeoutExpired(command,600,output=b'partial bytes',stderr=b'original timeout')
        if scenario=='author-failure':return subprocess.CompletedProcess(command,1,b'partial bytes',b'original failure')
        stage=out/'proposal-stage';stage.mkdir(parents=True)
        for name in ['request.json','proposal.json','design.json']:(stage/name).write_text('{}')
      elif any(str(x).endswith('validate-participant-runtime.py') for x in command):
        isolations.append(command)
        assert '--recorded-paths' not in command
        if scenario=='isolation-stop':return subprocess.CompletedProcess(command,1,b'',b'fresh isolation reject')
        out.write_text('{}')
      else:out.write_text('{}')
      return subprocess.CompletedProcess(command,0,b'original stdout',b'original stderr')
    with patch.dict(os.environ,AGENTLAB_PARTICIPANT_RUNTIME_CONFIG=str(root/'config'),GH_TOKEN='operator-only',GITHUB_TOKEN='operator-only'),patch.object(transport.subprocess,'run',side_effect=run):
      try:result=transport.execute(args)
      except Exception:assert scenario not in ['pass','prepared-pass']
      else:assert scenario in ['pass','prepared-pass'] and result['constructionCompleted'] is True and result['runtimeIsolationVerified'] is True
      if args.prepared_output:
        assert (args.output/'runtime-validation.json').read_text()=='original Action-owned evidence'
      if scenario=='pass':
        # Different new enrollment plus fresh local claim root cannot reuse the remote parent slot.
        packet['continuationEnrollmentOriginal']='{"id":"second"}';(root/'repair').write_text(json.dumps(packet))
        args.output=root/'second';args.claim_root=root/'new-claims';args.claim_root.mkdir()
        try:transport.execute(args)
        except subprocess.CalledProcessError:pass
        else:raise AssertionError('changed enrollment redispatched original failure')
        assert len(authors)==1 and len(posts)==2 and posts[0]==posts[1]
        assert len(reserved)==1
    terminal=json.loads((root/'output/transport-terminal.json').read_bytes())
    assert terminal['oldBudgetReopened'] is False and terminal['knowledgeWritePerformed'] is False
    assert terminal['recordedAuthorCompletionVerified'] is (scenario in ['pass','prepared-pass','post-stop'])
    assert terminal['qualified'] is False
    if scenario in ['prepared-drift','producer-drift','archive-drift','native-stop','review-stop','live-stop']:
      assert authors==[] and posts==[]
    if scenario in ['author-failure','timeout']:assert len(isolations)==1 and len(list((root/'claims').iterdir()))==1
    if scenario=='timeout':assert (root/'output/constructor-stdout.log').read_bytes()==b'partial bytes'
print('baseline transport identity, native stops, durable slot and failure preservation passed')
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "CONTINUATION_SCRIPT",
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../scripts/run-baseline-continuation.py"),
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
fn successor_transport_preserves_claims_and_stops_on_original_gate_failures() {
    // This mocks process transport only. Native capture/design semantics are
    // independently exercised by maintainer_source_diagnostic/operation tests.
    let code = r#"
import argparse,hashlib,importlib.util,json,os,subprocess,tempfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('bridge',os.environ['BRIDGE_SCRIPT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
  passing=['pass','prepared','durable']
  for scenario in passing+['durable-reject','native-stop','live-stop','author-failure','timeout','changed-request','changed-design','post-stop']:
    root=Path(directory)/scenario;root.mkdir();claims=root/'claims';claims.mkdir()
    for name in ['gate','pi','request','rubric','response','feedback','policy']:(root/name).write_bytes(b'{}')
    for name in ['source','evidence','git']:(root/name).mkdir()
    target='{"frozen":"original target"}'
    packet=dict(authorRequestOriginal='{}',parentDesignOriginal='{}',reviewFeedbackOriginal='{}',
      reviewResponseOriginal='{}',policyOriginal='{}',authorRequestSha256=hashlib.sha256(b'{}').hexdigest(),
      targetDesignOriginal=target,targetDesignSha256=hashlib.sha256(target.encode()).hexdigest(),successorIndex=1)
    args=argparse.Namespace(gate=root/'gate',pi=root/'pi',request=root/'request',quality_rubric=root/'rubric',
      review_response=root/'response',review_feedback=root/'feedback',successor_policy=root/'policy',
      source=root/'source',participant_evidence=root/'evidence',source_git_checkout=root/'git',
      previous_successor=None,claim_root=claims,output=root/'output',reasoning_effort='low')
    args.prepared_output=scenario in ['prepared','durable','durable-reject']
    if args.prepared_output:
      args.output.mkdir();args.request=args.output/'request.json';args.request.write_bytes(b'{}')
    args.github_claim_repository='owner/repository' if scenario in ['durable','durable-reject'] else None
    args.github_claim_revision='a'*40 if args.github_claim_repository else None
    authors=[];commands=[]
    def run(command,**kwargs):
      commands.append(command)
      if command[0]=='gh':
        assert command[1:4]==['api','--method','POST']
        assert any(str(value).startswith('ref=refs/heads/agentlab-successor-claims/') for value in command)
        reply=dict(ref=next(value[4:] for value in command if str(value).startswith('ref=')),object=dict(sha='a'*40))
        return subprocess.CompletedProcess(command,1 if scenario=='durable-reject' else 0,json.dumps(reply).encode(),b'original claim response')
      out=Path(command[command.index('--output')+1])
      if '--prepare-source-reviewed-successor' in command:
        assert '--source-git-checkout' in command
        if scenario=='native-stop':return subprocess.CompletedProcess(command,1,b'',b'original native reject')
        out.write_text(json.dumps(packet))
      elif '--validate-source-recipe-design' in command:
        if scenario=='live-stop':return subprocess.CompletedProcess(command,1,b'',b'live checkout drift')
        out.write_text('{}')
      elif '--check-source-reviewed-successor' in command:
        if scenario=='post-stop' and authors:return subprocess.CompletedProcess(command,1,b'',b'original review changed')
        out.write_text('{}')
      elif any(str(x).endswith('run-source-recipe-author.py') for x in command):
        authors.append(command)
        assert '--frozen-design' in command and '--design-first' not in command
        assert command[command.index('--design-revisions')+1]=='0'
        assert command[command.index('--proposal-format-revisions')+1]=='0'
        assert kwargs['timeout']==600
        assert kwargs['env']['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT']==str(args.output/'runtime-receipts')
        assert 'GH_TOKEN' not in kwargs['env'] and 'GITHUB_TOKEN' not in kwargs['env']
        if scenario=='timeout':raise subprocess.TimeoutExpired(command,600,output=b'partial original',stderr=b'original timeout')
        if scenario=='author-failure':return subprocess.CompletedProcess(command,1,b'partial original',b'original author reject')
        stage=out/'proposal-stage';stage.mkdir(parents=True)
        (stage/'request.json').write_bytes(b'changed' if scenario=='changed-request' else b'{}')
        (stage/'design.json').write_bytes(Path(command[command.index('--frozen-design')+1]).read_bytes())
        (stage/'stage-receipt.json').write_text('{}')
        if scenario=='changed-design':(args.output/'target-design.json').write_bytes(b'changed')
      else:
        assert '--validate-source-design-review-output' in command
        out.write_text('{}')
      return subprocess.CompletedProcess(command,0,b'original stdout',b'original stderr')
    with patch.object(module.subprocess,'run',side_effect=run):
      try:result=module.execute(args)
      except (ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired):assert scenario not in passing
      else:
        assert scenario in passing and result['constructionCompleted'] is True
        assert result['qualified'] is False and result['knowledgeWritePerformed'] is False
    terminal=json.loads((args.output/'transport-terminal.json').read_bytes())
    assert terminal['constructionCompleted']==(scenario in passing)
    expected=0 if scenario in ['native-stop','live-stop','durable-reject'] else 1
    expected_claims=0 if scenario in ['native-stop','live-stop'] else 1
    assert len(authors)==expected and len(list(claims.iterdir()))==expected_claims
    if scenario=='durable-reject':assert terminal['durableClaimIntentRecorded'] is True
    if scenario=='timeout':assert (args.output/'constructor-stdout.log').read_bytes()==b'partial original'
    if expected:
      retained=next(claims.iterdir()).read_bytes()
      args.output=root/'second-output'
      if args.prepared_output:
        args.output.mkdir();args.request=args.output/'request.json';args.request.write_bytes(b'{}')
      with patch.object(module.subprocess,'run',side_effect=run):
        try:module.execute(args)
        except (FileExistsError,subprocess.CalledProcessError):pass
        else:raise AssertionError('same original enrollment dispatched twice')
      assert len(authors)==1 and next(claims.iterdir()).read_bytes()==retained
    assert terminal['sourceControlSuiteExecuted'] is False and terminal['independentReviewExecuted'] is False
"#;
    let script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/run-reviewed-source-successor.py");
    let result = Command::new("python3")
        .args(["-c", code])
        .env("BRIDGE_SCRIPT", script)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
