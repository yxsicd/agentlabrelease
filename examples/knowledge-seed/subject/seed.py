"""Maintain a derived operational case in development TableGit before assessment."""
import argparse,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service
import importlib.util
spec=importlib.util.spec_from_file_location('navigation_subject_runner',Path(__file__).with_name('run.py'));runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner);DEMANDS=runner.DEMANDS;PIN=runner.PIN
PREFIX='flywheel/harmony-v3/'
def main():
 p=argparse.ArgumentParser();p.add_argument('--development',type=Path,required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();a.root.mkdir();(a.root/'rpc').mkdir();c=json.loads(a.development.read_text());s=Service(c['url'],Path(c['authorizationFile']).read_text().strip(),a.root/'rpc');repo=c['repo'];wt={'topic_id':None};rev=s.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision']
 tasks=store.read(s,repo,rev,PREFIX+'evaluation_cases');base=tasks['case-navigation'];case={**base,'id':'case-navigation-subject-v1','kind':'task','parentCaseId':'case-navigation','demands':DEMANDS,'sourceRevision':PIN,'calibrationAdapter':'subject/navigation.cjs actual bodies, TypeScript transpile, modeled stack','forkMode':'selected-source-cut/fresh-agent','formalSessionFSQualified':False,'uiRenderingQualified':False};case.pop('compilationEvidenceIds',None)
 rows=[('evaluation_cases',case)]
 for row in store.read(s,repo,rev,PREFIX+'maintainer_skills').values():
  if row.get('objectId')!='case-navigation':continue
  child={**row,'id':row['id']+'-subject-v1','objectId':case['id'],'caseIds':[case['id']],'parentSkillId':row['id'],'body':row['body']+'\n\nDerived operational case: actual-method oracle, named navigationFailed outcome, contained Pi runtime, exact first-turn source cut and fresh-Agent source-only branch. Follow subject/README.md; formal SessionFS/device scopes remain separate.'}
  method=Path(__file__).resolve().parents[3]/'skills'/child['methodSkillId']/'SKILL.md';import subprocess
  child['methodRevision']=subprocess.check_output(['git','log','-1','--format=%H','--',str(method)],text=True).strip();child['methodDigest']=hashlib.sha256(method.read_bytes()).hexdigest();rows.append(('maintainer_skills',child))
 for table,row in rows:
  existing=store.scan(s,repo,rev,PREFIX+table).get(row['id'])
  if existing and existing['row']==row:continue
  op=dict(op='insert',operation_id=str(uuid.uuid4()),key=row['id'],row=row) if not existing else dict(op='update',operation_id=str(uuid.uuid4()),key=row['id'],expected_row_version=existing['row_version'],field_updates=[dict(op='set',field='/'+k,value=v) for k,v in row.items() if existing['row'].get(k)!=v])
  rev=store.transact(s,repo,wt,rev,[dict(path=PREFIX+table,operations=[op])],'Freeze navigation operational seed and corresponding instance Skills')
 print(json.dumps(store.export(s,repo,rev,a.root/'export',PREFIX)))
if __name__=='__main__':main()
