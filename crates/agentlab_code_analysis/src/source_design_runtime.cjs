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
    if (!compiler || typeof compiler.transpileModule !== 'function')
      throw new Error('explicit compiler required');
    const text = source(relativePath);
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
  return Object.freeze({source, loadModule, createSeams});
};
