#!/usr/bin/env python3
"""Thin mini-SWE-agent adapter. The parent Harness owns Gateway capture and verdicts."""
import argparse
import contextlib
import sys
import json
import shlex
from pathlib import Path
EVENT_STREAM=sys.stdout
with contextlib.redirect_stdout(sys.stderr):
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.litellm_model import LitellmModel


def emit(value):
    print(json.dumps(value),file=EVENT_STREAM,flush=True)


def bounded_integer(name, minimum, maximum):
    def parse(value):
        parsed = int(value)
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f'{name} must be between {minimum} and {maximum}'
            )
        return parsed
    return parse


class RecordedEnvironment(LocalEnvironment):
    container = None
    def execute(self, action, **kwargs):
        emit({'type':'tool_execution_start','implementation':'mini-swe-agent','action':action})
        try:
            executed = action
            if self.container:
                executed = dict(action,command=shlex.join(['docker','exec','-w','/testbed',self.container,'bash','-lc',action['command']]))
                emit({'type':'adapter_execution','actualAction':executed})
            result = super().execute(executed, **kwargs)
        except Exception as error:
            emit({'type':'tool_execution_end','implementation':'mini-swe-agent',
                  'action':action,'exceptionClass':type(error).__name__,'exception':str(error)})
            raise
        emit({'type':'tool_execution_end','implementation':'mini-swe-agent','action':action,'result':result})
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--trajectory',type=Path,required=True)
    parser.add_argument('--container')
    parser.add_argument('--step-limit',type=bounded_integer('step limit',1,50),default=30)
    parser.add_argument('--wall-time-limit-seconds',
                        type=bounded_integer('wall time limit',60,1200),default=360)
    parser.add_argument('prompt')
    args=parser.parse_args()
    model=LitellmModel(model_name='openai/'+args.model,cost_tracking='ignore_errors',
                      model_kwargs={'api_base':args.base_url,'api_key':'agentlab-local-test-credential',
                                    'temperature':0,'max_tokens':8192,'timeout':180})
    env=RecordedEnvironment(cwd=str(Path.cwd()),timeout=60)
    env.container=args.container
    agent=DefaultAgent(model,env,
        system_template='You are a coding agent. Use the bash tool to inspect and edit the project. '
                        'After completing the task, use bash to run: '
                        'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT. Do not only describe edits.',
        instance_template='{{task}}',step_limit=args.step_limit,cost_limit=0,
        wall_time_limit_seconds=args.wall_time_limit_seconds,output_path=args.trajectory)
    with contextlib.redirect_stdout(sys.stderr):
        result=agent.run(args.prompt)
    emit({'type':'participant_exit','implementation':'mini-swe-agent','result':result})
    if result.get('exit_status')!='Submitted':
        raise RuntimeError('mini-SWE-agent did not submit: '+str(result))


if __name__=='__main__': main()
