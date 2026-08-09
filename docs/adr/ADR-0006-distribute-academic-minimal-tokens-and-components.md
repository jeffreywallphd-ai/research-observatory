---
id: ADR-0006
title: Distribute Academic Minimal tokens and components through governed local packages
status: Accepted
date: 2026-08-09
deciders:
  - CAP-01 repository-owner-approved capability and slice plans
  - CAP-01.S02.T01 independent review
linked_tasks:
  - CAP-01.S02.T01
decision_scope: Design-token transport, reusable React primitive boundary, component catalog, contrast and scaling qualification, and downstream package compatibility.
affected_paths:
  - packages/ui-tokens/**
  - packages/ui-components/**
  - apps/desktop/package.json
  - apps/desktop/tsconfig.json
  - apps/desktop/src/app/designSystem.test.tsx
  - tools/desktop_app_check.py
  - tests/desktop/test_desktop_app_check.py
supersedes: []
superseded_by: null
---

# ADR-0006: Distribute Academic Minimal tokens and components through governed local packages

## Context

CAP-01.S02 must turn the approved Academic Minimal reference into reusable,
versioned UI contracts without copying an alternate palette, taking durable
application authority, adding remote build infrastructure, or weakening the
desktop conformance gates. The first component set needs typed React APIs,
semantic light/dark states, WCAG 2.2 AA contrast, 100-200% scaling evidence, a
local catalog, and a low-cost downstream migration path. The source reference
and its human approval remain the visual authority.

## Candidates

1. Copy token values into a generated package and adopt a third-party hosted or
   dependency-heavy Storybook catalog. This is familiar, but creates a second
   byte authority, expands the supply chain, and makes offline qualification
   depend on another application stack.
2. Export a local CSS transport that imports the exact governed reference,
   expose stable TypeScript identities and React primitives, and qualify a
   repository-native static catalog through the already pinned Playwright and
   desktop verification stack. This preserves one token authority and adds no
   external package.
3. Keep page-level CSS and components inside the desktop application. This
   avoids package work but prevents downstream slices and later platforms from
   consuming a versioned design-system boundary.

## Decision

Adopt candidate 2. `@research-observatory/ui-tokens` is a private versioned
workspace package whose CSS entry imports only the approved token source and
whose JSON contract pins the reference identity and canonical source hash.
`@research-observatory/ui-components` exports typed, tree-shakeable React
primitives and token-only styles. Its local `catalog.html`, React server-render
tests, static contract checks, contrast calculations, and pinned Chromium runs
form the component-story and accessibility surface.

The initial contract covers typography, icon, button/form, table, dialog,
notification, badge, panel, semantic tone, evidence state, and uncertainty
identity. Focus trapping/restoration, global shortcuts, and live-region
scheduling remain T02 work. Boundary/recovery compositions remain T03 work.

## Consequences

There is one approved visual value source and no new network or package runtime.
Components can be adopted incrementally by the shell and later workspaces while
remaining independent of filesystem, service, credential, and scholarly state.
The local catalog is intentionally smaller than Storybook, so controls such as
knob generation and external addons must be added only when they provide tested
value without changing the approved supply-chain boundary. A visual semantic
change requires a newer approved reference; compatible API additions use normal
semantic versioning. Rollback removes the two workspace links and package files.

## Verification

- `pnpm --dir apps/desktop lint`
- `pnpm --dir apps/desktop typecheck`
- `pnpm --dir apps/desktop test`
- `python -m unittest tests.desktop.test_desktop_app_check`
- `python tools/desktop_app_check.py --repo .`
- `python tools/ui_change_gate.py --base <task-base> --head <implementation>`
- `python tools/verify.py --profile desktop`

## Task links

- `CAP-01.S02.T01`

