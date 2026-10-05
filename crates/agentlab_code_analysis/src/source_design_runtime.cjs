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
  const childPointer = (pointer, key) => pointer + '/' + String(key).replace(/~/g, '~0').replace(/\//g, '~1');
  function valueType(value) {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'number' && !Number.isFinite(value)) return 'non-finite-number';
    return typeof value;
  }
  function initialStateError(message, scenarioId, pointer, reason, actualType, expectedType) {
    const diagnostic = {schema:'agentlab.source_initial_state_error.v1',scenarioId,
      initialStatePointer:pointer,reason,actualType,expectedType};
    const error = new Error(message + ': ' + JSON.stringify(diagnostic));
    error.initialStateDiagnostic = diagnostic;
    return error;
  }
  function assertInitialState(scenarioId, actual, pointer = '') {
    // The verifier selects a source-observable subtree, not an expected output.
    // Assertion failure must escape before invoking the method under test.
    const expected = initialStateAt(scenarioId, pointer);
    const ancestors = new Set();
    function canonical(value, location, counterpart, counterpartPresent = true) {
      const invalid = (reason, actualType = valueType(value)) => {
        throw initialStateError('non-JSON observed initial state',scenarioId,location,
          reason,actualType,counterpartPresent ? valueType(counterpart) : 'missing-property');
      };
      const next = key => counterpart !== null && typeof counterpart === 'object' && Object.hasOwn(counterpart,key);
      if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
      if (typeof value === 'number' && Number.isFinite(value)) return value;
      if (Array.isArray(value)) {
        if (ancestors.has(value)) invalid('cyclic-value');
        ancestors.add(value);
        const result = [];
        for (let i = 0; i < value.length; i++) {
          if (!Object.hasOwn(value, i)) throw initialStateError('non-JSON observed initial state',
            scenarioId,childPointer(location,i),'sparse-array','array-hole',next(i) ? valueType(counterpart[i]) : 'missing-property');
          result.push(canonical(value[i],childPointer(location,i),next(i) ? counterpart[i] : undefined,next(i)));
        }
        ancestors.delete(value);
        return {array: result};
      }
      if (value && Object.prototype.toString.call(value) === '[object Object]') {
        if (ancestors.has(value)) invalid('cyclic-value');
        ancestors.add(value);
        // Entry arrays avoid __proto__ mutation and disregard property order.
        const object = Object.keys(value).sort().map(key => [key,
          canonical(value[key],childPointer(location,key),next(key) ? counterpart[key] : undefined,next(key))]);
        ancestors.delete(value);
        return {object};
      }
      invalid('non-json-value');
    }
    const actualCanonical = canonical(actual,pointer,expected);
    const expectedCanonical = canonical(expected,pointer,undefined,false);
    const canonicalType = value => value && typeof value === 'object' ?
      (Object.hasOwn(value,'array') ? 'array' : 'object') : valueType(value);
    function mismatch(a, b, location) {
      const result = (actualType = canonicalType(a),expectedType = canonicalType(b)) =>
        ({location,actualType,expectedType});
      if (canonicalType(a) !== canonicalType(b)) return result();
      if (!a || typeof a !== 'object') return a === b ? null : result();
      if (Object.hasOwn(a,'array')) {
        for (let i = 0; i < Math.max(a.array.length,b.array.length); i++) {
          if (i >= a.array.length || i >= b.array.length) return {
            location:childPointer(location,i),actualType:i >= a.array.length ? 'missing-element' : canonicalType(a.array[i]),
            expectedType:i >= b.array.length ? 'missing-element' : canonicalType(b.array[i])};
          const difference = mismatch(a.array[i],b.array[i],childPointer(location,i));
          if (difference) return difference;
        }
        return null;
      }
      const left = new Map(a.object),right = new Map(b.object);
      for (const key of [...new Set([...left.keys(),...right.keys()])].sort()) {
        if (!left.has(key) || !right.has(key)) return {location:childPointer(location,key),
          actualType:left.has(key) ? canonicalType(left.get(key)) : 'missing-property',
          expectedType:right.has(key) ? canonicalType(right.get(key)) : 'missing-property'};
        const difference = mismatch(left.get(key),right.get(key),childPointer(location,key));
        if (difference) return difference;
      }
      return null;
    }
    const difference = mismatch(actualCanonical,expectedCanonical,pointer);
    if (difference) throw initialStateError('observed initial state differs',scenarioId,
      difference.location,'value-mismatch',difference.actualType,difference.expectedType);
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
        throw initialStateError('initial field must be an own data property',scenarioId,
          childPointer(pointer,key),'not-own-data-property',descriptor ? 'accessor' : 'missing-property',valueType(expected[key]));
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
