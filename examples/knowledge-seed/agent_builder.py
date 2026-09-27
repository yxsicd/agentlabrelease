#!/usr/bin/env python3
"""Replaceable builder participant; Harness binds proposals to source facts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


def materialize_source_slice(project, source_root, package):
    """Copy only source files already bound into the frozen operator package."""
    project.mkdir(parents=True, exist_ok=True)
    if source_root is None:
        return []
    source_root = source_root.resolve(strict=True)
    rows = package['tables']['program_facts']
    file_facts = {row['path']: row for row in rows
                  if row.get('kind') == 'file' and isinstance(row.get('path'), str)}
    paths = sorted(file_facts)
    if not paths:
        raise ValueError('Frozen package has no source-bound file facts')
    copied = []
    for relative in paths:
        relative_path = Path(relative)
        if relative_path.is_absolute() or '..' in relative_path.parts:
            raise ValueError(f'Source fact is not a safe relative path: {relative}')
        source = (source_root / relative).resolve(strict=True)
        try:
            source.relative_to(source_root)
        except ValueError as error:
            raise ValueError(f'Source fact escapes source root: {relative}') from error
        if not source.is_file():
            raise ValueError(f'Source fact is not a regular file: {relative}')
        expected_digest = file_facts[relative].get('sha256')
        actual_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if expected_digest and actual_digest != expected_digest:
            raise ValueError(f'Source bytes do not match frozen fact: {relative}')
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(relative)
    return copied


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
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--agent-python',type=Path,required=True);p.add_argument('--gateway',required=True);p.add_argument('--model',default='glm-5.3-flash');p.add_argument('--source-root',type=Path);a=p.parse_args()
    evidence=a.root/'evidence';project=a.root/'project'
    path=evidence/'knowledge-package.json';package=json.loads(path.read_text())
    copied=materialize_source_slice(project,a.source_root,package)
    (project/'knowledge-input.json').write_text(json.dumps(package,indent=2)+'\n')
    shutil.copyfile(evidence/'builder-seed.json',project/'builder-seed.json')
    (evidence/'builder-source-slice.json').write_text(json.dumps({
        'sourceRootProvided': a.source_root is not None,
        'fileCount': len(copied),
        'paths': copied,
    },indent=2)+'\n')
    module_path=Path(__file__).parents[1]/'real-code-agent/participant.py'
    spec=importlib.util.spec_from_file_location('participant',module_path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    participant=m.Participant(evidence,a.root/'participant-state',a.agent_python,a.gateway,a.model,implementation='mini-swe-agent')
    try:
        participant.turn('knowledge-analysis',project,step_limit=20,wall_time_limit_seconds=720,prompt='You are the benchmark-building maintainer, not the assessed agent. Read builder-seed.json, knowledge-input.json and the actual source files. Produce one concise maintainer-knowledge body for every existing frozen Skill identity. Preserve all verified operator facts and uncertainty boundaries. Each body should briefly cover responsibility, caller dependencies, behavior boundaries, change workflow, validation, and a possible multi-turn task; aim for 80-180 words rather than an essay. Write knowledge-draft.json exactly as {"skills":[{"id":"existing id","body":"Markdown knowledge"}]}. Do not change source code or facts. Make one focused inspection pass, write the JSON once, validate only its JSON syntax plus exact ID/count equality, and then immediately submit with the required completion command. Do not repeatedly rewrite or exhaustively validate identifiers.')
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
