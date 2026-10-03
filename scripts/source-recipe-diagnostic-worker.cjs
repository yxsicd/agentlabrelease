'use strict';
// Runs only inside run-contained-behavior-worker.py. No host source execution.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const cp = require('node:child_process');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const request = JSON.parse(fs.readFileSync(process.argv[2]));
const support = JSON.parse(fs.readFileSync(process.argv[3]));
if (support.schema !== 'agentlab.source_recipe_diagnostic_support.v1' ||
    sha(request.submittedSource) !== request.submittedSourceSha256 ||
    sha(support.runtimeSource) !== support.runtimeSha256 ||
    sha(fs.readFileSync(process.argv[4])) !== support.compilerSha256)
  throw new Error('diagnostic input binding differs');
const root = fs.mkdtempSync('/tmp/source-recipe-diagnostic-');
const sourceRoot = path.join(root, 'source');
const seen = new Set();
for (const file of support.files) {
  const parts = file.path.split('/');
  if (path.isAbsolute(file.path) || parts.some(p => !p || p === '.' || p === '..' || p.includes('\\')) || seen.has(file.path))
    throw new Error('diagnostic source path invalid');
  seen.add(file.path);
  const bytes = Buffer.from(file.content, 'utf8');
  const blob = crypto.createHash('sha1').update(Buffer.from('blob ' + bytes.length + '\0')).update(bytes).digest('hex');
  if (bytes.length !== file.byteCount || sha(bytes) !== file.sha256 || blob !== file.gitBlobOid)
    throw new Error('diagnostic source inventory differs');
  const target = path.join(sourceRoot, file.path);
  fs.mkdirSync(path.dirname(target), {recursive:true});
  fs.writeFileSync(target, bytes, {flag:'wx',mode:0o444});
}
const verifier = path.join(root,'controls.cjs');
const runtime = path.join(root,'design-runtime.cjs');
fs.writeFileSync(verifier,request.submittedSource,{flag:'wx',mode:0o444});
fs.writeFileSync(runtime,support.runtimeSource,{flag:'wx',mode:0o444});
const result = cp.spawnSync(process.execPath,[verifier,sourceRoot,support.controlId,process.argv[4],runtime],
  {cwd:root,env:{PATH:'/usr/local/bin:/usr/bin:/bin'},timeout:15000,maxBuffer:1024*1024});
if (result.stderr) process.stderr.write(result.stderr);
if (result.error || result.status !== 0) {
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.error) process.stderr.write(String(result.error)+'\n');
  process.exit(result.status === null ? 125 : result.status);
}
// Independent Rust comparison is outside this container; no verdict here.
const verifierStdout = result.stdout.toString('utf8');
let observations;
try {
  if (!Buffer.from(verifierStdout,'utf8').equals(result.stdout)) throw new Error('verifier stdout is not UTF-8');
  observations = JSON.parse(verifierStdout);
} catch (error) {
  process.stdout.write(result.stdout);
  throw error;
}
process.stdout.write(JSON.stringify({id:request.id,submittedSource:request.submittedSource,
  submittedSourceSha256:request.submittedSourceSha256,observations,
  verifierStdout,verifierStdoutSha256:sha(result.stdout),
  runtime:process.version,architecture:process.arch,qualified:false}));
