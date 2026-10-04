#!/usr/bin/env python3
"""Bound a retained baseline rejection to one durable fresh constructor slot.

Rust owns diagnostic and review reconstruction. This transport does not grant
source-suite acceptance, knowledge authority or global exactly-once writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def execute(args):
    output = args.output
    if getattr(args, 'prepared_output', False):
        if output.is_symlink() or not output.is_dir():
            raise ValueError('Prepared output must be an existing regular Action directory')
    else:
        output.mkdir()
    terminal = dict(schema='agentlab.baseline_continuation_transport.v1',
        dispatchIntentRecorded=False, durableClaimCreated=False,
        constructionCompleted=False, runtimeIsolationVerified=False,
        recordedAuthorCompletionVerified=False, oldBudgetReopened=False,
        globalExactlyOnceVerified=False, sourceControlSuiteExecuted=False,
        independentReviewExecuted=False, knowledgeWritePerformed=False,
        semanticQualified=False, qualified=False, automaticPromotion=False)

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
        return result.stdout

    try:
        runtime_config = os.environ.get('AGENTLAB_PARTICIPANT_RUNTIME_CONFIG')
        if not runtime_config or not Path(runtime_config).is_file():
            raise ValueError('Contained participant config is required before claims')
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository)
                or not re.fullmatch(r'[0-9a-f]{40}', args.method_revision)
                or not re.fullmatch(r'[0-9a-f]{40}', args.parent_method_revision)
                or not re.fullmatch(r'[0-9a-f]{64}', args.parent_archive_sha256)
                or not str(args.parent_run).isdigit() or not str(args.parent_artifact).isdigit()):
            raise ValueError('Invalid exact GitHub enrollment identity')
        producer = json.loads(run(['gh', 'api', f'repos/{args.repository}/actions/runs/{args.parent_run}'], 'producer'))
        artifact = json.loads(run(['gh', 'api', f'repos/{args.repository}/actions/artifacts/{args.parent_artifact}'], 'artifact'))
        if (producer.get('id') != int(args.parent_run) or producer.get('status') != 'completed'
                or producer.get('run_attempt') != 1 or producer.get('event') != 'workflow_dispatch'
                or producer.get('path') != '.github/workflows/maintainer-source-recipe-author.yml'
                or producer.get('head_sha') != args.parent_method_revision or producer.get('head_branch') != 'main'
                or artifact.get('id') != int(args.parent_artifact) or artifact.get('expired') is not False
                or artifact.get('name') != f'unreviewed-source-recipe-{args.parent_run}'
                or (artifact.get('workflow_run') or {}).get('id') != int(args.parent_run)
                or artifact.get('digest') != 'sha256:' + args.parent_archive_sha256):
            raise ValueError('Original GitHub producer/artifact identity differs')
        if args.parent_archive.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Original archive budget')
        raw = args.parent_archive.read_bytes()
        if len(raw) > 64 * 1024 * 1024 or digest(raw) != args.parent_archive_sha256 or artifact.get('size_in_bytes') != len(raw):
            raise ValueError('Original archive digest/size differs')
        packet_bytes = args.diagnostic_repair.read_bytes()
        if len(packet_bytes) > 16 * 1024 * 1024:
            raise ValueError('Diagnostic continuation packet budget')
        packet = json.loads(packet_bytes)
        if packet.get('schema') != 'agentlab.source_recipe_diagnostic_repair.v2':
            raise ValueError('Only prospectively enrolled continuation packets are accepted')
        successor_bytes = args.successor_request.read_bytes()
        review_enrollment_bytes = args.review_enrollment.read_bytes()
        # Read only the exact original members; never execute/extract archive code.
        with zipfile.ZipFile(args.parent_archive) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate original archive members')
            process_names = [n for n in names if re.fullmatch(r'baseline-diagnostic/contained-input-[^/]+/process.json', n)]
            if len(process_names) != 1:
                raise ValueError('Expected one original baseline process')
            capture = process_names[0].rsplit('/', 1)[0]
            originals = {
                'parentRequestOriginal': 'agent/proposal-stage/request.json',
                'parentProposalOriginal': 'agent/proposal-stage/proposal.json',
                'parentDesignOriginal': 'agent/proposal-stage/design.json',
                'parentStageReceiptOriginal': 'agent/proposal-stage/stage-receipt.json',
                'intentOriginal': 'baseline-diagnostic/intent.json',
                'executionRequestOriginal': 'baseline-diagnostic/request.json',
                'descriptorOriginal': 'baseline-diagnostic/descriptor.json',
                'supportOriginal': 'baseline-diagnostic/support.json',
                'processOriginal': capture + '/process.json',
                'stdoutOriginal': capture + '/worker-stdout.log',
                'stderrOriginal': capture + '/worker-stderr.log',
            }
            for key, member in originals.items():
                if archive.getinfo(member).file_size > 4 * 1024 * 1024 or archive.read(member) != packet[key].encode():
                    raise ValueError('Original archive/packet bytes differ: ' + key)
            if (archive.getinfo('successor-request.json').file_size > 64 * 1024 * 1024
                    or archive.getinfo('successor-enrollment.json').file_size > 65536):
                raise ValueError('Original review lineage budget')
            if (archive.read('successor-request.json') != successor_bytes
                    or archive.read('successor-enrollment.json') != review_enrollment_bytes):
                raise ValueError('Original successor review lineage differs')
        request_bytes = args.request.read_bytes()
        if request_bytes != packet['parentRequestOriginal'].encode():
            raise ValueError('Fresh author request differs from original baseline')
        request = output / 'request.json'
        design = output / 'frozen-design.json'
        repair = output / 'diagnostic-repair.json'
        if getattr(args, 'prepared_output', False):
            if request.is_symlink() or request.read_bytes() != request_bytes:
                raise ValueError('Prepared Action request differs from original baseline')
        else:
            write_new(request, request_bytes)
        write_new(design, packet['parentDesignOriginal'].encode())
        write_new(repair, packet_bytes)
        gate = str(args.gate.resolve(strict=True))
        run([gate, '--check-source-recipe-diagnostic-repair', '--author-request', str(request),
             '--diagnostic-repair', str(repair), '--output', str(output / 'diagnostic-admission.json')], 'diagnostic-admission')
        acquisition = Path(__file__).with_name('prepare-reviewed-successor-action.py')
        run([sys.executable, str(acquisition), '--enrollment', str(args.review_enrollment),
             '--output', str(output / 'retained-review'), '--request', str(request), '--gate', gate,
             '--repository', args.repository, '--source-git-checkout', str(args.source_git_checkout)], 'retained-review')
        inputs = json.loads((output / 'retained-review/bridge-inputs.json').read_bytes())
        original_args = []
        for key in ('source', 'quality_rubric', 'participant_evidence', 'review_response',
                    'review_feedback', 'successor_policy', 'source_git_checkout'):
            original_args += ['--' + key.replace('_', '-'), inputs[key]]
        run([gate, '--check-source-reviewed-successor', *original_args,
             '--successor-request', str(args.successor_request), '--output', str(output / 'original-successor-check.json')], 'original-successor')
        successor = json.loads(successor_bytes)
        if (successor['authorRequestOriginal'].encode() != request_bytes
                or json.loads(successor['targetDesignOriginal']) != json.loads(design.read_bytes())):
            raise ValueError('Original reviewed target differs from retained failed design')
        run([gate, '--validate-source-recipe-design', '--author-request', str(request),
             '--design', str(design), '--output', str(output / 'live-design.json')], 'live-design')
        # Identity deliberately excludes the new enrollmentId and policy bytes.
        slot = digest(json.dumps(dict(repository=args.repository, parentRun=str(args.parent_run),
            parentArtifact=str(args.parent_artifact), parentArchiveSha256=args.parent_archive_sha256),
            sort_keys=True, separators=(',', ':')).encode())
        claim_root = args.claim_root.resolve(strict=True)
        if args.claim_root.is_symlink() or not claim_root.is_dir():
            raise ValueError('Claim root must be an existing regular operator directory')
        ref = f'refs/heads/agentlab-baseline-continuation-claims/{slot}/1'
        terminal.update(dispatchIntentRecorded=True, durableClaimRef=ref,
            parentArchiveSha256=args.parent_archive_sha256, packetSha256=digest(packet_bytes))
        write_new(claim_root / (slot + '.json'), json.dumps(terminal, sort_keys=True).encode())
        write_new(output / 'dispatch-intent.json', json.dumps(terminal, sort_keys=True).encode())
        remote = json.loads(run(['gh', 'api', '--method', 'POST', f'repos/{args.repository}/git/refs',
            '-f', 'ref=' + ref, '-f', 'sha=' + args.method_revision], 'durable-claim'))
        if remote.get('ref') != ref or (remote.get('object') or {}).get('sha') != args.method_revision:
            raise ValueError('Durable claim response differs')
        terminal['durableClaimCreated'] = True
        env = dict(os.environ)
        for key in ('GH_TOKEN', 'GITHUB_TOKEN'):
            env.pop(key, None)
        env['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'] = str(output / 'runtime-receipts')
        constructor = Path(__file__).with_name('run-source-recipe-author.py')
        constructor_error = None
        try:
            run([sys.executable, str(constructor), '--request', str(request), '--output', str(output / 'agent'),
            '--gate', gate, '--pi', str(args.pi), '--frozen-design', str(design),
            '--frozen-design-sha256', digest(design.read_bytes()), '--diagnostic-repair', str(repair),
            '--design-revisions', '0', '--proposal-format-revisions', '0', '--reasoning-effort', args.reasoning_effort,
                '--require-independent-completion',
                '--gateway-timeout-seconds', '180', '--max-output-tokens', '16384'], 'constructor', timeout=600, env=env)
        except Exception as error:
            constructor_error = error
        try:
            run([sys.executable, str(Path(__file__).with_name('validate-participant-runtime.py')),
                '--config', runtime_config, '--receipt-root', str(output / 'runtime-receipts'),
                '--workspace', str(output / 'agent/workspace'), '--participant-state', str(output / 'agent/participant-state'),
                '--label', 'source-recipe-author', '--output', str(output / 'continuation-runtime-validation.json')], 'runtime-validation')
            terminal['runtimeIsolationVerified'] = True
        except Exception as error:
            terminal['runtimeValidationError'] = str(error)
            if constructor_error is not None:
                raise constructor_error
            raise
        if constructor_error is not None:
            raise constructor_error
        stage = output / 'agent/proposal-stage'
        run([gate, '--verify-unguided-source-recipe-completion',
            '--participant-evidence', str(output / 'agent/evidence'), '--author-request', str(request),
            '--proposal', str(stage / 'proposal.json'),
            '--output', str(output / 'independent-author-completion.json')], 'independent-author-completion')
        terminal['recordedAuthorCompletionVerified'] = True
        if (request.read_bytes() != request_bytes or repair.read_bytes() != packet_bytes
                or args.successor_request.read_bytes() != successor_bytes
                or args.review_enrollment.read_bytes() != review_enrollment_bytes
                or stage.joinpath('request.json').read_bytes() != request_bytes):
            raise ValueError('Continuation inputs changed during construction')
        run([gate, '--validate-source-recipe-diagnostic-repair-output', '--author-request', str(request),
            '--diagnostic-repair', str(repair), '--proposal', str(stage / 'proposal.json'),
            '--design', str(stage / 'design.json'), '--output', str(output / 'output-admission.json')], 'output-admission')
        run([gate, '--check-source-reviewed-successor', *original_args,
             '--successor-request', str(args.successor_request), '--output', str(output / 'post-successor-check.json')], 'post-successor')
        terminal['constructionCompleted'] = True
        return terminal
    except Exception as error:
        terminal.update(errorType=type(error).__name__, error=str(error))
        raise
    finally:
        write_new(output / 'transport-terminal.json', json.dumps(terminal, sort_keys=True).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('gate', 'pi', 'request', 'diagnostic-repair', 'successor-request', 'review-enrollment',
                 'parent-archive', 'source-git-checkout', 'claim-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('repository', 'method-revision', 'parent-method-revision', 'parent-run',
                 'parent-artifact', 'parent-archive-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--reasoning-effort', choices=('default', 'none', 'low', 'medium', 'high', 'max'), default='low')
    parser.add_argument('--prepared-output', action='store_true', help='Reuse only the exact Action-owned request; all other outputs remain exclusive')
    print(json.dumps(execute(parser.parse_args())))


if __name__ == '__main__':
    main()
