# AgentLab public evaluation reports

Static public projections only. This orphan branch is the GitHub Pages source.
Private traces, task archives, credentials and internal service addresses must never enter this history.
Report versions are immutable; publish a new version for revised findings.

## Long-lived report workbench

The root provides the persistent report shell (`index.html`, `workbench.css`,
`workbench.js`). The five regions stay in place while the center reads the
versioned static report. Panel visibility and selected section persist locally.
Small screens use toggleable side drawers. No backend, analytics or CDN is used.
The shell is presentation only; immutable versioned report/data remain evidence
projections. Publish normally and verify actual Pages build and exact live assets.

Splitters support pointer dragging, arrow keys (Shift = larger steps), Home and
double-click reset; the toolbar restores all default panel sizes. Persisted data
is validated and contains presentation preferences only. Report-internal links
route through the outer shell; chapter changes do not reload the report iframe.
Mobile drawers are mutually exclusive and dismiss with backdrop or Escape.
Version CSS/JS URLs when updating the shell to avoid mixed cached asset versions.

Agent report v2 (same evidence cutoff, no new executions) separates task-level
completion from stage/runtime outcomes, discloses latest Agent/thinking config,
provides metric definitions and resource-usage coverage, and links ability claims
to numbered evidence rows. Filters affect the execution ledger only; campaign
summary metrics remain fixed. Reliability, total cost and global useful-call rate
remain null without adequate evidence. Preserve v1; current portal selects v2.

Report v3 retains v1/v2 and the SAME 31-run evidence cutoff. It adds a versioned
seven-item difficulty review, eleven help/context event summaries with exact
recipient-link coverage, normalized run JSONL and a draft independent-comparison
input checklist. Review states are scoped observations, never new task scores.
Missing model IDs remain null. Readiness is reporting metadata only, not evidence
authentication or runtime permission. Historical dependent runs stay exploration
records even when some local actions were autonomous.
