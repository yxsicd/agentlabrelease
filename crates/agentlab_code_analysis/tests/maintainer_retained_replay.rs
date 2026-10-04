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
