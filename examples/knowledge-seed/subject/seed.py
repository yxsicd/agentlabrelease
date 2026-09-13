"""Maintain a derived operational case in development TableGit before assessment."""
import argparse,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service
import importlib.util
spec=importlib.util.spec_from_file_location('navigation_subject_runner',Path(__file__).with_name('run.py'));runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner);DEMANDS=runner.DEMANDS;PIN=runner.PIN
PREFIX='assets/knowledge/contracts/'
def main():
 p=argparse.ArgumentParser();p.add_argument('--scenario',choices=runner.SCENARIOS,default='navigation');p.add_argument('--prefix',default=PREFIX);p.add_argument('--development',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir();(a.root/'rpc').mkdir();c=json.loads(a.development.read_text());s=Service(c['url'],Path(c['authorizationFile']).read_text().strip(),a.root/'rpc');repo=c['repo'];prefix=a.prefix;wt={'topic_id':None};rev=s.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision']
 scenario=runner.SCENARIOS[a.scenario];parent_id='case-delayed-loading' if a.scenario=='loading' else 'case-'+a.scenario
 tasks=store.read(s,repo,rev,prefix+'evaluation_cases');base=tasks[parent_id];case={**base,'id':scenario['caseId'],'kind':'task','assetClass':'reusable-knowledge','parentCaseId':parent_id,'demands':scenario['demands'],'sourceRevision':PIN,'calibrationAdapter':'subject/'+scenario['oracle']+' actual methods; TypeScript transpile; controlled backend', 'assessmentScope':scenario['scope'],'forkMode':'selected-source-cut/fresh-agent','formalSessionFSQualified':False,'uiRenderingQualified':False};case.pop('compilationEvidenceIds',None)
 case['oracleDigest']=hashlib.sha256(Path(__file__).with_name(scenario['oracle']).read_bytes()).hexdigest()
 if a.scenario=='loading':
  code="SELECT json_extract(row_json,'$.id') AS fact_id,json_extract(row_json,'$.path') AS path,json_extract(row_json,'$.targetPath') AS target FROM facts WHERE json_extract(row_json,'$.kind')='import' AND json_extract(row_json,'$.path') IN ('common/src/main/ets/view/DelayedLoadingView.ets','common/src/main/ets/view/LoadingView.ets') ORDER BY path,target"
  request=dict(bindings=[dict(alias='facts',repo=repo,path=prefix+'program_facts',revision=rev)],sql=code,parameters=[])
  result=s.call('table.relations.query',request);assert len(result['rows'])>=3
  analysis=dict(id='analysis-loading-subject-v1',kind='analysis',assetClass='reusable-knowledge',sourceRevision=PIN,code=code,request=request,result=result,interpretation='Fixed-source resolved import paths support loading/shared breakpoint task; not runtime call or UI coverage')
  existing_analysis=store.read(s,repo,rev,prefix+'program_facts').get(analysis['id'])
  if existing_analysis is None:rev=store.transact(s,repo,wt,rev,[dict(path=prefix+'program_facts',operations=[dict(op='insert',operation_id=str(uuid.uuid4()),key=analysis['id'],row=analysis)])],'Archive loading seed dependency analysis')
  else:assert existing_analysis['sourceRevision']==PIN and existing_analysis['code']==code
  case['analysisIds']=[analysis['id']]
  case['calibrationContract']=dict(variantExpectations={'baseline':False,'reference':True,'wrong-cancel':False,'wrong-fallback':False})
 rows=[('evaluation_cases',case)]
 for row in store.read(s,repo,rev,prefix+'maintainer_skills').values():
  if row.get('objectId')!=parent_id:continue
  child={**row,'assetClass':'reusable-knowledge','id':row['id']+'-subject-v1','objectId':case['id'],'caseIds':[case['id']],'parentSkillId':row['id'],'body':row['body']+'\n\nDerived operational case: actual-method oracle, frozen two-demand contract, contained Pi runtime, exact first-turn source cut and fresh-Agent source-only branch. Follow subject/README.md; formal SessionFS/device scopes remain separate.'}
  method=Path(__file__).resolve().parents[3]/'skills'/child['methodSkillId']/'SKILL.md';import subprocess
  child['methodRevision']=subprocess.check_output(['git','log','-1','--format=%H','--',str(method)],text=True).strip();child['methodDigest']=hashlib.sha256(method.read_bytes()).hexdigest();rows.append(('maintainer_skills',child))
 for table,row in rows:
  existing=store.scan(s,repo,rev,prefix+table).get(row['id'])
  if existing:
   if table=='evaluation_cases':assert existing['row']['demands']==scenario['demands'] and existing['row']['oracleDigest']==case['oracleDigest'], 'Existing frozen case has different demands; derive a new case version'
   else:assert existing['row']['objectId']==case['id']
   continue
  op=dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row) if not existing else dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=existing['row_version'],field_updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if existing['row'].get(k)!=v])
  rev=store.transact(s,repo,wt,rev,[dict(path=prefix+table,operations=[op])],'Freeze operational seed and corresponding instance Skills')
 goal_id='skill-goal-'+a.scenario+'-subject-v1';method=Path(__file__).resolve().parents[3]/'skills/agentlab-benchmark-goal/SKILL.md'
 import subprocess
 goal=dict(id=goal_id,assetClass='reusable-knowledge',title=a.scenario.title()+' actual assessment goal',body='# Frozen actual-method assessment goal\n\n'+scenario['scope']+'\n\n'+ '\n\n'.join(scenario['demands'])+'\n\nFull phone compile required; UI rendering and formal SessionFS are separate.',skillLayer='instance',role='maintenance',stage='goal',objectId=case['id'],sourceRevision=PIN,caseIds=[case['id']],methodSkillId='agentlab-benchmark-goal',methodRevision=subprocess.check_output(['git','log','-1','--format=%H','--',str(method)],text=True).strip(),methodDigest=hashlib.sha256(method.read_bytes()).hexdigest())
 old=store.scan(s,repo,rev,prefix+'maintainer_skills').get(goal_id)
 if old is None:rev=store.transact(s,repo,wt,rev,[dict(path=prefix+'maintainer_skills',operations=[dict(op='insert',operation_id=str(uuid.uuid4()),key=goal_id,row=goal)])],'Freeze corresponding goal instance')
 print(json.dumps(store.export(s,repo,rev,a.root/'export',prefix)))
if __name__=='__main__':main()
