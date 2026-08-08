# Repository bootstrap notes

## Installation record

- Date: 2026-08-08
- Package: Research Observatory AI Repository Setup Pack 1.3.5
- Package ZIP SHA-256: `559c65ad17ccb27a3ffeac7faa623d9b143a686a485ce1a2c00a05bd4d15cd63`
- Package integrity: all 504 entries listed in `SHA256SUMS.txt` verified
- Target baseline: `a19040a` on `main`
- Bootstrap branch: `codex/bootstrap-research-observatory-automation`
- Installer result: 495 files created, 0 identical, 0 conflicts, 0 blocked

The external setup kit remains outside the repository. Repository operation begins with root `AGENTS.md`.

## Windows validation adjustment

The packaged interaction smoke test hardcoded `/usr/bin/chromium`, which cannot run on the Windows-authoritative setup platform. `design/ui-reference/scripts/smoke_interactions.py` now launches the Chromium build managed by Playwright. The governed UI-reference hashes were regenerated with:

```text
python tools/ui_reference_check.py --reference design/ui-reference --write-hashes
```

Python Playwright 1.62.0 and its compatible Chromium runtime were installed in the current user's development environment. This is an environment prerequisite, not a repository authority or a completed CAP-00 toolchain decision.

## Verification outcome

`artifacts/bootstrap/setup-verification.json` records a passing external setup verification with no errors or warnings. The validated surfaces include:

- backlog, capability-plan, and slice-plan schemas;
- generated planning-review pages and decision controls;
- approved UI-reference integrity;
- UI HTML and browser interaction smoke tests; and
- planning-review JavaScript syntax.

## Planning handoff

- The authoritative next capability is `CAP-00`, Delivery foundation and Codex execution system.
- `CAP-01` has a decision-complete capability packet and five complete slice plans.
- CAP-01 implementation remains correctly blocked until its CAP-00 dependencies are complete and a human approves the CAP-01 packet and slice plans at an immutable commit.
- CAP-01 review page: `planning/review-site/CAP-01/index.html`.

## Pending external administration

The following repository-host settings require GitHub administration and remain pending:

- protect `main` and require pull-request review;
- configure required checks after CAP-00 installs the CI workflows;
- install and approve `CODEOWNERS` policy;
- enable secret scanning, dependency review, and code scanning where available; and
- configure protected signing infrastructure before Windows release qualification.

These items do not weaken the local bootstrap verification. They remain required before the corresponding CI, supply-chain, and release gates can pass.
