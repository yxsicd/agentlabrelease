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
PREFIX='flywheel/harmony-v3/'
SPECS=[
 ('feedback','Feedback submission and reset', ['common/src/main/ets/component/FeedbackSheet.ets','common/src/main/ets/model/FeedbackData.ets','common/src/main/ets/util/SubmitInfoUtil.ets'], ['Make feedback submission preserve selections until success and show a retryable failure.','Prevent duplicate submissions and preserve the previous success/reset behavior.'], ['Rejected submission preserves state; retry succeeds.','Repeated click creates one submission; success clears state.']),
 ('delayed-loading','Loading lifecycle across breakpoints', ['common/src/main/ets/view/DelayedLoadingView.ets','common/src/main/ets/view/LoadingView.ets','common/src/main/ets/util/BreakpointSystem.ets'], ['Make repeated loading appearances start a fresh delayed indicator and cancel old timers.','Allow breakpoint changes while loading without stale indicator callbacks.'], ['Disappear/reappear does not show a stale indicator.','Small/large delay and cancellation checks pass.']),
 ('navigation','Navigation replacement and error outcome', ['common/src/main/ets/routermanager/PageContext.ets','common/src/main/ets/model/PageEnum.ets','common/src/main/ets/util/Logger.ets'], ['Expose a usable navigation operation outcome while preserving stack and animation behavior.','Propagate failure outcomes to one actual caller without losing successful navigation behavior.'], ['Push/replace/pop postconditions checked with a stack oracle.','Failure reaches caller; previous success checks remain passing.']),
 ('image-url','Consistent remote image classification', ['common/src/main/ets/util/UrlUtil.ets','common/src/main/ets/component/ImageComponent.ets','features/devpractices/src/main/ets/view/ImagePreview.ets'], ['Define and apply consistent HTTP/HTTPS image URL handling across component and preview.','Add malformed/relative/local URL behavior while preserving remote preview.'], ['Both consumers agree on URL cases.','Local/malformed inputs and previous remote cases are covered.']),
 ('debounce','Independent click throttling across consumers', ['common/src/main/ets/util/DebounceUtil.ets','features/componentlibrary/src/main/ets/view/ComponentBaseView.ets','common/src/main/ets/util/index.ets'], ['Give each returned click handler its own timing state; unrelated handlers must not suppress one another.','Preserve suppression inside the wait window, allow the exact boundary, and keep independent handlers after the change.'], ['Two handlers at the same instant both execute.','Repeated same handler is suppressed; exact wait boundary executes.'])]

OBSERVATIONS={
 'feedback': 'FeedbackSheet keeps selection flags in feedbackListState and derives canSubmit from vote plus selected reason. It resets all state only in the submit promise success branch. SubmitInfoUtil currently logs the selected reasons and returns a resolved promise with Toast; it is a demonstration stub, not a remote submission backend. Failure/retry tests therefore need an operator-controlled asynchronous seam, not an invented production endpoint.',
 'delayed-loading': 'DelayedLoadingView computes delay from BreakpointType, starts setTimeout on appearance and clears its stored timer on disappearance. Appearance does not reset showLoading; repeated appearances also overwrite the stored timer handle. LoadingView is a separate imported rendering function. Tests must control lifecycle and time, then verify both stale-callback cancellation and visibility reset.',
 'navigation': 'PageContext owns one NavPathStack; push, replace, pop, popToIndex and clear catch errors and only log them. RouterParam binds PageEnum plus optional object parameters. An outcome change must preserve animation defaults and the same stack ownership; callers cannot currently observe a failed operation from the void methods.',
 'image-url': 'UrlUtil.isNetUrl lowercases a string and checks only the HTTP/HTTPS prefix, so it is classification rather than full URL validity. ImageComponent uses the direct relative import; ImagePreview consumes the exported common package alias. Keep classification semantics explicitly specified and compare both consumers. UrlUtil.maskUrl is unrelated existing application behavior; do not use it to redact Harness evidence.',
 'debounce': 'DebounceUtil stores lastClickTime as static class state, shared by all returned handlers. Suppressed clicks also advance that timestamp, giving sliding suppression. ComponentBaseView wraps callbacks with the common-package exported utility. Preserve the stated sliding behavior while moving timing state per handler; do not silently rename the API or replace it with a trailing debounce.'
}

METHODS={'goal':'agentlab-benchmark-goal','repository-analysis':'agentlab-codebase-analysis','program-analysis':'agentlab-program-analysis','seed-extraction':'agentlab-seed-extraction','calibration':'agentlab-benchmark-calibration','evaluation':'agentlab-benchmark-operations'}
def lineage(stage,object_id,role='maintenance'):
 root=Path(__file__).resolve().parents[3]
 name=METHODS[stage];path=root/'skills'/name/'SKILL.md'
 revision=subprocess.check_output(['git','log','-1','--format=%H','--',str(path.relative_to(root))],cwd=root,text=True).strip()
 return dict(skillLayer='instance',role=role,stage=stage,objectId=object_id,methodSkillId=name,methodRevision=revision,methodDigest=hashlib.sha256(path.read_bytes()).hexdigest())

def instance_skills(key,title,paths,turns,checks,revision):
 facts=[ident('file',p) for p in paths]
 common=dict(sourceRevision=revision,factIds=facts,caseIds=['case-'+key],analysisIds=['analysis-relative-imports','analysis-common-barrel'],status='source-supported')
 rows=[]
 bodies={
 'repository-analysis':'Observed contract: '+OBSERVATIONS[key]+'\n\nRead these pinned files before changing behavior: '+', '.join(paths)+'. Preserve the observed contract unless the task explicitly changes it.',
 'program-analysis':'Analyze '+', '.join(paths)+'. Trace AST module references, symbols, syntactic call/assignment locations and the common package/barrel chain in program_facts. Use the archived import SQL at its input cut. Package path resolution is not symbol/type/runtime call resolution; do not infer the latter from these facts.',
 'seed-extraction':'Derive staged demands from this contract: '+OBSERVATIONS[key]+'\n\nCurrent candidate turns: '+json.dumps(turns,ensure_ascii=False)+'. Link case-'+key+' and the analysis facts. Vary timing/failure/input boundaries only with independently specified oracles.',
 'calibration':'Calibrate case-'+key+' using '+json.dumps(checks,ensure_ascii=False)+'. Build an independent baseline/reference/wrong-variant oracle. Current executable isolated oracles cover debounce, delayed-loading and image-url; feedback/navigation remain proposed. The image oracle verifies consumer call seams but does not execute their full bodies. ArkUI rendering, HAP build and real subject success remain unqualified.',
 'evaluation':'Consume the frozen case-'+key+' source, knowledge and task cuts. Present only its demands, not the operator reference transform, to the subject. Execute staged demands '+json.dumps(turns,ensure_ascii=False)+'. Grade '+json.dumps(checks,ensure_ascii=False)+' and record Harness-owned calls/output/checkpoints. A construction oracle pass does not constitute subject evaluation.'}
 for stage,body in bodies.items():
  rid='skill-'+key if stage=='repository-analysis' else 'skill-'+stage+'-'+key
  rows.append(dict(id=rid,title=title+' / '+stage,body='# '+title+'\n\n'+body+'\n',**common,**lineage(stage,'case-'+key,'operations' if stage=='evaluation' else 'maintenance')))
 return rows

def ident(kind,path): return kind+'-'+hashlib.sha256(path.encode()).hexdigest()[:24]
def dump(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def construct(source,out):
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
 if revision!=PIN: raise ValueError('Use the pinned code-workshop source')
 files=subprocess.check_output(['git','ls-files'],cwd=source,text=True).splitlines()
 code=[p for p in files if Path(p).suffix in ('.ets','.ts','.js','.cpp','.h')]
 inventory=dict(id='source-code-workshop',kind='inventory',path='.',sourceRevision=revision,codeFiles=len(code),codeLines=sum(len((source/p).read_bytes().splitlines()) for p in code),method='git tracked source inventory',coverage='AST parses whole source; selected scenario AST rows imported; syntax coverage receipt and full corpus evidence retained',buildQualified=False)
 binary=Path(__file__).resolve().parents[3]/'target/debug/agentlab-code-analysis'
 ast_dir=out/'ast';subprocess.run([str(binary),str(source),str(ast_dir)],check=True,capture_output=True,text=True)
 ast_rows=[json.loads(line) for line in (ast_dir/'program_facts.jsonl').read_text().splitlines()]
 inventory['astReceipt']=json.loads((ast_dir/'analysis.json').read_text())
 facts=[inventory];skills=[];cases=[]
 # Verify the local file dependency and package entry before resolving an alias.
 bindings={}
 package=(source/'common/oh-package.json5').read_text()
 if not re.search(r'"name"\s*:\s*"@ohos/common"',package) or not re.search(r'"main"\s*:\s*"Index.ets"',package): raise ValueError('Unexpected common package entry')
 for module in ['features/componentlibrary','features/devpractices']:
  dep_path=module+'/oh-package.json5';dep=(source/dep_path).read_text()
  if not re.search(r'"@ohos/common"\s*:\s*"file:../../common"',dep):raise ValueError('Unverified local common binding')
  bindings[module]='common/Index.ets'
  facts.append(dict(id=ident('package',module),kind='package-binding',path=dep_path,specifier='@ohos/common',targetPath='common/Index.ets',resolution='verified-local-package-entry',sourceRevision=revision,method='checked dependency file path and package main',evidencePaths=[dep_path,'common/oh-package.json5']))
 chosen=sorted({p for _,_,paths,_,_ in SPECS for p in paths}|{'common/Index.ets','common/oh-package.json5','features/componentlibrary/oh-package.json5','features/devpractices/oh-package.json5'})
 for path in chosen:
  text=(source/path).read_text();lines=text.splitlines()
  facts.append(dict(id=ident('file',path),kind='file',path=path,sourceRevision=revision,sha256=hashlib.sha256(text.encode()).hexdigest(),lineCount=len(lines),method='source bytes'))
  for ast in [r for r in ast_rows if r['path']==path]:
   if ast['kind']!='module-reference':
    facts.append(ast);continue
   spec=ast['specifier'];target='';status='external-or-alias-unresolved'
   if spec.startswith('.'):
    base=(source/path).parent/spec
    for candidate in [base,Path(str(base)+'.ets'),Path(str(base)+'.ts'),base/'index.ets']:
     if candidate.is_file():target=str(candidate.resolve().relative_to(source.resolve()));status='relative-file-resolved';break
   if spec=='@ohos/common':
    for module,target_entry in bindings.items():
     if path.startswith(module+'/'):target=target_entry;status='package-entry-resolved'
   facts.append(dict(ast,kind='import',line=ast['span']['startLine'],targetPath=target,resolution=status))
 for key,title,paths,turns,checks in SPECS:
  skills.extend(instance_skills(key,title,paths,turns,checks,revision))
  cases.append(dict(id='case-'+key,kind='task',title=title,sourceRevision=revision,skillIds=['skill-'+key],paths=paths,turns=turns,acceptance=checks,analysisIds=[],status='candidate',calibration={},buildQualified=False))
 skills.append(dict(id='skill-harmony-goal',title='Harmony challenge instance goal',body='# Harmony benchmark goal\n\nUse the code-workshop project at the pinned source; inventory exceeds20k code lines, but build scope and SDK acceptance must be independently checked. Maintain five cross-file candidates and multi-turn process/final metrics. This source targets6.1 whereas the challenge names6.0; do not silently equate them. Guide-snippets is a companion corpus of many projects, not one20k-line project. Track method calibration separately from HAP, real Agent and SessionFS acceptance.\n',sourceRevision=revision,factIds=['source-code-workshop'],caseIds=['case-'+x[0] for x in SPECS],analysisIds=['analysis-relative-imports','analysis-common-barrel'],status='source-supported',**lineage('goal','harmony-challenge')))
 return dict(maintainer_skills=skills,program_facts=facts,evaluation_cases=cases)

def maintain_facts(service,repo,worktree,revision,tables):
 pending=[]
 for table,rows in [('program_facts',tables['program_facts']),('evaluation_cases',[r for r in tables['evaluation_cases'] if r['kind']=='calibration'])]:
  existing=store.scan(service,repo,revision,PREFIX+table)
  for row in rows:
   old=existing.get(row['id'])
   if old and old['row']==row:continue
   if old:
    fields=[dict(op='set',field='/'+k.replace('~','~0').replace('/','~1'),value=v) for k,v in row.items() if old['row'].get(k)!=v]
    fields += [dict(op='unset',field='/'+k.replace('~','~0').replace('/','~1')) for k in old['row'] if k not in row]
    op=dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=old['row_version'],field_updates=fields)
   else:op=dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row)
   pending.append((PREFIX+table,op))
  if table=='program_facts':
   desired={r['id'] for r in rows}
   for key,old in existing.items():
    if key.startswith('ast-') and key not in desired:
     pending.append((PREFIX+table,dict(op='delete',operation_id=str(uuid.uuid4()),key=key,expected_row_version=old['row_version'])))
 for start in range(0,len(pending),32):
  grouped={}
  for path,op in pending[start:start+32]:grouped.setdefault(path,[]).append(op)
  revision=store.transact(service,repo,worktree,revision,[dict(path=path,operations=ops) for path,ops in grouped.items()],'Maintain current parser facts and calibration evidence')
 return revision

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--development',type=Path);a=p.parse_args()
 a.root.mkdir(parents=True,exist_ok=True);e=a.root/'evidence'
 if e.exists() and any(e.iterdir()):
  archive=a.root/'history'/str(uuid.uuid4());archive.mkdir(parents=True)
  for name in ['evidence','export','export-repeated']:
   previous=a.root/name
   if previous.exists(): previous.rename(archive/name)
 e.mkdir(exist_ok=True)
 tables=construct(a.source,e);dump(e/'construction-proposal.json',tables)
 results={}
 for mode in ['baseline','reference','wrong-boundary']:
  cmd=['node',str(Path(__file__).with_name('debounce.js')),str(a.source/SPECS[-1][2][0]),mode]
  result=subprocess.run(cmd,capture_output=True,text=True)
  (e/(mode+'.stdout')).write_text(result.stdout);(e/(mode+'.stderr')).write_text(result.stderr)
  if result.returncode: raise RuntimeError('Preserved isolated oracle failure')
  results[mode]=json.loads(result.stdout)
 if results['baseline']['pass'] or not results['reference']['pass'] or results['wrong-boundary']['pass']:raise RuntimeError('Oracle calibration failed')

 loading={}
 for mode in ['baseline','reference','wrong-cancel']:
  result=subprocess.run(['node',str(Path(__file__).with_name('loading.js')),str(a.source/SPECS[1][2][0]),mode],capture_output=True,text=True)
  (e/('loading-'+mode+'.stdout')).write_text(result.stdout);(e/('loading-'+mode+'.stderr')).write_text(result.stderr)
  if result.returncode: raise RuntimeError('Preserved loading oracle failure')
  loading[mode]=json.loads(result.stdout)
 if loading['baseline']['pass'] or not loading['reference']['pass'] or loading['wrong-cancel']['pass']:raise RuntimeError('Loading oracle calibration failed')
 tables['program_facts'].append(dict(id='oracle-loading',kind='oracle',sourceRevision=PIN,code=Path(__file__).with_name('loading.js').read_text(),request={'runtime':subprocess.check_output(['node','--version'],text=True).strip(),'sourcePath':SPECS[1][2][0],'captureAuthority':'operator-owned construction runner'},result=loading,interpretation='Isolated lifecycle calibration with explicit timer/breakpoint stubs; not rendering or HAP'))
 tables['evaluation_cases'].append(dict(id='calibration-loading',kind='calibration',title='Isolated lifecycle calibration',sourceRevision=PIN,paths=SPECS[1][2],status='isolated-method-qualified',calibration=loading,buildQualified=False))
 image={}
 for mode in ['baseline','reference','wrong-prefix']:
  result=subprocess.run(['node',str(Path(__file__).with_name('image-url.js')),str(a.source),mode],capture_output=True,text=True)
  (e/('image-url-'+mode+'.stdout')).write_text(result.stdout);(e/('image-url-'+mode+'.stderr')).write_text(result.stderr)
  if result.returncode: raise RuntimeError('Preserved image URL oracle failure')
  image[mode]=json.loads(result.stdout)
 if image['baseline']['pass'] or not image['reference']['pass'] or image['wrong-prefix']['pass']:raise RuntimeError('Image URL oracle calibration failed')
 tables['program_facts'].append(dict(id='oracle-image-url',kind='oracle',sourceRevision=PIN,code=Path(__file__).with_name('image-url.js').read_text(),request={'sourcePaths':SPECS[3][2],'runtime':subprocess.check_output(['node','--version'],text=True).strip(),'captureAuthority':'operator-owned construction runner'},result=image,interpretation='Explicit classification fixture labels and source-verified consumer seams; consumer bodies, Harmony URL runtime and HAP not executed'))
 tables['evaluation_cases'].append(dict(id='calibration-image-url',kind='calibration',title='Image classification seam calibration',sourceRevision=PIN,paths=SPECS[3][2],status='isolated-seam-qualified',calibration=image,buildQualified=False))
 for row in tables['maintainer_skills']:
  if row['objectId']=='case-image-url':
   row['factIds'].append('oracle-image-url')
   row['body']+='\nCalibration evidence oracle-image-url:14 explicit input cases across both consumer decision seams; original prefix-only classification fails malformed inputs, reference passes, stale preview classification fails. Full consumer lifecycle, ArkTS URL runtime and HAP remain unqualified.\n'
 for row in tables['evaluation_cases']:
  if row['id']=='case-image-url': row.update(status='isolated-seam-qualified',calibration=image)
 for row in tables['maintainer_skills']:
  if row['objectId'] in ('case-debounce','case-delayed-loading','case-image-url') and row['stage']=='calibration':row['status']='isolated-seam-supported' if row['objectId']=='case-image-url' else 'isolated-method-supported'
 # Complete operator results are structured, not participant-reported success.
 tables['program_facts'].append(dict(id='oracle-debounce',kind='oracle',sourceRevision=PIN,code=Path(__file__).with_name('debounce.js').read_text(),request={'runtime':subprocess.check_output(['node','--version'],text=True).strip(),'sourcePath':SPECS[-1][2][0],'modes':['baseline','reference','wrong-boundary'],'captureAuthority':'operator-owned construction runner'},result=results,interpretation='Exact isolated-method calibration; not an assessed Code Agent or Harmony compiler'))
 tables['evaluation_cases'].append(dict(id='calibration-debounce',kind='calibration',title='Isolated method calibration',sourceRevision=PIN,paths=SPECS[-1][2],status='isolated-method-qualified',calibration=results,buildQualified=False))
 if not a.development:
  package={'tables':tables,'updates':[dict(table='maintainer_skills',id='skill-debounce',fields={'body':next(r['body'] for r in tables['maintainer_skills'] if r['id']=='skill-debounce')+'\nOperator isolated oracle confirms the shared-timestamp collision; per-handler reference passes. No HAP qualification.\n'})],'calibrated':False,'scope':'real Harmony source; three isolated scenarios calibrated, two proposed tasks'}
  dump(e/'knowledge-package.json',package)
  dump(e/'isolated-calibration.json',results)
  print(json.dumps({'sourceRevision':PIN,'taskCandidates':5,'isolatedCalibration':True,'calibratedMethods':3,'harmonyBuildQualified':False}))
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
  revision=maintain_facts(service,repo,wt,revision,tables)
 baseline=revision
 sql="SELECT json_extract(row_json,'$.path') AS source, json_extract(row_json,'$.targetPath') AS target FROM facts WHERE json_extract(row_json,'$.kind')='import' AND json_extract(row_json,'$.resolution') IN ('relative-file-resolved','package-entry-resolved') ORDER BY source,target"
 request=dict(bindings=[dict(alias='facts',repo=repo,path=PREFIX+'program_facts',revision=revision)],sql=sql,parameters=[])
 result=service.call('table.relations.query',request);dump(e/'dependency-analysis.json',result)
 analysis=dict(id='analysis-relative-imports',kind='analysis',sourceRevision=PIN,code=sql,request=request,result=result,interpretation='Selected-file AST module references plus verified local common package entry; external aliases and symbol/runtime calls unresolved')
 graph_sql="SELECT json_extract(e.row_json,'$.path') AS consumer, json_extract(b.row_json,'$.path') AS entry, json_extract(c.row_json,'$.path') AS barrel, json_extract(c.row_json,'$.targetPath') AS leaf FROM facts e JOIN facts b ON json_extract(e.row_json,'$.targetPath')=json_extract(b.row_json,'$.path') JOIN facts c ON json_extract(b.row_json,'$.targetPath')=json_extract(c.row_json,'$.path') WHERE json_extract(e.row_json,'$.kind')='import' AND json_extract(b.row_json,'$.kind')='import' AND json_extract(c.row_json,'$.kind')='import' AND json_extract(e.row_json,'$.resolution')='package-entry-resolved' AND json_extract(c.row_json,'$.targetPath') IN ('common/src/main/ets/util/DebounceUtil.ets','common/src/main/ets/util/UrlUtil.ets') ORDER BY consumer,leaf"
 graph_request=dict(bindings=[dict(alias='facts',repo=repo,path=PREFIX+'program_facts',revision=baseline)],sql=graph_sql,parameters=[])
 graph_result=service.call('table.relations.query',graph_request);dump(e/'barrel-analysis.json',graph_result)
 if len(graph_result['rows'])!=4: raise RuntimeError('Expected four package export path candidates; preserve analysis result')
 graph=dict(id='analysis-common-barrel',kind='analysis',sourceRevision=PIN,code=graph_sql,request=graph_request,result=graph_result,interpretation='Four package-export path candidates, not four resolved imported-symbol calls. Consumer -> common Index -> util index -> exported leaf.')
 updates=[]
 for table,rows in [('program_facts',[analysis,graph]+[r for r in tables['program_facts'] if r['kind']=='oracle']),('maintainer_skills',[dict(r,body=r['body']+'\nOperator calibration proves shared-state collision; per-handler reference passes. No HAP qualification.\n',status='isolated-method-supported') if r['id']=='skill-debounce' else r for r in tables['maintainer_skills']]),('evaluation_cases',[dict(tables['evaluation_cases'][4],status='isolated-method-qualified',analysisIds=[analysis['id'],graph['id']],calibration=results)]+[dict(r,analysisIds=[analysis['id'],graph['id']],status='isolated-method-qualified',calibration=loading) if r['id']=='case-delayed-loading' else dict(r,analysisIds=[analysis['id'],graph['id']]) for r in tables['evaluation_cases'][:4]])]:
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
 dump(e/'summary.json',dict(ok=True,sourceRevision=PIN,baselineRevision=baseline,finalRevision=revision,tablePrefix=PREFIX,counts={k:v['rowCount'] for k,v in final['tables'].items()},stableExport=True,repeatedImportNoChanges=True,knowledgeChanged=before!=after,instanceSkillLayers=sorted({r['skillLayer'] for r in after.values()}),instanceRoles=sorted({r['role'] for r in after.values()}),calibration=results,loadingCalibration=loading,imageCalibration=image,harmonyBuildQualified=False,formalSessionFSQualified=False,subjectAgentRun=False))
 dump(a.root/'authority.json',dict(repo=repo,tablePrefix=PREFIX,baselineRevision=baseline,finalRevision=revision,sourceRevision=PIN,snapshot=str(a.root/'export')))
 print(json.dumps(json.loads((e/'summary.json').read_text()),ensure_ascii=False))
if __name__=='__main__':main()
