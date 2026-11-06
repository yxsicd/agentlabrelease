#!/usr/bin/env python3
"""Compare evidence boundaries of mature benchmarks and a historical Harmony attempt."""
import argparse
import gzip
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path


def load(path):
    spec=importlib.util.spec_from_file_location('agentlab_benchmark_overview',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def build(swe_paths,terminal_attempt,terminal_trial,terminal_reference,harmony_supplement,harmony_marker,harmony_device_summary,harmony_device_evidence,oracle_repeat=None,nop_job=None,live_host=None,live_device=None):
    here=Path(__file__).resolve().parent
    mature=load(here/'compose.py').build(swe_paths,terminal_attempt,terminal_trial,terminal_reference)
    supplement=Path(harmony_supplement);root=supplement.parent.resolve()
    hist=json.loads(supplement.read_text());marker=json.loads(Path(harmony_marker).read_text())
    ui=json.loads(Path(harmony_device_summary).read_text());ui_path=Path(harmony_device_evidence)
    if hist.get('schema')!='agentlab.calendar.assessment-supplement.v1':
        raise ValueError('unsupported historical Harmony supplement')
    provenance=[]
    for name,entry in hist['provenance'].items():
        path=(root/entry['path']).resolve(strict=True)
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('historical Harmony evidence missing or changed')
        provenance.append({'name':name,'path':str(path),'sha256':entry['sha256']})
    if hashlib.sha256(ui_path.read_bytes()).hexdigest()!=ui.get('sha256'):
        raise ValueError('historical device evidence digest differs')
    ui_raw=json.loads(gzip.decompress(ui_path.read_bytes()))
    if ui.get('actor')!=ui_raw.get('actor'):
        raise ValueError('device evidence actor differs')
    cases=ui_raw.get('remainingCases')
    if not isinstance(cases,list) or not all(isinstance(case,dict) for case in cases):
        raise ValueError('device evidence cases are missing')
    device_counts={'observed':len(cases),'passed':sum(case.get('pass') is True for case in cases),
                   'failed':sum(case.get('pass') is False for case in cases),
                   'unknown':sum(case.get('pass') is not True and case.get('pass') is not False for case in cases)}
    help_count=(hist.get('assistance') or {}).get('teacherHelpCount')
    if help_count!=marker.get('teacherHelpCount'):
        raise ValueError('historical assistance counts disagree')
    if (hist.get('evaluation') or {}).get('numericalScore')!=marker.get('score'):
        raise ValueError('historical scoring records disagree')
    historical_sources=[{'path':str(Path(path).resolve()),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                        for path in (harmony_supplement,harmony_marker,harmony_device_summary,harmony_device_evidence)]
    terminal=mature['terminal'];oracle_count=1;repeat_details=[]
    if oracle_repeat is not None:
        repeat=Path(oracle_repeat);aggregate=json.loads((repeat/'result.json').read_text())
        results=sorted(repeat.glob('*/result.json'))
        if aggregate.get('finished_at') is None or len(results)!=aggregate.get('n_total_trials'):
            raise ValueError('reference repetition job is not complete')
        ids=set()
        for path in results:
            raw=path.read_bytes();item=json.loads(raw);ident=item.get('id')
            if not ident or ident in ids or item.get('task_checksum')!=terminal.get('taskChecksum') or item.get('agent_info',{}).get('name')!='oracle':
                raise ValueError('reference repetition identity differs')
            ids.add(ident);reward=((item.get('verifier_result') or {}).get('rewards') or {}).get('reward')
            repeat_details.append({'trialId':ident,'reward':reward,'exception':(item.get('exception_info') or {}).get('exception_type'),
                                   'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
        oracle_count+=len(results)
    verified=sum(type(x['reward']) in (int,float) and x['reward']==1.0 and x['exception'] is None for x in repeat_details)+1
    negative=None
    if nop_job is not None:
        job=Path(nop_job);aggregate=json.loads((job/'result.json').read_text());results=list(job.glob('*/result.json'))
        if aggregate.get('finished_at') is None or len(results)!=1 or aggregate.get('n_total_trials')!=1:
            raise ValueError('negative-control job is not complete')
        raw=results[0].read_bytes();item=json.loads(raw)
        if not item.get('id') or item.get('task_checksum')!=terminal.get('taskChecksum') or item.get('agent_info',{}).get('name')!='nop':
            raise ValueError('negative-control identity differs')
        reward=((item.get('verifier_result') or {}).get('rewards') or {}).get('reward')
        exception=(item.get('exception_info') or {}).get('exception_type')
        negative={'reward':reward,'exception':exception,'passed':type(reward) in (int,float) and reward==0.0 and exception is None,
                  'path':str(results[0]),'sha256':hashlib.sha256(raw).hexdigest()}
    controls_ready=oracle_count>=5 and verified==oracle_count and negative is not None and negative['passed']
    if (live_host is None)!=(live_device is None):
        raise ValueError('both live host and device readbacks are required')
    live=None
    if live_host is not None:
        host=json.loads(Path(live_host).read_text());device=json.loads(Path(live_device).read_text())
        if (host.get('schema')!='agentlab.harmony-live-readback.v1' or device.get('schema')!='agentlab.harmony-device-readback.v1'
            or host.get('targetPeerId')!=device.get('targetPeerId') or host.get('routeDecision')!='peer_direct'
            or device.get('routeDecision')!='peer_direct'):
            raise ValueError('live host and device identity or route differs')
        live={'hostObservedAt':host.get('observedAt'),'deviceObservedAt':device.get('observedAt'),
              'selectedContainers':host.get('selectedContainers'),'emulatorProcessName':host.get('calendarEmulatorProcessName'),
              'historicalPortListening':host.get('historicalPort19932Listening'),'rootAvailableBytes':host.get('rootAvailableBytes'),
              'targetBinding':device.get('targetBinding'),'versionRead':device.get('versionRead'),
              'targetPortListening':device.get('targetPortListening'),'shellEchoRead':device.get('shellEchoRead'),
              'deviceReady':device.get('deviceReady'),'qualification':device.get('readinessQualification'),
              'sourceEvidence':[{'path':str(Path(path).resolve()),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                                for path in (live_host,live_device)]}
    return {'schema':'agentlab.mature_to_harmony_alignment.v1',
        'mature':{'swe':[{'benchmark':g['configuration'].get('benchmark'),'counts':g['counts']} for g in mature['swe']['groups']],
                  'terminal':{'task':terminal.get('task'),'qualification':terminal.get('qualification'),'resolved':terminal.get('resolved'),
                              'normalSubmission':terminal.get('execution',{}).get('submitted'),'referenceRuns':oracle_count,
                              'referencePasses':verified,'repeatTrials':repeat_details,'negativeControl':negative}},
        'harmonyHistorical':{'recordedAt':marker.get('at'),'verdict':(hist.get('evaluation') or {}).get('verdict'),
            'numericalScore':(hist.get('evaluation') or {}).get('numericalScore'),
            'teacherHelpRecorded':help_count,'helpScope':'recorded exposures; consumption/effect not established for every entry',
            'harness':hist.get('harness'),'systemEvaluator':{'actor':ui.get('actor'),'reportedDeviceAcceptance':ui.get('publicAcceptance'),
                'rawRemainingCaseCounts':device_counts,'scopeLimit':ui.get('scopeLimit'),'deviceEvidenceSha256':ui.get('sha256')},
            'limitations':hist.get('limits'),'provenance':provenance,'sourceEvidence':historical_sources},
        'harmonyLive':live,
        'gaps':[{'id':'reference-and-negative-controls','status':'partial','reason':'将重复参考解与无解负对照迁移到冻结的鸿蒙用例；现有历史摘要不能证明这些控制已完成。'},
                {'id':'student-and-harness-attribution','status':'partial','reason':'分开记录学生结果、环境故障、教师帮助和未知效果；历史鸿蒙学生判定仍待定。'},
                {'id':'runtime-device-validation','status':'partial','reason':'历史设备检查由系统评测者完成，并非学生操作；新尝试需独立留存编译、部署与行为验证。'},
                {'id':'checkpoint-fork','status':'unqualified','reason':'外部 benchmark 不证明 AgentLab 原生 Session/Fork；不得重放旧的未知操作。'},
                {'id':'comparability','status':'partial','reason':'固定任务、源码、环境、Agent、模型、推理、预算和重复次数；不同 benchmark 与辅助尝试分开统计。'}],
        'next':([] if controls_ready else ['完成固定成熟用例的参考解重复验证与无解负对照。'])+[
                '读取鸿蒙现存实例和原操作的准确状态，不重放未知操作。',
                '冻结可恢复的新鸿蒙尝试，独立验证参考解与负对照。',
                '运行一次学生尝试，独立检查编译、部署、行为与保留证据。'],
        'limitations':['历史鸿蒙观察不代表当前实例已就绪。',
                       '重复参考任务的校验和已核对；未保留每次独立镜像 ID。',
                       '一次或少量尝试不能得出模型排名或有代表性的通过率。',
                       '哈希校验只证明一致性，不证明证据来源已认证。']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--swe-assessment',action='append',type=Path,required=True)
    for key in ('terminal-attempt','terminal-trial','terminal-reference','harmony-supplement','harmony-marker','harmony-device-summary','harmony-device-evidence','output'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--oracle-repeat',type=Path)
    p.add_argument('--nop-job',type=Path)
    p.add_argument('--live-host',type=Path)
    p.add_argument('--live-device',type=Path)
    a=p.parse_args();result=build(a.swe_assessment,a.terminal_attempt,a.terminal_trial,a.terminal_reference,
        a.harmony_supplement,a.harmony_marker,a.harmony_device_summary,a.harmony_device_evidence,a.oracle_repeat,a.nop_job,a.live_host,a.live_device)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for row in result['harmonyHistorical']['provenance']:row['path']=os.path.relpath(row['path'],out)
    for row in result['harmonyHistorical']['sourceEvidence']:row['path']=os.path.relpath(row['path'],out)
    for row in result['mature']['terminal']['repeatTrials']:row['path']=os.path.relpath(row['path'],out)
    if result['mature']['terminal']['negativeControl']:
        row=result['mature']['terminal']['negativeControl'];row['path']=os.path.relpath(row['path'],out)
    if result['harmonyLive']:
        for row in result['harmonyLive']['sourceEvidence']:row['path']=os.path.relpath(row['path'],out)
    (out/'alignment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    def section(title,obj):return '<section><h2>'+html.escape(title)+'</h2><pre>'+html.escape(json.dumps(obj,ensure_ascii=False,indent=2))+'</pre></section>'
    body=section('成熟 benchmark 实测',result['mature'])+section('鸿蒙历史证据：不是当前就绪结论',result['harmonyHistorical'])
    if result['harmonyLive']:body+=section('鸿蒙实时只读核对：时点观察',result['harmonyLive'])
    body+=section('差距',result['gaps'])+section('下一步',result['next'])+section('边界',result['limitations'])
    links=result['harmonyHistorical']['sourceEvidence']+result['harmonyHistorical']['provenance']+result['mature']['terminal']['repeatTrials']
    if result['mature']['terminal']['negativeControl']:links.append(result['mature']['terminal']['negativeControl'])
    if result['harmonyLive']:links+=result['harmonyLive']['sourceEvidence']
    body+='<h2>可复核证据</h2><ul>'+''.join('<li><a href="'+html.escape(row['path'],quote=True)+'">'+html.escape(row['path'])+'</a> <code>'+row['sha256']+'</code></li>' for row in links)+'</ul>'
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>成熟 Benchmark 与鸿蒙对照</title><style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:0 1em}'
        'section{border:1px solid #ddd;border-radius:8px;padding:0 1em;margin:1em 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>成熟 Benchmark 与鸿蒙对照</h1><p>区分学生结果、系统验证和历史未知状态；不同 benchmark 不合并通过率。</p>'+body+'</html>')


if __name__=='__main__':main()
