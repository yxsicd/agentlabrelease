#!/usr/bin/env python3
"""Fetch full official SWE seeds and bind content; no reference patch enters subject input."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request


def digest(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def fetch(catalog, selected, output):
    expected={r['instanceId']:r for r in catalog['cases'] if r['instanceId'] in selected}
    if set(expected)!=set(selected): raise ValueError('unknown seed')
    output.mkdir(parents=True,exist_ok=True)
    found={}
    for offset in [0,100,200]:
        query=urllib.parse.urlencode(dict(dataset=catalog['dataset'],config='default',split=catalog['split'],offset=offset,length=100))
        url='https://datasets-server.huggingface.co/rows?'+query
        raw=urllib.request.urlopen(url,timeout=60).read()
        (output/f'dataset-page-{offset}.json').write_bytes(raw)
        for entry in json.loads(raw)['rows']:
            row=entry['row'];id=row['instance_id']
            if id not in expected: continue
            seed=expected[id]
            if row['base_commit']!=seed['baseCommit'] or digest(row)!=seed['sourceRecordSha256']:
                raise ValueError('official seed content differs: '+id)
            path=output/id;path.mkdir()
            (path/'official.json').write_text(json.dumps(row,indent=2)+'\n')
            (path/'task.txt').write_text(row['problem_statement'])
            (path/'reference.patch').write_text(row['patch'])
            (path/'tests.patch').write_text(row['test_patch'])
            found[id]=row
    if set(found)!=set(expected): raise ValueError('official seed missing')
    (output/'seed-receipt.json').write_text(json.dumps(dict(schema='agentlab.swe_seed_receipt.v1',dataset=catalog['dataset'],seeds=[dict(instanceId=id,sourceRecordSha256=digest(row),baseCommit=row['base_commit']) for id,row in found.items()]),indent=2)+'\n')
    return found


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--instance',action='append')
    a=p.parse_args();catalog=json.loads(Path(__file__).with_name('catalog.json').read_text())
    fetch(catalog,a.instance or [r['instanceId'] for r in catalog['cases']],a.output)
