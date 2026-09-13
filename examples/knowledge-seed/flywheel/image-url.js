// Operator-owned isolated classification oracle; not ArkTS runtime/HAP proof.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = process.argv[2];
const mode = process.argv[3];
if (!['baseline', 'reference', 'wrong-prefix'].includes(mode)) throw Error('Unknown mode');
const sourcePath = 'common/src/main/ets/util/UrlUtil.ets';
const source = fs.readFileSync(path.join(root, sourcePath), 'utf8');
const start = source.indexOf('  public static isNetUrl(');
const end = source.indexOf('\n  public static maskUrl(', start);
if (start < 0 || end < 0) throw Error('Pinned method boundaries changed');
const original = source.slice(start, end);
const adapted = original.replace('public static isNetUrl(url: string): boolean', 'isNetUrl(url)')
  .replace('lowerCaseUrl: string', 'lowerCaseUrl');
const context = {};
vm.createContext(context);
vm.runInContext('this.classifier = ({' + adapted + '}).isNetUrl;', context);
const reference = value => {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value) || /\s/.test(value)) return false;
  try { return new URL(value).hostname.length > 0; } catch { return false; }
};
const classify = mode !== 'baseline' ? reference : context.classifier;
// Expected labels are explicit task fixtures, not computed by the reference.
const fixtures = [
  ['https://example.com/a.png?x=1#part', true], ['http://example.com/a.png', true],
  ['HTTPS://EXAMPLE.COM/a.png', true], ['https://', false], ['http://', false],
  ['https://example.com:bad/a', false], ['https://exa mple.com/a', false],
  [' https://example.com/a', false], ['images/a.png', false], ['/a.png', false],
  ['file:///data/a.png', false], ['data:image/png;base64,AA==', false], ['', false], [null, false]
];
const consumers = [
  ['common/src/main/ets/component/ImageComponent.ets', 'src'],
  ['features/devpractices/src/main/ets/view/ImagePreview.ets', 'url']
].map(([file, field]) => {
  const bytes = fs.readFileSync(path.join(root, file), 'utf8');
  const expression = 'UrlUtil.isNetUrl(this.' + field + ')';
  const occurrences = bytes.split(expression).length - 1;
  if (!occurrences) throw Error('Pinned consumer no longer uses classification seam');
  return {path:file, field, expression, occurrences};
});
const cases = fixtures.map(([input, expected]) => {
  const decisions = consumers.map(consumer => ({path:consumer.path,
    actual: mode === 'wrong-prefix' && consumer.field === 'url' ? context.classifier(input) : classify(input)}));
  return {input, expected, decisions, pass:decisions.every(d => d.actual === expected)};
});
console.log(JSON.stringify({mode, pass:cases.every(c => c.pass), cases, consumers,
  originalMethod:original, adaptedMethod:adapted, referenceMethod:reference.toString(),
  adapter:'Type-erased original UrlUtil method; source-verified consumer seams invoked in isolation. Reference uses Node URL, not Harmony URL runtime.',
  qualification:'isolated-classification-and-consumer-seam', consumerBodiesExecuted:false,
  harmonyBuildQualified:false}));
