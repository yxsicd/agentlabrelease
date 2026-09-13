"""Maintain complete controller compilation evidence in the development TableGit."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'))
from capture import Service

PREFIX='flywheel/harmony-v3/'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--development',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--producer-run',required=True)
    p.add_argument('--producer-revision',required=True)
    a=p.parse_args();a.root.mkdir(parents=True,exist_ok=True)
    summary=json.loads((a.evidence/'summary.json').read_text())
    config=json.loads(a.development.read_text());rpc=a.root/'rpc';rpc.mkdir(exist_ok=True)
    service=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),rpc)
    repo=config['repo'];wt={'topic_id':None}
    revision=service.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision']
    prefix='compiler-'+a.producer_run+'-'
    lineage={'producerRun':a.producer_run,'producerRevision':a.producer_revision,
             'sourceRevision':summary['materialization']['sourceRevision'],
             'captureAuthority':'operator-owned-ci-compiler-runner',
             'evidenceRunUrl':'https://github.com/yxsicd/agentlabrelease/actions/runs/'+a.producer_run}
    facts=[dict(id=prefix+'summary',kind='compilation-summary',**lineage,
                qualification=summary,fullSourceBuildQualified=summary['fullSourceBuildQualified'],
                sliceCompilationQualified=summary['sliceCompilationQualified'])]
    for phase,result in summary['phases'].items():
        facts.append(dict(id=prefix+'phase-'+phase,kind='compiler-phase',phase=phase,**lineage,**result))
    files={};byte_chunks={}
    # Native intermediate caches are not archived. Inputs/logs/receipts and final HAPs are.
    for path in sorted(a.evidence.rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(a.evidence).as_posix()
        if name.startswith('slice-input/') and any(p in {'.hvigor','node_modules','oh_modules','build'} for p in path.relative_to(a.evidence).parts):continue
        raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        file_id=prefix+'file-'+hashlib.sha256(name.encode()).hexdigest()[:20]
        chunks=[]
        for start in range(0,len(raw),3072):
            chunk=raw[start:start+3072];chunk_digest=hashlib.sha256(chunk).hexdigest()
            key='compiler-bytes-'+chunk_digest;chunks.append(key)
            byte_chunks[key]=dict(id=key,kind='compiler-byte-chunk',encoding='base64',
                                  sha256=chunk_digest,byteCount=len(chunk),value=base64.b64encode(chunk).decode())
        facts.append(dict(id=file_id,kind='compiler-file',path=name,sha256=digest,
                          byteCount=len(raw),chunkIds=chunks,
                          fileRole='final-unsigned-hap' if name.endswith('.hap') else 'input-log-or-receipt',**lineage))
        files[file_id]=(raw,chunks)
    facts.extend(byte_chunks.values())
    cases=[dict(id=prefix+'evaluation-'+key,kind='qualification',taskId='case-'+key,**lineage,
                status='typed-slice-qualified' if summary['sliceCompilationQualified'] else 'typed-slice-failed',
                compilationSummaryId=prefix+'summary',fullTaskQualified=False,subjectAgentRun=False)
           for key in ['feedback','navigation']]
    tasks=store.read(service,repo,revision,PREFIX+'evaluation_cases')
    for key in ['feedback','navigation']:
        row=dict(tasks['case-'+key]);ids=list(row.get('compilationEvidenceIds',[]))
        if prefix+'summary' not in ids:ids.append(prefix+'summary')
        row.update(compilationEvidenceIds=ids,latestCompilationQualificationId=prefix+'evaluation-'+key,
                   sliceBuildQualified=summary['sliceCompilationQualified'],fullSourceBuildQualified=summary['fullSourceBuildQualified'])
        cases.append(row)
    skills=store.read(service,repo,revision,PREFIX+'maintainer_skills');changed=[]
    for row in skills.values():
        if row.get('objectId') not in ['case-feedback','case-navigation']:continue
        row=dict(row);ids=list(row.get('compilationEvidenceIds',[]))
        if prefix+'summary' not in ids:
            ids.append(prefix+'summary')
        row['compilationEvidenceIds']=ids
        row['compilationGuidance']={'latestSummaryId':prefix+'summary','fullSourceBuildQualified':summary['fullSourceBuildQualified'],'sliceCompilationQualified':summary['sliceCompilationQualified'],'fullSourceBlocker':summary.get('fullSourceBlocker'),'consumerAndDeviceQualified':False,'next':'Inspect preparation/full-source compiler evidence and execute original consumers'}
        changed.append(row)
    for table,rows in [('program_facts',facts),('evaluation_cases',cases),('maintainer_skills',changed)]:
        existing=store.scan(service,repo,revision,PREFIX+table);ops=[]
        for row in rows:
            old=existing.get(row['id'])
            if old and old['row']==row:continue
            op=dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=old['row_version'],
                    field_updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if old['row'].get(k)!=v]) if old else dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row)
            ops.append(op)
        for start in range(0,len(ops),32):
            revision=store.transact(service,repo,wt,revision,[dict(path=PREFIX+table,operations=ops[start:start+32])],'Archive complete controller compiler evidence')
    durable=store.read(service,repo,revision,PREFIX+'program_facts')
    for file_id,(raw,chunks) in files.items():
        recovered=b''.join(base64.b64decode(durable[key]['value']) for key in chunks)
        if recovered!=raw:raise RuntimeError('Compiler file reconstruction mismatch: '+file_id)
    receipt=store.export(service,repo,revision,a.root/'export',PREFIX)
    if receipt!=store.export(service,repo,revision,a.root/'export-repeated',PREFIX):raise RuntimeError('Unstable export')
    again,changes=store.import_snapshot(service,repo,wt,a.root/'export',PREFIX)
    if again!=revision or changes:raise RuntimeError('Repeated import changed compiler evidence')
    result={'ok':True,'revision':revision,'producerRun':a.producer_run,'fileCount':len(files),
            'exactFiles':True,'stableExport':True,'repeatedImportNoChanges':True,
            'fullSourceBuildQualified':summary['fullSourceBuildQualified'],
            'sliceCompilationQualified':summary['sliceCompilationQualified']}
    (a.root/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
