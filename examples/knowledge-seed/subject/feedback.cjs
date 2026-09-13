// Execute submitted methods without reference substitutions. The service is a declared test seam.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require(process.env.AGENTLAB_ORACLE_TYPESCRIPT);
if(!process.env.AGENTLAB_SOURCE_PROBE)throw Error('Harness Rust source probe is not installed');
const root=process.argv[2],stage=Number(process.argv[3]);
if(![1,2].includes(stage))throw Error('Unsupported assessment stage');
try {
const source=fs.readFileSync(path.join(root,'common/src/main/ets/component/FeedbackSheet.ets'),'utf8');
const slice=(start,end)=>{const a=source.search(start),b=source.indexOf(end,a);if(a<0||b<0)throw Error('Actual method boundaries unavailable');return source.slice(a,b);};
const analysis=JSON.parse(require('node:child_process').execFileSync(process.env.AGENTLAB_SOURCE_PROBE,[path.join(root,'common/src/main/ets/component/FeedbackSheet.ets')],{maxBuffer:8*1024*1024}));
const properties=analysis.rows.filter(row=>row.kind==='property'&&row.owner==='FeedbackSheet');
const declaration=(name,type,value)=>properties.some(row=>row.name===name&&row.typeExpression===type&&value.includes(row.initializerExpression)&&row.decorators.includes('@State'));
const submitted=slice(/  private (?:async )?handleSubmit\(/,'  private handleVoteClick(');
const resets=slice(/  private resetSubmitStatus\(/,'  @Builder');
const code=ts.transpileModule('class Subject {\n'+submitted+resets+'\n}\nthis.Subject=Subject;', {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
const requests=[],toasts=[],chains=[];
const service={submitFeedbackInfo(params,data,selected){
 let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
 const then=promise.then.bind(promise);promise.then=(...args)=>{const chain=then(...args);chains.push(chain);chain.catch(()=>{});return chain;};
 requests.push({resolve,reject,input:JSON.parse(JSON.stringify([params,data,selected]))});return promise;
}};
const context={SubmitInfoUtil:service,Toast:{showToast:x=>toasts.push(x)},$r:x=>x,FeedbackType:{NONE:0}};vm.createContext(context);vm.runInContext(code,context);
const state=new context.Subject();Object.assign(state,{feedbackInitParams:{domainTitle:'test'},feedbackData:{canSubmit:true,listSelected:true,feedbackTypeStatus:1,feedbackInput:'reason',editStatus:true},feedbackListState:[true,false],bindFeedback:true,submitting:false,submitError:''});
const invoke=()=>{const result=state.handleSubmit();if(result&&typeof result.then==='function'){chains.push(result);result.catch(()=>{});}};
const settle=async()=>{await Promise.allSettled(chains);await new Promise(resolve=>setImmediate(resolve));};
async function run(){
 const initial=JSON.parse(JSON.stringify([state.feedbackInitParams,state.feedbackData,state.feedbackListState]));invoke();if(stage===2)invoke();
 const checks={reactivePendingDeclaration:declaration('submitting','boolean',['false']),reactiveErrorDeclaration:declaration('submitError','string',["''",'""']),sourceSyntaxParsed:!analysis.syntaxHasErrors,pendingObservable:state.submitting===true,retainedWhilePending:state.bindFeedback&&state.feedbackListState[0]&&state.feedbackData.feedbackInput==='reason',inputArgumentsPreserved:JSON.stringify(requests[0]?.input)===JSON.stringify(initial)};
 if(stage===2)checks.onePendingRequest=requests.length===1;
 for(const request of requests)request.reject(Error('controlled failure'));await settle();
 Object.assign(checks,{retainedAfterFailure:state.bindFeedback&&state.feedbackListState[0]&&state.feedbackData.feedbackInput==='reason'&&state.feedbackData.canSubmit,failureObservable:state.submitError==='controlled failure',releasedAfterFailure:state.submitting===false});
 const before=requests.length;invoke();checks.retryRequested=requests.length===before+1;checks.retryClearsError=state.submitError==='';
 for(const request of requests.slice(before))request.resolve();await settle();
 Object.assign(checks,{resetAfterSuccess:state.feedbackListState.every(x=>!x)&&!state.bindFeedback&&!state.feedbackData.canSubmit&&state.feedbackData.feedbackTypeStatus===0&&state.feedbackData.feedbackInput==='',releasedAfterSuccess:state.submitting===false});
 const after=requests.length;invoke();checks.invalidInputBlocked=requests.length===after;
 console.log(JSON.stringify({stage,pass:Object.values(checks).every(Boolean),checks,calls:requests.map(x=>({op:'submitFeedbackInfo',args:x.input})),toasts,submittedMethod:submitted,resetMethods:resets,sourceAnalysis:analysis,backend:'operator-controlled Promise replacing demonstration SubmitInfoUtil; no remote backend claim',actualMethodsExecuted:true,referenceTransformsApplied:false,uiRenderingQualified:false}));
}
run().catch(error=>console.log(JSON.stringify({stage,pass:false,error:String(error),referenceTransformsApplied:false})));
} catch(error) { console.log(JSON.stringify({stage,pass:false,error:String(error),referenceTransformsApplied:false})); }
