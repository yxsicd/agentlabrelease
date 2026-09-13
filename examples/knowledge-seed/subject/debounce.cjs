// Execute submitted debounce and real component click handlers; controlled clock.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),cp=require('node:child_process');
const ts=require(process.env.AGENTLAB_ORACLE_TYPESCRIPT),root=process.argv[2],stage=Number(process.argv[3]);
if(![1,2].includes(stage))throw Error('Unsupported stage');
try {
const analyze=f=>JSON.parse(cp.execFileSync(process.env.AGENTLAB_SOURCE_PROBE,[f],{maxBuffer:8*1024*1024}));
const utility=path.join(root,'common/src/main/ets/util/DebounceUtil.ets'),caller=path.join(root,'features/componentlibrary/src/main/ets/view/ComponentBaseView.ets');
const analyses=[analyze(utility),analyze(caller)],raw=fs.readFileSync(caller);
const methods=analyses[1].rows.filter(r=>r.kind==='symbol'&&r.owner==='ComponentBaseView'&&['jumpComponentDetailView','jumpCodelabDetailView'].includes(r.symbol)).map(r=>raw.subarray(r.span.startByte,r.span.endByte).toString());
let now=0;const events=[];class ClockDate extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
const context={exports:{},Date:ClockDate,ComponentListEventType:{JUMP_DETAIL_DETAIL:'detail'}};vm.createContext(context);
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
vm.runInContext(compile(fs.readFileSync(utility,'utf8')),context);context.DebounceUtil=context.exports.DebounceUtil;
vm.runInContext(compile('class Caller {\n'+methods.join('\n')+'\n}\nthis.Caller=Caller;'),context);
const state=new context.Caller();state.viewModel={sendEvent:e=>events.push({time:now,...e})};
const a={id:'a'},b={id:'b'};const first=state.jumpComponentDetailView(a),second=state.jumpComponentDetailView(b);
first();second();const checks={sourceSyntaxParsed:analyses.every(a=>!a.syntaxHasErrors),actualCallerMethodsFound:methods.length===2,firstCallAtZero:events.some(e=>e.param===a),independentHandlers:events.length===2,callerPayload:events.every(e=>e.type==='detail')};
now=100;first();checks.sameHandlerSuppressed=events.length===2;
now=1000;first();checks.exactBoundaryAccepted=events.filter(e=>e.param===a).length===2;
const card={componentContents:[{id:'card'}]};state.jumpCodelabDetailView(card)();checks.codelabForwarded=events.at(-1)?.param===card.componentContents[0];
let defaults=0;const defaultHandler=context.DebounceUtil.debounce(()=>defaults++);defaultHandler();now=1999;defaultHandler();checks.defaultWaitSuppression=defaults===1;now=2000;defaultHandler();checks.defaultWaitBoundary=defaults===2;
if(stage===2){let count=0;const handler=context.DebounceUtil.debounce(()=>count++,100);handler();now=2050;handler();now=2099;handler();now=2100;handler();checks.suppressedClicksDoNotExtendWindow=count===2;now=2150;handler();now=2200;handler();checks.acceptedClicksStartNextWindow=count===3;}
console.log(JSON.stringify({stage,pass:Object.values(checks).every(Boolean),checks,events,submittedMethods:methods,submittedUtilitySource:fs.readFileSync(utility,'utf8'),sourceAnalyses:analyses,actualMethodsExecuted:true,callerBodyExecuted:true,referenceTransformsApplied:false,adapter:'Submitted utility and two submitted click handlers; controlled Date and viewModel event sink',uiRenderingQualified:false}));
}catch(error){console.log(JSON.stringify({stage,pass:false,error:String(error),referenceTransformsApplied:false}));}
