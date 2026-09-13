#!/usr/bin/env python3
"""Execute public demos against one frozen plan; retain every check outcome."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time


def execute(plan, source, root, run=subprocess.run):
    root.mkdir(parents=True, exist_ok=True)
    publication, lock = plan['publication'], plan['environmentLock']
    sdk = source / 'session-sdk.json'
    sdk.write_text(json.dumps(publication['sessionSdk']))
    pack = publication['smoke']['pack']
    asset = next(a for a in publication['assets'] if a['url'] == pack)
    runtime = source / 'harness-runtime.json'
    runtime.write_text(json.dumps(dict(artifact=pack, bytes=asset['bytes'], sha256=asset['sha256'])))
    env = dict(os.environ, AGENTLAB_CI_ROOT=str(root),
               AGENTLAB_RELEASE_CHANNEL=plan['sourceChannelOrCandidate'],
               AGENTLAB_COMPOSITION_DIR=str(source))
    image = lock['images'][0]['reference']
    volume = next(c['volume'] for c in lock['components'] if c['slot'] == 'release')
    install = ['bash', 'scripts/ci-public-install-deploy-smoke.sh']
    mock = ['python3', 'scripts/ci-mock-agent-smoke.py', '--bin-dir', str(root/'standalone/bin'),
            '--evidence', str(root/'mock-evidence'), '--storage', str(root/'mock-storage'), '--backend', 'copy-tree']
    tablegit = ['python3', 'examples/tablegit-session/run.py', '--image', image,
                '--runtime-volume', volume, '--sdk-program', str(sdk), '--root', str(root/'tablegit-demo'),
                '--capture-evidence', str(root/'mock-evidence'), '--capture-agent-kind', 'mock']
    commands = {
        'clean_install': install,
        'protocol_discovery': ['python3', 'examples/run.py', 'protocol', '--runtime-program', str(runtime),
                               '--root', str(root/'protocol')],
        'mock_copy_tree': mock,
        'tablegit_recovery': tablegit,
        'cached_reinstall': install,
        'harmony_iterations': ['python3', 'examples/harmony-build/run.py', '--install-root', str(root),
                               '--root', str(root/'harmony-build-demo')],
        'repeat_cold_recovery': [str(root/'tablegit-repeat') if a == str(root/'tablegit-demo') else a for a in tablegit],
    }
    receipt = dict(schema='agentlab.channel-validation.v1', targetChannel=plan['targetChannel'],
                   compositionIdentity=plan['compositionIdentity'], sourceLockSha256=plan['sourceLockSha256'],
                   githubRunId=os.environ.get('GITHUB_RUN_ID'), producerRevision=os.environ.get('GITHUB_SHA'),
                   checks={}, qualified=False, activated=False)
    def save():
        receipt['qualified'] = all(receipt['checks'].get(c, {}).get('status') == 'passed' for c in plan['requiredChecks'])
        (root/'channel-qualification.json').write_text(json.dumps(receipt, indent=2)+'\n')
    save()
    for check in plan['requiredChecks']:
        command = commands.get(check)
        record = dict(status='not_run')
        receipt['checks'][check] = record
        if command:
            record.update(status='running', started=time.time(), command=command)
            save()
            try:
                with (root/(check+'.log')).open('wb') as log:
                    result = run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
                record.update(status='passed' if result.returncode == 0 else 'failed', exitCode=result.returncode)
            except Exception as error:
                record.update(status='failed', error=str(error))
            record['finished'] = time.time()
        else:
            record['reason'] = 'Dedicated tier adapter not connected; this check is not certified.'
        save()
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    spec = importlib.util.spec_from_file_location('channel_plan', Path(__file__).with_name('channel-plan.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    frozen = json.loads((source/'plan.json').read_text())
    actual = module.plan(frozen['targetChannel'], json.loads((source/'publication.json').read_text()),
                         json.loads((source/'environment-lock.json').read_text()), (source/'environment-lock.json').read_bytes())
    if actual != frozen:
        raise ValueError('downloaded inputs differ from frozen plan')
    result = execute(frozen, source, args.root.resolve())
    print(json.dumps(result))
    raise SystemExit(0 if result['qualified'] else 1)
