---
document_type: generated-backlog-status-summary
source: planning/backlog.yaml
source_sha256: 8b0ade646a8bf790290e7e9e2a0f94d1f3786e26e2d3379c66974931771d0280
generator: tools/backlog_views.py
manual_edit: prohibited
---

# Backlog status summary

> **GENERATED FILE - DO NOT EDIT.** `planning/backlog.yaml` is authoritative. Run `python tools/backlog_views.py --repo .` to regenerate this file.

## Ledger totals

| Item | Count |
|---|---:|
| Capabilities | 20 |
| Slices | 117 |
| Tasks | 356 |
| Enabler tasks | 3 |
| Waves | 12 |
| Wave approval bases | 1 |
| Wave amendments | 3 |
| Release gates | 12 |

## Status distributions

### Capability completion

| Status | Count |
|---|---:|
| `APPROVED` | 1 |
| `PAUSED` | 1 |
| `PENDING` | 18 |

### Wave campaign state

| Status | Count |
|---|---:|
| `ACTIVE` | 1 |
| `NONE` | 11 |

### Slice completion

| Status | Count |
|---|---:|
| `APPROVED` | 16 |
| `PENDING` | 101 |

### Task state

| Status | Count |
|---|---:|
| `NOT_STARTED` | 265 |
| `READY` | 1 |
| `REVIEW` | 1 |
| `DONE` | 53 |
| `DEFERRED` | 36 |

### Wave amendment lifecycle

| Status | Count |
|---|---:|
| `ADOPTED` | 3 |

### Enabler task state

| Status | Count |
|---|---:|
| `DONE` | 3 |

## Wave authority and append-only amendments

Proposal approval, materialization lifecycle, and campaign state remain distinct. A Wave approval is immutable; later authority is an ordered amendment record.

| Wave | Authority | Packet / ECR | Approval record | Lifecycle | Bootstrap | Campaign | Enabler tasks |
|---|---|---|---|---|---|---|---:|
| `W1` | `BASE` | `594e63be501711d67d17a4aef176bb9b6a8748be` | `901eb5c1351fa32c7173a5f0cebc2fdf9ddb1701` | `APPROVED` | - | - | 0 |
| `W1` | `W1.A01` | `-` | `planning/wave-amendment-approvals/W1.A01.json` | `ADOPTED` | `NONE` | `NONE` | 0 |
| `W1` | `W1.A02` | `ECR-0001` | `planning/wave-amendment-approvals/W1.A02.json` | `ADOPTED` | `APPROVED` | `COMPLETE` | 2 |
| `W1` | `W1.A03` | `ECR-0002` | `planning/wave-amendment-approvals/W1.A03.json` | `ADOPTED` | `APPROVED` | `COMPLETE` | 1 |

## Amendment-exit review and adoption projections

Immutable exit rounds, the latest completion projection, and bound adoption checkpoints remain distinct.

### Amendment-exit review and adoption — W1.A01

**Exit-review mode:** `legacy latest-completion-only projection` — no immutable exit rounds are recorded; this view does not fabricate history.

**Latest completion projection:** `APPROVED` by repository-owner at `2026-08-20T23:38:52+00:00`

**Latest completion evidence:** `planning/wave-amendment-approvals/W1.A01.json`

**Latest completion notes:** Historical authority migration only.

**Bound amendment-adoption checkpoints:**

- None

### Amendment-exit review and adoption — W1.A02

**Exit-review mode:** `append-only v1` / 4 completed round(s)

#### Exit round R01

**Immutable amendment-exit packet:** `R01` / packet SHA-256 `4e1a290f48f1ad2a5663fa1de657758aebcff7c6429deb79deb9ef419c3cf6df`

- Candidate / declared candidate / branch: `b77d5b1cea5526b391d5acbe3aa220a0ba510ca6` / `546eb572526acd2996ee2c5fb74f29135d295760` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-21T03:00:48+00:00`
- Bound exit evidence: amendment `W1.A02` / `artifacts/evidence/W1.A02.exit.json` / `fdfcbd04977e2c786caa36ad429f7713c5832fd6739663a52b0838ae64d48204` / `b77d5b1cea5526b391d5acbe3aa220a0ba510ca6`
- Acceptance-criteria SHA-256: `3144c4095e1d75a552137bb96fb35a74faa2f7eaa0c3e4f78eaaaa7ee7d15323`
- Selected-check SHA-256: `fba8ee2f3521746f6bfa8f2ee2fc2478009012967cedb4d280546496fed654fe`
- Selected checks: `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .`, `.venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved`, `git diff --check`
- Prior round / replayed open findings: `-` / -

**Disposition / reviewer / time:** `changes-requested` / b00-independent-reviewer / `2026-08-22T01:56:53+00:00`

**Reviewed state commit:** `b77d5b1cea5526b391d5acbe3aa220a0ba510ca6`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A02.exit-review-R01.json` / `758f40080e775d5ba19a78465d0ea7dec422929ff9285d61bb6978a49b1f48e7`

**Review notes:** CHANGES_REQUESTED at exact frozen state b77d5b1cea5526b391d5acbe3aa220a0ba510ca6. ECR authority, B00/T01/T02 histories, evidence hashes, privacy-safe telemetry, backlog, generated views, and 145 review pages pass. Adoption is not ready because amendment-exit evidence and checkpoint evidence are not exact-commit bound, and the exit record conflates the amendment campaign with the paused W1 campaign. No W1 qualification, adoption, G1 approval, ordinary resume, remote integration, or full W1 exit-suite claim was made.

**Findings opened:**

- `W1.A02-EXIT-R01-F01` `high` blocking=`True` criterion=`6` — Amendment-exit approval and adoption are not bound to the reviewed candidate or evidence; reproduce: The frozen completion record stores only the string artifacts/evidence/W1.A02.exit.json, without its SHA-256, candidate commit, branch, or an immutable exit-review ledger. command_amendment_review does not load or validate the exit evidence, and command_amendment_adopt revalidates amendment authority and task inventory but not the independently reviewed exit candidate/evidence. In a read-only in-memory replay, approve the current completion, replace completion.evidence with artifacts/evidence/never-reviewed-or-existing.json, and invoke adoption with artifacts/evidence/never-reviewed-checkpoint.json. Adoption succeeds, records ADOPTED and W1.CP01, and full semantic validation returns zero errors even though neither evidence path exists. An adverse amendment-exit review also lacks a frozen append-only finding/closure ledger, so a later submission can overwrite the completion projection while retaining only free-form lifecycle rationale.; remediate: Extend the frozen append-only review control to amendment exit: bind submission to exact candidate/frozen-state commit, branch, evidence path/SHA/commit, criteria and selected checks; store immutable severity-ranked exit-review attempts, findings, and closures; and make review plus adoption revalidate the exact reviewed blob and history. Store the adoption checkpoint as a validated path/SHA/commit reference and deny missing, substituted, stale, forked, dirty, or unreviewed evidence. Add adversarial tests for nonexistent and post-review-substituted exit/checkpoint evidence and preservation of a changes-requested exit round.
- `W1.A02-EXIT-R01-F02` `medium` blocking=`True` criterion=`5` — Exit evidence records an impossible mixed stopped-state tuple; reproduce: artifacts/evidence/W1.A02.exit.json records stoppedState as campaignStatus=PAUSED, campaignScope=wave-amendment, and pauseReason=amendment-hold. No campaign has that tuple. At b77d5b1, the amendment campaign is REVIEW/wave-amendment with pause_reason=null, while the W1 campaign is PAUSED/amendment-hold with the explicit ECR preparation pause reason.; remediate: Replace stoppedState with separately named exact waveCampaign and amendmentCampaign objects, preserving the exact required next transition. Regenerate and validate affected views, freeze a new evidence hash and candidate, and resubmit the amendment exit without claiming W1 qualification, adoption, or resumption.

**Prior finding closures:**

- None

#### Exit round R02

**Immutable amendment-exit packet:** `R02` / packet SHA-256 `d43be79f45d95fa3a5ae6565d737e40a8fd0d9207f2bf3588d34171a2add5bef`

- Candidate / declared candidate / branch: `85ec0972d4a823496f796de922e5ba3619c54e85` / `48017abbeb860f01591bb977c352a7d3739cc232` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-22T01:59:47+00:00`
- Bound exit evidence: amendment `W1.A02` / `artifacts/evidence/W1.A02.exit.json` / `0f195b6c97b3f01247239c23837e4081f45f5b2d862878e2a3a8ae18d196a957` / `85ec0972d4a823496f796de922e5ba3619c54e85`
- Acceptance-criteria SHA-256: `3144c4095e1d75a552137bb96fb35a74faa2f7eaa0c3e4f78eaaaa7ee7d15323`
- Selected-check SHA-256: `c7c99a81a388a5a199c6b7968c45c4a8a26a79b203f61984e3eb2694ec838216`
- Selected checks: `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_taskctl_schema tests.foundation.test_taskctl_workflow`, `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_plan_review_amendments`, `.venv\Scripts\python.exe tools\quality_check.py --repo .`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .`, `.venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved`, `git diff --check`
- Prior round / replayed open findings: `R01` / `W1.A02-EXIT-R01-F01`, `W1.A02-EXIT-R01-F02`

**Disposition / reviewer / time:** `changes-requested` / b00-independent-reviewer / `2026-08-22T02:09:50+00:00`

**Reviewed state commit:** `8df23af86380abb7359ab5a3349ac0cbc4ee7a3c`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A02.exit-review-R02.json` / `69c388e19ca03d34cf0faaf28112311d09925eb3505da539e22c4c57ac070a4a`

**Review notes:** CHANGES_REQUESTED at exact clean frozen state 8df23af86380abb7359ab5a3349ac0cbc4ee7a3c. R02 evidence is Git-bound at 85ec0972d4a823496f796de922e5ba3619c54e85 and declares implementation ancestor 48017abbeb860f01591bb977c352a7d3739cc232; both strictly descend from R01. R01 history, criteria/check/packet hashes, ECR authority, separate exact Wave/amendment campaign state, generated views, and legacy W1.A01 are truthful. R01-F02 is fixed. R01-F01 remains open because an exit-evidence payload can be relabeled as adoption evidence without documentType/target/history validation. The selected controller/schema replay is 68/69 because one historical-bootstrap fixture retains live exit-review control. Adoption is not ready; no full W1 exit suite was run.

**Findings opened:**

- `W1.A02-EXIT-R02-F01` `medium` blocking=`True` criterion=`4` — The frozen selected controller suite again depends on mutable canonical amendment state; reproduce: At 8df23af86380abb7359ab5a3349ac0cbc4ee7a3c run `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_taskctl_schema tests.foundation.test_taskctl_workflow`. It runs 69 tests and fails `test_b00_r04_historical_bootstrap_validation_does_not_depend_on_live_branch`: expected [], received `W1.A02: exit evidence waveCampaign is not the exact paused Wave state`. `canonical_workflow_with_b00_bootstrap` rewinds lifecycle, campaign, tasks, and Wave scope from the live backlog but retains the live R02 `completion.exit_review_control`; strict exit-state validation therefore leaks the later canonical submission into the historical fixture.; remediate: Make the historical bootstrap helper construct a coherent immutable pre-materialization completion state, including removal/reset of later exit-review control, or load an immutable historical fixture rather than partially rewriting the live canonical backlog. Preserve the production strict-state check. Also complete prior R01-F01 by revalidating the bound adoption payload's documentType, amendment identity, target Wave, candidate/reviewed-completion ancestry, branch, and exact approved exit history—not merely its reference label/hash. Add cross-type and wrong-target post-adoption substitution regressions, then rerun all controller/schema tests at the remediation candidate and strict-descendant frozen resubmission state with refreshed evidence/check hashes.

**Prior finding closures:**

- `W1.A02-EXIT-R01-F02` `fixed` — artifacts/evidence/W1.A02.exit.json

#### Exit round R03

**Immutable amendment-exit packet:** `R03` / packet SHA-256 `6b27d66c3f1adffdae0f3efb35a038004d381db63f22a33a83be09076cfec2f9`

- Candidate / declared candidate / branch: `f86bbb6e60203246178017cba2a69b41d0957a29` / `55bf2850a73dfde9e5ac9c712584b23132364665` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-22T02:17:29+00:00`
- Bound exit evidence: amendment `W1.A02` / `artifacts/evidence/W1.A02.exit.json` / `d7ee43166b1f57b596ed78622596ca7eac7ecb9f660a001b91f6ccb31bf3a6b5` / `f86bbb6e60203246178017cba2a69b41d0957a29`
- Acceptance-criteria SHA-256: `3144c4095e1d75a552137bb96fb35a74faa2f7eaa0c3e4f78eaaaa7ee7d15323`
- Selected-check SHA-256: `c7c99a81a388a5a199c6b7968c45c4a8a26a79b203f61984e3eb2694ec838216`
- Selected checks: `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_taskctl_schema tests.foundation.test_taskctl_workflow`, `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_plan_review_amendments`, `.venv\Scripts\python.exe tools\quality_check.py --repo .`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .`, `.venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved`, `git diff --check`
- Prior round / replayed open findings: `R02` / `W1.A02-EXIT-R01-F01`, `W1.A02-EXIT-R02-F01`

**Disposition / reviewer / time:** `approved` / b00-independent-reviewer / `2026-08-22T02:23:40+00:00`

**Reviewed state commit:** `5e270d61986111df566ceef084a60d7cf03ec635`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A02.exit-review-R03-rebound.json` / `660238108ed3527a7b58f176579e6181673373f48b24ab97609daada38acd38c`

**Review notes:** APPROVED at exact clean frozen state 5e270d61986111df566ceef084a60d7cf03ec635 on codex/w1-windows-local-runtime. The sole delta from previously approved state bd5133e2efa450832cbb1f451f01bfe64746727c is addition of the exact prior R03 ledger at artifacts/evidence/W1.A02.exit-review-R03.json, SHA-256 2faf60e09d48b67c304f425685dd07b16b5886af6173d7a040f20920377ad2a8. No backlog/state transition, implementation, submission, evidence, authority, generated-view, or workflow-control bytes changed. The current R03 submission remains semantically valid and binds artifacts/evidence/W1.A02.exit.json at SHA-256 d7ee43166b1f57b596ed78622596ca7eac7ecb9f660a001b91f6ccb31bf3a6b5 and commit f86bbb6e60203246178017cba2a69b41d0957a29, declaring remediation candidate 55bf2850a73dfde9e5ac9c712584b23132364665. R01/R02 history and both closures remain valid. The prior bounded results—70/70 controller/schema tests, 13/13 amendment review tests, quality, backlog, telemetry, review-site, generated-view, ECR authority, and diff checks—remain applicable; no unrelated or full W1 work was rerun. No W1/G1 approval or Wave resume is authorized. Adoption remains procedurally unavailable until taskctl records this exact approved review and a separately committed adoption checkpoint binds that approved completion.

**Findings opened:**

- None

**Prior finding closures:**

- `W1.A02-EXIT-R01-F01` `fixed` — Remediation candidate 55bf2850a73dfde9e5ac9c712584b23132364665 and the 70-test frozen-state controller/schema replay prove exact exit/adoption evidence, history, ancestry, branch, documentType, amendment, and target-Wave binding.
- `W1.A02-EXIT-R02-F01` `fixed` — The coherent historical bootstrap fixture at 55bf2850a73dfde9e5ac9c712584b23132364665 passes in the complete 70-test suite; the only subsequent delta is the exact prior ledger addition.

#### Exit round R04

**Immutable amendment-exit packet:** `R04` / packet SHA-256 `daaa3f2f923a1fc574b11e9acbe3e34dde89d5260b47163786e7bba95714908c`

- Candidate / declared candidate / branch: `917d8afcc594b0b9eb0df5eb095f066eb4372955` / `6f2db45108954e57a50b8f49abca7a37fa98faab` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-22T02:35:17+00:00`
- Bound exit evidence: amendment `W1.A02` / `artifacts/evidence/W1.A02.exit.json` / `6caf7ce2d52c945a9121438967351d910cb83666dd1d58d35de45882f4a9cc15` / `917d8afcc594b0b9eb0df5eb095f066eb4372955`
- Acceptance-criteria SHA-256: `3144c4095e1d75a552137bb96fb35a74faa2f7eaa0c3e4f78eaaaa7ee7d15323`
- Selected-check SHA-256: `c7c99a81a388a5a199c6b7968c45c4a8a26a79b203f61984e3eb2694ec838216`
- Selected checks: `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_taskctl_schema tests.foundation.test_taskctl_workflow`, `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_plan_review_amendments`, `.venv\Scripts\python.exe tools\quality_check.py --repo .`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .`, `.venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved`, `git diff --check`
- Prior round / replayed open findings: `R03` / -

**Disposition / reviewer / time:** `approved` / b00-independent-reviewer / `2026-08-22T02:39:36+00:00`

**Reviewed state commit:** `2d9795da2249319a8869618a2731d26e6cc6c29b`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A02.exit-review-R04.json` / `af763188f88cb3255bf0ef29b521ab2cd4e281b9d7d78a53764df37f76e8ddb3`

**Review notes:** APPROVED at exact clean frozen R04 state 2d9795da2249319a8869618a2731d26e6cc6c29b on codex/w1-windows-local-runtime. R04 evidence is Git-bound at 917d8afcc594b0b9eb0df5eb095f066eb4372955 and declares remediation candidate 6f2db45108954e57a50b8f49abca7a37fa98faab; both strictly descend from approved R03. R01-R03 attempts and lifecycle history are unchanged from the approved R03 completion, all prior findings remain closed, R04 correctly inherits no open findings, and criteria/check/packet hashes recompute exactly. Completed exit attempts are now validated against each attempt's committed reviewed backlog and Wave state rather than post-adoption live scope, while the current submission remains subject to strict live-state validation. Approved-exit reactivation is limited to lifecycle REVIEW, campaign COMPLETE, completion APPROVED, no current submission, a latest approved exit attempt, PAUSED amendment-hold Wave, exact approved authority/task inventory, clean codex execution identity, and no competing campaign; unapproved and inconsistent states remain denied. The adoption path records a commit-bound security checkpoint, changes W1 only from amendment-hold to ordinary wave scope, retains W1 status PAUSED, and validates the resulting ADOPTED state against frozen exit history. Exact selected checks pass: 71/71 controller/schema tests, 13/13 amendment review tests, quality across 113 governed Python files, backlog validation for 20 capabilities/117 slices/358 tasks/12 gates, privacy-safe telemetry, all 145 review pages, generated backlog views, approved history-bound ECR-0001 authority, and git diff hygiene. No full W1 qualification, W1/G1 review, or Wave resume was performed. Adoption is ready only after taskctl records and commits this exact R04 approval, followed by a newly committed adoption-checkpoint document binding that new approved-completion commit. The existing R03 checkpoint document is stale and must not be reused. Adoption will leave W1 PAUSED and will not itself authorize ordinary W1 resume.

**Findings opened:**

- None

**Prior finding closures:**

- None

**Current immutable amendment-exit submission awaiting review:** None

**Latest completion projection:** `APPROVED` by b00-independent-reviewer at `2026-08-22T02:39:36+00:00`

**Latest completion evidence:** `artifacts/evidence/W1.A02.exit.json`

**Latest completion notes:** APPROVED at exact clean frozen R04 state 2d9795da2249319a8869618a2731d26e6cc6c29b on codex/w1-windows-local-runtime. R04 evidence is Git-bound at 917d8afcc594b0b9eb0df5eb095f066eb4372955 and declares remediation candidate 6f2db45108954e57a50b8f49abca7a37fa98faab; both strictly descend from approved R03. R01-R03 attempts and lifecycle history are unchanged from the approved R03 completion, all prior findings remain closed, R04 correctly inherits no open findings, and criteria/check/packet hashes recompute exactly. Completed exit attempts are now validated against each attempt's committed reviewed backlog and Wave state rather than post-adoption live scope, while the current submission remains subject to strict live-state validation. Approved-exit reactivation is limited to lifecycle REVIEW, campaign COMPLETE, completion APPROVED, no current submission, a latest approved exit attempt, PAUSED amendment-hold Wave, exact approved authority/task inventory, clean codex execution identity, and no competing campaign; unapproved and inconsistent states remain denied. The adoption path records a commit-bound security checkpoint, changes W1 only from amendment-hold to ordinary wave scope, retains W1 status PAUSED, and validates the resulting ADOPTED state against frozen exit history. Exact selected checks pass: 71/71 controller/schema tests, 13/13 amendment review tests, quality across 113 governed Python files, backlog validation for 20 capabilities/117 slices/358 tasks/12 gates, privacy-safe telemetry, all 145 review pages, generated backlog views, approved history-bound ECR-0001 authority, and git diff hygiene. No full W1 qualification, W1/G1 review, or Wave resume was performed. Adoption is ready only after taskctl records and commits this exact R04 approval, followed by a newly committed adoption-checkpoint document binding that new approved-completion commit. The existing R03 checkpoint document is stale and must not be reused. Adoption will leave W1 PAUSED and will not itself authorize ordinary W1 resume.

**Bound amendment-adoption checkpoints:**

- `W1.CP01` `security` by codex at `2026-08-22T02:41:21+00:00` — Adopt independently approved W1.A02 workflow controls via exact R04 completion and commit-bound checkpoint; keep W1 paused for user handoff.
  - amendment `W1.A02` / `artifacts/evidence/W1.A02.adoption-R04.json` / `a43890b792808b848e4dd16bbd0ba8bc59aa2fc71a9fb08d33a0284e5da2a88f` / `996a6479dd7aae3422f73593097134b3b12a75fc`

### Amendment-exit review and adoption — W1.A03

**Exit-review mode:** `append-only v1` / 2 completed round(s)

#### Exit round R01

**Immutable amendment-exit packet:** `R01` / packet SHA-256 `5215368cda1222cba94f5ce662ceda2d6833500c77f9097fe650d87221e4172e`

- Candidate / declared candidate / branch: `69eeec6e388969a40d20fcb80939ca137158bc1a` / `f47241972c1e8c0be3d53c822d921dd142b65996` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-22T20:20:19+00:00`
- Bound exit evidence: amendment `W1.A03` / `artifacts/evidence/W1.A03.exit.json` / `c581e22cca63c5d572eb74f1c12e396480b31c5a2cffa403b44f24d848dc0f9e` / `69eeec6e388969a40d20fcb80939ca137158bc1a`
- Acceptance-criteria SHA-256: `f635fa4498c417483b2d2ba94efbce76855a652824a0f369d2bcdcd5c2333f6a`
- Selected-check SHA-256: `0da9b48b577b70ba4f6971602b86345c2741a596c918457a6155387991c33701`
- Selected checks: `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_task_recovery tests.foundation.test_taskctl_schema tests.foundation.test_taskctl_workflow tests.foundation.test_ui_change_gate`, `.venv\Scripts\python.exe tools\ui_change_gate.py --repo . --base bfb8797398707bece9e0662c0d995fabaced9979 --head 59079efccc122a7d56a9f18efc20030851bf32a9`, `.venv\Scripts\python.exe -m unittest -v tests.security.test_privacy_controls tests.contracts.test_privacy_policy_contract`, `.venv\Scripts\python.exe tools\quality_check.py --repo .`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0002 --require-approved; .venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved; .venv\Scripts\python.exe tools\recoveryctl.py --repo . validate GRR-0001 --require-approved`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .; .venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `git diff --exit-code 59079efccc122a7d56a9f18efc20030851bf32a9 HEAD -- apps/desktop services/core-api packages/contracts artifacts/evidence/ui-change/CAP-02.S04.T03.json docs/adr/ADR-0019-enforce-project-privacy-through-append-only-local-policy.md docs/architecture/privacy-controls.md tests/security/test_privacy_controls.py tests/contracts/test_privacy_policy_contract.py`, `git diff --check`
- Prior round / replayed open findings: `-` / -

**Disposition / reviewer / time:** `approved` / b00-independent-reviewer / `2026-08-22T20:27:47+00:00`

**Reviewed state commit:** `51da3a8d0cf46a2c157cea2eb618b298c9f4bd7d`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A03.exit-review-R01.json` / `be53d4ffe2765d02c0a557363bf055b67176a3f00f666b6d6a86c26ca984fc26`

**Review notes:** APPROVED at exact clean frozen exit-submission state 51da3a8d0cf46a2c157cea2eb618b298c9f4bd7d on codex/w1-windows-local-runtime. Exit evidence is Git-bound at 69eeec6e388969a40d20fcb80939ca137158bc1a, SHA-256 c581e22cca63c5d572eb74f1c12e396480b31c5a2cffa403b44f24d848dc0f9e, and truthfully declares completed-task candidate f47241972c1e8c0be3d53c822d921dd142b65996. The exact W1 base plus adopted W1.A01/W1.A02 chain and approved ECR-0002/W1.A03 authority remain ordered, hash-bound, and ancestral. W1.A03.B00 is independently approved at exact two-file scope; W1.A03.T01 is DONE with immutable R01/R02 history, and R02 explicitly closes W1.A03.T01-R01-F01/F02. Generic packet integrity, full historical/current T03 contract binding, real one-save persistence, competing-writer CAS preservation, and fail-closed recovery denials remain intact. W1 remains PAUSED with scope amendment-hold, HOLD-W1-GRR-0001 remains ACTIVE, CAP-02.S04.T03 remains BLOCKED with no recovery_control, no evidence or review, and G1 remains PENDING. Ordinary task records, release gates, protected product/runtime, privacy, approved-reference, canonical profile, and threshold bytes are unchanged. Independent replay passed 101/101 focused controller/schema/workflow/UI tests in 166.550 seconds, the exact cumulative UI command, 9/9 privacy tests, backlog and privacy-safe review-telemetry validation, ECR-0002/ECR-0001/GRR-0001 authority validation, 119-file quality, all 148 review pages, generated backlog views, protected-byte diff, and Git hygiene. The live recovery command is denied byte-stably by the active governance hold. No W1 product qualification, Wave resume, T03 approval, slice approval, W1 completion, G1 approval, local-main integration, or remote action is claimed. Adoption is the only lawful next lifecycle transition after this ledger is recorded and committed; it requires a newly committed checkpoint document bound to that approved-completion state, must record the W1 control/security checkpoint, and must leave W1 PAUSED. GRR release and explicit ordinary W1 resume remain separate later gates.

**Findings opened:**

- None

**Prior finding closures:**

- None

#### Exit round R02

**Immutable amendment-exit packet:** `R02` / packet SHA-256 `520ed2baf33d2dcb57d56519557388db0ce1005768d856e0bac869584ead8c6c`

- Candidate / declared candidate / branch: `b4e76925e9b72d99c616a2f6d26fce6e923636c2` / `c5ea2e7b44897077f7d617431cb8740b7f7dad4f` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-22T20:48:57+00:00`
- Bound exit evidence: amendment `W1.A03` / `artifacts/evidence/W1.A03.exit-remediation-01.json` / `819c25fd427533a509bf2d19a54100b872e4765343aeb65214572dcd9a339fc6` / `b4e76925e9b72d99c616a2f6d26fce6e923636c2`
- Acceptance-criteria SHA-256: `f635fa4498c417483b2d2ba94efbce76855a652824a0f369d2bcdcd5c2333f6a`
- Selected-check SHA-256: `d8110862b2292ae53cb952cd57e9304d39d2e62164cfad40280cefa5d0945a56`
- Selected checks: `.venv\Scripts\python.exe -m unittest -v tests.foundation.test_task_recovery tests.foundation.test_taskctl_schema tests.foundation.test_taskctl_workflow tests.foundation.test_ui_change_gate`, `.venv\Scripts\python.exe tools\ui_change_gate.py --repo . --base bfb8797398707bece9e0662c0d995fabaced9979 --head 59079efccc122a7d56a9f18efc20030851bf32a9`, `.venv\Scripts\python.exe -m unittest -v tests.security.test_privacy_controls tests.contracts.test_privacy_policy_contract`, `.venv\Scripts\python.exe tools\quality_check.py --repo .`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0002 --require-approved; .venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved; .venv\Scripts\python.exe tools\recoveryctl.py --repo . validate GRR-0001 --require-approved`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .; .venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `git diff --exit-code 59079efccc122a7d56a9f18efc20030851bf32a9 HEAD -- apps/desktop services/core-api packages/contracts artifacts/evidence/ui-change/CAP-02.S04.T03.json docs/adr/ADR-0019-enforce-project-privacy-through-append-only-local-policy.md docs/architecture/privacy-controls.md tests/security/test_privacy_controls.py tests/contracts/test_privacy_policy_contract.py`, `git diff --check c9ef5be1faf0119562b036c2b5eed882fab08b24..c5ea2e7b44897077f7d617431cb8740b7f7dad4f`
- Prior round / replayed open findings: `R01` / -

**Disposition / reviewer / time:** `approved` / b00-independent-reviewer / `2026-08-22T20:56:23+00:00`

**Reviewed state commit:** `f138b3c80729f06fa343d65e2043241097f9fa11`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A03.exit-review-R02.json` / `0797ea731286cac02f583e5bf0d40b9c52ab1b524c776345f877534d4be974d9`

**Review notes:** APPROVED at exact clean frozen R02 state f138b3c80729f06fa343d65e2043241097f9fa11 on codex/w1-windows-local-runtime. Remediation candidate c5ea2e7b44897077f7d617431cb8740b7f7dad4f is a strict descendant of approved R01 history; evidence artifacts/evidence/W1.A03.exit-remediation-01.json is committed at b4e76925e9b72d99c616a2f6d26fce6e923636c2 with SHA-256 819c25fd427533a509bf2d19a54100b872e4765343aeb65214572dcd9a339fc6. The R01 ledger remains byte-identical to its 89935d7c9c0473bd967810039d6a726a4be2c4fe Git blob, and the stored R01 attempt is unchanged from that approved historical state. The first adoption attempt failed before persistence: commits 89935d7c9c0473bd967810039d6a726a4be2c4fe and fb8bec15e0b02e521955269beabd7eb5a912d756 reference the identical planning/backlog.yaml object, and the sole intervening change is the inert R01 adoption-evidence file. Reactivation and R02 submission are append-only. Adopted-amendment validation now selects security checkpoints only when a bound amendment-adoption-evidence reference carries the exact amendment_id, so W1.A02 validates against W1.CP01 rather than a later W1.A03 checkpoint. A projected consecutive W1.A02/W1.A03 adoption using real historical backlog and evidence commits validates successfully. All eight ECR-0002/W1.A03 exit criteria remain satisfied: B00 and T01 approvals/histories are intact; T01 R01 blockers remain closed; generic packet, full T03 contract, one-save persistence, stale-writer, recovery denial, and adoption-boundary protections remain green. Independent replay passed 103/103 focused controller/schema/workflow/UI tests in 194.409 seconds, including both new adoption regressions; the exact UI command, 9/9 privacy tests, backlog and privacy-safe telemetry, ECR-0002/ECR-0001/GRR-0001 authority, 119-file quality, all 148 review pages, generated backlog views, protected-byte diff, exact R02 hashes, and Git hygiene pass. W1 remains PAUSED with scope amendment-hold, HOLD-W1-GRR-0001 remains ACTIVE, CAP-02.S04.T03 remains BLOCKED with no recovery_control, evidence, or review, and G1 remains PENDING. No ordinary task record, product/runtime, approved reference, canonical profile/threshold, predecessor authority, release gate, W1 qualification, local-main, remote, or ordinary-W1 authority changed. Adoption is ready only after this R02 approval is recorded and committed and a new adoption-checkpoint document is committed that binds that exact R02-approved completion; artifacts/evidence/W1.A03.adoption.json binds R01 and must not be reused. Adoption must leave W1 PAUSED. GRR release and explicit ordinary W1 resume remain separate later transitions.

**Findings opened:**

- None

**Prior finding closures:**

- None

**Current immutable amendment-exit submission awaiting review:** None

**Latest completion projection:** `APPROVED` by b00-independent-reviewer at `2026-08-22T20:56:23+00:00`

**Latest completion evidence:** `artifacts/evidence/W1.A03.exit-remediation-01.json`

**Latest completion notes:** APPROVED at exact clean frozen R02 state f138b3c80729f06fa343d65e2043241097f9fa11 on codex/w1-windows-local-runtime. Remediation candidate c5ea2e7b44897077f7d617431cb8740b7f7dad4f is a strict descendant of approved R01 history; evidence artifacts/evidence/W1.A03.exit-remediation-01.json is committed at b4e76925e9b72d99c616a2f6d26fce6e923636c2 with SHA-256 819c25fd427533a509bf2d19a54100b872e4765343aeb65214572dcd9a339fc6. The R01 ledger remains byte-identical to its 89935d7c9c0473bd967810039d6a726a4be2c4fe Git blob, and the stored R01 attempt is unchanged from that approved historical state. The first adoption attempt failed before persistence: commits 89935d7c9c0473bd967810039d6a726a4be2c4fe and fb8bec15e0b02e521955269beabd7eb5a912d756 reference the identical planning/backlog.yaml object, and the sole intervening change is the inert R01 adoption-evidence file. Reactivation and R02 submission are append-only. Adopted-amendment validation now selects security checkpoints only when a bound amendment-adoption-evidence reference carries the exact amendment_id, so W1.A02 validates against W1.CP01 rather than a later W1.A03 checkpoint. A projected consecutive W1.A02/W1.A03 adoption using real historical backlog and evidence commits validates successfully. All eight ECR-0002/W1.A03 exit criteria remain satisfied: B00 and T01 approvals/histories are intact; T01 R01 blockers remain closed; generic packet, full T03 contract, one-save persistence, stale-writer, recovery denial, and adoption-boundary protections remain green. Independent replay passed 103/103 focused controller/schema/workflow/UI tests in 194.409 seconds, including both new adoption regressions; the exact UI command, 9/9 privacy tests, backlog and privacy-safe telemetry, ECR-0002/ECR-0001/GRR-0001 authority, 119-file quality, all 148 review pages, generated backlog views, protected-byte diff, exact R02 hashes, and Git hygiene pass. W1 remains PAUSED with scope amendment-hold, HOLD-W1-GRR-0001 remains ACTIVE, CAP-02.S04.T03 remains BLOCKED with no recovery_control, evidence, or review, and G1 remains PENDING. No ordinary task record, product/runtime, approved reference, canonical profile/threshold, predecessor authority, release gate, W1 qualification, local-main, remote, or ordinary-W1 authority changed. Adoption is ready only after this R02 approval is recorded and committed and a new adoption-checkpoint document is committed that binds that exact R02-approved completion; artifacts/evidence/W1.A03.adoption.json binds R01 and must not be reused. Adoption must leave W1 PAUSED. GRR release and explicit ordinary W1 resume remain separate later transitions.

**Bound amendment-adoption checkpoints:**

- `W1.CP02` `security` by codex at `2026-08-22T20:58:21+00:00` — Adopt independently approved W1.A03 through the R02-bound control/security checkpoint; keep W1 paused pending GRR-0001 release and explicit ordinary Wave resume.
  - amendment `W1.A03` / `artifacts/evidence/W1.A03.adoption-R02.json` / `bd8085d6a9996bdf03ed21876740893470a330c4944f3ea6f7d2f61889f1418e` / `e125f983fcc2b5827516a97a811e53b822d2bd9f`


## Task review history projections

Append-only rounds remain distinct from the current latest-review projection. Legacy records are labeled latest-review-only and receive no synthesized rounds.

| Task | Mode | Completed rounds | Current submission | Latest projection | Open findings |
|---|---|---:|---|---|---|
| `CAP-00.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S01.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S01.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S02.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S02.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S02.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S03.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S03.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S03.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-security-review | - |
| `CAP-00.S04.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S04.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S04.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S05.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S05.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S05.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S06.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S06.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-00.S06.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-00.S06.T04` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-01.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-01.S01.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S01.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S02.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S02.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S02.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S03.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S03.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S03.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-01.S04.T01` | `legacy latest-review-only` | 0 | `-` | approved / curie | - |
| `CAP-01.S04.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-01.S04.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S01.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S01.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S02.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S02.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S02.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S03.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S03.T02` | `legacy latest-review-only` | 0 | `-` | approved / t02_security_review | - |
| `CAP-02.S03.T03` | `legacy latest-review-only` | 0 | `-` | approved / independent-agent-t03-slice-remediation | - |
| `CAP-02.S04.T01` | `legacy latest-review-only` | 0 | `-` | approved / cap02_s04_t01_security_review | - |
| `CAP-02.S04.T02` | `append-only v1` | 2 | `-` | approved / b00-independent-reviewer | - |
| `CAP-02.S04.T03` | `append-only v1` | 3 | `-` | approved / nash-independent-reviewer | - |
| `CAP-02.S04.T04` | `append-only v1` | 1 | `-` | approved / nash-independent-security-reviewer | - |
| `CAP-03.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-03.S01.T02` | `append-only v1` | 2 | `-` | approved / nash-independent-domain-lifecycle-reviewer | - |
| `CAP-03.S01.T03` | `append-only v1` | 3 | `-` | approved / nash-independent-domain-compatibility-reviewer | - |
| `CAP-03.S02.T01` | `append-only v1` | 2 | `-` | approved / codex-independent | - |
| `CAP-03.S02.T02` | `append-only v1` | 5 | `-` | approved / codex-independent-native-intent-boundary-reviewer | - |
| `CAP-03.S02.T03` | `append-only v1` | 4 | `-` | approved / codex-independent-epistemic-governance-reviewer | - |
| `CAP-03.S03.T01` | `append-only v1` | 3 | `-` | approved / codex-independent-provenance-contract-reviewer | - |
| `CAP-03.S03.T02` | `append-only v1` | 3 | `-` | approved / codex-independent-provenance-ledger-reviewer | - |
| `CAP-03.S03.T03` | `append-only v1` | 0 | `R01` | - / - | - |
| `CAP-07.S01.T01` | `append-only v1` | 2 | `-` | approved / codex-independent | - |
| `W1.A02.T01` | `append-only v1` | 2 | `-` | approved / b00-independent-reviewer | - |
| `W1.A02.T02` | `append-only v1` | 2 | `-` | approved / b00-independent-reviewer | - |
| `W1.A03.T01` | `append-only v1` | 2 | `-` | approved / b00-independent-reviewer | - |
## Wave progress

| Wave | Pre-Wave approval | Campaign | Qualification | Approved slices | Done tasks | Exit gate |
|---|---|---|---|---:|---:|---|
| `W0` - Engineering foundation | `APPROVED` | `NONE` | `APPROVED` | 6/6 | 19/19 | `G0` / `APPROVED` |
| `W1` - Windows local runtime and durable core | `APPROVED` | `ACTIVE` | `IN_PROGRESS` | 10/15 | 34/48 | `G1` / `PENDING` |
| `W2` - Windows local evidence foundation | `PENDING` | `NONE` | `PENDING` | 0/11 | 0/33 | `G2` / `PENDING` |
| `W3` - Windows local research workbench | `PENDING` | `NONE` | `PENDING` | 0/16 | 0/48 | `G3` / `PENDING` |
| `W4` - Windows scholarly reasoning and novelty MVP | `PENDING` | `NONE` | `PENDING` | 0/9 | 0/27 | `G4` / `PENDING` |
| `W5` - Windows PC/lab production release | `PENDING` | `NONE` | `PENDING` | 0/8 | 0/25 | `G5` / `PENDING` |
| `W6` - Cross-platform desktop qualification | `PENDING` | `NONE` | `PENDING` | 0/6 | 0/18 | `G6` / `PENDING` |
| `W7` - Study design and manuscript foundations | `PENDING` | `NONE` | `PENDING` | 0/13 | 0/39 | `G7` / `PENDING` |
| `W8` - Results integration, manuscript drafting, and reviewer simulation | `PENDING` | `NONE` | `PENDING` | 0/18 | 0/54 | `G8` / `PENDING` |
| `W9` - Advanced research-intelligence preview | `PENDING` | `NONE` | `PENDING` | 0/3 | 0/9 | `G9` / `PENDING` |
| `W10` - University-hosted pilot | `PENDING` | `NONE` | `PENDING` | 0/6 | 0/18 | `G10` / `PENDING` |
| `W11` - Managed cloud delivery | `PENDING` | `NONE` | `PENDING` | 0/6 | 0/18 | `G11` / `PENDING` |

## Capability progress

| Capability contribution | Legacy campaign | Completion | Approved slices | Done tasks | Active task |
|---|---|---|---:|---:|---|
| CAP-delivery-foundation (`CAP-00`) — Delivery foundation and Codex execution system | `COMPLETE` | `APPROVED` | 6/6 | 19/19 | - |
| CAP-windows-desktop-runtime (`CAP-01`) — Windows-first desktop shell and supervised local runtime | `PAUSED` | `PAUSED` | 4/5 | 12/15 | - |
| CAP-local-project-storage (`CAP-02`) — Local projects, durable storage, security, and recovery | `NONE` | `PENDING` | 4/5 | 13/16 | - |
| CAP-research-domain-workflows (`CAP-03`) — Canonical domain, research intent, provenance, and durable workflows | `NONE` | `PENDING` | 2/6 | 8/20 | `CAP-03.S03.T03` |
| CAP-scholarly-ingestion (`CAP-04`) — Scholarly ingestion, connectors, canonicalization, and corpus governance | `NONE` | `PENDING` | 0/5 | 0/15 | - |
| CAP-document-inspection (`CAP-05`) — Document acquisition, parsing, source inspection, and page anchors | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-search-screening (`CAP-06`) — Local search, discovery, corpus diagnostics, and screening | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-model-gateway (`CAP-07`) — Provider-neutral model gateway and governed AI execution | `NONE` | `PENDING` | 0/5 | 1/15 | - |
| CAP-evidence-verification (`CAP-08`) — Evidence schemas, extraction, verification, and adjudication | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-scholarly-graph-synthesis (`CAP-09`) — Scholarly graph, comparison sets, synthesis, and reproducibility | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-novelty-opportunities (`CAP-10`) — Novelty auditing, research opportunities, and plural research modes | `NONE` | `PENDING` | 0/7 | 0/21 | - |
| CAP-windows-release (`CAP-11`) — Windows PC/lab product hardening, validation, packaging, and release | `NONE` | `PENDING` | 0/6 | 0/19 | - |
| CAP-university-hosting (`CAP-12`) — University-hosted deployment, institutional identity, collaboration, and operations | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-cloud-platform (`CAP-13`) — Managed cloud control plane, tenant data planes, governance, and SaaS operations | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-cross-platform-desktop (`CAP-14`) — Cross-platform desktop qualification and release | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-study-design (`CAP-15`) — Empirical study design and protocol development | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-manuscript-blueprints (`CAP-16`) — Manuscript blueprint, venue profiles, and article architecture | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-results-integration (`CAP-17`) — Technical report and study-results integration | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-manuscript-drafting (`CAP-18`) — Source-grounded manuscript drafting and publication artifacts | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-review-revision (`CAP-19`) — Reviewer simulation, editorial synthesis, and revision | `NONE` | `PENDING` | 0/6 | 0/18 | - |

## Release gates

| Gate | After wave | Unlocks | Status |
|---|---|---|---|
| `G0` — W0 exit / W1 activation — Executable engineering baseline | `W0` | `W1` | `APPROVED` |
| `G1` — W1 exit / W2 activation — Durable Windows local application core | `W1` | `W2` | `PENDING` |
| `G2` — W2 exit / W3 activation — Inspectable Windows local corpus | `W2` | `W3` | `PENDING` |
| `G3` — W3 exit / W4 activation — Windows local evidence workbench | `W3` | `W4` | `PENDING` |
| `G4` — W4 exit / W5 activation — Minimum compelling Windows scholarly-reasoning product | `W4` | `W5` | `PENDING` |
| `G5` — W5 exit / W6 activation — Windows PC/lab version 1.0 | `W5` | `W6` | `PENDING` |
| `G6` — W6 exit / W7 activation — Cross-platform desktop version 1.0 | `W6` | `W7` | `PENDING` |
| `G7` — W7 exit / W8 activation — Study design and manuscript foundation | `W7` | `W8` | `PENDING` |
| `G8` — W8 exit / W9, W10 activation — End-to-end research-production desktop | `W8` | `W9`, `W10` | `PENDING` |
| `G9` — W9 exit / - activation — Advanced research-intelligence preview | `W9` | - | `PENDING` |
| `G10` — W10 exit / W11 activation — University pilot | `W10` | `W11` | `PENDING` |
| `G11` — W11 exit / - activation — Cloud limited availability | `W11` | - | `PENDING` |

## Active work

| Task | Status | Owner | Branch |
|---|---|---|---|
| `CAP-03.S03.T03` Create an audit and lineage inspection workspace | `REVIEW` | codex | `codex/w1-windows-local-runtime` |
