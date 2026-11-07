# Context history storage: isolated comparison, 2026-11-07

This is an operator-owned storage experiment, not a formal benchmark run or a
student assessment. It used the same 33 original request files (13,084,390
bytes total) from one real calculator run. The files contain private data and
are not published here. Responses and the rest of the traffic were not included.

* Isolated Git: 33 revisions of one exact JSON file. After `git gc`, Git object
  files occupied 482,196 bytes; all 33 revisions were read back byte-for-byte.
* Isolated released Session/TableGit demo on hwlinux: the existing capture
  collector stored those requests as chunked capture rows. Its report records
  1,118 rows, 34 observations, 33 files and 13,084,390 source bytes. After
  service restart, rows, payloads and files passed exact recovery. The exported
  complete session history bundle was 14,447,057 bytes; its recovered HEAD
  matched capture revision `c1855d5bcf0ee486bc9386e8a7e57def4d264ebb`.

These are different layouts and measurement units. The TableGit bundle contains
session history and metadata as well as base64-encoded chunk rows, while the
Git figure counts packed object files from a bare comparison history, not a
complete AgentLab session. The results show that this collector/layout has a
large storage cost for these repeated requests; they do not isolate TableGit's
intrinsic cost or prove a universally superior production design. Neither
comparison measures request/response capture completeness, concurrency,
latency or formal Attempt-bound admission.

The first isolated run failed before TableGit write: Docker's default bridge
was configured but its `docker0` device was absent. No resources bearing that
run's prefix remained at readback. The next isolated run used `--network none`
for empty-volume initialization, succeeded, and retained the original failure.
No host network or other instance was changed. MCPGit source revision was
`19f92d4aea35378ef7665b22df7d2b2fcb15ccd4`; Session SDK source revision was
`c075105a7ea7f37ef036ea016a71149f7d83c112`.

Formal evaluation still requires the actual execution entrypoint to persist and
verify its own Attempt-bound complete evidence. A diagnostic or this isolated
replay must not be represented as that qualification.
