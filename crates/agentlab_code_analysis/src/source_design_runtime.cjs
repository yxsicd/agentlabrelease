// Appended to an operator-generated, immutable manifest. Not a security sandbox.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const vm = require('vm');
module.exports = function createRuntime(sourceRoot, controlId, compiler) {
  const control = manifest.controls.find(c => c.id === controlId);
  if (!control) throw new Error('unknown frozen control');
  const root = fs.realpathSync(sourceRoot);
  const sources = new Map();
  for (const file of manifest.files) {
    const parts = file.path.split('/');
    if (parts.some(p => !p || p === '.' || p === '..') || path.isAbsolute(file.path))
      throw new Error('unsafe source path');
    let current = root;
    for (const part of parts) {
      current = path.join(current, part);
      if (fs.lstatSync(current).isSymbolicLink()) throw new Error('source symlink');
    }
    const bytes = fs.readFileSync(current);
    if (crypto.createHash('sha256').update(bytes).digest('hex') !== file.sha256 ||
        !bytes.equals(Buffer.from(file.content, 'utf8')))
      throw new Error('frozen source differs');
    sources.set(file.path, file.content);
  }
  for (const edit of control.edits) {
    const before = sources.get(edit.path);
    if (before === undefined || !edit.before ||
        before.split(edit.before).length !== 2)
      throw new Error('frozen edit must match exactly once');
    sources.set(edit.path, before.replace(edit.before, () => edit.after));
  }
  function source(relativePath) {
    if (!sources.has(relativePath)) throw new Error('unselected source');
    return sources.get(relativePath);
  }
  function loadModule(relativePath, imports = {}, globals = {}) {
    return loadText(relativePath, source(relativePath), imports, globals);
  }
  const readOnlySources = new Map();
  for (const file of manifest.readOnlyFiles || []) {
    if (sources.has(file.path) || readOnlySources.has(file.path) || file.access !== 'read-only' ||
        typeof file.contentUtf8 !== 'string' ||
        crypto.createHash('sha256').update(Buffer.from(file.contentUtf8, 'utf8')).digest('hex') !== file.sha256)
      throw new Error('invalid frozen read-only context');
    readOnlySources.set(file.path, file.contentUtf8);
  }
  function loadReadOnlyModule(relativePath, imports = {}, globals = {}) {
    if (!readOnlySources.has(relativePath)) throw new Error('unselected read-only source');
    return loadText(relativePath, readOnlySources.get(relativePath), imports, globals);
  }
  function loadText(relativePath, text, imports, globals) {
    if (!compiler || typeof compiler.transpileModule !== 'function')
      throw new Error('explicit compiler required');
    const parsed = compiler.createSourceFile(relativePath, text,
      compiler.ScriptTarget.ES2020, true, compiler.ScriptKind.TS);
    if (parsed.parseDiagnostics.length) throw new Error('source syntax diagnostics');
    const result = compiler.transpileModule(text, {
      fileName: relativePath.replace(/\.ets$/, '.ts'), reportDiagnostics: true,
      compilerOptions: {module: compiler.ModuleKind.CommonJS,
        target: compiler.ScriptTarget.ES2020}
    });
    if ((result.diagnostics || []).some(d => d.category === compiler.DiagnosticCategory.Error))
      throw new Error('transpile diagnostics');
    // One new module/context per call: no singleton or scenario cache leakage.
    const module = {exports: {}};
    const context = Object.assign(Object.create(null), globals);
    for (const key of ['module', 'exports', 'require']) {
      if (Object.hasOwn(globals, key)) throw new Error('reserved module binding');
    }
    Object.assign(context, {module, exports: module.exports, require(name) {
      if (!Object.hasOwn(imports, name)) throw new Error('unbound import: ' + name);
      return imports[name];
    }});
    new vm.Script(result.outputText, {filename: relativePath}).runInNewContext(context,
      {timeout: 1000});
    return module.exports;
  }
  function scenarioInputs(scenarioId) {
    const scenario = (manifest.scenarios || []).find(s => s.id === scenarioId);
    if (!scenario) throw new Error('unknown frozen input scenario');
    // Fresh data, not the Oracle: mutation cannot alter the manifest or seams.
    return JSON.parse(JSON.stringify({initialState: scenario.initialState, inputs: scenario.inputs}));
  }
  function initialStateAt(scenarioId, pointer) {
    let expected = scenarioInputs(scenarioId).initialState;
    if (typeof pointer !== 'string' || (pointer && !pointer.startsWith('/')) ||
        /~(?![01])/u.test(pointer)) throw new Error('invalid initial state pointer');
    for (const token of pointer === '' ? [] : pointer.slice(1).split('/')) {
      const key = token.replace(/~1/g, '/').replace(/~0/g, '~');
      if (expected === null || typeof expected !== 'object' ||
          !Object.hasOwn(expected, key)) throw new Error('missing initial state pointer');
      expected = expected[key];
    }
    return expected;
  }
  function assertInitialState(scenarioId, actual, pointer = '') {
    // The verifier selects a source-observable subtree, not an expected output.
    // Assertion failure must escape before invoking the method under test.
    const expected = initialStateAt(scenarioId, pointer);
    function canonical(value) {
      if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
      if (typeof value === 'number' && Number.isFinite(value)) return value;
      if (Array.isArray(value)) {
        const result = [];
        for (let i = 0; i < value.length; i++) {
          if (!Object.hasOwn(value, i)) throw new Error('non-JSON observed initial state');
          result.push(canonical(value[i]));
        }
        return {array: result};
      }
      if (value && Object.prototype.toString.call(value) === '[object Object]') {
        // Entry arrays avoid __proto__ mutation and disregard property order.
        return {object: Object.keys(value).sort().map(key => [key, canonical(value[key])])};
      }
      throw new Error('non-JSON observed initial state');
    }
    if (JSON.stringify(canonical(actual)) !== JSON.stringify(canonical(expected)))
      throw new Error('observed initial state differs: ' + scenarioId + ' ' + pointer);
  }
  function assertInitialFields(scenarioId, instance, pointer = '/fields') {
    // Expected keys select the observation, never supply observed values.
    // Only own data properties: do not execute accessors or silently use a prototype.
    const expected = initialStateAt(scenarioId, pointer);
    if (!expected || Object.prototype.toString.call(expected) !== '[object Object]' ||
        !Object.keys(expected).length) throw new Error('initial fields require a nonempty object');
    if (!instance || typeof instance !== 'object' || Array.isArray(instance))
      throw new Error('initial fields require an actual source instance');
    const observed = Object.create(null);
    for (const key of Object.keys(expected)) {
      const descriptor = Object.getOwnPropertyDescriptor(instance, key);
      if (!descriptor || !Object.hasOwn(descriptor, 'value'))
        throw new Error('initial field must be an own data property: ' + key);
      Object.defineProperty(observed, key, {value: descriptor.value, enumerable: true});
    }
    assertInitialState(scenarioId, observed, pointer);
    return observed;
  }
  function createSeams(scenarioId) {
    const scenario = (manifest.scenarios || []).find(s => s.id === scenarioId);
    if (!scenario) throw new Error('unknown frozen seam scenario');
    const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
    const calls = [], counts = Object.create(null), violations = new Set();
    const functions = Object.create(null);
    for (const [id, seam] of Object.entries(scenario.inputs.seams)) {
      functions[id] = (...args) => {
        const index = counts[id] || 0;
        counts[id] = index + 1;
        if (calls.length >= 1024) {
          violations.add('scenario call budget');
          throw new Error('scenario call budget');
        }
        // Snapshot JSON arguments before source code can mutate their objects.
        try { calls.push({seam:id, args:clone(args)}); }
        catch (error) {
          violations.add('non-JSON seam arguments: ' + id);
          throw error;
        }
        const outcome = seam.outcomes[index] || (seam.repeatLast ? seam.outcomes.at(-1) : null);
        if (!outcome) {
          violations.add('exhausted seam: ' + id);
          throw new Error('exhausted frozen seam: ' + id);
        }
        const value = clone(outcome.value);
        switch (outcome.kind) {
          case 'return': case 'return-undefined': return value;
          case 'resolve': case 'resolve-undefined': return Promise.resolve(value);
          case 'throw': throw value;
          case 'reject': return Promise.reject(value);
          default: throw new Error('unknown frozen seam outcome');
        }
      };
    }
    return Object.freeze({functions:Object.freeze(functions),
      observations:() => clone(calls),
      assertWithinBudget() {
        if (violations.size) throw new Error([...violations].join('; '));
      }});
  }
  return Object.freeze({source, loadModule, loadReadOnlyModule, scenarioInputs, assertInitialState, assertInitialFields, createSeams});
};

// Explicit convenience entry for the pinned compiler invocation protocol.
// No discovery, implicit fallback or repair of a verifier calling the legacy API.
module.exports.fromCompilerInvocation = function fromCompilerInvocation(argv) {
  if (!Array.isArray(argv) || argv.length < 5 ||
      [2, 3, 4].some(i => typeof argv[i] !== 'string' || !argv[i]))
    throw new Error('compiler invocation requires source root, control ID and pinned compiler argument');
  if (!path.isAbsolute(argv[4])) throw new Error('compiler argument must be an absolute pinned path');
  const compiler = require(argv[4]);
  if (!compiler || typeof compiler.createSourceFile !== 'function' ||
      typeof compiler.transpileModule !== 'function')
    throw new Error('compiler argument lacks required compiler API');
  return module.exports(argv[2], argv[3], compiler);
};
