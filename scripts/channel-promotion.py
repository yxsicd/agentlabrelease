#!/usr/bin/env python3
"""Prepare a qualified immutable channel cut without rebuilding components."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('planner', Path(__file__).with_name('channel-plan.py'))
planner = importlib.util.module_from_spec(spec); spec.loader.exec_module(planner)


def prepare(plan, qualification, raw_lock, repository):
    original = plan['publication']
    actual = planner.plan(plan['targetChannel'], original, json.loads(raw_lock), raw_lock)
    if actual != plan:
        raise ValueError('source plan changed')
    for field in ['targetChannel', 'compositionIdentity', 'sourceLockSha256', 'sourcePublicationSha256']:
        if qualification[field] != plan[field]:
            raise ValueError('qualification differs from selected '+field)
    if not qualification['qualified'] or any(qualification['checks'].get(c, {}).get('status') != 'passed'
                                             for c in plan['requiredChecks']):
        raise ValueError('required checks have not passed')
    run = str(qualification['githubRunId'])
    if not run.isdigit():
        raise ValueError('qualification has no durable GitHub run')
    tag = 'qualified-'+plan['targetChannel']+'-'+run
    base = 'https://github.com/'+repository+'/releases/download/'+tag+'/'
    publication = copy.deepcopy(original)
    publication.update(schema='agentlab.reference_publication.v3', status='qualified', tag=plan['targetChannel'],
                       qualifiedReleaseTag=tag, compositionIdentity=plan['compositionIdentity'],
                       environmentLockUrl=base+'environment-lock.json',
                       qualificationUrl=base+'qualification.json',
                       gates={c:'passed' for c in plan['requiredChecks']},
                       deploymentGates=copy.deepcopy(original.get('deploymentGates', original.get('gates', {}))),
                       sourceChannelOrCandidate=plan['sourceChannelOrCandidate'],
                       sourcePublicationSha256=plan['sourcePublicationSha256'],
                       activated=False)
    return tag, publication


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = (args.source/'environment-lock.json').read_bytes()
    tag, publication = prepare(json.loads((args.source/'plan.json').read_text()),
                               json.loads(args.qualification.read_text()), raw, args.repository)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'environment-lock.json').write_bytes(raw)
    (args.output/'publication.json').write_text(json.dumps(publication, indent=2)+'\n')
    (args.output/'qualification.json').write_bytes(args.qualification.read_bytes())
    print(tag)
