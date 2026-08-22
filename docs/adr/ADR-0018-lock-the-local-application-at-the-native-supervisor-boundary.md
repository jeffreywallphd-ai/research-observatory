---
id: ADR-0018
title: Lock the local application at the native supervisor boundary
status: Accepted
date: 2026-08-21
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
linked_tasks:
  - CAP-02.S04.T02
decision_scope: Windows local profile identity, inactivity and manual application-lock state, protected-action cancellation, same-user reauthentication, Core capability clearing, audit projection, and residual threat disclosure.
affected_paths:
  - apps/desktop/src/**
  - apps/desktop/src-tauri/**
  - packages/contracts/security/**
  - packages/contracts/README.md
  - packaging/build-inputs.json
  - docs/architecture/application-lock.md
  - docs/architecture/README.md
  - docs/planning-implementation-plan.md
  - planning/backlog.yaml
  - planning/status-summary.md
  - tests/contracts/test_credential_store_contract.py
  - tests/security/test_windows_credentials.py
  - tests/security/README.md
  - artifacts/evidence/ui-change/CAP-02.S04.T02.json
supersedes: []
superseded_by: null
---

# ADR-0018: Lock the local application at the native supervisor boundary

## Context

The approved W1 CAP-02.S04 packet requires an optional local profile name,
manual and inactivity lock, project lock state, protected reauthentication, and
removal of sensitive content without requiring an online account. ADR-0017
places the local secret boundary under the current Windows user and explicitly
leaves application lock as a necessary additional layer. The desktop native
supervisor already owns the per-launch Core capability, the Core process tree,
and the only renderer-to-Core request bridge.

The lock must be more than a visual overlay. A renderer-only flag would leave
Core, its capability, active requests, and decrypted key material available. A
second application passphrase would create another password lifecycle and put
transient password strings in the renderer. Suspending only the window would
also leave protected work active without an explicit policy.

## Candidates

1. Hide the renderer while leaving Core and the native request bridge active.
   This is cosmetic and does not satisfy the security boundary.
2. Add an application passphrase and verifier. This is portable, but creates a
   new recovery and secret-entry surface before one is required and handles the
   passphrase in renderer memory.
3. Make the native supervisor the lock authority. On lock, invalidate the
   protected-action generation, stop the contained Core process, zero its
   per-launch capability on drop, and discard sensitive renderer state. Unlock
   requires the current Windows account credentials through the non-persisting
   Windows credential UI and succeeds only when the returned logon token SID is
   the same as the running desktop process token SID.
4. Use Windows Hello exclusively. This gives strong user presence but is not
   available on every W1 Windows machine and would make an optional local
   profile depend on enrolled hardware or policy.

## Decision

Adopt candidate 3 for W1. The native host owns one strict local profile document
outside project homes. The profile name is optional and is not shown while
locked. Idle lock is opt-in with bounded supported intervals; a native monitor,
not a renderer timer, enforces the deadline. Manual, idle, and restart lock all
advance a protection generation before stopping Core. Every protected native
command checks that generation before and after work so a response completed
during a concurrent lock is discarded.

The current W1 operation seam has no durable worker allowed to continue through
lock, so stopping Core cancels every protected action. Later durable workflow
work may add an explicit checkpointed allowlist only through a compatible ADR
and tests; it must never infer permission from operation type or UI state.

Unlock invokes `CredUIPromptForCredentialsW` with an always-shown,
non-persisting credential prompt. `LogonUserW` validates the submitted local or
domain Windows credentials, and the returned token SID must equal the current
process token SID. Username, domain, and password buffers are cleared; handles
are closed; failure messages do not reveal whether an account or project
exists. Failed attempts receive bounded exponential backoff. Cancellation does
not unlock or restart Core.

This control does not create Windows-account isolation. A process already
running as the same Windows user, a compromised desktop process, or a
compromised signed-in session remains outside the application-lock boundary.
Windows sign-in protection, full-disk encryption, and endpoint controls remain
required.

## Consequences

Lock clears the active Core capability and in-process Core material by process
termination, removes the open-project projection and command input from the
renderer, and blocks Core restart, API, and support-export commands until
reauthentication. Unlock starts a fresh supervised Core session and does not
silently reopen a project.

The W1 credential prompt accepts account passwords; a Windows Hello-only user
may need the account password. A later compatible adapter may use a verified
Windows Hello user-presence API, but may not weaken same-user verification.
Profile corruption fails locked and remains recoverable after successful
same-user reauthentication and explicit profile reconfiguration.

Rollback is safe while no lock profile is enabled. Once enabled, removing this
implementation would remove a user-selected protection layer and therefore
requires an explicit migration that disables the profile only after an unlocked
user decision.

## Verification

- strict portable profile/configuration fixtures and unknown-field denial;
- native state-machine tests for manual, idle, restart, failed, cancelled, and
  rate-limited transitions;
- protected-command generation checks before and after concurrent lock;
- Windows compilation against Credential UI, token, SID, and handle APIs;
- desktop tests proving locked markup excludes project names, paths, command
  input, and workspaces and retains keyboard/focus/screen-reader semantics;
- approved-reference UI lineage plus desktop and security-local qualification.

## Task links

- `CAP-02.S04.T02`
