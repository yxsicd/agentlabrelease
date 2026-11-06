#!/usr/bin/env python3
"""Real mini-SWE-agent in official SWE images, followed by independent official grading."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from seeds import fetch
from workspace_patch import capture_patch
from usage import summarize as summarize_usage
from swebench.harness.test_spec.test_spec import make_test_spec


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--agent-python',type=Path,required=True);p.add_argument('--instance',required=True)
    p.add_argument('--gateway',required=True);p.add_argument('--model',default='glm-5.3-flash')
    p.add_argument('--step-limit',type=int,default=0,help='Model call limit; 0 disables it')
    p.add_argument('--wall-time-limit-seconds',type=int,default=1800,help='Agent wall-clock fallback')
    p.add_argument('--token-budget',type=int,help='Per-attempt input plus output token limit, checked between requests')
    p.add_argument('--catalog',type=Path,default=Path(__file__).with_name('catalog.json'))
    a=p.parse_args()
    if not 0 <= a.step_limit <= 10000 or not 60 <= a.wall_time_limit_seconds <= 86400:
        p.error('step limit must be 0..10000 and wall time must be 60..86400 seconds')
    if a.token_budget is not None and a.token_budget <= 0:
        p.error('token budget must be positive')
    a.root=a.root.resolve();a.root.mkdir(parents=True,exist_ok=False)
    evidence=a.root/'evidence';evidence.mkdir()
    summary=dict(schema='agentlab.swe_acceptance.v1',instanceId=a.instance,agent='mini-swe-agent',
                 harnessHealthy=False,agentResolved=False,status='running',
                 budget=dict(stepLimit=a.step_limit,wallTimeLimitSeconds=a.wall_time_limit_seconds,
                             transportRetryLimit=0,tokenBudget=a.token_budget,
                             tokenBudgetEnforced=a.token_budget is not None,
                             tokenBudgetBoundary='between_requests' if a.token_budget else None))
    def command(label,args,**kwargs):
        (evidence/(label+'-command.json')).write_text(json.dumps(args,indent=2)+'\n')
        with (evidence/(label+'-stdout.log')).open('wb') as out,(evidence/(label+'-stderr.log')).open('wb') as err:
            result=subprocess.run(args,stdout=out,stderr=err,timeout=1800,**kwargs)
        if result.returncode: raise RuntimeError(label+' failed: '+str(result.returncode))
    container='al-swe-'+os.environ.get('GITHUB_RUN_ID','local')
    participant=None
    try:
        catalog=json.loads(a.catalog.read_text())
        row=fetch(catalog,[a.instance],evidence/'seeds')[a.instance]
        evaluation_dataset = catalog['dataset']
        if catalog.get('frozenDatasetForEvaluation') is True:
            evaluation_dataset = str((evidence/'seeds'/'evaluation-dataset.json').resolve())
            Path(evaluation_dataset).write_text(json.dumps([row])+'\n')
        image=make_test_spec(row,namespace='swebench').instance_image_key
        command('image-pull',['docker','pull',image])
        command('subject-start',['docker','run','-d','--name',container,'--entrypoint','sleep',image,'infinity'])
        actual=subprocess.check_output(['docker','exec','-w','/testbed',container,'git','rev-parse','HEAD']).decode().strip()
        ancestry=subprocess.run(['docker','exec','-w','/testbed',container,'git','merge-base','--is-ancestor',row['base_commit'],actual],capture_output=True)
        if ancestry.returncode: raise RuntimeError('official task base is not an ancestor of prepared image cut: '+actual)
        preparation=subprocess.check_output(['docker','exec','-w','/testbed',container,'git','diff','--binary',row['base_commit'],actual])
        (evidence/'official-preparation.patch').write_bytes(preparation)
        image_identity=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]
        (evidence/'workspace-baseline.json').write_text(json.dumps(dict(taskBaseCommit=row['base_commit'],executionBaseCommit=actual,taskBaseAncestorVerified=True,image=image,imageId=image_identity['Id'],repoDigests=image_identity.get('RepoDigests',[])),indent=2)+'\n')
        module_path=Path(__file__).parents[1]/'real-code-agent/participant.py'
        spec=importlib.util.spec_from_file_location('participant',module_path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        participant=m.Participant(evidence,a.root/'participant-state',a.agent_python,a.gateway,a.model,
                                  implementation='mini-swe-agent',token_budget=a.token_budget)
        # Keep partial Agent failure and still evaluate the actual patch independently.
        try: participant.turn('swe-task',a.root,prompt=row['problem_statement'],container=container,
                              step_limit=a.step_limit,wall_time_limit_seconds=a.wall_time_limit_seconds,
                              transport_retry_limit=0)
        except Exception as error: summary['participantError']=str(error)
        observed_commands=[]
        def git(args,allow_diff=False):
            argv=['docker','exec','-w','/testbed',container,'git']+args
            observed_commands.append(argv)
            result=subprocess.run(argv,capture_output=True,timeout=120)
            if result.returncode not in ([0,1] if allow_diff else [0]):
                raise RuntimeError('Workspace patch observation failed: '+result.stderr.decode())
            return result.stdout
        patch=capture_patch(git,actual)
        (evidence/'patch-observation.json').write_text(json.dumps(dict(baseline=actual,taskBaseCommit=row['base_commit'],
            actualHead=git(['rev-parse','HEAD']).decode().strip(),commands=observed_commands,
            scope='Tracked changes since frozen base and non-ignored new files; not a full binary Workspace snapshot'),indent=2)+'\n')
        (evidence/'actual.patch').write_bytes(patch)
        for kind,value in [('agent',patch.decode()),('reference',row['patch'])]:
            predictions=evidence/(kind+'-predictions.jsonl')
            predictions.write_text(json.dumps(dict(instance_id=a.instance,model_name_or_path='agentlab-'+kind,model_patch=value))+'\n')
            command(kind+'-evaluation',[sys.executable,'-m','swebench.harness.run_evaluation',
                    '--dataset_name',evaluation_dataset,'--instance_ids',a.instance,
                    '--predictions_path',str(predictions),'--max_workers','1','--run_id',kind,'--timeout','600'],cwd=evidence)
            reports=list((evidence/'logs/run_evaluation'/kind).rglob('report.json'))
            if not reports and kind=='agent' and not value.strip():
                summary['agentResolved']=False
                summary['agentEvaluationReason']='Official evaluator skipped empty projected patch'
                continue
            if len(reports)!=1: raise RuntimeError(kind+' evaluator report missing')
            report=json.loads(reports[0].read_text())[a.instance]
            summary['harnessHealthy' if kind=='reference' else 'agentResolved']=report['resolved']
        summary['status']='completed' if summary['harnessHealthy'] else 'harness_failure'
        # A genuine unresolved subject is a valid evaluation result, not Harness failure.
        if not summary['harnessHealthy']: raise RuntimeError('reference patch did not resolve official tests')
    except Exception as error:
        summary.update(status='harness_failure',error=str(error));raise
    finally:
        if participant: participant.close()
        usage = summarize_usage(evidence/'gateway')
        usage['tokenBudgetEnforced'] = a.token_budget is not None and participant is not None and usage['exchanges'] > 0
        (evidence/'usage-observation.json').write_text(json.dumps(usage,indent=2)+'\n')
        summary['usageObservation'] = 'usage-observation.json'
        budget_decision = evidence/'token-budget-decision.json'
        if budget_decision.is_file():
            summary['budgetDecision'] = json.loads(budget_decision.read_text())
        subprocess.run(['docker','rm','-f',container],capture_output=True)
        (evidence/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
