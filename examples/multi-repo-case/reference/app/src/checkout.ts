import {reserve} from '@demo/service';

export async function checkout(tier, backend) {
  const result = await reserve(tier, backend);
  const prefix = result.status === 'accepted' ? 'reserved' : 'fallback';
  return `${prefix}:${result.tier}:${result.attempts}`;
}
