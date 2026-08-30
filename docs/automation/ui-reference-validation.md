# UI-reference validation

`tools/ui_reference_check.py` is the mandatory foundation gate for the approved
Academic Minimal experience reference. It reads governed files once, validates
the shared reference ID and approval/version state, and reports the exact
canonical SHA-256 map plus a package digest.

The reference is a design and verification authority, not deployable application
content. Its HTML pages, illustrative values, mock records, future-capability
navigation, and nonfunctional actions must never be configured as a production or
development frontend. Applications may consume approved semantic tokens and
implement only the page regions and workflows owned by completed capabilities.

The gate requires the product-page and HTML-document counts declared by the site
manifest to match the unique governed inventory exactly. It also requires 14
workflow profiles, 20 capability records, and page-contract parity. This keeps
the inventory deterministic without encoding a stale page total in the checker.
Every HTML link and asset must remain local, present, and inside
`design/ui-reference`; network dependencies and W10/W11 hosted-administration
routes are rejected. A temporary copy runs the deterministic generator and must
reproduce all governed hashes.

Run the check directly with:

```powershell
.venv\Scripts\python.exe tools\ui_reference_check.py --repo . `
  --reference design/ui-reference `
  --report artifacts/tmp/ui-reference.json
```

`--write-hashes` refuses an approved reference. A proposed experience revision
must follow the design-first workflow, receive a new approval, and only then be
used as an implementation baseline. Reports are confined to canonical
`artifacts/tmp` and contain no absolute checkout path, so repeated runs are
byte-deterministic.

Application change ordering and exact task/PR lineage are enforced separately
by `tools/ui_change_gate.py`; see `design-first-ui-changes.md`.
