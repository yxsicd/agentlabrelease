#!/usr/bin/env python3
"""Replaceable builder participant; Harness binds proposals to source facts."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil


def apply_draft(package,draft):
    known={s['id']:s for s in package['tables']['maintainer_skills']}
    proposals=draft['skills']
    if set(s['id'] for s in proposals)!=set(known) or len(proposals)!=len(known):
        raise ValueError('Builder must address the frozen source-bound Skill identities')
    for s in proposals:
        if not isinstance(s['body'],str) or not s['body'].strip(): raise ValueError('Missing maintainer knowledge')
    for update in package['updates']:
        update['fields']['body']=next(s['body'] for s in proposals if s['id']==update['id'])
        update['fields']['status']='agent_draft'
    package['builder']='mini-swe-agent'
    package['builderRole']='benchmark_builder'
    package['semanticKnowledgeVerified']=False
    return package


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--agent-python',type=Path,required=True);p.add_argument('--gateway',required=True);p.add_argument('--model',default='glm-5.3-flash');a=p.parse_args()
    evidence=a.root/'evidence';project=a.root/'project'
    path=evidence/'knowledge-package.json';package=json.loads(path.read_text())
    (project/'knowledge-input.json').write_text(json.dumps(package,indent=2)+'\n')
    shutil.copyfile(evidence/'builder-seed.json',project/'builder-seed.json')
    module_path=Path(__file__).parents[1]/'real-code-agent/participant.py'
    spec=importlib.util.spec_from_file_location('participant',module_path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    participant=m.Participant(evidence,a.root/'participant-state',a.agent_python,a.gateway,a.model,implementation='mini-swe-agent')
    try:
        participant.turn('knowledge-analysis',project,prompt='You are the benchmark-building maintainer, not the assessed agent. Read builder-seed.json, knowledge-input.json and the actual source files. Improve the maintainer knowledge for every existing Skill identity. Explain module responsibility, caller dependencies, behavior boundaries, change workflow, validation and a possible multi-turn task. Write knowledge-draft.json with {"skills":[{"id":"existing id","body":"Markdown knowledge"}]}. Do not change source code or facts. Use tools to inspect and write the file, then submit.')
        draft_path=project/'knowledge-draft.json';shutil.copyfile(draft_path,evidence/'knowledge-draft.json')
        apply_draft(package,json.loads(draft_path.read_text()))
        path.write_text(json.dumps(package,indent=2)+'\n')
    finally:
        # Operator captures actual final source/proposal bytes even on participant failure.
        for source in project.rglob('*'):
            if source.is_file():
                target=evidence/'builder-workspace'/source.relative_to(project);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        participant.close()

if __name__=='__main__':main()
