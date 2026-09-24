export function policyFor(tier) {
  if (tier === 'standard') return {tier, maxAttempts: 1};
  if (tier === 'premium') return {tier, maxAttempts: 3};
  throw new Error(`unsupported tier: ${tier}`);
}
