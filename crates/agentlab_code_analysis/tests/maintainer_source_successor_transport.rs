use std::path::Path;
use std::process::Command;

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
  for scenario in ['pass','native-stop','live-stop','author-failure','timeout','changed-request','changed-design','post-stop']:
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
    authors=[];commands=[]
    def run(command,**kwargs):
      commands.append(command)
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
      except (ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired):assert scenario!='pass'
      else:
        assert scenario=='pass' and result['constructionCompleted'] is True
        assert result['qualified'] is False and result['knowledgeWritePerformed'] is False
    terminal=json.loads((args.output/'transport-terminal.json').read_bytes())
    assert terminal['constructionCompleted']==(scenario=='pass')
    expected=0 if scenario in ['native-stop','live-stop'] else 1
    assert len(authors)==expected and len(list(claims.iterdir()))==expected
    if scenario=='timeout':assert (args.output/'constructor-stdout.log').read_bytes()==b'partial original'
    if expected:
      retained=next(claims.iterdir()).read_bytes()
      args.output=root/'second-output'
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
