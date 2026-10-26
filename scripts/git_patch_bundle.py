#!/usr/bin/env python3
"""Offline patch-file capture/verification/restore; no SessionFS or MCP authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

SCHEMA = 'agentlab.offline.git-patch-bundle.v1'
FIELDS = {'schema', 'repositoryId', 'baseCommit', 'targetTree', 'patchSHA256',
          'patchBytes', 'excludedPaths', 'captureScope'}
SCOPE = 'base-plus-nonexcluded-worktree-changes'

class Rejected(Exception):
    pass

def require(condition, message):
    if not condition:
        raise Rejected(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def git(repo, *args, env=None, data=None):
    e = os.environ.copy()
    for k in list(e):
        if k.startswith('GIT_'):
            del e[k]
    e.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
             GIT_TERMINAL_PROMPT='0')
    if env:
        e.update(env)
    r = subprocess.run(['git', '--no-replace-objects', '-C', str(repo),
                        '-c', 'core.hooksPath=' + os.devnull,
                        '-c', 'core.fsmonitor=false', '-c', 'core.autocrlf=false',
                        '-c', 'protocol.ext.allow=never', *args],
                       input=data, capture_output=True, env=e, timeout=60)
    require(r.returncode == 0, 'git ' + args[0] + ' failed: ' +
            r.stderr.decode(errors='replace')[-1600:])
    return r.stdout

def object_id(value):
    return isinstance(value, str) and re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', value)

def repository(path):
    root = Path(path).resolve(strict=True)
    require(root.is_dir(), 'repository must be a local directory')
    top = Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel')).strip()).resolve()
    require(root == top, 'use the repository root, not a subdirectory')
    return root

def relative_path(path):
    require(isinstance(path, str) and path and '\x00' not in path and
            '\\' not in path, 'invalid exclusion path')
    p = PurePosixPath(path)
    require(not p.is_absolute() and str(p) == path and
            all(x not in ('.', '..', '.git') for x in p.parts),
            'exclusions must be canonical repository-relative paths')
    require(path != '.', 'cannot exclude the entire repository')
    return path

def no_filters_or_submodules(repo, env=None):
    records = git(repo, 'ls-files', '--stage', '-z', env=env).split(b'\0')
    require(not any(x.startswith(b'160000 ') for x in records),
            'submodules/embedded repositories are not supported by this helper')
    names = git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', env=env)
    if names:
        values = git(repo, 'check-attr', '-z', '--stdin', 'filter', data=names).split(b'\0')
        require(all(v in (b'unspecified', b'unset') for v in values[2::3]),
                'Git clean/smudge filters require a separately qualified adapter')

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False) + '\n').encode()

def read_bundle(path, identity, manifest_sha):
    root = Path(path)
    require(not root.is_symlink() and root.is_dir(), 'bundle must be a real directory')
    require(set(p.name for p in root.iterdir()) == {'changes.patch', 'manifest.json'},
            'bundle incomplete or has unexpected files; do not replay capture')
    for name in ('changes.patch', 'manifest.json'):
        require(not (root/name).is_symlink() and (root/name).is_file(),
                'bundle members must be regular files')
    raw = (root/'manifest.json').read_bytes()
    require(digest(raw) == manifest_sha, 'manifest does not match trusted checkpoint digest')
    def unique(pairs):
        d = {}
        for k, v in pairs:
            require(k not in d, 'duplicate manifest key')
            d[k] = v
        return d
    m = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(m, dict) and set(m) == FIELDS, 'invalid manifest fields')
    require(m['schema'] == SCHEMA and m['repositoryId'] == identity,
            'schema or registered repository identity mismatch')
    require(object_id(m['baseCommit']) and object_id(m['targetTree']), 'invalid Git object identity')
    require(m['captureScope'] == SCOPE, 'unsupported capture scope')
    require(isinstance(m['excludedPaths'], list), 'invalid exclusions')
    require(m['excludedPaths'] == sorted(set(relative_path(x) for x in m['excludedPaths'])),
            'exclusions must be sorted and unique')
    patch = (root/'changes.patch').read_bytes()
    require(type(m['patchBytes']) is int and m['patchBytes'] == len(patch), 'patch size mismatch')
    require(m['patchSHA256'] == digest(patch), 'patch digest mismatch')
    return root, m, patch

def capture(args):
    repo = repository(args.repo)
    require(args.repository_id.strip(), 'repository identity is required')
    out = Path(args.output).absolute()
    require(not out.exists() and not out.is_symlink(), 'output already exists; verify/read back it instead')
    require(out.parent.is_dir(), 'output parent must exist')
    require(not out.resolve().is_relative_to(repo), 'output must be outside the captured repository')
    excluded = sorted(set(relative_path(x) for x in args.exclude))
    base = git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    index = Path(os.fsdecode(git(repo, 'rev-parse', '--git-path', 'index')).strip())
    if not index.is_absolute():
        index = repo/index
    initial_index = index.read_bytes() if index.exists() else None
    no_filters_or_submodules(repo)
    with tempfile.TemporaryDirectory(prefix='agentlab-patch-index-') as temp:
        env = {'GIT_INDEX_FILE': str(Path(temp)/'index')}
        git(repo, 'read-tree', base, env=env)
        git(repo, 'add', '-A', '--', '.', env=env)
        # Negative git-add pathspecs can reject already ignored directories.
        # Reset excluded paths to baseline in the PRIVATE index instead.
        def omitted(name):
            return any(name == os.fsencode(x) or name.startswith(os.fsencode(x) + b'/')
                       for x in excluded)
        remove = [n for n in git(repo, 'ls-files', '-z', env=env).split(b'\0') if n and omitted(n)]
        if remove:
            git(repo, 'update-index', '--force-remove', '-z', '--stdin', env=env,
                data=b'\0'.join(remove) + b'\0')
        original = []
        for entry in git(repo, 'ls-tree', '-r', '-z', base).split(b'\0'):
            if not entry:
                continue
            meta, name = entry.split(b'\t', 1)
            mode, kind, oid = meta.split(b' ')
            if omitted(name):
                original.append(mode + b' ' + oid + b'\t' + name)
        if original:
            git(repo, 'update-index', '-z', '--index-info', env=env,
                data=b'\0'.join(original) + b'\0')
        no_filters_or_submodules(repo, env)
        tree = git(repo, 'write-tree', env=env).decode().strip()
        patch = git(repo, 'diff', '--binary', '--full-index', '--no-ext-diff',
                    '--no-textconv', base, tree)
    require(git(repo, 'rev-parse', 'HEAD').decode().strip() == base,
            'HEAD changed during capture; bundle not published')
    require((index.read_bytes() if index.exists() else None) == initial_index,
            'real index changed during capture; bundle not published')
    m = dict(schema=SCHEMA, repositoryId=args.repository_id, baseCommit=base,
             targetTree=tree, patchSHA256=digest(patch), patchBytes=len(patch),
             excludedPaths=excluded, captureScope=SCOPE)
    raw = canonical(m)
    # Exclusive generation reservation; manifest is the last completion marker.
    # Partial output is intentionally retained and rejected, never overwritten.
    out.mkdir(mode=0o700)
    for name, data in [('changes.patch', patch), ('manifest.json', raw)]:
        with (out/name).open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    read_bundle(out, args.repository_id, digest(raw))
    return dict(status='captured', bundle=str(out), manifestSHA256=digest(raw), **m)

def verify(args):
    _, m, _ = read_bundle(args.bundle, args.repository_id, args.manifest_sha256)
    return dict(status='verified_file_bundle_only', **m)

def restore(args):
    root, m, patch = read_bundle(args.bundle, args.repository_id, args.manifest_sha256)
    source = repository(args.source_repo)
    require(git(source, 'cat-file', '-t', m['baseCommit']).strip() == b'commit',
            'exact baseline commit is unavailable locally')
    no_filters_or_submodules(source)
    dest = Path(args.destination).absolute()
    require(not dest.exists() and not dest.is_symlink(), 'destination exists; do not replay restore')
    require(dest.parent.is_dir(), 'destination parent must exist')
    require(not dest.resolve().is_relative_to(source), 'destination must be outside source repository')
    dest.mkdir(mode=0o700)
    git(dest, 'init', '-q')
    git(dest, '-c', 'protocol.file.allow=always', 'fetch', '-q', '--no-tags',
        '--depth=1', str(source), m['baseCommit'])
    git(dest, 'checkout', '-q', '--detach', m['baseCommit'])
    require(git(dest, 'rev-parse', 'HEAD').decode().strip() == m['baseCommit'], 'baseline mismatch')
    no_filters_or_submodules(dest)
    if patch:
        # Use already-verified immutable bytes, not a second open of a mutable path.
        git(dest, 'apply', '--check', '--index', '--binary', '-', data=patch)
        git(dest, 'apply', '--index', '--binary', '-', data=patch)
    tree = git(dest, 'write-tree').decode().strip()
    require(tree == m['targetTree'], 'restored tree mismatch; retain partial destination for readback')
    return dict(status='restored_code_tree', destination=str(dest), **m)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    c = commands.add_parser('capture')
    c.add_argument('--repo', required=True)
    c.add_argument('--repository-id', required=True)
    c.add_argument('--output', required=True, help='new immutable generation outside repository')
    c.add_argument('--exclude', action='append', default=[], help='explicit repository-relative path')
    for name in ('verify', 'restore'):
        p = commands.add_parser(name)
        p.add_argument('--bundle', required=True)
        p.add_argument('--repository-id', required=True, help='from trusted existing repository registry')
        p.add_argument('--manifest-sha256', required=True, help='from trusted existing checkpoint, not self-read')
        if name == 'restore':
            p.add_argument('--source-repo', required=True, help='local source of exact baseline Git objects')
            p.add_argument('--destination', required=True, help='must not exist')
    args = parser.parse_args()
    try:
        print(json.dumps({'capture': capture, 'verify': verify, 'restore': restore}[args.command](args),
                         sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'rejected', 'command': args.command, 'error': str(exc),
                          'retry': 'none; inspect exact output/destination before any new action'}), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
