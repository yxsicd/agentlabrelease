#!/usr/bin/env python3
"""Compose an operator-owned multi-benchmark view from verified attempt evidence."""
import argparse
import html
import importlib.util
import json
import os
from pathlib import Path


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def build(swe_paths, terminal_attempt, terminal_trial, terminal_reference):
    examples=Path(__file__).resolve().parents[1]
    swe=load('agentlab_swe_campaign',examples/'swe-bench/campaign_report.py').build(swe_paths)
    terminal=load('agentlab_terminal_report',examples/'terminal-bench/report.py').build(
        terminal_attempt,terminal_trial,terminal_reference)
    return {'schema':'agentlab.external_benchmark_overview.v1','swe':swe,'terminal':terminal,
            'limitations':['Dataset and model configurations remain separate; no cross-benchmark pass rate or ranking.',
                           'A single attempt does not establish general model ability.',
                           'These local benchmark runs do not qualify native AgentLab Session/Fork.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--swe-assessment',type=Path,action='append',required=True)
    p.add_argument('--terminal-attempt',type=Path,required=True);p.add_argument('--terminal-trial',type=Path,required=True)
    p.add_argument('--terminal-reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=build(a.swe_assessment,a.terminal_attempt,a.terminal_trial,a.terminal_reference)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for group in result['swe']['groups']:
        for attempt in group['attempts']:
            source=Path(attempt.pop('_path'));attempt['assessmentFile']=os.path.relpath(source,out)
    terminal=result['terminal']
    terminal['evidence']=[{'path':os.path.relpath(path.resolve(),out),'sha256':digest} for path,digest in terminal.pop('_sources')]
    (out/'overview.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    def section(title,obj):
        return '<section><h2>'+html.escape(title)+'</h2><pre>'+html.escape(json.dumps(obj,ensure_ascii=False,indent=2))+'</pre></section>'
    blocks=[]
    swe_links=[]
    for group in result['swe']['groups']:
        blocks.append(section('SWE：'+str(group['configuration'].get('benchmark')),
            {'configuration':group['configuration'],'counts':group['counts'],'passRate':group['passRate'],'attempts':group['attempts']}))
        for attempt in group['attempts']:
            path=Path(attempt['assessmentFile']).parent/'evaluation.html'
            swe_links.append('<li><a href="'+html.escape(str(path),quote=True)+'">'+html.escape(str(attempt['task']))+'</a> — '+html.escape(attempt['qualification'])+'</li>')
    blocks.append(section('Terminal-Bench：'+str(terminal.get('task')),
        {k:terminal[k] for k in ('qualification','resolved','verifierTests','participant','execution','usage')}))
    links=''.join('<li><a href="'+html.escape(e['path'],quote=True)+'">'+html.escape(e['path'])+'</a> <code>'+e['sha256']+'</code></li>' for e in terminal['evidence'])
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
       '<title>AgentLab 标准用例总览</title><style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#172033}'
       'section{border:1px solid #ddd;border-radius:8px;margin:1em 0;padding:0 1em}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
       'code{font-size:.75em;overflow-wrap:anywhere}</style><h1>AgentLab 标准用例总览</h1>'
       '<p>按数据集和运行配置分别展示；系统故障不计为学生失败，单次结果不构成模型排名。</p>'
       +''.join(blocks)+'<h2>SWE 详细报告</h2><ul>'+''.join(swe_links)+'</ul><h2>Terminal 原始证据</h2><ul>'+links+'</ul></html>')


if __name__=='__main__':main()
