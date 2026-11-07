#!/usr/bin/env python3
"""Audit captured LLM exchanges and compare recovered bytes; no authority claims."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PATTERN = re.compile(r'^(\d{4,})\.(request\.json|upstream-request\.json|response|status\.json)$')
PARTS = frozenset(('request.json', 'upstream-request.json', 'response', 'status.json'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('capture directory missing or symlink')
    found = {}
    for path in root.iterdir():
        match = PATTERN.fullmatch(path.name)
        if not match:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('capture member is not a regular file')
        exchange, part = match.groups()
        found.setdefault(exchange, {})[part] = path
    return found


def audit(root, expected_count, recovered=None):
    if expected_count < 1:
        raise ValueError('expected exchange count must be positive')
    entries = inventory(root)
    expected = {f'{i:04d}' for i in range(1, expected_count + 1)}
    issues = []
    if set(entries) != expected:
        issues.append('exchange identities or count differ')
    recovered_entries = inventory(recovered) if recovered is not None else None
    if recovered_entries is not None and set(recovered_entries) != expected:
        issues.append('recovered exchange identities or count differ')
    rows = []
    for ident in sorted(expected):
        parts = entries.get(ident, {})
        missing = sorted(PARTS - set(parts))
        if missing:
            issues.append(f'{ident}: missing {", ".join(missing)}')
            continue
        try:
            request = json.loads(parts['request.json'].read_bytes())
            upstream = json.loads(parts['upstream-request.json'].read_bytes())
            status = json.loads(parts['status.json'].read_bytes())
            if not all(isinstance(x, dict) for x in (request, upstream, status)):
                raise ValueError('JSON payload is not an object')
            if status.get('exchangeId') != ident:
                raise ValueError('exchange identity mismatch')
            response_bytes = parts['response'].stat().st_size
            if status.get('responseBytes') != response_bytes:
                raise ValueError('response byte count differs')
        except (ValueError, UnicodeError, OSError) as error:
            issues.append(f'{ident}: invalid metadata ({type(error).__name__})')
            continue
        files = {part: {'bytes': parts[part].stat().st_size, 'sha256': sha(parts[part])} for part in sorted(PARTS)}
        if recovered_entries is not None:
            back = recovered_entries.get(ident, {})
            if set(back) != PARTS:
                issues.append(f'{ident}: recovered parts differ')
            else:
                for part in PARTS:
                    if back[part].stat().st_size != files[part]['bytes'] or sha(back[part]) != files[part]['sha256']:
                        issues.append(f'{ident}: recovered {part} differs')
        rows.append({'exchange': ident, 'httpStatus': status.get('status'), 'outcome': status.get('outcome'),
                     'upstreamEof': status.get('upstreamEof'), 'semanticComplete': status.get('semanticComplete'),
                     'files': files})
    return {'schema': 'agentlab.llm_capture_audit.v1', 'expectedCount': expected_count,
            'observedCount': len(entries), 'completeInventory': not issues, 'issues': issues, 'exchanges': rows,
            'recoveryCompared': recovered is not None, 'recoveryMatches': recovered is not None and not issues,
            'tablegitAuthorityVerified': False,
            'qualification': 'byte audit only; neither a live TableGit receipt nor formal evaluation admission',
            'storageLayout': 'not inferred'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gateway-dir', required=True, type=Path)
    p.add_argument('--expected-exchanges', required=True, type=int)
    p.add_argument('--recovered-gateway-dir', type=Path)
    p.add_argument('--require-recovery', action='store_true')
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        result = audit(a.gateway_dir, a.expected_exchanges, a.recovered_gateway_dir)
        if a.require_recovery and not result['recoveryMatches']:
            result['issues'].append('byte recovery required')
            result['completeInventory'] = False
        with a.output.open('x', encoding='utf-8') as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write('\n')
        return 0 if result['completeInventory'] else 1
    except (ValueError, OSError) as error:
        print(f'capture audit refused: {error}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
