"""Summarize captured provider usage without changing participant traffic."""
import json
from pathlib import Path


def _integer(value):
    return value if type(value) is int and value >= 0 else None


def _usage(payload):
    if not isinstance(payload, dict):
        return None
    value = payload.get('usage')
    if value is None and isinstance(payload.get('response'), dict):
        value = payload['response'].get('usage')
    if not isinstance(value, dict):
        return None
    details = value.get('prompt_tokens_details') or value.get('input_tokens_details') or {}
    if not isinstance(details, dict):
        details = {}
    output_details = value.get('completion_tokens_details') or value.get('output_tokens_details') or {}
    if not isinstance(output_details, dict):
        output_details = {}
    return dict(input=_integer(value.get('prompt_tokens', value.get('input_tokens'))),
                output=_integer(value.get('completion_tokens', value.get('output_tokens'))),
                cached_input=_integer(details.get('cached_tokens')),
                reasoning_output=_integer(output_details.get('reasoning_tokens')))


def _read_usage(path):
    try:
        with path.open('rb') as stream:
            prefix = stream.read(1024).lstrip()
            stream.seek(0)
            if prefix.startswith(b'data:') or prefix.startswith(b'event:') or prefix.startswith(b':'):
                latest = None
                for line in stream:
                    if not line.startswith(b'data:'):
                        continue
                    try:
                        candidate = _usage(json.loads(line[5:].strip()))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if candidate is not None:
                        latest = candidate
                return latest
            return _usage(json.load(stream))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def summarize(capture):
    records = []
    capture = Path(capture)
    ids = set()
    for suffix in ('.status.json', '.response', '.request.json'):
        ids.update(path.name.removesuffix(suffix) for path in capture.glob('*' + suffix))
    for exchange in sorted(ids):
        status_path = capture / (exchange + '.status.json')
        try:
            status = json.loads(status_path.read_text())
        except (OSError, ValueError):
            status = {}
        if not isinstance(status, dict):
            status = {}
        response_path = capture / (exchange + '.response')
        usage = _read_usage(response_path)
        # Incomplete or non-successful exchanges may still carry partial usage;
        # retain it but do not call overall accounting complete.
        qualified = (status.get('outcome') == 'completed' and status.get('upstreamEof') is True
                     and isinstance(status.get('status'), int) and 200 <= status['status'] < 300)
        records.append(dict(exchange=exchange, complete=qualified, usage=usage))
    fields = ('input', 'output', 'cached_input', 'reasoning_output')
    totals = {key: sum(r['usage'][key] for r in records if r['usage'] and r['usage'][key] is not None)
              for key in fields}
    coverage = {key: sum(1 for r in records if r['usage'] and r['usage'][key] is not None)
                for key in fields}
    totals = {key: totals[key] if coverage[key] else None for key in fields}
    complete = bool(records) and all(r['complete'] and r['usage'] and
                                    r['usage']['input'] is not None and r['usage']['output'] is not None
                                    for r in records)
    return dict(schema='agentlab.swe_usage_observation.v1', exchanges=len(records),
                inputOutputComplete=complete, totalsObserved=totals, fieldCoverage=coverage,
                records=records, cachedInputIncludedInInput=True,
                # Captured provider usage alone cannot establish whether a
                # separate launcher enforced a budget. Its caller may supply
                # that fact from its own execution context.
                reasoningOutputIncludedInOutput=True, tokenBudgetEnforced=None)
