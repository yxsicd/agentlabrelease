#!/usr/bin/env python3
"""Create or verify a portable completed Harmony device campaign bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harmony_device_campaign_import import ImportError, prepare_bundle, verify_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--campaign", type=Path, required=True)
    prepare.add_argument("--handoff", type=Path, required=True)
    prepare.add_argument("--host-profile", type=Path, required=True)
    prepare.add_argument("--plan", type=Path, required=True)
    prepare.add_argument("--source-run", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--static-root", type=Path, required=True)
    verify.add_argument("--source-run", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("--verification-revision", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            value = prepare_bundle(
                args.campaign.resolve(),
                args.handoff.resolve(),
                args.host_profile.resolve(),
                args.plan.resolve(),
                args.source_run.resolve(),
                args.output.resolve(),
            )
            result = {
                "ok": True,
                "schema": value["schema"],
                "campaignId": value["campaignId"],
                "output": str(args.output.resolve()),
            }
        else:
            value = verify_bundle(
                args.archive.resolve(),
                args.static_root.resolve(),
                args.source_run.resolve(),
                args.output.resolve(),
                args.verification_revision,
            )
            result = {
                "ok": True,
                "schema": value["schema"],
                "campaignId": value["campaignId"],
                "harmonyEndToEndEvidenceQualified": value[
                    "harmonyEndToEndEvidenceQualified"
                ],
                "output": str(args.output.resolve()),
            }
    except (ImportError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
