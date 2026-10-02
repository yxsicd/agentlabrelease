use std::{path::PathBuf, process::Command};

#[test]
fn timed_out_launcher_cannot_start_after_the_scoped_stop_command() {
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/run-harmony-assessed-standard-test.py");
    let result = Command::new("python3")
        .args(["-c", r#"
import importlib.util,sys,tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('standard',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);tools=root/'tools';(tools/'bin').mkdir(parents=True)
 image=root/'image';image.mkdir();instances=root/'instances';instances.mkdir();(instances/'phone.ini').write_text('instance')
 out=root/'output';out.mkdir();state=root/'state';stop=root/'stop'
 emulator=tools/'bin/Emulator'
 emulator.write_text('#!/usr/bin/env python3\nimport pathlib,sys,time\n'
  +'state=pathlib.Path('+repr(str(state))+'); stop=pathlib.Path('+repr(str(stop))+')\n'
  +'if "-start" in sys.argv:\n'
  +' for _ in range(200):\n'
  +'  if stop.exists(): break\n'
  +'  time.sleep(.01)\n'
  +' time.sleep(.15)\n state.write_text("up")\n'
  +'else:\n stop.write_text("stopped")\n state.unlink(missing_ok=True)\n')
 emulator.chmod(0o755)
 m.target_connected=lambda *a:False
 m.wait_target=lambda *a,**k:False
 config={'toolsRoot':str(tools),'imageRoot':str(image),'instancePath':str(instances),
  'instance':'phone','hdcPort':15555,'bootMode':'coldboot','bootTimeoutSeconds':1}
 try:m.start_emulator(config,out,root/'hdc')
 except m.StandardGateError as error:assert 'did not expose' in str(error)
 else:raise AssertionError('boot failure accepted')
 assert stop.exists(),'scoped stop must still run'
 assert not state.exists(),'launcher completed startup after the stop command'
 assert (out/'emulator-start-failure-stop.log').is_file()
# This is a deterministic process-order regression, not a Harmony emulator receipt.
"#])
        .arg(script)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
