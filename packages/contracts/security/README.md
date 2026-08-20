# Local credential-store contract

`credential-store-profile.v1.json` is the portable policy record for the W1
Windows credential boundary. It declares current-user DPAPI protection for a
random profile-vault root, application-authenticated opaque secret records,
cross-process-serialized compare-and-swap replacement, callback-scoped delivery,
and a bounded audit projection that retains calling capability, declared purpose,
operation, outcome, reason, audit context, and an opaque keyed reference. It
deliberately contains no operating-system path, provider SDK type,
credential value, database handle, or implementation-specific error.

Provider keys, connector tokens, signing trust, and encryption key material are
scoped by profile, kind, subject, and name. Those identifiers are encrypted in
the record and keyed-hashed for physical identity. Secret material is forbidden
from SQLite, project packages and exports, support bundles, and process
arguments. Windows remains an adapter; later platforms must implement the same
portable port with their native user credential service.
