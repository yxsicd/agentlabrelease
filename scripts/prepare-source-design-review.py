#!/usr/bin/env python3
"""Transport a retained design to the existing native review gate; never approve it."""
import argparse
import subprocess
from pathlib import Path


def prepare(gate, request, parent, feedback, output):
    for name in ('revision-request.json', 'design-review-feedback.json', 'diagnostic-repair.json'):
        if (parent / 'agent' / name).exists():
            raise ValueError('Only an original construction may receive one reviewed child')
    if request.read_bytes() != (parent / 'request.json').read_bytes():
        raise ValueError('Design review requires unchanged exact original author request')
    design = (parent / 'agent/design.json').read_bytes()
    if len(design) > 64 * 1024 or feedback.stat().st_size > 16 * 1024:
        raise ValueError('Design review input budget')
    if any((output / name).exists() for name in ('review-parent-design.json', 'review-parent-admission.json')):
        raise FileExistsError('Design review already prepared')
    subprocess.run([str(gate), '--validate-source-design-review',
        '--author-request', str(request), '--design', str(parent / 'agent/design.json'),
        '--review-feedback', str(feedback),
        '--output', str(output / 'review-parent-admission.json')], check=True, timeout=60)
    if (parent / 'agent/design.json').read_bytes() != design:
        raise ValueError('Parent design changed during native review validation')
    with (output / 'review-parent-design.json').open('xb') as stream:
        stream.write(design)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gate', 'request', 'parent', 'feedback', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    prepare(args.gate, args.request, args.parent, args.feedback, args.output)


if __name__ == '__main__':
    main()
