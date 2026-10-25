#!/usr/bin/env python3
"""Offline, allowlisted process evidence projection. Never regrade or dispatch."""
import argparse,collections,hashlib,html,importlib.util,json,re,shutil
from pathlib import Path
LABELS={'preparation':'准备','validation_progress':'验证推进','informative_failure':'提供约束信息的失败','state_recovery':'状态恢复','repeated_check_no_new_requirement':'重复检查，未增加需求覆盖','goal_action':'目标操作'}
def require(ok,msg):
 if not ok: raise ValueError(msg)
def project(private,public):
 digest=hashlib.sha256(json.dumps(private,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 require(public['provenance']['privateReportSHA256']==digest,'private evidence mismatch')
 require(public['schema']=='agentlab.public-evaluation.v3','v3 required')
 ops=private['cases'][0]['operations'];require(len(ops)==len(public['operations'])==31,'population changed')
 lookup={o['operationId']:i for i,o in enumerate(ops,1)};actions=private['cases'][0]['reviewedLearning']['actions'];require(private['cases'][0]['reviewedLearning'].get('reviewedCalls')==len(actions)==8 and private['cases'][0]['reviewedLearning'].get('identifiedCalls')==373,'reviewed selection changed');ids={a['id']:f'A{i:02}' for i,a in enumerate(actions,1)};rows=[]
 for a in actions:
  require(a['operationId'] in lookup and a['kind'] in LABELS,'unbound action')
  require(all(re.fullmatch('[0-9a-f]{64}',a[k]) for k in ['requestSHA256','resultSHA256']),'invalid commitment')
  rows.append({'id':ids[a['id']],'run':lookup[a['operationId']],'kind':a['kind'],'finding':a['finding'],'reportedIsError':a['reportedIsError'],'requestSHA256':a['requestSHA256'],'resultSHA256':a['resultSHA256'],'recoveryOf':ids.get(a.get('recoveryOf')),'authority':'evaluator_reviewed_interpretation_not_hash_proven_truth'})
 judgments=[]
 for i,(o,p) in enumerate(zip(ops,public['operations']),1):
  require(o['phase']==p['phase'] and o['durationMs']==p['durationMs'],'row mismatch')
  f=o.get('traceEvidence',{}).get('failureAttribution');j={'run':i,'nativeStatus':p['runtimeStatus'],'historicalStageOutcome':p['outcome'],'recordedFailureKind':f.get('kind') if f else None,'studentCapabilityFailureEstablished':f.get('studentCapabilityFailureEstablished') if f else None,'wholeTaskIndependentVerdict':None,'reviewAnnotation':None}
  if i in [15,28]:j['reviewAnnotation']='上游502且未产生工具调用；保留原阶段标签，该轮未测得工具执行能力。'
  if i==22:j['reviewAnnotation']='模型流不完整；provider／gateway／client具体归因未闭合。'
  judgments.append(j)
 audit={'schema':'agentlab.process-audit.v1','evidenceReportCommitment':digest,'selection':'purposefully selected existing review, not random or complete','identifiedCalls':373,'reviewedCalls':len(rows),'unreviewedCalls':373-len(rows),'globalUsefulCallRate':None,'rows':rows,'kindCounts':dict(collections.Counter(r['kind'] for r in rows)),'judgments':judgments,'integrity':{'oracleIsolation':'not_audited','testLeakage':'not_audited','deadlinePolicyCompliance':'not_audited','misconductVerdict':None,'meaning':'未审计不代表违规或已通过；探索期教师帮助是披露的评测条件。'},'adjustedPassRate':None}
 result=json.loads(json.dumps(public));result.update(schema='agentlab.public-evaluation.v4',version='2026-10-25-v4',processAudit=audit);result['agentReport']['analysisRevision']='agent-report-v4';result['provenance']['publicProjectionPolicy']='allowlist-v4-process-adjudication';return result

def render(data,page):
 e=lambda s:html.escape(str(s));a=data['processAudit'];cards=[]
 for r in a['rows']:
  recovery='；恢复自 <a href="#audit-'+r['recoveryOf']+'">'+r['recoveryOf']+'</a>' if r['recoveryOf'] else ''
  cards.append('<article class="difficulty-card" id="audit-'+r['id']+'"><span class="state-tag">'+r['id']+' · '+e(LABELS[r['kind']])+'</span><h3><a class="run-link" href="#run-'+str(r['run'])+'">第'+str(r['run'])+'轮原证据</a></h3><p>'+e(r['finding'])+'</p><p class="helper-note">外层reportedIsError='+str(r['reportedIsError']).lower()+recovery+'</p><details><summary>请求／结果字节承诺</summary><p style="overflow-wrap:anywhere">request '+r['requestSHA256']+'<br>result '+r['resultSHA256']+'</p><p>哈希绑定证据字节，不证明解释正确；原始私有轨迹不公开。</p></details></article>')
 process='<section id="process"><div class="report-kicker">05 / PROCESS EVIDENCE</div><h2>工具正常返回，不等于操作成功或目标推进</h2><p>373次已识别调用中，仅8次被定向语义审阅，365次尚未审阅；不能外推整体有益调用率。8次外层均未标记错误，其中A03实际命令参数错误，A04由学生自行恢复。重复检查未增加当前需求覆盖，也不等于绝对无价值。</p><div class="difficulty-cards"><article><b>373</b><span>已识别调用</span></article><article><b>8</b><span>定向审阅，非随机样本</span></article><article><b>365</b><span>未语义审阅</span></article><article><b>未测</b><span>全局有益调用率</span></article></div><p><a href="#audit-A03">查看 参数错误 → 学生恢复 → 重启验证 的原链条</a></p>'+''.join(cards)+'<a href="process-audit.json" download>下载过程审阅与逐轮判定分层</a></section>'
 trs=[]
 for j in a['judgments']:
  trs.append('<tr><td><a class="run-link" href="#run-'+str(j['run'])+'">第'+str(j['run'])+'轮</a></td><td>'+e(j['nativeStatus'])+'</td><td>'+e(j['historicalStageOutcome'])+'</td><td>'+e(j['recordedFailureKind'] or '未记录，保持未知')+'</td><td>'+e(j['reviewAnnotation'] or '不由此推断整题能力通过／失败')+'</td></tr>')
 judgment='<section id="judgment"><div class="report-kicker">06 / ADJUDICATION AND INTEGRITY</div><h2>运行状态、历史阶段判定和能力归因分层</h2><p>原有31轮阶段结论完全保留。超时说明在当时预算与执行条件下未闭环，不能证明延长后一定成功或能力不足。上游／Harness问题只按已有证据标注，不偷偷从分母删除，也不计算“排除故障后的通过率”。</p><div class="readiness-banner"><strong>整题独立完成结论仍未建立。</strong><p>记录中的studentCapabilityFailureEstablished=false表示未建立该归因，不表示学生已通过。缺归因字段保留null。</p></div><div class="scroll"><table><thead><tr><th>原执行</th><th>原生状态</th><th>原阶段结论</th><th>原记录归因</th><th>审阅注释</th></tr></thead><tbody>'+''.join(trs)+'</tbody></table></div><h3>评测完整性：明确未知，不作自证</h3><p>独立判据隔离、测试泄露检查、超时策略遵守情况：均未完成独立审计。未审计不等于违规，也不等于通过。探索阶段教师帮助属于已披露的条件，仍计入学生帮助依赖；正式无帮助队列须独立冻结。</p><p>对照 <a href="https://www.tbench.ai/news/leaderboard-integrity-update" target="_blank" rel="noopener">Terminal-Bench 2.0完整性更新</a>的轨迹与判据隔离审查，及 <a href="https://www.swebench.com/SWE-bench/guides/evaluation/" target="_blank" rel="noopener">SWE-bench运行／解决／错误分层</a>；借鉴披露方式，不宣称通过这些基准的认证。</p></section>'
 page=page.replace('2026-10-25-v3','2026-10-25-v4').replace('探索性评测报告 v3','探索性评测报告 v4').replace('agent-report-v3','agent-report-v4')
 page=page.replace('href="../2026-10-25-v2/">上一报告版本','href="../2026-10-25-v3/">上一报告版本')
 return page.replace('<section id="difficulty"',process+judgment+'<section id="difficulty"',1).replace('<p class="links">','<p class="links"><a href="#process">调用收益证据</a><a href="#judgment">判定与完整性</a>',1)
def main():
 p=argparse.ArgumentParser();p.add_argument('--private-report',type=Path,required=True);p.add_argument('--public-v3',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--scanner',type=Path,required=True);args=p.parse_args();require(not args.output.exists(),'immutable output exists')
 data=project(json.loads(args.private_report.read_text()),json.loads((args.public_v3/'evaluation.json').read_text()));page=render(data,(args.public_v3/'index.html').read_text());spec=importlib.util.spec_from_file_location('scanner',args.scanner);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);s.scan_public(data);s.scan_public(page)
 shutil.copytree(args.public_v3,args.output);(args.output/'evaluation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(args.output/'index.html').write_text(page);(args.output/'process-audit.json').write_text(json.dumps(data['processAudit'],ensure_ascii=False,indent=2)+'\n');print(json.dumps({'reviewedCalls':len(data['processAudit']['rows']),'judgments':len(data['processAudit']['judgments']),'globalUsefulCallRate':None}))
if __name__=='__main__': main()
