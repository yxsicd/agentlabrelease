#!/usr/bin/env python3
"""Prepare one explicit fixed pointer after retained formal deployment gates pass."""
import argparse
import json
import hashlib
from pathlib import Path


def pointer(publication):
    gates = publication['deploymentGates']
    required = ['dActivation', 'formalHarmonyHapRestartParity', 'aBCPromotion']
    missing = [gate for gate in required if gates.get(gate) != 'passed']
    if missing:
        raise ValueError('fixed activation blocked by retained deployment gates: '+', '.join(missing))
    result = dict(publication)
    result['activated'] = True
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
