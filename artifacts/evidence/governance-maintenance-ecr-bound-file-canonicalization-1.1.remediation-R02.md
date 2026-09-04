# Governance maintenance 1.1 remediation R02: exact-candidate evidence qualification

- **Predecessor commit:** `1942ab0ca231aaafd2c47aef92d11a1314b72af9`
- **Original candidate:** `fe9e5345595e12fe63887b343034bcec5796ab80`
- **Adverse review:**
  `artifacts/evidence/governance-maintenance-ecr-bound-file-canonicalization-1.1.review-R01.md`,
  SHA-256
  `c1a112c72670c58662339f731784f226f23a7b4e2a930db6b47dc63cda806694`.
- **Finding closed by this candidate:**
  `GOV-MAINT-ECR-CANON-1.1-R01-F01`.
- **Risk tier and authority:** unchanged Tier 2 authority under `GOV-MIG-0001`
  and the repository governance-automation simplification rule. This record
  corrects evidence classification only; it changes no implementation or
  product/ECR/Wave/task/release authority.

## Root cause

The 1.1 maintenance record correctly disclosed that pending ECR-0007 R02 edits
were present locally and excluded from its candidate, but its “Pre-freeze
results” did not explicitly distinguish checks of the exact supplement commit
from checks of the paired integration preview. The combined 28-test run and
full 491-page regeneration used the pending R02 Git-blob digest. They were
truthful working-tree integration previews, not exact-candidate-only evidence.

The ambiguity arose because the generator correction and its first real
consumer form a deliberately sequenced boundary: the exact supplement commit
still contains the old ECR digest and must continue to deny the repository-wide
site until the separately reviewed ECR R02 commit supplies the corrected
digest. Treating the preview as candidate-bound evidence was therefore wrong.

## Corrected evidence classification

### Exact `fe9e5345595e12fe63887b343034bcec5796ab80` evidence

- Commit ancestry, sole-parent identity, three-path scope, and diff hygiene:
  **PASS**.
- Focused review-loader regression invoked without live repository class setup:
  **PASS**. It accepts an LF Git blob with CRLF worktree materialization,
  projects the canonical digest, and denies a semantic change.
- Existing declared-source tamper regression invoked without live repository
  class setup: **PASS**; exact ECR source byte changes remain denied.
- Previously approved shared-helper regression: **PASS**, covering clean
  pending/exact-commit acceptance, pending-untracked local bytes, semantic and
  exact-commit divergence denial, and invalid-commit fail-closed behavior.
- Import identity, absence of a `planctl`/`plan_review_site` cycle, and review
  generator CLI startup: **PASS**.
- Ruff format/lint and affected mypy over the two changed Python files:
  **PASS**.
- Exact-candidate repository-wide site setup: expected **DENIAL** on the old
  `ECR-0007` `tokens.css` digest. This is the still-open ECR finding that the
  supplement enables R02 to correct; it is not a supplement code failure.

### Provisional paired integration preview—not candidate evidence

With the pending, unstaged ECR-0007 R02 source correction present locally, the
combined amendment suites passed 28 tests in 218.468 seconds, `planctl ecr
validate ECR-0007` passed, and the full 491-page review site regenerated and
validated. These results establish interface compatibility only. They are not
commit-bound evidence for the supplement and do not approve or authenticate the
pending ECR bytes.

The broad PASS may be claimed as commit-bound only after the exact ECR R02
proposal/generated projection is frozen, independently reviewed, and replayed
at that immutable candidate.

## Invariants

- The 1.1 record and adverse R01 ledger remain immutable and visible.
- No code change is required to close this evidence-only finding.
- The supplement does not make the old digest acceptable, incorporate pending
  ECR files retroactively, close `ECR-0007-R01-F01`, or authorize amendment
  execution.
- W1 remains `PAUSED`; `CAP-07.S01.T02` remains `BLOCKED` and lease-free.
- The protected untracked `artifacts/evidence/W1.A04.B00.json` witness is not
  read, edited, moved, deleted, hashed, or staged.

## Exact R02 review condition

An independent reviewer must authenticate this correction as a strict
descendant of the adverse R01 ledger, replay the exact-candidate focused checks,
confirm the paired-preview qualification, and explicitly close
`GOV-MAINT-ECR-CANON-1.1-R01-F01` before the ECR-0007 R02 candidate is frozen.

