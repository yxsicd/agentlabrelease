#!/usr/bin/env python3
"""Acquire and reconstruct retained rejection inputs before Action model budget."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prepare(args):
    script_root = Path(__file__).resolve().parent
    acquisition = module('acquisition', script_root / 'acquire-source-suite-review-input.py')
    isolation = module('isolation', script_root / 'validate-participant-runtime.py')
    envelope = json.loads(args.enrollment.read_bytes())
    required = {'schema', 'reviewRun', 'reviewArtifact', 'reviewMethodRevision',
                'reviewArtifactSha256', 'reviewFeedback', 'successorPolicy'}
    acquisition.require(set(envelope) == required and
                        envelope['schema'] == 'agentlab.source_reviewed_successor_enrollment.v1',
                        'Unsupported successor enrollment fields')
    root = args.output
    root.mkdir()
    acquired = root / 'acquired'
    acquisition.acquire(argparse.Namespace(repository=args.repository,
        run=str(envelope['reviewRun']), artifact=str(envelope['reviewArtifact']),
        source_revision=envelope['reviewMethodRevision'],
        artifact_sha256=envelope['reviewArtifactSha256'], output=acquired,
        artifact_kind='review-feedback', coordinator_request_id=None))
    retained = acquired / 'review-inputs'
    run = json.loads((acquired / 'source-run.json').read_bytes())
    enrollment = json.loads((retained / 'enrollment.json').read_bytes())
    if run['path'] == '.github/workflows/maintainer-source-suite-review.yml':
        original_root = '/home/runner/work/_temp/source-suite-review'
    else:
        original_root = '/home/runner/work/_temp/recipe-author/automatic-review'
    repair_limit = enrollment['reviewRepairLimit']
    acquisition.require(type(repair_limit) is int and repair_limit in (0, 1),
                        'Unsupported historical review repair budget')
    agent = retained / 'agent'
    coordinator = json.loads((agent / 'attempt-coordinator.json').read_bytes())
    acquisition.require(coordinator.get('completed') is True and
                        coordinator.get('selectedAttempt') in ('.', 'repair-attempt'),
                        'Historical review has no bounded selected completion')
    receipts = retained / 'runtime-receipts'
    checks = [('initial', receipts / 'initial' if repair_limit else receipts,
               original_root + '/agent')]
    if (agent / 'repair-attempt').exists():
        acquisition.require(repair_limit == 1, 'Historical repair exceeds enrollment')
        checks.append(('repair', receipts / 'repair-1', original_root + '/agent/repair-attempt'))
    for label, receipt_root, capture_root in checks:
        verdict = isolation.validate_runtime_receipts(retained / 'runtime-inputs/config.json',
            receipt_root, capture_root + '/workspace', capture_root + '/participant-state',
            ['source-suite-review'], recorded_paths=True)
        with (root / (label + '-retained-isolation.json')).open('x') as stream:
            json.dump(verdict, stream, sort_keys=True)
    selected = agent if coordinator['selectedAttempt'] == '.' else agent / 'repair-attempt'
    for key, filename in [('reviewFeedback', 'review-feedback.json'), ('successorPolicy', 'policy.json')]:
        with (root / filename).open('x') as stream:
            json.dump(envelope[key], stream, separators=(',', ':'))
    inputs = dict(source=str(retained / 'source/observations'),
                  quality_rubric=str(retained / 'rubric.json'),
                  participant_evidence=str(selected / 'evidence'),
                  review_response=str(selected / 'response.json'),
                  review_feedback=str(root / 'review-feedback.json'),
                  successor_policy=str(root / 'policy.json'), source_git_checkout=str(args.source_git_checkout))
    command = [str(args.gate.resolve()), '--prepare-source-reviewed-successor']
    for key, value in inputs.items():
        command += ['--' + key.replace('_', '-'), value]
    command += ['--output', str(root / 'native-preview.json')]
    subprocess.run(command, check=True, timeout=60)
    packet = json.loads((root / 'native-preview.json').read_bytes())
    original_request = retained / 'source/observations/source-stage/request.json'
    if 'sourceRecipeTarget' in json.loads(packet['authorRequestOriginal']):
        restored = root / 'restored-parent-request.json'
        subprocess.run([str(args.gate.resolve()), '--restore-source-recipe-author-target',
            '--author-request', str(args.request), '--parent-author-request', str(original_request),
            '--output', str(restored)], check=True, timeout=60)
        restored.replace(args.request)
    acquisition.require(args.request.read_bytes() == packet['authorRequestOriginal'].encode(),
                        'Current Action request differs from original successor enrollment')
    # The bridge performs mandatory live target validation before durable claims
    # and model dispatch. Native preparation here is an earlier read-only gate.
    with (root / 'bridge-inputs.json').open('x') as stream:
        json.dump(inputs, stream, sort_keys=True)
    (root / 'local-claims').mkdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('enrollment', 'output', 'request', 'gate', 'source-git-checkout'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repository', required=True)
    prepare(parser.parse_args())


if __name__ == '__main__':
    main()
