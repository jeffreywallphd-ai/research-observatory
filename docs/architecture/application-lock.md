# Windows local application lock

ADR-0018 makes the Tauri native supervisor the W1 application-lock authority.
The portable policy and configuration shape are
[`application-lock-profile.v1.json`](../../packages/contracts/security/application-lock-profile.v1.json)
and its strict schema. The document is stored under the desktop application's
LocalAppData authority, never in a project, export, renderer store, or Core
database.

## Lock sequence

```text
manual, idle, or restart trigger
  -> native state becomes locked and protection generation advances
  -> pending support previews are cleared and staged publications lose authority
  -> renderer receives the lock event and discards project/command/dialog state
  -> a listener-first sequence check plus native-status polling closes missed/stale event gaps
  -> malformed or unavailable reconciliation fails to the locked-only tree
  -> protected native requests and late responses are denied
  -> supervised Core request cancellation is signaled and the process tree terminates immediately
  -> per-launch Core capability is zeroed on drop
  -> locked screen is the only rendered application content
```

W1 has no durable workflow authorized to continue through this boundary, so the
native supervisor stops every Core operation. A later checkpointed worker may
continue only after an explicit compatible policy and allowlist are approved and
tested. UI labels or operation names never grant continuation.

## Verification providers

The lock manager owns a provider-neutral verification seam. Every provider is
admitted through the same one-attempt reservation, backoff, lock-generation,
Core-start, stale-result, and Core-stop boundary. Provider availability and
verification results are closed typed contracts; the renderer cannot submit a
provider result or turn an adverse result into success.

The Windows-password provider opens a generic, always-shown, non-persisting
Windows credential prompt prefilled from the current
`NameSamCompatible` identity. Parsed local/down-level names retain their domain;
UPNs pass a null domain to `LogonUserW` as required by Windows. The returned token
SID must match the desktop process token SID. Password, username, and domain
buffers are cleared, and all token handles are closed.

The Windows Hello adapter checks `UserConsentVerifier` availability and uses
`IUserConsentVerifierInterop::RequestVerificationForWindowAsync` with the native
desktop window handle. Windows owns the PIN/face/fingerprint prompt and returns
only an availability or verification enum; Research Observatory receives no PIN
or biometric material. Not-present, not-configured, policy-disabled, busy,
cancelled, retry-exhausted/denied, unsupported, and failed paths never call the
password provider and never unlock. A separate argument-free native password
recovery command retains the same-SID proof and must be invoked deliberately; it
is not a Hello fallback. T02 supplies this adapter and recovery boundary. T03
owns persisted provider selection and transition authorization, and T04 owns the
approved user-facing selection and recovery experience.

## Unlock sequence

Unlock reserves one native attempt before invoking the natively selected
provider. Concurrent attempts, cancellation, a different Windows account,
invalid credentials, provider unavailability, API failure, and Core restart
failure leave the application locked. Denied attempts receive bounded
exponential backoff without revealing whether an account or project exists.

Successful reauthentication starts a fresh supervised Core process with a new
capability. It does not reopen a project or restore discarded renderer input.
Local Windows accounts work; no Research Observatory or cloud account is
required.

## Residual threat and recovery

This is application-session protection within the current Windows account, not
a second Windows-account isolation boundary. Same-user malware, a compromised
desktop process, a compromised signed-in session, screen capture, and data
already copied outside the application remain outside the control. Windows
sign-in protection, full-disk encryption, endpoint controls, and physical
security remain necessary.

The optional profile name is hidden while locked. A corrupt profile fails locked
and may be replaced only after successful same-user reauthentication. With idle
lock disabled, manual lock remains available but application restart does not
start locked; enabling an idle interval makes restart lock mandatory.
