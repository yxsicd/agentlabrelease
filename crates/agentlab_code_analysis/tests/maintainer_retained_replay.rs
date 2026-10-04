use std::{path::PathBuf, process::Command};

#[test]
fn retained_replay_rejects_path_and_dependency_drift_before_execution() {
    let scripts = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../scripts");
    let result = Command::new("python3")
        .arg("-c")
        .arg(r#"
import hashlib,importlib.util,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('replay',Path(sys.argv[1])/'replay-retained-source-completion.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for path in ['/home/runner/work/_temp/source','/usr/local/bin/node']:
    assert m.destination(path)==path
for path in ['/', '/proc/self/mem','/etc/passwd','/tmp/x','/inputs/x','/a/../b','/a//b','/a/b,ro','relative/path']:
    try:m.destination(path)
    except ValueError:pass
    else:raise AssertionError(path)
with tempfile.TemporaryDirectory(prefix='retained-replay-guard-') as name:
    file=Path(name)/'node';file.write_bytes(b'original binary fixture')
    expected=hashlib.sha256(file.read_bytes()).hexdigest()
    assert m.bound_file(file,expected)==file.resolve()
    file.write_bytes(b'changed binary fixture')
    try:m.bound_file(file,expected)
    except ValueError:pass
    else:raise AssertionError('Changed dependency accepted')
spec=importlib.util.spec_from_file_location('restore',Path(sys.argv[1])/'restore-retained-source-dependencies.py')
restore=importlib.util.module_from_spec(spec);spec.loader.exec_module(restore)
import io,tarfile
for kind in ['regular','symlink','oversize']:
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as bundle:
        info=tarfile.TarInfo('package/lib/typescript.js');info.size=4
        if kind=='symlink':info.type=tarfile.SYMTYPE;info.linkname='/etc/passwd';info.size=0
        bundle.addfile(info,io.BytesIO(b'code') if kind!='symlink' else None)
    restore.urllib.request.urlopen=lambda *a,**kw:io.BytesIO(archive.getvalue())
    with tempfile.TemporaryDirectory(prefix='retained-dependency-guard-') as name:
        file=Path(name)/'compiler.js'
        try:restore.member('https://fixture.invalid/archive','package/lib/typescript.js',file,3 if kind=='oversize' else 4)
        except ValueError:assert kind!='regular' and not file.exists()
        else:assert kind=='regular' and file.read_bytes()==b'code'
        assert file.with_suffix('.archive').read_bytes()==archive.getvalue()
# This tests scheduling/permissions only; native gates and real replay are
# exercised separately. Never treat the mocked workers as business acceptance.
import json,types
original_run=m.subprocess.run;original_output=m.subprocess.check_output
for dirty in [False,True]:
    with tempfile.TemporaryDirectory(prefix='retained-git-phase-') as name:
        root=Path(name).resolve();inputs=root/'inputs';inputs.mkdir()
        source=root/'source';source.mkdir();(source/'.git').mkdir()
        knowledge=root/'knowledge';knowledge.mkdir()
        node=root/'node';node.write_bytes(b'node fixture')
        compiler=root/'compiler';compiler.write_bytes(b'compiler fixture')
        gate=root/'gate';gate.write_bytes(b'trusted gate fixture')
        request={'sourceWorktree':'/home/runner/source','knowledgeDirectory':'/home/runner/knowledge',
            'source':{'repository':'https://fixture.invalid/repo.git','revision':'a'*40},
            'policy':{'program':'/usr/local/bin/node','programSha256':hashlib.sha256(node.read_bytes()).hexdigest(),
                'methodDependencies':[{'path':'/home/runner/compiler.js','sha256':hashlib.sha256(compiler.read_bytes()).hexdigest()}]},
            'readOnlySourceContext':{'packet':{'selectedFiles':[{'path':'shared/context.js'}]}}}
        raw=json.dumps(request).encode();(inputs/'request.json').write_bytes(raw)
        calls=[]
        def output(command,**kw):
            if command[:3]==['docker','image','inspect']:return json.dumps([{'Id':command[3]}]).encode()
            return ('a'*40 if command[-2:]==['rev-parse','HEAD'] else request['source']['repository']).encode()
        def run(command,**kw):
            calls.append(command)
            if command[-3:]==['status','--porcelain=v1','--untracked-files=all'] and dirty:kw['stdout'].write(b'?? changed.js\n')
            return types.SimpleNamespace(returncode=0)
        m.subprocess.check_output=output;m.subprocess.run=run
        args=types.SimpleNamespace(inputs=inputs,gate=gate,source_checkout=source,knowledge=knowledge,
            host_node=node,compiler=compiler,stage_image='sha256:'+'b'*64,worker_image='sha256:'+'c'*64,output=root/'result')
        try:result=m.replay(args)
        except ValueError:assert dirty
        else:assert not dirty and result['newAuthorCalls']==0 and result['qualified'] is False
        acquisition=[c for c in calls if c[0]=='docker' and 'git' in c]
        assert acquisition and all('--network' not in c and '--read-only' in c for c in acquisition)
        assert all(str(source/'.git')+':'+request['sourceWorktree']+'/.git:rw' in c for c in acquisition)
        stages=[c for c in calls if '--stage-source-recipe-proposal' in c]
        assert len(stages)==(0 if dirty else 1)
        if stages:
            assert stages[0][stages[0].index('--network')+1]=='none'
            assert not any('/.git:rw' in value for value in stages[0])
        assert (inputs/'request.json').read_bytes()==raw
m.subprocess.run=original_run;m.subprocess.check_output=original_output
"#)
        .arg(&scripts)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
