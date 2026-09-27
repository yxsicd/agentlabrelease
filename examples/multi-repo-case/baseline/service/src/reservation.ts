import {policyFor} from '@demo/contracts';

export async function reserve(tier, backend) {
  const policy = policyFor(tier);
  const response = await backend();
  return {status: response.ok ? 'accepted' : 'rejected', tier: policy.tier, attempts: 1};
}
