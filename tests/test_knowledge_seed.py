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
            self.assertEqual([e['passed'] for e in p['tables']['knowledge_evaluations']],[False,True,False,False])
            self.assertTrue(p['calibrated'])
            self.assertEqual({s['id'] for s in p['tables']['knowledge_skills']},{u['id'] for u in p['updates']})
            q=m.build(Path(temp)/'second')
            self.assertEqual([n['id'] for n in p['tables']['knowledge_nodes']],[n['id'] for n in q['tables']['knowledge_nodes']])
            self.assertTrue(all(e['resolution']=='syntactic_unresolved' for e in p['tables']['knowledge_edges']))

    def test_external_source_does_not_claim_calibrated_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'src';source.mkdir();(source/'example.py').write_text('def f():\n    return g()\n')
            p=m.build(Path(temp)/'run',source)
            self.assertFalse(p['calibrated']);self.assertEqual(p['tables']['knowledge_tasks'],[])
            self.assertEqual(p['tables']['knowledge_edges'][0]['targetName'],'g')

class AgentDraftTest(unittest.TestCase):
    def test_agent_proposal_preserves_operator_facts_and_ids(self):
        import copy
        spec=importlib.util.spec_from_file_location('agent_builder',Path(__file__).parents[1]/'examples/knowledge-seed/agent_builder.py')
        adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        with tempfile.TemporaryDirectory() as temp:
            package=m.build(Path(temp)/'run');facts=copy.deepcopy(package['tables'])
            proposal={'skills':[{'id':s['id'],'body':'Caller-aware maintainer workflow'} for s in facts['knowledge_skills']]}
            result=adapter.apply_draft(package,proposal)
            self.assertEqual(result['tables'],facts)
            self.assertFalse(result['semanticKnowledgeVerified'])
            self.assertTrue(all(u['fields']['body']=='Caller-aware maintainer workflow' for u in result['updates']))
            with self.assertRaises(ValueError): adapter.apply_draft(package,{'skills':[{'id':'invented','body':'x'}]})
