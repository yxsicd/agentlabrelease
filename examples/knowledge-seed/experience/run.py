"""Execute generic TableGit analysis, persist lessons, and export an explicit promotion candidate."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import store
sys.path.insert(0, str(REPO / 'examples/tablegit-session'))
from capture import Service

SQL = """SELECT json_extract(row_json,'$.id') AS tool_call_id,
json_extract(row_json,'$.runId') AS run_id,
json_extract(row_json,'$.phaseId') AS phase_id,
json_extract(row_json,'$.result') AS complete_result
FROM calls WHERE json_extract(row_json,'$.isError')=1
ORDER BY tool_call_id"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('development', 'instance', 'knowledge', 'binary', 'calibration', 'root'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--instance-prefix', required=True)
    p.add_argument('--lesson-prefix', required=True)
    p.add_argument('--knowledge-prefix', required=True)
    p.add_argument('--observation-kind', choices=['synthetic-tool-observation','real-source-campaign'],default='synthetic-tool-observation')
    a = p.parse_args()
    a.root.mkdir()
    rpc = a.root / 'rpc'
    rpc.mkdir()
    config = json.loads(a.development.read_text())
    s = Service(config['url'], Path(config['authorizationFile']).read_text().strip(), rpc)
    repo = config['repo']
    cut = s.call('table.worktree.open', dict(repo=repo, worktree={'topic_id': None}))['revision']
    request = dict(bindings=[dict(alias='calls', repo=repo, path=a.instance_prefix + 'tool_calls', revision=cut)], sql=SQL, parameters=[])
    result = s.call('table.relations.query', request)
    analysis = a.root / 'analysis.json'
    outcome_sql="SELECT json_extract(row_json,'$.id') AS check_id,json_extract(row_json,'$.phaseId') AS phase_id,json_extract(row_json,'$.check') AS check_name FROM checks WHERE json_extract(row_json,'$.passed')=0 ORDER BY check_id"
    outcome_request=dict(bindings=[dict(alias='checks',repo=repo,path=a.instance_prefix+'checks',revision=cut)],sql=outcome_sql,parameters=[])
    outcome_result=s.call('table.relations.query',outcome_request)
    analysis.write_text(json.dumps(dict(request=request,result=result,outcomeRequest=outcome_request,outcomeResult=outcome_result),indent=2)+'\n')

    def run(label, command):
        r = subprocess.run([str(x) for x in command], capture_output=True)
        (a.root / (label + '.stdout')).write_bytes(r.stdout)
        (a.root / (label + '.stderr')).write_bytes(r.stderr)
        if r.returncode:
            raise RuntimeError('Preserved experience failure: ' + label)

    exchange = a.root / 'instance-lessons'
    run('observe', [a.binary, 'observe', a.instance, analysis, a.calibration / 'calibration.json', exchange])
    importer = HERE.parent / 'subject/import-assets.py'
    receipts = []
    for number in (1, 2):
        evidence = a.root / ('import-' + str(number))
        command = [sys.executable, importer, '--development', a.development, '--directory', exchange, '--prefix', a.lesson_prefix, '--evidence', evidence]
        if number == 1:
            command.append('--create-tables')
        run('import-' + str(number), command)
        receipts.append(json.loads((evidence / 'receipt.json').read_text()))
    assert receipts[0]['revision'] == receipts[1]['revision'] and receipts[1]['insertedOrUpdatedRows'] == 0
    lessons = store.read(s, repo, receipts[1]['revision'], a.lesson_prefix + 'experiment_lessons')
    observations = [r for r in lessons.values() if r['kind'] == 'tool-error-observation']
    assert len(observations) == len(result['rows'])
    assert {r['toolCallId'] for r in observations} == {row[0]['value'] for row in result['rows']}
    failures=[r for r in lessons.values() if r['kind']=='assessed-check-failure']
    assert {r['checkId'] for r in failures}=={row[0]['value'] for row in outcome_result['rows']}
    # Read the durable lesson export before promoting, rather than using only local proposals.
    committed = a.root / 'committed-lessons'
    run('export-lessons', [sys.executable, HERE.parent / 'subject/finalize.py', '--development', a.development, '--directory', exchange, '--prefix', a.lesson_prefix, '--root', committed])
    calibration=json.loads((a.calibration/'calibration.json').read_text())
    verified_lesson_id=calibration['lesson']['id']
    candidate = a.root / 'promotion-candidate'
    run('promote', [a.binary, 'promote', committed, a.knowledge, candidate, verified_lesson_id])
    promotion_import = a.root / 'promotion-import'
    run('import-promotion', [sys.executable, importer, '--development', a.development, '--directory', candidate, '--prefix', a.knowledge_prefix, '--evidence', promotion_import, '--create-tables'])
    run('export-promotion', [sys.executable, HERE.parent / 'subject/finalize.py', '--development', a.development, '--directory', candidate, '--prefix', a.knowledge_prefix, '--root', a.root / 'promotion-export'])
    summary = dict(schema='agentlab.experience_campaign.v1', ok=True, analysisInputRevision=cut, lessonRevision=receipts[1]['revision'], observations=len(observations), failedCheckObservations=len(failures), verifiedLessonId=verified_lesson_id, unchangedRepeatedImport=True, promotionExplicit=True, promotionAppliedToActiveKnowledge=False, promotionSourceExport=json.loads((committed / 'export.json').read_text()), promotionExport=json.loads((a.root / 'promotion-export/export.json').read_text()), scope=calibration['lesson']['scope']+'; '+a.observation_kind, observationKind=a.observation_kind, qualificationAuthority='Instance runs/assessments carry actual Agent and build verdicts; this summary qualifies only committed lessons and explicit promotion', uiQualified=False)
    (a.root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
