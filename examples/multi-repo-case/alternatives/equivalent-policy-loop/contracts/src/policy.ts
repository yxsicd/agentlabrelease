const maxAttemptsByTier = {standard: 1, premium: 3};

export function policyFor(tier) {
  const maxAttempts = maxAttemptsByTier[tier];
  if (maxAttempts === undefined) throw new Error(`unsupported tier: ${tier}`);
  return {tier, maxAttempts};
}
