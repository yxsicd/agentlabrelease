use std::path::Path;
use std::process::Command;

#[test]
fn successor_action_reconstructs_original_review_before_dispatch_inputs() {
    let code = r#"
import argparse,importlib.util,json,os,subprocess,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('action',os.environ['ACTION_SCRIPT'])
action=importlib.util.module_from_spec(spec);spec.loader.exec_module(action)
with tempfile.TemporaryDirectory() as directory:
  for scenario in ['pass','isolation-reject','native-reject','request-drift','unknown-field']:
    root=Path(directory)/scenario;root.mkdir()
    envelope=dict(schema='agentlab.source_reviewed_successor_enrollment.v1',reviewRun='1',reviewArtifact='2',
      reviewMethodRevision='a'*40,reviewArtifactSha256='b'*64,reviewFeedback={},successorPolicy={})
    if scenario=='unknown-field':envelope['automaticApproval']=True
    (root/'enrollment.json').write_text(json.dumps(envelope));(root/'request').write_bytes(b'{}')
    (root/'gate').touch();(root/'source').mkdir()
    args=argparse.Namespace(enrollment=root/'enrollment.json',output=root/'output',request=root/'request',
      gate=root/'gate',repository='owner/repository',source_git_checkout=root/'source')
    calls=[]
    def require(ok,message):
      if not ok:raise ValueError(message)
    def acquire(value):
      calls.append('acquire');value.output.mkdir()
      (value.output/'source-run.json').write_text(json.dumps(dict(path='.github/workflows/maintainer-source-suite-review.yml')))
      retained=value.output/'review-inputs';(retained/'agent/repair-attempt/evidence').mkdir(parents=True)
      (retained/'enrollment.json').write_text(json.dumps(dict(reviewRepairLimit=1)))
      (retained/'agent/attempt-coordinator.json').write_text(json.dumps(dict(completed=True,selectedAttempt='repair-attempt')))
    def isolation(config,receipts,workspace,state,labels,recorded_paths):
      calls.append('isolation');assert recorded_paths is True and labels==['source-suite-review']
      assert workspace.startswith('/home/runner/work/_temp/source-suite-review/agent/')
      assert state.endswith('/participant-state')
      if scenario=='isolation-reject':raise ValueError('original mount reject')
      return dict(recordedPathsOnly=True,freshRuntimeExecuted=False)
    def native(command,**kwargs):
      calls.append('native');assert '--prepare-source-reviewed-successor' in command
      selected=command[command.index('--participant-evidence')+1]
      assert selected.endswith('/agent/repair-attempt/evidence')
      if scenario=='native-reject':raise subprocess.CalledProcessError(1,command)
      Path(command[command.index('--output')+1]).write_text(json.dumps(dict(authorRequestOriginal='changed' if scenario=='request-drift' else '{}')))
    def module(name,path):
      return SimpleNamespace(require=require,acquire=acquire) if name=='acquisition' else SimpleNamespace(validate_runtime_receipts=isolation)
    with patch.object(action,'module',side_effect=module),patch.object(action.subprocess,'run',side_effect=native):
      try:action.prepare(args)
      except (ValueError,subprocess.CalledProcessError):assert scenario!='pass'
      else:assert scenario=='pass'
    if scenario=='pass':
      result=json.loads((args.output/'bridge-inputs.json').read_bytes())
      assert result['review_response'].endswith('/agent/repair-attempt/response.json')
      assert calls==['acquire','isolation','isolation','native']
      assert (args.output/'local-claims').is_dir()
    else:
      assert not (args.output/'bridge-inputs.json').exists()
      if scenario=='unknown-field':assert calls==[]
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "ACTION_SCRIPT",
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../scripts/prepare-reviewed-successor-action.py"),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
