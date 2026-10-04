#!/usr/bin/env python3
"""Bridge original rejected feedback to one fresh frozen-design constructor.

Rust owns reconstruction and admission. The persistent claim is scoped to the
chosen operator claim directory, not global exactly-once scheduling.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def execute(args):
    output = args.output
    output.mkdir()
    packet_path = output / 'successor-request.json'
    terminal = dict(schema='agentlab.source_successor_construction_transport.v1',
                    dispatchIntentRecorded=False, constructorReturned=False,
                    constructionCompleted=False, oldBudgetReopened=False,
                    sourceControlSuiteExecuted=False, independentReviewExecuted=False,
                    knowledgeWritePerformed=False, automaticPromotion=False,
                    semanticQualified=False, qualified=False,
                    runtimeIsolationVerified=False, recordedAuthorCompletionVerified=False,
                    globalExactlyOnceVerified=False, historicalFeedbackCaptureVerified=False)

    def run(command, label, timeout=60, env=None):
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired as error:
            write_new(output / (label + '-stdout.log'), error.stdout or b'')
            write_new(output / (label + '-stderr.log'), error.stderr or b'')
            raise
        write_new(output / (label + '-stdout.log'), result.stdout)
        write_new(output / (label + '-stderr.log'), result.stderr)
        result.check_returncode()
        return result

    try:
        original_args = []
        for name in ('source', 'quality_rubric', 'participant_evidence', 'review_response',
                     'review_feedback', 'successor_policy', 'source_git_checkout'):
            original_args += ['--' + name.replace('_', '-'), str(getattr(args, name).resolve(strict=True))]
        if args.previous_successor:
            original_args += ['--previous-successor', str(args.previous_successor.resolve(strict=True))]
        gate = str(args.gate.resolve(strict=True))
        run([gate, '--prepare-source-reviewed-successor', *original_args,
             '--output', str(packet_path)], 'prepare')
        packet_bytes = packet_path.read_bytes()
        packet = json.loads(packet_bytes)
        request_bytes = args.request.read_bytes()
        if request_bytes != packet['authorRequestOriginal'].encode():
            raise ValueError('Fresh author request differs from original successor enrollment')
        request = output / 'request.json'
        design = output / 'target-design.json'
        parent = output / 'parent-design.json'
        feedback = output / 'review-feedback.json'
        write_new(request, request_bytes)
        write_new(design, packet['targetDesignOriginal'].encode())
        write_new(parent, packet['parentDesignOriginal'].encode())
        write_new(feedback, packet['reviewFeedbackOriginal'].encode())
        run([gate, '--validate-source-recipe-design', '--author-request', str(request),
             '--design', str(design), '--output', str(output / 'live-design-validation.json')], 'live-design')
        run([gate, '--check-source-reviewed-successor', *original_args,
             '--successor-request', str(packet_path), '--output', str(output / 'pre-dispatch-reconstruction.json')],
            'pre-dispatch')
        identity = dict(authorRequestSha256=packet['authorRequestSha256'],
                        parentDesignSha256=digest(packet['parentDesignOriginal'].encode()),
                        targetDesignSha256=packet['targetDesignSha256'],
                        reviewResponseSha256=digest(packet['reviewResponseOriginal'].encode()),
                        policySha256=digest(packet['policyOriginal'].encode()))
        claim_id = digest(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode())
        claim_root = args.claim_root.resolve(strict=True)
        if not claim_root.is_dir() or args.claim_root.is_symlink():
            raise ValueError('Operator claim root must be an existing regular directory')
        claim = dict(schema='agentlab.source_successor_dispatch_claim.v1', identity=identity,
                     successorRequestSha256=digest(packet_bytes),
                     successorIndex=packet['successorIndex'], participantBudgetSeconds=420,
                     transportRetryLimit=0, output=str(output.resolve()),
                     globalExactlyOnceVerified=False, qualified=False)
        # Keep an uncertain or failed claim permanently; no retry, unlink or rebase.
        write_new(claim_root / (claim_id + '.json'), json.dumps(claim, sort_keys=True).encode())
        terminal.update(dispatchIntentRecorded=True, dispatchClaimId=claim_id,
                        successorRequestSha256=digest(packet_bytes), successorIndex=packet['successorIndex'])
        write_new(output / 'dispatch-intent.json', json.dumps(terminal, sort_keys=True).encode())
        env = dict(os.environ)
        env['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'] = str(output / 'runtime-receipts')
        constructor = Path(__file__).resolve().with_name('run-source-recipe-author.py')
        command = [sys.executable, str(constructor), '--request', str(request),
                   '--output', str(output / 'agent'), '--gate', gate, '--pi', str(args.pi.resolve(strict=True)),
                   '--frozen-design', str(design), '--frozen-design-sha256', packet['targetDesignSha256'],
                   '--design-revisions', '0', '--proposal-format-revisions', '0',
                   '--reasoning-effort', args.reasoning_effort,
                   '--gateway-timeout-seconds', '180', '--max-output-tokens', '16384']
        run(command, 'constructor', timeout=600, env=env)
        terminal['constructorReturned'] = True
        if packet_path.read_bytes() != packet_bytes or request.read_bytes() != request_bytes:
            raise ValueError('Successor enrollment changed during construction')
        stage = output / 'agent/proposal-stage'
        if stage.joinpath('request.json').read_bytes() != request_bytes:
            raise ValueError('Staged successor request differs')
        if design.read_bytes() != packet['targetDesignOriginal'].encode():
            raise ValueError('Frozen target changed during construction')
        run([gate, '--check-source-reviewed-successor', *original_args,
             '--successor-request', str(packet_path), '--output', str(output / 'post-construction-reconstruction.json')],
            'post-construction')
        run([gate, '--validate-source-design-review-output', '--author-request', str(request),
             '--parent-design', str(parent), '--review-feedback', str(feedback),
             '--design', str(stage / 'design.json'), '--output', str(output / 'staged-target-validation.json')],
            'staged-target')
        terminal.update(constructionCompleted=True,
                        stageReceiptSha256=digest((stage / 'stage-receipt.json').read_bytes()))
        return terminal
    except Exception as error:
        terminal.update(errorType=type(error).__name__, error=str(error))
        raise
    finally:
        write_new(output / 'transport-terminal.json', json.dumps(terminal, sort_keys=True).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gate', 'source', 'quality-rubric', 'participant-evidence', 'review-response',
                 'review-feedback', 'successor-policy', 'source-git-checkout', 'request', 'pi',
                 'claim-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--previous-successor', type=Path)
    parser.add_argument('--reasoning-effort', choices=('default', 'none', 'low', 'medium', 'high', 'max'), default='low')
    print(json.dumps(execute(parser.parse_args())))


if __name__ == '__main__':
    main()
