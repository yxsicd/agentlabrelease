// Operator-owned isolated-method oracle. This is not ArkTS/HAP qualification.
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const mode = process.argv[3];
let adapted = source.replace('export class DebounceUtil', 'class DebounceUtil')
  .replace('private static lastClickTime: number', 'static lastClickTime')
  .replace('func: Function, wait: number', 'func, wait')
  .replace('public static debounce', 'static debounce');
if (mode !== 'baseline') {
  adapted = adapted.replace('static lastClickTime: number', 'static lastClickTime');
  adapted = adapted.replace('    return () => {', '    let lastClickTime = -Infinity;\n    return () => {')
    .replaceAll('DebounceUtil.lastClickTime', 'lastClickTime');
}
if (mode === 'wrong-boundary') adapted = adapted.replace('< wait', '<= wait');
let now = 10000;
const context = {Date: class {getTime() { return now; }}};
vm.createContext(context);
vm.runInContext(adapted + '\nthis.DebounceUtil = DebounceUtil;', context);
let a = 0, b = 0;
const first = context.DebounceUtil.debounce(() => {a++;}, 1000);
const second = context.DebounceUtil.debounce(() => {b++;}, 1000);
first(); second();
const independent = a === 1 && b === 1;
now += 100; first();
const suppress = a === 1;
now += 1000; first();
const boundary = a === 2;
// Retain prior demand after a later turn: independent callbacks still work.
const third = context.DebounceUtil.debounce(() => {b++;}, 1000);
third();
const retention = b === 2;
console.log(JSON.stringify({mode, independent, suppress, boundary, retention,
  pass: independent && suppress && boundary && retention,
  adapter: 'exact method body with explicit type erasure and operator reference transform',
  harmonyBuildQualified: false}));
