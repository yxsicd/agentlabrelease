use std::path::Path;
use std::process::Command;

#[test]
fn constructor_observation_guide_preserves_per_check_shape_without_answers() {
    let code = r#"
import copy,importlib.util,json,os
spec=importlib.util.spec_from_file_location('author',os.environ['AUTHOR_SCRIPT'])
author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
design={'checks':[
  {'id':'left','pointer':'/left/present','expected':['unique-secret-probe', 'other']},
  {'id':'right','pointer':'/right/absent','expected':['distinct-probe']},
  {'id':'state','pointer':'/right/state','expected':{'flag':True,'count':3,'missing':None,'nested':[[1]]}},
  {'id':'empty','pointer':'/left/empty','expected':[]}]}
original=copy.deepcopy(design)
guide=author.observation_contract_guide(design)
assert design==original
assert [(row['id'],row['pointer']) for row in guide]==[(row['id'],row['pointer']) for row in design['checks']]
assert guide[0]['shape']=={'type':'array','length':2,'items':[{'type':'string'},{'type':'string'}]}
assert guide[1]['shape']=={'type':'array','length':1,'items':[{'type':'string'}]}
assert guide[2]['shape']=={'type':'object','properties':{'flag':{'type':'boolean'},'count':{'type':'number'},'missing':{'type':'null'},'nested':{'type':'array','length':1,'items':[{'type':'array','length':1,'items':[{'type':'number'}]}]}}}
assert guide[3]['shape']=={'type':'array','length':0,'items':[]}
assert not any(probe in json.dumps(guide) for probe in ['unique-secret-probe','other','distinct-probe'])
# Same shapes, different answers: guide must not turn into an answer inventory.
changed=copy.deepcopy(design)
changed['checks'][0]['expected']=['changed','values']
changed['checks'][2]['expected']['flag']=False
changed['checks'][2]['expected']['count']=99
assert author.observation_contract_guide(changed)==guide
print('per-check shapes, nonmutation and answer exclusion passed')
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "AUTHOR_SCRIPT",
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../scripts/run-source-recipe-author.py"),
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
  # Execute the workflow's actual parser, not a separately reimplemented schema router.
  import textwrap
  workflow=(Path(os.environ['ACTION_SCRIPT']).resolve().parents[1]/'.github/workflows/maintainer-source-recipe-author.yml').read_text()
  section=workflow.split('      - name: Validate explicit revision input pairing\n',1)[1].split('      - name:',1)[0]
  code=textwrap.dedent(section.split("          python3 - <<'PY'\n",1)[1].rsplit('          PY',1)[0])
  for mode in ['empty','legacy','successor','successor-pretty','mixed','rerun']:
    envelope=dict(schema='agentlab.source_reviewed_successor_enrollment.v1',reviewRun='1')
    feedback=json.dumps(envelope,indent=2 if mode=='successor-pretty' else None) if mode in ['successor','successor-pretty','mixed','rerun'] else ('{}' if mode=='legacy' else '')
    env=dict(KNOWLEDGE='examples/maintainer-knowledge-gate/first-four',REVISION_PARENT_RUN='1' if mode in ['legacy','mixed'] else '',
      REVISION_FEEDBACK=feedback,CONSTRUCTION_CODE_REVISIONS='0',CONSTRUCTION_DESIGN_REVISIONS='0',
      CONSTRUCTION_DESIGN_FIRST='false',CONSTRUCTION_GATEWAY_TIMEOUT='180',CONSTRUCTION_CODE_GATEWAY_TIMEOUT='inherit',
      CONSTRUCTION_MAX_OUTPUT_TOKENS='16384',CONSTRUCTION_API='openai-completions',CONSTRUCTION_THINKING_TYPE='default',
      CONSTRUCTION_RESPONSE_FORMAT='default',AGENTLAB_SOURCE_GUIDANCE_SELECTION='',GITHUB_RUN_ATTEMPT='2' if mode=='rerun' else '1',
      GITHUB_OUTPUT=str(Path(directory)/(mode+'-outputs')),GITHUB_ENV=str(Path(directory)/(mode+'-env')))
    with patch.dict(os.environ,env):
      try:exec(code,{})
      except AssertionError:assert mode in ['mixed','rerun']
      else:
        assert mode not in ['mixed','rerun']
        selected='true' if mode.startswith('successor') else 'false'
        assert Path(env['GITHUB_OUTPUT']).read_text()=='reviewed_successor='+selected+'\n'
        value=Path(env['GITHUB_ENV']).read_text().split('=',1)[1].strip()
        if selected=='true':assert json.loads(value)==envelope and '\n' not in value
        else:assert value==''
  section=workflow.split('      - name: Freeze optional independent review before construction budget\n',1)[1].split('      - name:',1)[0]
  code=textwrap.dedent(section.split("          python3 - <<'PY'\n",1)[1].rsplit('          PY',1)[0])
  for mode in ['fresh-design','frozen-successor','no-design']:
    temporary=Path(directory)/('freeze-'+mode);(temporary/'recipe-author').mkdir(parents=True)
    env=dict(AUTOMATIC_REVIEW_ENABLED='true',AUTOMATIC_REVIEW_RUBRIC='examples/maintainer-knowledge-gate/source-quality-rubric.json',
      AUTOMATIC_REVIEW_RUBRIC_SHA256='d3276328cc1e23fc4216d0539eb7a003dc2e43d59de0d384b6476cbab4862731',
      AUTOMATIC_REVIEW_REPAIR_LIMIT='1',GITHUB_RUN_ATTEMPT='1',CONSTRUCTION_DESIGN_FIRST='true' if mode=='fresh-design' else 'false',
      REVIEWED_SUCCESSOR=json.dumps(envelope) if mode=='frozen-successor' else '',RUNNER_TEMP=str(temporary),GITHUB_SHA='a'*40,
      GITHUB_RUN_ID='1',AGENTLAB_MODEL='fixture-model',AGENTLAB_PROVIDER_ROUTE='fixture-route',CONSTRUCTION_REASONING_EFFORT='low',
      CONSTRUCTION_THINKING_TYPE='default',CONSTRUCTION_MAX_OUTPUT_TOKENS='16384')
    with patch.dict(os.environ,env):
      try:exec(code,{})
      except AssertionError:assert mode=='no-design'
      else:
        assert mode!='no-design'
        review=json.loads((temporary/'recipe-author/automatic-review/enrollment.json').read_bytes())
        assert review['maximumReviewerAttempts']==2 and review['transportRetryLimit']==0
        assert review['automaticPromotion'] is False
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .current_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
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
