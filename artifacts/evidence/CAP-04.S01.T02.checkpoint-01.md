# CAP-04.S01.T02 — bounded groundwork integration

Candidate: `18bb29df5a02ef0b829facc5fc3c6efeb2d487e5`.
Base: `34a8015b14245ed76a6f9629a69c3ed8574bde42`.
Task status remains **IN_PROGRESS**. This is not a task submission, R01 disposition,
completed wizard, production-native qualification or slice approval.

## Delivered boundary

- Immutable mapping profiles, separate per-record decisions/corrections, explicit
  singleton conflicts, action-specific restrictive rights, streaming effective-draft
  hashing and content-free parser diagnostics.
- Shared parser/mapping normalization without changing parser semantics.
- Bounded encrypted source chunks through the existing object port, with verified
  readers closed before parser yields; no plaintext staging or new crypto.
- Worker project admission honors the already accepted UUIDv4/UUIDv7 bridge;
  job/actor identity and exact project/repository/storage checks remain intact.
- Claimed-task worksheet and generated status pages reflect incomplete work.

## Exact-candidate checks

At clean, unchanged candidate HEAD:

- 44 focused tests passed in 1.203 seconds: `test_import_drafts`,
  `test_reference_imports`, `test_reference_import_contracts`,
  `test_import_source_chunks`, `test_object_store_contract`, and the three
  worker tests for lifecycle-created project admission, invalid project IDs and
  repository/policy/storage substitution. Parser checks were selected because
  normalization moved into the shared helper; no historical full W1 suite replay.
- Ruff format/lint and Mypy passed on the ten affected/adjacent Python files.
- Architecture check passed: 13 areas, 12 modules, 5 interfaces, 3 profiles.
- Quality inventory passed: 244 governed Python files.
- Build-manifest validation passed, clean `0.1.0+g18bb29d`. This is not an
  executable/package build or native smoke test.
- Backlog views matched. Review-site validation passed before commit with the
  same generated-site inputs: 19 capabilities, 111 slices, 337 tasks, 492 pages.
- Prospective privacy hooks passed for all 21 committed entries and the message.

Independent reviewer `agent:/root/w2_source_packet_preflight` reviewed the exact
base-to-candidate delta and approved **local integration of this checkpoint**,
with no blocking findings. Fresh independent checks passed: three tests in 0.937
seconds for encrypted replay/write-lock release, revoked-rights buffered-read
denial, and rejection of reference-import as controlled egress or with an egress
destination. The reviewer changed no files and did not approve task completion.

The object-boundary tests use real encrypted objects with an explicit isolated
plaintext database fixture and synthetic keys; they do not establish production
SQLCipher/DPAPI, native file-dialog, renderer or packaged composition behavior.

## Next work and retained obligations

Continue the existing CAP-04.S01.T02 claim. Add protected preview persistence and
backup-first migration; include chunk references in deletion authority and never
delete a shared chunk when cancelling one preview. Atomically bind complete ordered
source membership and whole-source digest, preserve incomplete attempts, and join
page/draft authority to current project, parser, mapping revision and rights.
Complete mapping/exclusion diagnostics, durable-job and Core/native/UI composition,
then qualify the actual user journey and obtain the formal independent task review.
CAP-04.S01.T03 still owns canonical import commits/manifests. No later-task scope,
Wave approval, release decision or remote push is conferred by this checkpoint.
