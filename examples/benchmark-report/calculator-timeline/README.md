# Reviewed evidence projection

This tool constructs a public, allowlisted projection of a private native event trace and its captured Gateway usage. Raw commands, outputs, credentials, task paths, and screenshots are never copied into the output. Human-reviewed annotations must be bound to the exact whole-trace SHA-256 and each command's SHA-256; all other commands stay explicitly unannotated. Native event line numbers reference the private original. Model call timestamps are a separate timeline: no timestamp or mapping is invented for command events.

Usage: `python3 project.py --trace PRIVATE_EVENTS --closed PRIVATE_USAGE --gateway-dir PRIVATE_GATEWAY --review REVIEW_JSON --out PUBLIC_JSON`. Verify the counts, independent assessment, privacy, and HTML before release. A digest is an integrity check, not proof of provenance or authorization. Tokens for cached input and reasoning are subsets, not additional usage.
