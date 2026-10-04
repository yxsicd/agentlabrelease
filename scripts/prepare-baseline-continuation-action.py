#!/usr/bin/env python3
"""Acquire an exact retained baseline failure and prepare native continuation inputs.

This does not run a participant, create a claim, or grant semantic acceptance.
"""
import argparse
import json
from pathlib import Path
import subprocess

from importlib.util import module_from_spec, spec_from_file_location


def prepare(args):
    spec = spec_from_file_location('acquisition', Path(__file__).with_name('acquire-source-suite-review-input.py'))
    acquisition = module_from_spec(spec)
    spec.loader.exec_module(acquisition)
    raw = args.enrollment.read_bytes()
    acquisition.require(len(raw) <= 16384, 'Action continuation enrollment exceeds dispatch budget')
    envelope = json.loads(raw)
    required = {'schema', 'parentRun', 'parentArtifact', 'parentMethodRevision',
                'parentArchiveSha256', 'continuationEnrollment'}
    acquisition.require(set(envelope) == required and
        envelope['schema'] == 'agentlab.baseline_continuation_action_enrollment.v1',
        'Unsupported baseline Action enrollment')
    root = args.output
    root.mkdir()
    acquired = root / 'acquired'
    acquisition.acquire(argparse.Namespace(repository=args.repository,
        run=str(envelope['parentRun']), artifact=str(envelope['parentArtifact']),
        source_revision=envelope['parentMethodRevision'],
        artifact_sha256=envelope['parentArchiveSha256'], output=acquired,
        artifact_kind='baseline', coordinator_request_id=None))
    retained = acquired / 'baseline-inputs'
    stage = retained / 'agent/proposal-stage'
    if 'sourceRecipeTarget' in json.loads((stage / 'request.json').read_bytes()):
        restored = root / 'restored-parent-request.json'
        subprocess.run([str(args.gate.resolve(strict=True)), '--restore-source-recipe-author-target',
            '--author-request', str(args.request), '--parent-author-request', str(stage / 'request.json'),
            '--output', str(restored)], check=True, timeout=60)
        restored.replace(args.request)
    acquisition.require(args.request.read_bytes() == (stage / 'request.json').read_bytes(),
                        'Current Action request differs from original failed baseline')
    policy = root / 'continuation-enrollment.json'
    with policy.open('x') as stream:
        json.dump(envelope['continuationEnrollment'], stream, separators=(',', ':'))
    diagnostic = retained / 'baseline-diagnostic'
    captures = list(diagnostic.glob('contained-input-*'))
    acquisition.require(len(captures) == 1, 'Exactly one original capture is required')
    repair = root / 'diagnostic-repair.json'
    subprocess.run([str(args.gate.resolve(strict=True)), '--prepare-source-recipe-diagnostic-continuation',
        '--stage', str(stage), '--diagnostic-inputs', str(diagnostic),
        '--worker-capture', str(captures[0]), '--continuation-enrollment', str(policy),
        '--output', str(repair)], check=True, timeout=60)
    inputs = dict(diagnostic_repair=str(repair), successor_request=str(retained / 'successor-request.json'),
        review_enrollment=str(retained / 'successor-enrollment.json'),
        parent_archive=str(acquired / 'original-artifact.zip'),
        parent_run=str(envelope['parentRun']), parent_artifact=str(envelope['parentArtifact']),
        parent_method_revision=envelope['parentMethodRevision'],
        parent_archive_sha256=envelope['parentArchiveSha256'])
    with (root / 'bridge-inputs.json').open('x') as stream:
        json.dump(inputs, stream, sort_keys=True)
    (root / 'local-claims').mkdir()
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('enrollment', 'output', 'request', 'gate'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repository', required=True)
    print(json.dumps(prepare(parser.parse_args())))


if __name__ == '__main__':
    main()
