#!/usr/bin/env python3
"""Restore a trusted portable case through the maintained Git helper; no actors or authority."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path, PurePosixPath

def require(ok,message):
    if not ok: raise ValueError(message)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def member(root,rel):
    p=Path(rel);require(not p.is_absolute() and '..' not in p.parts,'unsafe member')
    out=(root/p).resolve();require(out.is_relative_to(root.resolve()) and out.is_file(),'missing/escaped member');return out

def declared_mappings(case):
    mappings=case.get('logicalMappings')
    require(isinstance(mappings,dict) and mappings,'missing logical mappings')
    pairs=[]
    for source,target in mappings.items():
        for value in (source,target):
            require(isinstance(value,str) and value and '\\' not in value,'invalid mapping')
            rel=PurePosixPath(value)
            require(not rel.is_absolute() and str(rel)==value and all(p not in ('.','..','.git') for p in rel.parts),'unsafe mapping')
        require(PurePosixPath(source).parts[0]=='artifacts','logical mapping must remain in artifact namespace')
        require(PurePosixPath(target).parts[0]=='project','mapping target must remain in restored project')
        pairs.append((source,target))
    for source,_ in pairs:
        require(not any(source!=other and PurePosixPath(source).is_relative_to(PurePosixPath(other)) for other,_ in pairs),'overlapping logical mappings')
    return pairs

def restore(package,point,destination,trusted):
    package=package.resolve();require(digest(package/'case.json')==trusted,'case digest mismatch')
    case=json.loads((package/'case.json').read_text());require(case['schema']=='agentlab.portable-application-case.v1','unsupported case')
    require(case['authorityClaimed'] is False and case['restorePrecision']=='selected_code_and_explicit_public_inputs','unsupported guarantee')
    require(point in case['points'],'unknown point');spec=case['points'][point];mappings=declared_mappings(case)
    require(not destination.exists(),'destination exists')
    for entry in case['files']:
        require(digest(member(package,entry['path']))==entry['sha256'],'member digest mismatch: '+entry['path'])
    helper=member(package,case['gitPatchHelper']);base=member(package,case['baseBundle']);bundle=member(package,spec['bundle']+'/manifest.json').parent
    require(digest(bundle/'manifest.json')==spec['manifestSHA256'],'point manifest mismatch')
    destination.parent.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
    with tempfile.TemporaryDirectory(prefix='.case-base-',dir=destination.parent) as td:
        working=Path(td)/'base'
        subprocess.run(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','clone','--no-hardlinks',str(base),str(working)],env=env,capture_output=True,check=True)
        destination.mkdir()
        z=subprocess.run([sys.executable,str(helper),'restore','--bundle',str(bundle),'--repository-id',case['repositoryId'],'--manifest-sha256',spec['manifestSHA256'],'--source-repo',str(working),'--destination',str(destination/'project')],env=env,capture_output=True,text=True)
        require(z.returncode==0,z.stdout+z.stderr);result=json.loads(z.stdout)
    require(result['targetTree']==spec['targetTree'],'restored tree mismatch')
    (destination/'project/evaluation/calendar-verification').mkdir(parents=True,exist_ok=True)
    for source,target in mappings:
        link=destination/source;physical=destination/target
        require(physical.resolve().is_relative_to((destination/'project').resolve()),'mapping target escaped project')
        physical.mkdir(parents=True,exist_ok=True);link.parent.mkdir(parents=True,exist_ok=True)
        require(not link.exists() and not link.is_symlink(),'mapping entry already exists')
        link.symlink_to(os.path.relpath(physical,link.parent),target_is_directory=True)
        require(link.resolve().is_relative_to(destination.resolve()),'mapping escaped workspace')
    inputs=destination/'inputs';inputs.mkdir();shutil.copyfile(member(package,spec['task']),inputs/'task.txt')
    for rel in spec['inputs']:shutil.copyfile(member(package,rel),inputs/Path(rel).name)
    out={'schema':'agentlab.portable-application-restore.v1','point':point,'targetTree':result['targetTree'],'workspace':str(destination),'project':str(destination/'project'),'task':str(inputs/'task.txt'),'caseSHA256':trusted,'actorDispatches':0,'physicalCapsuleRestored':False,'privateControllerAssetsMounted':False,'authorityClaimed':False}
    (destination/'restore-receipt.json').write_text(json.dumps(out,indent=2));return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,default=Path(__file__).parent);p.add_argument('--point',required=True);p.add_argument('--destination',type=Path,required=True);p.add_argument('--trusted-case-sha256',required=True);a=p.parse_args()
    try: print(json.dumps(restore(a.package,a.point,a.destination,a.trusted_case_sha256)))
    except Exception as e: print(json.dumps({'status':'rejected','error':str(e),'automaticRetry':False}),file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':main()
