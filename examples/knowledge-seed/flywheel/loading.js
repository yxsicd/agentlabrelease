// Operator-owned lifecycle oracle. ArkUI rendering and HAP compilation excluded.
const fs = require('node:fs');
const vm = require('node:vm');
const text = fs.readFileSync(process.argv[2], 'utf8');
const mode = process.argv[3];
function body(name) {
  const start = text.indexOf('{', text.indexOf(name + '(): void'));
  if (start < 0) throw Error('Expected pinned lifecycle method');
  let depth = 1, end = start + 1;
  for (; depth && end < text.length; end++) {
    if (text[end] === '{') depth++;
    if (text[end] === '}') depth--;
  }
  return text.slice(start + 1, end - 1);
}
let appear = body('aboutToAppear'), disappear = body('aboutToDisappear');
if (mode !== 'baseline') appear = 'if (this.delayTimer !== -1) clearTimeout(this.delayTimer); this.showLoading = false;\n' + appear;
if (mode === 'wrong-cancel') appear = appear.replace('clearTimeout(this.delayTimer);', 'void this.delayTimer;');
let next = 0;
const timers = new Map();
const context = {
  LOADING_DELAY_THRESHOLD_SM: 350, LOADING_DELAY_THRESHOLD_LG: 400,
  BreakpointType: class {constructor(values) {this.values = values;} getValue(bp) {return this.values[bp];}},
  setTimeout: (fn, delay) => {const id = ++next; timers.set(id, {fn, delay}); return id;},
  clearTimeout: id => timers.delete(id),
};
vm.createContext(context);
vm.runInContext('this.hooks = {appear() {' + appear + '}, disappear() {' + disappear + '}};', context);
const state = {showLoading:false, delayTimer:-1, breakpoint:'sm'};
const invoke = method => context.hooks[method].call(state);
invoke('appear');
const smallDelay = timers.get(state.delayTimer).delay === 350;
timers.get(state.delayTimer).fn();
invoke('disappear'); invoke('appear');
const visibilityReset = state.showLoading === false;
invoke('appear');
const onePendingTimer = timers.size === 1;
invoke('disappear');
const cancelled = timers.size === 0;
state.breakpoint = 'lg'; invoke('appear');
const largeDelay = timers.get(state.delayTimer).delay === 400;
console.log(JSON.stringify({mode,smallDelay,visibilityReset,onePendingTimer,cancelled,largeDelay,
  pass:smallDelay && visibilityReset && onePendingTimer && cancelled && largeDelay,
  adapter:'original lifecycle bodies; timer scheduler and BreakpointType mapping are operator stubs for sm/lg',
  harmonyBuildQualified:false}));
