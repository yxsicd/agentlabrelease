import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('knowledge_seed',Path(__file__).parents[1]/'examples/knowledge-seed/run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class KnowledgeSeedTest(unittest.TestCase):
    def test_calibration_rejects_boundary_and_history_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            p=m.build(Path(temp)/'first')
            self.assertEqual([e['passed'] for e in [r for r in p['tables']['evaluation_cases'] if r['kind']=='calibration']],[False,True,False,False])
            self.assertTrue(p['calibrated'])
            self.assertEqual({s['id'] for s in p['tables']['maintainer_skills']},{u['id'] for u in p['updates']})
            q=m.build(Path(temp)/'second')
            self.assertEqual([n['id'] for n in [r for r in p['tables']['program_facts'] if r['kind']=='symbol']],[n['id'] for n in [r for r in q['tables']['program_facts'] if r['kind']=='symbol']])
            self.assertTrue(all(e['resolution']=='syntactic_unresolved' for e in [r for r in p['tables']['program_facts'] if r['kind']=='call']))

    def test_external_source_does_not_claim_calibrated_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'src';source.mkdir();(source/'example.py').write_text('def f():\n    return g()\n')
            p=m.build(Path(temp)/'run',source)
            self.assertFalse(p['calibrated']);self.assertEqual([r for r in p['tables']['evaluation_cases'] if r['kind']=='task'],[])
            self.assertEqual([r for r in p['tables']['program_facts'] if r['kind']=='call'][0]['targetName'],'g')

class AgentDraftTest(unittest.TestCase):
    def test_agent_proposal_preserves_operator_facts_and_ids(self):
        import copy
        spec=importlib.util.spec_from_file_location('agent_builder',Path(__file__).parents[1]/'examples/knowledge-seed/agent_builder.py')
        adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        with tempfile.TemporaryDirectory() as temp:
            package=m.build(Path(temp)/'run');facts=copy.deepcopy(package['tables'])
            proposal={'skills':[{'id':s['id'],'body':'Caller-aware maintainer workflow'} for s in facts['maintainer_skills']]}
            result=adapter.apply_draft(package,proposal)
            self.assertEqual(result['tables'],facts)
            self.assertFalse(result['semanticKnowledgeVerified'])
            self.assertTrue(all(u['fields']['body']=='Caller-aware maintainer workflow' for u in result['updates']))
            with self.assertRaises(ValueError): adapter.apply_draft(package,{'skills':[{'id':'invented','body':'x'}]})

store_spec=importlib.util.spec_from_file_location('knowledge_store',Path(__file__).parents[1]/'examples/knowledge-seed/store.py')
store=importlib.util.module_from_spec(store_spec);store_spec.loader.exec_module(store)

class SnapshotTest(unittest.TestCase):
    def test_paging_stays_at_one_revision(self):
        class Pages:
            def call(self,method,payload):
                self_revision=payload['view']['revision']
                offset=payload['offset']
                return {'revision':self_revision,'dirty':False,'truncated':offset==0,'rows':[{'key':str(offset),'row':{'id':str(offset)},'deleted':False,'row_version':4}]}
        self.assertEqual(set(store.read(Pages(),'repo','cut','table')),{'0','1'})

    def test_snapshot_reimport_uses_actual_versions_and_skips_equal_rows(self):
        class Rows:
            def __init__(self,tables): self.tables=tables;self.operations=[]
            def call(self,method,payload):
                if method=='table.worktree.open': return {'revision':'cut'}
                if method=='table.query':return {'revision':'cut','dirty':False,'truncated':False,'rows':[{'key':k,'row':row,'deleted':False,'row_version':9} for k,row in self.tables[payload['path']].items()]}
                if method=='table.transact_many':
                    self.operations.extend(payload['tables']);return {'applied':True,'conflicts':[],'revision':'new-cut'}
                raise AssertionError(method)
        with tempfile.TemporaryDirectory() as temp:
            tables={t:{'x':{'id':'x','body':'new'}} for t in store.TABLES}
            source=Rows(tables);store.export(source,'repo','cut',temp)
            same=Rows(tables);self.assertEqual(store.import_snapshot(same,'repo',{},temp),('cut',0));self.assertFalse(same.operations)
            different={t:dict(rows) for t,rows in tables.items()};different['maintainer_skills']={'x':{'id':'x','body':'old'}};different['program_facts']['obsolete']={'id':'obsolete'}
            target=Rows(different);self.assertEqual(store.import_snapshot(target,'repo',{},temp),('new-cut',2))
            ops=[op for group in target.operations for op in group['operations']]
            self.assertEqual({op['op'] for op in ops},{'update','delete'});self.assertTrue(all(op['expected_row_version']==9 for op in ops))
