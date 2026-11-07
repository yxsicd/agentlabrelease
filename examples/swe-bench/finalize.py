#!/usr/bin/env python3
"""Summarize existing CI stages after persistence; never invoke or retry them."""
import argparse
import html
import json
from pathlib import Path


def make_status(root, persistence_outcome, run_id, task, replay):
    root = Path(root)
    assessment = root / 'real-agent/evidence/report/assessment.json'
    summaries = list((root / 'real-tablegit').glob('evidence-*/summary.json'))
    result = {'schema': 'agentlab.swe_ci_completion.v1', 'workflowRunId': run_id,
              'task': task, 'captureReplay': replay,
              'studentAssessment': 'available' if assessment.is_file() else 'unavailable',
              'persistenceStep': persistence_outcome,
              'captureRecovery': 'failed' if persistence_outcome == 'failure' else 'unknown',
              'formalAttemptCapture': 'not_qualified', 'captureRevision': None}
    if len(summaries) == 1:
        try:
            summary = json.loads(summaries[0].read_text())
            capture = summary.get('capture') or {}
            if (persistence_outcome == 'success' and summary.get('ok') is True
                    and isinstance(capture.get('revision'), str) and capture['revision']
                    and all(capture.get(k) is True for k in ('exactRows', 'exactPayloads', 'exactFiles'))):
                result['captureRecovery'] = 'reported_exact'
                result['captureRevision'] = capture.get('revision')
            elif persistence_outcome == 'failure' or summary.get('ok') is False:
                result['captureRecovery'] = 'failed'
        except (OSError, ValueError, AttributeError):
            pass
    elif persistence_outcome == 'failure':
        result['captureRecovery'] = 'failed'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--persistence-outcome', required=True,
                        choices=['success', 'failure', 'skipped', 'cancelled'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    result = make_status(args.root, args.persistence_outcome, args.run_id, args.task, args.replay)
    output = args.root / 'final-report'
    output.mkdir(parents=True, exist_ok=False)
    data = json.dumps(result, ensure_ascii=False, indent=2)
    (output / 'completion.json').write_text(data + '\n')
    (output / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Evaluation completion</title><h1>Evaluation completion</h1>'
        '<p>System stage status; student assessment remains separate. '
        'Recovery is reported by the CI fixture and is not formal Attempt admission.</p><pre>'
        + html.escape(data) + '</pre>'
        '<p><a href="../real-agent/evidence/report/evaluation.html">Independent assessment, if available</a></p></html>')


if __name__ == '__main__':
    main()
