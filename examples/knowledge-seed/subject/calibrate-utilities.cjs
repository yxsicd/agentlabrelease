// Local/CI calibration only. No subject dispatch and no assessed workspace repair.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const [source,reference,output]=process.argv.slice(2);if(!source||!reference||!output)throw Error('usage: SOURCE REFERENCE FRESH_OUTPUT');
fs.mkdirSync(output);const digest=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const summary={schema:'agentlab.utility_calibration.v1',sourceRevision:cp.execFileSync('git',['-C',source,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),cases:{},actualAgentQualified:false,fullPhoneBuildQualified:false};
for(const scenario of ['debounce','image-url']){
 const root=path.join(output,scenario);fs.mkdirSync(root);
 const oracle=path.join(__dirname,scenario+'.cjs');
 const variants={baseline:{directory:source,expected:false},reference:{directory:reference,expected:true}};
 const definitions=scenario==='debounce'?[['wrong-boundary','common/src/main/ets/util/DebounceUtil.ets','lastClickTime < wait','lastClickTime <= wait'],['wrong-window','common/src/main/ets/util/DebounceUtil.ets','        return;','        lastClickTime = now;\n        return;']]:[['wrong-protocol','common/src/main/ets/util/UrlUtil.ets',"parsed.hostname.length > 0","true"],['wrong-dispatch','common/src/main/ets/util/ImageUtil.ets','if (UrlUtil.isNetUrl(url))','if (false)']];
 for(const [name,file,before,after] of definitions){const directory=path.join(root,name);fs.mkdirSync(directory);for(const subtree of ['common','features'])fs.cpSync(path.join(reference,subtree),path.join(directory,subtree),{recursive:true});const target=path.join(directory,file),raw=fs.readFileSync(target,'utf8');if(!raw.includes(before))throw Error('Negative mutation anchor missing '+name);fs.writeFileSync(target,raw.replace(before,after));variants[name]={directory,expected:false};}
 // A missing-host parser result isolates the predicate guard: the platform seam
 // normally rejects https:// before this guard. Use a malformed protocol variant
 // instead, keeping the actual body and the same modeled parser for every variant.
 if(scenario==='image-url'){
  const target=path.join(variants['wrong-protocol'].directory,'common/src/main/ets/util/UrlUtil.ets');let raw=fs.readFileSync(target,'utf8');raw=raw.replace("!/^https?:\\/\\//i.test(value)","false").replace("(parsed.protocol === 'http:' || parsed.protocol === 'https:')","true");fs.writeFileSync(target,raw);
 }
 const receipts={};for(const [name,variant] of Object.entries(variants)){receipts[name]={};for(const stage of [1,2]){const result=cp.spawnSync(process.execPath,[oracle,variant.directory,String(stage)],{encoding:'utf8',maxBuffer:16*1024*1024});const filename=path.join(root,name+'-stage-'+stage+'.json');fs.writeFileSync(filename,result.stdout);fs.writeFileSync(filename+'.stderr',result.stderr);if(result.status!==0)throw Error('Oracle infrastructure failure '+name);const outcome=JSON.parse(result.stdout);receipts[name][stage]={pass:outcome.pass,checks:outcome.checks,error:outcome.error,sha256:digest(filename)};const expected=name==='wrong-dispatch'?stage===1:variant.expected;if(outcome.pass!==expected)throw Error('Calibration mismatch '+scenario+'/'+name+'/'+stage+' '+JSON.stringify(receipts[name][stage]));}}
 summary.cases[scenario]={oracleDigest:digest(oracle),variants:receipts};
}
summary.ok=true;fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');console.log(JSON.stringify(summary));
