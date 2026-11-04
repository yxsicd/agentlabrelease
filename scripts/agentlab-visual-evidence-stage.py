#!/usr/bin/env python3
"""Stage an offline visual-evidence tools payload. No pip, Docker or activation."""
import argparse,hashlib,json,os,shutil,stat,tempfile,zipfile
from pathlib import Path

def stage(wheel, expected, output, tool, platform):
    if output.exists(): raise ValueError('output exists; stage a new immutable candidate')
    raw=wheel.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('wheel digest mismatch')
    arch={'linux-x64':'x86_64','linux-arm64':'aarch64'}[platform]
    if '-cp312-cp312-' not in wheel.name or 'manylinux' not in wheel.name or arch not in wheel.name: raise ValueError('expected CPython3.12 manylinux wheel for selected architecture')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.tools-stage-',dir=output.parent) as td:
        root=Path(td);base=root/'share/agentlab/visual-evidence';lib=base/'python';lib.mkdir(parents=True);(root/'bin').mkdir()
        with zipfile.ZipFile(wheel) as z:
            if sum(f.file_size for f in z.infolist())>64*1024*1024: raise ValueError('wheel expansion exceeds budget')
            for item in z.infolist():
                rel=Path(item.filename)
                if rel.is_absolute() or '..' in rel.parts or stat.S_ISLNK(item.external_attr>>16): raise ValueError('unsafe wheel entry')
                dest=lib/rel
                if item.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(item));dest.chmod(0o644)
        shutil.copyfile(tool,base/'agentlab-visual-evidence.py')
        wrapper=root/'bin/agentlab-visual-evidence'
        wrapper.write_text('''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT/share/agentlab/visual-evidence/python"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
exec "${AGENTLAB_VISUAL_PYTHON:-/usr/bin/python3}" -s "$ROOT/share/agentlab/visual-evidence/agentlab-visual-evidence.py" "$@"
''');wrapper.chmod(0o755)
        inventory=[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file()]
        receipt={'schema':'agentlab.visual_tools_payload.v1','platform':platform,'pythonAbi':'cp312','requiresBaseImagePython':True,'runtimeNetworkRequired':False,'wheel':{'filename':wheel.name,'sha256':expected,'bytes':len(raw)},'requiredCommands':['/tools/bin/agentlab-visual-evidence'],'releaseQualificationCommand':'/tools/bin/agentlab-visual-evidence self-check','qualificationPending':True,'files':inventory,'logicalBytes':sum(x['bytes'] for x in inventory)}
        root.chmod(0o755)
        (base/'payload.json').write_text(json.dumps(receipt,indent=2)+'\n');os.rename(root,output)
    return {'output':str(output),'files':len(inventory),'logicalBytes':receipt['logicalBytes'],'qualificationPending':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wheel',type=Path,required=True);p.add_argument('--wheel-sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--platform',choices=['linux-x64','linux-arm64'],required=True);p.add_argument('--tool',type=Path,default=Path(__file__).with_name('agentlab-visual-evidence.py'));a=p.parse_args()
    print(json.dumps(stage(a.wheel,a.wheel_sha256,a.output,a.tool,a.platform)))
if __name__=='__main__':main()
