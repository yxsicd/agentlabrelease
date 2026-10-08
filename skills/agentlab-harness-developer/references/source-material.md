# Repository evaluation material

Read before accepting a target repository for understanding, Skills construction
or evaluation. Source transport is independent from participant A/B, execution
remote/shared/native, restore level and installation components. GitHub is the
distribution authority for AgentLab; it is **not** the only permitted target
repository host.

## One input contract

Use [the request schema](../../../schemas/source-material-request.schema.json).
A campaign may declare several independently identified repositories.
The human supplies a URL or an uploaded code package, not precomputed hashes or
a prepared Git repository. The intake Agent resolves the source kind/format,
acquires under bounds and freezes machine-readable identities before import;
an observed digest pins received bytes but alone does not prove source authenticity.

- `git-http`: a credential-free HTTP(S) repository URL, optionally a requested
  branch/tag/commit. Resolve an omitted ref as the remote default once during
  acquisition, then freeze the actual full commit and Tree. A branch name or URL
  alone is not a reproducible source identity.
- `archive`: an uploaded immutable artifact ID or an HTTP(S) archive URL, with
  original SHA256, byte count and explicit format (`zip`, `tar`, `tar.gz`,
  `tar.zst`). An upload may first be hashed in bounded private staging; freeze
  that identity before importing it. Archive filenames/extensions are not format
  verification. No `.git` directory or Git history is required.

`sourceRoot` selects a relative project root explicitly. Without one, use the
package root or an unambiguous single wrapper directory. Multiple plausible
roots require a choice; never pick a random child. Retain original package
provenance and the exact root-selection transform. Detect monorepo boundaries
after import, not by assuming that one URL means one application.

The existing public Rust `agentlab-source-probe` supports
`--validate-material-request request.json`. It validates only this declaration,
with no download, extraction, execution or Session writes. It is public source
qualification, not a newly installed controller capability. Its result explicitly
leaves acquisition, byte verification, extraction and Session import false.

## Normalize once, bind every ring

Git is an execution/versioning mechanism, **not an eligibility condition**. For
non-Git code, the normal import path is: safely materialize and verify source
bytes -> initialize a new Agent-owned project Git repository -> commit the
initial source baseline -> run the same evaluation pipeline. The resulting
commit is a real generated evaluation baseline; preserve original archive
identity separately. Do not require users to prepare a Git repository first or
reduce source-only input to a second-class assessment mode.

Both sources must produce the same logical **SourceSnapshot** contract before
any real-source Skills/case admission: repository ID, source provenance, root
transform, canonical complete path/type/mode/size/content inventory, content
digest, and independently verified acquisition/import receipt. Preserve original
archive bytes as immutable evidence; Git provenance records the real commit,
Tree and available Blob identities. Never manufacture Git IDs for an archive.

The current Rust `source_material::declared_content_id` defines a v1 regular-file
content key: SHA256 of the UTF-8 compact JSON tuple
`["agentlab.source_tree.regular.v1", entries]`. Entries are structs serialized in
`path,bytes,sha256,executable` order, paths sorted bytewise, root-relative with no
wrapper or `.git`. Identical file inventories share a key regardless of transport.
Changing a path, bytes, declared hash or executable flag changes the key.
This is **declared inventory identity only**, not proof of actual bytes. Empty
directories and host UID/GID/mtimes are outside this content-key profile. v1
rejects links and special files rather than dropping or following them.

The later importer must record a provenance-bound snapshot identity in addition
to that content key. Skills, analysis facts, case seeds, initial Session state,
Attempts and returned lessons all bind that exact snapshot and applicable method
cut. Source changes invalidate admission of old evidence unless an explicit
verified rebind proves the selected scope unchanged; they never silently reuse
old Skills. Staged operator artifacts are not TableGit authority. The existing
Git-only knowledge/context consumers remain fail-closed until their snapshot
bridge is implemented and qualified; contract validation cannot satisfy them.

After initialization, ordinary code understanding, editing, build/test,
commit/branch/merge and subsequent checkpoint/Fork assessment work from that
real baseline. Only operations requiring **the original repository's history**,
such as historical repair mining or pre-import blame/refs, need that missing
history; they do not block ordinary evaluation. Capture and restore generated
project-Git state through the existing owned Workspace/Session contracts, not
through a second framework Git engine.

## Acquisition and import boundaries

Require enforced transfer bytes, expanded bytes, per-file bytes, entry count,
path depth and wall-clock limits. Current request validation checks the declared
limits, not enforcement on a network stream. The acquisition owner must implement
bounded streaming, redirects/egress policy and cancellation before runtime use.
Authorize every network destination, including redirects/DNS changes; never
forward credentials to a new origin. Configure private authentication separately;
no URL userinfo, query token, headers, credential files or Agent home in the
request, snapshot or public repository. HTTP cannot carry private credentials.

Extract into a fresh isolated staging root, never over an existing instance or
workspace. Before writes reject absolute/drive/backslash/parent paths, duplicate
normalized paths, case/Unicode conflicts under the destination filesystem,
file-directory collisions, links/special files unsupported by this profile,
oversized entries and decompression bombs. Do not run archive hooks, repository
scripts, Git hooks, LFS filters or submodule fetches while acquiring material.
Nested repositories, LFS pointers and submodules need explicit dependency
receipts; do not infer full source availability from a successful outer clone.
Preserve rejected/partial diagnostics privately without consuming the material.

## Qualification still pending

The public request and regular-file inventory validators have Rust contract
tests. URL acquisition, real ZIP/tar normalization, verified SourceSnapshot
production, automatic project-Git baseline initialization, Git-only consumer
migration, Session import and both-host end-to-end
assessment are **not performed** by this slice. Require the deployed capability
contract and independent actual-byte readback before claiming any of them.
The [source qualification receipt](../../../docs/evidence/source-material-contract-20261008.json)
records this bounded checkpoint, tested scope, earlier failures, next action and
rollback. It is not an installation or runtime intake receipt.
