#!/usr/bin/env python3
"""Thin scheduling: Rust binds repairs; existing isolated launchers execute them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--gate', type=Path, required=True)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--image-id', required=True)
    p.add_argument('--maximum-repairs', type=int, choices=range(3), default=0)
    args = p.parse_args()
    root, gate, compiler = args.root.resolve(strict=True), args.gate.resolve(strict=True), args.compiler.resolve(strict=True)
    repository = Path(__file__).resolve().parents[1]
    if args.maximum_repairs and (root/'revision-request.json').exists():
        raise ValueError('Reviewed child cannot reset its budget into automatic diagnostic repair')
    # Fresh exclusive loop ownership: never resume/retry an uncertain invocation.
    frozen=root/'diagnostic-loop-intent.json'
    if args.maximum_repairs or frozen.exists():
        subprocess.run([str(gate),'--check-source-recipe-loop-intent','--author-request',str(root/'request.json'),
            '--diagnostic-loop-intent',str(frozen),'--output',str(root/'diagnostic-loop-intent-admission.json')],
            check=True,timeout=60,stdout=subprocess.DEVNULL)
        if json.loads(frozen.read_bytes())['maximumRepairs'] != args.maximum_repairs:
            raise ValueError('Code repair budget differs from pre-generation intent')
    intent = dict(schema='agentlab.source_recipe_diagnostic_loop_start.v1',
        maximumRepairs=args.maximum_repairs, automaticPromotion=False,
        authorityWritePerformed=False, qualified=False)
    with (root/'diagnostic-loop-start.json').open('x') as stream:
        json.dump(intent, stream)
    rows = []
    stage = root/'agent/proposal-stage'
    for index in range(args.maximum_repairs+1):
        diagnostic = root/('baseline-diagnostic' if index == 0 else f'baseline-diagnostic-repair-{index}')
        subprocess.run([str(gate),'--prepare-source-recipe-diagnostic', '--stage',str(stage),
            '--typescript',str(compiler),'--worker',str(repository/'scripts/source-recipe-diagnostic-worker.cjs'),
            '--image-id',args.image_id,'--output',str(diagnostic)], check=True, timeout=60,
            stdout=subprocess.DEVNULL)
        with (diagnostic/'launcher-stdout.log').open('xb') as out, (diagnostic/'launcher-stderr.log').open('xb') as err:
            execution = subprocess.run([sys.executable,str(repository/'scripts/run-contained-behavior-worker.py'),
                str(diagnostic/'descriptor.json'),str(diagnostic/'request.json')],
                cwd=diagnostic,stdout=out,stderr=err,timeout=65)
        captures = list(diagnostic.glob('contained-input-*'))
        if len(captures) != 1:
            raise ValueError('Expected exactly one owned capture; no Agent repair after pre-launch failure')
        feedback = diagnostic/'feedback.json'
        subprocess.run([str(gate),'--feedback-source-recipe-diagnostic','--diagnostic-inputs',str(diagnostic),
            '--worker-capture',str(captures[0]),'--output',str(feedback)],check=True,timeout=60,
            stdout=subprocess.DEVNULL)
        report=json.loads(feedback.read_bytes())
        rows.append(dict(index=index,stage=str(stage.relative_to(root)),diagnostic=diagnostic.name,
            feedbackSha256=hashlib.sha256(feedback.read_bytes()).hexdigest(),
            launcherExitCode=execution.returncode,baselinePassed=report['baselinePassed'],
            classification=report['classification']))
        with (root/f'diagnostic-loop-observation-{index}.json').open('x') as stream:
            json.dump(dict(schema='agentlab.source_recipe_diagnostic_loop_observation.v1',
                attempts=rows,maximumRepairs=args.maximum_repairs,qualified=False,
                automaticPromotion=False,authorityWritePerformed=False),stream)
        if report['baselinePassed']:
            if execution.returncode:
                raise ValueError('Launcher failed despite reconstructed observations; stop for infrastructure review')
            result=dict(schema='agentlab.source_recipe_diagnostic_loop_result.v1',
                status='baseline-passed',selectedStage=str(stage.relative_to(root)),attempts=rows,
                maximumRepairs=args.maximum_repairs,qualified=False,semanticQualified=False,
                automaticPromotion=False,authorityWritePerformed=False)
            with (root/'diagnostic-loop-result.json').open('x') as stream:
                json.dump(result,stream)
            print(json.dumps(result))
            return
        if index == args.maximum_repairs:
            raise ValueError('Diagnostic code repair budget exhausted; all originals retained')
        repair = root/f'code-repair-{index+1}'
        repair.mkdir()
        packet = repair/'packet.json'
        # Native requalification decides whether failure is eligible. Timeout,
        # log growth, cleanup uncertainty and budget drift never get another turn.
        subprocess.run([str(gate),'--prepare-source-recipe-diagnostic-repair','--stage',str(stage),
            '--diagnostic-inputs',str(diagnostic),'--worker-capture',str(captures[0]),
            '--maximum-repairs',str(args.maximum_repairs),'--output',str(packet)],
            check=True,timeout=60,stdout=subprocess.DEVNULL)
        design=stage/'design.json'
        env=dict(os.environ,AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT=str(repair/'runtime-receipts'))
        command=[sys.executable,str(repository/'scripts/run-source-recipe-author.py'),
            '--request',str(root/'request.json'),'--output',str(repair/'agent'),'--gate',str(gate),
            '--pi',str(repository/'scripts/run-pi-in-docker.py'), '--frozen-design',str(design),
            '--frozen-design-sha256',hashlib.sha256(design.read_bytes()).hexdigest(),
            '--diagnostic-repair',str(packet),'--design-revisions','0']
        for option,name in [('reasoning-effort','CONSTRUCTION_REASONING_EFFORT'),
            ('gateway-timeout-seconds','CONSTRUCTION_GATEWAY_TIMEOUT'),('max-output-tokens','CONSTRUCTION_MAX_OUTPUT_TOKENS'),
            ('thinking-type','CONSTRUCTION_THINKING_TYPE'),('response-format','CONSTRUCTION_RESPONSE_FORMAT'),('api','CONSTRUCTION_API')]:
            command += ['--'+option,os.environ[name]]
        code_deadline = os.environ.get('CONSTRUCTION_CODE_GATEWAY_TIMEOUT', 'inherit')
        if code_deadline != 'inherit':
            command += ['--code-gateway-timeout-seconds', code_deadline]
        with (repair/'author-stdout.log').open('xb') as out, (repair/'author-stderr.log').open('xb') as err:
            generated=subprocess.run(command,env=env,stdout=out,stderr=err,timeout=360)
        # Independently validate even a failed/partial generation; never replace
        # transport failure with a code correction or continue after failed isolation.
        isolation=subprocess.run([sys.executable,str(repository/'scripts/validate-participant-runtime.py'),
            '--config',os.environ['AGENTLAB_PARTICIPANT_RUNTIME_CONFIG'],
            '--receipt-root',str(repair/'runtime-receipts'),'--workspace',str(repair/'agent/workspace'),
            '--participant-state',str(repair/'agent/participant-state'),'--label','source-recipe-author',
            '--output',str(repair/'runtime-validation.json')],timeout=60,stdout=subprocess.DEVNULL)
        generated.check_returncode()
        isolation.check_returncode()
        stage=repair/'agent/proposal-stage'


if __name__ == '__main__':
    main()
