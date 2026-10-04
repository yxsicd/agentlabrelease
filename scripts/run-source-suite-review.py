#!/usr/bin/env python3
"""Thin isolated reviewer transport; all evidence/decision gates belong to Rust."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate(args, flag, output, *extra):
    command = [str(args.gate.resolve()), flag, '--source', str(args.source.resolve()),
               '--quality-rubric', str(args.rubric.resolve()), '--output', str(output), *extra]
    result = subprocess.run(command, capture_output=True, timeout=90)
    with output.with_suffix(output.suffix + '.stdout.log').open('xb') as stream:
        stream.write(result.stdout)
    with output.with_suffix(output.suffix + '.stderr.log').open('xb') as stream:
        stream.write(result.stderr)
    if result.returncode:
        raise RuntimeError(f'Native review gate {flag} rejected input; retained original stderr')


def run(args, participant_class=None):
    if not os.environ.get('AGENTLAB_PARTICIPANT_RUNTIME_CONFIG'):
        raise ValueError('Independent review requires the contained participant runtime')
    output = args.output.absolute()
    output.mkdir()  # Exclusive fresh capture, never resume the constructor session.
    evidence = output / 'evidence'
    workspace = output / 'workspace'
    evidence.mkdir()
    workspace.mkdir()
    terminal = dict(schema='agentlab.independent_source_suite_review_transport.v1',
                    completed=False, automaticPromotion=False, authorityWritePerformed=False,
                    qualified=False)
    try:
        gate(args, '--prepare-source-suite-review', output / 'request.json')
        gate(args, '--prepare-source-suite-review-prompt', output / 'prompt.txt')
        prompt = (output / 'prompt.txt').read_text()
        packet = json.loads((output / 'request.json').read_bytes())
        # Request digest is emitted by the native prompt, not reimplemented here.
        request_digest = prompt.split('reviewRequestSha256 is ', 1)[1].split('.', 1)[0]
        if len(request_digest) != 64 or any(c not in '0123456789abcdef' for c in request_digest):
            raise ValueError('Native review prompt digest absent')
        repo = Path(__file__).resolve().parents[1]
        helpers = load_module('source_author_transport', repo / 'scripts/run-source-recipe-author.py')
        helpers.prepare_runtime_receipt_root()
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
        policy = helpers.freeze_pi_retry_policy(output / 'participant-state', workspace, evidence)
        effort = None if args.reasoning_effort == 'default' else args.reasoning_effort
        wall_time = max(240, args.gateway_timeout_seconds + 60)
        intent = dict(schema='agentlab.independent_source_suite_review_intent.v1',
                      reviewRequestSha256=request_digest,
                      qualityRubricSha256=packet['qualityRubricSha256'],
                      promptSha256=hashlib.sha256(prompt.encode()).hexdigest(),
                      participantBudgetSeconds=participant.process_budget_seconds(wall_time),
                      transportRetryLimit=0,
                      participantIdentity=dict(model=os.environ['AGENTLAB_MODEL'],
                                               providerRoute=os.environ['AGENTLAB_PROVIDER_ROUTE'],
                                               providerReasoningEffort=effort))
        with (evidence / 'review-intent.json').open('x') as stream:
            json.dump(intent, stream)
        helpers.require_pi_retry_policy(output / 'participant-state', workspace, policy)
        result = participant.turn('source-suite-review', workspace, prompt=prompt,
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
            gate(args, '--verify-source-suite-review-completion', output / 'validation.json',
                 '--review-response', str(output / 'response.json'), '--participant-evidence', str(evidence))
        except RuntimeError:
            # Complete diagnostics are feedback, never a replacement acceptance gate.
            try:
                gate(args, '--diagnose-source-suite-review-citations', output / 'citation-diagnostic.json',
                     '--review-response', str(output / 'response.json'))
            except RuntimeError:
                pass  # Invalid JSON/identity retains the original rejection and both logs.
            raise
        validated = json.loads((output / 'validation.json').read_bytes())
        terminal.update(completed=True, verdict=validated['verdict'],
                        recordedCompletionVerified=validated['recordedCompletionVerified'])
        # Reject/unverified are completed feedback. No lesson extraction or writer here.
        return terminal
    except Exception as error:
        terminal.update(errorType=type(error).__name__, error=str(error))
        raise
    finally:
        with (output / 'transport-receipt.json').open('x') as stream:
            json.dump(terminal, stream, indent=2)
            stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    for name in ('source', 'rubric', 'output', 'gate', 'pi'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reasoning-effort', choices=['default', 'none', 'low', 'medium', 'high', 'max'], default='default')
    parser.add_argument('--thinking-type', choices=['default', 'enabled', 'disabled'], default='disabled')
    parser.add_argument('--gateway-timeout-seconds', type=int, choices=[180, 240], default=240)
    parser.add_argument('--max-output-tokens', type=int, choices=[8192, 16384], default=16384)
    print(json.dumps(run(parser.parse_args())))


if __name__ == '__main__':
    main()
