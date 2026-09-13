#!/usr/bin/env python3
"""Prepare one explicit fixed pointer after retained formal deployment gates pass."""
import argparse
import json
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
    args = parser.parse_args()
    result = pointer(json.loads((args.cut/'publication.json').read_text()))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/('agentlab-'+result['tag']+'-publication.json')).write_text(json.dumps(result, indent=2)+'\n')
