const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const [source,reference,output]=process.argv.slice(2);fs.mkdirSync(output);
const files=['common/src/main/ets/storagemanager/PreferenceManager.ets','common/src/main/ets/storagemanager/PreferenceCacheHelper.ets','features/devpractices/src/main/ets/service/SampleService.ets','features/devpractices/src/main/ets/model/SampleModel.ets'];
const variants={baseline:source,reference};
for(const [name,file,before,after] of [['lost-flush',files[0],'    await this.preferences.flush();','    void this.preferences.flush().catch(() => {});'],['lost-model-await',files[3],'        await this.service.setSamplePageToPreference(data);','        void this.service.setSamplePageToPreference(data).catch(() => {});']]){
 const directory=path.join(output,name);fs.mkdirSync(directory);for(const file of files){const target=path.join(directory,file);fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(path.join(reference,file),target);}cp.execFileSync('git',['init','-q',directory]);cp.execFileSync('git',['-C',directory,'add','.']);cp.execFileSync('git',['-C',directory,'-c','user.name=Calibration','-c','user.email=calibration@example.invalid','commit','-qm','Calibration variant']);
 const target=path.join(directory,file),raw=fs.readFileSync(target,'utf8');if(!raw.includes(before))throw Error('Missing mutation anchor');fs.writeFileSync(target,raw.replace(before,after));variants[name]=directory;
}
const receipts={};for(const [name,directory] of Object.entries(variants)){
 receipts[name]={};for(const stage of [1,2]){
 const result=cp.spawnSync(process.execPath,[path.join(__dirname,'cache-durability.cjs'),directory,String(stage)],{encoding:'utf8',maxBuffer:16*1024*1024});fs.writeFileSync(path.join(output,name+'-stage-'+stage+'.json'),result.stdout);fs.writeFileSync(path.join(output,name+'-stage-'+stage+'.stderr'),result.stderr);if(result.status!==0)throw Error('Probe infrastructure failed '+name+result.stderr);const receipt=JSON.parse(result.stdout);receipts[name][stage]={checks:receipt.checks,pass:receipt.pass,sha256:crypto.createHash('sha256').update(result.stdout).digest('hex')};if(receipt.pass!==(name==='reference'||(name==='lost-model-await'&&stage===1)))throw Error('Calibration mismatch '+name+'/'+stage);
}}
fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify({schema:'agentlab.cache_calibration.v1',receipts,candidateOnly:true,actualAgentQualified:false,fullPhoneBuildQualified:false},null,2)+'\n');console.log(JSON.stringify(receipts));
