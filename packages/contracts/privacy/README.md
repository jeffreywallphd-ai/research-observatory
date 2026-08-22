# Project privacy policy contract

`privacy-policy.schema.json` defines the portable W1 project privacy profile and
`privacy-policy.v1.json` is its canonical current instance.

The contract fixes offline and telemetry-off defaults, informed consent before a
non-offline preference is recorded, and a separate per-task preview requirement.
Changing a preference never sends data. Metadata-only denies document/object
content, while approved-provider content remains `require-confirmation` at the
object-store boundary.

Retention review intervals do not automatically delete documents. Cache cleanup
is project-cache-only, exact-preview-bound logical removal. It expressly cannot
guarantee physical erasure because media remapping, journals, snapshots, backups,
and hard links can retain copies. The contract exposes no project path, content,
provider credential, or filesystem capability.
