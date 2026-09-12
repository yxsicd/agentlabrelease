#!/usr/bin/env python3
"""Render actual demo receipts as a readable GitHub job summary."""
import json
from pathlib import Path
import sys


def render(root):
    paths = sorted(root.rglob("summary.json"))
    print("## AgentLab executable demo results\n")
    print("These are scoped demonstrations; fixed-channel promotion and full whitebox qualification remain separate.\n")
    print("| Evidence | Result | Passed checks | Scope |")
    print("|---|---|---|---|")
    for path in paths:
        value = json.loads(path.read_text())
        checks = value.get("checks", {})
        count = f"{sum(v is True for v in checks.values())}/{len(checks)}" if checks else "see receipt"
        scope = value.get("scope", value.get("schema", "unspecified"))
        print(f"| `{path.relative_to(root)}` | {'PASS' if value.get('ok') is True else 'FAIL'} | {count} | {scope} |")
    if not paths:
        print("| No completed receipt | NOT VERIFIED | — | Inspect setup logs |")
    print("\nDownload this job's evidence artifact for complete requests, responses, revisions and process logs.")


if __name__ == "__main__":
    render(Path(sys.argv[1]))
