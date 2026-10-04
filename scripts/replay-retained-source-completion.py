#!/usr/bin/env python3
"""Requalify retained bytes, stage in frozen paths, then run maintained workers.

Dependency acquisition is separate: every supplied dependency must match the
unchanged author request. No author invocation or knowledge write occurs here.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys


def destination(value):
    if not isinstance(value, str):
        raise ValueError('Frozen mount destination must be a string')
    path = PurePosixPath(value)
    if (not path.is_absolute() or str(path) != value or len(path.parts) < 3
            or '..' in path.parts
            or any(c in value for c in ':,\n\r\x00')
            or path.parts[1] in ('proc', 'sys', 'dev', 'etc', 'tmp', 'inputs', 'output', 'validator')):
        raise ValueError('Unsafe frozen mount destination')
    return value


def bound_file(path, expected):
    path = path.resolve(strict=True)
    if not path.is_file() or not isinstance(expected, str) or len(expected) != 64:
        raise ValueError('Invalid original dependency identity')
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
        actual = digest.hexdigest()
    if actual != expected:
        raise ValueError('Recovered dependency differs from original bytes')
    return path


def replay(args):
    inputs = args.inputs.resolve(strict=True)
    gate = args.gate.resolve(strict=True)
    source = args.source_checkout.resolve(strict=True)
    knowledge = args.knowledge.resolve(strict=True)
    request = json.loads((inputs/'request.json').read_bytes())
    policy = request['policy']
    dependencies = policy['methodDependencies']
    if len(dependencies) != 1:
        raise ValueError('This replay adapter requires exactly one compiler dependency')
    node = bound_file(args.host_node, policy['programSha256'])
    compiler = bound_file(args.compiler, dependencies[0]['sha256'])
    mounts = [(source, destination(request['sourceWorktree'])),
              (knowledge, destination(request['knowledgeDirectory'])),
              (node, destination(policy['program'])),
              (compiler, destination(dependencies[0]['path']))]
    for index, (_, target) in enumerate(mounts):
        for _, other in mounts[:index]:
            if target == other or target.startswith(other+'/') or other.startswith(target+'/'):
                raise ValueError('Overlapping original context mounts')
    for image in (args.stage_image, args.worker_image):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('Exact local image identity required')
        inspected = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], timeout=30))
        if len(inspected) != 1 or inspected[0]['Id'] != image:
            raise ValueError('Local image identity differs')
    output = args.output.resolve()
    if any(c in str(host) for host in [output, gate, inputs, *(host for host, _ in mounts)]
           for c in ':,\n\r\x00'):
        raise ValueError('Unsafe context mount source')
    if any(output == original or original in output.parents or output in original.parents
           for original in (inputs, source, knowledge)):
        raise ValueError('Replay output must be separate from original input/source')
    output.mkdir()  # Exclusive attempt ownership; never resume an uncertain run.
    intent = dict(schema='agentlab.retained_source_completion_replay.v1',
                  requestSha256=hashlib.sha256((inputs/'request.json').read_bytes()).hexdigest(),
                  newAuthorCalls=0, maximumRepairs=0, qualified=False,
                  automaticPromotion=False, authorityWritePerformed=False,
                  stageImage=args.stage_image, workerImage=args.worker_image,
                  currentValidatorSha256=hashlib.sha256(gate.read_bytes()).hexdigest())
    with (output/'replay-intent.json').open('x') as stream:
        json.dump(intent, stream)
    subprocess.run([str(gate), '--verify-unguided-source-recipe-completion',
                    '--participant-evidence', str(inputs/'agent/evidence'),
                    '--author-request', str(inputs/'request.json'),
                    '--proposal', str(inputs/'agent/proposal.json'),
                    '--output', str(output/'native-completion.json')], check=True, timeout=180)
    # The consumer's Git may need objects omitted by a sparse blob:none fetch
    # (for example tracked ignore files). Acquire that read-only query closure
    # before the network-disabled stage, without materializing extra source paths.
    metadata = source/'.git'
    repository = request['source']['repository']
    if (not metadata.is_dir() or metadata.is_symlink()
            or not repository.startswith('https://') or '@' in repository):
        raise ValueError('Owned HTTPS source checkout with regular Git metadata required')
    for query, expected in [(['rev-parse', 'HEAD'], request['source']['revision']),
                            (['remote', 'get-url', 'origin'], repository)]:
        actual = subprocess.check_output(['git', '-C', str(source), *query], timeout=30).decode().strip()
        if actual != expected:
            raise ValueError('Source identity differs before Git object acquisition')
    acquisition = ['docker', 'run', '--rm', '--read-only', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--pids-limit', '64',
                   '--memory', '512m', '--cpus', '1', '--user', f'{os.getuid()}:{os.getgid()}',
                   '--tmpfs', '/tmp:rw,size=16m', '-e', 'GIT_OPTIONAL_LOCKS=0',
                   '-e', 'GIT_TERMINAL_PROMPT=0', '-e', 'GIT_CONFIG_COUNT=1',
                   '-e', 'GIT_CONFIG_KEY_0=safe.directory',
                   '-e', 'GIT_CONFIG_VALUE_0='+request['sourceWorktree'],
                   '-v', f'{source}:{request["sourceWorktree"]}:ro',
                   '-v', f'{metadata}:{request["sourceWorktree"]}/.git:rw',
                   args.stage_image, 'git', '-C', request['sourceWorktree'],
                   'status', '--porcelain=v1', '--untracked-files=all']
    with (output/'git-object-acquisition-command.json').open('x') as stream:
        json.dump(dict(command=acquisition, network='dependency-acquisition-only',
                       generatedCodeExecuted=False, qualified=False), stream)
    with (output/'git-object-acquisition-stdout.log').open('xb') as out, (output/'git-object-acquisition-stderr.log').open('xb') as err:
        subprocess.run(acquisition, stdout=out, stderr=err, check=True, timeout=90)
    if (output/'git-object-acquisition-stdout.log').read_bytes().strip():
        raise ValueError('Source checkout is dirty; no stage or model dispatch')
    for index, item in enumerate(request.get('readOnlySourceContext', {}).get('packet', {}).get('selectedFiles', [])):
        path = item['path']
        if (not isinstance(path, str) or PurePosixPath(path).is_absolute()
                or str(PurePosixPath(path)) != path or '..' in PurePosixPath(path).parts):
            raise ValueError('Unsafe original supplementary context path')
        command = acquisition[:-3] + ['show', request['source']['revision']+':'+path]
        with (output/f'git-context-acquisition-{index}-stdout.log').open('xb') as out, (output/f'git-context-acquisition-{index}-stderr.log').open('xb') as err:
            subprocess.run(command, stdout=out, stderr=err, check=True, timeout=90)
    shutil.copyfile(inputs/'request.json', output/'request.json')
    (output/'agent').mkdir()
    command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--pids-limit', '64', '--memory', '512m', '--cpus', '1',
               '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,size=16m',
               '-e', 'GIT_CONFIG_COUNT=1', '-e', 'GIT_CONFIG_KEY_0=safe.directory',
               '-e', 'GIT_CONFIG_VALUE_0='+request['sourceWorktree']]
    for host, target in mounts + [(gate, '/validator'), (inputs, '/inputs')]:
        if any(c in str(host) for c in ':,\n\r\x00'):
            raise ValueError('Unsafe context source path')
        command += ['-v', f'{host}:{target}:ro']
    command += ['-v', f'{output}:/output:rw', args.stage_image, '/validator',
                '--stage-source-recipe-proposal', '--author-request', '/inputs/request.json',
                '--proposal', '/inputs/agent/proposal.json', '--design', '/inputs/frozen-design.json',
                '--diagnostic-repair', '/inputs/diagnostic-repair.json',
                '--output', '/output/agent/proposal-stage']
    subprocess.run(command, check=True, timeout=180)
    scripts = Path(__file__).resolve().parent
    for script in ('run-source-recipe-diagnostic-loop.py', 'run-source-recipe-control-suite.py'):
        command = [sys.executable, str(scripts/script), '--root', str(output),
                   '--gate', str(gate), '--compiler', str(compiler), '--image-id', args.worker_image]
        if script == 'run-source-recipe-diagnostic-loop.py':
            command += ['--maximum-repairs', '0']
        subprocess.run(command, check=True, timeout=900)
    intent.update(completed=True, observations=str(output/'observation-export'),
                  independentReviewPerformed=False)
    with (output/'replay-result.json').open('x') as stream:
        json.dump(intent, stream)
    return intent


def main():
    parser = argparse.ArgumentParser()
    for name in ('inputs', 'gate', 'source-checkout', 'knowledge', 'host-node', 'compiler', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('stage-image', 'worker-image'):
        parser.add_argument('--'+name, required=True)
    print(json.dumps(replay(parser.parse_args())))


if __name__ == '__main__':
    main()
