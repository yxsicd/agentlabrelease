#!/usr/bin/env python3
"""Bind operator-controlled real execution and persistence outcomes to the frozen composition."""
import argparse
import json
import os
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((args.source/'plan.json').read_text())
    subject, persistence = os.environ['SUBJECT_OUTCOME'], os.environ['PERSISTENCE_OUTCOME']
    fresh = not os.environ.get('CAPTURE_RUN_ID')
    record = dict(schema='agentlab.channel-real-check.v1', compositionIdentity=plan['compositionIdentity'],
                  sourceLockSha256=plan['sourceLockSha256'], targetChannel=plan['targetChannel'],
                  githubRunId=os.environ.get('GITHUB_RUN_ID'), producerRevision=os.environ.get('GITHUB_SHA'),
                  validationDependenciesSha256=plan.get('validationDependenciesSha256'),
                  check='real_agent', status='passed' if subject == persistence == 'success' and fresh else 'failed',
                  subjectOutcome=subject, persistenceOutcome=persistence, freshSubjectExecution=fresh)
    args.root.mkdir(parents=True, exist_ok=True)
    (args.root/'channel-real-check.json').write_text(json.dumps(record, indent=2)+'\n')
