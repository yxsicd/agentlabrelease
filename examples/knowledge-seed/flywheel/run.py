"""First real-source construction round; TableGit rows are live authority."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'))
from capture import Service
PIN='7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6'
PREFIX='flywheel/harmony/'
SPECS=[
 ('feedback','Feedback submission and reset', ['common/src/main/ets/component/FeedbackSheet.ets','common/src/main/ets/model/FeedbackData.ets','common/src/main/ets/util/SubmitInfoUtil.ets'], ['Make feedback submission preserve selections until success and show a retryable failure.','Prevent duplicate submissions and preserve the previous success/reset behavior.'], ['Rejected submission preserves state; retry succeeds.','Repeated click creates one submission; success clears state.']),
 ('delayed-loading','Loading lifecycle across breakpoints', ['common/src/main/ets/view/DelayedLoadingView.ets','common/src/main/ets/view/LoadingView.ets','common/src/main/ets/util/BreakpointSystem.ets'], ['Make repeated loading appearances start a fresh delayed indicator and cancel old timers.','Allow breakpoint changes while loading without stale indicator callbacks.'], ['Disappear/reappear does not show a stale indicator.','Small/large delay and cancellation checks pass.']),
 ('navigation','Navigation replacement and error outcome', ['common/src/main/ets/routermanager/PageContext.ets','common/src/main/ets/model/PageEnum.ets','common/src/main/ets/util/Logger.ets'], ['Expose a usable navigation operation outcome while preserving stack and animation behavior.','Propagate failure outcomes to one actual caller without losing successful navigation behavior.'], ['Push/replace/pop postconditions checked with a stack oracle.','Failure reaches caller; previous success checks remain passing.']),
 ('image-url','Consistent remote image classification', ['common/src/main/ets/util/UrlUtil.ets','common/src/main/ets/component/ImageComponent.ets','features/devpractices/src/main/ets/view/ImagePreview.ets'], ['Define and apply consistent HTTP/HTTPS image URL handling across component and preview.','Add malformed/relative/local URL behavior while preserving remote preview.'], ['Both consumers agree on URL cases.','Local/malformed inputs and previous remote cases are covered.']),
 ('debounce','Independent click throttling across consumers', ['common/src/main/ets/util/DebounceUtil.ets','features/componentlibrary/src/main/ets/view/ComponentBaseView.ets','common/src/main/ets/util/index.ets'], ['Give each returned click handler its own timing state; unrelated handlers must not suppress one another.','Preserve suppression inside the wait window, allow the exact boundary, and keep independent handlers after the change.'], ['Two handlers at the same instant both execute.','Repeated same handler is suppressed; exact wait boundary executes.'])]

def ident(kind,path): return kind+'-'+hashlib.sha256(path.encode()).hexdigest()[:24]
def dump(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def construct(source,out):
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
 if revision!=PIN: raise ValueError('Use the pinned code-workshop source')
 files=subprocess.check_output(['git','ls-files'],cwd=source,text=True).splitlines()
 code=[p for p in files if Path(p).suffix in ('.ets','.ts','.js','.cpp','.h')]
 inventory=dict(id='source-code-workshop',kind='inventory',path='.',sourceRevision=revision,codeFiles=len(code),codeLines=sum(len((source/p).read_bytes().splitlines()) for p in code),method='git tracked source inventory',coverage='inventory whole source; lexical imports only selected task files',buildQualified=False)
 facts=[inventory];skills=[];cases=[]
 chosen=sorted({p for _,_,paths,_,_ in SPECS for p in paths})
 for path in chosen:
  text=(source/path).read_text();lines=text.splitlines()
  facts.append(dict(id=ident('file',path),kind='file',path=path,sourceRevision=revision,sha256=hashlib.sha256(text.encode()).hexdigest(),lineCount=len(lines),method='source bytes'))
  for number,line in enumerate(lines,1):
   m=re.search(r"(?:import|export).*?from\s+['\"]([^'\"]+)['\"]",line)
   if not m: continue
   spec=m[1];target='';status='external-or-alias-unresolved'
   if spec.startswith('.'):
    base=(source/path).parent/spec
    for candidate in [base,Path(str(base)+'.ets'),Path(str(base)+'.ts'),base/'index.ets']:
     if candidate.is_file():target=str(candidate.resolve().relative_to(source.resolve()));status='relative-file-resolved';break
   facts.append(dict(id=ident('import',path+':'+str(number)),kind='import',path=path,line=number,specifier=spec,targetPath=target,resolution=status,sourceRevision=revision,method='single-line lexical import; not symbol or runtime resolution'))
 for key,title,paths,turns,checks in SPECS:
  skills.append(dict(id='skill-'+key,title=title,body='# '+title+'\n\nMaintain the contract across '+', '.join(paths)+'.\nRead the pinned files and import facts before modifying behavior.\nThe proposed requirements are evaluation demands, not claims that current behavior is defective.\n',sourceRevision=revision,factIds=[ident('file',p) for p in paths],status='source-supported'))
  cases.append(dict(id='case-'+key,kind='task',title=title,sourceRevision=revision,skillIds=['skill-'+key],paths=paths,turns=turns,acceptance=checks,analysisIds=[],status='candidate',calibration={},buildQualified=False))
 return dict(maintainer_skills=skills,program_facts=facts,evaluation_cases=cases)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--development',type=Path);a=p.parse_args()
 a.root.mkdir(parents=True,exist_ok=True);e=a.root/'evidence';e.mkdir(exist_ok=True)
 tables=construct(a.source,e);dump(e/'construction-proposal.json',tables)
 results={}
 for mode in ['baseline','reference','wrong-boundary']:
  cmd=['node',str(Path(__file__).with_name('debounce.js')),str(a.source/SPECS[-1][2][0]),mode]
  result=subprocess.run(cmd,capture_output=True,text=True)
  (e/(mode+'.stdout')).write_text(result.stdout);(e/(mode+'.stderr')).write_text(result.stderr)
  if result.returncode: raise RuntimeError('Preserved isolated oracle failure')
  results[mode]=json.loads(result.stdout)
 if results['baseline']['pass'] or not results['reference']['pass'] or results['wrong-boundary']['pass']:raise RuntimeError('Oracle calibration failed')
 # Complete operator results are structured, not participant-reported success.
 tables['program_facts'].append(dict(id='oracle-debounce',kind='oracle',sourceRevision=PIN,code=Path(__file__).with_name('debounce.js').read_text(),request={'runtime':subprocess.check_output(['node','--version'],text=True).strip(),'sourcePath':SPECS[-1][2][0],'modes':['baseline','reference','wrong-boundary'],'captureAuthority':'operator-owned construction runner'},result=results,interpretation='Exact isolated-method calibration; not an assessed Code Agent or Harmony compiler'))
 tables['evaluation_cases'].append(dict(id='calibration-debounce',kind='calibration',title='Isolated method calibration',sourceRevision=PIN,paths=SPECS[-1][2],status='isolated-method-qualified',calibration=results,buildQualified=False))
 if not a.development:
  package={'tables':tables,'updates':[dict(table='maintainer_skills',id='skill-debounce',fields={'body':tables['maintainer_skills'][-1]['body']+'\nOperator isolated oracle confirms the shared-timestamp collision; per-handler reference passes. No HAP qualification.\n'})],'calibrated':False,'scope':'real Harmony source; one isolated method calibrated, four proposed tasks'}
  dump(e/'knowledge-package.json',package)
  dump(e/'isolated-calibration.json',results)
  print(json.dumps({'sourceRevision':PIN,'taskCandidates':5,'isolatedCalibration':True,'harmonyBuildQualified':False}))
  return
 config=json.loads(a.development.read_text());service=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),e/'rpc')
 (e/'rpc').mkdir(exist_ok=True)
 wt={'topic_id':None};repo=config['repo'];revision=service.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision']
 # This development namespace is separate from fixture tables. Repeated rounds
 # reconcile actual row versions instead of assuming version one.
 created=not (a.root/'authority.json').exists()
 if created:
  revision=store.create(service,repo,wt,revision,tables,PREFIX)
  for start in range(0,len(tables['program_facts']),32):
   rows=tables['program_facts'][start:start+32]
   revision=store.transact(service,repo,wt,revision,[dict(path=PREFIX+'program_facts',operations=[dict(op='insert',operation_id=str(uuid.uuid4()),key=r['id'],row=r) for r in rows])],'Extract pinned Harmony program facts')
  for table in ['maintainer_skills','evaluation_cases']:
   revision=store.transact(service,repo,wt,revision,[dict(path=PREFIX+table,operations=[dict(op='insert',operation_id=str(uuid.uuid4()),key=r['id'],row=r) for r in tables[table]])],'Maintain source-backed Skills and candidate seeds')
  dump(a.root/'authority.json',dict(repo=repo,tablePrefix=PREFIX,baselineRevision=revision))
 else:
  revision=service.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision']
 baseline=revision
 sql="SELECT json_extract(row_json,'$.path') AS source, json_extract(row_json,'$.targetPath') AS target FROM facts WHERE json_extract(row_json,'$.kind')='import' AND json_extract(row_json,'$.resolution')='relative-file-resolved' ORDER BY source,target"
 request=dict(bindings=[dict(alias='facts',repo=repo,path=PREFIX+'program_facts',revision=revision)],sql=sql,parameters=[])
 result=service.call('table.relations.query',request);dump(e/'dependency-analysis.json',result)
 analysis=dict(id='analysis-relative-imports',kind='analysis',sourceRevision=revision,code=sql,request=request,result=result,interpretation='Selected-file lexical relative import paths; aliases and symbol calls unresolved')
 updates=[]
 for table,rows in [('program_facts',[analysis]+[r for r in tables['program_facts'] if r['kind']=='oracle']),('maintainer_skills',[dict(tables['maintainer_skills'][-1],body=tables['maintainer_skills'][-1]['body']+'\nIsolated oracle proves the shared timestamp suppresses unrelated callbacks. Per-handler state passes independence, suppression, boundary and retained-demand checks. This is method-level validation, not HAP compilation.\n',status='isolated-method-supported')]),('evaluation_cases',[dict(tables['evaluation_cases'][4],status='isolated-method-qualified',analysisIds=[analysis['id']],calibration=results)]+[dict(r,analysisIds=[analysis['id']]) for r in tables['evaluation_cases'][:4]])]:
  existing=store.scan(service,repo,revision,PREFIX+table);ops=[]
  for row in rows:
   old=existing.get(row['id'])
   if old and old['row']==row: continue
   op=dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=old['row_version'],field_updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if old['row'].get(k)!=v]) if old else dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row)
   ops.append(op)
  if ops: revision=store.transact(service,repo,wt,revision,[dict(path=PREFIX+table,operations=ops)],'Archive analysis and feed calibration back into knowledge')
 final=store.export(service,repo,revision,a.root/'export',PREFIX)
 repeated=store.export(service,repo,revision,a.root/'export-repeated',PREFIX);assert final==repeated
 again,changed=store.import_snapshot(service,repo,wt,a.root/'export',PREFIX);assert again==revision and changed==0
 before=store.read(service,repo,baseline,PREFIX+'maintainer_skills');after=store.read(service,repo,revision,PREFIX+'maintainer_skills')
 dump(e/'summary.json',dict(ok=True,sourceRevision=PIN,baselineRevision=baseline,finalRevision=revision,tablePrefix=PREFIX,counts={k:v['rowCount'] for k,v in final['tables'].items()},stableExport=True,repeatedImportNoChanges=True,knowledgeChanged=before!=after,calibration=results,harmonyBuildQualified=False,formalSessionFSQualified=False,subjectAgentRun=False))
 dump(a.root/'authority.json',dict(repo=repo,tablePrefix=PREFIX,baselineRevision=baseline,finalRevision=revision,sourceRevision=PIN,snapshot=str(a.root/'export')))
 print(json.dumps(json.loads((e/'summary.json').read_text()),ensure_ascii=False))
if __name__=='__main__':main()
