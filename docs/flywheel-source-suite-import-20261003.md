# Source-suite operational import integration

Overall engineering maturity remains **74%**. Accepted complete automatic
business loops remain **zero**. This change closes a format integration gap,
not durable knowledge return or demonstrated learning benefit.

PR231 merged at `3513e3b` after every applicable CI check passed. Its reviewed
source-suite lesson is retained from real Action 37147845918. The ordinary
observation import planner previously required behavior-contract.json and
behavior-capture.json, making this new export incompatible with the existing
revision-fenced import/readback path.

The planner now recognizes source-suite-inputs.json, independently reconstructs
the original suite and optional lesson-review.json, and compares every exported
table row against that reconstruction. It preserves historical analyzer identity
without asserting authentication, recording the current reconstruction consumer
separately. Mixed capture formats, missing or unresolved reviews, forged rows and
altered raw evidence are rejected. Legacy observation import is retained.

Rust regressions exercise observation and reviewed-lesson planning, exact full
readback, unchanged repeat import and historical projection preservation. Fixed
synthetic destination/receipt fixtures prove gate behavior, not remote commits.

The actual retained reviewed export from Action 37147845918 also passes the native
CLI planner: **8 tables, 207 inserted rows** against an explicitly synthetic empty
baseline. Inputs and plan are outside Release under
`flywheel-source-suite-import-sneGGh`. No model, worker or remote write was run.

Remaining boundaries: provision independent operational tables through live
contracts, retain complete raw evidence remotely, execute the native planned
transaction and exact committed readback, then explicit promotion and fixed-cut
knowledge admission. Analytical-row persistence alone explicitly leaves
remoteRawBytesPreserved=false. Neither this planner nor the importer silently
admits knowledge, authenticates a review or proves next-round consumption.
