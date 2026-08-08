# Static planning review site

Open `index.html` in a browser. Review interface release 1.3.5; canonical planning supplement 1.3.4. The site contains 19 capability pages and 111 individual slice pages. Every researched best-in-class recommendation is already selected and treated as a completed planning decision. The site lets a reviewer confirm the defaults, record a reasoned documented override, choose Other with a brief description plus detailed rationale, add notes, and export a JSON feedback record before the single explicit capability approval.

Canonical commands:

```bash
python tools/planctl.py --repo . review CAP-XX
python tools/planctl.py --repo . adopt-recommendations CAP-XX  # already complete for authored packets
python tools/planctl.py --repo . approve CAP-XX --by "Reviewer" --commit <git-sha>
# Only when an override or note was exported:
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
python tools/planctl.py --repo . approve CAP-XX --feedback <downloaded-json> --by "Reviewer" --commit <git-sha>
```

The Markdown plans remain authoritative. The review site is a generated human review surface and must be regenerated and validated after plan changes.
