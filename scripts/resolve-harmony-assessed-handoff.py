#!/usr/bin/env python3
"""Resolve a portable static handoff against one qualified Harmony host."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harmony_assessed_handoff import HandoffError, resolve


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--host-profile", type=Path, required=True)
    parser.add_argument("--host-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = resolve(args.handoff, args.host_profile, args.host_root, args.output)
    except HandoffError as error:
        print(f"handoff resolution failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"schema": value["schema"], "campaignId": value["campaignId"], "attemptCount": len(value["attempts"]), "ok": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
