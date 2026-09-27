import {policyFor} from '@demo/contracts';

export async function reserve(tier, backend) {
  const policy = policyFor(tier);
  for (let attempts = 1; attempts <= policy.maxAttempts; attempts += 1) {
    const response = await backend();
    if (response.ok) return {status: 'accepted', tier: policy.tier, attempts};
  }
  return {status: 'rejected', tier: policy.tier, attempts: policy.maxAttempts};
}
