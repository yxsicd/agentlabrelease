// Trusted-source diagnostic adapter, not a sandbox or Harmony runtime Oracle.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const crypto = require('node:crypto');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const args = process.argv.slice(2);
function value(flag) {
  const index = args.indexOf(flag);
  if (index < 0 || !args[index + 1]) throw Error('Missing ' + flag);
  return args[index + 1];
}
function source() {
  const revision = value('--revision'), file = value('--test-path');
  if (!/^[a-f0-9]{40}$/.test(revision) || file.startsWith('/') || file.split('/').some(p => !p || p === '.' || p === '..'))
    throw Error('Unsafe source identity');
  const git = tail => cp.execFileSync('git', ['-C', value('--source-repo'), ...tail], {maxBuffer: 2 * 1024 * 1024});
  const oid = git(['rev-parse', revision + ':' + file]).toString().trim();
  if (!/^[a-f0-9]{40}$/.test(oid) || git(['cat-file', '-t', oid]).toString().trim() !== 'blob')
    throw Error('Source is not an exact Git Blob');
  const bytes = git(['cat-file', 'blob', oid]);
  return {bytes, identity: {revision, path: file, gitBlobOid: oid, sha256: sha(bytes)}};
}
class Unsupported extends Error {}
function expectation(actual) {
  return {
    assertTrue: () => assert.equal(actual, true), assertFalse: () => assert.equal(actual, false),
    assertEqual: expected => assert.equal(actual, expected),
    assertDeepEquals: expected => assert.deepEqual(actual, expected),
  };
}
async function worker() {
  const input = source();
  let code = input.bytes.toString(), compiler = {kind: 'javascript-pass-through'};
  if (args.includes('--typescript')) {
    const library = value('--typescript');
    if (!path.isAbsolute(library) || fs.lstatSync(library).isSymbolicLink()) throw Error('Unsafe compiler path');
    const digest = sha(fs.readFileSync(library));
    if (digest !== value('--typescript-sha256')) throw Error('Compiler pin mismatch');
    const ts = require(library);
    const transformed = ts.transpileModule(code, {fileName: input.identity.path,
      compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}, reportDiagnostics: true});
    if (transformed.diagnostics.some(d => d.category === ts.DiagnosticCategory.Error)) throw Error('Transpile diagnostics');
    code = transformed.outputText;
    compiler = {kind: 'typescript-type-erasure-only', version: ts.version, sha256: digest};
  }
  const tests = [], hooks = {beforeAll: [], beforeEach: [], afterEach: [], afterAll: []}, events = [];
  const control = value('--worker');
  let startCalls = 0;
  const delegator = {startAbility: async () => {
    startCalls++;
    events.push({operation: 'startAbility', outcome: control});
    if (control === 'reject') throw Error('operator-injected-startAbility-rejection');
  }};
  const registry = {getAbilityDelegator: () => delegator};
  const hypium = {describe: (_name, body) => body(), it: (id, _mask, body) => tests.push({id, body}), expect: expectation};
  for (const key of Object.keys(hooks)) hypium[key] = body => hooks[key].push(body);
  const modules = {
    '@ohos/hypium': hypium,
    '@kit.TestKit': {abilityDelegatorRegistry: registry, Driver: {}, ON: {}},
    '@ohos.app.ability.abilityDelegatorRegistry': {...registry, default: registry},
    '@kit.PerformanceAnalysisKit': {hilog: {info: (...values) => events.push({log: values})}},
  };
  const context = vm.createContext({exports: {}, console: {log() {}, info() {}, error() {}},
    require: name => {if (!(name in modules)) throw new Unsupported('Unsupported import: ' + name); return modules[name];}});
  vm.runInContext(code, context, {timeout: 1000});
  const suite = context.exports[value('--suite-export')];
  if (typeof suite !== 'function') throw Error('Suite export not found');
  suite();
  const selected = tests.filter(test => test.id === value('--test-id'));
  if (selected.length !== 1) throw Error('Test selector absent or ambiguous');
  let doneCalls = 0, rejected = null;
  try {
    for (const hook of [...hooks.beforeAll, ...hooks.beforeEach]) await hook();
    const test = selected[0];
    await test.body(() => {doneCalls++;});
    if (test.body.length > 0 && doneCalls !== 1) throw new Unsupported('Callback test did not complete exactly once');
    for (const hook of [...hooks.afterEach, ...hooks.afterAll]) await hook();
  } catch (error) {
    if (error instanceof Unsupported) throw error;
    if (error.name !== 'AssertionError' && error.message !== 'operator-injected-startAbility-rejection')
      throw new Unsupported('Unmodeled test failure: ' + error.name + ': ' + error.message);
    rejected = {name: error.name, message: error.message};
  }
  if (startCalls !== 1) throw new Unsupported('Adapter requires exactly one observed startAbility call');
  return {source: input.identity, compiler, control, startCalls, doneCalls,
    verdict: rejected ? 'reject' : 'accept', rejected, events};
}
async function main() {
  if (args.includes('--worker')) { console.log(JSON.stringify(await worker())); return; }
  const output = value('--output');
  if (fs.existsSync(output)) throw Error('Output already exists');
  const input = source(), controls = [];
  for (const control of ['resolve', 'reject']) {
    const result = cp.spawnSync(process.execPath, [__filename, ...args, '--worker', control], {
      encoding: 'utf8', timeout: 5000, maxBuffer: 2 * 1024 * 1024,
      env: {PATH: process.env.PATH || '/usr/bin:/bin'},
    });
    if (result.status !== 0 || result.error) {
      const error = result.error?.message || result.stderr;
      fs.writeFileSync(output, JSON.stringify({schema: 'agentlab.hypium_failure_control_probe.v1',
        source: input.identity, controls, failedControl: control, workerExitCode: result.status,
        stdout: result.stdout, stderr: result.stderr, error,
        decision: 'probe-infrastructure-failed', qualified: false, failureSensitive: null,
        automaticPromotion: false, authorityWritePerformed: false}, null, 2) + '\n', {flag: 'wx'});
      throw Error('Probe infrastructure failure: ' + error);
    }
    const observed = JSON.parse(result.stdout);
    assert.deepEqual(observed.source, input.identity);
    controls.push(observed);
  }
  const sensitive = controls[0].verdict === 'accept' && controls[1].verdict === 'reject';
  const receipt = {schema: 'agentlab.hypium_failure_control_probe.v1', source: input.identity,
    testId: value('--test-id'), suiteExport: value('--suite-export'),
    methodSha256: sha(fs.readFileSync(__filename)), runtime: process.version, controls,
    failureSensitive: sensitive, decision: sensitive ? 'continue-runtime-calibration' : 'repair-oracle-before-runtime-calibration',
    qualified: false, automaticPromotion: false, authorityWritePerformed: false,
    limitations: ['Controlled TestKit startAbility resolve/reject seam only; not device or emulator execution.',
      'TypeScript erasure does not prove ArkTS typing or HAP build.',
      'Trusted source only; VM and subprocess deadlines are not a security sandbox.',
      'No assessed Agent, wrong-implementation calibration, benchmark freeze or runtime qualification.']};
  fs.writeFileSync(output, JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({decision: receipt.decision, failureSensitive: sensitive, qualified: false}));
}
main().catch(error => {console.error(error.stack); process.exitCode = 1;});
