# Local project package and storage layout

ADR-0012 makes a local project a relocatable, versioned directory package. The
project root is selected by the researcher; durable code stores only its
location outside the package and resolves governed relative paths beneath that
root. Moving the complete package therefore does not alter project identity or
the bytes recorded in `project.ro.json`.

## Root contract

The plaintext `project.ro.json` manifest contains only project identity,
revision, package/layout versions, lifecycle state, application compatibility,
database/object format identities, and timestamps. It must not contain a
project title, source metadata, research content, filesystem path, credential,
encryption key, provider identifier, endpoint, or raw diagnostic.

The exact machine contract is the combination of
`project-manifest.schema.json` and the bound
`project-manifest.semantic-rules.json` beside it. Draft 2020-12 owns lexical,
shape, format, UTC, and safe-integer constraints; the language-neutral semantic
rules own compatibility-range and timestamp ordering that JSON Schema cannot
compare across fields. The compatibility rule fixes every semantic-version
component to the inclusive JavaScript-safe integer domain
`0..9007199254740991`; all readers apply that exact bound before comparing the
range. A reader that runs only one layer is incomplete. The
canonical layout and its schema live beside them. Core is the project-home
authority; desktop code, workers, and downstream modules consume the contract
and never build paths by string concatenation.

## File classes and lifecycle

| Class | Relative location | Authority | Retention | Backup | Project delete | Portable export |
|---|---|---|---|---|---|---|
| Database | `state/project.sqlite3` | Authoritative | Project lifetime | Required | Recoverable project delete | Include |
| Objects | `objects` | Authoritative | Project lifetime | Required | Recoverable project delete | Include |
| Indexes | `indexes` | Derived | Rebuildable | Excluded | May be rebuilt/deleted | Exclude |
| Caches | `cache` | Cache | Bounded | Excluded | Eviction | Exclude |
| Models | `models` | Derived project working data | Rebuildable | Excluded | May be rebuilt/deleted | Exclude |
| Configuration | `config` | Authoritative | Project lifetime | Required | Recoverable project delete | Include |
| Exports | `exports` | Authoritative researcher output | Project lifetime | Required | Recoverable project delete | Include |
| Logs | `logs` | Operational | Bounded | Excluded | Retention expiry | Exclude |
| Locks | `.locks` | Operational | Lease bound | Excluded | Close or explicit stale recovery | Exclude |
| Temporary | `.tmp` | Transient | Operation scoped | Excluded | Operation cleanup | Exclude |

`models` is reserved for project-private, rebuildable working data until the
model-runtime contract owns a stronger representation. Shared application model
caches remain outside every project package and survive project deletion.

## Portability and recovery rules

- Export includes `project.ro.json`, the database, encrypted objects,
  configuration, and researcher exports.
- Export denies all entries marked `exclude`; a copied cache, lock, log, index,
  model working directory, or temporary file is a contract violation.
- Backup preserves included bytes and their relative paths. Restore may choose a
  different absolute root without rewriting the manifest.
- Delete first moves the whole project to a recoverable quarantine. Secure purge
  is a later explicit action and must accurately describe filesystem/SSD limits.
- Creation is staged under a recognizable temporary sibling and published only
  after the required structure and manifest validate. Interrupted staging never
  masquerades as a usable project.

## Implemented lifecycle boundary

Core now owns create, open, close, archive, restore, and recoverable-delete
transitions through the generated local API. Creation stages a complete sibling
package before publication. Open acquires an exclusive `session.lock` carrying
only process/instance/heartbeat/recovery identity; close removes only a lock
owned by the current supervised Core instance. Archive is reversible. Delete
requires the exact project-specific confirmation and moves the whole closed
package to a sibling `.research-observatory-trash` directory without touching
application-level shared model caches. Project titles remain in the governed
profile under `config`, never in the plaintext root manifest or audit events.

On the release-authoritative Windows path, lifecycle operations hold canonical
project, lock, configuration, and audit directories by stable handles that deny
rename/delete until validation and mutation complete. Device paths and roots
inside Windows installation directories are rejected. Audit JSONL updates use a
bounded atomic replacement and reject redirects or hardlinks; an audit failure
rolls manifest and lock state back before the request reports failure. Project
publication and recoverable-trash movement rename the held directory itself, so
another local process cannot substitute a different validated project by path.

Open classifies the stable manifest envelope before granting access. The
current package format and application range receive an exclusive `read-write`
session. A structurally sound older package (`migration-required`) or newer
package/application range (`newer-unsupported`) receives only an in-process
`read-only` inspection session: Core writes no lock, audit, manifest, profile,
or other package byte. Close therefore only releases that read-only session.
Mutation commands reject the incompatible package and name the exact
backup-first migration or compatible-application recovery action. Malformed
metadata is reported as `RO-CORE-PROJECT-DAMAGED`; missing required entries are
reported as `RO-CORE-PROJECT-INCOMPLETE`. Both fail before any package write and
direct repair to a verified working copy rather than the original.

## Explicit recovery copy

ADR-0054 records the ECR-0014 recovery implementation under W2.A06. Recovery is
available only for newly proof-eligible Windows sessions. Native binds its own
actual process and owned Core child, creation times, executable file identities,
current principal and fresh launch identity through the inherited private pipe.
Public project API bodies cannot supply or replace that authority. A dedicated
nonportable profile store emits immutable current-user-then-machine DPAPI
witnesses and protected issuance receipts before lock publication and after
successful open. The existing project encryption and portable seven-field lock
format are unchanged. Failure to seal proof permits only an ordinarily owned,
nonrecoverable session while its stable private exclusion remains held.

Recovery preview, confirmation, status and cancellation are separate authenticated
commands. Both predecessor Native and Core owners must be proven dead; a live,
reused or uninspectable identity, foreign principal/host, missing or changed
witness, invalid heartbeat or terminal close denies recovery. The ten-second
heartbeat is an exact owned-record refresh and never grants an age-based takeover.
Close, rollback and shutdown remove only the complete current owned record and
file identity; changed or unknown locks remain untouched.

Confirmation copies held original files into a new private staging sibling.
This recovery inventory includes database/WAL, objects, configuration, exports
and operational logs/locks so that the original session evidence is retained;
it does not change the portable export inventory. Complete membership, identities
and bytes are checked before any staged SQLite access. The copied old lock is
archived inside staging. A read-only staging authority then verifies every
canonical table/row/cell and the complete physical object inventory, authenticates
all available encrypted objects with retained keys and rights, and checks source
stability again. Only a verified copy receives its own bounded operational audit
event and a held no-replace directory publication. Failed or cancelled copies are
retained under an operation-owned quarantine name. Original files, old locks,
accepted facts and ciphertexts are never repaired or removed.

A temporary root-level recovery completion marker is flushed before copying
and remains until the final published inventory/identity check completes.
Canonical copy bytes stay held through marker removal. Ordinary layout
validation rejects the marker, including on fresh Core startup after failed
quarantine or interruption; removal failure grants no ready/open authority.
Successful recovery removes it and leaves the existing package format unchanged.

The copy remains closed until the researcher uses normal open, which obtains a
new lock and worker authority. Copy verification alone does not report recovered.
Legacy sessions without original durable proof are denied rather than backfilled.
W2.A06.T01 requires actual whole Native/Core termination and fresh startup,
protected readback and principal/path/fault evidence. W2.A06.T02 adds actual
shipping Native/Core/UI recovery evidence. Secure purge remains a separate explicit
workflow; recoverable trash is not cryptographic erasure.
