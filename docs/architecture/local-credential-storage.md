# Windows local credential storage

ADR-0017 governs the first production local credential adapter. Its portable
machine policy is
[`credential-store-profile.v1.json`](../../packages/contracts/security/credential-store-profile.v1.json).
The implementation is a Windows adapter behind the dependency-neutral
`CredentialStore` port; no consumer receives its filesystem root or a DPAPI
handle.

## Protection hierarchy

```text
Windows current-user DPAPI
  -> random profile-vault root key
      -> provider-key records
      -> connector-token records
      -> signing-trust records
      -> object-encryption key records
      -> later database/export/recovery namespaces
```

Core calls `CryptProtectData` and `CryptUnprotectData` with a null prompt and
`CRYPTPROTECT_UI_FORBIDDEN`. It never selects machine scope: Microsoft documents
that `CRYPTPROTECT_LOCAL_MACHINE` permits any user on the computer to decrypt the
blob. Returned plaintext is cleared before `LocalFree`. The application validates
an exact root envelope because Microsoft also warns callers not to rely on one
DPAPI error code or DPAPI alone to classify every possible corrupted blob.

The root protects authenticated XChaCha20-Poly1305 records. A record's profile,
kind, subject, name, and CAS version exist only inside ciphertext. Its filename
is a keyed HMAC and its associated data binds the requested scope. A held
cross-process vault lock serializes root creation and record CAS. Missing,
changed, or unauthenticated state is unavailable without deleting the protected
bytes, so a researcher can restore a known-good backup or recovery artifact.

## Access and disclosure boundary

Every request declares the calling capability, purpose, and audit context. The
audit projection contains only the operation/outcome, a bounded reason, and an
opaque keyed reference token. A failing audit authority denies access before
plaintext is returned. A successful lease exposes a read-only view of one
mutable buffer and zeroes that buffer when the lease closes.

Secret values and plaintext record identifiers are forbidden from SQLite,
project packages, project exports, support bundles, environment variables,
process arguments, configuration projections, and diagnostic messages. The
vault lives under the Windows LocalAppData known-folder authority, outside every
project home. Support bundles already carry the exact
`credentials-and-tokens` and `environment-variables` exclusions.

The object-store provider is the first consumer. Normal Core composition binds
its stable key-provider port to `encryption-key-material/object-store/object-key-v1`.
First use creates the 256-bit key; later process starts retrieve the same value.
An explicitly injected `None` remains available to deterministic recovery tests
and produces the existing key-unavailable state without rewriting project data.

## Recovery and residual threat

There is no machine-scope fallback, online account, or automatic escrow. Until
the later CAP-02.S04 recovery task creates an explicit passphrase-protected
artifact, loss of the Windows logon protection material makes the vault
unrecoverable. A same-user malicious process can request DPAPI decryption, so
Windows sign-in protection, full-disk encryption, endpoint controls, and the
later application-lock coordinator remain necessary. Secure deletion is
cryptographic erasure plus best-effort ciphertext cleanup, never a promise about
flash remanence or external backups.

Official platform constraints:

- [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
- [CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata)
- [LocalFree](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-localfree)
