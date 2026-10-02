// Trusted-source AbilityStage seam calibration, not a Harmony runtime or sandbox.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const vm = require('node:vm');
const crypto = require('node:crypto');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const args = process.argv.slice(2);
function arg(name) {
  const i = args.indexOf(name);
  if (i < 0 || !args[i + 1]) throw Error('Missing ' + name);
  return args[i + 1];
}
function safe(p) {
  if (typeof p !== 'string' || path.isAbsolute(p) || p.includes('\\') || p.split('/').some(x => !x || x === '.' || x === '..'))
    throw Error('Unsafe source path');
  return p;
}
function retainedSources(c) {
  const retained = args.includes('--source-binding');
  if (!retained) {
    if (args.includes('--source-workspace')) throw Error('Workspace without source binding');
    return null;
  }
  if (args.includes('--source-repo')) throw Error('Ambiguous source authority');
  const bytes = fs.readFileSync(arg('--source-binding'));
  const binding = JSON.parse(bytes);
  if (!Array.isArray(binding.sources) || !binding.sources.length) throw Error('Missing retained sources');
  const requestedRoot = path.resolve(arg('--source-workspace'));
  if (fs.lstatSync(requestedRoot).isSymbolicLink()) throw Error('Unsafe source workspace');
  const root = fs.realpathSync(requestedRoot);
  const rows = new Map();
  const repositories = new Set();
  for (const row of binding.sources) {
    safe(row.path); safe(row.workspacePath);
    if (!row.repositoryId || row.revision !== c.sourceRevision || rows.has(row.path) ||
        !/^[a-f0-9]{64}$/.test(row.sha256) || !/^[a-f0-9]{40}$/.test(row.gitBlobOid) ||
        !Number.isSafeInteger(row.bytes) || row.bytes < 0) throw Error('Invalid retained source identity');
    repositories.add(row.repositoryId);
    let file = root;
    for (const part of row.workspacePath.split('/')) {
      file = path.join(file, part);
      if (fs.lstatSync(file).isSymbolicLink()) throw Error('Retained source symlink');
    }
    if (!fs.lstatSync(file).isFile()) throw Error('Retained source is not a file');
    const original = fs.readFileSync(file);
    const oid = crypto.createHash('sha1').update(Buffer.from(`blob ${original.length}\0`)).update(original).digest('hex');
    if (original.length !== row.bytes || sha(original) !== row.sha256 || oid !== row.gitBlobOid)
      throw Error('Retained source bytes differ');
    rows.set(row.path, {text: original.toString(), identity: {path: row.path, gitBlobOid: oid, sha256: sha(original)}});
  }
  if (repositories.size !== 1) throw Error('Ambiguous retained repository');
  return {rows, authority: {kind: 'retained-source-binding', bindingSha256: sha(bytes),
    repositoryId: [...repositories][0], sourceRevision: c.sourceRevision, verifiedFiles: rows.size,
    revisionAuthenticated: false}};
}
function load() {
  const bytes = fs.readFileSync(arg('--contract'));
  const c = JSON.parse(bytes);
  const diagnostic = args.includes('--diagnostic-unreviewed');
  if (c.schema !== 'agentlab.harmony_stage_control_contract.v1' ||
      (diagnostic ? c.reviewed !== false : c.reviewed !== true) ||
      !/^[a-f0-9]{40}$/.test(c.sourceRevision) || !Array.isArray(c.variants) || c.variants.length < 2 ||
      !Array.isArray(c.configurations) || c.configurations.length < 3)
    throw Error('Invalid reviewed stage contract');
  safe(c.modulePath);
  const unique = values => new Set(values).size === values.length;
  if (!unique(c.variants.map(x => x.id)) || !unique(c.configurations.map(x => x.id))) throw Error('Duplicate controls');
  for (const key of ['createMarker', 'destroyMarker', 'registrationMarker', 'configurationPrefix', 'eventName'])
    if (typeof c[key] !== 'string' || !c[key]) throw Error('Missing contract ' + key);
  for (const config of c.configurations)
    if (!config.id || typeof config.language !== 'string' || !Number.isInteger(config.colorMode)) throw Error('Invalid configuration');
  const changedDimensions = new Set();
  for (let i = 1; i < c.configurations.length; i++) {
    const changed = ['language', 'colorMode'].filter(k => c.configurations[i][k] !== c.configurations[i - 1][k]);
    if (changed.length !== 1) throw Error('Configuration controls must change exactly one dimension');
    changedDimensions.add(changed[0]);
  }
  if (changedDimensions.size !== 2) throw Error('Both configuration dimensions require independent controls');
  if (!unique(['stage-created', 'stage-destroyed', 'application-environment-registration', ...c.configurations.map(x => x.id)]))
    throw Error('Behavior check IDs collide');
  for (const v of c.variants) {
    safe(v.path);
    if (!v.id || v.id === 'baseline' || typeof v.from !== 'string' || !v.from || typeof v.to !== 'string' ||
        v.from === v.to || !Array.isArray(v.expectedFailedChecks) || !v.expectedFailedChecks.length)
      throw Error('Invalid semantic variant');
  }
  if (!unique(c.variants.map(v => JSON.stringify([v.path, v.from, v.to])))) throw Error('Duplicate mutations');
  if (!args.includes('--typescript')) {
    if (args.includes('--typescript-sha256')) throw Error('Compiler pin without compiler');
    return {c, contractSha256: sha(bytes), retained: retainedSources(c), compiler: null, compilerSha256: null};
  }
  const compilerPath = arg('--typescript');
  if (!path.isAbsolute(compilerPath) || fs.lstatSync(compilerPath).isSymbolicLink()) throw Error('Unsafe compiler');
  const compilerSha256 = sha(fs.readFileSync(compilerPath));
  if (compilerSha256 !== arg('--typescript-sha256')) throw Error('Compiler digest differs');
  return {c, contractSha256: sha(bytes), retained: retainedSources(c), compiler: require(compilerPath), compilerSha256};
}
function blob(c, file, retained) {
  safe(file);
  if (retained) {
    const row = retained.rows.get(file);
    if (!row) throw Error('Executed path absent from retained source binding');
    return row;
  }
  const git = tail => cp.execFileSync('git', ['-C', arg('--source-repo'), ...tail], {timeout: 5000, maxBuffer: 2 * 1024 * 1024});
  const spec = c.sourceRevision + ':' + file;
  const oid = git(['rev-parse', spec]).toString().trim();
  if (git(['cat-file', '-t', oid]).toString().trim() !== 'blob') throw Error('Expected source Blob');
  const bytes = git(['cat-file', 'blob', oid]);
  return {text: bytes.toString(), identity: {path: file, gitBlobOid: oid, sha256: sha(bytes)}};
}
function worker() {
  const {c, compiler: ts, contractSha256, compilerSha256, retained} = load();
  const id = arg('--worker');
  const variant = id === 'baseline' ? null : c.variants.find(v => v.id === id);
  if (id !== 'baseline' && !variant) throw Error('Unknown variant');
  let applied = false;
  const sources = [];
  function source(file) {
    const b = blob(c, file, retained);
    sources.push({...b.identity, originalSource: b.text});
    if (!variant || variant.path !== file) return b.text;
    if (b.text.split(variant.from).length !== 2) throw Error('Mutation is absent or ambiguous');
    applied = true;
    return b.text.replace(variant.from, variant.to);
  }
  const moduleText = source(c.modulePath);
  const module = ts ? ts.parseConfigFileTextToJson(c.modulePath, moduleText) : {config: JSON.parse(moduleText)};
  if (module.error || typeof module.config?.module?.srcEntry !== 'string') throw Error('Invalid module config');
  const entry = module.config.module.srcEntry;
  if (!entry.startsWith('./')) throw Error('Unsupported module entry');
  safe(entry.slice(2));
  const stagePath = safe(path.posix.join(path.posix.dirname(c.modulePath), entry.slice(2)));
  const stage = source(stagePath);
  if (variant && !applied) throw Error('Variant did not reach executed source');
  const transformed = ts ? ts.transpileModule(stage, {fileName: stagePath,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}, reportDiagnostics: true})
    : {outputText: stage, diagnostics: []};
  if (ts && transformed.diagnostics.some(d => d.category === ts.DiagnosticCategory.Error)) throw Error('Transpile failed');
  const logs = [], registrations = [];
  const register = owner => (event, callback) => {registrations.push({owner, event, callback}); return registrations.length;};
  const app = {on: register('application')};
  class Stage { constructor() {this.context = {getApplicationContext: () => app, on: register('stage')};} onCreate() {} onDestroy() {} }
  const modules = {'@kit.AbilityKit': {AbilityStage: Stage}, '@kit.BasicServicesKit': {}};
  const context = vm.createContext({exports: {}, console: {
    info: (...x) => logs.push({level: 'info', text: x.join(' ')}),
    error: (...x) => logs.push({level: 'error', text: x.join(' ')}),
  }, require: name => {if (!(name in modules)) throw Error('Unsupported import: ' + name); return modules[name];}});
  vm.runInContext(transformed.outputText, context, {timeout: 1000});
  // Missing default export is a loader/typing failure, not a killed behavior variant.
  if (typeof context.exports.default !== 'function') throw Error('Unsupported default-export shape');
  vm.runInContext('instance = new exports.default(); instance.onCreate();', context, {timeout: 1000});
  const createLogEnd = logs.length, configurationRanges = [];
  const check = (id, passed) => ({id, passed});
  const has = marker => logs.some(l => l.level === 'info' && l.text.includes(marker));
  const checks = [check('stage-created', has(c.createMarker)),
    check('application-environment-registration', registrations.length === 1 && registrations[0].owner === 'application' &&
      registrations[0].event === c.eventName && has(c.registrationMarker))];
  for (const config of c.configurations) {
    const start = logs.length;
    context.configuration = {language: config.language, colorMode: config.colorMode};
    context.callbacks = registrations.filter(r => r.owner === 'application' && r.event === c.eventName).map(r => r.callback);
    vm.runInContext('for (const callback of callbacks) callback.onConfigurationUpdated(configuration);', context, {timeout: 1000});
    configurationRanges.push({id: config.id, start, end: logs.length, input: {...context.configuration}});
    const observations = logs.slice(start).filter(l => l.level === 'info' && l.text.startsWith(c.configurationPrefix));
    const observed = observations.map(l => {try {return JSON.parse(l.text.slice(c.configurationPrefix.length));} catch {return null;}});
    checks.push(check(config.id, observations.length === 1 && observed[0]?.language === config.language && observed[0]?.colorMode === config.colorMode));
  }
  const destroyLogStart = logs.length;
  vm.runInContext('instance.onDestroy();', context, {timeout: 1000});
  checks.push(check('stage-destroyed', logs.slice(destroyLogStart).some(l => l.level === 'info' && l.text.includes(c.destroyMarker))));
  const expected = variant?.expectedFailedChecks || [];
  if (!expected.every(id => checks.some(check => check.id === id))) throw Error('Unknown intended behavior check');
  return {id, completed: true, contractSha256, sourceRevision: c.sourceRevision, compilerSha256,
    sources, executedStagePath: stagePath, executedStageSource: stage,
    typeErasedStageSource: transformed.outputText,
    mutation: variant ? {...variant, applied: true} : null,
    checks, verdict: checks.every(c => c.passed) ? 'accept' : 'reject', logs,
    createLogEnd, destroyLogStart, configurationRanges,
    registrations: registrations.map(({owner, event}) => ({owner, event})),
    intendedFailureObserved: variant ? expected.every(id => checks.some(c => c.id === id && !c.passed)) : null};
}
function main() {
  if (args.includes('--worker')) {console.log(JSON.stringify(worker())); return;}
  const output = arg('--output');
  if (fs.existsSync(output)) throw Error('Output already exists');
  const {c, contractSha256, compiler, compilerSha256, retained} = load();
  const controls = [];
  let infrastructureFailure = null;
  for (const id of ['baseline', ...c.variants.map(v => v.id)]) {
    const start = process.hrtime.bigint();
    const r = cp.spawnSync(process.execPath, [__filename, ...args, '--worker', id], {encoding: 'utf8',
      timeout: 5000, maxBuffer: 2 * 1024 * 1024, env: {PATH: process.env.PATH || '/usr/bin:/bin'}});
    if (r.status !== 0 || r.error) {infrastructureFailure = {id, exitCode: r.status, error: r.error?.message || null, stdout: r.stdout, stderr: r.stderr}; break;}
    const observed = JSON.parse(r.stdout);
    observed.workerExecution = {exitCode: r.status, durationMs: Number((process.hrtime.bigint() - start) / 1000000n),
      stdout: r.stdout, stdoutSha256: sha(r.stdout), stderr: r.stderr};
    controls.push(observed);
  }
  const passed = !infrastructureFailure && controls[0].verdict === 'accept' &&
    controls.slice(1).every(c => c.verdict === 'reject' && c.intendedFailureObserved);
  const receipt = {schema: 'agentlab.harmony_stage_control_calibration.v2', contractSha256,
    contractReviewed: c.reviewed, diagnosticOnly: args.includes('--diagnostic-unreviewed'),
    sourceAuthority: retained?.authority || {kind: 'git-object-read', revisionAuthenticated: false},
    sourceRevision: c.sourceRevision, methodSha256: sha(fs.readFileSync(__filename)), runtime: process.version,
    compiler: {kind: compiler ? 'typescript-type-erasure-only' : 'javascript-pass-through', version: compiler?.version || null, sha256: compilerSha256}, controls, infrastructureFailure,
    semanticSeamCalibrationPassed: passed, qualified: false, automaticPromotion: false, authorityWritePerformed: false,
    limitations: ['Actual type-erased stage bodies on operator ApplicationContext dispatch seams, not Harmony framework dispatch.',
      'No ArkTS type check, HAP build, emulator, assessed Agent, case freeze or whole-candidate qualification.']};
  fs.writeFileSync(output, JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({semanticSeamCalibrationPassed: passed, qualified: false, infrastructureFailure: !!infrastructureFailure}));
  if (infrastructureFailure) process.exitCode = 1;
}
try {main();} catch (e) {console.error(e.stack); process.exitCode = 1;}
