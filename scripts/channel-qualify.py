#!/usr/bin/env python3
"""Close baseline and real-Agent check receipts against one required-check set."""
import argparse
import json
from pathlib import Path


def qualify(plan, baseline, real=None):
    result = dict(schema='agentlab.channel-qualification.v1', targetChannel=plan['targetChannel'],
                  compositionIdentity=plan['compositionIdentity'], sourceLockSha256=plan['sourceLockSha256'],
                  sourcePublicationSha256=plan['sourcePublicationSha256'], requiredChecks=plan['requiredChecks'],
                  checks={}, qualified=False, activated=False)
    for receipt in [baseline, real]:
        if receipt is None:
            continue
        for key in ['compositionIdentity', 'sourceLockSha256', 'targetChannel']:
            if receipt[key] != plan[key]:
                raise ValueError('check receipt belongs to another '+key)
    result['checks'] = dict(baseline['checks'])
    if real is not None:
        result['checks']['real_agent'] = real
    for check in plan['requiredChecks']:
        result['checks'].setdefault(check, dict(status='not_run'))
    result['qualified'] = all(result['checks'][c]['status'] == 'passed' for c in plan['requiredChecks'])
    result['githubRunId'] = baseline['githubRunId']
    result['producerRevision'] = baseline['producerRevision']
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((args.root/'channel-validation-plan/plan.json').read_text())
    path = args.root/'channel-validation-evidence/channel-qualification.json'
    baseline = json.loads(path.read_text()) if path.exists() else dict(
        compositionIdentity=plan['compositionIdentity'], sourceLockSha256=plan['sourceLockSha256'],
        targetChannel=plan['targetChannel'], checks={}, githubRunId=None, producerRevision=None)
    path = args.root/'real-pi-harmony-acceptance/channel-real-check.json'
    real = json.loads(path.read_text()) if path.exists() else None
    result = qualify(plan, baseline, real)
    (args.root/'qualification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['qualified'] else 1)
