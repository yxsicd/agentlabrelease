import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';

const [root, stage] = process.argv.slice(2);
if (!root || !['turn-1', 'turn-2'].includes(stage)) {
  throw new Error('Usage: node --experimental-vm-modules oracle.mjs <source-root> <turn-1|turn-2>');
}

const bindings = new Map([
  ['@demo/contracts', path.join(root, 'contracts/src/policy.ts')],
  ['@demo/service', path.join(root, 'service/src/reservation.ts')],
]);
const cache = new Map();
async function load(file) {
  const resolved = path.resolve(file);
  if (cache.has(resolved)) return cache.get(resolved);
  const source = fs.readFileSync(resolved, 'utf8');
  const module = new vm.SourceTextModule(source, {identifier: resolved});
  cache.set(resolved, module);
  await module.link((specifier, parent) => {
    if (bindings.has(specifier)) return load(bindings.get(specifier));
    if (specifier.startsWith('.')) return load(path.resolve(path.dirname(parent.identifier), specifier));
    throw new Error(`unbound module ${specifier}`);
  });
  await module.evaluate();
  return module;
}

function backend(sequence) {
  let calls = 0;
  return {
    call: async () => ({ok: Boolean(sequence[calls++])}),
    calls: () => calls,
  };
}

const service = (await load(bindings.get('@demo/service'))).namespace;
const app = (await load(path.join(root, 'app/src/checkout.ts'))).namespace;
const checks = [];
async function check(id, expected, operation) {
  let actual;
  try { actual = await operation(); } catch (error) { actual = {error: String(error?.message || error)}; }
  checks.push({id, expected, actual, pass: JSON.stringify(actual) === JSON.stringify(expected)});
}

await check('standard-one-attempt', {status:'rejected',tier:'standard',attempts:1,calls:1}, async () => {
  const target = backend([false, true]);
  return {...await service.reserve('standard', target.call), calls:target.calls()};
});
await check('premium-third-attempt', {status:'accepted',tier:'premium',attempts:3,calls:3}, async () => {
  const target = backend([false, false, true]);
  return {...await service.reserve('premium', target.call), calls:target.calls()};
});
await check('premium-exhaustion', {status:'rejected',tier:'premium',attempts:3,calls:3}, async () => {
  const target = backend([false, false, false, true]);
  return {...await service.reserve('premium', target.call), calls:target.calls()};
});

if (stage === 'turn-2') {
  await check('accepted-consumer-output', 'reserved:premium:2', async () => {
    const target = backend([false, true]);
    return app.checkout('premium', target.call);
  });
  await check('fallback-consumer-output', 'fallback:premium:3', async () => {
    const target = backend([false, false, false]);
    return app.checkout('premium', target.call);
  });
  await check('standard-consumer-output', 'reserved:standard:1', async () => {
    const target = backend([true]);
    return app.checkout('standard', target.call);
  });
}

const receipt = {
  schema:'agentlab.multi_repo_oracle_receipt.v1',
  stage,
  pass:checks.every(row => row.pass),
  checks,
};
const canonical = JSON.stringify(receipt);
receipt.receiptSha256 = crypto.createHash('sha256').update(canonical).digest('hex');
process.stdout.write(JSON.stringify(receipt) + '\n');
