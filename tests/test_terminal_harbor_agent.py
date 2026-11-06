import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]
HARBOR_AVAILABLE=importlib.util.find_spec('harbor') is not None
if HARBOR_AVAILABLE:
    spec=importlib.util.spec_from_file_location('terminal_harbor_adapter',ROOT/'examples/terminal-bench/harbor_agent.py')
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)


@unittest.skipUnless(HARBOR_AVAILABLE,'Harbor runtime is optional')
class HarborAgentTest(unittest.TestCase):
    def environment(self):
        env=MagicMock(spec=adapter.DockerEnvironment)
        env.session_id='fix-git__abc__env'
        env.exec=AsyncMock(return_value=SimpleNamespace(stdout='aaaaaaaaaaaa\n/app/personal-site\n',return_code=0))
        return env

    def variables(self, root):
        return {'AGENTLAB_EXPECTED_TASK_IMAGE_ID':'sha256:image','AGENTLAB_ATTEMPT_ROOT':str(root),
                'AGENTLAB_WORKTREE':str(ROOT),'AGENTLAB_MINI_PYTHON':'/tmp/python',
                'AGENTLAB_GATEWAY_URL':'http://127.0.0.1:1','AGENTLAB_PROVIDER_ROUTE':'glm',
                'AGENTLAB_TOKEN_BUDGET':'500000','AGENTLAB_WALL_SECONDS':'1800'}

    def test_rejects_container_owned_by_another_project(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,self.variables(Path(tmp))):
            agent=adapter.HostMini(logs_dir=Path(tmp),model_name='openai/glm-5.3-flash')
            with patch.object(adapter.subprocess,'check_output',return_value='a'*64+'|other-project|main|sha256:image\n'):
                with self.assertRaisesRegex(RuntimeError,'ownership'):
                    asyncio.run(agent.setup(self.environment()))
            self.assertFalse((Path(tmp)/'evidence').exists())

    def test_passes_actual_container_and_workdir_to_operator(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,self.variables(Path(tmp))):
            agent=adapter.HostMini(logs_dir=Path(tmp),model_name='openai/glm-5.3-flash')
            usage={'exchanges':1,'inputOutputComplete':True,'totalsObserved':{'input':4,'output':2,'cached_input':1}}
            proxy=MagicMock();proxy.token_usage.summarize.return_value=usage
            def participant(evidence,*args,**kwargs):
                (evidence/'runtime-probe-stdout.log').write_text('{"version":"2.4.6"}\n')
                return proxy
            module=SimpleNamespace(Participant=MagicMock(side_effect=participant))
            fake_spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
            result='a'*64+'|fix-git__abc__env|main|sha256:image\n'
            with patch.object(adapter.subprocess,'check_output',return_value=result), \
                 patch.object(adapter.importlib.util,'spec_from_file_location',return_value=fake_spec), \
                 patch.object(adapter.importlib.util,'module_from_spec',return_value=module):
                env=self.environment();asyncio.run(agent.setup(env));context=SimpleNamespace()
                asyncio.run(agent.run('fixture instruction',env,context))
            kwargs=proxy.turn.call_args.kwargs
            self.assertEqual(module.Participant.call_args.args[4],'glm-5.3-flash')
            self.assertEqual(module.Participant.call_args.kwargs['route'],'glm')
            self.assertEqual(module.Participant.call_args.kwargs['token_budget'],500000)
            self.assertEqual(kwargs['container'],'a'*64);self.assertEqual(kwargs['container_workdir'],'/app/personal-site')
            self.assertEqual(kwargs['transport_retry_limit'],0);self.assertEqual(kwargs['step_limit'],0)
            self.assertEqual((context.n_input_tokens,context.n_output_tokens,context.n_cache_tokens),(4,2,1))
            self.assertIsNone(json.loads((Path(tmp)/'participant-outcome.json').read_text())['error'])

    def test_wrong_agent_version_closes_proxy_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,self.variables(Path(tmp))):
            agent=adapter.HostMini(logs_dir=Path(tmp),model_name='openai/glm-5.3-flash')
            proxy=MagicMock()
            def participant(evidence,*args,**kwargs):
                (evidence/'runtime-probe-stdout.log').write_text('{"version":"1.0.0"}\n')
                return proxy
            module=SimpleNamespace(Participant=MagicMock(side_effect=participant))
            fake_spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
            result='a'*64+'|fix-git__abc__env|main|sha256:image\n'
            with patch.object(adapter.subprocess,'check_output',return_value=result), \
                 patch.object(adapter.importlib.util,'spec_from_file_location',return_value=fake_spec), \
                 patch.object(adapter.importlib.util,'module_from_spec',return_value=module):
                with self.assertRaisesRegex(RuntimeError,'version differs'):
                    asyncio.run(agent.setup(self.environment()))
            proxy.close.assert_called_once()
            self.assertFalse((Path(tmp)/'container-binding.json').exists())


if __name__=='__main__': unittest.main()
