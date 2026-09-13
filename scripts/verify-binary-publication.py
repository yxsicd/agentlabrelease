#!/usr/bin/env python3
"""Independently recover published external deliverables; never rebuild them."""
import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--manifest',type=Path,required=True)
p.add_argument('--downloads',type=Path,required=True)
p.add_argument('--receipt',type=Path,required=True)
a=p.parse_args();a.downloads.mkdir(parents=True,exist_ok=False)
rows=json.loads(a.manifest.read_text());verified=[]
for n,row in enumerate(rows):
    target=a.downloads/f'{n:04d}.hap'
    subprocess.run(['curl','--fail','--location','--silent','--show-error','--retry','4','--retry-all-errors','--output',str(target),row['uri']],check=True)
    digest=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
    observed=dict(label=row['label'],uri=row['uri'],expectedSHA256=row['sha256'],observedSHA256=digest,expectedBytes=row['bytes'],observedBytes=target.stat().st_size)
    observed['exact']=observed['expectedSHA256']==digest and observed['expectedBytes']==observed['observedBytes'];verified.append(observed)
    if not observed['exact']:break
receipt=dict(schema='agentlab.external_binary_recovery.v1',ok=len(verified)==len(rows) and all(x['exact'] for x in verified),publicationCount=len(rows),distinctContentCount=len({r['sha256'] for r in rows}),recoveries=verified,rebuilt=False,agentRedispatched=False,formalSessionFSQualified=False)
a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
assert receipt['ok'], 'Published bytes differ from captured manifest; receipt retained'
print(json.dumps({k:v for k,v in receipt.items() if k!='recoveries'}))
