# CAP-04.S01 bounded performance qualification

Predecessor: `cb1ac8071d3644b08b021de097215bbe52607fd4`. Qualification completes
approved slice-plan sections 10–11; no product scope, security, timeout, migration,
UX reference or release-criterion change. Existing task functional evidence is
not replayed. No generic receipt system or package benchmark is introduced.

Independent reviewer `/root/cap04_s01_qualification_review` approved the prospective
comparison input at `8d932f185b9037b4d08c2f749fd36197c1057859`:
`tests/fixtures/imports/performance-baseline.json`, SHA256
`6b5a7f196046423ce3fbc07f8d79af642a15b0ce353994b4f7ea0e4a11a34a92`.
The reviewer authenticated historical report values and their tool Git blobs.
Those single diagnostic samples are not retroactively qualifying or percentiles.
Historical RAM was not captured and remains unknown.

Selected fresh work: one existing parser-memory case (100k RIS/BibTeX/CSV, two
repetitions each), two fresh-process protected review samples, and two protected
commit samples. Each protected sample gets a fresh synthetic project/vault;
Windows DPAPI, SQLCipher, Core composition and durable workers are real. ASGI
transport and native context are fixture substitutions. OS cache is not flushed.
Current hardware/RAM, runtime identity and installed-file digest are recorded;
no minimum-hardware, ordinary-read latency, native accessibility, packaging or
evidence-cache qualification is claimed.

The wrapper runs only these workloads, pins the baseline digest, locks selected
committed source/helper and installed files during execution, binds the exact
candidate, and checks input/runtime equality before final publication. It gates
every sample (not merely the median), retains raw phases/pages/facts, and reports
min/median/max. Limits are historical elapsed/worker/process-memory values plus
20%, capped at existing worker and 1200-second observation budgets; parse remains
180 seconds. Parser memory retains its exclusive 16 MiB bound; parser latency
stays descriptive. Existing product deadlines are untouched. Protected review's
observer now rejects retries as the commit observer already does.

Reports/logs stay under ignored `artifacts/tmp`. The destination is made
nonqualifying before preflight; errors, interruption, skips, missing facts,
partial traversal, input drift or any overage cannot retain a stale PASS. A
failed sample is retained without automatic retry or discarded outliers.

Focused controls cover reviewed baseline bytes/finite values and caps,
per-sample overages, missing facts/traversal/retries, exact parser inventory,
unskipped case/report inventory, failed/interrupted/final-drift publication,
confined output and the real Windows selected-file write-denial boundary.
Broad service/data/desktop profiles remain deferred to their actual integration
impact or Wave qualification; this increment does not justify replaying them.

Invocation after independent control review, from the campaign checkout with
its configured Python environment:

```text
python tools/import_performance_check.py --report artifacts/tmp/CAP-04.S01.performance-qualification-01.json
```

The tool sets its child source paths and explicit workload opt-ins itself. Unit
controls: `python -m unittest tests.service.test_import_performance_check -v`.
Actual scale results and independent result disposition are pending.

## Prerequisite-only attempt

At `7c1b4dcc`, ten exact-candidate controls passed in 1.001s; focused Ruff,
format and two-file mypy passed. A real-principal locking/import/Git preflight
then rejected the campaign's existing `.venv` junction before any workload or
project creation. It points to the repository's configured shared environment;
rejecting that launcher alias was an overly strict harness assumption, not a
product failure. The correction resolves the installed root once, binds its
digest without logging its path, and locks/hashes the actual installed bytes.
Child launches use the resolved Python executable. Links below the actual root
remain rejected; changed root/bytes still fail final equality. A focused synthetic
installed-file fingerprint control covers root binding and byte changes.

The reviewer approved that correction at
`79c4d86751361ad5f13307079314bb86ddef8f75`; eleven controls passed in 0.992s.
Its prerequisite check then rejected raw-byte equality for a nonexecuted generated
TypeScript test, because the existing checkout uses Git's CRLF conversion for
those frontend/generator files. No workload started. The selected input list is
now narrowed to executed Core source, JSON contracts/fixtures, exact workload and
measurement helpers, baseline and environment locks. TypeScript tests/generator
templates are not executed by these Python workloads; no checkout setting or
file was rewritten, and committed/raw equality remains strict for every selected
input. Existing diagnostics still retain their broader before/after inventory.
A focused inventory test verifies Core/schema inclusion and frontend exclusion.
