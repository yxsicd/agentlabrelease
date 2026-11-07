#!/usr/bin/env python3
"""Summarize existing CI stages after persistence; never invoke or retry them."""
import argparse
import hashlib
import html
import json
from pathlib import Path


def make_status(root, persistence_outcome, run_id, task, replay, *, run_attempt='1', source_run_id=None,
                subject_outcome='unknown', assessment_outcome='unknown'):
    root = Path(root)
    assessment = root / 'real-agent/evidence/report/assessment.json'
    summaries = list((root / 'real-tablegit').glob('evidence-*/summary.json'))
    assessment_status = 'unavailable'
    if assessment.is_file():
        try:
            doc = json.loads(assessment.read_text())
            if not isinstance(doc, dict) or doc.get('schema') != 'agentlab.swe_report.v1':
                assessment_status = 'invalid'
            elif doc.get('task') != task:
                assessment_status = 'task_mismatch'
            else:
                assessment_status = 'available'
        except (OSError, ValueError):
            assessment_status = 'invalid'
    result = {'schema': 'agentlab.swe_ci_completion.v1', 'workflowRunId': run_id,
              'workflowRunAttempt': run_attempt, 'sourceWorkflowRunId': source_run_id if replay else None,
              'task': task, 'captureReplay': replay,
              'subjectStep': subject_outcome, 'assessmentStep': assessment_outcome,
              'studentAssessment': assessment_status,
              'persistenceStep': persistence_outcome,
              'captureRecovery': 'failed' if persistence_outcome == 'failure' else 'unknown',
              'formalAttemptCapture': 'not_qualified', 'captureRevision': None}
    if len(summaries) == 1:
        try:
            summary = json.loads(summaries[0].read_text())
            capture = summary.get('capture') or {}
            if persistence_outcome == 'failure' or summary.get('ok') is False:
                result['captureRecovery'] = 'failed'
            elif persistence_outcome == 'success' and summary.get('ok') is True:
                directory = summaries[0].parent
                recovery = json.loads((directory / 'capture-recovery.json').read_text())
                manifest = json.loads((directory / 'capture-commit-manifest.json').read_text())
                bundle_info = json.loads((directory / 'bundle-recovery.json').read_text())
                bundle = directory / 'tablegit-capture.bundle'
                revision = capture.get('revision')
                flags = ('exactRows', 'exactPayloads', 'exactFiles')
                counts = ('rowCount', 'observationCount', 'fileCount', 'byteCount')
                matches = (isinstance(revision, str) and bool(revision)
                           and revision == recovery.get('revision') == manifest.get('captureRevision')
                           and all(capture.get(k) is True and recovery.get(k) is True for k in flags)
                           and all(type(capture.get(k)) is int and capture[k] >= 0
                                   and capture[k] == recovery.get(k) for k in counts)
                           and all(bundle_info.get(k) == revision for k in
                                   ('restoredHead', 'expectedCaptureRevision', 'exportRevision'))
                           and bundle_info.get('historyExported') is True
                           and bundle_info.get('captureHistoryPresent') is True
                           and bundle.is_file() and bundle.stat().st_size == bundle_info.get('byteLength'))
                if matches:
                    digest = hashlib.sha256()
                    with bundle.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(block)
                    matches = digest.hexdigest() == bundle_info.get('sha256')
                result['captureRecovery'] = 'reported_exact' if matches else 'inconsistent'
                if matches:
                    result['captureRevision'] = revision
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
    parser.add_argument('--source-run-id')
    parser.add_argument('--run-attempt', default='1')
    parser.add_argument('--subject-outcome', default='unknown')
    parser.add_argument('--assessment-outcome', default='unknown')
    args = parser.parse_args()
    result = make_status(args.root, args.persistence_outcome, args.run_id, args.task, args.replay,
                         run_attempt=args.run_attempt, source_run_id=args.source_run_id,
                         subject_outcome=args.subject_outcome, assessment_outcome=args.assessment_outcome)
    output = args.root / 'final-report'
    output.mkdir(parents=True, exist_ok=False)
    data = json.dumps(result, ensure_ascii=False, indent=2)
    (output / 'completion.json').write_text(data + '\n')
    assessment_link = ('<p><a href="../real-agent/evidence/report/evaluation.html">Independent assessment</a></p>'
                       if result['studentAssessment'] == 'available'
                       and (args.root / 'real-agent/evidence/report/evaluation.html').is_file() else '')
    (output / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Evaluation completion</title><h1>Evaluation completion</h1>'
        '<p>System stage status; student assessment remains separate. '
        'Recovery is reported by the CI fixture and is not formal Attempt admission.</p><pre>'
        + html.escape(data) + '</pre>' + assessment_link + '</html>')


if __name__ == '__main__':
    main()
