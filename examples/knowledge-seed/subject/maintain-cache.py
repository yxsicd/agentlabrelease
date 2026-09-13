import sys,json,uuid
from pathlib import Path
import argparse
p=argparse.ArgumentParser(description='Maintain a Rust-prepared cross-file candidate and archive generic SQL in development TableGit.')
p.add_argument('--development',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--prefix',required=True);p.add_argument('--create-tables',action='store_true')
a=p.parse_args();repo=Path(__file__).resolve().parents[3];sys.path.insert(0,str(repo/'examples/knowledge-seed'));import store
sys.path.insert(0,str(repo/'examples/tablegit-session'));from capture import Service
# Fresh namespace keeps previously assessed snapshots immutable.
e=a.root;e.mkdir();c=json.loads(a.development.read_text());s=Service(c['url'],Path(c['authorizationFile']).read_text().strip(),e);r=c['repo'];wt={'topic_id':None};prefix=a.prefix;rev=s.call('table.worktree.open',dict(repo=r,worktree=wt))['revision'];tables={t:store.jsonl_rows((a.prepared/f'{t}.jsonl').read_bytes()) for t in store.TABLES};
if a.create_tables:rev=store.create(s,r,wt,rev,tables,prefix)

changed=0
for table,rows in tables.items():
 current=store.scan(s,r,rev,prefix+table);pending=[]
 for row in rows:
  old=current.get(row['id'])
  if old:
   updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if old['row'].get(k)!=v]
   if not updates:continue
   op=dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=old['row_version'],field_updates=updates)
  else:op=dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row)
  pending.append(op)
 changed+=len(pending)
 for start in range(0,len(pending),128):
  rev=store.transact(s,r,wt,rev,[dict(path=prefix+table,operations=pending[start:start+128])],'Maintain Rust-derived cross-file candidate knowledge')

cut=rev
paths=['common/src/main/ets/storagemanager/PreferenceManager.ets','common/src/main/ets/storagemanager/PreferenceCacheHelper.ets','features/devpractices/src/main/ets/service/SampleService.ets','features/devpractices/src/main/ets/model/SampleModel.ets'];quoted=','.join("'"+x+"'" for x in paths)
queries=[('analysis-cache-program-v1','program_facts',"SELECT json_extract(row_json,'$.id') AS id,json_extract(row_json,'$.path') AS path,json_extract(row_json,'$.owner') AS owner,json_extract(row_json,'$.targetExpression') AS expression,json_extract(row_json,'$.span.startLine') AS line FROM facts WHERE json_extract(row_json,'$.kind')='call' AND json_extract(row_json,'$.path') IN ("+quoted+") ORDER BY path,line,id",'Syntax calls expose write/flush and model propagation; targets are unresolved syntax, not compiler dataflow.'),('analysis-cache-semantic-v1','maintainer_skills',"SELECT json_extract(row_json,'$.id') AS id,json_extract(row_json,'$.stage') AS stage,json_extract(row_json,'$.methodSkillId') AS method,json_extract(row_json,'$.body') AS guidance FROM facts WHERE json_extract(row_json,'$.objectId')='case-cache-durability-candidate-v1' ORDER BY stage,id",'Six target-instance Skills encode semantic responsibilities, grounded in source facts and method revisions.')]
analyses=[];archived=store.read(s,r,rev,prefix+'program_facts')
for identifier,table,code,interpretation in queries:
 old=archived.get(identifier)
 if changed==0 and old and old['code']==code:
  analyses.append(old);continue
 request=dict(bindings=[dict(alias='facts',repo=r,path=prefix+table,revision=cut)],sql=code,parameters=[]);result=s.call('table.relations.query',request);assert result['rows'];analyses.append(dict(id=identifier,kind='analysis',assetClass='reusable-knowledge',sourceRevision='7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6',code=code,request=request,result=result,interpretation=interpretation))
current=store.scan(s,r,rev,prefix+'program_facts');ops=[]
for row in analyses:
 old=current.get(row['id'])
 if old:
  updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if old['row'].get(k)!=v]
  if updates:ops.append(dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=old['row_version'],field_updates=updates))
 else:ops.append(dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row))
if ops:rev=store.transact(s,r,wt,rev,[dict(path=prefix+'program_facts',operations=ops)],'Archive exact generic semantic and program SQL evidence')
old=store.scan(s,r,rev,prefix+'evaluation_cases')['case-cache-durability-candidate-v1'];identifiers=[row['id'] for row in analyses]
if old['row'].get('analysisIds')!=identifiers:
 rev=store.transact(s,r,wt,rev,[dict(path=prefix+'evaluation_cases',operations=[dict(op='update',operation_id=str(uuid.uuid4()),key=old['key'],expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/analysisIds',value=identifiers)])])],'Bind candidate to both archived analyses')

receipt=store.export(s,r,rev,e/'export',prefix);receipt['preparedRowsChanged']=changed;receipt['queryInputRevision']=analyses[0]['request']['bindings'][0]['revision'];receipt['analysisRows']={row['id']:len(row['result']['rows']) for row in analyses};(e/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
