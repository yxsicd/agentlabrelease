import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('knowledge-branch.py')


class KnowledgeHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.target, self.hub, self.work = [self.root / x for x in ['target.git', 'hub.git', 'work']]
        for repo in [self.target, self.hub]:
            self.git(self.root, 'init', '--bare', '--quiet', str(repo))
        self.git(self.root, 'init', '--quiet', str(self.work))
        self.git(self.work, 'config', 'user.name', 'Knowledge test')
        self.git(self.work, 'config', 'user.email', 'test@localhost')
        self.git(self.work, 'checkout', '--orphan', 'al-knowledge')
        self.b = {'schema':'agentlab.knowledge-branch.v1','targetId':'calendar','sources':[{'repository':str(self.target),'revision':'a'*40}],'target':{'repository':str(self.target),'branch':'al-knowledge'},'hub':{'repository':str(self.hub),'branch':'knowledge/targets/calendar'},'entrypoint':'AGENTS.md'}
        (self.work/'knowledge.json').write_text(json.dumps(self.b))
        (self.work/'AGENTS.md').write_text('Read skills; public material only.\n')
        self.commit('initial');self.expected_root=self.git(self.work,'rev-parse','HEAD')
        self.git(self.work, 'push', str(self.target), 'HEAD:refs/heads/al-knowledge')
        self.bind = self.root/'binding.json';self.bind.write_text(json.dumps(self.b));self.n=0
    def tearDown(self):self.tmp.cleanup()
    def git(self, repo, *args):
        p=subprocess.run(['git','-C',str(repo),*args],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr.decode());return p.stdout.decode().strip()
    def commit(self,msg):self.git(self.work,'add','AGENTS.md','knowledge.json');self.git(self.work,'commit','-qm',msg)
    def run_sync(self, origin='target', create=False):
        self.n+=1;r=self.root/('receipt%d.json'%self.n);cmd=[sys.executable,str(SCRIPT),'sync','--binding',str(self.bind),'--expected-root',self.expected_root,'--from',origin,'--receipt',str(r),'--allow-local']
        if create:cmd.append('--create-destination')
        p=subprocess.run(cmd,capture_output=True);return p,json.loads(r.read_text())
    def test_round_trip_same_commits_and_bytes(self):
        p,r=self.run_sync(create=True);self.assertEqual(p.returncode,0,p.stdout);self.assertTrue(r['exactCommitAndAllFilesVerified'])
        (self.work/'AGENTS.md').write_text('Improved on the hub.\n');self.commit('hub improvement');head=self.git(self.work,'rev-parse','HEAD');self.git(self.work,'push',str(self.hub),'HEAD:refs/heads/knowledge/targets/calendar')
        p,r=self.run_sync('hub');self.assertEqual(p.returncode,0,p.stdout);self.assertEqual(self.git(self.target,'rev-parse','al-knowledge'),head)
        p,r=self.run_sync('hub');self.assertEqual(r['pushAttempts'],0)
    def test_divergence_refuses_without_push(self):
        self.run_sync(create=True);old=self.git(self.work,'rev-parse','HEAD')
        (self.work/'AGENTS.md').write_text('target edit');self.commit('target');self.git(self.work,'push',str(self.target),'HEAD:refs/heads/al-knowledge')
        self.git(self.work,'checkout','--detach',old);(self.work/'AGENTS.md').write_text('hub edit');self.commit('hub');hub=self.git(self.work,'rev-parse','HEAD');self.git(self.work,'push',str(self.hub),'HEAD:refs/heads/knowledge/targets/calendar')
        p,r=self.run_sync();self.assertNotEqual(p.returncode,0);self.assertEqual(r['pushAttempts'],0);self.assertEqual(self.git(self.hub,'rev-parse','knowledge/targets/calendar'),hub)
    def test_business_ref_and_binding_drift_refused(self):
        b=dict(self.b);b['hub']={'repository':str(self.hub),'branch':'main'};self.bind.write_text(json.dumps(b));p,r=self.run_sync(create=True);self.assertNotEqual(p.returncode,0);self.assertEqual(r['pushAttempts'],0)
        self.bind.write_text(json.dumps(self.b));(self.work/'knowledge.json').write_text(json.dumps({**self.b,'sources':[{'repository':str(self.target),'revision':'b'*40}]}));self.commit('drift');self.git(self.work,'push',str(self.target),'HEAD:refs/heads/al-knowledge');p,r=self.run_sync(create=True);self.assertNotEqual(p.returncode,0);self.assertEqual(r['pushAttempts'],0)
    def test_wrong_root_refused_before_push(self):
        self.expected_root='f'*40
        p,r=self.run_sync(create=True);self.assertNotEqual(p.returncode,0);self.assertEqual(r['pushAttempts'],0)

    def test_actual_remote_rejection_has_one_push_and_retained_receipt(self):
        hook=self.hub/'hooks/pre-receive';count=self.root/'count';hook.write_text('#!/bin/sh\necho attempt >> "'+str(count)+'"\nexit 1\n');hook.chmod(0o755)
        p,r=self.run_sync(create=True);self.assertNotEqual(p.returncode,0);self.assertEqual(r['pushAttempts'],1);self.assertEqual(r['pushExitCode'],1);self.assertEqual(count.read_text().splitlines(),['attempt']);self.assertEqual(r['state'],'push_rejected_or_unconfirmed')


if __name__=='__main__':unittest.main()
