// Explicit ApplicationContext subscription seam, not Harmony framework delivery.
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const request = JSON.parse(fs.readFileSync(process.argv[2]));
const support = JSON.parse(fs.readFileSync(process.argv[3]));
const compilerPath = process.argv[4];
if (request.schema !== 'agentlab.behavior_executor_request.v1' ||
    sha(request.submittedSource) !== request.submittedSourceSha256 ||
    sha(fs.readFileSync(compilerPath)) !== support.compilerSha256 ||
    support.adapter !== 'application-environment-lifecycle-host-seam-v1') throw Error('Worker input binding differs');
const ts = require(compilerPath);
const transformed = ts.transpileModule(request.submittedSource, {fileName:'AbilityStage.ts', reportDiagnostics:true,
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
const sourceErrors = transformed.diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error);
// Only compiler diagnostics bound to submitted bytes are task observations.
// Compiler/configuration errors and unsupported loaders remain infrastructure failures.
if (sourceErrors.some(d => !d.file || d.file.text !== request.submittedSource ||
    !Number.isInteger(d.code) || !Number.isInteger(d.start) || d.start < 0 ||
    d.start > request.submittedSource.length)) throw Error('Unbound compiler diagnostic');
const rejection = sourceErrors.length ? {sourceRejected:true,diagnostics:sourceErrors.map(d => ({
  code:d.code,start:d.start,length:d.length,
  message:ts.flattenDiagnosticMessageText(d.messageText,'\n')
}))} : null;

async function observe(check) {
  const input = check.input;
  if (!Number.isInteger(input.firstCallbackId) || input.firstCallbackId < 0 || input.firstCallbackId > 65535 ||
      ![0,1].includes(input.failedRegistrations) || !Array.isArray(input.actions) ||
      input.actions.length < 1 || input.actions.length > 32) throw Error('Unsupported lifecycle input');
  for (const action of input.actions) {
    if (!(action.op==='create' || action.op==='destroy' ||
        (action.op==='configuration' && typeof action.language==='string' && action.language.length<=32 && [0,1].includes(action.colorMode)) ||
        (action.op==='memory' && Number.isInteger(action.level) && action.level>=0 && action.level<=5)))
      throw Error('Unsupported lifecycle action');
  }
  if (rejection) return {id:check.id,input,actual:rejection};
  let next = input.firstCallbackId, failures = input.failedRegistrations, invalidOffCalls = 0;
  const subscriptions = new Map(), logs = [];
  function ownerContext(owner) {
    return {
      on(event, callback) {
        if (failures) { failures--; const error = new Error('controlled registration failure'); error.code=401; throw error; }
        const id = next++;
        subscriptions.set(id,{owner,event,callback});
        return id;
      },
      off(event, id, callback) {
        const previous = subscriptions.get(id);
        if (previous && previous.owner===owner && previous.event===event) subscriptions.delete(id);
        else invalidOffCalls++;
        // This seam observes invalid cancellation instead of modelling SDK errors.
        if (typeof callback==='function') callback(undefined);
        return Promise.resolve();
      }
    };
  }
  const application = ownerContext('application');
  class Stage {
    constructor() { this.context={...ownerContext('stage'),getApplicationContext:()=>application}; }
    onCreate() {}
    onDestroy() {}
  }
  const modules={'@kit.AbilityKit':{AbilityStage:Stage},'@kit.BasicServicesKit':{}};
  const module={exports:{}};
  const context=vm.createContext({module,exports:module.exports,
    require(name) { if (!(name in modules)) throw Error('Unsupported import '+name); return modules[name]; },
    console:{info(...values){logs.push(values.join(' '));},error(){}}
  });
  vm.runInContext(transformed.outputText,context,{timeout:1000});
  if (typeof module.exports.default!=='function') throw Error('Unsupported default export');
  vm.runInContext('instance = new exports.default();',context,{timeout:1000});
  const steps=[];
  for (const action of input.actions) {
    const start=logs.length;
    if (action.op==='create' || action.op==='destroy') {
      context.operation=action.op==='create'?'onCreate':'onDestroy';
      await vm.runInContext('instance[operation]();',context,{timeout:1000});
    } else {
      context.callbacks=[...subscriptions.values()].filter(s=>s.owner==='application'&&s.event==='environment').map(s=>s.callback);
      if (action.op==='configuration' && typeof action.language==='string' && action.language.length<=32 && [0,1].includes(action.colorMode)) {
        context.configuration={language:action.language,colorMode:action.colorMode};
        await vm.runInContext('Promise.all(callbacks.map(callback=>callback.onConfigurationUpdated(configuration)));',context,{timeout:1000});
      } else if (action.op==='memory' && Number.isInteger(action.level) && action.level>=0 && action.level<=5) {
        context.memoryLevel=action.level;
        await vm.runInContext('Promise.all(callbacks.map(callback=>callback.onMemoryLevel(memoryLevel)));',context,{timeout:1000});
      } else throw Error('Unsupported lifecycle action');
    }
    const configuration=[],memory=[];
    for (const line of logs.slice(start)) {
      if (line.startsWith(support.configurationPrefix)) {
        const value=JSON.parse(line.slice(support.configurationPrefix.length));
        configuration.push([value.language,value.colorMode]);
      }
      if (line.startsWith(support.memoryPrefix)) memory.push(Number(line.slice(support.memoryPrefix.length)));
    }
    steps.push({active:[...subscriptions.values()].filter(s=>s.owner==='application'&&s.event==='environment').length,configuration,memory});
  }
  const markersIntact=[support.startMarker,support.endMarker].every(marker=>request.submittedSource.split(marker).length===2);
  return {id:check.id,input,actual:{steps,invalidOffCalls,markersIntact}};
}
(async()=>{
  if (!Array.isArray(request.checks)||request.checks.length<1||request.checks.length>128) throw Error('Checks absent or excessive');
  const observations=[];
  for (const check of request.checks) observations.push(await observe(check));
  console.log(JSON.stringify({id:request.id,originalSourceSha256:request.originalSourceSha256,
    submittedSource:request.submittedSource,submittedSourceSha256:request.submittedSourceSha256,observations}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
