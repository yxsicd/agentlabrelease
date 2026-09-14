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

def phases(package):
    return {row['phase']: row for row in package['phaseVerdicts']}

def count(package, key, value=True):
    return sum(row.get(key) is value for row in package['phaseVerdicts'])

def first_compile(package):
    return package.get('buildTiming', {}).get('firstCompileStartMs')

def process(package):
    return {row['phase']: row for row in package.get('participantProcess', [])}

bph, cph = phases(baseline), phases(current)
bproc, cproc = process(baseline), process(current)
phase_delta = []
for name in sorted(set(bph) | set(cph)):
    before, after = bph.get(name, {}), cph.get(name, {})
    before_process, after_process = bproc.get(name, {}), cproc.get(name, {})
    phase_delta.append(dict(
        phase=name,
        behaviorPassBefore=before.get('behaviorPass'), behaviorPassAfter=after.get('behaviorPass'),
        buildPassBefore=before.get('buildPass'), buildPassAfter=after.get('buildPass'),
        scopeDriftBefore=before.get('scopeDrift'), scopeDriftAfter=after.get('scopeDrift'),
        extraPathsBefore=before.get('extraPaths', []), extraPathsAfter=after.get('extraPaths', []),
        participantDurationMsBefore=before_process.get('durationMs'), participantDurationMsAfter=after_process.get('durationMs'),
        completedToolCallsBefore=before_process.get('completedToolCalls'), completedToolCallsAfter=after_process.get('completedToolCalls'),
        timedOutBefore=before_process.get('timedOut'), timedOutAfter=after_process.get('timedOut'),
        firstSourceMutationMsBefore=before_process.get('firstSourceMutationMs'), firstSourceMutationMsAfter=after_process.get('firstSourceMutationMs'),
        rawEventBytesBefore=before_process.get('rawEventBytes'), rawEventBytesAfter=after_process.get('rawEventBytes')))

bf, cf = first_compile(baseline), first_compile(current)
duration_before = sum(row.get('durationMs') or 0 for row in bproc.values())
duration_after = sum(row.get('durationMs') or 0 for row in cproc.values())
tools_before = sum(row.get('completedToolCalls') or 0 for row in bproc.values())
tools_after = sum(row.get('completedToolCalls') or 0 for row in cproc.values())
events_before = sum(row.get('rawEventBytes') or 0 for row in bproc.values())
events_after = sum(row.get('rawEventBytes') or 0 for row in cproc.values())
summary = dict(
    behaviorPassCountBefore=count(baseline, 'behaviorPass'), behaviorPassCountAfter=count(current, 'behaviorPass'),
    buildPassCountBefore=count(baseline, 'buildPass'), buildPassCountAfter=count(current, 'buildPass'),
    scopeDriftCountBefore=count(baseline, 'scopeDrift'), scopeDriftCountAfter=count(current, 'scopeDrift'),
    launchErrorCountBefore=len(baseline.get('launchErrors', [])), launchErrorCountAfter=len(current.get('launchErrors', [])),
    timeoutCountBefore=sum(row.get('timedOut') is True for row in bproc.values()), timeoutCountAfter=sum(row.get('timedOut') is True for row in cproc.values()),
    participantDurationMsBefore=duration_before, participantDurationMsAfter=duration_after, participantDurationMsDelta=duration_after-duration_before,
    completedToolCallsBefore=tools_before, completedToolCallsAfter=tools_after, completedToolCallsDelta=tools_after-tools_before,
    rawEventBytesBefore=events_before, rawEventBytesAfter=events_after, rawEventBytesDelta=events_after-events_before,
    firstCompileStartMsBefore=bf, firstCompileStartMsAfter=cf,
    firstCompileStartMsDelta=(cf-bf if isinstance(bf, int) and isinstance(cf, int) else None))

result = dict(
    schema='agentlab.harness_decision_comparison.v1', scenario=current['scenario'], taskId=current['taskId'],
    baselineSeedGuidance=baseline.get('seedGuidance'), currentSeedGuidance=current.get('seedGuidance'),
    summary=summary, phaseDelta=phase_delta,
    interpretationPolicy='Deltas are evidence, not causal attribution. Runner/model variance and prompt guidance may confound results.',
    agentDecisionRequired=True,
    allowedDecisions=['adopt-guidance','reject-guidance','rerun-control','rerun-guided','modify-guidance','design-next-experiment'])
output_path.write_text(json.dumps(result, indent=2) + '\n')
