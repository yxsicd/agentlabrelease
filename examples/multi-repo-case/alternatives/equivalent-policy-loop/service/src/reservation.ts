import {policyFor} from '@demo/contracts';

export async function reserve(tier, backend) {
  const policy = policyFor(tier);
  let attempts = 0;
  while (attempts < policy.maxAttempts) {
    attempts += 1;
    if ((await backend()).ok) return {status: 'accepted', tier, attempts};
  }
  return {status: 'rejected', tier, attempts};
}
