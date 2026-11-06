#!/usr/bin/env python3
"""Summarize existing operator assessments, never launch or regrade a participant."""
import argparse
import hashlib
import html
import importlib.util
import json
import os
from collections import defaultdict
from pathlib import Path

_spec = importlib.util.spec_from_file_location('agentlab_swe_report', Path(__file__).with_name('report.py'))
_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_report)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def build(paths):
    groups = defaultdict(list)
    seen = set()
    for source in paths:
        source = Path(source).resolve(strict=True)
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        row = json.loads(raw)
        if row.get('schema') != 'agentlab.swe_report.v1':
            raise ValueError('unsupported assessment schema')
        identity = hashlib.sha256(canonical(row).encode('utf-8')).hexdigest()
        if identity in seen:
            raise ValueError('duplicate assessment')
        seen.add(identity)
        qualification, resolved = row.get('qualification'), row.get('resolved')
        if qualification not in ('qualified', 'harness_failure', 'unknown'):
            raise ValueError('invalid qualification')
        if resolved is not None and (qualification != 'qualified' or type(resolved) is not bool):
            raise ValueError('unqualified result must not be scored')
        evidence_root = source.parent.parent.resolve(strict=True)
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('assessment lacks evidence references')
        for entry in evidence:
            path = (evidence_root / entry['path']).resolve(strict=True)
            if not path.is_relative_to(evidence_root) or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('assessment evidence missing or changed')
        expected = _report.build(evidence_root)
        if canonical(row) != canonical(expected):
            raise ValueError('assessment does not match its source evidence')
        page = source.parent / 'evaluation.html'
        if not page.is_file() or page.read_text() != _report.render(expected):
            raise ValueError('assessment HTML does not match its source evidence')
        participant = row.get('participant') or {}
        execution = row.get('execution') or {}
        key = json.dumps({'benchmark': row.get('benchmark'), 'agent': participant.get('agent'),
                          'agentVersion': participant.get('version'), 'model': participant.get('model'),
                          'reasoningEffort': participant.get('reasoningEffort'),
                          'budget': execution.get('budget')}, sort_keys=True)
        groups[key].append({'task': row.get('task'), 'qualification': qualification,
                            'resolved': resolved, 'normalSubmission': row.get('normalSubmission'),
                            'assessmentSha256': digest, '_path': str(source)})
    result = []
    for key, attempts in sorted(groups.items()):
        scored = [a for a in attempts if a['qualification'] == 'qualified' and type(a['resolved']) is bool]
        result.append({'configuration': json.loads(key), 'attempts': attempts,
                       'counts': {'total': len(attempts), 'scored': len(scored),
                                  'resolved': sum(a['resolved'] is True for a in scored),
                                  'unresolved': sum(a['resolved'] is False for a in scored),
                                  'harnessFailure': sum(a['qualification'] == 'harness_failure' for a in attempts),
                                  'unknownOrUnscored': sum(a['qualification'] != 'harness_failure' and a not in scored for a in attempts)},
                       'passRate': (sum(a['resolved'] is True for a in scored) / len(scored)) if scored else None})
    return {'schema': 'agentlab.swe_campaign_report.v1', 'groups': result,
            'limitations': ['Counts are attempt-level, not an official leaderboard or a representative model ranking.',
                            'Configuration groups must not be merged across datasets, models, reasoning settings or budgets.',
                            'Harness failures and unscored attempts are excluded from the resolved-rate denominator.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assessment', action='append', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.assessment)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sections = []
    for group in report['groups']:
        links = []
        for attempt in group['attempts']:
            source = Path(attempt.pop('_path'))
            link = os.path.relpath(source.parent / 'evaluation.html', output)
            attempt['assessmentFile'] = os.path.relpath(source, output)
            links.append('<li><a href="' + html.escape(link, quote=True) + '">' + html.escape(str(attempt['task'])) + '</a> — ' + html.escape(attempt['qualification']) + '</li>')
        contents = html.escape(json.dumps({'configuration': group['configuration'], 'counts': group['counts'],
                                           'passRate': group['passRate']}, ensure_ascii=False, indent=2))
        sections.append('<section><pre>' + contents + '</pre><ul>' + ''.join(links) + '</ul></section>')
    (output / 'campaign.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (output / 'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>AgentLab 标准用例汇总</title><style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:0 1em}'
        'section{border:1px solid #ccc;border-radius:8px;margin:1em 0;padding:1em}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>AgentLab 标准用例汇总</h1><p>按数据集与执行配置分别统计；系统故障和未评分项不进入通过率分母。样本不足不代表模型排名。</p>'
        + ''.join(sections) + '</html>')


if __name__ == '__main__':
    main()
