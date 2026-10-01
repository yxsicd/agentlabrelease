# Oracle repair continuation

Overall maturity remains **49%**, an engineering estimate. This round advances
the actual failure-to-repair path; it does not add an operational qualified case.

The generic Rust `--compare-oracle-repair` CLI reconstructs original and successor
diagnostics from their full byte-bound captures. It requires an explicitly linked
successor, unchanged candidate demands/selectors/runtime/deadline, a clean pinned
source and one additive commit changing only the selected test path. The complete
test-file edit remains subject to semantic review; path isolation alone cannot
prove its assertions are correct. It never promotes source or knowledge.

## Actual retained candidate repair

The original active candidate is
`shadow-case-refresh-35a06c03f9d7c77cfa6156add329c2ec`. Its local diagnostic execution
SHA256 is `83a52f4cac8cea775a8576b1ec9c2c87360313bfbb93a5b0b13d44171a7e7fdf`:
success and failure were both accepted. The original source, candidate and
knowledge cut remain unchanged.

A separate local source worktree stages a one-line assertion in the startup
test's catch branch: `expect(false).assertTrue()`. The implementation is unchanged.
The local derivative revision is `98e2483386434b08bc355c1196a98d9ade1e997e`, directly
parented by `71bbb3916625c8d9a370b7a1989b3a7f82090525`. No target repository push was
performed. The staging candidate ID is `staged-oracle-repair-abilitystage-20261001`;
its inherited knowledge/source-set references identify its original basis only,
not an admitted derivative source catalog. It is not a formal schema-admitted
candidate or TableGit authority row.

The same executor, Node and TypeScript erasure compiler executed the staged test:

| Control | Original | Repaired |
| --- | --- | --- |
| startAbility resolves | accept | accept |
| startAbility rejects | accept | reject, AssertionError |

Successor execution SHA256:
`6dd13afb58614c1107dff1629551b02b027675e49c93ccb6c3cdc446794d1b7b`.
Independent comparison returned `controlsImproved=true`,
`implementationUnchanged=true`, `nextAction=continue-runtime-calibration`, and
`qualified=false`. Complete diagnostic inputs/results/logs and comparison are
retained locally outside the source publication. This does not substitute the
successful Linux Action's separate original capture or compiler.

## Verification and remaining gates

Rust integration coverage uses two arbitrary fixture identities: an effective
repair advances; a still-vacuous repair does not. Valid captures with changed
demand, runtime budget or extra source edits are rejected. Dirty sources fail.
Existing readback rejects tampered evidence. These protocol fixtures are not real
cross-repository benchmark qualification.

Next: independently review/admit a derivative Oracle contract and its source cut,
calibrate meaningful wrong implementations, then execute the explicitly required
API22 Harmony emulator environment. Agent assessment, automatic repair generation,
cross-Action continuation, runtime/performance and second-real-repository migration
remain unproved. No formal evaluation case, TableGit write or Release was produced
by this round.
