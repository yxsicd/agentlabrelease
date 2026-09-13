import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('channel_plan', ROOT/'scripts/channel-plan.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class ChannelPlanTests(unittest.TestCase):
    def setUp(self):
        root=ROOT/'release/candidates/40ecdf4b-linux-x64'
        self.raw=(root/'environment-lock.json').read_bytes()
        self.lock=json.loads(self.raw)
        self.pub=json.loads((root/'publication.json').read_bytes())
    def upstream(self,tag):
        p=copy.deepcopy(self.pub);p.update(tag=tag,status='qualified',gates={'channel_tests':'passed'});return p
    def test_promotion_preserves_component_identity_and_freezes_inputs(self):
        dev=m.plan('aldev',self.pub,self.lock,self.raw)
        main=m.plan('almain',self.upstream('aldev'),self.lock,self.raw)
        prod=m.plan('alprod',self.upstream('almain'),self.lock,self.raw)
        self.assertEqual(dev['compositionIdentity'],main['compositionIdentity'])
        self.assertEqual(main['compositionIdentity'],prod['compositionIdentity'])
        self.lock['components'].clear()
        self.assertTrue(dev['environmentLock']['components'])
        self.assertFalse(prod['activated'])
    def test_no_channel_skipping(self):
        for target,p in [('almain',self.pub),('alprod',self.pub),('alprod',self.upstream('aldev'))]:
            with self.assertRaises(ValueError):m.plan(target,p,self.lock,self.raw)
    def test_changed_sdk_changes_release_identity(self):
        old=m.plan('almain',self.upstream('aldev'),self.lock,self.raw)
        pub=self.upstream('aldev');pub['sessionSdk']['sha256']='0'*64
        self.assertNotEqual(old['compositionIdentity'],m.plan('almain',pub,self.lock,self.raw)['compositionIdentity'])
    def test_failed_upstream_cannot_promote(self):
        pub=self.upstream('aldev');pub['gates']['channel_tests']='failed'
        with self.assertRaises(ValueError):m.plan('almain',pub,self.lock,self.raw)
    def test_coverage_increases_without_automatic_promotion(self):
        self.assertLess(set(m.CHECKS['aldev']),set(m.CHECKS['almain']))
        self.assertLess(set(m.CHECKS['almain']),set(m.CHECKS['alprod']))
        self.assertFalse(m.plan('aldev',self.pub,self.lock,self.raw)['automaticPromotion'])
