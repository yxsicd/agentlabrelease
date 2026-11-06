"""Operator-owned adapter: Harbor task, host mini-SWE-agent, scoped Gateway capture."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from harbor.agents.base import BaseAgent
from harbor.environments.docker.docker import DockerEnvironment, _sanitize_docker_compose_project_name


class HostMini(BaseAgent):
    @staticmethod
    def name(): return 'agentlab-host-mini-swe-agent'
    def version(self): return '2.4.6'

    async def setup(self, environment):
        if not isinstance(environment, DockerEnvironment):
            raise RuntimeError('Only the assigned Docker environment is supported')
        if not self.model_name or not self.model_name.startswith('openai/'):
            raise ValueError('Select an explicit openai-compatible model')
        self._model = self.model_name.removeprefix('openai/')
        if not self._model:
            raise ValueError('Model name must not be empty')
        budget = int(os.environ['AGENTLAB_TOKEN_BUDGET'])
        self._wall_seconds = int(os.environ['AGENTLAB_WALL_SECONDS'])
        if budget <= 0 or not 60 <= self._wall_seconds <= 86400:
            raise ValueError('Invalid token budget or wall-clock fallback')
        identity = await environment.exec("cat /etc/hostname; pwd", timeout_sec=15)
        lines = (identity.stdout or '').splitlines()
        if identity.return_code != 0 or len(lines) != 2 or not re.fullmatch('[a-f0-9]{12,64}', lines[0]) or not lines[1].startswith('/'):
            raise RuntimeError('Cannot bind the assigned task container and workdir')
        fmt='{{.Id}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{.Image}}'
        info = subprocess.check_output(['docker','inspect','--format',fmt,lines[0]],text=True,timeout=15).strip().split('|')
        expected_project = _sanitize_docker_compose_project_name(environment.session_id)
        expected_image = os.environ['AGENTLAB_EXPECTED_TASK_IMAGE_ID']
        if len(info) != 4 or not info[0].startswith(lines[0]) or info[1] != expected_project or info[2] != 'main' or info[3] != expected_image:
            raise RuntimeError('Assigned container identity, ownership or image differs')
        self._container, self._workdir = info[0], lines[1]
        root=Path(os.environ['AGENTLAB_ATTEMPT_ROOT'])
        evidence=root/'evidence'; evidence.mkdir(mode=0o700,exist_ok=False)
        source=Path(os.environ['AGENTLAB_WORKTREE'])/'examples/real-code-agent/participant.py'
        spec=importlib.util.spec_from_file_location('agentlab_operator_participant',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self._proxy=module.Participant(evidence,root/'state',os.environ['AGENTLAB_MINI_PYTHON'],
             os.environ['AGENTLAB_GATEWAY_URL'],self._model,route=os.environ['AGENTLAB_PROVIDER_ROUTE'],
             implementation='mini-swe-agent',token_budget=budget)
        try:
            probe=json.loads((evidence/'runtime-probe-stdout.log').read_text().splitlines()[-1])
            if probe.get('version') != self.version():
                raise RuntimeError('Installed mini-SWE-agent version differs from the pinned version')
        except Exception:
            self._proxy.close()
            raise
        self._root,self._evidence=root,evidence
        (root/'container-binding.json').write_text(json.dumps({'containerId':self._container,'composeProject':expected_project,
            'composeService':'main','imageId':info[3],'workdir':self._workdir},indent=2)+'\n')

    async def run(self, instruction, environment, context):
        error=None
        try:
            await asyncio.to_thread(self._proxy.turn,'terminal-task',self._root,prompt=instruction,
                container=self._container,container_workdir=self._workdir,step_limit=0,
                wall_time_limit_seconds=self._wall_seconds,transport_retry_limit=0)
        except Exception as exc:
            error={'type':type(exc).__name__,'message':str(exc)}
        finally:
            self._proxy.close()
            usage=self._proxy.token_usage.summarize(self._evidence/'gateway')
            (self._evidence/'usage-observation.json').write_text(json.dumps(usage,indent=2)+'\n')
            total=usage['totalsObserved']
            if usage['inputOutputComplete']:
                context.n_input_tokens=total['input'];context.n_output_tokens=total['output'];context.n_cache_tokens=total['cached_input']
            status={'error':error,'upstreamExchanges':usage['exchanges'],'usageComplete':usage['inputOutputComplete'],
                    'verifierMayRun':usage['exchanges']>0,'budgetDecision':None}
            decision=self._evidence/'token-budget-decision.json'
            if decision.exists(): status['budgetDecision']=json.loads(decision.read_text())
            (self._root/'participant-outcome.json').write_text(json.dumps(status,indent=2)+'\n')
        # No model dispatch is an operator failure, never a student verdict.
        if error and usage['exchanges']==0:
            raise RuntimeError('Participant failed before any captured model exchange')
