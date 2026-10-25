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
