#!/usr/bin/env python3
"""Build an operator-owned SWE report from preserved evidence, without model calls."""
import argparse
import hashlib
import html
import json
from pathlib import Path


def build(evidence):
    evidence = Path(evidence)
    sources = {}

    def read(path):
        path = evidence / path
        if not path.is_file():
            return None
        raw = path.read_bytes()
        sources[str(path.relative_to(evidence))] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    summary = read('summary.json')
    if not isinstance(summary, dict) or summary.get('schema') != 'agentlab.swe_acceptance.v1':
        raise ValueError('missing or invalid operator summary')
    task = summary.get('instanceId')
    if not isinstance(task, str) or not task:
        raise ValueError('missing instance ID')
    participant = read('participant.json') or {}
    lifecycle = read('swe-task-lifecycle.json') or {}
    usage = read('usage-observation.json') or {}
    seeds = read('seeds/seed-receipt.json') or {}
    baseline = read('workspace-baseline.json') or {}

    def evaluation(kind):
        matches = list((evidence / 'logs' / 'run_evaluation' / kind).glob('*/*/report.json'))
        if len(matches) != 1:
            return None
        doc = read(matches[0].relative_to(evidence))
        result = doc.get(task) if isinstance(doc, dict) else None
        if not isinstance(result, dict) or type(result.get('resolved')) is not bool:
            return None
        tests = result.get('tests_status') or {}
        counts = {}
        for key in ('FAIL_TO_PASS', 'PASS_TO_PASS'):
            status = tests.get(key)
            if isinstance(status, dict) and isinstance(status.get('success'), list) and isinstance(status.get('failure'), list):
                counts[key] = {'passed': len(status['success']), 'failed': len(status['failure'])}
            else:
                counts[key] = None
        return {'resolved': result['resolved'], 'tests': counts}

    agent, reference = evaluation('agent'), evaluation('reference')
    # A candidate result is scoreable only with an independently passing reference.
    if summary.get('harnessHealthy') is False or (reference is not None and not reference['resolved']):
        qualification = 'harness_failure'
    elif reference is not None and summary.get('harnessHealthy') is True and summary.get('status') == 'completed':
        qualification = 'qualified'
    else:
        qualification = 'unknown'
    score = agent['resolved'] if qualification == 'qualified' and agent is not None else None
    exit_status = lifecycle.get('participantExitStatus')
    # Do not infer successful submission merely from a passing captured patch.
    submitted = True if exit_status == 'Submitted' else (False if exit_status is not None or lifecycle.get('exitCode') not in (None, 0) else None)
    seed = next((item for item in seeds.get('seeds', []) if item.get('instanceId') == task), {})
    decision = summary.get('budgetDecision') or {}
    return {
        'schema': 'agentlab.swe_report.v1', 'benchmark': seeds.get('dataset'), 'task': task,
        'seed': {'baseCommit': seed.get('baseCommit'), 'sourceRecordSha256': seed.get('sourceRecordSha256'),
                 'executionBaseCommit': baseline.get('executionBaseCommit'), 'imageId': baseline.get('imageId')},
        'participant': {'agent': participant.get('implementation'), 'version': participant.get('packageVersion'),
                        'model': participant.get('model'), 'reasoningEffort': participant.get('reasoningEffort'),
                        'teacherHelp': None},
        'qualification': qualification, 'resolved': score, 'agentEvaluation': agent,
        'referenceEvaluation': reference, 'normalSubmission': submitted,
        'execution': {'exitStatus': exit_status, 'exitCode': lifecycle.get('exitCode'),
                      'durationMs': lifecycle.get('durationMs'), 'toolCalls': lifecycle.get('completedToolCalls'),
                      'toolErrors': lifecycle.get('toolErrors'), 'budget': summary.get('budget'),
                      'budgetDecision': decision or None},
        'usage': {'exchanges': usage.get('exchanges'), 'inputOutputComplete': usage.get('inputOutputComplete'),
                  'totalsObserved': usage.get('totalsObserved'), 'fieldCoverage': usage.get('fieldCoverage'),
                  'cachedInputIncludedInInput': usage.get('cachedInputIncludedInInput'),
                  'reasoningOutputIncludedInOutput': usage.get('reasoningOutputIncludedInOutput')},
        'limitations': ['Reference qualification does not prove formal AgentLab Session/Fork.',
                        'Tool errors are not automatically unproductive; inspect the trace.',
                        'Missing teacher-help evidence and usage fields remain unknown.',
                        'Token budget is checked between requests; the last request can overshoot.'],
        'evidence': [{'path': key, 'sha256': value} for key, value in sorted(sources.items())],
    }


def render(report, completion_link=None):
    def val(value):
        return html.escape('未知' if value is None else json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value))
    labels = [('数据集', report['benchmark']), ('用例', report['task']), ('评分资格', report['qualification']),
              ('独立评分结果', report['resolved']), ('学生正常提交', report['normalSubmission']),
              ('官方参考解', report['referenceEvaluation']), ('学生补丁', report['agentEvaluation']),
              ('参与者', report['participant']), ('执行与预算', report['execution']), ('Token 用量', report['usage']),
              ('限定与说明', report['limitations'])]
    rows = ''.join(f'<section><h2>{val(label)}</h2><pre>{val(value)}</pre></section>' for label, value in labels)
    links = ''.join('<li><a href="../' + html.escape(item['path'], quote=True) + '">' + val(item['path']) + '</a> <code>' + item['sha256'] + '</code></li>' for item in report['evidence'])
    completion = ('<p><a href="' + html.escape(completion_link, quote=True) + '">查看采集和恢复状态</a></p>'
                  if completion_link else '')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>AgentLab SWE 评测报告</title><style>body{font:16px system-ui;max-width:1080px;margin:2em auto;padding:0 1em;color:#172033}'
            'section{border:1px solid #ddd;border-radius:8px;margin:1em 0;padding:0 1em}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
            'code{font-size:.75em;overflow-wrap:anywhere}h2{font-size:1em}</style><h1>AgentLab SWE 评测报告</h1>'
            '<p>由评测系统从保留的证据生成；学生未参与评分。</p>' + completion + rows + '<h2>证据与 SHA-256</h2><ul>' + links + '</ul></html>')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--completion-link', help='Relative link to the workflow completion report')
    args = parser.parse_args()
    if args.output.resolve().parent != args.evidence.resolve():
        parser.error('output must be a new direct child of the evidence directory')
    report = build(args.evidence)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'assessment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'evaluation.html').write_text(render(report, args.completion_link))


if __name__ == '__main__':
    main()
