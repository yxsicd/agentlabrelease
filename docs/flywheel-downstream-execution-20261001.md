# Bounded downstream execution and feedback

Overall maturity estimate: **49%** (previously 48%). The increment represents
one actually executed diagnostic-to-feedback transition, not a complete
five-stage flywheel or qualified benchmark.

PR121 merged as `1265d045aa1c52d640b459a4111bcdf37ea432e0` after its CI passed.
The next implementation reuses the existing Rust process-group capture primitive.
No parallel subprocess supervisor, shell-command generator, provider secret or
physical-device fallback is introduced.

The first Linux CI run `36914161438` failed at the common file-budget check.
Executable acquisition and raw evidence must not share one size budget: use a
256 MiB bounded streaming SHA256 for executables, retaining the original 64 MiB
evidence/log bound. A sparse-file regression checks bytes beyond 64 MiB affect
the executable digest and rejects files above 256 MiB. This changes transport
compatibility, not Oracle acceptance or runtime qualification.

## Shared CLI and Action

1. Run `bash scripts/plan-maintainer-downstream.sh KNOWLEDGE EVIDENCE_ROOT OUTPUT`.
2. Select an ID in batch `activeCandidateIds`; never dispatch a historical parent.
3. Use `--prepare-downstream-probe` with `--downstream-plan`, `--source-worktree`,
   `--node`, `--probe-script`, `--test-path`, `--suite-export`, `--test-id`, optional
   `--typescript`, and `--output`. This prepares a reviewed supported adapter
   recipe; its review declaration is not authentication or a permission system.
4. Invoke `--execute-downstream-probe` with that plan, `--candidates`,
   `--candidate-id`, `--probe-recipe`, source worktree and a fresh output directory.
5. Independently hash `execution.json`. Invoke `--feedback-downstream-probe` with
   `--execution-root`, `--execution-sha256` and a fresh output file.
6. Supply the prior next-action file through `--previous-feedback-plan` for a
   bounded repeat. The same feedback selects no new scheduling.

The main-only `maintainer-downstream-probe.yml` workflow performs this recipe
against the committed knowledge/source cut, installs the existing locked
TypeScript-only runtime and retains evidence on failures too. It has contents-read
permissions and does not run an assessed Agent, use an LM Gateway Secret, update
TableGit or publish a Release. Workflow success means evidence collection and
feedback completed, not that the candidate or its Oracle passed.

## Actual local candidate transition

The active candidate was `shadow-case-refresh-35a06c03f9d7c77cfa6156add329c2ec`,
value SHA256 `a3b0f718650daea79c6e2b99565278bff3485b43396dd04d2a8acad456cec34c`.
Source revision: `71bbb3916625c8d9a370b7a1989b3a7f82090525`; startup-test Blob:
`246bf2e2ed3178ea1932d54a2f34328de403be22`; original bytes SHA256:
`5b389d208ebb6f832abe8e27d9c6a50602b35540aaf9f8d0f1558cacf21363fe`.

The process exited zero in 436 ms with source unchanged. Both injected startup
success and failure completed and were accepted, so the reconstructed next action
was `repair-independent-oracle`, not another semantic refresh. The diagnostic used
Node v26.5.1 and the retained TypeScript 4.9.5 erasure compiler, independently
pinned in the recipe and checked in both controls. This compiler differs from the
Action's locked 5.9.3 runtime; neither is an ArkTS type-check or device verdict.

Execution receipt SHA256:
`83a52f4cac8cea775a8576b1ec9c2c87360313bfbb93a5b0b13d44171a7e7fdf`.
Original raw diagnostic, inputs, stdout/stderr, lifecycle and feedback remain
outside the public source checkout. Readback verifies their exact byte counts and
hashes and reconstructs the decision without running Node or requiring the source
checkout. Repeated readback returns `awaiting-new-evidence`, scheduling false.

## Evidence boundaries and remaining work

- The seam is trusted-source-only; VM/process deadlines are not a security sandbox.
- Binary/compiler digests are not a complete OS/shared-library environment lock.
- Recorded source postconditions are not authenticated producer attestation.
- An Oracle that rejects injected failure remains unqualified until independently
  calibrated against accepted implementations and declared meaningful wrong variants.
- API22 emulator/build/runtime requirements remain unqualified; no API26 substitute.
- No new operational evaluation case, assessed Agent, multi-round autonomous repair,
  cross-repository real benchmark execution or automatic knowledge promotion.
- Previous-feedback reuse is explicit; fresh Actions do not yet load older history.

Next: repair the independent Oracle on an additive candidate/cut, preserve the
failed result, and prove that the same executor consumes changed evidence and
continues calibration. Then connect another supported adapter/repository without
weakening the acceptance gates. Protocol tests across two arbitrary source
repositories are controls, not this real migration proof.
