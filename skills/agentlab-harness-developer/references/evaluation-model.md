# Evaluation model

```text
Task Seed
  -> Session
    -> Attempt
      -> Turn and event stream
        -> Checkpoint Cut
          -> derived Attempts
            -> analysis and comparison
```

A task seed contains the initial problem, fixture identity, acceptance contract,
budget, and environmental constraints. A Session is one long-lived trajectory.
An Attempt is one participant execution within a campaign matrix. A Cut binds a
restorable Harness state and its lineage revision.

Useful comparison cells include the same Agent with preserved or fresh context,
a different Agent with fresh context, a different model through the same
adapter, or the same task and cut under a changed tool/inference policy. Change
one controlled dimension at a time and retain the complete cell identity.
