"""Compile materialized fixed-source controllers with installed public components."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--install-root',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();e=root/'evidence';e.mkdir()
    lock=json.loads((a.install_root/'downloads/environment-lock.json').read_text())
    sdk=next(c for c in lock['components'] if c['slot']=='harmony-cli')
    kit=next(c for c in lock['components'] if c['slot']=='harmony-build-kit')
    image=lock['images'][0]['reference']
    base=['docker','run','--rm','--platform','linux/amd64','--network=none',
          '--mount',f'type=volume,src={sdk["volume"]},dst=/toolchains/harmony,readonly',
          '--mount',f'type=volume,src={kit["volume"]},dst=/toolchains/harmony-build-kit,readonly',
          '--mount',f'type=bind,src={root},dst=/case',
          '--env','HARMONY_TOOLCHAIN_ROOT=/toolchains/harmony',
          '--env','HARMONY_BUILD_CACHE=/runtime/toolchain-cache/controller',
          '--entrypoint','/usr/bin/python3',image,'/toolchains/harmony-build-kit/bin/harmony']
    summary={'schema':'agentlab.harmony_controller_compilation.v1','ok':False,
             'materialization':json.loads((root/'materialization.json').read_text()),
             'fullSourceBuildQualified':False,'sliceCompilationQualified':False,
             'deviceInteractionQualified':False,'subjectAgentRun':False,'phases':{}}
    (e/'environment-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    for name in ['materialization.json','reference.patch']:shutil.copy2(root/name,e/name)
    def call(label,project,module):
        command=base+['build','--project','/case/'+project,'--module',module,'--offline']
        (e/(label+'-command.json')).write_text(json.dumps(command,indent=2)+'\n')
        start=time.monotonic();r=subprocess.run(command,capture_output=True,timeout=240)
        (e/(label+'-stdout.log')).write_bytes(r.stdout);(e/(label+'-stderr.log')).write_bytes(r.stderr)
        item={'exitCode':r.returncode,'wallSeconds':time.monotonic()-start}
        reports=root/project/'.native-build'
        if reports.exists():
            shutil.copytree(reports,e/label)
            if (reports/'result.json').exists():item['compiler']=json.loads((reports/'result.json').read_text())
        summary['phases'][label]=item
        return r,item
    def build(label):
        result,item=call(label,'workspace/hello','entry')
        if result.returncode:raise RuntimeError(label+' failed; complete logs retained')
        report=item['compiler'];artifacts=[]
        if report['status']!='succeeded' or not report['artifacts']:raise RuntimeError('No compiler artifact')
        for entry in report['artifacts']:
            hap=root/'workspace/hello'/entry['path'];raw=hap.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry['sha256'] or len(raw)!=entry['bytes']:raise RuntimeError('HAP receipt mismatch')
            with zipfile.ZipFile(hap) as z:
                if z.testzip() or not any(n.endswith('.abc') for n in z.namelist()):raise RuntimeError('Invalid HAP')
                abc=b''.join(z.read(n) for n in z.namelist() if n.endswith('.abc'))
                if summary['materialization']['sliceMarker'].encode() not in abc:raise RuntimeError('HAP lacks materialized controller marker')
            shutil.copy2(hap,e/(label+'.hap'));artifacts.append(entry)
        item['verifiedArtifacts']=artifacts
    try:
        # Preserve the full-project result independently; slice success cannot overwrite it.
        full,item=call('whole-source-probe','patched-source','phone')
        summary['fullSourceBuildQualified']=full.returncode==0 and bool(item.get('compiler',{}).get('artifacts'))
        summary['fullSourceBlocker']=None if summary['fullSourceBuildQualified'] else item.get('compiler',{}).get('error','See complete compiler logs')
        source=root/'workspace/hello/entry/src/main/ets/pages/Index.ets';original=source.read_text()
        shutil.copytree(root/'workspace/hello',e/'slice-input')
        build('typed-controller-build');summary['sliceCompilationQualified']=True
        source.write_text(original.replace('@State submitting: boolean = false','@State submitting: number = false'))
        shutil.copy2(source,e/'invalid-state-type.ets')
        failed,item=call('invalid-state-type','workspace/hello','entry')
        if failed.returncode==0 or item.get('compiler',{}).get('artifacts'):raise RuntimeError('Invalid state type accepted or stale artifact returned')
        summary['invalidTypeRejected']=True
        source.write_text(original);build('recovered-controller-build');summary['recoveryCompiled']=True
        summary['ok']=True
    finally:
        (e/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
