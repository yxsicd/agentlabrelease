export function policyFor(tier) {
  if (tier === 'standard') return {tier, maxAttempts: 1};
  throw new Error(`unsupported tier: ${tier}`);
}
