import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upgrade', ROOT/'scripts/component-upgrade.py')
upgrade = importlib.util.module_from_spec(spec); spec.loader.exec_module(upgrade)

class ComponentUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.base = upgrade.load(ROOT/'release/channels/aldev')
        self.donor = copy.deepcopy(self.base)
        sdk = self.donor[0]['sessionSdk']
        sdk['sourceRevision'] = 'a'*40
        sdk['artifact'] = sdk['artifact'].replace('c075105a','aaaaaaaa')
        self.donor[0]['assets'].append(dict(url=sdk['artifact'],bytes=sdk['bytes'],sha256=sdk['sha256']))

    def test_sdk_preserves_every_other_component_and_requires_new_qualification(self):
        pub, lock, raw, receipt = upgrade.compose(self.base,self.donor,'session-sdk','candidate-test')
        self.assertEqual(lock,self.base[1])
        self.assertEqual(pub['smoke'],self.base[0]['smoke'])
        self.assertEqual(pub['sourceRevision'],self.base[0]['sourceRevision'])
        self.assertTrue(all(value=='not_run' for value in pub['gates'].values()))
        self.assertNotIn('qualification',pub)
        self.assertFalse(pub['activated'])
        self.assertEqual(receipt['component'],'session-sdk')
        planner = upgrade.module('channel-plan')
        old = planner.plan('almain',*self.base, (ROOT/'release/channels/aldev/environment-lock.json').read_bytes())
        new = planner.plan('aldev',pub,lock,raw)
        self.assertNotEqual(old['compositionIdentity'],new['compositionIdentity'])

    def test_noop_is_not_a_release(self):
        with self.assertRaisesRegex(ValueError,'unchanged'):
            upgrade.compose(self.base,self.base,'session-sdk','candidate-test')

    def test_contract_change_does_not_silently_upgrade_other_components(self):
        donor = copy.deepcopy(self.base)
        donor[1]['components'][0]['version'] = 'new'
        donor[1]['componentGraph']['nodes'][1]['requires']['mcpgit.session-template-contract']['min'] = 12
        with self.assertRaisesRegex(ValueError,'unsatisfied contract'):
            upgrade.compose(self.base,donor,'pack:release','candidate-test')

    def test_real_published_sdk_upgrade_keeps_runtime_and_graph(self):
        base = upgrade.load(ROOT/'release/candidates/c22b7bfd-linux-x64')
        pub, lock, raw, receipt = upgrade.compose(base,self.base,'session-sdk','candidate-real-sdk')
        self.assertEqual(lock,base[1])
        self.assertEqual(pub['sessionSdk'],self.base[0]['sessionSdk'])
        self.assertEqual(pub['smoke'],base[0]['smoke'])

    def test_image_and_tools_preserve_runtime_and_sdk(self):
        for component,collection,index in [('image:runtime','images',0),('pack:tools','components',1)]:
            donor = copy.deepcopy(self.base)
            donor[1][collection][index]['version'] = 'new'
            if collection == 'images': donor[1][collection][index]['reference'] = 'new-image'
            binding = {'kind':'image-slot' if collection=='images' else 'pack-slot','slot':component.split(':')[1]}
            next(n for n in donor[1]['componentGraph']['nodes'] if n['binding']==binding)['version'] = 'new'
            pub,lock,_,_ = upgrade.compose(self.base,donor,component,'candidate-test')
            self.assertEqual(pub['sessionSdk'],self.base[0]['sessionSdk'])
            self.assertEqual(pub['sourceRevision'],self.base[0]['sourceRevision'])
            self.assertEqual(lock['sourceRevision'],self.base[1]['sourceRevision'])
