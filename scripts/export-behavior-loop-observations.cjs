// Thin transport: Rust owns all behavior reconstruction and analytical rows.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const crypto=require('node:crypto'),assert=require('node:assert/strict');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const retained=new Map();
function option(name){const i=process.argv.indexOf(name);assert(i>=0&&process.argv[i+1],`Missing ${name}`);return process.argv[i+1];}
function read(file){
 for(let p=path.resolve(file);;p=path.dirname(p)){
  assert(!fs.lstatSync(p).isSymbolicLink(),'Observation input symlink');
  if(path.dirname(p)===p)break;
 }
 const meta=fs.statSync(file);assert(meta.isFile()&&meta.size<=4*1024*1024,'Observation input budget');
 const bytes=fs.readFileSync(file);assert(bytes.length<=4*1024*1024,'Observation input grew');
 if(retained.has(file))assert(bytes.equals(retained.get(file)),'Observation input drifted');
 else retained.set(file,bytes);
 return bytes;
}
function recheck(){for(const file of retained.keys())read(file);}
const attempts=path.resolve(option('--attempts')),output=path.resolve(option('--output'));
const candidates=path.resolve(option('--candidates')),candidateId=option('--candidate-id');
const tool=path.resolve(option('--flywheel-tool')),resultPath=path.join(attempts,'loop-result.json');
assert(!fs.existsSync(output),'Observation output exists');
if(!fs.existsSync(resultPath)){
 console.log(JSON.stringify({status:'incomplete-loop-capture',observationExported:false,qualified:false,authorityWritePerformed:false}));
 process.exit(0);
}
const resultBytes=read(resultPath),result=JSON.parse(resultBytes);
assert.equal(result.schema,'agentlab.behavior_loop_capture.v1');
for(const flag of ['qualified','automaticPromotion','authorityWritePerformed'])assert.equal(result[flag],false);
assert(['recorded-attempt-passed','attempt-budget-exhausted','unchanged-attempt-suppressed'].includes(result.status),'Unsupported loop terminal state');
assert(Array.isArray(result.attempts)&&result.attempts.length>=1&&result.attempts.length<=3,'Completed attempts missing');
const originalBytes=read(path.join(attempts,'frozen-contract.json')),original=JSON.parse(originalBytes);
assert.equal(sha(originalBytes),result.contractSha256);
assert.equal(sha(read(path.join(attempts,'calibration-capture.json'))),result.calibrationCaptureSha256);
assert.equal(sha(read(path.join(attempts,'recipe.json'))),result.recipeSha256);
assert.equal(original.candidateId,candidateId);
read(candidates);assert(fs.lstatSync(tool).isFile(),'Native exporter must be a regular file');
const inputs=result.attempts.map((attempt,index)=>{
 assert.equal(attempt.attempt,index,'Noncontiguous attempt');
 const directory=path.join(attempts,`attempt-${index}`);
 const contractPath=path.join(directory,'attempt-contract.json'),capturePath=path.join(directory,'attempt-capture.json');
 const contract=JSON.parse(read(contractPath)),captureBytes=read(capturePath);
 const controls=contract.controls;assert(Array.isArray(controls)&&controls.length===original.controls.length+1);
 const submission=controls.at(-1);assert.equal(submission.id,`agent-attempt-${index}`);assert.equal(submission.role,'agent-attempt');
 assert.equal(submission.submittedSourceSha256,attempt.submittedSourceSha256);
 assert.deepEqual({...contract,controls:controls.slice(0,-1)},original,'Frozen checks drifted');
 const feedbackBytes=read(path.join(directory,'feedback.json'));
 assert.equal(sha(feedbackBytes),attempt.feedbackSha256);
 assert.equal(JSON.parse(feedbackBytes).nextAction,attempt.nextAction);
 return {index,contractPath,capturePath,captureSha256:sha(captureBytes),feedback:JSON.parse(feedbackBytes),feedbackSha256:sha(feedbackBytes)};
});
assert.deepEqual(result.latestFeedback,inputs.at(-1).feedback);
assert.equal(result.status==='recorded-attempt-passed',inputs.at(-1).feedback.nextAction==='review-agent-outcome');
fs.mkdirSync(output);
const exported=[];
for(const input of inputs){
 const verified=path.join(output,`feedback-${input.index}.json`);
 function run(args){recheck();const r=cp.spawnSync(tool,args,{encoding:'utf8',timeout:30000,maxBuffer:1024*1024});assert(!r.error&&r.status===0,`Native observation reconstruction failed: ${r.stderr||r.error||r.status}`);recheck();}
 run(['--verify-behavior-checks','--contract',input.contractPath,'--capture',input.capturePath,'--output',verified]);
 assert.deepEqual(JSON.parse(read(verified)),input.feedback,'Recorded feedback differs');
 const destination=path.join(output,`attempt-${input.index}`);
 run(['--export-behavior-observation','--candidates',candidates,'--candidate-id',candidateId,'--contract',input.contractPath,'--capture',input.capturePath,'--output',destination]);
 const manifestBytes=read(path.join(destination,'export.json'));
 const runs=read(path.join(destination,'runs.jsonl')).toString('utf8').trim().split('\n').map(JSON.parse);
 assert.equal(runs.length,1);assert.equal(typeof runs[0].id,'string');
 exported.push({attempt:input.index,runId:runs[0].id,exportSha256:sha(manifestBytes),captureSha256:input.captureSha256,feedbackSha256:input.feedbackSha256,path:`attempt-${input.index}`});
}
const manifest={schema:'agentlab.behavior_loop_observation_exports.v1',loopCaptureSha256:sha(resultBytes),loopStatus:result.status,exports:exported,observationExported:true,lessonCreated:false,participantAuthenticated:false,remotePersistenceVerified:false,qualified:false,automaticPromotion:false,authorityWritePerformed:false};
recheck();
fs.writeFileSync(path.join(output,'loop-result.json'),resultBytes,{flag:'wx'});
fs.writeFileSync(path.join(output,'export-index.json'),JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'observations-exported',attempts:exported.length,qualified:false,authorityWritePerformed:false}));
