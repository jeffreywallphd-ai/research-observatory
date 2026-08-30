# Local credential-store contract

`credential-store-profile.v1.json` is the portable policy record for the W1
Windows credential boundary. It declares current-user DPAPI protection for a
random profile-vault root, application-authenticated opaque secret records,
cross-process-serialized compare-and-swap replacement, callback-scoped delivery,
and a bounded audit projection that retains calling capability, declared purpose,
operation, outcome, reason, audit context, and an opaque keyed reference. It
deliberately contains no operating-system path, provider SDK type,
credential value, database handle, or implementation-specific error.

Purpose is not free-form. The profile closes it to provider authentication,
connector authentication, signing verification, and object encryption so a
caller cannot place a scope identifier or value into diagnostics by relabeling it
as purpose.

Provider keys, connector tokens, signing trust, and encryption key material are
scoped by profile, kind, subject, and name. Those identifiers are encrypted in
the record and keyed-hashed for physical identity. Secret material is forbidden
from SQLite, project packages and exports, support bundles, and process
arguments. Windows remains an adapter; later platforms must implement the same
portable port with their native user credential service.

`application-lock-profile.v1.json` is the immutable W1 predecessor contract.
Every valid instance migrates to `windows-password` without rewriting the
predecessor bytes and preserves its profile name and zero/nonzero idle timeout.

`application-sign-in-policy.v1.json` is the current application-wide policy.
It permits exactly `none`, `windows-password`, or `windows-hello`, and records
`none` explicitly for a new or previously absent configuration. Protected
transitions are authorized by native provider proof, explicit confirmation,
and compare-and-swap publication; an invalid policy stays fail-locked and can
only be reset after a same-SID native Windows-password recovery proof. The
renderer receives an opaque, one-time transition handle and never provider
credentials, an HWND, or a caller-selected verification outcome.

The shared application-lock boundary remains at the desktop native supervisor.
A manual, idle, or restart lock invalidates the
protected-action generation, stops Core, clears its per-launch capability,
discards renderer research state, and requires a same-SID current Windows user
credential check before a fresh Core session starts. The optional display name
and idle interval are application-local configuration outside project packages.
The contract explicitly does not claim Windows-account isolation, and W1 permits
no durable job to continue through lock without a future explicit allowlist.
