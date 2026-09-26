#!/usr/bin/env python3
"""Create a portable handoff from a complete static assessed campaign artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harmony_assessed_handoff import HandoffError, prepare


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--campaign-id")
    args = parser.parse_args()
    try:
        value = prepare(args.root, args.output, args.campaign_id)
    except HandoffError as error:
        print(f"handoff preparation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"schema": value["schema"], "campaignId": value["campaignId"], "attemptCount": len(value["attempts"]), "ok": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
