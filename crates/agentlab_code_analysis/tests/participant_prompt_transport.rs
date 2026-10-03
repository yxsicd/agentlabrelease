#![cfg(unix)]
use std::{path::Path, process::Command};

#[test]
fn actual_launcher_streams_large_utf8_prompts_without_changing_small_turns() {
    // Exercise the Python boundary through an actual child process, not a
    // mocked Popen. This fixture does not contact a model or qualify an Agent.
    let fixture = r#"
import hashlib, importlib.util, json, os, tempfile
from pathlib import Path
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('participant',os.environ['PARTICIPANT_SCRIPT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);workspace=root/'workspace';workspace.mkdir()
    binary=root/'pi-fixture'
    binary.write_text('''#!/usr/bin/env python3
import hashlib,json,sys
from pathlib import Path
args=sys.argv[1:];i=args.index('--session')+1;session=Path(args[i])
raw=sys.stdin.buffer.read() if len(args)==i+1 else args[-1].encode()
header={'type':'session','id':'transport-fixture'}
session.write_text(json.dumps(header)+'\\n')
print(json.dumps(header))
print(json.dumps({'type':'message_end','message':{'role':'assistant','stopReason':'stop','content':hashlib.sha256(raw).hexdigest()}}))
''');binary.chmod(0o755)
    prompts=['unchanged small prompt', '源代码上下文\n'*100000]
    if os.environ.get('RETAINED_PROMPT'):
        prompts.append(Path(os.environ['RETAINED_PROMPT']).read_text())
    for index,prompt in enumerate(prompts):
        evidence=root/f'evidence-{index}';evidence.mkdir();state=root/f'state-{index}';state.mkdir()
        p=module.Participant.__new__(module.Participant)
        p.state=state;p.evidence=evidence;p.binary=str(binary);p.model='fixture'
        p.implementation='pi';p.reasoning_effort=None;p.server=SimpleNamespace(server_port=12345)
        result=p.turn('turn',workspace,prompt=prompt,require_completed_tool_call=False,transport_retry_limit=0)
        raw=prompt.encode();expected=hashlib.sha256(raw).hexdigest()
        assert result['content']==expected
        assert (evidence/'turn-prompt.txt').read_bytes()==raw
        lifecycle=json.loads((evidence/'turn-lifecycle.json').read_bytes())
        command=json.loads((evidence/'turn-command.json').read_bytes())
        large=len(raw)>65536
        assert lifecycle['promptTransport']=={'kind':'stdin-file' if large else 'argv','bytes':len(raw),'sha256':expected}
        assert lifecycle['exitCode']==0 and lifecycle['sessionContinuity']['qualified']
        assert (prompt not in command) if large else (command[-1]==prompt)
        if large: assert max(len(arg.encode()) for arg in command)<65536
"#;
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let mut command = Command::new("python3");
    command.args(["-c", fixture]).env(
        "PARTICIPANT_SCRIPT",
        root.join("examples/real-code-agent/participant.py"),
    );
    if let Ok(path) = std::env::var("AGENTLAB_RETAINED_PROMPT") {
        command.env("RETAINED_PROMPT", path);
    }
    let result = command.output().unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
