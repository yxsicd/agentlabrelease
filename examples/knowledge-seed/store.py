"""AgentLab-owned business tables; no MCPGit source changes or duplicate file authority."""
import uuid

TABLES=('knowledge_skills','knowledge_nodes','knowledge_edges','knowledge_links','knowledge_tasks','knowledge_evaluations')

def read(service,repo,revision,table):
    result=service.call('table.query',dict(repo=repo,view={'kind':'committed','revision':revision},path=table,limit=1000))
    if result['truncated'] or result['dirty'] or result['revision']!=revision:
        raise RuntimeError('Knowledge read must be complete and revision-bound')
    return {r['key']:r['row'] for r in result['rows'] if not r['deleted']}

def persist(service,repo,worktree,package):
    revision=service.call('table.worktree.open',dict(repo=repo,worktree=worktree))['revision']
    for table in TABLES:
        rows=package['tables'][table]
        fields={'id':{'type':'string','required':True}}
        for row in rows:
            for key,value in row.items():
                kind='boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'array' if isinstance(value,list) else 'markdown' if key=='body' else 'string'
                fields[key]={'type':kind,'required':True}
        revision=service.call('table.create',dict(repo=repo,worktree=worktree,path=table,expected_revision=revision,definition=dict(key_field='id',fields=fields,required_fields=list(fields),indexes=[dict(name='by_'+key,field=key) for key,value in fields.items() if value['type'] in ('string','integer','boolean') and key!='title'],description='AgentLab engineering knowledge: '+table),message='Create engineering knowledge table'))['revision']
    def transact(operations):
        nonlocal revision
        txn=str(uuid.uuid4())
        result=service.call('table.transact_many',dict(repo=repo,worktree=worktree,expected_revision=revision,transaction_id=txn,idempotency_key=txn,actor=None,tables=operations,message='Knowledge seed iteration'))
        if not result['applied'] or result.get('conflicts'): raise RuntimeError('Knowledge transaction failed; preserve request')
        revision=result['revision']
    transact([dict(path=t,operations=[dict(op='insert',operation_id=str(uuid.uuid4()),key=r['id'],row=r) for r in package['tables'][t]]) for t in TABLES if package['tables'][t]])
    baseline=revision
    grouped={}
    for update in package['updates']:
        grouped.setdefault(update['table'],[]).append(dict(op='update',operation_id=str(uuid.uuid4()),key=update['id'],expected_row_version=1,field_updates=[dict(op='set',field=k,value=v) for k,v in update['fields'].items()]))
    transact([dict(path=t,operations=ops) for t,ops in grouped.items()])
    return dict(baselineRevision=baseline,updatedRevision=revision)

def verify(service,repo,package,cuts):
    expected={t:{r['id']:r.copy() for r in package['tables'][t]} for t in TABLES}
    for t in TABLES:
        assert read(service,repo,cuts['baselineRevision'],t)==expected[t]
    for update in package['updates']: expected[update['table']][update['id']].update(update['fields'])
    for t in TABLES: assert read(service,repo,cuts['updatedRevision'],t)==expected[t]
    return dict(**cuts,exactHistoricalRows=True,exactUpdatedRows=True,stableSkillIds=True,fullWhiteboxQualified=False)
