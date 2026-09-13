"""Archive full runtime tables before exporting compact, reusable knowledge seeds.

The three seed tables hold Skills, analysis knowledge and task definitions.
Assessment observations and content-addressed bytes remain in TableGit runtime
business tables, with a separately published, stable-order exchange snapshot.
"""
import argparse,base64,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service
from ingest import PREFIX,OBS,PAYLOAD

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--development',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--runtime-archive-url',required=True);a=p.parse_args();a.root.mkdir();(a.root/'rpc').mkdir();config=json.loads(a.development.read_text());s=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),a.root/'rpc');repo=config['repo'];wt={'topic_id':None};rev=s.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision'];runtime=a.root/'runtime';runtime.mkdir();
 # Earlier compiler captures follow the same separation; retain full old bytes.
 legacy={key:row for key,row in store.read(s,repo,rev,PREFIX+'program_facts').items() if row.get('kind') in ('compiler-file','compiler-byte-chunk')}
 for name in (OBS,PAYLOAD):
  existing=store.scan(s,repo,rev,PREFIX+name);ops=[]
  for key,row in legacy.items():
   target=PAYLOAD if row['kind']=='compiler-byte-chunk' else OBS
   if target!=name:continue
   old=existing.get(key)
   if old:assert old['row']==row
   else:ops.append(dict(op='insert',operation_id=str(uuid.uuid4()),key=key,row=row))
  for start in range(0,len(ops),32):rev=store.transact(s,repo,wt,rev,[dict(path=PREFIX+name,operations=ops[start:start+32])],'Archive earlier compiler raw evidence in runtime tables')
 receipt=dict(schema='agentlab.construction_runtime_export.v1',repository=repo,revision=rev,tablePrefix=PREFIX,tables={})
 tables={name:store.read(s,repo,rev,PREFIX+name) for name in (OBS,PAYLOAD)}
 for name,rows in tables.items():
  raw=''.join(json.dumps(rows[key],ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for key in sorted(rows)).encode();(runtime/(name+'.jsonl')).write_bytes(raw);definition=s.call('table.query',dict(repo=repo,view={'kind':'committed','revision':rev},path=PREFIX+name,offset=0,limit=1))['definition'];receipt['tables'][name]=dict(rowCount=len(rows),sha256=hashlib.sha256(raw).hexdigest(),keyField='id',definition=definition)
 (runtime/'export.json').write_text(json.dumps(receipt,indent=2)+'\n')
 for row in tables[OBS].values():
  if row.get('kind')=='compiler-file':
   raw=b''.join(base64.b64decode(tables[PAYLOAD][key]['value']) for key in row['chunkIds']);assert len(raw)==row['byteCount'] and hashlib.sha256(raw).hexdigest()==row['sha256']
 # Read back every exported row before relocating duplicate historical seed data.
 for name in tables:assert {r['id']:r for r in store.jsonl_rows((runtime/(name+'.jsonl')).read_bytes())}==tables[name]
 pending=[];findings=[];existing_findings=store.scan(s,repo,rev,PREFIX+'program_facts')
 for table in ('program_facts','evaluation_cases'):
  existing=store.scan(s,repo,rev,PREFIX+table)
  for key,old in existing.items():
   if key.startswith(('subject-','evidence-bytes-')) or key in legacy:
    target=PAYLOAD if key.startswith(('evidence-bytes-','compiler-bytes-')) else OBS
    assert key in tables[target],('No durable runtime copy',key)
    pending.append((table,dict(op='delete',operation_id=str(uuid.uuid4()),key=key,expected_row_version=old['row_version'])))
 for row in tables[OBS].values():
  if row.get('kind')!='assessment-summary':continue
  ref=dict(repository=repo,table=PREFIX+OBS,id=row['id'],revision=receipt['revision'],archiveUrl=a.runtime_archive_url)
  finding=dict(id='finding-'+('feedback' if row['taskId']=='case-feedback-subject-v1' else 'navigation')+'-'+row['producerRun'],kind='assessment-finding',producerRun=row['producerRun'],producerRevision=row['producerRevision'],sourceRevision=row['sourceRevision'],taskId=row['taskId'],harnessCompleted=row['harnessCompleted'],subjectTaskSucceeded=row['subjectTaskSucceeded'],formalSessionFSForkQualified=False,scope=row.get('assessmentScope','Actual navigation controller/caller methods, full phone compile and selected-source fresh-Agent fork'),runtimeEvidenceRef=ref)
  old=existing_findings.get(finding['id'])
  if old is None:pending.append(('program_facts',dict(op='insert',operation_id=str(uuid.uuid4()),key=finding['id'],row=finding)))
  elif old['row']!=finding:pending.append(('program_facts',dict(op='update',operation_id=str(uuid.uuid4()),key=finding['id'],expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/'+k,value=v) for k,v in finding.items() if old['row'].get(k)!=v])))
  findings.append(finding)
 for key,old in existing_findings.items():
  if old['row'].get('kind') not in ('compiler-phase','compilation-summary'):continue
  pending.append(('program_facts',dict(op='update',operation_id=str(uuid.uuid4()),key=key,expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/runtimeArchiveRef',value=dict(repository=repo,observationTable=PREFIX+OBS,payloadTable=PREFIX+PAYLOAD,revision=receipt['revision'],archiveUrl=a.runtime_archive_url,producerRun=old['row']['producerRun']))])))
 for key,old in store.scan(s,repo,rev,PREFIX+'maintainer_skills').items():
  row=old['row']
  if row.get('objectId')not in ('case-navigation-subject-v1','case-feedback-subject-v1'):continue
  refs=[dict(repository=repo,table=PREFIX+OBS,id=k,revision=receipt['revision'],archiveUrl=a.runtime_archive_url) for k in row['evaluationEvidenceIds']]
  guidance=dict(row['evaluationGuidance']);guidance['latestSummaryRef']=next(ref for ref in refs if ref['id']==guidance['latestSummaryId'])
  pending.append(('maintainer_skills',dict(op='update',operation_id=str(uuid.uuid4()),key=key,expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/evaluationEvidenceRefs',value=refs),dict(op='set',field='/evaluationGuidance',value=guidance),dict(op='set',field='/factIds',value=list(dict.fromkeys(row.get('factIds',[]))))])))
 for start in range(0,len(pending),256):
  grouped={}
  for table,op in pending[start:start+256]:grouped.setdefault(table,[]).append(op)
  rev=store.transact(s,repo,wt,rev,[dict(path=PREFIX+t,operations=ops) for t,ops in grouped.items()],'Keep reusable seeds compact; runtime evidence durably archived')
 exported=store.export(s,repo,rev,a.root/'knowledge',PREFIX);assert exported==store.export(s,repo,rev,a.root/'knowledge-repeated',PREFIX);assert store.import_snapshot(s,repo,wt,a.root/'knowledge',PREFIX)==(rev,0)
 result=dict(ok=True,knowledgeRevision=rev,runtimeExport=receipt,knowledgeExport=exported,fullRuntimeRowsPreserved=True,stableExport=True,reimportUnchanged=True,findings=findings);(a.root/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
