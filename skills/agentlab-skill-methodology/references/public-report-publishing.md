# Public report publication

Publish the evaluator's reviewed output, never a student's self-grade. Keep the
private report and evidence closure as the authority; public pages are projections.
Use `scripts/export-public-evaluation.py` for the current single Calendar sample:

```sh
python3 scripts/export-public-evaluation.py --source PRIVATE_REPORT_JSON \
  --portable-validation PRIVATE_PORTABLE_VALIDATION \
  --package-digest PRIVATE_PACKAGE_DIGEST --output NEW_REPORT_DIRECTORY \
  --version YYYY-MM-DD
```

This adapter targets the retained Calendar report contract, not arbitrary report
schemas. It explicitly selects public fields and rejects private paths, endpoints,
credential patterns, inconsistent counters and student assessment authority.
Unknown input fields are omitted. Review allowlisted free text before publication;
pattern checks cannot guarantee all confidential business information is absent.
No raw trace, archive, internal operation identifier or service route is copied.
Keep original failed findings and assistance/confounders; stage qualification is
not independent whole-task completion. Do not derive model rankings from mixed
historical configurations or targeted call review.

The existing public host is https://yxsicd.github.io/agentlabrelease/ and its
source is the independent orphan `gh-pages` branch, root directory, HTTPS enabled.
Only reviewed public static files belong there; keep private repository history
out. Preserve version directories, update the portal explicitly, push normally,
read back exact commit bytes and verify live anonymous HTML/JSON and browser render.
After an unknown creation response, read the Pages API before another effect.
A 409 already-enabled response is not permission to recreate or change a site.

Initial version: reports/calendar/2026-10-25/; site commit
0e54bc90f5899b8dc8d3abc34e4f8191e88adf17. Five checks covered unknown private
field omission, private finding rejection, student-grade rejection, inconsistent
counts and HTML escaping. Seven public files total 43590 bytes. This publication
adds no new student result or independent whole-task pass.
