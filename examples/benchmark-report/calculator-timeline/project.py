#!/usr/bin/env python3
"""Build a reviewed public projection; never export raw student payloads."""
import argparse, datetime as dt, hashlib, json
from pathlib import Path

def digest(data): return hashlib.sha256(data).hexdigest()
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def main():
    p=argparse.ArgumentParser(); p.add_argument('--trace',required=True);p.add_argument('--closed',required=True);p.add_argument('--gateway-dir',required=True);p.add_argument('--review',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    raw=Path(a.trace).read_bytes(); review=read_json(a.review); sha=digest(raw)
    if sha != review['trace_sha256']: raise ValueError('trace digest does not match reviewed annotations')
    commands=[]; found=set()
    for line_no,line in enumerate(raw.split(b'\n'),1):
        if not line.strip(): continue
        event=json.loads(line);item=event.get('item') or {}
        if event.get('type')!='item.completed' or item.get('type')!='command_execution': continue
        ident=item['id']; ann=review['annotations'].get(ident)
        if ann:
            if digest(item['command'].encode())!=ann['command_sha256']: raise ValueError('reviewed command changed: '+ident)
            found.add(ident)
        commands.append({'ordinal':len(commands)+1,'event_id':ident,'trace_line':line_no,'exit_code':item.get('exit_code'),'status':item.get('status'),'command_sha256':digest(item['command'].encode()),'output_sha256':digest((item.get('aggregated_output') or '').encode()),'annotation':ann['text'] if ann else '命令执行；未作逐条人工标注','kind':ann['kind'] if ann else '未标注'})
    if found!=set(review['annotations']): raise ValueError('review refers to missing command')
    if len(commands)!=review['expected_commands']: raise ValueError('command count differs')
    closed=read_json(a.closed)['usage'];records={x['exchange']:x for x in closed['records']};statuses=sorted(Path(a.gateway_dir).glob('*.status.json'));calls=[]
    if len(statuses)!=closed['exchanges']: raise ValueError('gateway status count differs')
    first=None
    for path in statuses:
        s=read_json(path); ident=s['exchangeId']; start=dt.datetime.fromisoformat(s['startedAt']);first=first or start
        usage=records[ident]['usage'];calls.append({'exchange':ident,'offset_seconds':round((start-first).total_seconds(),3),'duration_ms':s['durationMs'],'http_status':s['status'],'outcome':s['outcome'],'usage':usage,'budget_used':s.get('attemptBudget',{}).get('used')})
    totals=closed['totalsObserved'];
    for key in ('input','output','cached_input','reasoning_output'):
        if sum(x['usage'].get(key,0) for x in calls)!=totals[key]: raise ValueError('usage mismatch: '+key)
    out={'schema':'agentlab.reviewed_timeline.v1','trace_sha256':sha,'trace_record_count':sum(bool(line.strip()) for line in raw.split(b'\n')),'trace_access':'原始轨迹为私有证据；行号和哈希供授权核对，网页不公开原始命令与输出','ordering_limit':'命令仅有事件顺序、无时间戳；模型调用时间线独立，不能据此精确关联单条命令','commands':commands,'model_calls':calls,'usage_totals':totals,'usage_complete':closed['inputOutputComplete'],'cached_input_included_in_input':True,'reasoning_output_included_in_output':True,'review_method':'仅显示与原始命令哈希绑定的人工复核摘要；其余不作收益判断'}
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'commands':len(commands),'calls':len(calls),'reviewed':len(found),'trace_sha256':sha}))
if __name__=='__main__': main()
