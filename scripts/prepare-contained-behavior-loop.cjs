// Profile data owns repository paths, mutations, checks and adapter selection.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const preparerBytes=fs.readFileSync(__filename);
const root=path.resolve(__dirname,'..');
function option(name){const i=process.argv.indexOf(name);if(i<0||!process.argv[i+1])throw Error('Missing '+name);return process.argv[i+1];}
function requireOk(ok,message){if(!ok)throw Error(message);}
function save(file,value){const bytes=Buffer.from(JSON.stringify(value,null,2)+'\n');fs.writeFileSync(file,bytes,{flag:'wx'});return bytes;}
function run(program,args,cwd,timeout=120000){const result=cp.spawnSync(program,args,{cwd,encoding:'utf8',timeout,maxBuffer:1024*1024});requireOk(!result.error&&result.status===0,'Preparation command failed: '+program+' '+(result.stderr||'')+' '+(result.error||''));return result.stdout.trim();}
const profilePath=path.resolve(option('--profile'));
const candidatesPath=path.resolve(option('--candidates'));
const compiler=fs.realpathSync(option('--compiler'));
const imageId=option('--image-id');
const python=fs.realpathSync(option('--python'));
const out=path.resolve(option('--output'));fs.mkdirSync(out);
const profileBytes=fs.readFileSync(profilePath),profile=JSON.parse(profileBytes);
const maximumAttempts=Number(option('--maximum-attempts'));
requireOk(Number.isInteger(maximumAttempts)&&maximumAttempts>=1&&maximumAttempts<=3,'Attempt budget invalid');
requireOk(Number.isInteger(profile.workerDeadlineMs)&&profile.workerDeadlineMs>=5000&&profile.workerDeadlineMs<=60000,'Worker deadline invalid');
requireOk(profile.schema==='agentlab.reviewed_behavior_profile.v1'&&profile.reviewed===true&&profile.automaticPromotion===false,'Profile not reviewed');
requireOk(/^sha256:[0-9a-f]{64}$/.test(imageId)&&/^[0-9a-f]{40}$/.test(profile.sourceRevision),'Image or source identity invalid');
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const candidatesBytes=fs.readFileSync(candidatesPath);
const candidates=candidatesBytes.toString('utf8').trim().split('\n').map(JSON.parse);
const selected=candidates.filter(c=>c.id===profile.candidateId);
requireOk(selected.length===1&&sha(JSON.stringify(canonical(selected[0])))===profile.candidateSha256&&selected[0].sourceRevision===profile.sourceRevision,'Profile candidate differs');
const source=path.join(out,'source');fs.mkdirSync(source);
run('git',['init',source],out);
run('git',['remote','add','origin',profile.repository],source);
requireOk(profile.sources.every(row=>typeof row.path==='string'&&!row.path.startsWith('/')&&!row.path.includes('\\')&&!/[\r\n*?\[\]]/.test(row.path)&&row.path.split('/').every(s=>s&&s!=='.'&&s!=='..')),'Sparse source path unsafe');
run('git',['config','core.sparseCheckout','true'],source);
fs.writeFileSync(path.join(source,'.git/info/sparse-checkout'),profile.sources.map(row=>'/'+row.path).join('\n')+'\n',{flag:'wx'});
const fetched=cp.spawnSync('git',['fetch','--filter=blob:none','--depth','1','origin',profile.sourceRevision],{cwd:source,encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
fs.writeFileSync(path.join(out,'source-fetch.stdout'),fetched.stdout||'',{flag:'wx'});fs.writeFileSync(path.join(out,'source-fetch.stderr'),fetched.stderr||'',{flag:'wx'});
requireOk(!fetched.error&&fetched.status===0,'Source acquisition failed; original logs retained');
run('git',['checkout','--detach','FETCH_HEAD'],source);
requireOk(run('git',['rev-parse','HEAD'],source)===profile.sourceRevision&&run('git',['status','--porcelain'],source)==='','Source cut differs or dirty');
const safe=p=>typeof p==='string'&&!p.startsWith('/')&&!p.includes('\\')&&p.split('/').every(s=>s&&s!=='.'&&s!=='..');
const originals=new Map();
for(const row of profile.sources){
 requireOk(safe(row.path),'Source path unsafe');
 let current=source;for(const part of row.path.split('/')){current=path.join(current,part);requireOk(!fs.lstatSync(current).isSymbolicLink(),'Source symlink');}
 const bytes=fs.readFileSync(current);requireOk(sha(bytes)===row.sha256&&run('git',['rev-parse',profile.sourceRevision+':'+row.path],source)===row.gitBlobOid,'Source bytes or Blob differ');
 requireOk(!originals.has(row.path),'Repeated source');originals.set(row.path,bytes.toString('utf8'));
}
const original=originals.get(profile.originalSourcePath);requireOk(typeof original==='string','Original source missing');
requireOk(sha(fs.readFileSync(compiler))===profile.compilerSha256,'Compiler differs');
const support={...profile.supportFields,compilerSha256:profile.compilerSha256};
for(const row of profile.supportSources){
 requireOk(originals.has(row.path)&&/^[A-Za-z][A-Za-z0-9]*$/.test(row.contentKey)&&/^[A-Za-z][A-Za-z0-9]*$/.test(row.shaKey)&&!(row.contentKey in support)&&!(row.shaKey in support),'Support binding invalid');
 support[row.contentKey]=originals.get(row.path);support[row.shaKey]=sha(support[row.contentKey]);
}
const supportPath=path.join(out,'support.json');save(supportPath,support);
requireOk(safe(profile.workerPath)&&profile.workerPath.startsWith('scripts/'),'Worker path invalid');
run('git',['ls-files','--error-unmatch','--',profile.workerPath],root);
const worker=fs.realpathSync(path.join(root,profile.workerPath));
const launcher=path.join(root,'scripts/run-contained-behavior-worker.py');
const launcherBytes=fs.readFileSync(launcher);
const descriptor={schema:'agentlab.contained_behavior_executor.v1',reviewed:true,automaticPromotion:false,imageId,
 workerPath:worker,workerSha256:sha(fs.readFileSync(worker)),compilerPath:compiler,compilerSha256:profile.compilerSha256,
 supportPath,supportSha256:sha(fs.readFileSync(supportPath)),timeoutMs:profile.workerDeadlineMs-2000};
const descriptorPath=path.join(out,'executor.json');const descriptorBytes=save(descriptorPath,descriptor);
const runtime=run('docker',['run','--rm','--network','none','--entrypoint','node',imageId,'--version'],out,30000)+' / '+imageId;
const controls=profile.controls.map(control=>{
 requireOk(/^[A-Za-z0-9_-]+$/.test(control.id),'Control ID invalid');
 let source=original;for(const edit of control.edits){requireOk(typeof edit.from==='string'&&edit.from&&typeof edit.to==='string'&&source.split(edit.from).length===2&&edit.from!==edit.to,'Control edit absent or ambiguous');source=source.replace(edit.from,edit.to);}
 return {manifest:{id:control.id,role:control.role,submittedSourceSha256:sha(source),expectedFailedCheckIds:control.expectedFailedCheckIds},source};
});
const contract={schema:'agentlab.frozen_behavior_checks.v1',candidateId:profile.candidateId,candidateSha256:profile.candidateSha256,
 sourceRevision:profile.sourceRevision,originalSourceSha256:sha(original),methodSha256:sha(JSON.stringify({profileSha256:sha(profileBytes),descriptorSha256:sha(descriptorBytes),launcherSha256:sha(launcherBytes),preparerSha256:sha(preparerBytes)})),
 compilerSha256:profile.compilerSha256,runtime,workerDeadlineMs:profile.workerDeadlineMs,checks:profile.checks,controls:controls.map(c=>c.manifest),automaticPromotion:false};
// Freeze normative predicates and source variants before any calibration worker.
const contractBytes=save(path.join(out,'frozen-checks.json'),contract);
const workers=[];
for(const control of controls){
 const dir=path.join(out,'control-'+control.manifest.id);fs.mkdirSync(dir);
 const request={schema:'agentlab.behavior_executor_request.v1',id:control.manifest.id,originalSourceSha256:contract.originalSourceSha256,
  submittedSourceSha256:control.manifest.submittedSourceSha256,submittedSource:control.source,checks:contract.checks.map(({id,input})=>({id,input}))};
 const requestPath=path.join(dir,'request.json');save(requestPath,request);
 const started=process.hrtime.bigint();
 const result=cp.spawnSync(python,[launcher,descriptorPath,requestPath],{cwd:dir,encoding:'utf8',timeout:profile.workerDeadlineMs,maxBuffer:1024*1024});
 fs.writeFileSync(path.join(dir,'launcher.stdout'),result.stdout||'',{flag:'wx'});fs.writeFileSync(path.join(dir,'launcher.stderr'),result.stderr||'',{flag:'wx'});
 requireOk(!result.error&&result.status===0,'Calibration infrastructure failure; logs retained');
 workers.push({id:control.manifest.id,execution:{exitCode:result.status,timedOut:false,durationMs:Math.max(1,Number((process.hrtime.bigint()-started)/1000000n)),stdout:result.stdout,stdoutSha256:sha(result.stdout)}});
}
const capture={schema:'agentlab.behavior_worker_capture.v1',contractSha256:sha(contractBytes),candidateId:contract.candidateId,candidateSha256:contract.candidateSha256,
 sourceRevision:contract.sourceRevision,methodSha256:contract.methodSha256,compilerSha256:contract.compilerSha256,runtime,workers};
const captureBytes=save(path.join(out,'worker-capture.json'),capture);
for(const [file,bytes] of [[__filename,preparerBytes],[launcher,launcherBytes],[profilePath,profileBytes],[candidatesPath,candidatesBytes]])requireOk(sha(fs.readFileSync(file))===sha(bytes),'Preparation method or input changed; capture not admitted');
const adapter=path.join(root,'examples/real-code-agent/behavior-participant.py');
const command=args=>({program:python,programSha256:sha(fs.readFileSync(python)),args,cwd:'.',timeoutMs:180000});
const executorCommand=command([launcher,descriptorPath,'{request}']);executorCommand.timeoutMs=profile.workerDeadlineMs;
const immutable=[profilePath,candidatesPath,compiler,supportPath,descriptorPath,worker,launcher,adapter,path.join(root,'examples/real-code-agent/participant.py')];
const recipe={schema:'agentlab.behavior_loop_recipe.v1',reviewed:true,automaticPromotion:false,contractSha256:sha(contractBytes),captureSha256:sha(captureBytes),taskDemand:profile.taskDemand,
 maximumAttempts,participantCompletionRequired:true,
 participantEnvironmentNames:['AGENTLAB_LM_GATEWAY_URL','AGENTLAB_LM_GATEWAY_KEY','AGENTLAB_PI_BINARY','AGENTLAB_MODEL','AGENTLAB_PROVIDER_ROUTE','AGENTLAB_REASONING_EFFORT'],
 immutableInputs:immutable.map(p=>({path:p,sha256:sha(fs.readFileSync(p))})),participantCommand:command([adapter,'{request}']),executorCommand};
save(path.join(out,'loop-recipe.json'),recipe);
requireOk(run('git',['status','--porcelain'],source)==='','Source changed during preparation');
console.log(JSON.stringify({contractSha256:sha(contractBytes),captureSha256:sha(captureBytes),qualified:false}));
