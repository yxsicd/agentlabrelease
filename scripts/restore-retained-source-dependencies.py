#!/usr/bin/env python3
"""Acquire declared Linux dependencies and original producer knowledge bytes."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import urllib.request
from importlib.util import module_from_spec, spec_from_file_location


def member(url, name, output, limit):
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(64*1024*1024+1)
    if len(data) > 64*1024*1024:
        raise ValueError('Dependency archive exceeds acquisition budget')
    with output.with_suffix('.archive').open('xb') as stream:
        stream.write(data)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        info = archive.getmember(name)
        if not info.isfile() or info.size > limit:
            raise ValueError('Dependency member exceeds regular-file budget')
        with output.open('xb') as stream:
            stream.write(archive.extractfile(info).read())


def main():
    p = argparse.ArgumentParser()
    for name in ('request', 'output', 'producer-checkout'):
        p.add_argument('--'+name, type=Path, required=True)
    for name in ('producer-revision', 'repository', 'node-version', 'typescript-version'):
        p.add_argument('--'+name, required=True)
    args = p.parse_args()
    if not all(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', v) for v in (args.node_version, args.typescript_version)):
        raise ValueError('Explicit dependency release versions required')
    if not re.fullmatch('[0-9a-f]{40}', args.producer_revision) or not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        raise ValueError('Invalid producer identity')
    checkout = args.producer_checkout.resolve(strict=True)
    commit = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', args.producer_revision+'^{commit}'], timeout=30).decode().strip()
    if commit != args.producer_revision:
        raise ValueError('Knowledge producer commit differs')
    request = json.loads(args.request.read_bytes())
    repo = args.repository.split('/')[1]
    prefix = f'/home/runner/work/{repo}/{repo}/'
    path = request['knowledgeDirectory']
    if not path.startswith(prefix):
        raise ValueError('Knowledge path is outside original producer workspace')
    relative = path[len(prefix):]
    if str(PurePosixPath(relative)) != relative or any(v in ('', '.', '..') for v in relative.split('/')):
        raise ValueError('Unsafe producer knowledge path')
    args.output.mkdir()
    node = args.output/'host-node'
    compiler = args.output/'typescript.js'
    member(f'https://nodejs.org/dist/v{args.node_version}/node-v{args.node_version}-linux-x64.tar.xz',
           f'node-v{args.node_version}-linux-x64/bin/node', node, 128*1024*1024)
    node.chmod(0o755)
    member(f'https://registry.npmjs.org/typescript/-/typescript-{args.typescript_version}.tgz',
           'package/lib/typescript.js', compiler, 16*1024*1024)
    spec = spec_from_file_location('replay', Path(__file__).with_name('replay-retained-source-completion.py'))
    module = module_from_spec(spec); spec.loader.exec_module(module)
    module.bound_file(node, request['policy']['programSha256'])
    dependencies = request['policy']['methodDependencies']
    if len(dependencies) != 1:
        raise ValueError('One original compiler dependency required')
    module.bound_file(compiler, dependencies[0]['sha256'])
    raw = subprocess.check_output(['git', '-C', str(checkout), 'archive', args.producer_revision, '--', relative], timeout=60)
    if len(raw) > 128*1024*1024:
        raise ValueError('Knowledge archive exceeds budget')
    knowledge = args.output/'knowledge'; knowledge.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        entries = archive.getmembers()
        if len(entries) > 20000 or sum(e.size for e in entries) > 128*1024*1024:
            raise ValueError('Knowledge inventory exceeds budget')
        seen = set()
        for entry in entries:
            if entry.isdir():
                continue
            if not entry.isfile() or not entry.name.startswith(relative+'/'):
                raise ValueError('Unsafe knowledge member')
            name = entry.name[len(relative)+1:]
            if any(v in ('', '.', '..') for v in name.split('/')) or name in seen:
                raise ValueError('Unsafe or duplicate knowledge path')
            seen.add(name)
            target = knowledge/name; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream: stream.write(archive.extractfile(entry).read())
    receipt = dict(schema='agentlab.retained_dependency_restoration.v1',
                   sourceMethodRevision=args.producer_revision,
                   knowledgeRelativePath=relative,
                   requestSha256=hashlib.sha256(args.request.read_bytes()).hexdigest(),
                   hostNodeVersion=args.node_version, typescriptVersion=args.typescript_version,
                   hostNodeSha256=request['policy']['programSha256'],
                   compilerSha256=dependencies[0]['sha256'],
                   nodeArchiveSha256=hashlib.sha256(node.with_suffix('.archive').read_bytes()).hexdigest(),
                   compilerArchiveSha256=hashlib.sha256(compiler.with_suffix('.archive').read_bytes()).hexdigest(),
                   dependencyBytesMatchedOriginal=True, qualified=False, authorityWritePerformed=False)
    with (args.output/'receipt.json').open('x') as stream:
        json.dump(receipt, stream)
    print(json.dumps(dict(hostNode=str(node), compiler=str(compiler), knowledge=str(knowledge), qualified=False)))


if __name__ == '__main__':
    main()
