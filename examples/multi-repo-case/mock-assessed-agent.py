#!/usr/bin/env python3
"""Deterministic assessed-participant protocol fixture."""
import argparse
import json
import os
from pathlib import Path
import sys


POLICY = """export function policyFor(tier) {
  if (tier === 'standard') return {tier, maxAttempts: 1};
  if (tier === 'premium') return {tier, maxAttempts: 3};
  throw new Error(`unsupported tier: ${tier}`);
}
"""
SERVICE = """import {policyFor} from '@demo/contracts';

export async function reserve(tier, backend) {
  const policy = policyFor(tier);
  for (let attempts = 1; attempts <= policy.maxAttempts; attempts += 1) {
    const response = await backend();
    if (response.ok) return {status: 'accepted', tier: policy.tier, attempts};
  }
  return {status: 'rejected', tier: policy.tier, attempts: policy.maxAttempts};
}
"""
APP = """import {reserve} from '@demo/service';

export async function checkout(tier, backend) {
  const result = await reserve(tier, backend);
  const prefix = result.status === 'accepted' ? 'reserved' : 'fallback';
  return `${prefix}:${result.tier}:${result.attempts}`;
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", action="store_true", required=True)
    parser.parse_args()
    profile = os.environ.get("AGENTLAB_MOCK_ASSESSED_PROFILE", "baseline")
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("action") == "close":
            print(json.dumps({"ok": True, "closed": True}), flush=True)
            return
        stage = request["stageId"]
        workspace = Path(request["workspace"])
        if profile in {"reference", "scope-drift"}:
            if stage == "turn-1":
                (workspace / "contracts/src/policy.ts").write_text(POLICY)
                (workspace / "service/src/reservation.ts").write_text(SERVICE)
            elif stage == "turn-2":
                (workspace / "app/src/checkout.ts").write_text(APP)
        if profile == "scope-drift":
            (workspace / "participant-note.txt").write_text("unauthorized")
        print(
            json.dumps(
                {
                    "ok": True,
                    "stageId": stage,
                    "profile": profile,
                    "selfAssessment": {
                        "expectedOraclePass": profile != "baseline",
                        "confidence": 0.9,
                    },
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
