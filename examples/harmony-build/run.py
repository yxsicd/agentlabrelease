#!/usr/bin/env python3
"""Compile a public Harmony seed and two edits using installed release packages."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--agent-bin', type=Path)
    parser.add_argument('--gateway-url', default='https://llm-m4dd.de.yxsbase.win')
    parser.add_argument('--model', default='glm-5.3-flash')
    parser.add_argument('--provider-route', default='glm')
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    project = root / 'workspace/hello'
    shutil.copytree(Path(__file__).parent / 'seed', project)
    evidence = root / 'evidence'
    evidence.mkdir()
    lock = json.loads((args.install_root / 'downloads/environment-lock.json').read_text())
    image = lock['images'][0]['reference']
    sdk = next(c for c in lock['components'] if c['slot'] == 'harmony-cli')
    kit = next(c for c in lock['components'] if c['slot'] == 'harmony-build-kit')
    summary = {'schema': 'agentlab.harmony_build_demo.v1', 'ok': False,
               'scope': 'Real offline unsigned HAP compilation; no device or formal Harness qualification',
               'checks': {}, 'components': {'image': image, 'sdk': sdk, 'buildKit': kit},
               'builds': []}
    (evidence / 'environment-lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    base = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network=none',
            '--mount', f'type=volume,src={sdk["volume"]},dst=/toolchains/harmony,readonly',
            '--mount', f'type=volume,src={kit["volume"]},dst=/toolchains/harmony-build-kit,readonly',
            '--mount', f'type=bind,src={root / "workspace"},dst=/workspace',
            '--mount', f'type=bind,src={evidence},dst=/evidence',
            '--env', 'HARMONY_TOOLCHAIN_ROOT=/toolchains/harmony',
            '--env', 'HARMONY_BUILD_CACHE=/runtime/toolchain-cache/demo',
            '--entrypoint', '/usr/bin/python3', image,
            '/toolchains/harmony-build-kit/bin/harmony']

    def call(label, action, expect_success=True):
        command = base + [action, '--project', '/workspace/hello', '--offline']
        (evidence / f'{label}-command.json').write_text(json.dumps(command, indent=2) + '\n')
        start = time.monotonic()
        result = subprocess.run(command, capture_output=True, timeout=240)
        (evidence / f'{label}-stdout.log').write_bytes(result.stdout)
        (evidence / f'{label}-stderr.log').write_bytes(result.stderr)
        (evidence / f'{label}-exit.json').write_text(json.dumps({'exitCode': result.returncode,
                                                'wallSeconds': time.monotonic() - start}) + '\n')
        if (project / '.native-build').exists():
            shutil.copytree(project / '.native-build', evidence / label)
        if expect_success != (result.returncode == 0):
            raise RuntimeError(f'{label}: unexpected exit {result.returncode}; see retained logs')
        print(f'{label}: exit {result.returncode}', flush=True)
        return result

    def build(label, marker):
        result = call(label, 'build')
        report = json.loads(result.stdout)
        if report['status'] != 'succeeded' or not report['artifacts']:
            raise RuntimeError('No successful compiler artifact')
        item = report['artifacts'][0]
        hap = project / item['path']
        raw = hap.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item['sha256'] or len(raw) != item['bytes']:
            raise RuntimeError('Compiler receipt differs from actual HAP')
        with zipfile.ZipFile(hap) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Corrupt HAP')
            module = json.loads(archive.read('module.json'))
            bytecode = b''.join(archive.read(n) for n in archive.namelist() if n.endswith('.abc'))
            if marker.encode() not in bytecode or module['module']['name'] != 'entry':
                raise RuntimeError('Compiled bytecode does not contain this iteration marker')
        shutil.copy2(hap, evidence / f'{label}.hap')
        summary['builds'].append({'label': label, 'marker': marker, **item})
        summary['checks'][label] = True
        return digest

    source = project / 'entry/src/main/ets/pages/Index.ets'
    participant = None
    try:
        if args.agent_bin:
            import importlib.util
            spec = importlib.util.spec_from_file_location('live_participant',
                Path(__file__).parent.parent / 'real-code-agent/participant.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            participant = module.Participant(evidence, root / 'participant-state',
                                             args.agent_bin, args.gateway_url, args.model, args.provider_route)
            summary['participant'] = {'implementation': 'pi', 'model': args.model}
        call('doctor', 'doctor')
        summary['checks']['publishedToolchainReady'] = True
        original = source.read_text()
        hashes = [build('seed-build', 'Native Build Verified')]
        for number, marker in enumerate(('Public Iteration One', 'Public Iteration Two'), 1):
            if participant:
                participant.turn(f'agent-iteration-{number}', project, marker)
            else:
                source.write_text(original.replace('Native Build Verified', marker))
            (evidence / f'iteration-{number}.ets').write_text(source.read_text())
            hashes.append(build(f'iteration-{number}-build', marker))
        summary['checks']['eachEditChangesCompiledHap'] = len(set(hashes)) == 3
        if not summary['checks']['eachEditChangesCompiledHap']:
            raise RuntimeError('Changed source reused an old compiled HAP')
        # A stale HAP must not hide an invalid-source compiler failure.
        source.write_text(original + '\nTHIS IS INVALID ARKTS !!!\n')
        call('invalid-source', 'build', expect_success=False)
        failed = json.loads((project / '.native-build/result.json').read_text())
        if failed['status'] != 'failed' or failed['artifacts']:
            raise RuntimeError('Invalid source reported stale artifacts as success')
        summary['checks']['invalidSourceRejected'] = True
        if participant:
            participant.turn('agent-repair', project, 'Public Iteration Two', repair=True)
            summary['checks']['realAgentMultiTurnAndRepair'] = True
        else:
            source.write_text(original.replace('Native Build Verified', 'Public Iteration Two'))
        build('recovered-build', 'Public Iteration Two')
        summary['ok'] = True
    except Exception as error:
        summary['error'] = str(error)
        raise
    finally:
        if participant:
            summary['gatewayRequestCount'] = participant.requests
            participant.close()
        (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
