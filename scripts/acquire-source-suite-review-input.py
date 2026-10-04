#!/usr/bin/env python3
"""Acquire one exact original Action artifact; never run downloaded content."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def extract_observations(archive, output, feedback=False):
    compressed_limit = (64 if feedback else 50) * 1024 * 1024
    require(archive.stat().st_size <= compressed_limit, 'Artifact exceeds compressed budget')
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        expanded_limit = (1024 if feedback else 256) * 1024 * 1024
        require(len(entries) <= 20000 and sum(e.file_size for e in entries) <= expanded_limit,
                'Artifact exceeds expanded budget')
        seen = set()
        selected = []
        for entry in entries:
            path = PurePosixPath(entry.filename)
            require(not path.is_absolute() and '\\' not in entry.filename
                    and not any(p in ('', '.', '..') for p in entry.filename.rstrip('/').split('/'))
                    and '\x00' not in entry.filename and entry.filename not in seen,
                    'Unsafe or duplicate artifact member')
            seen.add(entry.filename)
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode) and (stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR))
                    and not (entry.flag_bits & 1), 'Nonregular or encrypted artifact member')
            if feedback and not entry.is_dir():
                exact = {'enrollment.json', 'rubric.json', 'runtime-validation.json', 'runtime-repair-validation.json',
                         'agent/response.json', 'agent/validation.json', 'agent/transport-receipt.json', 'agent/attempt-coordinator.json'}
                prefix = ('source/observations/', 'feedback/', 'agent/evidence/',
                          'agent/repair-attempt/evidence/', 'runtime-inputs/', 'runtime-receipts/')
                exact.update({'agent/repair-attempt/response.json', 'agent/repair-attempt/validation.json',
                              'agent/repair-attempt/transport-receipt.json'})
                # The complete Pi event stream stays in the byte-bound original
                # ZIP. Native reception consumes wire/final/lifecycle, not events.
                excluded = {'agent/evidence/source-suite-review-events.jsonl',
                            'agent/repair-attempt/evidence/source-suite-review-events.jsonl'}
                if entry.filename not in excluded and (entry.filename in exact or entry.filename.startswith(prefix)):
                    require(entry.file_size <= 4 * 1024 * 1024,
                            'Selected feedback file exceeds native read budget')
                    selected.append((entry, Path(*path.parts)))
            elif not feedback and path.parts[0] == 'observation-export' and not entry.is_dir():
                require(len(path.parts) > 1, 'Invalid observation member')
                selected.append((entry, Path(*path.parts[1:])))
        if feedback:
            names = {entry.filename for entry, _ in selected}
            required = {'enrollment.json', 'rubric.json', 'agent/response.json',
                        'agent/evidence/review-intent.json',
                        'agent/evidence/source-suite-review-prompt.txt',
                        'agent/evidence/source-suite-review-lifecycle.json',
                        'agent/evidence/source-suite-review-final-assistant-message.json',
                        'source/observations/export.json', 'source/observations/source-suite-inputs.json'}
            require(required <= names, 'Original review reception inputs incomplete')
            require(any(name.startswith('agent/evidence/gateway/') for name in names),
                    'Original review wire capture absent')
            require(sum(entry.file_size for entry, _ in selected) <= 64 * 1024 * 1024,
                    'Selected feedback exceeds reception budget')
        else:
            require(selected, 'Original native observation export absent; do not rerun source workers')
        output.mkdir()
        for entry, path in selected:
            target = output / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(bundle.read(entry))


def acquire(args):
    feedback = getattr(args, 'artifact_kind', 'source') == 'review-feedback'
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository), 'Invalid repository')
    require(all(re.fullmatch(r'[1-9][0-9]{0,19}', value) for value in (args.run, args.artifact)), 'Invalid exact IDs')
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_revision), 'Invalid source method commit')
    require(re.fullmatch(r'[0-9a-f]{64}', args.artifact_sha256), 'Invalid artifact digest')
    args.output.mkdir()
    terminal = dict(schema='agentlab.source_suite_review_acquisition.v1', completed=False,
                    artifactKind='review-feedback' if feedback else 'source',
                    repository=args.repository, runId=args.run, artifactId=args.artifact,
                    expectedMethodRevision=args.source_revision, expectedArtifactSha256=args.artifact_sha256,
                    automaticPromotion=False, qualified=False)
    try:
        def metadata(endpoint, name):
            raw = subprocess.check_output(['gh', 'api', endpoint], timeout=60)
            with (args.output / name).open('xb') as stream:
                stream.write(raw)
            return json.loads(raw)
        run = metadata(f'repos/{args.repository}/actions/runs/{args.run}', 'source-run.json')
        artifact = metadata(f'repos/{args.repository}/actions/artifacts/{args.artifact}', 'source-artifact.json')
        require(str(run['id']) == args.run and run['status'] == 'completed'
                and run['event'] == 'workflow_dispatch'
                and run['name'] == ('Maintainer independent source suite review' if feedback else 'Maintainer source recipe construction')
                and run['path'] == ('.github/workflows/maintainer-source-suite-review.yml' if feedback else '.github/workflows/maintainer-source-recipe-author.yml')
                and run['head_branch'] == 'main'
                and run['head_sha'] == args.source_revision, 'Source Action identity differs or still running')
        require(str(artifact['id']) == args.artifact and not artifact['expired']
                and str(artifact['workflow_run']['id']) == args.run
                and artifact['workflow_run']['head_sha'] == args.source_revision
                and artifact['name'] == ('independent-source-suite-review-' if feedback else 'unreviewed-source-recipe-') + args.run
                and 0 < artifact['size_in_bytes'] <= (64 if feedback else 50) * 1024 * 1024,
                'Source artifact identity differs')
        if artifact.get('digest') is not None:
            require(artifact['digest'] == 'sha256:' + args.artifact_sha256,
                    'GitHub artifact digest differs from enrolled identity')
        archive = args.output / 'original-artifact.zip'
        with archive.open('xb') as stream:
            subprocess.run(['gh', 'api', f'repos/{args.repository}/actions/artifacts/{args.artifact}/zip'],
                           stdout=stream, check=True, timeout=120)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        require(digest == args.artifact_sha256, 'Original ZIP digest differs')
        extract_observations(archive, args.output / ('review-inputs' if feedback else 'observations'), feedback)
        terminal.update(completed=True, artifactSha256=digest, originalBytes=True,
                        sourceProducerAuthenticated=False, reviewAccepted=False,
                        nativeReceptionVerified=False, authorityWritePerformed=False)
        return terminal
    except Exception as error:
        terminal.update(errorType=type(error).__name__, error=str(error))
        raise
    finally:
        with (args.output / 'acquisition-receipt.json').open('x') as stream:
            json.dump(terminal, stream, indent=2)
            stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    for name in ('repository', 'run', 'artifact', 'source-revision', 'artifact-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--artifact-kind', choices=['source', 'review-feedback'], default='source')
    print(json.dumps(acquire(parser.parse_args())))


if __name__ == '__main__':
    main()
