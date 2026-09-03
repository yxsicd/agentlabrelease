#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,pathlib,urllib.request

def read_url(url:str)->bytes:
    req=urllib.request.Request(url,headers={'User-Agent':'agentlab-offline-closure/1'})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read()

def validate(blob:bytes,meta:dict,label:str):
    if len(blob)!=meta['bytes']: raise SystemExit(f'{label}: byte count mismatch')
    got=hashlib.sha256(blob).hexdigest()
    if got!=meta['sha256']: raise SystemExit(f'{label}: sha256 mismatch')

def resolve(path:pathlib.Path)->dict:
    c=json.loads(path.read_text())
    if c.get('schema')!='agentlab.offline_closure.v1': raise SystemExit('unsupported closure schema')
    assets=list(c['directAssets'])
    base='https://github.com/yxsicd/agentlabrelease/releases/download'
    manifests=[]
    for ref in c['manifestRefs']:
        meta=ref['manifest']; blob=read_url(meta['url']); validate(blob,meta,ref['group']+' manifest')
        d=json.loads(blob); manifests.append({'group':ref['group'],**meta})
        if ref['adapter']=='single-artifact-v1': rows=[d]
        elif ref['adapter']=='assets-array-v1': rows=d['assets']
        else: raise SystemExit('unsupported manifest adapter')
        for row in rows:
            assets.append({'group':ref['group'],'filename':row['filename'],'url':f"{base}/{ref['releaseTag']}/{row['filename']}",'bytes':row['bytes'],'sha256':row['sha256']})
    seen=set()
    for a in assets:
        key=(a['url'],a['sha256'])
        if key in seen: raise SystemExit('duplicate resolved asset')
        seen.add(key)
    return {'schema':'agentlab.offline_closure_resolved.v1','platform':c['platform'],'sourceClosureSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'assets':assets,'manifests':manifests,'totalBytes':sum(x['bytes'] for x in assets),'credentialsIncluded':False}

def verify_cache(lock:dict,cache:pathlib.Path):
    missing=[]
    for a in lock['assets']:
        p=cache/a['filename']
        if not p.is_file() or p.stat().st_size!=a['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=a['sha256']: missing.append(a['filename'])
    print(json.dumps({'schema':'agentlab.offline_cache_verify.v1','ok':not missing,'missingOrInvalid':missing,'assetCount':len(lock['assets'])},sort_keys=True))
    if missing: raise SystemExit(1)

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    r=sub.add_parser('resolve'); r.add_argument('--closure',type=pathlib.Path,required=True); r.add_argument('--out',type=pathlib.Path,required=True)
    v=sub.add_parser('verify-cache'); v.add_argument('--lock',type=pathlib.Path,required=True); v.add_argument('--cache',type=pathlib.Path,required=True)
    a=ap.parse_args()
    if a.cmd=='resolve':
        d=resolve(a.closure); a.out.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n'); print(json.dumps({'ok':True,'assetCount':len(d['assets']),'totalBytes':d['totalBytes']},sort_keys=True))
    else: verify_cache(json.loads(a.lock.read_text()),a.cache)
if __name__=='__main__': main()
