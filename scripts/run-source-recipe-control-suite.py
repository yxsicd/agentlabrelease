#!/usr/bin/env python3
"""Schedule frozen controls; native Rust reconstructs all behavioral comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def owned(root, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Invalid suite-owned path')
    relative = Path(name)
    if relative.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Invalid suite-owned path')
    path = root
    for part in relative.parts:
        path = path/part
        if path.is_symlink():
            raise ValueError('Suite path symlink')
    return path


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--gate', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--image-id', required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    gate = args.gate.resolve(strict=True)
    compiler = args.compiler.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    result = json.loads((root/'diagnostic-loop-result.json').read_bytes())
    if result.get('schema') != 'agentlab.source_recipe_diagnostic_loop_result.v1' or result.get('status') != 'baseline-passed':
        raise ValueError('Successful native baseline diagnostic required')
    stage = owned(root, result['selectedStage'])
    last = result['attempts'][-1]
    if last['stage'] != result['selectedStage'] or last['baselinePassed'] is not True:
        raise ValueError('Selected baseline lineage differs')
    baseline = owned(root, last['diagnostic'])
    captures = list(baseline.glob('contained-input-*'))
    if len(captures) != 1:
        raise ValueError('Exactly one retained baseline capture required')
    if (stage/'request.json').read_bytes() != (root/'request.json').read_bytes():
        raise ValueError('Selected stage request differs from root')
    suite = root/'control-suite'
    suite.mkdir()  # Exclusive ownership: never restart an uncertain invocation.
    save(suite/'start.json', dict(schema='agentlab.source_recipe_control_suite_start.v1',
        selectedStage=result['selectedStage'], diagnosticOnly=True, qualified=False,
        automaticPromotion=False, authorityWritePerformed=False))
    admission = suite/'baseline-admission.json'
    subprocess.run([str(gate), '--feedback-source-recipe-diagnostic', '--diagnostic-inputs', str(baseline),
        '--worker-capture', str(captures[0]), '--output', str(admission)], check=True, timeout=60,
        stdout=subprocess.DEVNULL)
    report = json.loads(admission.read_bytes())
    intent = json.loads((baseline/'intent.json').read_bytes())
    if report.get('baselinePassed') is not True or intent['originalStageReceipt'] != json.loads((stage/'stage-receipt.json').read_bytes()):
        raise ValueError('Reconstructed baseline or selected stage differs')
    design_bytes = (stage/'design.json').read_bytes()
    controls = json.loads(design_bytes)['controls']
    ids = [c['id'] for c in controls]
    if not 4 <= len(controls) <= 16 or len(set(ids)) != len(ids):
        raise ValueError('Bounded unique control inventory required')
    references = [c for c in controls if c['role'] == 'reference']
    if len(references) < 2 or sum(c['role'] == 'wrong' for c in controls) < 1 or sum(c['role'] == 'baseline' for c in controls) != 1:
        raise ValueError('Complete declared baseline, valid and wrong inventory required')
    rows = []
    schedule = [(c, False) for c in controls] + [(references[0], True)]
    for index, (control, recovery) in enumerate(schedule):
        directory = suite/f'control-{index}'
        subprocess.run([str(gate), '--prepare-source-recipe-control-diagnostic', '--stage', str(stage),
            '--control-id', control['id'], '--typescript', str(compiler),
            '--worker', str(repo/'scripts/source-recipe-diagnostic-worker.cjs'),
            '--image-id', args.image_id, '--output', str(directory)],
            check=True, timeout=60, stdout=subprocess.DEVNULL)
        with (directory/'launcher-stdout.log').open('xb') as out, (directory/'launcher-stderr.log').open('xb') as err:
            executed = subprocess.run([sys.executable, str(repo/'scripts/run-contained-behavior-worker.py'),
                str(directory/'descriptor.json'), str(directory/'request.json')],
                cwd=directory, stdout=out, stderr=err, timeout=65)
        captures = list(directory.glob('contained-input-*'))
        if len(captures) != 1:
            raise ValueError('Exactly one control capture required; no hidden retry')
        feedback = directory/'feedback.json'
        subprocess.run([str(gate), '--feedback-source-recipe-diagnostic', '--diagnostic-inputs', str(directory),
            '--worker-capture', str(captures[0]), '--output', str(feedback)],
            check=True, timeout=60, stdout=subprocess.DEVNULL)
        verdict = json.loads(feedback.read_bytes())
        rows.append(dict(controlId=control['id'], role=control['role'], recovery=recovery,
            feedbackSha256=hashlib.sha256(feedback.read_bytes()).hexdigest(),
            classification=verdict['classification'], declarationMatched=verdict['declarationMatched']))
        save(suite/f'observation-{index}.json', dict(attempts=rows, diagnosticOnly=True, qualified=False))
        if executed.returncode or verdict.get('executionCompleted') is not True:
            raise ValueError('Control infrastructure failure; retained without semantic retry')
    if (stage/'design.json').read_bytes() != design_bytes:
        raise ValueError('Frozen design changed during suite')
    matched = all(row['declarationMatched'] for row in rows)
    save(suite/'result.json', dict(schema='agentlab.source_recipe_control_suite_result.v1',
        status='declarations-matched' if matched else 'review-declaration-mismatch',
        selectedStage=result['selectedStage'], designSha256=hashlib.sha256(design_bytes).hexdigest(),
        attempts=rows, diagnosticOnly=True, qualified=False, semanticQualified=False,
        automaticPromotion=False, authorityWritePerformed=False))
    if not matched:
        raise ValueError('Frozen declaration mismatch; review without rewriting expectations')


if __name__ == '__main__':
    main()
