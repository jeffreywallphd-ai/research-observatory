# Static planning review site

Open `index.html` in a browser. Review interface release 1.3.7; canonical planning supplement 1.3.4. The site contains 12 wave/gate pages, 19 capability pages, and 111 individual slice pages. Wave pages show contributing capability increments, ordered slices, and the exact exit/activation gate decision. Descriptive capability and slice aliases are the default presentation; numeric IDs remain immutable evidence and ordering keys. Capability decisions are resolved once, while slice-plan approval is progressive by active wave.

Canonical commands:

```bash
python tools/planctl.py --repo . review CAP-XX
python tools/planctl.py --repo . adopt-recommendations CAP-XX  # already complete for authored packets
python tools/planctl.py --repo . approve CAP-XX --wave WN --by "Reviewer" --commit <git-sha>
# Only when an override or note was exported:
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
python tools/planctl.py --repo . approve CAP-XX --wave WN --feedback <downloaded-json> --by "Reviewer" --commit <git-sha>
```

The Markdown plans remain authoritative. The review site is a generated human review surface and must be regenerated and validated after plan changes.
