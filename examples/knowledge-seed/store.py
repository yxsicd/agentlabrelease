"""TableGit is development authority; JSONL files are exact-cut exchange snapshots."""
import hashlib
import json
from pathlib import Path
import uuid

TABLES=('maintainer_skills','program_facts','evaluation_cases')
SQL="""SELECT json_extract(e.row_json,'$.sourceId') AS caller,
 json_extract(n.row_json,'$.id') AS candidate_target,
 json_extract(n.row_json,'$.path') AS target_path
 FROM facts e JOIN facts n
 ON json_extract(e.row_json,'$.targetName')=json_extract(n.row_json,'$.symbol')
 WHERE json_extract(e.row_json,'$.kind')='call'
 AND json_extract(n.row_json,'$.kind')='symbol'
 ORDER BY caller,candidate_target"""

def scan(service,repo,revision,table):
    rows={};offset=0
    while True:
        result=service.call('table.query',dict(repo=repo,view={'kind':'committed','revision':revision},path=table,offset=offset,limit=1000))
        if result['dirty'] or result['revision']!=revision:
            raise RuntimeError('Knowledge scan must stay at one committed cut')
        rows.update({r['key']:r for r in result['rows'] if not r['deleted']})
        if not result['truncated']: return rows
        if not result['rows']: raise RuntimeError('Table page cannot make progress')
        offset+=len(result['rows'])

def read(service,repo,revision,table):
    return {key:item['row'] for key,item in scan(service,repo,revision,table).items()}

def transact(service,repo,worktree,revision,tables,message):
    txn=str(uuid.uuid4())
    result=service.call('table.transact_many',dict(repo=repo,worktree=worktree,expected_revision=revision,transaction_id=txn,idempotency_key=txn,actor=None,tables=tables,message=message))
    if not result['applied'] or result.get('conflicts'): raise RuntimeError('Knowledge transaction failed; preserve request')
    return result['revision']

def insert(service,repo,worktree,revision,tables):
    pending=[(t,row) for t in TABLES for row in tables[t]]
    for start in range(0,len(pending),32):
        group={}
        for t,row in pending[start:start+32]:
            group.setdefault(t,[]).append(dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row))
        revision=transact(service,repo,worktree,revision,[dict(path=t,operations=ops) for t,ops in group.items()],'Import knowledge rows')
    return revision

def create(service,repo,worktree,revision,tables,prefix=''):
    for table in TABLES:
        fields={'id':{'type':'string','required':True}}
        for row in tables[table]:
            for key,value in row.items():
                kind='boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'markdown' if key=='body' else 'string'
                fields[key]={'type':kind,'required':key=='id'}
        if table=='program_facts':
            fields.update({k:{'type':v,'required':False} for k,v in [('code','text'),('request','object'),('result','object'),('interpretation','text')]})
        if table=='evaluation_cases': fields['analysisIds']={'type':'array','required':False}
        revision=service.call('table.create',dict(repo=repo,worktree=worktree,path=prefix+table,expected_revision=revision,definition=dict(key_field='id',fields=fields,required_fields=['id'],indexes=[dict(name='by_'+key,field=key) for key,value in fields.items() if value['type'] in ('string','integer','boolean') and key!='title'],description='AgentLab engineering knowledge: '+table),message='Create engineering knowledge table'))['revision']
    return revision

def persist(service,repo,worktree,package):
    revision=service.call('table.worktree.open',dict(repo=repo,worktree=worktree))['revision']
    revision=create(service,repo,worktree,revision,package['tables'])
    revision=insert(service,repo,worktree,revision,package['tables'])
    baseline=revision
    grouped={}
    for update in package['updates']:
        grouped.setdefault(update['table'],[]).append(dict(op='update',operation_id=str(uuid.uuid4()),key=update['id'],expected_row_version=1,field_updates=[dict(op='set',field='/'+k.replace('~','~0').replace('/','~1'),value=v) for k,v in update['fields'].items()]))
    revision=transact(service,repo,worktree,revision,[dict(path=t,operations=ops) for t,ops in grouped.items()],'Maintain stable Skill rows')
    return dict(baselineRevision=baseline,updatedRevision=revision)

def verify(service,repo,package,cuts):
    expected={t:{r['id']:r.copy() for r in package['tables'][t]} for t in TABLES}
    for t in TABLES: assert read(service,repo,cuts['baselineRevision'],t)==expected[t]
    for update in package['updates']: expected[update['table']][update['id']].update(update['fields'])
    for t in TABLES: assert read(service,repo,cuts['updatedRevision'],t)==expected[t]
    return dict(**cuts,exactHistoricalRows=True,exactUpdatedRows=True,stableSkillIds=True,fullWhiteboxQualified=False)

def export(service,repo,revision,destination,prefix=''):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    receipt=dict(schema='agentlab.knowledge_export.v1',repository=repo,revision=revision,tables={})
    if prefix: receipt['tablePrefix']=prefix
    for table in TABLES:
        rows=read(service,repo,revision,prefix+table)
        raw=''.join(json.dumps(rows[k],ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for k in sorted(rows)).encode()
        (destination/(table+'.jsonl')).write_bytes(raw)
        receipt['tables'][table]=dict(rowCount=len(rows),sha256=hashlib.sha256(raw).hexdigest())
    (destination/'export.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

def load_snapshot(directory):
    directory=Path(directory);receipt=json.loads((directory/'export.json').read_text());tables={}
    for table in TABLES:
        raw=(directory/(table+'.jsonl')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==receipt['tables'][table]['sha256']
        rows=[json.loads(line) for line in raw.splitlines()];assert len(rows)==receipt['tables'][table]['rowCount']
        assert len({r['id'] for r in rows})==len(rows)
        tables[table]=rows
    return tables

def analyze(service,repo,worktree,revision):
    request=dict(bindings=[dict(alias='facts',repo=repo,path='program_facts',revision=revision)],sql=SQL,parameters=[])
    result=service.call('table.relations.query',request)
    # Store exact query/code, input cut, typed result and limits/coverage receipt.
    row=dict(id='analysis-call-candidates',kind='analysis',sourceRevision=revision,code=SQL,request=request,result=result,interpretation='Syntactic name-match candidates, not resolved runtime calls')
    revision=transact(service,repo,worktree,revision,[dict(path='program_facts',operations=[dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row)])],'Archive search-as-code analysis')
    tasks=read(service,repo,revision,'evaluation_cases')
    operations=[dict(op='update',operation_id=str(uuid.uuid4()),key=k,expected_row_version=1,field_updates=[dict(op='set',field='/analysisIds',value=[row['id']])]) for k,r in tasks.items() if r['kind']=='task']
    if operations: revision=transact(service,repo,worktree,revision,[dict(path='evaluation_cases',operations=operations)],'Bind cases to archived analysis')
    return revision,result

def import_snapshot(service,repo,worktree,directory,prefix='',create_tables=False):
    tables=load_snapshot(directory)
    revision=service.call('table.worktree.open',dict(repo=repo,worktree=worktree))['revision']
    if create_tables: revision=create(service,repo,worktree,revision,tables,prefix)
    pending=[]
    for table in TABLES:
        path=prefix+table
        existing=scan(service,repo,revision,path)
        desired={r['id']:r for r in tables[table]}
        for key,row in desired.items():
            previous=existing.get(key)
            if previous is None: op=dict(op='insert',operation_id=str(uuid.uuid4()),key=key,row=row)
            elif previous['row']==row: continue
            else:
                updates=[dict(op='set',field='/'+k.replace('~','~0').replace('/','~1'),value=v) for k,v in row.items() if previous['row'].get(k)!=v]
                updates += [dict(op='unset',field='/'+k.replace('~','~0').replace('/','~1')) for k in previous['row'] if k not in row]
                op=dict(op='update',operation_id=str(uuid.uuid4()),key=key,expected_row_version=previous['row_version'],field_updates=updates)
            pending.append((path,op))
        for key,previous in existing.items():
            if key not in desired: pending.append((path,dict(op='delete',operation_id=str(uuid.uuid4()),key=key,expected_row_version=previous['row_version'])))
    for start in range(0,len(pending),32):
        grouped={}
        for path,op in pending[start:start+32]: grouped.setdefault(path,[]).append(op)
        revision=transact(service,repo,worktree,revision,[dict(path=t,operations=ops) for t,ops in grouped.items()],'Import fixed knowledge snapshot')
    return revision,len(pending)

def roundtrip(service,repo,worktree,revision,destination):
    original=export(service,repo,revision,destination)
    tables=load_snapshot(destination)
    prefix='roundtrip/'
    current,changed=import_snapshot(service,repo,worktree,destination,prefix,True)
    for table in TABLES: assert read(service,repo,current,prefix+table)=={r['id']:r for r in tables[table]}
    repeated_revision,repeated_changes=import_snapshot(service,repo,worktree,destination,prefix)
    assert repeated_revision==current and repeated_changes==0
    repeated=export(service,repo,revision,Path(destination).parent/'export-repeated')
    assert original==repeated
    return current,dict(sourceRevision=revision,importRevision=current,exactRows=True,stableExport=True,repeatedImportNoChanges=True,importedRows=changed)

if __name__=='__main__':
    import argparse,sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'tablegit-session'))
    from capture import Service
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['import','export','analyze']);p.add_argument('--url',required=True);p.add_argument('--authorization-file',type=Path,required=True);p.add_argument('--repo',required=True);p.add_argument('--topic');p.add_argument('--revision');p.add_argument('--directory',type=Path,required=True);p.add_argument('--create-tables',action='store_true');p.add_argument('--evidence-directory',type=Path);a=p.parse_args()
    a.directory.mkdir(parents=True,exist_ok=True)
    import tempfile
    evidence=a.evidence_directory or Path(tempfile.mkdtemp(prefix='agentlab-knowledge-rpc-'))
    evidence.mkdir(parents=True,exist_ok=True)
    service=Service(a.url,a.authorization_file.read_text().strip(),evidence)
    worktree={'topic_id':a.topic}
    if a.mode=='import': result=import_snapshot(service,a.repo,worktree,a.directory,create_tables=a.create_tables)
    elif a.mode=='export':
        if not a.revision: p.error('export requires --revision')
        result=export(service,a.repo,a.revision,a.directory)
    else:
        if not a.revision: p.error('analyze requires --revision')
        result=analyze(service,a.repo,worktree,a.revision)
    print(json.dumps(dict(result=result,evidenceDirectory=str(evidence)),ensure_ascii=False))
