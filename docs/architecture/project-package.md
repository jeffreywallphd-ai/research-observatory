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

The lifecycle and lock implementations arrive in the next tasks; this document
defines the stable layout and their required extension points without claiming
those behaviors already exist.
