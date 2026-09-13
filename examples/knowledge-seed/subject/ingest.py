"""Capture full assessment evidence in runtime tables; knowledge seeds retain feedback."""
import argparse,base64,hashlib,json,sys,uuid
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service
PREFIX='flywheel/harmony-v3/'
OBS='runtime_observations'
PAYLOAD='runtime_payload_chunks'
def gateway_phases(evidence):
 lifecycles=[]
 for path in sorted(evidence.glob('*/*-lifecycle.json')):
  row=json.loads(path.read_text())
  if row.get('startedAt') and row.get('endedAt'):
   lifecycles.append((path.relative_to(evidence).as_posix(),row))
 result={}
 for path in sorted(evidence.glob('*/gateway/*.status.json')):
  receipt=json.loads(path.read_text());participant=path.relative_to(evidence).parts[0]
  started=datetime.fromisoformat(receipt['startedAt'])
  matches=[(name,row) for name,row in lifecycles if name.split('/')[0]==participant and datetime.fromisoformat(row['startedAt'])<=started<=datetime.fromisoformat(row['endedAt'])]
  result[(participant,int(path.name.split('.')[0]))]=dict(phase=matches[0][1]['label'] if len(matches)==1 else None,phaseAttribution='supervisor-lifecycle-interval' if len(matches)==1 else 'ambiguous' if matches else 'unmatched',phaseReceiptPath=path.relative_to(evidence).as_posix(),phaseLifecyclePaths=[name for name,_ in matches])
 return result
def assessment_guidance(previous,refs,summary_id,summary,scope,stage_next,run):
 previous_id=previous.get('latestSummaryId')
 if previous_id and int(previous_id.split('-')[1])>int(run):
  return {**previous,'stageNext':stage_next}
 guidance=dict(previous) if previous_id==summary_id else {}
 guidance.update(stageNext=stage_next,latestSummaryId=summary_id,subjectTaskSucceeded=summary['subjectTaskSucceeded'],harnessCompleted=summary['ok'],scope=scope,next='Diagnose failed Agent outcomes from gateway/source evidence; formal SessionFS and device remain separate')
 guidance['latestSummaryRef']=next(ref for ref in refs if ref['id']==summary_id)
 return guidance

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--development',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--revision',required=True);p.add_argument('--create-runtime-tables',action='store_true');a=p.parse_args();a.root.mkdir();(a.root/'rpc').mkdir();config=json.loads(a.development.read_text());s=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),a.root/'rpc');repo=config['repo'];wt={'topic_id':None};rev=s.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision'];summary=json.loads((a.evidence/'summary.json').read_text());task_id=json.loads((a.evidence/'frozen-task.json').read_text())['id'];assessment_name='feedback' if task_id=='case-feedback-subject-v1' else 'navigation';scope=summary.get('assessmentScope','Actual controller/caller methods and full phone compile; source-only fresh-Agent branch');pre='subject-'+a.run+'-';lineage=dict(producerRun=a.run,producerRevision=a.revision,taskId=task_id,sourceRevision=summary['sourceRevision'],captureAuthority='supervisor-owned-collector',evidenceRunUrl='https://github.com/yxsicd/agentlabrelease/actions/runs/'+a.run)
 phase_map=gateway_phases(a.evidence)
 facts=[dict(id=pre+'summary',kind='assessment-summary',assessmentScope=scope,harnessCompleted=summary['ok'],subjectTaskSucceeded=summary['subjectTaskSucceeded'],sourceForkQualified=summary['sourceForkQualified'],formalSessionFSForkQualified=False,calibration=summary.get('calibration'),phaseIds=[pre+'phase-'+x for x in summary['phases']],**lineage)];chunks={};files={}
 for path in sorted(a.evidence.rglob('*')):
  if not path.is_file():continue
  name=path.relative_to(a.evidence).as_posix();raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();ids=[]
  for start in range(0,len(raw),3072):
   data=raw[start:start+3072];sha=hashlib.sha256(data).hexdigest();key='evidence-bytes-'+sha;ids.append(key);chunks[key]=dict(id=key,kind='evidence-byte-chunk',encoding='base64',sha256=sha,byteCount=len(data),value=base64.b64encode(data).decode())
  role='gateway-wire' if '/gateway/' in name else 'participant-adapter-events' if name.endswith('events.jsonl') or name.endswith('pi-session.jsonl') else 'supervisor-input-outcome'
  key=pre+'file-'+hashlib.sha256(name.encode()).hexdigest()[:20]
  facts.append(dict(id=key,kind='assessment-file',path=name,fileRole=role,sha256=digest,byteCount=len(raw),partCount=len(ids),**lineage));files[key]=(raw,ids)
  for ordinal,chunk in enumerate(ids):facts.append(dict(id=key+'-part-'+str(ordinal),kind='assessment-file-part',fileId=key,ordinal=ordinal,chunkId=chunk,**lineage))
  if name.endswith('-oracle.stdout.json'):
   oracle=json.loads(raw);analysis=oracle.get('sourceAnalysis')
   if analysis:
    analysis_id=key+'-source-analysis'
    facts.append(dict(id=analysis_id,kind='source-analysis-receipt',observedSourceCut=analysis['sourceCut'],grammar=analysis['grammar'],grammarDigest=analysis['grammarDigest'],syntaxHasErrors=analysis['syntaxHasErrors'],rowCount=len(analysis['rows']),wireFileId=key,**lineage))
    for syntax in analysis['rows']:
     syntax=dict(syntax);fact_id=syntax.pop('id');fact_kind=syntax.pop('kind');observed=syntax.pop('sourceRevision')
     facts.append(dict(id=analysis_id+'-'+fact_id,kind='source-syntax-fact',factKind=fact_kind,observedSourceCut=observed,sourceAnalysisId=analysis_id,**syntax,**lineage))
  if name.endswith('/source-cut.json'):
   observed=json.loads(raw);cut_key=pre+'cut-'+hashlib.sha256(name.encode()).hexdigest()[:16]
   facts.append(dict(id=cut_key,kind='source-cut',sourceCutId=observed['id'],fileCount=len(observed['files']),scope='selected-source-only',manifestFileId=key,**lineage))
   for ordinal,fingerprint in enumerate(observed['files']):facts.append(dict(id=cut_key+'-file-'+str(ordinal),kind='source-file-fingerprint',sourceCutId=observed['id'],cutObservationId=cut_key,**fingerprint,**lineage))
  if name.endswith('events.jsonl'):
   for number,line in enumerate(raw.split(b'\n'),1):
    if not line.strip():continue
    try:event=json.loads(line)
    except ValueError:continue
    facts.append(dict(id=pre+'native-'+hashlib.sha256(name.encode()).hexdigest()[:12]+'-'+str(number),kind='native-event-index',phase=Path(name).name.removesuffix('-events.jsonl'),eventType=event.get('type'),toolName=event.get('toolName'),toolCallId=event.get('toolCallId'),reportedIsError=event.get('isError'),participant=name.split('/')[0],nativeFileId=key,lineNumber=number,observationAuthority='participant-adapter',**lineage))
  if '/gateway/' in name and name.endswith(('.request.json','.upstream-request.json')):
   wire=json.loads(raw);phase_fields=phase_map.get((name.split('/')[0],int(Path(name).name.split('.')[0])),dict(phase=None,phaseAttribution='missing-receipt'))
   facts.append(dict(id=pre+'request-'+hashlib.sha256(name.encode()).hexdigest()[:16],kind='gateway-request-index',exchangeOrdinal=int(Path(name).name.split('.')[0]),participant=name.split('/')[0],model=wire.get('model'),providerRoute=wire.get('providerId'),direction='upstream' if name.endswith('.upstream-request.json') else 'participant',messageCount=len(wire.get('messages',[])),toolCount=len(wire.get('tools',[])),wireFileId=key,**phase_fields,**lineage))
   for number,tool in enumerate(wire.get('tools',[])):
    function=tool.get('function',{})
    facts.append(dict(id=pre+'tool-definition-'+hashlib.sha256(name.encode()).hexdigest()[:16]+'-'+str(number),kind='gateway-tool-definition',exchangeOrdinal=int(Path(name).name.split('.')[0]),direction='upstream' if name.endswith('.upstream-request.json') else 'participant',toolName=function.get('name'),inputSchema=function.get('parameters'),wireFileId=key,jsonPointer='/tools/'+str(number),**phase_fields,**lineage))
   for number,message in enumerate(wire.get('messages',[])):
    facts.append(dict(id=pre+'message-'+hashlib.sha256(name.encode()).hexdigest()[:16]+'-'+str(number),kind='gateway-context-message-index',exchangeOrdinal=int(Path(name).name.split('.')[0]),messageOrdinal=number,direction='upstream' if name.endswith('.upstream-request.json') else 'participant',role=message.get('role'),toolCallId=message.get('tool_call_id'),toolCallCount=len(message.get('tool_calls',[])),wireFileId=key,jsonPointer='/messages/'+str(number),**phase_fields,**lineage))
  if '/gateway/' in name and name.endswith('.status.json'):
   facts.append(dict(id=pre+'gateway-'+name.replace('/','-'),kind='gateway-exchange',participant=name.split('/')[0],exchange=json.loads(raw),wireFileId=key,**phase_map.get((name.split('/')[0],int(Path(name).name.split('.')[0])),dict(phase=None,phaseAttribution='missing-receipt')),**lineage))
 # Content-addressed payloads are separate from searchable observations.
 publication=a.evidence/'binary-publication.json'
 if publication.exists():
  for item in json.loads(publication.read_text()):facts.append(dict(id=pre+'binary-'+item['sha256'],kind='assessment-artifact',**lineage,**item))
 cases=[dict(id=pre+'result',kind='assessment',summaryId=pre+'summary',harnessCompleted=summary['ok'],subjectTaskSucceeded=summary['subjectTaskSucceeded'],sourceForkQualified=summary['sourceForkQualified'],formalSessionFSForkQualified=False,**lineage)]
 for label,result in summary['phases'].items():
  if not isinstance(result,dict):cases.append(dict(id=pre+'phase-'+label,kind='assessment-phase',phase=label,launchError=result,**lineage));continue
  behavior=result.get('behavior',{})
  cases.append(dict(id=pre+'phase-'+label,kind='assessment-phase',phase=label,buildPassed=result.get('build'),behaviorPassed=behavior.get('pass'),sourceCut=result.get('sourceCut'),oracleError=behavior.get('error'),**lineage))
  for check,passed in behavior.get('checks',{}).items():facts.append(dict(id=pre+'check-'+label+'-'+check,kind='assessment-check',phase=label,check=check,passed=passed,**lineage))
  for number,call in enumerate(behavior.get('calls',[])):facts.append(dict(id=pre+'stack-call-'+label+'-'+str(number),kind='feedback-submit-call' if assessment_name=='feedback' else 'navigation-stack-call',phase=label,ordinal=number,operation=call['op'],arguments=call['args'],**lineage))
 skills=[]
 existing_skills=store.read(s,repo,rev,PREFIX+'maintainer_skills')
 goal_id='skill-goal-'+assessment_name+'-subject-v1'
 if goal_id not in existing_skills:
  method=Path(__file__).resolve().parents[3]/'skills/agentlab-benchmark-goal/SKILL.md'
  import subprocess
  goal=dict(id=goal_id,title=assessment_name.title()+' subject acceptance goal',body='# Bounded actual assessment goal\n\n'+scope+'\n\nFrozen demands and actual check rows own the criteria.',skillLayer='instance',role='maintenance',stage='goal',objectId=task_id,sourceRevision=summary['sourceRevision'],caseIds=[task_id],methodSkillId='agentlab-benchmark-goal',methodRevision=subprocess.check_output(['git','log','-1','--format=%H','--',str(method)],text=True).strip(),methodDigest=hashlib.sha256(method.read_bytes()).hexdigest())
  existing_skills[goal_id]=goal
 for row in existing_skills.values():
  if row.get('objectId')!=task_id:continue
  row=dict(row);row['evaluationEvidenceIds']=list(dict.fromkeys(row.get('evaluationEvidenceIds',[])+[pre+'summary']));stage_next={'goal':'Maintain bounded acceptance against named checks and explicit qualification limits.','repository-analysis':'Compare actual outcome and state contracts against frozen source semantics.','program-analysis':'Analyze tracked deltas, actual backend calls and original static facts; keep static versus executed scope distinct.','seed-extraction':'Derive the next variants from failed checks without rewriting this assessed demand.','calibration':'Retain original/reference/negative calibration and distinguish actual-method execution from UI rendering.','evaluation':'Compare parent/fresh-Agent phases, gateway context and source-cut identity; formal SessionFS remains separate.'};prior_refs={ref['id']:ref for ref in row.get('evaluationEvidenceRefs',[])};row['evaluationEvidenceRefs']=[prior_refs.get(key,dict(repository=repo,table=PREFIX+OBS,id=key)) for key in row['evaluationEvidenceIds']];row['evaluationGuidance']=assessment_guidance(row.get('evaluationGuidance',{}),row['evaluationEvidenceRefs'],pre+'summary',summary,scope,stage_next.get(row['stage']),a.run)
  skills.append(row)
 runtime={OBS:facts+cases,PAYLOAD:list(chunks.values())}
 if a.create_runtime_tables:
  for table,rows in runtime.items():
   fields={'id':dict(type='string',required=True)}
   for row in rows:
    for key,value in row.items():
     if value is None:continue
     kind='boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'string'
     fields[key]=dict(type=kind,required=key=='id')
   rev=s.call('table.create',dict(repo=repo,worktree=wt,path=PREFIX+table,expected_revision=rev,definition=dict(key_field='id',fields=fields,required_fields=['id'],indexes=[dict(name='by_'+key,field=key) for key,value in fields.items() if key in ('kind','producerRun','taskId','phase','fileId','ordinal','sha256','eventType','toolName','sourceCutId','participant','direction','wireFileId','toolCallId')],description='AgentLab construction-fixture '+table+'; full raw evidence and typed indexes'),message='Separate runtime evidence from reusable knowledge'))['revision']
 for table,rows in [(OBS,facts+cases),(PAYLOAD,list(chunks.values())),('maintainer_skills',skills)]:
  existing=store.scan(s,repo,rev,PREFIX+table);ops=[]
  for row in rows:
   old=existing.get(row['id'])
   if old and old['row']==row:continue
   if old:
    updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if k not in old['row'] or old['row'][k]!=v]
    if row.get('kind')=='assessment-file' and 'chunkIds' in old['row']:updates.append(dict(op='unset',field='/chunkIds'))
    if not updates:continue
    op=dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=old['row_version'],field_updates=updates)
   else:op=dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row)
   ops.append(op)
  for start in range(0,len(ops),128):rev=store.transact(s,repo,wt,rev,[dict(path=PREFIX+table,operations=ops[start:start+128])],'Capture actual staged assessment and next-instance feedback')
 durable=store.read(s,repo,rev,PREFIX+OBS);payloads=store.read(s,repo,rev,PREFIX+PAYLOAD)
 for file_id,(raw,ids) in files.items():
  parts=sorted((row for row in durable.values() if row.get('kind')=='assessment-file-part' and row['fileId']==file_id),key=lambda x:x['ordinal'])
  assert [row['ordinal'] for row in parts]==list(range(len(ids)))
  assert raw==b''.join(base64.b64decode(payloads[row['chunkId']]['value']) for row in parts)
 receipt=store.export(s,repo,rev,a.root/'export',PREFIX);assert receipt==store.export(s,repo,rev,a.root/'export-repeated',PREFIX)
 assert store.import_snapshot(s,repo,wt,a.root/'export',PREFIX)==(rev,0)
 result=dict(ok=True,repository=repo,observationTable=PREFIX+OBS,payloadTable=PREFIX+PAYLOAD,revision=rev,fileCount=len(files),gatewayPhaseCounts={phase:sum(item['phase']==phase for item in phase_map.values()) for phase in sorted({item['phase'] for item in phase_map.values() if item['phase']})},unattributedGatewayExchanges=sum(item['phase'] is None for item in phase_map.values()),allFilesExact=True,stableExport=True,reimportUnchanged=True,subjectTaskSucceeded=summary['subjectTaskSucceeded']);(a.root/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
