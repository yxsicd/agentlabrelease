#!/usr/bin/env python3
"""Thin isolated reviewer transport; all evidence/decision gates belong to Rust."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import copy


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate(args, flag, output, *extra):
    command = [str(args.gate.resolve()), flag,
               '--quality-rubric', str(args.rubric.resolve()), '--output', str(output), *extra]
    if getattr(args, 'author_request', None) is not None:
        command.extend(['--author-request', str(args.author_request.resolve()),
                        '--design', str(args.design.resolve())])
    else:
        command.extend(['--source', str(args.source.resolve())])
    if getattr(args, 'source_git_checkout', None) is not None:
        command.extend(['--source-git-checkout', str(args.source_git_checkout.resolve())])
    result = subprocess.run(command, capture_output=True, timeout=90)
    with output.with_suffix(output.suffix + '.stdout.log').open('xb') as stream:
        stream.write(result.stdout)
    with output.with_suffix(output.suffix + '.stderr.log').open('xb') as stream:
        stream.write(result.stderr)
    if result.returncode:
        raise RuntimeError(f'Native review gate {flag} rejected input; retained original stderr')


def run_attempt(args, participant_class=None):
    if not os.environ.get('AGENTLAB_PARTICIPANT_RUNTIME_CONFIG'):
        raise ValueError('Independent review requires the contained participant runtime')
    output = args.output.absolute()
    args._capture_created = False
    output.mkdir()  # Exclusive fresh capture, never resume the constructor session.
    args._capture_created = True
    evidence = output / 'evidence'
    workspace = output / 'workspace'
    evidence.mkdir()
    workspace.mkdir()
    design_review = getattr(args, 'author_request', None) is not None
    label = 'source-design-review' if design_review else 'source-suite-review'
    terminal = dict(schema=('agentlab.independent_source_design_review_transport.v1' if design_review
                           else 'agentlab.independent_source_suite_review_transport.v1'),
                    completed=False, automaticPromotion=False, authorityWritePerformed=False,
                    qualified=False)
    try:
        repair_enabled = getattr(args, 'review_repair_limit', 0) == 1
        if repair_enabled:
            review_policy = dict(schema='agentlab.review_repair_policy.v1', reviewRepairLimit=1,
                                 maximumReviewerAttempts=2, participantBudgetSeconds=420,
                                 totalParticipantBudgetSeconds=840, transportRetryLimit=0)
            with (evidence / 'review-repair-policy.json').open('x') as stream:
                json.dump(review_policy, stream)
            parent = getattr(args, 'repair_parent', None)
            if parent is not None:
                retained = evidence / 'repair-inputs'
                retained.mkdir()
                shutil.copyfile(parent / 'response.json', retained / 'response.json')
                shutil.copytree(parent / 'evidence', retained / 'evidence',
                                symlinks=True, ignore=shutil.ignore_patterns('source-suite-review-events.jsonl'))
        gate(args, '--prepare-source-design-quality-review' if design_review else
             '--prepare-source-suite-review', output / 'request.json')
        if repair_enabled:
            gate(args, '--source-design-quality-review-attempt-prompt' if design_review else
                 '--prepare-source-suite-review-attempt-prompt', output / 'prompt.txt',
                 '--evidence' if design_review else '--participant-evidence', str(evidence))
        else:
            gate(args, '--source-design-quality-review-prompt' if design_review else
                 '--prepare-source-suite-review-prompt', output / 'prompt.txt')
        prompt = (output / 'prompt.txt').read_text()
        packet = json.loads((output / 'request.json').read_bytes())
        # Request digest is emitted by the native prompt, not reimplemented here.
        request_digest = prompt.split('reviewRequestSha256 is ', 1)[1].split('.', 1)[0]
        if len(request_digest) != 64 or any(c not in '0123456789abcdef' for c in request_digest):
            raise ValueError('Native review prompt digest absent')
        repo = Path(__file__).resolve().parents[1]
        helpers = load_module('source_author_transport', repo / 'scripts/run-source-recipe-author.py')
        helpers.prepare_runtime_receipt_root()
        effort = None if args.reasoning_effort == 'default' else args.reasoning_effort
        if design_review and getattr(args, 'repair_parent', None) is not None:
            parent_intent = json.loads((evidence / 'repair-inputs/evidence/review-intent.json').read_bytes())
            identity = dict(model=os.environ['AGENTLAB_MODEL'],
                            providerRoute=os.environ['AGENTLAB_PROVIDER_ROUTE'],
                            providerReasoningEffort=effort)
            if parent_intent.get('participantIdentity') != identity:
                raise ValueError('Design review repair model or reasoning treatment differs')
        if participant_class is None:
            participant_class = load_module('review_participant', repo / 'examples/real-code-agent/participant.py').Participant
        participant = participant_class(
            evidence, output / 'participant-state', args.pi,
            os.environ['AGENTLAB_LM_GATEWAY_URL'], os.environ['AGENTLAB_MODEL'],
            route=os.environ['AGENTLAB_PROVIDER_ROUTE'],
            gateway_timeout_seconds=args.gateway_timeout_seconds,
            thinking_type=None if args.thinking_type == 'default' else args.thinking_type,
            response_format='json_object', api='openai-completions',
            max_output_tokens=args.max_output_tokens)
        policy = helpers.freeze_pi_retry_policy(output / 'participant-state', workspace, evidence,
                                                disable_compaction=True)
        wall_time = max(240, args.gateway_timeout_seconds + 60)
        intent = dict(schema=('agentlab.independent_source_design_review_intent.v1' if design_review
                              else 'agentlab.independent_source_suite_review_intent.v1'),
                      reviewRequestSha256=request_digest,
                      qualityRubricSha256=packet['rubricSha256' if design_review else 'qualityRubricSha256'],
                      promptSha256=hashlib.sha256(prompt.encode()).hexdigest(),
                      participantBudgetSeconds=participant.process_budget_seconds(wall_time),
                      transportRetryLimit=0,
                      automaticCompactionDisabled=True,
                      participantIdentity=dict(model=os.environ['AGENTLAB_MODEL'],
                                               providerRoute=os.environ['AGENTLAB_PROVIDER_ROUTE'],
                                               providerReasoningEffort=effort))
        if repair_enabled:
            if intent['participantBudgetSeconds'] != 420:
                raise ValueError('Native participant watchdog differs from declared repair policy')
            compact = json.dumps(review_policy, sort_keys=True, separators=(',', ':')).encode()
            intent['reviewRepairPolicySha256'] = hashlib.sha256(compact).hexdigest()
        with (evidence / 'review-intent.json').open('x') as stream:
            json.dump(intent, stream)
        helpers.require_pi_retry_policy(output / 'participant-state', workspace, policy)
        result = participant.turn(label, workspace, prompt=prompt,
                                  wall_time_limit_seconds=wall_time, tool_call_limit=1,
                                  transport_retry_limit=0, require_completed_tool_call=False,
                                  reasoning_effort=effort)
        helpers.require_pi_retry_policy(output / 'participant-state', workspace, policy)
        content = result.get('content') if isinstance(result, dict) else None
        if not isinstance(content, str) or not content.strip() or len(content.encode()) > 256 * 1024:
            raise ValueError('Missing or oversized original reviewer response')
        with (output / 'response.json').open('xb') as stream:
            stream.write(content.encode())  # No fences stripped, operator repairs or JSON rewriting.
        try:
            gate(args, '--verify-source-design-quality-review-completion' if design_review else
                 '--verify-source-suite-review-completion', output / 'validation.json',
                 '--review-response', str(output / 'response.json'),
                 '--evidence' if design_review else '--participant-evidence', str(evidence))
        except RuntimeError:
            if design_review:
                raise  # Native attempt preparation decides protocol eligibility.
            # Complete diagnostics are feedback, never a replacement acceptance gate.
            try:
                gate(args, '--diagnose-source-suite-review-citations', output / 'citation-diagnostic.json',
                     '--review-response', str(output / 'response.json'))
            except RuntimeError:
                pass  # Invalid JSON/identity retains the original rejection and both logs.
            raise
        validated = json.loads((output / 'validation.json').read_bytes())
        terminal.update(completed=True, recordedCompletionVerified=validated['recordedCompletionVerified'])
        terminal['decision' if design_review else 'verdict'] = validated['decision' if design_review else 'verdict']
        # Reject/unverified are completed feedback. No lesson extraction or writer here.
        return terminal
    except Exception as error:
        terminal.update(errorType=type(error).__name__, error=str(error))
        raise
    finally:
        with (output / 'transport-receipt.json').open('x') as stream:
            json.dump(terminal, stream, indent=2)
            stream.write('\n')


def run(args, participant_class=None):
    limit = getattr(args, 'review_repair_limit', 0)
    design_review = getattr(args, 'author_request', None) is not None
    if design_review:
        if (getattr(args, 'design', None) is None or getattr(args, 'source', None) is not None
                or getattr(args, 'source_git_checkout', None) is not None):
            raise ValueError('Design review requires paired original request/design, no suite lane')
    elif getattr(args, 'design', None) is not None or getattr(args, 'source', None) is None:
        raise ValueError('Select exactly one original design or suite review lane')
    if limit not in (0, 1):
        raise ValueError('Review repair limit must be zero or one')
    if limit and not design_review and getattr(args, 'source_git_checkout', None) is None:
        raise ValueError('Citation repair requires independently verified Git source')
    root = args.output.absolute()
    original_runtime_root = os.environ.get('AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT')
    coordinator = dict(schema=('agentlab.design_review_attempt_coordinator.v1' if design_review
                               else 'agentlab.review_attempt_coordinator.v1'), completed=False,
                       reviewRepairLimit=limit, maximumReviewerAttempts=1+limit,
                       totalParticipantBudgetSeconds=420*(1+limit), transportRetryLimit=0,
                       attempts=[], automaticPromotion=False, authorityWritePerformed=False,
                       qualified=False)
    try:
        if limit and original_runtime_root:
            os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'] = str(Path(original_runtime_root) / 'initial')
        coordinator['attempts'].append('initial')
        try:
            result = run_attempt(args, participant_class)
            selected = '.'
        except RuntimeError:
            if not limit:
                raise
            # Routing only; native preparation must recheck original complete
            # exchange/policy and compute eligible findings before any inference.
            if design_review:
                if not (root / 'response.json').is_file() or not (root / 'validation.json.stderr.log').is_file():
                    raise
            else:
                diagnostic_path = root / 'citation-diagnostic.json'
                if not diagnostic_path.is_file() or json.loads(diagnostic_path.read_bytes()).get('citationFindingCount', 0) == 0:
                    raise
            repaired = copy.copy(args)
            repaired.output = root / 'repair-attempt'
            repaired.repair_parent = root
            if original_runtime_root:
                os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'] = str(Path(original_runtime_root) / 'repair-1')
            coordinator['attempts'].append('repair-1')
            result = run_attempt(repaired, participant_class)
            selected = 'repair-attempt'
        coordinator.update(completed=True, selectedAttempt=selected,
                           recordedCompletionVerified=result['recordedCompletionVerified'])
        coordinator['decision' if design_review else 'verdict'] = result['decision' if design_review else 'verdict']
        return coordinator
    except Exception as error:
        coordinator.update(errorType=type(error).__name__, error=str(error))
        raise
    finally:
        if original_runtime_root is not None:
            os.environ['AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT'] = original_runtime_root
        else:
            os.environ.pop('AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT', None)
        # Only the fresh invocation owns this directory. Never replace receipts
        # when a second invocation finds an existing capture.
        if getattr(args, '_capture_created', False) and not (root / 'attempt-coordinator.json').exists():
            with (root / 'attempt-coordinator.json').open('x') as stream:
                json.dump(coordinator, stream, indent=2)
                stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    for name in ('rubric', 'output', 'gate', 'pi'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--author-request', type=Path)
    parser.add_argument('--design', type=Path)
    parser.add_argument('--source-git-checkout', type=Path)
    parser.add_argument('--review-repair-limit', type=int, choices=[0, 1], default=0)
    parser.add_argument('--reasoning-effort', choices=['default', 'none', 'low', 'medium', 'high', 'max'], default='default')
    parser.add_argument('--thinking-type', choices=['default', 'enabled', 'disabled'], default='disabled')
    parser.add_argument('--gateway-timeout-seconds', type=int, choices=[180, 240], default=240)
    parser.add_argument('--max-output-tokens', type=int, choices=[8192, 16384], default=16384)
    print(json.dumps(run(parser.parse_args())))


if __name__ == '__main__':
    main()
