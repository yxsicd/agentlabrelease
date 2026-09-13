#!/usr/bin/env python3
"""Deterministic builder participant: source facts -> Skill rows -> calibrated seed."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import argparse

def identity(*parts):
    return hashlib.sha256('\0'.join(parts).encode()).hexdigest()[:24]

def build(root, source=None):
    root=Path(root); root.mkdir(parents=True,exist_ok=False)
    project=root/'project';project.mkdir()
    if source is None:
        (project/'price.py').write_text('def price(quantity):\n    return quantity * 10\n')
        (project/'checkout.py').write_text('from price import price\ndef total(quantity):\n    return price(quantity)\n')
    else:
        import shutil
        shutil.copytree(source,project,dirs_exist_ok=True)
    evidence=root/'evidence';evidence.mkdir()
    seed_bytes=Path(__file__).with_name('builder-seed.json').read_bytes()
    (evidence/'builder-seed.json').write_bytes(seed_bytes)
    revision=subprocess.run(['git','-C',str(project),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip() or 'owned-fixture'
    nodes=[];edges=[];skills=[];links=[]
    for path in sorted(project.rglob('*.py')):
        relative=path.relative_to(project).as_posix();text=path.read_text();digest=hashlib.sha256(text.encode()).hexdigest()
        tree=ast.parse(text)
        for symbol in ast.walk(tree):
            if isinstance(symbol,(ast.FunctionDef,ast.AsyncFunctionDef)):
                key=identity(relative,symbol.name);nodes.append(dict(id=key,path=relative,symbol=symbol.name,line=symbol.lineno,sourceSha256=digest,sourceRevision=revision))
                sid=identity('skill',relative,symbol.name)
                skills.append(dict(id=sid,title=f'Maintain {relative}:{symbol.name}',scope=relative,body=f'Inspect {symbol.name} and its callers before changing its return contract. Verify downstream tests.',sourceRevision=revision,status='candidate',feedbackEvaluationIds=[]))
                links.append(dict(id=identity(sid,key),skillId=sid,nodeId=key,relation='maintains'))
                for call in ast.walk(symbol):
                    if isinstance(call,ast.Call):
                        target=ast.unparse(call.func);edges.append(dict(id=identity(key,target,str(call.lineno)),sourceId=key,targetName=target,relation='calls',line=call.lineno,sourceRevision=revision,resolution='syntactic_unresolved'))
    tables={'knowledge_skills':skills,'knowledge_nodes':nodes,'knowledge_edges':edges,'knowledge_links':links,'knowledge_tasks':[],'knowledge_evaluations':[]}
    calibrated=False
    if source is None:
        task=dict(id=identity('task','volume-discount'),requirement='For quantity >= 3 apply a 20% discount, preserving checkout delegation and smaller quantities.',sourceRevision=revision,skillIds=[s['id'] for s in skills],status='candidate')
        tables['knowledge_tasks'].append(task)
        variants={'baseline':'return quantity * 10','reference':'return quantity * 10 * (0.8 if quantity >= 3 else 1)','wrong_boundary':'return quantity * 10 * (0.8 if quantity > 3 else 1)','lost_history':'return quantity * 8'}
        for name,implementation in variants.items():
            (project/'price.py').write_text('def price(quantity):\n    '+implementation+'\n')
            code='from checkout import total; assert total(1)==10; assert total(2)==20; assert total(3)==24; assert total(4)==32'
            result=subprocess.run(['python3','-B','-c',code],cwd=project,capture_output=True)
            (evidence/(name+'.stdout')).write_bytes(result.stdout);(evidence/(name+'.stderr')).write_bytes(result.stderr)
            tables['knowledge_evaluations'].append(dict(id=identity(task['id'],name),taskId=task['id'],variant=name,exitCode=result.returncode,passed=result.returncode==0,authority='operator_owned_harness'))
        calibrated=[e['passed'] for e in tables['knowledge_evaluations']]==[False,True,False,False]
        assert calibrated
        task['status']='calibrated'
        (project/'price.py').write_text('def price(quantity):\n    return quantity * 10\n')
    updates=[dict(table='knowledge_skills',id=s['id'],fields={'body':s['body']+' Preserve boundary behavior and prior requirements; calibration must reject boundary and regression mutations.','status':'verified_fixture' if calibrated else 'candidate','feedbackEvaluationIds':[e['id'] for e in tables['knowledge_evaluations']]}) for s in skills]
    facts=[dict(r,kind=kind) for name,kind in [('knowledge_nodes','symbol'),('knowledge_edges','call'),('knowledge_links','skill_link')] for r in tables[name]]
    cases=[dict(r,kind=kind,sourceRevision=revision) for name,kind in [('knowledge_tasks','task'),('knowledge_evaluations','calibration')] for r in tables[name]]
    tables={'maintainer_skills':skills,'program_facts':facts,'evaluation_cases':cases}
    for update in updates: update['table']='maintainer_skills'
    package=dict(schema='agentlab.knowledge_seed.v1',builder='deterministic_mock',builderSeedSha256=hashlib.sha256(seed_bytes).hexdigest(),sourceRevision=revision,tables=tables,updates=updates,calibrated=calibrated,scope='Python AST fixture; no Harmony analysis or strong-Agent claim')
    (evidence/'knowledge-package.json').write_text(json.dumps(package,indent=2)+'\n')
    (evidence/'participant.json').write_text(json.dumps({'implementation':'knowledge-builder-mock'})+'\n')
    return package

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--source',type=Path);a=p.parse_args();build(a.root,a.source)
