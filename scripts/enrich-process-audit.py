#!/usr/bin/env python3
"""Offline, allowlisted process evidence projection. Never regrade or dispatch."""
import argparse,collections,hashlib,html,importlib.util,json,re,shutil,sys
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
 if "--frozen-reviews" in sys.argv:return frozen_main()
 p=argparse.ArgumentParser();p.add_argument('--private-report',type=Path,required=True);p.add_argument('--public-v3',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--scanner',type=Path,required=True);args=p.parse_args();require(not args.output.exists(),'immutable output exists')
 data=project(json.loads(args.private_report.read_text()),json.loads((args.public_v3/'evaluation.json').read_text()));page=render(data,(args.public_v3/'index.html').read_text());spec=importlib.util.spec_from_file_location('scanner',args.scanner);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);s.scan_public(data);s.scan_public(page)
 shutil.copytree(args.public_v3,args.output);(args.output/'evaluation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(args.output/'index.html').write_text(page);(args.output/'process-audit.json').write_text(json.dumps(data['processAudit'],ensure_ascii=False,indent=2)+'\n');print(json.dumps({'reviewedCalls':len(data['processAudit']['rows']),'judgments':len(data['processAudit']['judgments']),'globalUsefulCallRate':None}))

def frozen_cohort(public,intake):
 require(public['schema']=='agentlab.public-evaluation.v4','separate frozen intake requires v4 baseline')
 require(intake.get('schema')=='agentlab.frozen-review-intake.v1','unsupported frozen intake')
 protocol={k:intake['protocol'][k] for k in ['taskSHA256','initialStateRevision','agent','model','thinking','nativeBudgetMs','gatewaySHA256','oracleSHA256']};task=protocol['taskSHA256'];require(bool(re.fullmatch('[0-9a-f]{64}',task)),'task hash required')
 require(type(protocol['nativeBudgetMs']) is int and protocol['nativeBudgetMs']>0,'positive native budget required')
 labels=set();out=[]
 for row in intake['attempts']:
  label=row['label'];require(label in ['A2','B2'] and label not in labels,'unique frozen attempt label required');labels.add(label)
  freeze=row['freeze'];native=row['nativeAcceptance'];config=native['configurationObserved'];start=row['qualifiedStart']
  require(start['forkCommit']==protocol['initialStateRevision'] and start['priorContextFiles']==[],'initial state or inherited context mismatch')
  require(freeze['gatewaySHA256']==protocol['gatewaySHA256'],'gateway environment mismatch')
  require(native['freshParticipantContext'] is True,'fresh context not qualified')
  require(freeze['taskSHA256']==native['taskSHA256']==task,'frozen task mismatch')
  require(freeze['nativeBudgetMs']==protocol['nativeBudgetMs'],'budget mismatch')
  require(any(c.get('modelId')==protocol['model'] for c in config),'observed model mismatch')
  require(any(c.get('thinkingLevel')==protocol['thinking'] for c in config),'observed thinking mismatch')
  require(type(native['newHelpEvents']) is int and native['newHelpEvents']>=0,'help count required')
  review=row.get('review');record={'label':label,'status':row['status'],'newTeacherHelpEvents':native['newHelpEvents'],'wholeTaskIndependentVerdict':None,'canonicalPublished':False,'functionalChecks':[],'deliveryChecks':[],'strengths':[],'limitations':[],'evidenceCommitment':hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
  if review:
   require(review.get('schema')=='agentlab.independent-frozen-task-review.v1' and review.get('producer')=='teacher_evaluator','independent reviewer required')
   require(review['taskSHA256']==task,'review task mismatch')
   require(review['originalOperationId']==native['recipient']['operationId'] and review['sessionId']==native['recipient']['sessionId'] and review['requestDigest']==native['recipient']['requestDigest'],'original operation review binding mismatch')
   require(review['teacherSolutionHelpEvents']==native['newHelpEvents'],'help audit mismatch')
   # A claimed pass is not imported as authority. Canonical readback qualification
   # and full completion review are separate downstream acceptance steps.
   require(review.get('wholeTaskPassed') is not True,'whole-pass promotion requires separately qualified original publication')
   require(type(review['canonicalPublished']) is bool,'publication declaration must be boolean')
   record.update(canonicalPublished=review['canonicalPublished'],wholeTaskIndependentVerdict=review['wholeTaskVerdict'])
   record['faultBoundaries']=[{k:v for k,v in f.items() if k in ['layer','observed','rootCause','meaning','studentAbilityFailureEstablished']} for f in review.get('faultBoundaries',[])]
   for key in ['functionalChecks','deliveryChecks','strengths','limitations']:
    for c in review.get(key,[]):
     record[key].append({**{k:c[k] for k in ['id','status']},'finding':c.get('publicFinding',c['finding'])})
  metrics=row.get('publishedMetrics')
  if metrics:
   require(review and review['canonicalPublished'] is True and metrics.get('publishedOriginalQualified') is True,'metrics require qualified original publication')
   original=metrics['originalOperation'];recipient=native['recipient'];proof=metrics['maintainedReaderProof'];tools=proof['toolActivity']
   require(original['operationId']==recipient['operationId'] and original['sessionId']==recipient['sessionId'] and original['requestId']==freeze['requestId'],'metric original-operation mismatch')
   require(original['checkpoint']==review['publishedCheckpoint'],'metric checkpoint mismatch')
   require(proof['kind']=='owning_runtime_fact' and proof['records']==original['traceExpected']==original['traceVerified'],'metric trace mismatch')
   require(all(tools[k]==0 for k in ['unknownResultCalls','orphanTerminalCalls','malformedEvents','conflictingCalls']),'incomplete trace cannot supply complete metrics')
   usage={k:metrics['nativeUsageFieldTotals'][k] for k in ['input','output','cacheRead','cacheWrite','reasoning','totalTokens']}
   require(all(type(v) is int and v>=0 for v in usage.values()),'invalid usage fields')
   record['processMetrics']={'participantDurationMs':original['durationMs'],'nativeRuntimeStatus':original['runtimeStatus'],'nativeEventCount':proof['records'],'toolCalls':tools['toolCallCount'],'returnedWithoutError':tools['returnedWithoutError'],'returnedWithError':tools['returnedWithError'],'missingOrConflictingResults':0,'nativeUsageFields':usage,'billingCost':None,'globalUsefulCallRate':None,'meaning':'Tool flags are not command success or usefulness. totalTokens includes cacheRead; reasoning is part of output. Not a billing statement.','qualifiedFactCommitment':proof['proofSHA256']}
  out.append(record)
 require(labels=={'A2','B2'},'retain both attempts, including pending or failed')
 result=json.loads(json.dumps(public));result.update(schema='agentlab.public-evaluation.v5',version='2026-10-25-v6');result['agentReport']['analysisRevision']='agent-report-v6'
 result['frozenCohort']={'schema':'agentlab.public-frozen-cohort.v1','protocol':protocol,'attempts':out,'selection':'Both planned same-condition attempts retained; pending and failures not removed. Old Harness run and historical31 remain separate.','wholeTaskPassRate':None,'statisticalStabilityClaim':False,'meaning':'Frozen declarations and evaluator-reviewed observations; pending publication is not task success. n=2 checks procedural repeatability, not statistical stability.'}
 portable=intake.get('portableValidation')
 if portable:
  package=portable['package'];cross=portable['crossHost'];require(package['caseSHA256']==cross['caseSHA256'] and package['archiveSHA256']==cross['archiveSHA256'] and cross['sameArchiveUsedBothHosts'] is True,'portable archive mismatch')
  require(len(cross['results'])==3 and all(r['sameAsLinux'] is True and r['actorDispatches']==0 for r in cross['results']),'cross-host selected restore incomplete')
  require(sum(r['filesSHA256Matched'] for r in cross['results'])==cross['totalFileSHA256ChecksEachHost'],'portable count mismatch')
  result['frozenCohort']['portableValidation']={k:package[k] for k in ['archiveBytes','baseBundleBytes','pointPatchBytes','caseSHA256','archiveSHA256']}
  result['frozenCohort']['portableValidation'].update(points=3,fileSHA256ChecksEachHost=cross['totalFileSHA256ChecksEachHost'],hostSystems=['Linux','macOS'],gitBasePlusPatchesBytes=package['baseBundleBytes']+sum(package['pointPatchBytes'].values()),scope='selected code/evidence semantic restore only; not SDK, device, agent context or whole physical Capsule',privateEvidenceArchivePublished=False)
 result['provenance']['publicProjectionPolicy']='allowlist-v5-separate-frozen-cohort'
 return result

def render_frozen(data,page):
 e=lambda x:html.escape(str(x));a=data['frozenCohort'];rows=[]
 labels={'published_failed':'已发布／运行中断','running':'执行中','partial_delivery_runtime_fault':'部分交付／请求故障中断','incomplete_runtime_fault':'实现未完成／请求故障中断','not_executed':'未执行','observed':'已观察到','baseline_only':'仅原始工程','source_only':'仅源码观察','partial':'部分证据','incomplete':'未闭合','behavior_observed_process_identity_incomplete':'行为已观察／进程身份记录不足'}
 label=lambda v:labels.get(v,v)
 for r in a['attempts']:
  rows.append('<tr><td>'+e(r['label'])+'</td><td>'+e(label(r['status']))+'</td><td>'+e(r['newTeacherHelpEvents'])+'</td><td>'+e(label(r['wholeTaskIndependentVerdict'] or '尚未评审'))+'</td></tr>')
 detail=[]
 for r in a['attempts']:
  for key,title in [('functionalChecks','功能核对'),('deliveryChecks','交付核对'),('strengths','观察到的长处'),('limitations','限制与未闭合项')]:
   if r[key]:detail.append('<h3>'+e(r['label'])+' · '+title+'</h3><ul>'+''.join('<li><strong>'+e(c['id'])+' · '+e(label(c['status']))+'</strong>：'+e(c['finding'])+'</li>' for c in r[key])+'</ul>')
 metrics_rows=[]
 for r in a['attempts']:
  m=r.get('processMetrics')
  if m:
   u=m['nativeUsageFields'];metrics_rows.append('<tr><td>'+e(r['label'])+'</td><td>'+e(round(m['participantDurationMs']/60000,2))+' 分钟</td><td>'+e(m['toolCalls'])+'</td><td>'+e(m['returnedWithoutError'])+' / '+e(m['returnedWithError'])+'</td><td>'+e(u['input'])+'</td><td>'+e(u['output'])+'</td><td>'+e(u['reasoning'])+'</td><td>'+e(u['cacheRead'])+'</td><td>'+e(u['totalTokens'])+'</td></tr>')
 metrics_html='<h3>正式原操作的过程指标</h3><div class="scroll"><table><thead><tr><th>执行</th><th>学生运行时间</th><th>工具调用</th><th>未标错 / 标错</th><th>输入 Token</th><th>输出 Token</th><th>其中推理</th><th>缓存读取</th><th>原生合计</th></tr></thead><tbody>'+''.join(metrics_rows)+'</tbody></table></div><p>工具未标错不代表命令成功或对目标有益；不计算整体有益调用率。原生合计含缓存读取，推理 Token 是输出的一部分，不能再次相加。费用未知。运行时间与发布等待时间不同；两轮均在30分钟上限前因502结束，不能归因为超时。</p>' if metrics_rows else ''
 portable=a.get('portableValidation');portable_html=''
 if portable:portable_html='<h3>可迁移用例与空间</h3><p>同一私有归档在 Linux 和 macOS 还原三个点，每端 '+e(portable['fileSHA256ChecksEachHost'])+' 项文件哈希核对一致。完整私有包 '+e(portable['archiveBytes'])+' 字节；基础 Git '+e(portable['baseBundleBytes'])+' 字节，基础加三个差异补丁 '+e(portable['gitBasePlusPatchesBytes'])+' 字节。基础是本任务18文件的最小提取工程，并非整个生产仓库。</p><p>包包含原始事实、冻结条件、私有判据和教师审核；原始轨迹和归档不公开，也不放入学生工作区。已验证选定源码与证据的语义还原，不包含 SDK、缓存、学生上下文、设备状态或整个物理 Capsule。</p>'
 section='<section id="frozen-cohort"><div class="report-kicker">FROZEN WHOLE-TASK REPEAT</div><h2>同一整题的冻结重复：与历史探索分开</h2><p>同一起点与任务，'+e(a['protocol']['agent'])+' / '+e(a['protocol']['model'])+' / thinking '+e(a['protocol']['thinking'])+' / '+e(a['protocol']['nativeBudgetMs']//1000)+'秒安全上限。high 指 Agent 原生设置记录，推理已产生；最终上游强度未逐请求独立审计，厂商权重版本未公开。两轮用于检查流程可复现性，不代表统计稳定性。无整题通过率。</p><div class="scroll"><table><thead><tr><th>执行</th><th>当前状态</th><th>本轮教师解题帮助</th><th>独立判定</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p>实际行为、学生交付声明、运行终态和正式发布分别判断；未发布不等于未执行，也不能判为通过。解析器测试通过不冒充新增持久化单元测试覆盖率。</p>'+metrics_html+portable_html+''.join(detail)+'<p><a href="frozen-cohort.json" download>下载冻结重复与审核事实</a></p></section>'
 page=page.replace('2026-10-25-v4','2026-10-25-v6').replace('探索性评测报告 v4','综合评测报告 v6').replace('agent-report-v4','agent-report-v6')
 page=page.replace('href="../2026-10-25-v3/">上一报告版本','href="../2026-10-25-v5/">上一报告版本')
 require('<section id="process">' in page,'existing report insertion anchor missing')
 for old,new in {'缺同协议独立重复；这里不是0%，也不是4/31。pass@k、pass^k、稳定性和置信区间暂不估计。': '历史31轮不组成独立重复；新增A2/B2已单列，两轮请求故障中断，不估计任务通过率、pass@k或统计稳定性。', '无合格同协议独立重复队列；不是0%，不可用4/31替代': '历史31轮不进入可比队列；A2/B2单列，不用阶段合格数替代能力通过率。', '没有同配置、同起点、无额外帮助的整题独立重复，不能估计整题通过率、pass@k/pass^k或置信区间。': 'A2/B2已完成同条件整题执行并正式发布；两次均在请求链路502时中断，不据此估计一般能力通过率或统计稳定性。', '最新自由输入与收尾阶段，不覆盖全部历史轮次': '本轮A2/B2冻结整题；不覆盖历史31轮的混合配置。', '历史混合；续跑继承产物与帮助上下文，不是统一预算组': '本轮同一干净起点、30分钟安全上限、无新增解题帮助；历史配置另列。', '本公开视图未核定完整OS、SDK、模拟器和工具版本': '本轮记录SDK 6.1.1（构建125）、Hvigor 6.24.4、构建Node 18.20.1；整机和模拟器完整版本未独立核定。', '冻结后可在同一任务上建立独立重复；不需要先扩到更多任务。': '本轮A2/B2已在独立冻结队列披露；历史缺口不倒填，不需要扩到更多任务。'}.items():page=page.replace(old,new)
 return page.replace('<section id="process">',section+'<section id="process">',1).replace('<p class="links">','<p class="links"><a href="#frozen-cohort">冻结整题重复</a>',1)

def frozen_main():
 p=argparse.ArgumentParser();p.add_argument('--frozen-reviews',type=Path,required=True);p.add_argument('--public-v4',type=Path,required=True);p.add_argument('--scanner',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();require(not args.output.exists(),'immutable output exists')
 data=frozen_cohort(json.loads((args.public_v4/'evaluation.json').read_text()),json.loads(args.frozen_reviews.read_text()));page=render_frozen(data,(args.public_v4/'index.html').read_text());spec=importlib.util.spec_from_file_location('scanner',args.scanner);scanner=importlib.util.module_from_spec(spec);spec.loader.exec_module(scanner);scanner.scan_public(data);scanner.scan_public(page)
 shutil.copytree(args.public_v4,args.output);(args.output/'evaluation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(args.output/'index.html').write_text(page);(args.output/'frozen-cohort.json').write_text(json.dumps(data['frozenCohort'],ensure_ascii=False,indent=2)+'\n');print(json.dumps({'historicalOperations':len(data['operations']),'separateFrozenAttempts':len(data['frozenCohort']['attempts']),'wholeTaskPassRate':None}))

if __name__=='__main__': main()
