---
id: ADR-0017
title: Use a user-scoped Windows DPAPI profile vault for local secrets
status: Accepted
date: 2026-08-20
deciders:
  - W1 repository-owner pre-Wave approval at c5bbd97c0cdc665eecb973f5862478ef7be97752
linked_tasks:
  - CAP-02.S04.T01
decision_scope: Windows local profile-vault hierarchy, OS protection scope, secret-record authentication and identity, in-process delivery, audit projection, and recovery-key policy boundary.
affected_paths:
  - packages/contracts/security/**
  - packages/contracts/README.md
  - packaging/build-inputs.json
  - services/core-api/src/research_observatory_core/ports/credential_store.py
  - services/core-api/src/research_observatory_core/windows_credentials.py
  - services/core-api/src/research_observatory_core/main.py
  - services/core-api/packaging/sidecar-build.json
  - tests/contracts/test_credential_store_contract.py
  - tests/security/test_windows_credentials.py
  - tests/data/test_object_envelope_upgrades.py
  - tests/packaging/test_core_sidecar_package.py
  - tests/foundation/test_build_manifest.py
  - quality-scope.json
  - docs/architecture/local-credential-storage.md
  - docs/architecture/local-object-storage.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0017: Use a user-scoped Windows DPAPI profile vault for local secrets

## Context

W1 must supply production key material to the encrypted object-store coordinator
and later provider/connectors without putting credentials in SQLite, project
packages, exports, diagnostics, environment variables, or process arguments.
The approved CAP-02 packet selects an OS credential store, a random profile vault
root, distinct subordinate key namespaces, explicit recovery, and account-
optional offline operation. Windows x64 is the release authority through W5.

DPAPI is available to packaged Win32 desktop applications without a new runtime
dependency. Current Microsoft guidance says current-user protected blobs are
normally recoverable only by the same logon user on the same computer, while
machine-scoped blobs are decryptable by any local user. It also requires
`LocalFree` for returned buffers, recommends clearing sensitive plaintext, and
warns applications not to depend on one DPAPI error code for tamper detection.
The prompt-based flow is deprecated; Core is a non-interactive sidecar.

## Candidates

1. Use plaintext or application-obfuscated configuration files. This fails the
   approved threat boundary and makes support/export exclusion unreliable.
2. Store every secret directly in Windows Credential Locker. This is attractive
   for interactive UWP scenarios but couples the Core adapter to a credential
   naming and payload surface that is awkward for opaque versioned binary keys.
3. Protect one random profile-vault root with current-user DPAPI, then store
   separately authenticated, opaque, versioned secret records below that root.
   This keeps the OS boundary small, supports binary material and CAS rotation,
   and leaves a replaceable portable credential-store port.
4. Use machine-scoped DPAPI. This improves service-style access but permits any
   local user on the workstation to decrypt the vault and is rejected.

## Decision

Adopt candidate 3 for W1 Windows. `CryptProtectData` and
`CryptUnprotectData` run with a null prompt and
`CRYPTPROTECT_UI_FORBIDDEN`, without `CRYPTPROTECT_LOCAL_MACHINE`. The protected
root plaintext has an exact versioned magic, fixed length, and SHA-256 integrity
commitment. DPAPI-returned plaintext is copied into a mutable buffer, cleared,
and released with `LocalFree`.

Each secret reference is scoped by profile, kind, subject, and name. HMAC-SHA-256
under the root derives its physical name so none of those identifiers appears in
the path. The encrypted record repeats the exact scope and random CAS version
inside XChaCha20-Poly1305 authenticated ciphertext with scope-bound associated
data. A held cross-process vault lock serializes root creation and record CAS.
New records are create-only; replacement requires the observed version.
Corrupt or unavailable protection fails with a bounded recoverable classification
and retains ciphertext.

Access requires a calling capability, declared purpose, and audit context. Audit
records retain those bounded capability and purpose values plus operation,
outcome, bounded reason, audit context, and an opaque keyed reference token. They
never retain plaintext scope identifiers or values. Material is delivered through
a short-lived mutable lease and cleared on close. The existing object-key port necessarily copies one
32-byte key into its cryptographic operation; it does not expose vault paths or
general credential DTOs.

No automatic cloud escrow or silent machine-scope fallback exists. Loss of the
Windows account protection material and every explicit recovery artifact is
honestly unrecoverable. The optional passphrase-protected recovery/export key,
rotation, and cryptographic erasure workflow remain required later in CAP-02.S04;
T01 neither invents nor silently persists one. The profile/object namespace is
separate from later database and portable-export key namespaces.

## Consequences

The normal Windows Core composition can now create and recover its object master
key without a system Python or external service. Encrypted records can be backed
up as ciphertext, but moving them without an explicit recovery artifact does not
make them decryptable on a different account or machine. Same-user malware and a
fully compromised interactive session remain outside this control; OS sign-in,
full-disk encryption, endpoint protection, and later application lock remain
important layers.

The adapter is Windows-specific while the port and machine profile are portable.
macOS and Linux qualification must supply native credential-service adapters, not
emulate DPAPI or broaden machine access. Rollback is safe before secrets are used;
after encrypted project objects depend on the stored key, uninstalling the
adapter without recovery support makes those objects unavailable and may never
delete or rewrite them as corrupt.

## Verification

- real current-user DPAPI create/restart/read on release-authoritative Windows;
- exact portable profile schema and weaker-scope mutation rejection;
- authenticated record/root tamper, missing authority, CAS conflict, audit
  failure, redirected authority, and ciphertext-retention checks;
- provider/object encryption restart and default legacy-envelope upgrade;
- recursive scans proving secret bytes and plaintext identifiers are absent from
  SQLite, project/export content, support bundles, logs, and arguments;
- frozen-sidecar archive, security-local, architecture/ADR, and supply-chain
  qualification.

## Task links

- `CAP-02.S04.T01`
