import {reserve} from '@demo/service';

export async function checkout(tier, backend) {
  const {status, tier: resultTier, attempts} = await reserve(tier, backend);
  if (status === 'accepted') return `reserved:${resultTier}:${attempts}`;
  return `fallback:${resultTier}:${attempts}`;
}
