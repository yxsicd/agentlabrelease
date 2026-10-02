// Explicit PushServiceManager Promise seam, not SDK delivery or ArkTS qualification.
'use strict';
const fs = require('node:fs'), vm = require('node:vm'), crypto = require('node:crypto');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const request = JSON.parse(fs.readFileSync(process.argv[2]));
const support = JSON.parse(fs.readFileSync(process.argv[3]));
const compilerPath = process.argv[4];
const modes = new Set(['denied','check-throws','pending','post-failure','concurrent',
  'retry-success','retry-post-failure','retry-token-failure','permission-pending','token-pending']);
if (request.schema !== 'agentlab.behavior_executor_request.v1' ||
    typeof request.submittedSource !== 'string' ||
    sha(request.submittedSource) !== request.submittedSourceSha256 ||
    sha(fs.readFileSync(compilerPath)) !== support.compilerSha256 ||
    support.adapter !== 'push-initialization-host-seam-v1' ||
    Object.keys(support).some(key => !['adapter','compilerSha256'].includes(key)))
  throw Error('Worker input binding differs');
// Validate the complete request before executing source or reporting rejection.
if (!Array.isArray(request.checks) || request.checks.length < 1 || request.checks.length > 128 ||
    new Set(request.checks.map(check => check.id)).size !== request.checks.length)
  throw Error('Checks absent, duplicate or excessive');
for (const check of request.checks) {
  if (typeof check.id !== 'string' || !check.id ||
      Object.keys(check).some(key => !['id','input'].includes(key)) ||
      !check.input || Object.keys(check.input).some(key => !['mode','observe'].includes(key)) ||
      !modes.has(check.input.mode) ||
      (Object.hasOwn(check.input,'observe') && check.input.observe !== 'outcome'))
    throw Error('Unsupported push input or evaluator expectations');
}
const ts = require(compilerPath);
const transformed = ts.transpileModule(request.submittedSource, {fileName:'PushServiceManager.ts', reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}});
const errors = transformed.diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error);
if (errors.some(d => !d.file || d.file.text !== request.submittedSource ||
    !Number.isInteger(d.code) || !Number.isInteger(d.start) || d.start < 0 ||
    d.start > request.submittedSource.length)) throw Error('Unbound compiler diagnostic');
const rejection = errors.length ? {sourceRejected:true,diagnostics:errors.map(d => ({
  code:d.code,start:d.start,length:d.length,message:ts.flattenDiagnosticMessageText(d.messageText,'\n')
}))} : null;
const deferred = () => { let resolve,reject; const promise = new Promise((a,b) => {resolve=a;reject=b;}); return {promise,resolve,reject}; };
const tick = () => new Promise(resolve => setImmediate(resolve));
async function observe(check) {
  if (rejection) return {id:check.id,input:check.input,actual:rejection};
  const mode=check.input.mode, postGate=deferred(), permissionGate=deferred(), tokenGate=deferred();
  let token=0,post=0,requests=0,settledCalls=0,phase=0,unhandled=0,errorLogs=0,rejectedCalls=0;
  const payloads=[];
  const listener=() => {unhandled++;};
  process.on('unhandledRejection',listener);
  try {
    const imports = {
      '@kit.AbilityKit':{},
      '@kit.NotificationKit':{notificationManager:{isNotificationEnabledSync(){
        if(mode==='check-throws') throw {message:'check-failed'};
        return !['denied','permission-pending'].includes(mode);
      },requestEnableNotification(){requests++;return mode==='denied' ? Promise.reject({message:'permission-denied'}) : permissionGate.promise;}}},
      '@kit.PushKit':{pushService:{getToken(){token++;
        if(mode==='token-pending' && phase===0) return tokenGate.promise;
        return mode==='retry-token-failure' && phase===0 ? Promise.reject({message:'token-failed'}) : Promise.resolve('token-'+phase);}}},
      '../util/Logger':{__esModule:true,default:{info(){},error(){errorLogs++;}}},
      './PushService':{PushService:{postPushToken(params){
        post++;
        // Observe submitted values without throwing into (and changing) source
        // failure handling. The independent contract decides payload correctness.
        payloads.push(typeof params?.pushToken === 'string' ? params.pushToken : null);
        return phase===0 ? postGate.promise : Promise.resolve(true);
      }}}
    };
    const module={exports:{}};
    const context=vm.createContext({module,exports:module.exports,require(name){
      if(!Object.hasOwn(imports,name)) throw Error('Unsupported import '+name);
      return imports[name];
    }});
    vm.runInContext(transformed.outputText,context,{timeout:1000});
    vm.runInContext('manager = exports.PushServiceManager.getInstance();',context,{timeout:1000});
    if(!vm.runInContext('manager === exports.PushServiceManager.getInstance()',context,{timeout:1000}))
      throw Error('Unsupported singleton export');
    const start=() => {
      const promise=vm.runInContext('manager.initPushServiceManager({});',context,{timeout:1000});
      if(!promise || typeof promise.then !== 'function') throw Error('Unsupported initialization return');
      promise.then(() => {settledCalls++;},() => {settledCalls++;rejectedCalls++;});
    };
    const concurrent=['concurrent','retry-success','retry-post-failure','retry-token-failure','permission-pending','token-pending'].includes(mode);
    start();if(concurrent) start();await tick();await tick();
    let actual;
    if(mode==='pending') actual={pending:settledCalls===0,post};
    else if(mode==='concurrent') actual={token,post,settledCalls};
    else if(mode==='token-pending') actual={token,post,settledCalls};
    else if(mode==='permission-pending') actual={requests,token,settledCalls};
    else if(mode==='denied'||mode==='check-throws') actual={token,post,settledCalls,unhandled};
    else {
      if(mode==='post-failure'||mode==='retry-post-failure') postGate.reject({message:'post-failed'});
      else postGate.resolve(true);
      await tick();await tick();
      if(mode.startsWith('retry-')) {phase=1;start();await tick();await tick();actual={token,post,settledCalls,unhandled};}
      else actual={settledCalls,unhandled};
    }
    if(check.input.observe==='outcome') actual={...actual,payloads:payloads.slice(),failureObserved:errorLogs>0||rejectedCalls>0};
    postGate.resolve(true);permissionGate.resolve();tokenGate.resolve('token-0');await tick();await tick();
    return {id:check.id,input:check.input,actual};
  } finally {process.removeListener('unhandledRejection',listener);}
}
(async() => {
  const observations=[];
  for(const check of request.checks) observations.push(await observe(check));
  console.log(JSON.stringify({id:request.id,originalSourceSha256:request.originalSourceSha256,
    submittedSource:request.submittedSource,submittedSourceSha256:request.submittedSourceSha256,observations}));
})().catch(error => {console.error(error.stack);process.exitCode=1;});
