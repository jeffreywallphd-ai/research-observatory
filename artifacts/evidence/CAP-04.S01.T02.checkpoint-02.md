# CAP-04.S01.T02 — protected preview persistence checkpoint

This is an implementation checkpoint, not a task submission or completion.
Predecessor: `5eed97f29b4e200f3b6904f74fe9de90450799ab`.
Approved W2/task authority and the acceptance map are unchanged. No human gate
is requested. CAP-04.S01.T03 still owns canonical SourceRecord/import commits.

## Bounded implementation

- Additive schema v11 uses the existing backup-first protected migration runner.
  Exact v10 schema/profile hashes and all older migration files stay unchanged.
  Empty preview tables do not fabricate import observations or decisions.
- Immutable source membership, complete-source seals, durable parse attempts,
  bounded typed IR metadata, receipt-bound completion and draft-history tables
  reside in the canonical protected database. Binary source bytes stay in the
  existing encrypted object store. Draft editing methods are not implemented yet.
- Preview chunk references join both object metadata/deletion and storage
  accounting. Cancelling one preview does not erase retained/shared references.
- Repository writes reuse the existing worker capability/lease validation inside
  the same writer transaction. Pages require the exact successful job attempt and
  its accepted workflow receipt. A provisional receipt is not an imported source
  or a successful preview. Ordinary restart fences the old attempt; security
  cancellation keeps content unavailable.
- Packaging/quality/architecture inventories and current storage contracts are
  updated together; no build-profile relaxation or new database authority.

## Preflight findings and regression selection

The independent storage preflight found a nullable-predecessor CHECK bypass.
Revision > 1 now explicitly requires a non-NULL predecessor, with an isolated
constraint regression. It also identified post-seal/post-completion insertion,
cross-job attempt pairing, populated-state and shared-reference proof obligations.
Targeted insertion guards plus transactional repository checks close implemented
boundaries; independent review must not infer future draft/UI authority from them.

Tests were added before implementation for the exact v10 upgrade/rollback and
preview intake/worker boundaries. Initial failures reproduced missing migration,
missing repository methods, zero preview reference accounting and an append after
source seal. A new synthetic v10 setting makes row preservation directly visible;
no historical fixture has been replaced or weakened.

Selected qualification: v10 upgrade and every v11 interruption step; existing
v1–v9 migration chains because their target profile changed; schema/profile parity;
actual encrypted-object intake/restart/shared-reference protection; typed record,
source/lease substitution, provisional completion, ordinary restart and security
cancellation; actual SQLCipher migration/encrypted backup with synthetic keys;
affected packaging-contract, architecture, quality, build-identity and view checks.
Post-commit results and independent disposition will be appended separately.

Deferred: native file selection, runtime worker/project-lock composition, draft
mapping/correction/group undo, duplicate candidates, complete diagnostic report,
renderer/accessibility and 100k integrated pagination. No native, Windows DPAPI,
packaged-executable or whole-task acceptance claim follows from this checkpoint.
The broad unchanged W1 profile is not selected.
