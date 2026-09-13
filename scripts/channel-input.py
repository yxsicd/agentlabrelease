#!/usr/bin/env python3
"""Prepare demo inputs from the selected composition, validating a frozen plan if present."""
import argparse
import importlib.util
import json
from pathlib import Path


def load(source):
    publication = json.loads((source/'publication.json').read_text())
    raw = (source/'environment-lock.json').read_bytes()
    lock = json.loads(raw)
    path = source/'plan.json'
    if path.exists():
        spec = importlib.util.spec_from_file_location('channel_plan', Path(__file__).with_name('channel-plan.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        frozen = json.loads(path.read_text())
        if module.plan(frozen['targetChannel'], publication, lock, raw) != frozen:
            raise ValueError('composition differs from frozen plan')
    (source/'session-sdk.json').write_text(json.dumps(publication['sessionSdk'], indent=2)+'\n')
    return publication, lock

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    publication, _ = load(args.source)
    with args.output.open('a') as stream:
        stream.write('channel='+publication['tag']+'\n')
