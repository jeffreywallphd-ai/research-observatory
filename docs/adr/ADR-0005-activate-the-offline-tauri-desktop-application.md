---
id: ADR-0005
title: Activate the offline Tauri desktop application
status: Accepted
date: 2026-08-09
deciders:
  - CAP-01 repository-owner-approved plan and CAP-01.S01.T01 independent review
linked_tasks:
  - CAP-01.S01.T01
decision_scope: Desktop host and renderer boundary, initial routing and project-session ownership, zero-privilege Tauri activation, and approved-reference application conformance.
affected_paths:
  - apps/desktop/**
  - Cargo.toml
  - Cargo.lock
  - package.json
  - pnpm-lock.yaml
  - verification/extensions/desktop-ui.json
  - verification/desktop-ui.schema.json
  - verification-profiles.json
  - quality-scope.json
  - tools/desktop_app_check.py
  - tools/ui_conformance.py
  - tools/ui_change_gate.py
  - tests/desktop/**
supersedes: []
superseded_by: null
---

# ADR-0005: Activate the offline Tauri desktop application

## Context

CAP-01 must turn the approved desktop reference into a runnable application
without weakening the design-first controls qualified by CAP-00. The application
must not open a development listener in production, grant renderer code ambient
filesystem/process/credential access, duplicate Core business logic in views, or
claim conformance from the temporary reference fixture. The initial shell also
needs deterministic routing, explicit project-session states, pinned toolchains,
and a build that can be reproduced and reviewed from exact inputs.

## Candidates

1. Ship an Electron or browser-hosted frontend. This offers a familiar JavaScript
   environment but introduces a larger host surface or a production listener and
   conflicts with the approved Tauri plan.
2. Copy the static reference into an application directory and verify selected
   pages. This is quick, but copied sources can drift and fixture checks can pass
   without proving the built product.
3. Use Tauri 2 as the sole native host, bundle a strict React/TypeScript runtime,
   generate the webview target from the exact approved reference, bind every build
   input/output digest, and run all conformance checks against that generated target.

## Decision

Adopt candidate 3. `apps/desktop` owns renderer composition, route resolution, and
the project-session state machine. Tauri owns the native window. The first
capability grants the main window no privileged commands, does not install the
global Tauri bridge, has no `devUrl`, and uses a restrictive offline CSP. Future
filesystem, process, keychain, service, or storage behavior requires narrow typed
Tauri commands or versioned Core API contracts and a later reviewed decision.

The build creates `apps/desktop/dist` from the exact approved reference, injects a
bundled React hydration runtime without changing the approved semantic or visual
contract, and writes a deterministic application manifest over the complete source
and output inventories. The desktop profile builds first and then targets that real
application for token, route, workflow, accessibility, responsive, and visual checks.
The fixture-to-application gate transition is allowed only for the exact protected
activation set, with the activation commit strictly preceding every governed UI
implementation commit.

## Consequences

The initial product remains offline, least-privilege, deterministic, and visually
identical to the approved Academic Minimal reference. The webview assets are larger
than the static fixture because React is bundled, and native builds require the
pinned Rust/MSVC/WebView2 environment. Later interactive slices may replace static
reference data with typed application state, but they must preserve the approved
contract or obtain a newer human-approved reference.

Rollback is a revert of the Tauri/app activation before dependent CAP-01 work ships.
After dependent slices exist, reversal requires a superseding ADR and migration plan.

## Verification

- `python tools/verify.py --profile desktop`
- Pinned pnpm lint, strict typecheck, unit tests, and deterministic build.
- Locked Cargo format, Clippy, unit, and build checks.
- Application-manifest missing/stale/inventory-boundary regressions.
- UI fixture escape and protected activation ordering regressions.
- Independent Windows launch and no-listener smoke evidence.

## Task links

- `CAP-01.S01.T01`
