# Two-repository Harmony build fixture

This fixture composes one unsigned Stage application from exact revisions of
two repositories:

- AgentLabRelease supplies `scaffold/` and `app/Index.ets`;
- ASRelease supplies
  `web2atomic/template-sources/hybrid-base/entry/src/main/ets/modules/payment/PaymentAuthorityPolicy.ets`.

Materialize `scaffold/` at the project root, `app/` at
`entry/src/main/ets/pages`, and the ASRelease payment module directory at
`entry/src/main/ets/modules/payment`. The page imports and executes
`PaymentAuthorityScriptGenerator.classify`; the UI displays
`Multi Repo Ready` only when the returned policy program contains the expected
merchant and provider branches.

The independent emulator Oracle is `multi-repo-ready.ui`. A successful source
composition or HAP build is not by itself an evaluation-case qualification:
the exact two-repository source set still needs analyzed difficulty evidence,
explicit review, failing/reference calibration and a frozen case before it can
enter `build-harmony-evaluation-artifact.py` and
`run-harmony-evaluation-case.py`.

When the source is the output of an assessed Agent rather than the frozen
baseline, use `build-harmony-assessed-workspace.py`. It requires the passing
Harness decision and exact final workspace state, then emits the same HAP/build
receipt interface with additional participant and subject-workspace lineage.
