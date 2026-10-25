#!/usr/bin/env python3
"""Enrich the existing public Calendar projection with explicit Agent-report methods.
No student dispatch, network access, private artifacts or new grades are produced.
"""
import argparse, collections, hashlib, html, importlib.util, json
from pathlib import Path

def require(ok, message):
    if not ok: raise ValueError(message)

def enrich(private, public):
    digest=hashlib.sha256(json.dumps(private,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(digest==public['provenance']['privateReportSHA256'],'public/private report commitment mismatch')
    require(private['assessmentAuthority']['reportProducer']=='evaluation_system','system assessment required')
    case=private['cases'][0]; ops=case['operations']
    require(len(ops)==31 and ops[-1]['phase']=='同任务旧示例按钮收尾','this adapter requires the reviewed 31-operation Calendar cut')
    require('Pi1.4.0' in case['configurationLimits'] and 'glm-5.3-flash' in case['configurationLimits'],'configuration review required for new cut')
    require(len(ops)==len(public['operations'])==private['operationCount'],'operation count mismatch')
    require(sum(o['durationMs'] for o in ops)==private['studentDurationMs'],'duration mismatch')
    require(dict(collections.Counter(o['outcome'] for o in ops))==private['outcomeCounts'],'outcome mismatch')
    metrics=[]
    for number,(original,row) in enumerate(zip(ops,public['operations']),1):
        require(original['phase']==row['phase'] and original['durationMs']==row['durationMs'],'row correspondence mismatch')
        tools=original.get('traceEvidence',{}).get('toolActivity',{})
        item={**row,'anchor':'run-'+str(number),'toolCalls':tools.get('toolCallCount'),'toolReturnedError':tools.get('returnedWithError'),'toolUnknown':tools.get('unknownResultCalls')}
        if item['toolCalls'] is not None:
            require(item['toolCalls']==tools['returnedWithoutError']+tools['returnedWithError']+tools['unknownResultCalls'],'tool row totals mismatch')
        metrics.append(item)
    covered=[o for o in metrics if o['toolCalls'] is not None]
    require(len(covered)==public['tools']['coveredOperations'],'tool coverage mismatch')
    require(sum(o['toolCalls'] for o in covered)==public['tools']['identifiedCalls'],'tool total mismatch')
    usage=[]
    for key in ['current509','current528','current531']:
        u=case['reportedProviderUsage'][key]
        seq=next(i for i,o in enumerate(ops,1) if o['operationId']==u['operationId'])
        t=u['tokens'] if u['tokens'] is not None else u['observedTokens']
        require(t['totalTokens']==sum(t[k] for k in ['input','output','cacheRead','cacheWrite']),'usage sum mismatch')
        usage.append({'sequence':seq,'coverage':u['status'],'tokens':{k:t[k] for k in ['input','output','cacheRead','cacheWrite','totalTokens']},'billedCost':None,'scope':'原生消息暴露的usage；包含缓存，非账单；partial不作完整执行总量'})
    result=json.loads(json.dumps(public))
    result.update(schema='agentlab.public-evaluation.v2',version='2026-10-25-v2',operations=metrics)
    result['agentReport']={
      'reportType':'教师辅助的单任务探索性评测 / 非托管排行榜',
      'evidenceCutoff':'2026-10-25','analysisRevision':'agent-report-v2',
      'configuration':{'agent':'Pi','agentVersion':'1.4.0','modelId':'glm-5.3-flash','thinking':'native确认开启 / high','effectiveProviderEffort':None,'apiProtocolVersion':None,'uniformBudgetCohort':False,'latestConfigurationScope':'最新自由输入及收尾阶段，不追溯覆盖全部历史轮次','modelLabelsAreNormalizedGroups':False,'environmentVersionManifest':'本公开视图未核定完整OS/SDK/模拟器及工具版本清单'},
      'sample':{'tasks':1,'operations':len(ops),'retainedPoints':public['portable']['retainedPoints'],'independentRepeatCohort':None,'taskPassRate':None,'passAtK':None,'passPowerK':None,'confidenceInterval':None,'reason':'同一任务的续跑、帮助和配置变化相互依赖；阶段标签不构成整题重复抽样'},
      'runtimeCounts':dict(collections.Counter(o['runtimeStatus'] for o in ops)),
      'executionDurationMs':sum(o['durationMs'] for o in ops),
      'durationScope':'原生参与者执行时长之和；包含超时轮次，不是应用耗时、纯推理时间或完整项目日历周期',
      'usageExamples':usage,'usageScope':'本版仅展开两轮observed和一轮partial的逐操作usage，不求全程token或美元总计；旧阶段聚合usage不混入。',
      'metricDefinitions':[
       {'id':'task_completion','name':'整题独立完成率','value':None,'unit':'率','denominator':'相同协议下的独立整题执行','reason':'无合格同协议独立重复队列；不是0%，不可用4/31替代'},
       {'id':'ui_checks','name':'受辅助UI历史证据检查','value':7,'denominator':7,'unit':'项','scope':'跨受辅助续跑累计，不是任务通过率'},
       {'id':'tool_coverage','name':'工具明细覆盖','value':19,'denominator':31,'unit':'轮','scope':'未覆盖轮次不是零调用'},
       {'id':'tool_return','name':'未显式报错返回','value':361,'denominator':373,'unit':'调用','scope':'仅工具返回状态，不等于语义成功或目标收益'},
       {'id':'useful_calls','name':'全程有收益调用率','value':None,'denominator':373,'unit':'率','reason':'只定向审阅8次，不足以外推全程'},
       {'id':'reliability','name':'多次重复稳定性','value':None,'denominator':None,'unit':'率','reason':'需相同任务/配置/预算/起点下预先冻结的独立重复'}],
      'failureExamples':[
       {'sequence':11,'category':'任务验证失败','finding':'原生completed，但阶段评测failed：完成运行不等于通过任务。'},
       {'sequence':28,'category':'上游故障 / 能力未评测','finding':'首次模型请求502；保留原生failed，评测记完成未判分，不记学生语义失败。'},
       {'sequence':22,'category':'Harness混杂','finding':'性能粗测伴随Harness恢复，阶段partial；不能把全部中断归咎于模型。'}],
      'capabilityEvidence':[[13,14],[30],[30,31]],
      'references':[
       {'name':'SWE-bench','url':'https://www.swebench.com/','lesson':'以任务实例为分母定义Resolved，并披露评测集合和运行环境；本报告分开整题与阶段结果。'},
       {'name':'OSWorld 2.0','url':'https://osworld-v2.xlang.ai/','lesson':'分开整题和部分完成，结合轨迹分析长程难点，并披露effort与资源；不移植其分数。'},
       {'name':'τ-bench','url':'https://taubench.com/','lesson':'可核验状态判定与重复可靠性；当前探索续跑不计算pass^k。'},
       {'name':'HAL','url':'https://hal.cs.princeton.edu/','lesson':'关注成本、usage和可复现轨迹；缺账单时不生成美元成本或性价比排名。'}],
      'remainingGaps':[
       '没有同配置、同起点、无额外帮助的整题独立重复，不能估计整题通过率、pass@k/pass^k或置信区间。',
       '最新Agent/model/thinking已明确，但历史预算、完整工具及SDK/模拟器版本尚未归一成可比配置组。',
       '全程token、有效调用率和账单没有完整核定；只呈现已绑定的样例和覆盖范围。',
       '教师帮助事实持续计入评价，权重尚未冻结；不输出装饰性总分或雷达分数。',
       '公开记录只有摘要与校验承诺；原始轨迹、原生操作ID和任务包由授权人员在私有侧复核。']}
    return result

EXTRA_CSS='''
.report-kicker{letter-spacing:1px;font-size:12px;color:#7084a1}.metric-note{font-size:13px;color:#6a7891}.protocol-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.protocol-grid .panel h3{margin-top:0}dl.spec{display:grid;grid-template-columns:125px 1fr;gap:8px 12px;font-size:14px}.spec dt{color:#8490a2}.spec dd{margin:0}.verdict{display:flex;gap:14px;align-items:flex-start;padding:18px;border-radius:10px;background:#fff8e9;border:1px solid #eedebd}.distribution{display:flex;height:24px;border-radius:6px;overflow:hidden;margin:14px 0}.distribution span{display:block;min-width:2px}.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px}.legend i{width:8px;height:8px;display:inline-block;border-radius:2px;margin-right:5px}.study-tools{display:flex;flex-wrap:wrap;gap:14px;align-items:center;background:#edf2f9;padding:14px;border-radius:8px;font-size:13px;margin:16px 0}.study-tools select,.study-tools input{padding:6px;border:1px solid #cfd9e8;background:#fff;border-radius:5px;font:inherit;max-width:220px}.study-tools button{padding:6px 12px;cursor:pointer;border:1px solid #c6d4e7;background:white;border-radius:5px}.run-link{font-size:12px;background:#eff4fb;border-radius:4px;padding:3px 7px;display:inline-block;margin:4px}tr:target{background:#fff4d9}tr[hidden]{display:none}.unknown{color:#986b27}.status-label{font-size:12px;color:#54709c}.trace-card{margin-bottom:14px}.revision{font-size:12px;color:#8b98ab}.protocol-section{padding-top:10px;border-top:1px solid #e0e6ee;margin-top:32px}.counter-row{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0}.counter-row span{background:#eff3f9;padding:8px 12px;border-radius:5px;font-size:13px}#run-table{min-width:1000px}#run-table th{position:sticky;top:0;background:#edf2f9}#run-table td:last-child{min-width:320px}.new-summary{background:#eaf1fb;border:1px solid #d4e2f6;border-radius:10px;padding:18px 22px;margin:20px 0}.dim-status{display:inline-block;margin-right:12px;font-size:12px;color:#7790af}@media(max-width:700px){.protocol-grid{grid-template-columns:1fr}.spec{grid-template-columns:100px 1fr!important}.study-tools{gap:8px}.study-tools label{display:flex;gap:7px;align-items:center}}
'''

def render(data, exporter):
    e=lambda value:html.escape(str(value));a=data['agentReport'];out=data['outcomeCounts'];colors={'independent_qualified':'#4b8c82','assisted_qualified':'#5d83b2','failed':'#ba6f69','partial':'#d1ab68','completed_ungraded':'#929eb1'}
    labels={'independent_qualified':'阶段独立合格','assisted_qualified':'帮助后阶段合格','failed':'阶段失败','partial':'部分验证','completed_ungraded':'能力未判分'}
    chips=''.join('<span><b>'+e(v)+'</b> '+labels[k]+'</span>' for k,v in out.items())
    bars=''.join('<span title="'+labels[k]+'：'+str(v)+'轮" style="flex:'+str(v)+';background:'+colors[k]+'"></span>' for k,v in out.items())
    legend=''.join('<span><i style="background:'+colors[k]+'"></i>'+labels[k]+' '+str(v)+'</span>' for k,v in out.items())
    config=a['configuration']
    protocol='''<section id="protocol" class="protocol-section"><div class="report-kicker">01 / EVALUATION PROTOCOL</div><h2>先明确测什么、怎么测，再解释结果</h2><div class="protocol-grid"><article class="panel"><h3>任务与独立验证</h3><dl class="spec"><dt>评测单元</dt><dd>1个Calendar提取ArkUI应用；31轮是同一任务的探索续跑</dd><dt>覆盖链路</dt><dd>规则输入／解析、测试运行、实际编译部署、设备交互、重启后状态验证</dd><dt>判定方</dt><dd>评测系统与教师；学生测试和报告是待核验交付物</dd><dt>当前证据</dt><dd>7/7受辅助UI检查；历史35/35测试；存在历史编译部署证据，范围各自独立</dd><dt>排除范围</dt><dd>完整Calendar项目、整个平台验收、10库100任务、模型总体能力排名</dd></dl></article><article class="panel"><h3>最新阶段配置卡</h3><dl class="spec"><dt>Code Agent</dt><dd>Pi 1.4.0</dd><dt>模型</dt><dd>glm-5.3-flash</dd><dt>Thinking</dt><dd>原生确认开启 / high；上游实际effort未核定</dd><dt>适用范围</dt><dd>最新自由输入与收尾阶段，不覆盖全部历史轮次</dd><dt>预算与起点</dt><dd>历史混合；续跑继承产物与帮助上下文，不是统一预算组</dd><dt>环境清单</dt><dd>本公开视图未核定完整OS、SDK、模拟器和工具版本</dd></dl></article></div><p class="metric-note">目标库commit和私有输入承诺见页尾。最新配置卡描述被测对象，不代表其他历史标签已经归一；没有API／账单核定的数据保持未知。</p></section>'''
    distribution='<section id="results" class="protocol-section"><div class="report-kicker">02 / RESULTS WITH DENOMINATORS</div><h2>31轮探索有进展，不能换算成整题通过率</h2><div class="verdict"><b>整题独立完成率：—</b><span>缺同协议独立重复；这里不是0%，也不是4/31。pass@k、pass^k、稳定性和置信区间暂不估计。</span></div><h3>阶段结果的次数分布</h3><div class="distribution" role="img" aria-label="'+e('；'.join(labels[k]+str(v)+'轮' for k,v in out.items()))+'">'+bars+'</div><div class="legend">'+legend+'</div><p class="metric-note">分母：31次历史执行操作。相互依赖的续跑和帮助后阶段不构成31道独立试题。各颜色表示次数，不是能力得分。历史“阶段失败”分组也含上游故障（如第15轮502），不是7次学生能力失败。</p><div class="counter-row"><span>原生完成 17轮</span><span>原生超时 11轮</span><span>原生失败 3轮</span><span>累计参与者时长 '+f"{a['executionDurationMs']/60000:.1f}"+' 分钟</span></div><p class="metric-note">原生状态与任务判分分开：运行结束不等于答题正确，运行失败也可能来自上游或Harness。累计时长包含超时轮次，不代表单题独立完成时间或应用性能。</p></section>'
    definitions=''.join('<tr><td>'+e(m['name'])+'</td><td>'+('—' if m['value'] is None else e(m['value'])+' / '+e(m['denominator']))+'</td><td>'+e(m.get('scope',m.get('reason','')))+'</td></tr>' for m in a['metricDefinitions'])
    methodology='<section id="definitions"><h2>指标字典：每个数字都带分母和范围</h2><div class="scroll"><table><thead><tr><th>指标</th><th>观察值</th><th>口径与限制</th></tr></thead><tbody>'+definitions+'</tbody></table></div></section>'
    usage=''.join('<tr><td><a href="#run-'+str(u['sequence'])+'">第'+str(u['sequence'])+'轮</a></td><td>'+('完整暴露usage' if u['coverage']=='observed' else '部分观察，非完整总量')+'</td>'+''.join('<td>'+f"{u['tokens'][k]:,}"+'</td>' for k in ['input','output','cacheRead','totalTokens'])+'<td>—</td></tr>' for u in a['usageExamples'])
    costs='<section id="cost"><h2>资源成本：展示可核定usage，不估造账单</h2><div class="scroll"><table><thead><tr><th>执行</th><th>覆盖</th><th>输入</th><th>输出</th><th>缓存读取</th><th>暴露总token</th><th>美元费用</th></tr></thead><tbody>'+usage+'</tbody></table></div><p class="metric-note">'+e(a['usageScope'])+' 总token包含缓存，不能视为新生成token。reasoning未额外加到output；未取得真实账单，不做成本排名。</p></section>'
    failures=''.join('<article class="panel trace-card"><span class="status-label">'+e(x['category'])+'</span><p>'+e(x['finding'])+'</p><a class="run-link" href="#run-'+str(x['sequence'])+'">核对第'+str(x['sequence'])+'轮 →</a></article>' for x in a['failureExamples'])
    diagnosis='<section id="attribution"><h2>先区分学生、Harness和上游，再讨论能力</h2><div class="grid">'+failures+'</div><p class="metric-note">上述是有证据的案例，不是对31轮作穷尽故障归因。没有证据的根因保持未知；帮助与混杂因素不会因最终发布成功而消失。</p></section>'
    rows=[]
    for o in data['operations']:
        tools='未提取' if o['toolCalls'] is None else str(o['toolCalls'])+'（显式错 '+str(o['toolReturnedError'])+'）'
        rows.append('<tr id="'+o['anchor']+'" data-result="'+e(o['outcome'])+'"><td>'+str(o['sequence'])+'</td><td>'+e(o['phase'])+'</td><td>'+e(o['model'])+'</td><td>'+e(o['runtimeStatus'])+'</td><td>'+labels[o['outcome']]+'</td><td>'+f"{o['durationMs']/1000:.3f}"+'</td><td>'+tools+'</td><td>'+e(o['finding'])+'</td></tr>')
    history='<section id="history" class="protocol-section"><div class="report-kicker">05 / INSPECTABLE EXECUTION EVIDENCE</div><h2>逐轮证据台账</h2><p>按阶段结果或关键词筛选；链接直达所讨论的执行轮次。显示的是系统摘要，不是原始私有轨迹。</p><div class="study-tools"><label>阶段结果 <select id="outcome-filter"><option value="all">全部31轮</option>'+''.join('<option value="'+k+'">'+labels[k]+'</option>' for k in out)+'</select></label><label>查找 <input id="run-search" type="search" placeholder="阶段、模型或观察关键词"></label><button id="reset-runs">重置筛选</button><strong id="visible-runs" aria-live="polite">显示31 / 31轮</strong></div><div class="scroll"><table id="run-table"><thead><tr><th>轮次</th><th>阶段</th><th>历史配置标签</th><th>原生状态</th><th>阶段评价</th><th>秒</th><th>调用数</th><th>观察与证据边界</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p id="no-runs" hidden>没有匹配记录。请重置筛选；空结果不表示没有执行。</p></section>'
    gaps='<section id="gaps"><h2>还缺什么，才能成为可比较的正式评测</h2><ol>'+''.join('<li>'+e(g)+'</li>' for g in a['remainingGaps'])+'</ol></section>'
    refs='<section id="references"><h2>借鉴哪些Agent报告方法</h2><p>只借鉴报告方法，不移植其他基准的分数、难度或通过率。当前仍是教师辅助探索报告，未来托管独立评测应另建冻结队列。</p><div class="scroll"><table><thead><tr><th>参考</th><th>落实到本报告</th></tr></thead><tbody>'+''.join('<tr><td><a href="'+e(x['url'])+'" target="_blank" rel="noopener">'+e(x['name'])+'</a></td><td>'+e(x['lesson'])+'</td></tr>' for x in a['references'])+'</tbody></table></div><p class="revision">方法审视：2026-10-25；证据截止不随页面重建虚增。参考基准不是对本报告的认证。</p></section>'
    text=exporter.page(data)
    text=text.replace('</style>','\n'+EXTRA_CSS+'</style>',1)
    text=text.replace('<section id="capabilities">',protocol+distribution+methodology+costs+diagnosis+'<section id="capabilities">',1)
    for claim,seqs in zip(data['capabilityClaims'],a['capabilityEvidence']):
        needle='<p>'+e(claim['finding'])+'</p>'
        links=''.join('<a class="run-link" href="#run-'+str(seq)+'">证据：第'+str(seq)+'轮</a>' for seq in seqs)
        text=text.replace(needle,needle+links,1)
    start=text.index('<section id="history">');end=text.index('</section>',start)+len('</section>');text=text[:start]+history+gaps+refs+text[end:]
    text=text.replace('<p class="links">','<p class="links"><a href="#protocol">协议与配置</a><a href="#results">结果口径</a><a href="#cost">资源成本</a><a href="#gaps">剩余差距</a>',1)
    text=text.replace('公开评测视图 ·','探索性评测报告 v2 ·',1)
    text=text.replace('<footer>AgentLab','<footer>证据截止：2026-10-25 · 方法版本 agent-report-v2 · <a href="../2026-10-25/">上一报告版本</a><br>AgentLab',1)
    text=text.replace('</html>','<script src="report.js"></script></html>')
    return text

REPORT_JS='''"use strict";
(() => {
 const select=document.getElementById("outcome-filter"), search=document.getElementById("run-search"), rows=[...document.querySelectorAll("#run-table tbody tr")];
 function filter(){let n=0;const term=search.value.trim().toLowerCase();for(const row of rows){const visible=(select.value==="all"||select.value===row.dataset.result)&&row.textContent.toLowerCase().includes(term);row.hidden=!visible;if(visible)n++;}document.getElementById("visible-runs").textContent=`显示${n} / ${rows.length}轮`;document.getElementById("no-runs").hidden=n!==0;}
 function reset(){select.value="all";search.value="";filter();}
 function reveal(){if(/^#run-\\d+$/.test(location.hash)){reset();document.getElementById(location.hash.slice(1))?.scrollIntoView({block:"center"});}}
 select.addEventListener("change",filter);search.addEventListener("input",filter);document.getElementById("reset-runs").addEventListener("click",reset);addEventListener("hashchange",reveal);filter();reveal();
})();
'''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--private-report',type=Path,required=True);ap.add_argument('--public-report',type=Path,required=True);ap.add_argument('--exporter',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    require(not args.output.exists(),'version directory exists; never overwrite')
    spec=importlib.util.spec_from_file_location('existing_exporter',args.exporter);ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    data=enrich(json.loads(args.private_report.read_text()),json.loads(args.public_report.read_text()));text=render(data,ex);ex.scan_public(data);ex.scan_public(text)
    args.output.mkdir(parents=True);(args.output/'evaluation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(args.output/'index.html').write_text(text);(args.output/'report.js').write_text(REPORT_JS)
    print(json.dumps({'operations':len(data['operations']),'runtimeCounts':data['agentReport']['runtimeCounts'],'derivedOnly':True,'reportBytes':len(text.encode()),'publicJSONBytes':(args.output/'evaluation.json').stat().st_size}))
if __name__=='__main__':main()
