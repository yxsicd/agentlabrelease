#!/usr/bin/env node
// Operator MCP transport only. Rust reconstructs and validates business rows.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function mainArgs() {
  const args = process.argv.slice(2), values = {};
  for (let i=0;i<args.length;i+=2) {
    assert(['--request','--credentials'].includes(args[i]) && !values[args[i]] && args[i+1], 'Invalid import argument');
    values[args[i]]=args[i+1];
  }
  assert(values['--request'] && values['--credentials'], 'Request and private credentials file required');
  return values;
}
async function main() {
  const args=mainArgs();
  const requestBytes=fs.readFileSync(args['--request']);
  const request=JSON.parse(requestBytes);
  assert.equal(request.schema,'agentlab.observation_store_request.v1');
  assert.equal(request.reviewed,true);
  assert.equal(request.automaticPromotion,false);
  const root=request.outputDirectory;
  assert(path.isAbsolute(root) && path.isAbsolute(request.sourceDirectory) && path.isAbsolute(request.flywheelTool));
  assert.equal(sha(fs.readFileSync(request.flywheelTool)),request.flywheelToolSha256);
  assert.equal(sha(fs.readFileSync(path.join(request.sourceDirectory,'export.json'))),request.sourceManifestSha256);
  const endpoint=new URL(request.endpoint);
  assert(['https:','http:'].includes(endpoint.protocol) && !endpoint.username && !endpoint.password);
  fs.mkdirSync(root);
  const save=(name,value)=>fs.writeFileSync(path.join(root,name),JSON.stringify(value,null,2),{flag:'wx'});
  save('request.json',request);
  const credentialStat=fs.lstatSync(args['--credentials']);
  assert(credentialStat.isFile() && !credentialStat.isSymbolicLink(), 'Private credentials must be regular');
  const privateEnv=Object.fromEntries(fs.readFileSync(args['--credentials'],'utf8').split('\n').filter(x=>x.trim()&&!x.startsWith('#')).map(x=>{
    const i=x.indexOf('='); return [x.slice(0,i).trim(),x.slice(i+1).trim().replace(/^['"]|['"]$/g,'')];
  }));
  const auth={basic_username:privateEnv.MCPGIT_BASIC_USERNAME,basic_verify:privateEnv.MCPGIT_BASIC_VERIFY};
  assert(auth.basic_username && auth.basic_verify, 'Private Basic pair required');
  let session,sequence=0;
  async function rpc(method,params) {
    const headers={'Content-Type':'application/json',Accept:'application/json, text/event-stream'};
    if(session) headers['Mcp-Session-Id']=session;
    const response=await fetch(endpoint,{method:'POST',headers,body:JSON.stringify({jsonrpc:'2.0',id:++sequence,method,params}),signal:AbortSignal.timeout(30000)});
    session=response.headers.get('mcp-session-id')||session;
    assert(response.ok,`MCP HTTP ${response.status}`);
    const body=await response.text();
    const data=body.startsWith('data:')||body.startsWith('event:') ? body.split('\n').find(x=>x.startsWith('data:')&&x.slice(5).trim())?.slice(5) : body;
    const packet=JSON.parse(data);
    assert(!packet.error && !packet.result?.isError,'MCP operation failed; no transport retry');
    return packet.result?.structuredContent || (packet.result?.content?.[0]?.text ? JSON.parse(packet.result.content[0].text) : packet.result);
  }
  const tool=(name,arguments_)=>rpc('tools/call',{name,arguments:arguments_});
  await rpc('initialize',{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'AgentLab observation importer',version:'1'}});
  save('service-metadata.json',await tool('service_metadata',{}));
  save('skill-list.json',await tool('skill_list',{}));
  const versions={};
  for (const [skill,operations] of [['table.author',['worktree_table_open','worktree_table_batch_transaction']],['table.query',['table_query']]]) {
    const loaded=await tool('skill_get',{skill_id:skill});
    save(skill+'-contract.json',loaded);
    assert.equal(loaded.outcome,'loaded');
    assert(operations.every(op=>loaded.skill.summary.operation_names.includes(op)), 'Required live contract missing');
    versions[skill]=loaded.skill.summary.skill_version;
  }
  const status=await tool('person_status',auth);
  const personName=request.personShowname || privateEnv.MCPGIT_DEFAULT_PERSON_SHOWNAME;
  const person=(status.selectable_persons||status.persons||status.options||status.choices||[]).find(x=>x.showname===personName);
  assert(person,'Selected Person absent');
  await tool('person_select',{...auth,person_id:person.person_id,person_showname:person.showname});
  save('acting-person.json',{person_id:person.person_id,showname:person.showname});
  async function business(lane,skill,operation,arguments_) {
    const response=await tool('skill_run_'+lane,{...auth,caller_person_id:person.person_id,skill_id:skill,skill_version:versions[skill],operation,arguments:arguments_});
    assert.equal(response.outcome,'executed', 'Business operation rejected; no retry');
    return response.result;
  }
  const manifest=JSON.parse(fs.readFileSync(path.join(request.sourceDirectory,'export.json')));
  const names=Object.keys(manifest.tables).sort();
  const destination=request.destination;
  async function snapshot(revision) {
    const tables={};
    for(const name of names) tables[name]=await business('read','table.query','table_query',{
      repo:destination.repository,path:destination.tablePrefix+name,view:{kind:'committed',revision},limit:1000});
    return {schema:'agentlab.observation_store_snapshot.v1',repository:destination.repository,revision,tablePrefix:destination.tablePrefix,tables};
  }
  save('destination.json',destination);
  save('baseline.json',await snapshot(destination.expectedRevision));
  function native(mode,extra,output) {
    assert.equal(sha(fs.readFileSync(request.flywheelTool)),request.flywheelToolSha256);
    const result=spawnSync(request.flywheelTool,[mode,'--source',request.sourceDirectory,...extra,'--output',path.join(root,output)],{encoding:'utf8',timeout:60000,env:{PATH:'/usr/bin:/bin'}});
    fs.writeFileSync(path.join(root,output+'.stdout'),result.stdout||'',{flag:'wx'});
    fs.writeFileSync(path.join(root,output+'.stderr'),result.stderr||'',{flag:'wx'});
    assert.equal(result.status,0, 'Native observation validation rejected');
    return JSON.parse(fs.readFileSync(path.join(root,output)));
  }
  const plan=native('--plan-observation-import',['--remote-snapshot',path.join(root,'baseline.json'),'--destination',path.join(root,'destination.json')],'plan.json');
  const opened=await business('write','table.author','worktree_table_open',{repo:destination.repository,topic_id:'main'});
  save('open.json',opened);
  assert.equal(opened.revision,destination.expectedRevision,'Authority drift; no rebase');
  let receipt={revision:destination.expectedRevision,conflicts:[],noChange:true};
  if(plan.transaction) {
    save('transaction-intent.json',plan.transaction);
    // Exactly one call. Unknown write outcomes require retained-intent recovery.
    receipt=await business('write','table.author','worktree_table_batch_transaction',plan.transaction);
  }
  save('commit-receipt.json',receipt);
  save('committed.json',await snapshot(receipt.revision));
  const verified=native('--verify-observation-import',['--plan',path.join(root,'plan.json'),'--commit-receipt',path.join(root,'commit-receipt.json'),'--remote-snapshot',path.join(root,'committed.json'),'--baseline-snapshot',path.join(root,'baseline.json')],'verification.json');
  save('result.json',verified);
  console.log(JSON.stringify(verified));
}
main().catch(()=>{console.error('Observation import stopped; retain partial evidence and reconcile any saved transaction intent.');process.exitCode=1;});
