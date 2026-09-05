# Static planning review site

Open `index.html` in a browser. Review interface release 1.4.0; canonical planning supplement 1.3.4. The site contains 12 Wave packet/gate pages, 19 capability pages, 111 individual slice pages, 337 individual task pages, 8 hash-bound enabler change request pages, and 2 governance recovery pages plus their registers. A Wave page is the pre-execution approval surface: it aggregates every contributing capability decision, ordered slice plan, review cadence, exit-gate decision, and any interrupting append-only amendment or recovery hold. Its nested capability, slice, and task cards are generated from the authoritative backlog. Descriptive aliases are the default presentation; numeric IDs remain immutable evidence and ordering keys. Task pages display an optional task-start worksheet only when `artifacts/evidence/<TASK-ID>.task-start.md` exists; worksheet absence is non-blocking.

Canonical commands:

```bash
python tools/planctl.py --repo . wave review WN
python tools/planctl.py --repo . adopt-recommendations CAP-XX  # already complete for authored packets
python tools/planctl.py --repo . wave approve WN --by "Reviewer" --commit <git-sha>
# Only when an override or note was exported:
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
python tools/planctl.py --repo . wave approve WN --by "Reviewer" --commit <git-sha>
```

The Markdown plans remain authoritative. The review site is a generated human review surface and must be regenerated and validated after plan changes.
