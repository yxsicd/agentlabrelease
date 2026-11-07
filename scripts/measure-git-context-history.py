#!/usr/bin/env python3
"""Measure Git history for captured requests in a new disposable repository.

This measures Git, not TableGit, and preserves original JSON bytes per revision.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gateway-dir', required=True, type=Path)
    p.add_argument('--expected-exchanges', required=True, type=int)
    p.add_argument('--root', required=True, type=Path, help='new empty path, never reused')
    a = p.parse_args()
    if a.gateway_dir.is_symlink():
        p.error('capture directory must not be a symlink')
    source = a.gateway_dir.resolve(strict=True)
    if not source.is_dir() or a.expected_exchanges < 1:
        p.error('invalid source or expected count')
    files = sorted(x for x in source.iterdir() if re.fullmatch(r'\d{4,}\.request\.json', x.name))
    if [x.name for x in files] != [f'{i:04d}.request.json' for i in range(1, a.expected_exchanges + 1)]:
        p.error('source exchange identities differ')
    if any(x.is_symlink() or not x.is_file() for x in files):
        p.error('source contains non-regular file')
    root = a.root.absolute()
    if source == root or source in root.parents or root in source.parents:
        p.error('measurement root must be separate from source')
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root),
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0',
           'GIT_AUTHOR_NAME': 'AgentLab capture test', 'GIT_AUTHOR_EMAIL': 'test@invalid',
           'GIT_COMMITTER_NAME': 'AgentLab capture test', 'GIT_COMMITTER_EMAIL': 'test@invalid'}
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], env=env, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    git('init', '--quiet')
    refs = []
    for path in files:
        data = path.read_bytes()
        if b'\n' in data or not isinstance(json.loads(data), dict):
            raise ValueError('request is not a single-line JSON object')
        (root/'context.json').write_bytes(data)
        git('add', '--', 'context.json')
        git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '--allow-empty', '-m', 'capture '+path.name)
        refs.append((git('rev-parse', 'HEAD').decode().strip(), hashlib.sha256(data).hexdigest(), len(data)))
    def object_bytes():
        return sum(x.stat().st_size for x in (root/'.git/objects').rglob('*') if x.is_file())
    before = object_bytes()
    git('-c', 'gc.auto=0', 'gc', '--prune=now')
    after = object_bytes()
    for revision, expected, length in refs:
        raw = git('show', revision+':context.json')
        if len(raw) != length or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('historical Git byte readback mismatch')
    result = {'schema': 'agentlab.git_context_measurement.v1', 'snapshots': len(refs),
              'inputBytes': sum(x[2] for x in refs), 'looseObjectBytes': before,
              'packedObjectBytes': after, 'allRevisionsExact': True,
              'scope': 'isolated Git only; not TableGit, real database, concurrent performance, or durability acceptance',
              'sourceClass': 'captured agent requests; upstream copies and responses excluded'}
    (root/'measurement.json').open('x', encoding='utf-8').write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
