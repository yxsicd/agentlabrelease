// Candidate discovery probe: execute four submitted modules, not a reference rewrite.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),cp=require('node:child_process'),crypto=require('node:crypto');
const ts=require(process.env.AGENTLAB_ORACLE_TYPESCRIPT),root=process.argv[2],stage=Number(process.argv[3]||2);if(![1,2].includes(stage))throw Error('Unsupported stage');
const files={manager:'common/src/main/ets/storagemanager/PreferenceManager.ets',helper:'common/src/main/ets/storagemanager/PreferenceCacheHelper.ets',service:'features/devpractices/src/main/ets/service/SampleService.ets',model:'features/devpractices/src/main/ets/model/SampleModel.ets'};
(async()=>{
 const sources=Object.fromEntries(Object.entries(files).map(([key,file])=>[key,fs.readFileSync(path.join(root,file),'utf8')]));
 const analyses=Object.fromEntries(Object.entries(files).map(([key,file])=>[key,JSON.parse(cp.execFileSync(process.env.AGENTLAB_SOURCE_PROBE,[path.join(root,file)],{maxBuffer:8*1024*1024}))]));
 const ticks=async()=>{for(let n=0;n<30;n++)await Promise.resolve();};
 async function trial(entry,rejectFlush=false,networkFailure=false,putFailure=false){
  const events=[],logs=[],data={currentPage:1,pageSize:30,data:{sampleCategories:[]}},store=new Map([['page',JSON.stringify({'neighbor':{id:'keep'},'1_30':{currentPage:1,pageSize:30,data:{sampleCategories:[]},cached:true}})]]);let settle;
  const flush=new Promise((resolve,reject)=>{settle=()=>{events.push(rejectFlush?'flush-rejected':'flush-committed');rejectFlush?reject(Error('controlled flush failure')):resolve();};});
  const preferences={putSync:(key,value)=>{events.push('put');if(putFailure)throw Error('controlled put failure');store.set(key,value);},hasSync:key=>store.has(key),getSync:key=>store.get(key),flush:()=>{events.push('flush-started');return flush;}};
  const logger={error:(...args)=>logs.push(args),info:()=>{}};
  const loaded={};const common={Logger:logger,ImageKnifeUtil:{preloadImg:()=>{}},TriggerEnums:{SAMPLE_PAGE:'page'},HmosRequest:{getInstance:()=>({request:async()=>{events.push('network');if(networkFailure)throw Error('controlled network failure');return data;}})}};
  function load(key){const context={exports:{},AppStorage:{get:()=>({getHostContext:()=>({})})},require:name=>{
   if(name==='@kit.ArkData')return {preferences:{getPreferencesSync:()=>preferences}};
   if(name==='@kit.BasicServicesKit')return {deviceInfo:{deviceType:'phone',sdkApiVersion:23}};
   if(name==='@ohos/common')return common;
   if(name==='@ohos/commonbusiness')return {};
   if(name.endsWith('CommonEnums'))return {StorageKey:{UI_CONTEXT:'ui'}};
   if(name.endsWith('/Logger'))return {default:logger};
   if(name.endsWith('/PreferenceManager'))return loaded.manager;
   if(name.endsWith('/SampleService'))return loaded.service;
   throw Error('Unmodeled runtime import '+name);
  }};vm.createContext(context);vm.runInContext(ts.transpileModule(sources[key],{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,context,{filename:files[key]});return loaded[key]=context.exports;}
  load('manager');load('helper');common.PreferenceCacheHelper=loaded.helper.PreferenceCacheHelper;load('service');load('model');
  const operations={helper:()=>loaded.helper.PreferenceCacheHelper.setSubValue('page','1_30',data),service:()=>new loaded.service.SampleService().setSamplePageToPreference(data),model:()=>loaded.model.SampleModel.getInstance().getSamplePage(1,30)};
  let settled=false,outcome,value;Promise.resolve(operations[entry]()).then(result=>{settled=true;outcome='resolved';value=result;events.push('caller-resolved');},error=>{settled=true;outcome='rejected';events.push('caller-rejected');});
  await ticks();const pendingBeforeFlush=!settled;settle();await ticks();
  return {entry,rejectFlush,networkFailure,putFailure,pendingBeforeFlush,settled,outcome,returnedFreshData:value===data,returnedCachedData:value?.cached===true,events,logs,stored:JSON.parse(store.get('page'))};
 }
 const trials=[];for(const entry of ['helper','service','model'])trials.push(await trial(entry));trials.push(await trial('helper',true));trials.push(await trial('model',true));trials.push(await trial('model',false,true));trials.push(await trial('helper',false,false,true));
 const checks={sourceSyntaxParsed:Object.values(analyses).every(a=>!a.syntaxHasErrors),helperWaitsForFlush:trials[0].pendingBeforeFlush,serviceWaitsForFlush:trials[1].pendingBeforeFlush,modelWaitsForFlush:trials[2].pendingBeforeFlush,helperPropagatesFlushFailure:trials[3].outcome==='rejected',modelRetainsFreshDataAfterFlushFailure:trials[4].pendingBeforeFlush&&trials[4].returnedFreshData&&trials[4].logs.length>0,networkFailureUsesOfflineCache:trials[5].returnedCachedData&&!trials[5].events.includes('flush-started'),helperPropagatesPutFailure:trials[6].outcome==='rejected',neighborRecordPreserved:trials.every(t=>t.stored.neighbor.id==='keep'),recordAndFreshDataPreserved:trials.slice(0,3).every(t=>t.stored['1_30'].currentPage===1)&&trials[2].returnedFreshData};
 if(stage===1){delete checks.modelWaitsForFlush;delete checks.modelRetainsFreshDataAfterFlushFailure;}
 console.log(JSON.stringify({stage,schema:'agentlab.cache_durability_probe.v1',sourceRevision:cp.spawnSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).stdout.trim()||null,checks,pass:Object.values(checks).every(Boolean),trials,sourceFiles:Object.entries(files).map(([key,file])=>({path:file,sha256:crypto.createHash('sha256').update(sources[key]).digest('hex'),source:sources[key],analysis:analyses[key]})),referenceTransformsApplied:false,actualModulesExecuted:4,qualification:{candidateOnly:true,phoneBuild:false,pageUI:false,actualAgent:false}}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
