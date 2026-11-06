#!/usr/bin/env python3
"""Generate a Terminal-Bench assessment from operator and Harbor evidence."""
import argparse
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path


def build(attempt, trial, reference):
    attempt, trial, reference = map(Path, (attempt, trial, reference))
    sources = []
    def read(path):
        raw=path.read_bytes();sources.append((path,hashlib.sha256(raw).hexdigest()))
        return json.loads(raw)
    intent=read(attempt/'intent.json')
    outcome=read(attempt/'participant-outcome.json')
    binding=read(attempt/'container-binding.json')
    usage=read(attempt/'evidence/usage-observation.json')
    lifecycle=read(attempt/'evidence/terminal-task-lifecycle.json')
    captured_participant=read(attempt/'evidence/participant.json')
    student=read(trial/'result.json')
    tests=read(trial/'verifier/ctrf.json')
    ref=read(reference/'reference-qualification.json')
    reference_trials=[]
    for name,digest in ref['evidence'].items():
        path=(reference/name).resolve(strict=True)
        if not path.is_relative_to(reference.resolve()):
            raise ValueError('reference evidence escapes its root')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('reference evidence digest mismatch')
        if name.endswith('/result.json'):
            reference_trials.append(read(path))
    if len(reference_trials)!=1:
        raise ValueError('reference trial evidence is missing or ambiguous')
    reference_trial=reference_trials[0]
    if (ref.get('qualification')!='reference_passed_once' or ref.get('oracle',{}).get('verifierReward')!=1.0
        or reference_trial.get('id')!=ref.get('oracle',{}).get('trialId')
        or reference_trial.get('exception_info') is not None or reference_trial.get('agent_info',{}).get('name')!='oracle'
        or ((reference_trial.get('verifier_result') or {}).get('rewards') or {}).get('reward')!=1.0
        or reference_trial.get('task_checksum')!=ref.get('taskChecksum')
        or ref.get('taskChecksum')!=student.get('task_checksum') or ref.get('image',{}).get('id')!=binding.get('imageId')
        or ref.get('sourceCommit')!=intent.get('taskCommit') or ref.get('benchmark')!=intent.get('benchmark')
        or ref.get('task')!=intent.get('task') or (student.get('task_name') or '').split('/')[-1]!=ref.get('task')
        or captured_participant.get('model')!=intent.get('model')
        or (student.get('agent_info',{}).get('model_info') or {}).get('name')!=intent.get('model')):
        raise ValueError('reference, task, image or source identity mismatch')
    spec=importlib.util.spec_from_file_location('agentlab_terminal_usage',Path(__file__).resolve().parents[1]/'swe-bench/usage.py')
    usage_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(usage_module)
    gateway=attempt/'evidence/gateway'
    if usage != usage_module.summarize(gateway):
        raise ValueError('usage observation differs from retained Gateway exchanges')
    for pattern in ('*.status.json','*.request.json','*.response'):
        for path in sorted(gateway.glob(pattern)):
            if not path.resolve(strict=True).is_relative_to(gateway.resolve()):
                raise ValueError('Gateway evidence escapes its root')
            sources.append((path,hashlib.sha256(path.read_bytes()).hexdigest()))
    raw=(attempt/'evidence/terminal-task-events.jsonl').read_bytes()
    sources.append((attempt/'evidence/terminal-task-events.jsonl',hashlib.sha256(raw).hexdigest()))
    events=[json.loads(line) for line in raw.split(b'\n') if line.strip()]
    calls=[e for e in events if e.get('type')=='tool_execution_end']
    errors=[e for e in calls if (e.get('exceptionClass') not in (None,'Submitted') or
             ((e.get('result') or {}).get('returncode') not in (None,0)))]
    commands=[str((e.get('action') or {}).get('command','')) for e in calls]
    merge_calls=[e for e in calls if 'git merge' in str((e.get('action') or {}).get('command',''))]
    reference_pass=ref.get('oracle',{}).get('exceptions')==0
    reward=((student.get('verifier_result') or {}).get('rewards') or {}).get('reward')
    summary=(tests.get('results') or {}).get('summary') or {}
    total,passed,failed=(summary.get(k) for k in ('tests','passed','failed'))
    valid_counts=all(type(x) is int and x>=0 for x in (total,passed,failed))
    valid_counts=valid_counts and total>0 and passed+failed>0 and passed+failed<=total
    valid_reward=type(reward) in (int,float) and reward in (0.0,1.0)
    skipped=summary.get('skipped')
    skipped_consistent=(skipped is None or (type(skipped) is int and skipped>=0
                        and passed+failed+skipped==total)) if valid_counts else False
    # A positive reward cannot establish a complete pass when the retained
    # independent test summary leaves any test skipped or unaccounted for.
    complete_pass=valid_counts and passed==total and failed==0 and skipped in (None,0)
    consistent=valid_counts and skipped_consistent and valid_reward and (reward!=1.0 or complete_pass)
    qualified=(reference_pass and student.get('exception_info') is None and outcome.get('error') is None
               and usage.get('inputOutputComplete') is True and consistent)
    resolved=(reward==1.0) if qualified else None
    return {'schema':'agentlab.terminal_bench_assessment.v1','benchmark':ref.get('benchmark'),
        'task':ref.get('task'),'taskCommit':ref.get('sourceCommit'),'taskChecksum':ref.get('taskChecksum'),
        'image':ref.get('image'),'hostArchitecture':ref.get('hostArchitecture'),
        'emulationLikely':ref.get('emulationLikely'),
        'qualification':'qualified' if qualified else 'unscored', 'resolved':resolved,'verifierReward':reward,
        'referenceReward':ref['oracle']['verifierReward'],
        'verifierTests':{k:summary.get(k) for k in ('tests','passed','failed','skipped')},
        'participant':{'agent':intent.get('participant'),'version':intent.get('version'),'model':intent.get('model'),
            'reasoning':intent.get('reasoning'),'teacherHelpCountOperatorDeclared':intent.get('teacherHelp'),
            'mcpBudgetQueryAvailable':intent.get('mcpBudgetQueryAvailable')},
        'execution':{'submitted':lifecycle.get('participantExitStatus')=='Submitted','durationMs':lifecycle.get('durationMs'),
            'toolCalls':len(calls),'toolErrors':len(errors),'originalLifecycleToolErrors':lifecycle.get('toolErrors'),
            'previousSetupFailure':intent.get('previousSetupFailure'),
            'toolErrorCorrection':'Submitted is a normal submission signal, not a tool failure',
            'observedCommands':{'inspectedReflog':any('git reflog' in x for x in commands),
               'inspectedFsck':any('git fsck' in x for x in commands),
               'attemptedMerge':any('git merge' in x for x in commands),
               'mergeConflictOutputObserved':any('CONFLICT' in str((e.get('result') or {}).get('output','')) for e in merge_calls),
               'attemptedCommit':any('git commit' in x for x in commands)}},
        'usage':{k:usage.get(k) for k in ('exchanges','inputOutputComplete','totalsObserved','fieldCoverage',
                  'cachedInputIncludedInInput','reasoningOutputIncludedInOutput')},
        'limitations':['One easy task and one attempt do not establish a model ranking or general weakness.',
            'Teacher help count is operator-declared; raw trajectory remains available.',
            'A successful outer shell exit does not establish the success of each subcommand; preserve outputs.',
            'Token enforcement is per attempt between requests; the final request can exceed the budget.',
            'This local Harbor run does not prove AgentLab native Session/Fork or budget MCP qualification.'],
        '_sources':sources}


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=Path,required=True);p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=build(a.attempt,a.trial,a.reference)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result['evidence']=[{'path':os.path.relpath(path.resolve(),out),'sha256':digest} for path,digest in result.pop('_sources')]
    (out/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    rows=[('评测资格',result['qualification']),('任务结果',result['resolved']),('验证器测试',result['verifierTests']),
          ('参考解',result['referenceReward']),('学生与帮助',result['participant']),('过程',result['execution']),
          ('Token 用量',result['usage']),('限制',result['limitations'])]
    sections=''.join('<section><h2>'+html.escape(k)+'</h2><pre>'+html.escape(json.dumps(v,ensure_ascii=False,indent=2))+'</pre></section>' for k,v in rows)
    links=''.join('<li><a href="'+html.escape(x['path'],quote=True)+'">'+html.escape(x['path'])+'</a> <code>'+x['sha256']+'</code></li>' for x in result['evidence'])
    (out/'evaluation.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>AgentLab Terminal-Bench 报告</title><style>body{font:16px system-ui;max-width:1050px;margin:2em auto;padding:0 1em;color:#172033}'
        'section{border:1px solid #ddd;border-radius:8px;margin:1em 0;padding:0 1em}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        'code{font-size:.75em;overflow-wrap:anywhere}</style><h1>Terminal-Bench fix-git 评测报告</h1>'
        '<p>由系统依据 Harbor 验证和操作侧轨迹生成。</p>'+sections+'<h2>证据与 SHA-256</h2><ul>'+links+'</ul></html>')


if __name__=='__main__': main()
