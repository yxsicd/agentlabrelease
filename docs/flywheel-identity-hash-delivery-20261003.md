# Large identity hashing and delivery latency

Overall maturity remains **71%**, an engineering estimate; accepted complete
automatic business loops remain **0**. This improves delivery throughput, not
maintainer coverage, knowledge benefit or full-loop acceptance.

At PR 199 head ecfeacfbaf90f2cdaa35218edfbcbe4d817cf452, release validation
run 37106466288 reached its 15-minute job limit during source-operation tests.
Twenty tests completed; the remaining authored-recipe test was canceled. In
the independent successful run 37106466279 the same suite took 396.45 seconds,
with authored-recipe finishing last. Thus cancellation is established, but a
deadlock is not. Release validation also has earlier preparation and later
release-build work inside the same budget.

The recipe author validates the exact executable digest on preparation and
staging. Extensive invalid/valid draft and review coverage repeatedly exercises
these gates. macOS Node here is a 49 KiB loader, while the local Linux validation
image contains a 142 MiB executable. Unoptimized SHA-256 is a plausible major
contributor; these observations alone do not establish exact cloud CPU attribution.

The workspace now optimizes only sha2 in the dev profile inherited by tests.
Project debug code/assertions, locked dependencies, release profile, executable
byte checks and all negative controls remain unchanged. No metadata cache or
timeout increase is introduced. A 64 MiB independent known-digest regression
also changes one middle byte and requires a different digest. It reports timing
without an unstable machine-dependent pass threshold.

Local macOS comparison: that first hash took 2.526502833 seconds before the
override and 138.096375 milliseconds after it (approximately 18.3 times faster).
The full 21-test source-operation suite then passed in 13.90 seconds. This is
not a claim of the same speedup for the full suite or an x86 GitHub runner.

Linux validation uses the existing arm64 image
mcpgit-validation:rust-1.96-node26 at
sha256:c5adbd7a0611e558c899e3c904051a2f7a9bbf383ef4fe663e14be1394882e91,
an ephemeral network-disabled container, read-only source and registry mounts,
and a fresh temporary target directory. The optimized 64 MiB hash passed in
124.783436 milliseconds; all 21 source-operation tests passed in 47.85 seconds
against the actual large Linux Node executable. Cloud integration and productive Agent loops require
their own subsequent execution evidence.
