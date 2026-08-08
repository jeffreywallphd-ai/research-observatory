# UI-reference validation

`tools/ui_reference_check.py` is the mandatory foundation gate for the approved
Academic Minimal experience reference. It reads governed files once, validates
the shared reference ID and approval/version state, and reports the exact
canonical SHA-256 map plus a package digest.

The gate requires exactly 32 product pages, 34 HTML documents, 14 workflow
profiles, 20 capability records, and page-contract parity. Every HTML link and
asset must remain local, present, and inside `design/ui-reference`; network
dependencies and W10/W11 hosted-administration routes are rejected. A temporary
copy runs the deterministic generator and must reproduce all governed hashes.

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
