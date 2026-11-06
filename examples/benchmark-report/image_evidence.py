#!/usr/bin/env python3
"""Link captured view_image calls to later image-bearing requests; never expose image data."""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path


class EvidenceError(ValueError):
    pass


def _images(value):
    if not isinstance(value, list):
        return []
    result = []
    for part in value:
        if not isinstance(part, dict) or part.get('type') != 'input_image':
            continue
        url = part.get('image_url')
        if not isinstance(url, str) or not url.startswith('data:') or ',' not in url:
            result.append({'identity': 'unavailable'})
            continue
        header, data = url.split(',', 1)
        if not header.lower().endswith(';base64') or len(data) > 180_000_000:
            result.append({'identity': 'unavailable'})
            continue
        try:
            raw = base64.b64decode(data, validate=True)
        except ValueError:
            result.append({'identity': 'unavailable'})
            continue
        result.append({'identity': 'sha256', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    return result


def _outputs(request):
    result = {}
    items = request.get('input', []) if isinstance(request, dict) else []
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict) or item.get('type') != 'function_call_output':
            continue
        call_id = item.get('call_id')
        if not isinstance(call_id, str) or not call_id:
            continue
        imgs = _images(item.get('output'))
        if imgs:
            if call_id in result and result[call_id] != imgs:
                raise EvidenceError('conflicting image outputs for same call')
            result[call_id] = imgs
    return result


def _calls(path):
    calls = {}
    with path.open('rb') as stream:
        for line in stream:
            if not line.startswith(b'data:'):
                continue
            try:
                event = json.loads(line[5:].strip())
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(event, dict) or event.get('type') != 'response.output_item.done':
                continue
            item = event.get('item')
            if not isinstance(item, dict) or item.get('type') != 'function_call' or item.get('name') != 'view_image':
                continue
            call_id = item.get('call_id')
            if not isinstance(call_id, str) or not call_id:
                raise EvidenceError('view_image call has no identity')
            calls[call_id] = True
    return calls


def reconcile(capture):
    capture = Path(capture)
    files = {}
    paths = list(capture.glob('*.response')) + list(capture.glob('*.request.json'))
    for path in paths:
        stem = path.name.removesuffix('.response').removesuffix('.request.json')
        if re.fullmatch(r'[0-9]+', stem):
            number = int(stem)
            if number in files and files[number] != stem:
                raise EvidenceError('ambiguous numeric exchange identity')
            files[number] = stem
    calls = {}
    for number, stem in sorted(files.items()):
        path = capture / (stem + '.response')
        if not path.is_file():
            continue
        for call_id in _calls(path):
            if call_id in calls:
                raise EvidenceError('duplicate view_image call identity')
            calls[call_id] = {'call_id': call_id, 'call_exchange': stem,
                              'image_input': 'not_observed', 'forwarded_to_intermediate': 'unknown',
                              'provider_delivery': 'unknown'}
    for number, stem in sorted(files.items()):
        req = capture / (stem + '.request.json')
        if not req.is_file():
            continue
        try:
            request = json.loads(req.read_bytes())
        except (OSError, ValueError):
            continue
        observed = _outputs(request)
        upstream_path = capture / (stem + '.upstream-request.json')
        try:
            upstream = _outputs(json.loads(upstream_path.read_bytes()))
        except (OSError, ValueError):
            upstream = {}
        try:
            status = json.loads((capture / (stem + '.status.json')).read_bytes())
        except (OSError, ValueError):
            status = {}
        if not isinstance(status, dict):
            status = {}
        for call_id, images in observed.items():
            call = calls.get(call_id)
            if not call or int(call['call_exchange']) >= number or call['image_input'] != 'not_observed':
                continue
            call.update(image_input='observed', request_exchange=stem, images=images)
            # Only byte identities can prove equality at the captured proxy boundary.
            if (all(x.get('identity') == 'sha256' for x in images) and upstream.get(call_id) == images
                    and type(status.get('status')) is int and 200 <= status['status'] < 300):
                call['forwarded_to_intermediate'] = 'observed'
    return {'schema': 'agentlab.image_evidence_reconciliation.v1',
            'scope': 'captured_intermediate_gateway_only', 'calls': list(calls.values()),
            'limitations': ['No proof of provider receipt, visual comprehension or task correctness',
                            'Incomplete capture means not_observed is not proof of absence']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    if not args.capture.is_dir():
        parser.error('capture directory does not exist')
    print(json.dumps(reconcile(args.capture), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
