#!/usr/bin/env python3
"""Prepare one explicit fixed pointer after target GitHub Actions qualification passes."""
import argparse
import json
import hashlib
import importlib.util
from pathlib import Path


def pointer(publication):
    spec=importlib.util.spec_from_file_location('channel_plan', Path(__file__).with_name('channel-plan.py'))
    planner=importlib.util.module_from_spec(spec); spec.loader.exec_module(planner)
    channel=publication['tag']
    if publication['status'] != 'qualified' or channel not in planner.CHECKS:
        raise ValueError('fixed activation requires a qualified channel cut')
    missing=[check for check in planner.CHECKS[channel] if publication['gates'].get(check) != 'passed']
    if missing:
        raise ValueError('fixed activation requires passed GitHub Actions checks: '+', '.join(missing))
    result = dict(publication)
    result['activated'] = True
    result['activationPolicy'] = 'github-actions-qualified-v1'
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cut', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    args = parser.parse_args()
    result = pointer(json.loads((args.cut/'publication.json').read_text()))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.previous:
        previous=args.previous.read_bytes()
        previous_digest=hashlib.sha256(previous).hexdigest()
        name='previous-publication-'+previous_digest+'.json'
        (args.output/name).write_bytes(previous)
        result['previousPublicationSha256']=previous_digest
        result['previousPublicationUrl']='https://github.com/'+args.repository+'/releases/download/'+result['qualifiedReleaseTag']+'/'+name
    (args.output/('agentlab-'+result['tag']+'-publication.json')).write_text(json.dumps(result, indent=2)+'\n')
