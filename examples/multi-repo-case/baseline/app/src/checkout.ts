import {reserve} from '@demo/service';

export async function checkout(tier, backend) {
  const result = await reserve(tier, backend);
  return result.status === 'accepted' ? `reserved:${result.tier}` : `fallback:${result.tier}`;
}
