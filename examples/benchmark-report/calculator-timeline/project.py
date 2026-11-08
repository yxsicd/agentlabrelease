#!/usr/bin/env python3
"""Build a reviewed public projection; never export raw student payloads."""
import argparse, datetime as dt, hashlib, importlib.util, json
from pathlib import Path

def digest(data): return hashlib.sha256(data).hexdigest()
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def image_projection(path, gateway_dir=None):
    if path is None:
        return {'availability':'not_supplied','view_image_calls':None,'forwarded_to_intermediate':None,
                'provider_delivery':'unknown','capture_inventory':'unknown'}
    raw=Path(path).read_bytes(); doc=json.loads(raw)
    if not isinstance(doc,dict) or doc.get('schema')!='agentlab.image_evidence_reconciliation.v1':
        raise ValueError('unsupported image evidence')
    status=doc.get('analysisStatus'); inventory=doc.get('captureInventoryStatus')
    if status not in ('completed','not_run','no_requests','unsupported_protocol','error'):
        raise ValueError('unsupported image evidence analysis status')
    if inventory not in ('complete','incomplete','no_requests','audit_error','unknown'):
        raise ValueError('unsupported capture inventory status')
    result={'availability':status,'view_image_calls':None,'forwarded_to_intermediate':None,
            'provider_delivery':'unknown','capture_inventory':inventory,'receipt_sha256':digest(raw),
            'limitation':'仅统计捕获到的查看调用与中间网关转发；不证明模型服务收到、理解或完成任务。'}
    if status=='completed':
        calls=doc.get('calls')
        if not isinstance(calls,list) or any(not isinstance(c,dict) or c.get('forwarded_to_intermediate') not in ('observed','unknown') or c.get('provider_delivery')!='unknown' for c in calls):
            raise ValueError('invalid image evidence calls')
        if gateway_dir is None:
            raise ValueError('gateway capture is required to bind image evidence')
        module_path=Path(__file__).resolve().parents[1]/'image_evidence.py'
        spec=importlib.util.spec_from_file_location('agentlab_image_evidence',module_path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        actual=module.reconcile(gateway_dir)
        if doc.get('scope')!=actual['scope'] or calls!=actual['calls']:
            raise ValueError('image evidence differs from this gateway capture')
        inventory_path=Path(gateway_dir).parent/'gateway-capture-inventory.json'
        if not inventory_path.is_file():
            result['capture_inventory']='unverified'
        else:
            producer=read_json(inventory_path)
            if producer.get('schema')!='agentlab.gateway_capture_inventory.v1' or producer.get('status')!=inventory:
                raise ValueError('image evidence differs from producer inventory')
            count=producer.get('producerObservedCount')
            if inventory=='complete' and (type(count) is not int or count!=len(list(Path(gateway_dir).glob('*.status.json')))):
                raise ValueError('gateway count differs from producer inventory')
        result['view_image_calls']=len(calls)
        result['forwarded_to_intermediate']=sum(c['forwarded_to_intermediate']=='observed' for c in calls)
    return result
def main():
    p=argparse.ArgumentParser(); p.add_argument('--trace',required=True);p.add_argument('--closed',required=True);p.add_argument('--gateway-dir',required=True);p.add_argument('--review',required=True);p.add_argument('--out',required=True);p.add_argument('--image-evidence');a=p.parse_args()
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
    out['image_observations']=image_projection(a.image_evidence,a.gateway_dir)
    target=Path(a.out);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'commands':len(commands),'calls':len(calls),'reviewed':len(found),'trace_sha256':sha}))
if __name__=='__main__': main()
