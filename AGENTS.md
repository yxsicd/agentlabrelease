# Public report publishing

Only allowlisted report projections and static portal assets belong on this branch.
Never copy a private evaluation report or a task archive directly. Preserve existing report versions.
Validate counts, independent assessment authority, private-field omission and HTML escaping before publication.

The root is a long-lived IDE-style report workbench: persistent top navigation,
left report explorer, central reading area, right assessment context, bottom
evidence panel and status bar. Navigate reports inside this shell. Preserve
standalone versioned report URLs. Panel preferences and selected section are
browser-local, never authentication or assessment authority. Keep shell summary
metrics bound to the same reviewed public report; update them together on a new
report selection. Do not infer new results from UI state.
