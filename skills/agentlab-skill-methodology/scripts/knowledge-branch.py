#!/usr/bin/env python3
"""Synchronize one admitted public knowledge history; never change business refs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit


def git(repo, *args, timeout=60):
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError('git read/preflight failed (exit %s)' % r.returncode)
    return r.stdout


def endpoint(value, local):
    if local and Path(value).is_absolute():
        return
    u = urlsplit(value)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('repository must be credential-free HTTPS; local paths require --allow-local')


def binding(value, local=False):
    required = {'schema', 'targetId', 'sources', 'target', 'hub', 'entrypoint'}
    if set(value) != required or value['schema'] != 'agentlab.knowledge-branch.v1':
        raise ValueError('invalid knowledge binding schema')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}', value['targetId']):
        raise ValueError('invalid targetId')
    if value['entrypoint'] != 'AGENTS.md' or not value['sources']:
        raise ValueError('missing entrypoint/sources')
    for source in value['sources']:
        if set(source) != {'repository', 'revision'} or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', source['revision']):
            raise ValueError('each source needs an immutable full Git revision')
        endpoint(source['repository'], local)
    for name in ['target', 'hub']:
        ep = value[name]
        if set(ep) != {'repository', 'branch'}:
            raise ValueError('invalid endpoint')
        endpoint(ep['repository'], local)
    if value['target']['branch'] != 'al-knowledge':
        raise ValueError('target destination must be al-knowledge')
    if value['hub']['branch'] != 'knowledge/targets/' + value['targetId']:
        raise ValueError('hub destination must match the admitted target namespace')
    return value


def remote_head(ep):
    r = subprocess.run(['git', 'ls-remote', '--exit-code', ep['repository'], 'refs/heads/' + ep['branch']], capture_output=True, timeout=45)
    if r.returncode == 2:
        return None
    if r.returncode:
        raise RuntimeError('remote read failed (exit %s)' % r.returncode)
    rows = r.stdout.decode().splitlines()
    if len(rows) != 1:
        raise ValueError('ambiguous remote branch')
    return rows[0].split()[0]


def fetch(repo, ep, expected):
    git(repo, 'fetch', '--quiet', '--no-tags', ep['repository'], 'refs/heads/' + ep['branch'])
    if git(repo, 'rev-parse', 'FETCH_HEAD').decode().strip() != expected:
        raise ValueError('remote changed during read; refresh before any push')


def inventory(repo, revision, admitted):
    roots = git(repo, 'rev-list', '--max-parents=0', revision).decode().splitlines()
    if len(roots) != 1:
        raise ValueError('knowledge history must have one independent root')
    files = []
    for row in git(repo, 'ls-tree', '-rz', '--full-tree', revision).split(b'\0'):
        if not row:
            continue
        meta, rawpath = row.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        path = rawpath.decode('utf-8')
        if mode not in ['100644', '100755'] or kind != 'blob':
            raise ValueError('links/submodules are not public knowledge files')
        if path not in ['AGENTS.md', 'knowledge.json', 'LICENSE', 'NOTICE'] and not path.startswith(('skills/', 'cases/', 'evidence/')):
            raise ValueError('file outside public knowledge layout: ' + path)
        size = int(git(repo, 'cat-file', '-s', oid))
        if size > 262144:
            raise ValueError('knowledge file exceeds 256KiB')
        raw = git(repo, 'cat-file', 'blob', oid)
        raw.decode('utf-8')
        if b'\0' in raw:
            raise ValueError('binary payload must remain an external evidence asset')
        files.append({'path': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    if len(files) > 256 or sum(x['bytes'] for x in files) > 2097152:
        raise ValueError('knowledge branch exceeds bounded text inventory')
    actual = json.loads(git(repo, 'show', revision + ':knowledge.json'))
    if actual != admitted:
        raise ValueError('candidate binding differs from independently admitted binding')
    if 'AGENTS.md' not in [x['path'] for x in files]:
        raise ValueError('missing agent entrypoint')
    return {'rootCommit': roots[0], 'files': files, 'bytes': sum(x['bytes'] for x in files)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['sync', 'verify'])
    p.add_argument('--binding', required=True, type=Path)
    p.add_argument('--expected-root', required=True, help='independently admitted knowledge root from the catalog/bootstrap receipt')
    p.add_argument('--from', dest='origin', required=True, choices=['target', 'hub'])
    p.add_argument('--receipt', required=True, type=Path)
    p.add_argument('--create-destination', action='store_true')
    p.add_argument('--allow-local', action='store_true', help='explicit offline-test/local-bare mode')
    a = p.parse_args()
    if a.receipt.exists() or not a.receipt.parent.is_dir():
        p.error('receipt must be new and have an existing parent; never overwrite a prior operation')
    state = {'schema': 'agentlab.knowledge-sync-receipt.v1', 'startedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'action': a.action, 'pushAttempts': 0, 'state': 'preflight', 'automaticRetry': False}
    def save():
        tmp = a.receipt.with_name(a.receipt.name + '.tmp-' + str(os.getpid()))
        tmp.write_text(json.dumps(state, indent=2) + '\n')
        os.replace(tmp, a.receipt)
    save()
    try:
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', a.expected_root):
            raise ValueError('expected root must be a full Git commit')
        b = binding(json.loads(a.binding.read_text()), a.allow_local)
        src = b[a.origin]
        dst = b['hub' if a.origin == 'target' else 'target']
        state.update(targetId=b['targetId'], source=src, destination=dst)
        with tempfile.TemporaryDirectory(prefix='al-knowledge-sync-') as work:
            repo = Path(work)
            subprocess.run(['git', 'init', '--bare', '--quiet', str(repo)], check=True, capture_output=True)
            head = remote_head(src)
            if head is None:
                raise ValueError('source branch absent')
            fetch(repo, src, head)
            inv = inventory(repo, head, b)
            if inv['rootCommit'] != a.expected_root:
                raise ValueError('knowledge root differs from independent catalog/bootstrap admission')
            state['expectedRoot'] = a.expected_root
            previous = remote_head(dst)
            state.update(sourceCommit=head, destinationBefore=previous, inventory=inv)
            if previous:
                fetch(repo, dst, previous)
                r = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', previous, head], capture_output=True)
                if r.returncode != 0:
                    raise ValueError('destination diverged; perform an ordinary reviewed merge, then rerun with a new receipt')
            elif not a.create_destination:
                raise ValueError('destination absent; explicit --create-destination required')
            if a.action == 'verify' and previous != head:
                raise ValueError('source/destination commits differ')
            if a.action == 'sync' and previous != head:
                state.update(state='push_intent', pushAttempts=1)
                save()
                # One ordinary push. Destination races are handled by Git's fast-forward gate.
                r = subprocess.run(['git', '-C', str(repo), 'push', dst['repository'], head + ':refs/heads/' + dst['branch']], capture_output=True, timeout=90)
                state['pushExitCode'] = r.returncode
                state['state'] = 'push_returned' if r.returncode == 0 else 'push_rejected_or_unconfirmed'
                save()
            actual = remote_head(dst)
            state['destinationAfter'] = actual
            if actual != head:
                raise ValueError('exact destination not confirmed; read original receipt/ref, do not replay automatically')
            with tempfile.TemporaryDirectory(prefix='al-knowledge-readback-') as fresh:
                subprocess.run(['git', 'init', '--bare', '--quiet', fresh], check=True, capture_output=True)
                fetch(fresh, dst, head)
                if inventory(fresh, head, b) != inv:
                    raise ValueError('independent full byte readback differs')
            state.update(state='verified', exactCommitAndAllFilesVerified=True)
    except Exception as exc:
        state.update(errorType=type(exc).__name__, error=str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'operation interrupted; read original receipt and exact refs before another effect')
        if state['state'] == 'push_intent':
            state['state'] = 'outcome_unknown'
        save()
        print(json.dumps({'state': state['state'], 'pushAttempts': state['pushAttempts'], 'error': state['error']}))
        return 1
    save()
    print(json.dumps({k: state[k] for k in ['state', 'sourceCommit', 'destinationAfter', 'pushAttempts', 'exactCommitAndAllFilesVerified']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
