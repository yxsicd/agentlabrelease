"""Import explicitly separated analytical assets and replay context heads into Git history."""
import argparse,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service

def batches(pending):
    group=[];size=0
    for name,op in pending:
        encoded=len(json.dumps(op,ensure_ascii=False).encode())
        if group and (len(group)>=512 or size+encoded>800000):yield group;group=[];size=0
        group.append((name,op));size+=encoded
    if group:yield group

def apply(s,repo,wt,rev,prefix,pending,message):
    for batch in batches(pending):
        grouped={}
        for name,op in batch:grouped.setdefault(name,[]).append(op)
        rev=store.transact(s,repo,wt,rev,[dict(path=prefix+n,operations=ops) for n,ops in grouped.items()],message)
    return rev

def definition(fields,indexes):
    return dict(key_field='id',fields={k:dict(type=v,required=k=='id') for k,v in fields.items()},required_fields=['id'],indexes=[dict(name='by_'+k,field=k) for k in indexes],description='AgentLab instance context history')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--development',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);p.add_argument('--prefix',required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--create-tables',action='store_true');p.add_argument('--replay-context',action='store_true');a=p.parse_args();a.evidence.mkdir();config=json.loads(a.development.read_text());s=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),a.evidence);repo=config['repo'];wt={'topic_id':None};rev=s.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision'];manifest=json.loads((a.directory/'export.json').read_text());tables={};pending=[]
    for name,meta in manifest['tables'].items():
        raw=(a.directory/(name+'.jsonl')).read_bytes();assert hashlib.sha256(raw).hexdigest()==meta['sha256'];rows=store.jsonl_rows(raw);assert len(rows)==meta['rowCount'];assert all(r['assetClass']==manifest['assetClass'] for r in rows);tables[name]={r['id']:r for r in rows};assert len(tables[name])==len(rows)
        if a.create_tables:rev=s.call('table.create',dict(repo=repo,worktree=wt,path=a.prefix+name,expected_revision=rev,definition=meta['definition'],message='Create '+manifest['assetClass']+' '+name))['revision']
        current=store.scan(s,repo,rev,a.prefix+name)
        for key,row in tables[name].items():
            old=current.get(key)
            if old and old['row']==row:continue
            if old:op=dict(op='update',operation_id=str(uuid.uuid4()),key=key,expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/'+k.replace('~','~0').replace('/','~1'),value=v) for k,v in row.items() if old['row'].get(k)!=v]+[dict(op='unset',field='/'+k.replace('~','~0').replace('/','~1')) for k in old['row'] if k not in row])
            else:op=dict(op='insert',operation_id=str(uuid.uuid4()),key=key,row=row)
            pending.append((name,op))
    rev=apply(s,repo,wt,rev,a.prefix,pending,'Import separated analytical assets')
    for name,rows in tables.items():assert store.read(s,repo,rev,a.prefix+name)==rows
    replay=[]
    if a.replay_context:
        assert manifest['assetClass']=='evaluation-instance'
        if a.create_tables:
            defs={'context_heads':definition(dict(id='string',assetClass='string',runId='string',attemptId='string',direction='string',ordinal='integer',contentVersionId='string',role='string',message='object'),['attemptId','direction','ordinal']), 'context_commits':definition(dict(id='string',assetClass='string',runId='string',contextVersionId='string',revision='string'),['contextVersionId'])}
            for name,d in defs.items():rev=s.call('table.create',dict(repo=repo,worktree=wt,path=a.prefix+name,expected_revision=rev,definition=d,message='Create context replay '+name))['revision']
        heads=store.scan(s,repo,rev,a.prefix+'context_heads');commits=store.read(s,repo,rev,a.prefix+'context_commits')
        for version in sorted(tables['context_versions'].values(),key=lambda r:r['sequence']):
            key=version['id'];stem=version['attemptId']+'-'+version['direction']+'-';expected={}
            for ordinal,content in enumerate(version['messageIds']):
                body=tables['message_contents'][content];identifier=stem+str(ordinal);expected[identifier]=dict(id=identifier,assetClass='evaluation-instance',runId=version['runId'],attemptId=version['attemptId'],direction=version['direction'],ordinal=ordinal,contentVersionId=content,role=body['role'],message=body['message'])
            if key in commits:cut=commits[key]['revision']
            else:
                ops=[]
                for identifier,row in expected.items():
                    old=heads.get(identifier)
                    if old and old['row']==row:continue
                    if old:op=dict(op='update',operation_id=str(uuid.uuid4()),key=identifier,expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if old['row'].get(k)!=v])
                    else:op=dict(op='insert',operation_id=str(uuid.uuid4()),key=identifier,row=row)
                    ops.append(('context_heads',op))
                for identifier,old in heads.items():
                    if identifier.startswith(stem) and identifier not in expected:ops.append(('context_heads',dict(op='delete',operation_id=str(uuid.uuid4()),key=identifier,expected_row_version=old['row_version'])))
                rev=apply(s,repo,wt,rev,a.prefix,ops,'Restore context '+key+' by stable logical message rows');cut=rev;heads=store.scan(s,repo,rev,a.prefix+'context_heads');record=dict(id=key,assetClass='evaluation-instance',runId=version['runId'],contextVersionId=key,revision=cut);rev=apply(s,repo,wt,rev,a.prefix,[('context_commits',dict(op='insert',operation_id=str(uuid.uuid4()),key=key,row=record))],'Bind request context to durable Git cut');commits[key]=record
            historical=store.read(s,repo,cut,a.prefix+'context_heads');actual={k:r for k,r in historical.items() if k.startswith(stem)};assert actual==expected;replay.append(dict(contextVersionId=key,revision=cut,exact=True))
    result=dict(ok=True,assetClass=manifest['assetClass'],repository=repo,prefix=a.prefix,revision=rev,insertedOrUpdatedRows=len(pending),allTablesExact=True,contextHistory=replay)
    (a.evidence/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
