import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'scripts'/('channel-'+name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
planner=module('plan');qualifier=module('qualify');promoter=module('promotion');activation=module('activate')
spec=importlib.util.spec_from_file_location('composition', ROOT/'scripts/validate-composition-release.py')
composition=importlib.util.module_from_spec(spec);spec.loader.exec_module(composition)

class ChannelPromotionTests(unittest.TestCase):
    def setUp(self):
        source=ROOT/'release/candidates/40ecdf4b-linux-x64'
        self.raw=(source/'environment-lock.json').read_bytes()
        self.publication=json.loads((source/'publication.json').read_text())
        self.plan=planner.plan('aldev',self.publication,json.loads(self.raw),self.raw)
        self.baseline=dict(targetChannel='aldev', compositionIdentity=self.plan['compositionIdentity'],
                           sourceLockSha256=self.plan['sourceLockSha256'], githubRunId='12345', producerRevision='test',
                           checks={c:dict(status='passed') for c in self.plan['requiredChecks']})
    def test_same_bytes_through_qualified_upstream(self):
        qualification=qualifier.qualify(self.plan,self.baseline)
        tag,pub=promoter.prepare(self.plan,qualification,self.raw,'yxsicd/agentlabrelease')
        self.assertEqual(tag,'qualified-aldev-12345')
        self.assertEqual(pub['assets'],self.publication['assets'])
        self.assertEqual(pub['deploymentGates'],self.publication['gates'])
        main=planner.plan('almain',pub,json.loads(self.raw),self.raw)
        self.assertEqual(main['compositionIdentity'],self.plan['compositionIdentity'])
        self.assertFalse(pub['activated'])
        self.assertIn(tag,pub['environmentLockUrl'])
        composition.validate(pub,json.loads(self.raw),self.raw)
    def test_incomplete_or_other_composition_never_qualifies(self):
        self.baseline['checks'].pop('tablegit_recovery')
        qualification=qualifier.qualify(self.plan,self.baseline)
        self.assertFalse(qualification['qualified'])
        with self.assertRaises(ValueError):promoter.prepare(self.plan,qualification,self.raw,'owner/repo')
        self.baseline['compositionIdentity']='another'
        with self.assertRaises(ValueError):qualifier.qualify(self.plan,self.baseline)
    def test_prod_requires_same_plan_real_receipt(self):
        plan=copy.deepcopy(self.plan);plan['requiredChecks']+=['real_agent']
        self.assertFalse(qualifier.qualify(plan,self.baseline)['qualified'])
        real={k:self.baseline[k] for k in ['targetChannel','compositionIdentity','sourceLockSha256']}
        real.update(status='passed',check='real_agent')
        self.assertTrue(qualifier.qualify(plan,self.baseline,real)['qualified'])
        real['targetChannel']='alprod'
        with self.assertRaises(ValueError):qualifier.qualify(plan,self.baseline,real)
    def test_fixed_gate_preserved_without_full_whitebox_requirement(self):
        pub=promoter.prepare(self.plan,qualifier.qualify(self.plan,self.baseline),self.raw,'owner/repo')[1]
        with self.assertRaisesRegex(ValueError,'formalHarmony'):activation.pointer(pub)
        pub['deploymentGates'].update(dActivation='passed',formalHarmonyHapRestartParity='passed',aBCPromotion='passed')
        self.assertTrue(activation.pointer(pub)['activated'])
        self.assertEqual(pub['deploymentGates']['fullWhiteboxCoverage'],'not_run')

    def test_validation_dependencies_follow_selected_upstream_cut(self):
        dependencies={'standaloneHarmony':{'artifact':'fixed-url','sha256':'old-hash'}}
        plan=planner.plan('aldev',self.publication,json.loads(self.raw),self.raw,dependencies)
        baseline=copy.deepcopy(self.baseline)
        baseline['validationDependenciesSha256']=plan['validationDependenciesSha256']
        qualification=qualifier.qualify(plan,baseline)
        pub=promoter.prepare(plan,qualification,self.raw,'owner/repo')[1]
        main=planner.plan('almain',pub,json.loads(self.raw),self.raw)
        self.assertEqual(main['validationDependencies'],plan['validationDependencies'])
        dependencies['standaloneHarmony']['sha256']='new-hash'
        self.assertEqual(main['validationDependencies']['standaloneHarmony']['sha256'],'old-hash')
        baseline['validationDependenciesSha256']='different'
        with self.assertRaises(ValueError):qualifier.qualify(plan,baseline)
