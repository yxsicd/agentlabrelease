// Submitted lifecycle + shared breakpoint implementation; operator timer/enum seam.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),cp=require('node:child_process');
const ts=require(process.env.AGENTLAB_ORACLE_TYPESCRIPT);
const root=process.argv[2],stage=Number(process.argv[3]);
if(![1,2].includes(stage))throw Error('Unsupported loading stage');
try {
const file=path.join(root,'common/src/main/ets/view/DelayedLoadingView.ets');
const helper=path.join(root,'common/src/main/ets/util/BreakpointSystem.ets');
const raw=fs.readFileSync(file),utility=fs.readFileSync(helper,'utf8');
const analyze=f=>JSON.parse(cp.execFileSync(process.env.AGENTLAB_SOURCE_PROBE,[f],{maxBuffer:8*1024*1024}));
const analysis=analyze(file),utilityAnalysis=analyze(helper);
const methods=analysis.rows.filter(r=>r.kind==='symbol'&&r.owner==='DelayedLoadingView'&&r.syntaxKind==='method_definition'&&r.symbol!=='build').map(r=>raw.subarray(r.span.startByte,r.span.endByte).toString());
const properties=analysis.rows.filter(r=>r.kind==='property'&&r.owner==='DelayedLoadingView');
const declaration=(name,type,initial,decorator)=>properties.some(r=>r.name===name&&r.typeExpression===type&&r.initializerExpression===initial&&(!decorator||r.decorators.includes(decorator)));
const timers=new Map(),calls=[];let next=0;
const context={exports:{},WidthBreakpoint:{WIDTH_XS:'xs',WIDTH_SM:'sm',WIDTH_MD:'md',WIDTH_LG:'lg',WIDTH_XL:'xl'},
 setTimeout:(fn,delay)=>{const id=++next;timers.set(id,{fn,delay});calls.push({op:'setTimeout',id,delay,callbackSource:fn.toString()});return id;},clearTimeout:id=>{calls.push({op:'clearTimeout',id});timers.delete(id);}};
vm.createContext(context);
const compile=code=>ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
vm.runInContext(compile(utility),context);context.BreakpointType=context.exports.BreakpointType;
const bindings=analysis.rows.filter(r=>r.kind==='binding'&&r.owner==='').map(r=>r.bindingKind+' '+raw.subarray(r.span.startByte,r.span.endByte).toString()+';');
vm.runInContext(compile(bindings.join('\n')),context);
vm.runInContext(compile('class Subject {\n'+methods.join('\n')+'\n}\nthis.Subject=Subject;'),context);
const state=new context.Subject();Object.assign(state,{showLoading:false,delayTimer:-1,breakpoint:'sm',delayThreshold:350});
const invoke=name=>state[name]();
invoke('aboutToAppear');const first=state.delayTimer;
const checks={reactiveVisibilityDeclaration:declaration('showLoading','boolean','false','@State'),timerInitialDeclaration:declaration('delayTimer','number','-1'),sourceSyntaxParsed:!analysis.syntaxHasErrors&&!utilityAnalysis.syntaxHasErrors,smallDelay:timers.get(first)?.delay===350,initialHidden:state.showLoading===false};
const due=timers.get(first);timers.delete(first);calls.push({op:'fire',id:first});due.fn();checks.visibleAfterDelay=state.showLoading===true;
invoke('aboutToAppear');checks.visibilityReset=state.showLoading===false;
const prior=state.delayTimer;invoke('aboutToAppear');checks.oldTimerCancelled=!timers.has(prior);checks.onePendingTimer=timers.size===1;
invoke('aboutToDisappear');checks.cancelledOnDisappear=timers.size===0;checks.timerHandleReleased=state.delayTimer===-1;
const mapping={xs:350,sm:350,md:400,lg:400,xl:400};checks.allKnownDelays=true;
for(const [bp,delay] of Object.entries(mapping)){state.breakpoint=bp;invoke('aboutToAppear');checks.allKnownDelays&&=timers.get(state.delayTimer)?.delay===delay;invoke('aboutToDisappear');}
const values=new context.BreakpointType({sm:11,md:22,lg:33});checks.optionalBreakpointFallback=values.getValue('xs')===11&&values.getValue('xl')===33;
if(stage===2){checks.unknownHelperFallback=values.getValue('unknown')===11;state.breakpoint='unknown';invoke('aboutToAppear');checks.unknownLoadingDelay=timers.get(state.delayTimer)?.delay===350;invoke('aboutToDisappear');}
const caller=analyze(path.join(root,'common/src/main/ets/view/LoadingView.ets'));
checks.loadingCallerUsesSharedHelper=caller.rows.some(r=>r.kind==='module-reference'&&r.specifier==='../util/BreakpointSystem');
console.log(JSON.stringify({stage,pass:Object.values(checks).every(Boolean),checks,calls,submittedMethods:methods,submittedBreakpointSource:utility,sourceAnalyses:[analysis,utilityAnalysis,caller],actualMethodsExecuted:true,referenceTransformsApplied:false,adapter:'Actual submitted lifecycle and BreakpointType bodies; operator timer scheduler and WidthBreakpoint enum values',callerBodyExecuted:false,uiRenderingQualified:false}));
}catch(error){console.log(JSON.stringify({stage,pass:false,error:String(error),referenceTransformsApplied:false}));}
