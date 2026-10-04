use std::path::Path;
use std::process::Command;

#[test]
fn retained_isolation_reconstruction_keeps_live_gates_and_exact_mount_policy() {
    let code = r#"
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path
root=Path(os.environ['RELEASE_ROOT'])
spec=importlib.util.spec_from_file_location('fixture',root/'tests/test_participant_runtime_isolation.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
module=fixture.MODULE
with tempfile.TemporaryDirectory() as directory:
  base=Path(directory).resolve()
  config,receipts,workspace,state,label,inspect_path=fixture.ParticipantRuntimeIsolationTests().prepare(base)
  live=module.validate_runtime_receipts(config,receipts,workspace,state,[label])
  assert 'recordedPathsOnly' not in live
  workspace.rmdir();state.rmdir()
  (base/'pi-runtime').rename(base/'retained-pi-runtime')
  (base/'participant-case').rename(base/'retained-participant-case')
  try:module.validate_runtime_receipts(config,receipts,workspace,state,[label])
  except FileNotFoundError:pass
  else:raise AssertionError('live paths accepted after retirement')
  result=module.validate_runtime_receipts(config,receipts,workspace,state,[label],recorded_paths=True)
  for key in ['filesystemIsolationQualified','externalCredentialIsolationQualified','networkEgressIsolationQualified','recordedPathsOnly']:
    assert result[key] is True
  assert result['liveFilesystemRechecked'] is False and result['freshRuntimeExecuted'] is False
  assert result['producerAuthenticated'] is False
  cli=subprocess.run([sys.executable,str(root/'scripts/validate-participant-runtime.py'),
    '--config',str(config),'--receipt-root',str(receipts),'--workspace',str(workspace),
    '--participant-state',str(state),'--label',label,'--recorded-paths'],capture_output=True)
  assert cli.returncode==0,cli.stderr
  assert json.loads(cli.stdout)==result
  try:module.validate_runtime_receipts(config,receipts,base/'wrong-workspace',state,[label],recorded_paths=True)
  except ValueError as error:assert 'least-mount policy' in str(error)
  else:raise AssertionError('borrowed recorded workspace accepted')
  for bad in ['relative','/tmp/../escape','/tmp//duplicate','/tmp/./dot','/tmp/back\\slash','/tmp/nul\x00']:
    try:module.recorded_absolute_path(bad)
    except ValueError:pass
    else:raise AssertionError(bad)
  original=inspect_path.read_bytes()
  receipt_path=receipts/(label+'.json');receipt=json.loads(receipt_path.read_bytes())
  for attack in ['extra-mount','credential','host-network']:
    inspect=json.loads(original)
    if attack=='extra-mount':inspect[0]['Mounts'].append(dict(Type='bind',Source='/',Destination='/host',RW=False))
    if attack=='credential':inspect[0]['Config']['Env'].append('AGENTLAB_LM_GATEWAY_KEY=fixture')
    if attack=='host-network':inspect[0]['HostConfig']['NetworkMode']='host'
    inspect_path.write_text(json.dumps(inspect))
    changed=dict(receipt,containerInspectSha256=fixture.sha(inspect_path));receipt_path.write_text(json.dumps(changed))
    try:module.validate_runtime_receipts(config,receipts,workspace,state,[label],recorded_paths=True)
    except ValueError:pass
    else:raise AssertionError('retained isolation weakened: '+attack)
"#;
    let result = Command::new("python3")
        .args(["-c", code])
        .env(
            "RELEASE_ROOT",
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
