// Original controller methods with an operator-controlled asynchronous submit seam.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = process.argv[2], mode = process.argv[3];
if (!['baseline','reference','wrong-reset'].includes(mode)) throw Error('Unknown mode');
const source = fs.readFileSync(path.join(root,'common/src/main/ets/component/FeedbackSheet.ets'),'utf8');
const slice = (a,b) => {
  const start=source.indexOf(a), end=source.indexOf(b,start);
  if(start<0 || end<0) throw Error('Pinned method boundaries changed');
  return source.slice(start,end).trim();
};
const original = slice('  private handleSubmit(): void','  private handleVoteClick(');
const resets = slice('  private resetSubmitStatus(): void','  @Builder');
const erase = s => s.replaceAll('private ','').replaceAll(': void','');
let submit = erase(original);
if(mode !== 'baseline') {
  submit=submit.replace('if (!this.feedbackData.canSubmit)', 'if (this.submitting || !this.feedbackData.canSubmit)')
    .replace('    SubmitInfoUtil.submitFeedbackInfo', '    this.submitting = true; this.submitError = null;\n    return SubmitInfoUtil.submitFeedbackInfo')
    .replace('      });','      }).catch(err => { this.submitError = err.message; '+
      (mode==='wrong-reset'?'this.resetAllStatus();':'')+' }).finally(() => { this.submitting = false; });');
}
const requests=[], chains=[], toasts=[];
const service={submitFeedbackInfo(params,data,selected) {
  let resolve,reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const then=promise.then.bind(promise);
  promise.then=(...args)=>{const chain=then(...args);chains.push(chain);chain.catch(()=>{});return chain;};
  requests.push({resolve,reject,input:JSON.parse(JSON.stringify({params,data,selected}))});
  return promise;
}};
const context={SubmitInfoUtil:service,Toast:{showToast:x=>toasts.push(x)},$r:x=>x,FeedbackType:{NONE:0}};
vm.createContext(context);
vm.runInContext('this.methods = ({'+submit+',\n'+erase(resets).replace(/}\s*resetAllStatus/, '},\nresetAllStatus')+'});',context);
const state={feedbackInitParams:{domainTitle:'test'},feedbackData:{canSubmit:true,listSelected:true,
  feedbackTypeStatus:1,feedbackInput:'reason',editStatus:true},feedbackListState:[true,false],
  bindFeedback:true,submitting:false,submitError:null};
Object.assign(state,context.methods);
async function run() {
  state.handleSubmit();state.handleSubmit();
  const onePendingRequest=requests.length===1;
  const retainedWhilePending=state.feedbackListState[0] && state.bindFeedback;
  for(const request of requests)request.reject(Error('controlled failure'));
  await Promise.allSettled(chains);await new Promise(resolve=>setImmediate(resolve));
  const retainedAfterFailure=state.feedbackListState[0] && state.feedbackData.feedbackInput==='reason' && state.bindFeedback;
  const failureObservable=state.submitError==='controlled failure';
  const releasedAfterFailure=!state.submitting;
  const before=requests.length;state.handleSubmit();
  const retryRequested=requests.length===before+1;
  for(const request of requests.slice(before))request.resolve();
  await Promise.allSettled(chains);await new Promise(resolve=>setImmediate(resolve));
  const resetAfterSuccess=state.feedbackListState.every(x=>!x) && !state.bindFeedback &&
    !state.feedbackData.canSubmit && state.feedbackData.feedbackTypeStatus===0;
  const after=requests.length;state.handleSubmit();
  const invalidInputBlocked=requests.length===after;
  const checks={onePendingRequest,retainedWhilePending,retainedAfterFailure,failureObservable,
    releasedAfterFailure,retryRequested,resetAfterSuccess,invalidInputBlocked};
  console.log(JSON.stringify({mode,pass:Object.values(checks).every(Boolean),checks,
    requests:requests.map(x=>x.input),toasts,originalMethod:original,adaptedMethod:submit,resetMethods:resets,
    adapter:'Type-erased original submit/reset methods; operator-controlled Promise service; rejected chains observed by Harness',
    backend:'SubmitInfoUtil is a resolved demonstration stub; injected failure does not claim a real backend',
    consumerBodiesExecuted:false,harmonyBuildQualified:false,uiErrorRenderingQualified:false}));
}
run().catch(err=>{console.error(err);process.exitCode=1;});
