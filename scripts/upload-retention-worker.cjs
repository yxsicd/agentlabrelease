// Explicit type-erased upload/retention host seam. Not Harmony/RDB qualification.
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
    sha(support.modelSource) !== support.modelSourceSha256 ||
    support.adapter !== 'upload-retention-host-seam-v1') throw Error('Worker input binding differs');
const ts = require(compilerPath);
function transpile(source, name) {
  const result = ts.transpileModule(source, {fileName: name, reportDiagnostics: true,
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}});
  if (result.diagnostics.some(d => d.category === ts.DiagnosticCategory.Error)) throw Error('Unsupported source');
  return result.outputText;
}
const modelModule = {exports: {}};
vm.runInNewContext(transpile(support.modelSource, 'TrackModel.ts'),
  {module: modelModule, exports: modelModule.exports}, {timeout: 1000});
async function observe(check) {
  const {count, upload} = check.input;
  if (!Number.isInteger(count) || count < 0 || count > 1001 || !['true','false','reject'].includes(upload)) throw Error('Unsupported input');
  let tick, deleted = 0, posted = 0;
  let records = Array.from({length: count}, (_,id) => ({id, eventType:'CLICK'}));
  const table = {queryAll: async () => records.slice(), deleteTrackData: async () => {deleted++; records=[];}};
  const service = {postTrackData: async () => {posted++; if (upload === 'reject') throw Error('controlled rejection'); return upload === 'true';}};
  const modules = {
    '@kit.ArkUI': {}, '@kit.AbilityKit': {}, '@kit.BasicServicesKit': {deviceInfo:{}},
    '../constant/CommonEnums': {StorageKey:{}}, '../model/PageEnum': {PageEnum:{MAIN_PAGE:'main'}},
    '../model/BundleInfoData': {}, '../model/TrackModel':modelModule.exports,
    '../storagemanager/PreferenceManager': {}, '../storagemanager/rdb/TrackTable': {default:function(){}},
    '../util/DateFormatUtil': {}, '../util/Logger': {default:{info(){}}}, './TrackService': {TrackService:service}
  };
  const module = {exports:{}};
  const context = {module,exports:module.exports, require(name) {
    if (!(name in modules)) throw Error('Unsupported import '+name); return modules[name];
  }, setInterval(fn,period) {if (period!==60000) throw Error('Interval changed');tick=fn;return 1;},clearInterval(){},AppStorage:{}};
  vm.runInNewContext(transpile(request.submittedSource,'TrackManager.ts'),context,{timeout:1000});
  const type = module.exports.TrackManager;
  type.trackTable=table;
  const instance=type.getInstance();
  instance.trackCommonData={}; instance.startReporting(60000);
  if (typeof tick!=='function') throw Error('No reporting tick');
  tick(); await new Promise(resolve=>setImmediate(resolve));
  return {id:check.id,input:check.input,actual:[posted,deleted,records.length]};
}
(async()=>{
  if (!Array.isArray(request.checks) || request.checks.length<1 || request.checks.length>128) throw Error('Checks absent or excessive');
  const observations=[];
  for (const check of request.checks) observations.push(await observe(check));
  console.log(JSON.stringify({id:request.id,originalSourceSha256:request.originalSourceSha256,
    submittedSource:request.submittedSource,submittedSourceSha256:request.submittedSourceSha256,observations}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
