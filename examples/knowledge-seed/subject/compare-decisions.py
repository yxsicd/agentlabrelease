"""Compare two Harness decision packages without choosing a winner."""
import json
import sys
from pathlib import Path

baseline_path, current_path, output_path = map(Path, sys.argv[1:4])
baseline = json.loads(baseline_path.read_text())
current = json.loads(current_path.read_text())
assert baseline['schema'] == current['schema'] == 'agentlab.harness_decision_package.v1'
assert baseline['scenario'] == current['scenario']
assert baseline['taskId'] == current['taskId']
infrastructure_comparable = baseline.get('infrastructureAvailable', True) is True and current.get('infrastructureAvailable', True) is True and baseline.get('assessmentStatus','assessed') == current.get('assessmentStatus','assessed') == 'assessed'

def phases(package):
    return {row['phase']: row for row in package['phaseVerdicts']}

def count(package, key, value=True):
    return sum(row.get(key) is value for row in package['phaseVerdicts'])

def first_compile(package):
    return package.get('buildTiming', {}).get('firstCompileStartMs')

def process(package):
    return {row['phase']: row for row in package.get('participantProcess', [])}

def blocking_launch_error_phases(package):
    """Return only infrastructure/transport launch failures.

    A Participant budget timeout is an assessed outcome and is intentionally
    comparable: reducing a timeout is one of the effects a seed candidate may
    legitimately demonstrate.  Transport/gateway failures are not model/seed
    outcomes and therefore block phase comparison.
    """
    tokens=('frp','http 404','404 <!doctype','502','gateway exchange failed','gateway readiness failed')
    blocked=set()
    for row in package.get('launchErrors', []):
        phase=row.get('phase'); error=str(row.get('error','')).lower()
        if phase and (phase=='gateway-preflight' or any(token in error for token in tokens)):
            blocked.add(phase)
    return blocked

def duration(row):
    return row.get('effectiveDurationMs', row.get('durationMs'))

def event_bytes(row):
    return row.get('effectiveRawEventBytes', row.get('rawEventBytes'))

bph, cph = phases(baseline), phases(current)
bproc, cproc = process(baseline), process(current)
berr, cerr = blocking_launch_error_phases(baseline), blocking_launch_error_phases(current)
phase_delta = []
for name in sorted(set(bph) | set(cph)):
    before, after = bph.get(name, {}), cph.get(name, {})
    before_process, after_process = bproc.get(name, {}), cproc.get(name, {})
    phase_delta.append(dict(
        phase=name,
        comparable=(infrastructure_comparable and name not in berr and name not in cerr and bool(before) and bool(after)),
        comparisonBlocker=(None if infrastructure_comparable and name not in berr and name not in cerr and bool(before) and bool(after) else 'Phase missing or has an infrastructure/transport launch error in at least one run.'),
        behaviorPassBefore=before.get('behaviorPass'), behaviorPassAfter=after.get('behaviorPass'),
        buildPassBefore=before.get('buildPass'), buildPassAfter=after.get('buildPass'),
        scopeDriftBefore=before.get('scopeDrift'), scopeDriftAfter=after.get('scopeDrift'),
        extraPathsBefore=before.get('extraPaths', []), extraPathsAfter=after.get('extraPaths', []),
        participantDurationMsBefore=duration(before_process), participantDurationMsAfter=duration(after_process),
        completedToolCallsBefore=before_process.get('completedToolCalls'), completedToolCallsAfter=after_process.get('completedToolCalls'),
        timedOutBefore=before_process.get('timedOut'), timedOutAfter=after_process.get('timedOut'),
        transportRetryCountBefore=before_process.get('transportRetryCount', 0), transportRetryCountAfter=after_process.get('transportRetryCount', 0),
        firstSourceMutationMsBefore=before_process.get('firstSourceMutationMs'), firstSourceMutationMsAfter=after_process.get('firstSourceMutationMs'),
        rawEventBytesBefore=event_bytes(before_process), rawEventBytesAfter=event_bytes(after_process)))

comparable_phase_count=sum(row['comparable'] for row in phase_delta)
comparable = infrastructure_comparable and comparable_phase_count == len(phase_delta) and len(phase_delta) > 0

bf, cf = first_compile(baseline), first_compile(current)
duration_before = sum(duration(row) or 0 for row in bproc.values())
duration_after = sum(duration(row) or 0 for row in cproc.values())
tools_before = sum(row.get('completedToolCalls') or 0 for row in bproc.values())
tools_after = sum(row.get('completedToolCalls') or 0 for row in cproc.values())
events_before = sum(event_bytes(row) or 0 for row in bproc.values())
events_after = sum(event_bytes(row) or 0 for row in cproc.values())
retries_before = sum(row.get('transportRetryCount') or 0 for row in bproc.values())
retries_after = sum(row.get('transportRetryCount') or 0 for row in cproc.values())
summary = dict(
    behaviorPassCountBefore=count(baseline, 'behaviorPass'), behaviorPassCountAfter=count(current, 'behaviorPass'),
    buildPassCountBefore=count(baseline, 'buildPass'), buildPassCountAfter=count(current, 'buildPass'),
    scopeDriftCountBefore=count(baseline, 'scopeDrift'), scopeDriftCountAfter=count(current, 'scopeDrift'),
    launchErrorCountBefore=len(baseline.get('launchErrors', [])), launchErrorCountAfter=len(current.get('launchErrors', [])),
    timeoutCountBefore=sum(row.get('timedOut') is True for row in bproc.values()), timeoutCountAfter=sum(row.get('timedOut') is True for row in cproc.values()),
    transportRetryCountBefore=retries_before, transportRetryCountAfter=retries_after, transportRetryCountDelta=retries_after-retries_before,
    participantDurationMsBefore=duration_before, participantDurationMsAfter=duration_after, participantDurationMsDelta=duration_after-duration_before,
    completedToolCallsBefore=tools_before, completedToolCallsAfter=tools_after, completedToolCallsDelta=tools_after-tools_before,
    rawEventBytesBefore=events_before, rawEventBytesAfter=events_after, rawEventBytesDelta=events_after-events_before,
    comparablePhaseCount=comparable_phase_count,totalPhaseCount=len(phase_delta),
    firstCompileStartMsBefore=bf, firstCompileStartMsAfter=cf,
    firstCompileStartMsDelta=(cf-bf if isinstance(bf, int) and isinstance(cf, int) else None))

result = dict(
    schema='agentlab.harness_decision_comparison.v1', scenario=current['scenario'], taskId=current['taskId'],
    baselineSeedGuidance=baseline.get('seedGuidance'), currentSeedGuidance=current.get('seedGuidance'),
    baselineReasoningPolicy=baseline.get('reasoningPolicy'), currentReasoningPolicy=current.get('reasoningPolicy'),
    baselineEvidenceTriggeredEscalation=baseline.get('evidenceTriggeredEscalation'), currentEvidenceTriggeredEscalation=current.get('evidenceTriggeredEscalation'),
    summary=summary, phaseDelta=phase_delta, comparable=comparable,
    comparisonBlocker=(None if comparable else ('At least one run was not an assessed, infrastructure-available Participant experiment.' if not infrastructure_comparable else 'At least one phase is missing or has an infrastructure/transport launch error; whole-generation comparison is not valid.')),
    interpretationPolicy='Deltas are evidence, not causal attribution. Do not interpret outcome/performance deltas when comparable=false. Runner/model variance and prompt guidance may confound results.',
    agentDecisionRequired=True,
    allowedDecisions=(['adopt-guidance','reject-guidance','rerun-control','rerun-guided','modify-guidance','design-next-experiment'] if comparable else ['rerun-control','rerun-guided','design-next-experiment']))
output_path.write_text(json.dumps(result, indent=2) + '\n')
