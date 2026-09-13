import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

def load(path):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class CampaignTests(unittest.TestCase):
    def test_swe_catalog_has_multiple_repositories_and_bound_baselines(self):
        catalog=json.loads((ROOT/'examples/swe-bench/catalog.json').read_text())
        self.assertEqual(len(catalog['cases']),4)
        self.assertEqual(len({r['repo'] for r in catalog['cases']}),3)
        self.assertTrue(all(len(r['baseCommit'])==40 and len(r['sourceRecordSha256'])==64 for r in catalog['cases']))

    def test_harmony_demands_reject_marker_only_edits_and_feature_loss(self):
        m=load(ROOT/'examples/harmony-build/scenarios.py')
        for name in ['counter','form']:
            base=m.render(name,0,'marker')
            self.assertFalse(m.verify(name,1,base)['passed'])
            self.assertTrue(m.verify(name,1,m.render(name,1,'marker'))['passed'])
            self.assertFalse(m.verify(name,2,m.render(name,1,'marker'))['passed'])
            self.assertTrue(m.verify(name,2,m.render(name,2,'marker'))['passed'])

    def test_harmony_source_contract_accepts_multiline_formatting(self):
        m=load(ROOT/'examples/harmony-build/scenarios.py')
        for name in ['counter','form']:
            source=m.render(name,2,'marker').replace('Button(', 'Button(\n ').replace('Text(', 'Text(\n ')
            self.assertTrue(m.verify(name,2,source)['passed'])

    def test_patch_includes_agent_commits_and_untracked_binary_without_index_changes(self):
        m=load(ROOT/'examples/swe-bench/workspace_patch.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);subject=root/'subject';subject.mkdir()
            def git(args,allow_diff=False):
                p=subprocess.run(['git','-C',str(subject)]+args,capture_output=True)
                if p.returncode not in ([0,1] if allow_diff else [0]):raise RuntimeError(p.stderr.decode())
                return p.stdout
            git(['init','-q']);git(['config','user.email','test@example.com']);git(['config','user.name','test'])
            (subject/'source.txt').write_text('before');git(['add','.']);git(['commit','-qm','base'])
            base=git(['rev-parse','HEAD']).decode().strip()
            (subject/'source.txt').write_text('after');git(['commit','-qam','participant commit'])
            (subject/'new.bin').write_bytes(bytes(range(256)))
            index_before=(subject/'.git/index').read_bytes()
            patch=m.capture_patch(git,base)
            self.assertEqual(index_before,(subject/'.git/index').read_bytes())
            restored=root/'restored'
            subprocess.run(['git','clone','-q',str(subject),str(restored)],check=True)
            subprocess.run(['git','-C',str(restored),'checkout','-q',base],check=True)
            subprocess.run(['git','-C',str(restored),'apply','--binary','-'],input=patch,check=True)
            self.assertEqual((restored/'source.txt').read_bytes(),b'after')
            self.assertEqual((restored/'new.bin').read_bytes(),bytes(range(256)))
