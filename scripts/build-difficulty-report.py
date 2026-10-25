#!/usr/bin/env python3
"""Build a reviewed difficulty/reporting-readiness view; never dispatch or regrade."""
import argparse, collections, hashlib, html, importlib.util, json
from pathlib import Path

REQUIRED=['taskDefinitionRevision','initialStateRevision','agentBuild','modelVersion','thinkingPolicy','budgetManifest','toolEnvironmentManifest','oracleRevision','assistanceAudit','repeatGroup']
LABELS={'local_autonomy':'局部自主处理','assisted_progress':'帮助后推进','unfinished':'独立闭环未成立','not_assessed':'未测／证据不足'}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def readiness(record):
    missing=[field for field in REQUIRED if not record.get('frozenComparisonInputs',{}).get(field)]
    reasons=[]
    if record.get('mode')!='independent_task':reasons.append('探索续跑，不是冻结协议下的独立整题执行')
    if record.get('assistanceCondition')!='independently_audited_no_help':reasons.append('帮助／继承上下文未满足独立队列条件')
    if missing:reasons.append('冻结配置输入不完整')
    return {'reportingMetadataReady':not reasons,'missingFields':missing,'reasons':reasons,'meaning':'仅报告元数据完整性检查，不认证证据真实性，不授予执行权限，不判定学生通过'}

def help_ledger(private):
    ops=private['cases'][0]['operations'];lookup={o['operationId']:i for i,o in enumerate(ops,1)}
    summaries=[
      '提醒必须字段；原始上下文缺失对帮助效果归因有混杂。',
      '提供CLI名称标点兼容线索，未提供具体文件名。',
      '提示定位原始输入日志及程序化提取方法；未代改代码。',
      '优先把已有测试输入接成最小可运行闭环，再完善其他交付。',
      '澄清selector字段必须放既有裸ID，不能用描述或替代字段。',
      '优先保存基于已有事实的有效交付，未知项诚实保留。',
      '提示复用自己的既有工具证据，先保存最小交付，不重复设备采集。',
      '反馈输入追加、bounds表示、动态视口和增量保存方法。',
      '提供旧学生源码恢复材料及布局／存证提示，存在Harness混杂。',
      '通知Harness已恢复旧源码并限定剩余UI验证，未提供新在线解法。',
      '交付剩余旧示例回归范围，学生自行选择、定位和验证。']
    require(len(private['cases'][0]['teacherHelpEvents'])==len(summaries),'help inventory changed; review required')
    rows=[]
    for i,(h,summary) in enumerate(zip(private['cases'][0]['teacherHelpEvents'],summaries),1):
        d=h.get('actualDelivery',{});recipient=h.get('recipient',{})
        candidates=[h.get('operationId'),d.get('afterOperation'),d.get('operationId'),d.get('recipient',{}).get('operationId'),recipient.get('operationId')]
        targets=sorted({lookup[x] for x in candidates if x in lookup})
        types=h.get('types',h.get('helpTypes',[h['type']] if 'type' in h else []))
        rows.append({'id':f'H{i:02d}','summary':summary,'types':types,'boundRecipientRuns':targets,'bindingStatus':'original_operation_link' if targets else 'legacy_event_without_exact_public_recipient_binding','scoreWeight':None,'countsAsOneEvent':True})
    require(sum(bool(h['types']) for h in rows)==8,'typed event coverage changed')
    return rows

def validate_review(review,seqs,help_ids,dims):
    for row in review['rows']:
        require(row['state'] in LABELS,'unknown difficulty state')
        require(set(row['runs'])<=seqs and set(row['helpEvents'])<=help_ids,'missing review references')
        require(not row.get('wholeTaskIndependentPass',False),'local difficulty cannot assert whole-task pass')
        if row['state']=='not_assessed':
            require(row['dimensionEvidence'] in dims and row['confidence']=='not_assessed','unmeasured item needs scope evidence')
        else:
            require(row['runs'] and row['exposure']=='reached','observed difficulty needs reached execution evidence')
        if row['state']=='assisted_progress':require(row['helpEvents'],'assistance disclosure required')
        if row['state']=='local_autonomy':require(row.get('scope')!='whole_task','local scope required')
        require(row['confidence'] in ['case_observation','hypothesis','not_assessed'],'invalid confidence')

def build_data(private,public,review):
    commitment=hashlib.sha256(json.dumps(private,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(public['provenance']['privateReportSHA256']==commitment==review['evidenceReportCommitment'],'evidence commitment mismatch')
    require(public['schema']=='agentlab.public-evaluation.v2' and len(public['operations'])==31,'reviewed v2 input required')
    require(private['assessmentAuthority']['reportProducer']=='evaluation_system','student grade forbidden')
    require(review['author']=='evaluation_system_with_teacher_review','review author required')
    help_rows=help_ledger(private);help_ids={h['id'] for h in help_rows};seqs={o['sequence'] for o in public['operations']};dims={d['id'] for d in public['dimensions']}
    validate_review(review,seqs,help_ids,dims)
    public=json.loads(json.dumps(public));public.update(schema='agentlab.public-evaluation.v3',version='2026-10-25-v3')
    public['agentReport']['analysisRevision']='agent-report-v3';public['provenance']['publicProjectionPolicy']='allowlist-v3-difficulty-review';public['difficultyReview']=review;public['helpLedger']=help_rows;public['difficultyCounts']=dict(collections.Counter(x['state'] for x in review['rows']))
    run_rows=[]
    for original,op in zip(private['cases'][0]['operations'],public['operations']):
        require(original['phase']==op['phase'] and original['durationMs']==op['durationMs'],'row mismatch')
        run={'runKey':op['anchor'],'sequence':op['sequence'],'taskKey':'calendar','mode':'assisted_exploration','stage':op['phase'],'declaredModelId':original.get('modelId'),'reportedConfigurationLabel':op['model'],'nativeStatus':op['runtimeStatus'],'stageOutcome':op['outcome'],'durationMs':op['durationMs'],'toolCalls':op['toolCalls'],'boundHelpEvents':[h['id'] for h in help_rows if op['sequence'] in h['boundRecipientRuns']],'helpLinkCoverage':'exactly linked recipient subset only; missing link does not mean zero help','assistanceCondition':'mixed_or_inherited_context','frozenComparisonInputs':{field:None for field in REQUIRED},'reportEvidenceCommitment':commitment}
        run['readiness']=readiness(run);run_rows.append(run)
    require(not any(r['readiness']['reportingMetadataReady'] for r in run_rows),'historical exploration must not silently enter independent cohort')
    public['runRecords']=run_rows
    public['comparisonProtocol']={'schema':'agentlab.independent-comparison-inputs.v1','status':'draft_not_executable','requiredFields':REQUIRED,'readyHistoricalRuns':0,'reviewedHistoricalRuns':31,'selectionPolicy':review['selectionPolicy'],'scope':'报告所需输入清单；不是已冻结运行配置，不触发学生执行或新安装。','teacherAssistancePolicy':'探索阶段同样评测学生；帮助和继承上下文计入事实。正式无帮助队列须另行冻结。','gradingPolicy':'学生交付物由系统独立判定；独立整题、局部自主与帮助后进展分开。'}
    public['agentReport']['references'] += [
      {'name':'Terminal-Bench','url':'https://www.tbench.ai/','lesson':'分别披露model、Agent、资源与完成结果；本版导出运行记录，历史冻结配置仍待补。'},
      {'name':'TheAgentCompany','url':'https://the-agent-company.com/','lesson':'完整完成与检查点进展分开；难点审阅不冒充预先冻结的检查点得分。'},
      {'name':'WebArena','url':'https://webarena.dev/og/','lesson':'按任务意图检查真实环境状态；学生提交报告和文件存在不能独立证明完成。'},
      {'name':'GAIA','url':'https://huggingface.co/spaces/gaia-benchmark/leaderboard','lesson':'披露难度与运行选择规则；本版保留当前31轮历史，不选择最佳一轮冒充稳定性。'}]
    return public

CSS='''
.difficulty-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.difficulty-cards article{background:#fff;border:1px solid #dce5f0;border-radius:9px;padding:16px}.difficulty-cards b{font-size:25px;display:block;color:#3b608c}.difficulty-cards span{font-size:12px;color:#6e829c}.difficulty-card{background:#fff;border:1px solid #dce5f0;border-radius:10px;padding:22px;margin:16px 0}.difficulty-card h3{margin:8px 0 12px}.difficulty-card dl{display:grid;grid-template-columns:85px 1fr;gap:8px;font-size:14px}.difficulty-card dt{color:#8a98ab}.difficulty-card dd{margin:0}.state-tag{display:inline-block;border-radius:12px;background:#edf3fb;padding:3px 11px;font-size:12px;color:#5279a5}.state-local_autonomy{background:#e6f3ee;color:#407d68}.state-assisted_progress{background:#e8effa;color:#4c70a0}.state-unfinished{background:#fbefd9;color:#9a763a}.state-not_assessed{background:#edf0f4;color:#7d8899}.helper-note{font-size:12px;color:#7a8ca5}.readiness-banner{padding:17px 20px;border-radius:8px;background:#fff7e8;border:1px solid #f0e0c0}.readiness-banner strong{color:#896a32}.input-key{font-family:monospace;font-size:12px}.help-table{min-width:900px}.help-table td:first-child{white-space:nowrap}.download-links{display:flex;gap:18px;flex-wrap:wrap;margin:15px 0}.difficulty-controls{display:flex;align-items:center;gap:12px;background:#edf3f9;padding:12px;border-radius:7px;flex-wrap:wrap}.difficulty-controls select{padding:6px;font:inherit;border:1px solid #cdd9e8;border-radius:5px;background:#fff}.difficulty-controls button{padding:6px 12px;border:1px solid #cdd9e8;background:#fff;border-radius:5px;cursor:pointer}@media(max-width:700px){.difficulty-cards{grid-template-columns:1fr 1fr}.difficulty-card{padding:16px}.difficulty-card dl{grid-template-columns:70px 1fr}}
'''
def render(data,old_html):
    e=lambda x:html.escape(str(x));review=data['difficultyReview'];counts=data['difficultyCounts']
    cards=''.join('<article><b>'+str(counts.get(k,0))+'</b><span>'+LABELS[k]+'</span></article>' for k in LABELS)
    items=[]
    for x in review['rows']:
        refs=''.join('<a class="run-link" href="#run-'+str(n)+'">第'+str(n)+'轮</a>' for n in x['runs']) or '<a href="#capabilities">性能维度的范围说明</a>'
        helps=''.join('<a class="run-link" href="#help-'+h+'">'+h+'</a>' for h in x['helpEvents']) or '此条不据帮助缺链推定零帮助；继承上下文仍保留。'
        items.append('<article class="difficulty-card" data-difficulty="'+x['state']+'"><span class="state-tag state-'+x['state']+'">'+LABELS[x['state']]+'</span><h3>'+e(x['title'])+'</h3><dl>'+''.join('<dt>'+label+'</dt><dd>'+e(x[key])+'</dd>' for label,key in [('观察事实','facts'),('擅长的部分','strength'),('困难所在','barrier'),('原因判断','hypothesis')])+'</dl><p class="helper-note">其他解释：'+e('；'.join(x['alternatives']))+'。证据性质：'+('待验证解释' if x['confidence']=='hypothesis' else '当前切片未评测' if x['confidence']=='not_assessed' else '单任务行为观察')+'；不外推模型总体能力。</p><div>'+refs+'</div><p class="helper-note">帮助／背景：'+helps+'</p></article>')
    section='<section id="difficulty" class="protocol-section"><div class="report-kicker">03 / REACHED DIFFICULTIES AND ASSISTANCE</div><h2>难点到哪里了：局部自主、帮助后推进和未测分开</h2><p>'+e(review['denominator'])+'局部自主处理仍可能继承历史辅助上下文。下方筛选只改变审阅卡片，上方计数保持七条全体口径。</p><div class="difficulty-cards">'+cards+'</div><div class="difficulty-controls"><label for="difficulty-filter">难点状态</label><select id="difficulty-filter"><option value="all">全部7条审阅</option>'+''.join('<option value="'+k+'">'+v+'</option>' for k,v in LABELS.items())+'</select><button id="reset-difficulty">重置</button><strong id="difficulty-count" aria-live="polite">显示7 / 7条</strong></div>'+''.join(items)+'</section>'
    help_rows=[]
    for h in data['helpLedger']:
        targets=''.join('<a class="run-link" href="#run-'+str(n)+'">第'+str(n)+'轮</a>' for n in h['boundRecipientRuns']) or '历史事件保留；缺精确接收轮次绑定'
        help_rows.append('<tr id="help-'+h['id']+'"><td>'+h['id']+'</td><td>'+e(h['summary'])+'</td><td>'+e(' / '.join(h['types']) or '类型未标准化')+'</td><td>'+targets+'</td><td>未设定</td></tr>')
    helpsec='<section id="assistance-ledger"><h2>11个帮助／上下文事件逐项披露</h2><p>8个事件有类型、3个未标准化；一个事件可以包含多种类型。提示解法、恢复旧材料、限定剩余范围各自保留，不按标签数重复计分，不把它们等量扣分。权重可以后续版本化调整。</p><div class="scroll"><table class="help-table"><thead><tr><th>报告编号</th><th>公开摘要</th><th>原有类型</th><th>可精确绑定的接收轮次</th><th>评分权重</th></tr></thead><tbody>'+''.join(help_rows)+'</tbody></table></div><p class="helper-note">'+e(review['helpSummaryPolicy'])+'没有精确接收绑定，不代表没有发生帮助。探索阶段也在评测学生，不因出题／教师指导而免除帮助依赖。</p></section>'
    fieldlabels={'taskDefinitionRevision':'冻结的整题需求','initialStateRevision':'统一起点与还原身份','agentBuild':'Agent版本／构建','modelVersion':'模型版本','thinkingPolicy':'Thinking策略','budgetManifest':'预算与停止条件','toolEnvironmentManifest':'工具／SDK／设备清单','oracleRevision':'独立判据版本','assistanceAudit':'帮助与继承上下文审计','repeatGroup':'同条件重复组与选取规则'}
    readinesssec='<section id="protocol-ready" class="protocol-section"><div class="report-kicker">04 / COMPARABLE RUN INPUTS</div><h2>运行记录已统一，正式可比条件仍需冻结</h2><div class="readiness-banner"><strong>当前31轮：探索记录，不进入正式独立比较队列。</strong><p>这是数据资格说明，不是学生0分或31次失败。报告元数据检查也不是运行授权或证据真实性认证。</p></div><p>'+e(review['selectionPolicy'])+'</p><div class="scroll"><table><thead><tr><th>输入字段</th><th>现状与缺口</th></tr></thead><tbody>'+''.join('<tr><td>'+e(label)+'<br><span class="input-key">'+key+'</span></td><td>'+('最新阶段已有声明，历史尚未归一为同协议冻结输入' if key in ['agentBuild','modelVersion','thinkingPolicy'] else '已有帮助事实与部分接收绑定；尚不满足无帮助独立队列' if key=='assistanceAudit' else '尚未为正式比较队列冻结；历史观察不能自动填成已核定输入')+'</td></tr>' for key,label in fieldlabels.items())+'</tbody></table></div><div class="download-links"><a href="run-records.jsonl" download>下载31轮标准运行记录</a><a href="difficulty-review.json" download>下载难点审阅事实</a><a href="evaluation.json">完整公开结构化报告</a></div><p class="helper-note">标准记录保留原生状态、阶段结论、时长、工具覆盖与精确绑定帮助。缺少的冻结字段为null，不从模型标签、报告摘要或事后解释补造。冻结后可在同一任务上建立独立重复；不需要先扩到更多任务。</p></section>'
    reference='<section id="references"><h2>对照主流Agent评测：哪些已落实，哪些仍待测</h2><p>按领域代表性选取，不是热度排名；借鉴报告方法，不移植其他任务集的分数。</p><div class="scroll"><table><thead><tr><th>参考体系</th><th>在AL报告中的对应方式</th></tr></thead><tbody>'+''.join('<tr><td><a href="'+e(r['url'])+'" target="_blank" rel="noopener">'+e(r['name'])+'</a></td><td>'+e(r['lesson'])+'</td></tr>' for r in data['agentReport']['references'])+'</tbody></table></div><p class="helper-note">教师辅助探索和最终托管独立评测分别呈现；帮助前后进展不构成随机对照因果结论。</p></section>'
    text=old_html.replace('2026-10-25-v2','2026-10-25-v3').replace('探索性评测报告 v2','探索性评测报告 v3').replace('agent-report-v2','agent-report-v3')
    # Preserve the previous-version destination instead of pointing v3 to itself.
    text=text.replace('href="../2026-10-25/">上一报告版本','href="../2026-10-25-v2/">上一报告版本')
    text=text.replace('</style>',CSS+'</style>',1).replace('<section id="capabilities">',section+helpsec+readinesssec+'<section id="capabilities">',1)
    start=text.index('<section id="references">');end=text.index('</section>',start)+len('</section>');text=text[:start]+reference+text[end:]
    text=text.replace('<p class="links">','<p class="links"><a href="#difficulty">难点矩阵</a><a href="#assistance-ledger">帮助台账</a><a href="#protocol-ready">比较输入完整性</a>',1)
    text=text.replace('按阶段结果或关键词筛选；链接直达所讨论的执行轮次。','筛选仅作用于下表，上方汇总仍按全部31轮。链接直达所讨论的执行轮次。')
    return text

JS='''
// Difficulty filters affect reviewed cards only, not execution/campaign counts.
(() => {
 const choice=document.getElementById("difficulty-filter"), cards=[...document.querySelectorAll("[data-difficulty]")];
 function apply(){let count=0;for(const card of cards){card.hidden=choice.value!=="all"&&choice.value!==card.dataset.difficulty;if(!card.hidden)count++;}document.getElementById("difficulty-count").textContent=`显示${count} / ${cards.length}条`;}
 choice.addEventListener("change",apply);document.getElementById("reset-difficulty").addEventListener("click",()=>{choice.value="all";apply();});apply();
})();
'''
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--private-report',type=Path,required=True);ap.add_argument('--public-v2',type=Path,required=True);ap.add_argument('--review',type=Path,required=True);ap.add_argument('--scanner',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    require(not args.output.exists(),'version exists; do not overwrite')
    spec=importlib.util.spec_from_file_location('public_scanner',args.scanner);scanner=importlib.util.module_from_spec(spec);spec.loader.exec_module(scanner)
    data=build_data(json.loads(args.private_report.read_text()),json.loads((args.public_v2/'evaluation.json').read_text()),json.loads(args.review.read_text()));page=render(data,(args.public_v2/'index.html').read_text());scanner.scan_public(data);scanner.scan_public(page)
    args.output.mkdir(parents=True);(args.output/'index.html').write_text(page);(args.output/'evaluation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(args.output/'difficulty-review.json').write_text(json.dumps(data['difficultyReview'],ensure_ascii=False,indent=2)+'\n');(args.output/'run-records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data['runRecords']));(args.output/'report.js').write_text((args.public_v2/'report.js').read_text()+JS)
    print(json.dumps({'difficultyCounts':data['difficultyCounts'],'helpEvents':len(data['helpLedger']),'exactlyBoundHelpEvents':sum(bool(h['boundRecipientRuns']) for h in data['helpLedger']),'runRecords':len(data['runRecords']),'independentComparisonReady':0}))
if __name__=='__main__':main()
