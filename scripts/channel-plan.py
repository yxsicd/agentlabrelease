#!/usr/bin/env python3
"""Freeze a reference composition and required channel tests; never activate it."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

BASE = ['clean_install', 'protocol_discovery', 'mock_copy_tree', 'tablegit_recovery']
CHECKS = {
    'aldev': BASE,
    'almain': BASE + ['cached_reinstall', 'mock_btrfs', 'harmony_iterations', 'restart_fork_parity'],
    'alprod': BASE + ['cached_reinstall', 'mock_btrfs', 'harmony_iterations',
                     'restart_fork_parity', 'real_agent', 'repeat_cold_recovery'],
}
PARENT = {'almain': 'aldev', 'alprod': 'almain'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan(target, publication, lock, raw_lock):
    if target not in CHECKS:
        raise ValueError('unknown target channel')
    source = publication['tag']
    if target == 'aldev':
        if not source.startswith('candidate-'):
            raise ValueError('aldev selects a candidate')
    elif source != PARENT[target]:
        raise ValueError(f'{target} must select {PARENT[target]}')
    if publication['environmentLockSha256'] != hashlib.sha256(raw_lock).hexdigest():
        raise ValueError('source lock digest differs')
    if publication['sourceRevision'] != lock['sourceRevision']:
        raise ValueError('source identity differs')
    if target != 'aldev' and publication['status'] not in ('fixed', 'qualified'):
        raise ValueError('upstream channel is not qualified')
    if target != 'aldev' and any(v != 'passed' for v in publication['gates'].values()):
        raise ValueError('upstream channel has unpassed gates')
    frozen = copy.deepcopy(lock)
    identity = dict(images=frozen['images'], components=frozen['components'],
                    componentGraph=frozen['componentGraph'], sourceRevision=frozen['sourceRevision'],
                    sessionSdk=publication.get('sessionSdk'), control=publication['smoke']['control'])
    return dict(schema='agentlab.channel-validation-plan.v1', targetChannel=target,
                sourceChannelOrCandidate=source, sourcePublicationSha256=digest(publication),
                sourceLockSha256=hashlib.sha256(raw_lock).hexdigest(), compositionIdentity=digest(identity),
                publication=copy.deepcopy(publication), environmentLock=frozen,
                requiredChecks=list(CHECKS[target]), freshRunnerRequired=True,
                rebuildComponents=False, automaticPromotion=False, activated=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=CHECKS, required=True)
    parser.add_argument('--publication', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.lock.read_bytes()
    result = plan(args.target, json.loads(args.publication.read_bytes()), json.loads(raw), raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:result[k] for k in ['targetChannel','compositionIdentity','requiredChecks','activated']}))
