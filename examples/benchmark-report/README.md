# Benchmark-to-Harmony evidence alignment

`compose.py` re-derives retained SWE and Terminal-Bench evaluations without
combining their rates. `harmony_alignment.py` adds a historical Calendar
supplement, system-operated UI evidence, repeated Terminal oracle trials, and a
separate no-op control. It verifies original evidence digests, exact task
checksums, evaluator identity and distinct reference trial IDs. A no-op
control is not a student attempt. The historical Calendar score remains pending
when its original record says pending; a system-operated device check is not a
student success.

The alignment command needs the same SWE assessments and Terminal paths as
`compose.py`, plus `--harmony-supplement`, `--harmony-marker`,
`--harmony-device-summary`, `--harmony-device-evidence`, and a fresh `--output`.
Optional `--oracle-repeat` and `--nop-job` point to completed Harbor jobs.
Optional `--live-host` and `--live-device` must be supplied together and are
point-in-time readbacks, not proof of durable current readiness. All evidence
paths in the generated HTML and JSON are relative to its output folder; retain
the original evidence when moving or archiving the report.

These are consistency checks, not signed provenance or an automatic release
approval. In particular, task checksum equality does not establish a separately
captured image ID for every reference trial. The next Harmony attempt still
requires fresh live instance discovery, exact old-operation readback, a frozen
recoverable task, independent positive and negative controls, and separate
student, Harness and teacher-help evidence.
