'use strict';
// Trusted compiler only: source text is data, never evaluated or required.
const fs = require('node:fs');
const crypto = require('node:crypto');
const ts = require(process.argv[1]);
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
if (typeof ts.transpileModule !== 'function' || typeof ts.createSourceFile !== 'function' ||
    typeof ts.version !== 'string') throw Error('explicit dependency is not a compiler adapter');
const files = input.files.map(file => {
  if (sha(Buffer.from(file.content)) !== file.sha256) throw Error('compiler input source drift');
  try {
  const parsed = ts.createSourceFile(file.path,file.content,ts.ScriptTarget.ES2020,true,ts.ScriptKind.TS);
  const sourceParseDiagnosticCodes = parsed.parseDiagnostics.map(d=>d.code);
  const result = ts.transpileModule(file.content, {
    fileName:file.path.replace(/\.ets$/, '.ts'), reportDiagnostics:true,
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
  });
  const diagnostics = (result.diagnostics || [])
    .filter(d => d.category === ts.DiagnosticCategory.Error)
    .map(d => ({code:d.code,start:d.start ?? null,length:d.length ?? null}));
  if (diagnostics.length > 128) throw Error('compiler diagnostics exceed capture budget');
  const emitted = ts.createSourceFile('output.js', result.outputText,
    ts.ScriptTarget.ES2020,true,ts.ScriptKind.JS);
  const specifiers = [];
  function visit(node) {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) &&
        node.expression.text === 'require' && node.arguments.length === 1 &&
        ts.isStringLiteral(node.arguments[0])) specifiers.push(node.arguments[0].text);
    ts.forEachChild(node,visit);
  }
  visit(emitted);
  if (sourceParseDiagnosticCodes.length > 128 || emitted.parseDiagnostics.length > 128)
    throw Error('compiler parse diagnostics exceed capture budget');
  return {path:file.path,sourceSha256:file.sha256,
    status:diagnostics.length || sourceParseDiagnosticCodes.length || emitted.parseDiagnostics.length ? 'transpile-errors' : 'transpiled',
    diagnostics,sourceParseDiagnosticCodes,
    emittedJavaScriptSha256:sha(Buffer.from(result.outputText)),
    emittedRequireSpecifiers:specifiers,
    emittedParseDiagnosticCodes:emitted.parseDiagnostics.map(d=>d.code)};
  } catch (error) {
    const message = String(error.message || error);
    if (message.length > 8192) throw Error('compiler error exceeds capture budget');
    return {path:file.path,sourceSha256:file.sha256,status:'compiler-error',
      compilerError:message,
      emittedJavaScriptSha256:null,emittedRequireSpecifiers:[]};
  }
});
process.stdout.write(JSON.stringify({compilerVersion:ts.version,files}));
