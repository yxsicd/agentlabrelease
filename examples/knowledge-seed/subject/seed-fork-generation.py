"""Summarize one control -> qualified candidate -> guided seed-fork generation without choosing a winner."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--current',type=Path,required=True)
p.add_argument('--comparison',type=Path,required=True)
p.add_argument('--baseline-run-id',required=True)
p.add_argument('--guided-run-id',required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()

baseline=json.loads(a.baseline.read_text())
current=json.loads(a.current.read_text())
comparison=json.loads(a.comparison.read_text())
assert baseline['schema']==current['schema']=='agentlab.harness_decision_package.v1'
assert comparison['schema']=='agentlab.harness_decision_comparison.v1'
assert baseline['scenario']==current['scenario']==comparison['scenario']
assert baseline['taskId']==current['taskId']==comparison['taskId']

guidance=current.get('seedGuidance')
if not guidance:
    state='control-only'
    actions=['design-next-experiment']
elif current.get('infrastructureAvailable') is False:
    state='blocked-by-infrastructure'
    actions=['rerun-guided','design-next-experiment']
elif comparison.get('comparable') is True:
    state='decision-ready'
    actions=['adopt-guidance','reject-guidance','rerun-guided','modify-guidance','design-next-experiment']
else:
    state='not-comparable'
    actions=['rerun-control','rerun-guided','design-next-experiment']

result=dict(
    schema='agentlab.seed_fork_generation.v1',
    scenario=current['scenario'],taskId=current['taskId'],sourceRevision=current.get('sourceRevision'),
    baselineRunId=a.baseline_run_id,guidedRunId=a.guided_run_id,
    qualificationRunId=(guidance or {}).get('sourceRunId'),captureRunId=(guidance or {}).get('captureRunId'),
    candidateDigest=(guidance or {}).get('candidateDigest'),verifiedLessonId=(guidance or {}).get('verifiedLessonId'),
    baselineAssessmentStatus=baseline.get('assessmentStatus','assessed'),
    guidedAssessmentStatus=current.get('assessmentStatus','assessed'),
    comparable=bool(comparison.get('comparable')),comparisonBlocker=comparison.get('comparisonBlocker'),
    generationState=state,decisionSummary=comparison.get('summary',{}),
    agentDecisionRequired=True,allowedAgentDecisions=actions,
    harnessDecision=None,
    policy='Harness records lineage, validity and deltas; an Agent decides whether to adopt, reject, modify or rerun the candidate.'
)
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(result,indent=2)+'\n')
