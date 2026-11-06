#!/usr/bin/env python3
"""Inspect one retained UI layout; execution and verdict authority stay external."""
import argparse
import hashlib
import json
from pathlib import Path


def inspect(raw, bundle, node_id, text):
    if not all(isinstance(s, str) and s for s in (bundle, node_id, text)):
        raise ValueError('bundle, node id and text must be nonempty strings')
    layout = json.loads(raw)
    matches = []

    def visit(value, owner=None):
        if isinstance(value, dict):
            attrs = value.get('attributes')
            if isinstance(attrs, dict):
                declared = attrs.get('bundleName')
                if 'bundleName' in attrs:
                    # An explicit but invalid owner must not inherit authority.
                    owner = declared if isinstance(declared, str) and declared else None
                if owner == bundle and attrs.get('id') == node_id and attrs.get('text') == text:
                    matches.append(True)
            for child in value.values():
                visit(child, owner)
        elif isinstance(value, list):
            for child in value:
                visit(child, owner)

    visit(layout)
    return {'schema': 'agentlab.harmony_layout_owner_observation.v1',
            'layoutSha256': hashlib.sha256(raw).hexdigest(),
            'bundle': bundle, 'nodeId': node_id, 'text': text,
            'matched': bool(matches), 'matchCount': len(matches)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', required=True, type=Path)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--text', required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.layout.read_bytes(), args.bundle, args.id, args.text), ensure_ascii=False))


if __name__ == '__main__':
    main()
