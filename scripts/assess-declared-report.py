#!/usr/bin/env python3
"""Describe and assess one declared report contract, without network or execution.

The contract is public; expected values are a separate private oracle. Freeze
both digests before an assessed run. Later correction is explicitly posthoc.
This checks declarations, not evidence authenticity or whole-task completion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'agentlab.report_contract.v1'
JSON_TYPES = {'string': str, 'boolean': bool, 'integer': int}
RULES = {'object', 'exact', 'coverage', 'comparison', 'evidence_path', 'strings', 'contains_any'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate JSON key: ' + k)
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def validate(contract):
    if contract.get('schema') != SCHEMA:
        raise ValueError('unsupported contract')
    ids = contract.get('observationIds', [])
    prefix = contract.get('referencePrefix', '')
    if not ids or len(set(ids)) != len(ids) or not prefix or not all(
        isinstance(i, str) and i.startswith(prefix) and re.fullmatch(r'[A-Za-z0-9_-]+', i) for i in ids
    ):
        raise ValueError('invalid observation identifiers')
    rules = contract.get('rules', [])
    if not rules or len({r['id'] for r in rules}) != len(rules):
        raise ValueError('invalid criterion identifiers')
    for r in rules:
        if r['kind'] not in RULES:
            raise ValueError('unsupported rule')
        if r['kind'] in {'exact', 'comparison'} and (not isinstance(r.get('fieldTypes'), dict) or not r['fieldTypes'] or any(t not in JSON_TYPES for t in r['fieldTypes'].values())):
            raise ValueError('declare exact compared fields and JSON types publicly')
        if r['kind'] in {'comparison', 'evidence_path'} and r.get('observationId') not in ids:
            raise ValueError('unknown observation identifier')
    return contract


def describe(contract):
    validate(contract)
    return ('# Report output contract\n\n'
            'This is a report reference, never an executable selector. `selector` '
            'must contain exactly one identifier token from the declared observation IDs, '
            'either bare or inside descriptive text; unknown or multiple prefixed tokens '
            'and duplicate rows fail. Expected business values remain private. '
            'Evidence paths must be absolute and contain no parent traversal. '
            'Missing fields are distinct from null; exact comparisons preserve JSON types.\n\n'
            'The following rules are the exact input to the checker (not an independently maintained guide):\n\n'
            '```json\n' + json.dumps(contract, ensure_ascii=False, indent=2) + '\n```\n')


def observation_index(report, contract):
    rows = report.get('observations')
    if not isinstance(rows, list):
        return {}, False
    index = {}
    pattern = r'(?<![A-Za-z0-9_-])' + re.escape(contract['referencePrefix']) + r'[A-Za-z0-9_-]+(?![A-Za-z0-9_-])'
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('selector'), str):
            return {}, False
        tokens = re.findall(pattern, row['selector'])
        if len(tokens) != 1 or tokens[0] not in contract['observationIds'] or tokens[0] in index:
            return {}, False
        index[tokens[0]] = row
    return index, set(index) == set(contract['observationIds'])


def equal_fields(actual, expected):
    # Python bool==int is not JSON typed equality.
    return bool(expected) and all(k in actual and type(actual[k]) is type(v) and actual[k] == v for k, v in expected.items())


def assess(raw, contract, oracle):
    validate(contract)
    # Validate oracle configuration before parsing student output. Missing oracle
    # is an evaluator error, never a student failure or empty expectation pass.
    for rule in contract['rules']:
        kind = rule['kind']
        if kind in {'exact', 'comparison', 'evidence_path', 'contains_any'}:
            expected = oracle[rule['oracleKey']]
            if kind in {'exact', 'comparison'} and (not isinstance(expected, dict) or not expected):
                raise ValueError('expected fields must be a nonempty object')
            if kind in {'exact', 'comparison'} and (set(expected) != set(rule['fieldTypes']) or any(type(expected[k]) is not JSON_TYPES[t] for k, t in rule['fieldTypes'].items())):
                raise ValueError('oracle must match publicly declared fields/types')
            if kind == 'evidence_path' and (not isinstance(expected, str) or not expected.startswith('/') or '..' in expected.split('/')):
                raise ValueError('expected evidence path must be absolute and normalized')
            if kind == 'contains_any' and (not isinstance(expected, list) or not expected or not all(isinstance(v, str) and v for v in expected)):
                raise ValueError('expected source declarations must be nonempty strings')
    try:
        report = decode(raw)
    except (ValueError, UnicodeError):
        report = None
    valid = isinstance(report, dict) and bool(report)
    report = report if isinstance(report, dict) else {}
    index, coverage = observation_index(report, contract)
    criteria = []
    for rule in contract['rules']:
        kind = rule['kind']
        if kind == 'object':
            ok = valid
        elif kind == 'exact':
            ok = equal_fields(report, oracle[rule['oracleKey']])
        elif kind == 'coverage':
            ok = coverage
        elif kind == 'comparison':
            ok = equal_fields(index.get(rule['observationId'], {}), oracle[rule['oracleKey']])
        elif kind == 'evidence_path':
            path = index.get(rule['observationId'], {}).get('rawLayoutPath')
            ok = isinstance(path, str) and '..' not in path.split('/') and path == oracle[rule['oracleKey']]
        elif kind == 'strings':
            value = report.get(rule['field'])
            ok = isinstance(value, list) and len(value) >= rule['minimum'] and all(isinstance(v, str) and v.strip() for v in value)
        elif kind == 'contains_any':
            value = report.get(rule['field'])
            ok = isinstance(value, list) and any(isinstance(v, str) and any(s in v for s in oracle[rule['oracleKey']]) for v in value)
        criteria.append({'criterionId': rule['id'], 'verdict': 'pass' if ok else 'fail'})
    passed = sum(c['verdict'] == 'pass' for c in criteria)
    return {'schema': 'agentlab.report_contract_assessment.v1', 'criteria': criteria,
            'passed': passed, 'total': len(criteria), 'verdict': 'pass' if passed == len(criteria) else 'fail',
            'reportSHA256': digest(raw), 'reportBytes': len(raw),
            'qualification': 'declared-report-content-only; no evidence authenticity or independent whole-task claim'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['describe', 'assess'])
    p.add_argument('--contract', required=True, type=Path)
    p.add_argument('--oracle', type=Path)
    p.add_argument('--report', type=Path)
    p.add_argument('--timing', choices=['frozen', 'posthoc'])
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    cbytes = a.contract.read_bytes()
    contract = decode(cbytes)
    if a.action == 'describe':
        output = describe(contract)
        status = 0
    else:
        if not a.oracle or not a.report or not a.timing:
            p.error('assess requires --oracle, --report and --timing; frozen requires separately retained pre-run freeze evidence')
        obytes = a.oracle.read_bytes()
        result = assess(a.report.read_bytes(), contract, decode(obytes))
        result.update(contractSHA256=digest(cbytes), oracleSHA256=digest(obytes), assessmentTiming=a.timing)
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        status = 0 if result['verdict'] == 'pass' else 1
    # Never overwrite an earlier policy, assessment or generated declaration.
    with a.output.open('x') as f:
        f.write(output)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
