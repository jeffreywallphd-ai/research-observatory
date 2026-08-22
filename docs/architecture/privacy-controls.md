# W1 local project privacy controls

ADR-0019 places project privacy policy in canonical local Core state. The
portable defaults and enforcement vocabulary are defined by
[`privacy-policy.v1.json`](../../packages/contracts/privacy/privacy-policy.v1.json)
and its strict schema.

## Policy and egress sequence

```text
open compatible project session
  -> Core projects deterministic offline / telemetry-off defaults
  -> researcher reviews will-send / will-not-send boundary
  -> non-offline preference requires exact versioned acknowledgement
  -> complete settings revision commits append-only with content-free provenance
  -> offline and metadata-only deny object content
  -> approved-provider content returns require-confirmation, never allow
  -> future provider task must still preview its exact payload and obtain consent
```

The settings screen and update call do not transmit data. W1 implements no
provider adapter or remote telemetry pipeline. Local diagnostics are operational
and content-safe; they remain distinct from scholarly provenance.

Document review intervals do not delete documents. The log-retention setting is
for classified operational project diagnostics and excludes the append-only
project lifecycle audit and scholarly provenance. T03 records this policy but
does not invent a destructive maintenance executor for classes that do not yet
exist.

## Cache cleanup sequence

```text
inventory project cache without following redirects
  -> return bounded counts/bytes, disclosure, opaque token, and expiry
  -> require exact project/token confirmation
  -> verify policy revision and inventory are unchanged
  -> atomically rename active cache to project-local staging
  -> create fresh cache and append content-free provenance
  -> roll back before failure when the commit cannot complete
  -> remove staging without following redirects, or report cleanup pending
```

Only rebuildable project cache is in scope. Logical removal does not establish
physical erasure: SSD remapping, journals, snapshots, backups, and hard links
can retain copies. Canonical database state, documents, objects, configuration,
logs, exports, models, and shared caches are excluded.
