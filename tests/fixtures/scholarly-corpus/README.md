# Synthetic scholarly fixture corpus

This miniature corpus exercises ingestion and parsing boundaries without using
third-party scholarly content. All titles, people, identifiers, venues, prose,
tables, citations, and document bytes were created specifically as test fixtures
for this repository. They are intentionally fictional and must never be cited as
research evidence.

## Redistribution and provenance

Repository contributors dedicate the fixture corpus files listed by
`manifest.json` to the public domain under **CC0 1.0 Universal** (`CC0-1.0`).
The canonical terms are <https://creativecommons.org/publicdomain/zero/1.0/>.
The repository software remains governed by the root license; this corpus notice
applies only to the listed synthetic fixture files.

Every manifest item records its SHA-256 digest, media type, synthetic provenance,
license, expected acceptance/rejection outcome, and covered edge cases. The
manifest deliberately includes malformed files, so do not “repair” them in place.

## Coverage

- complete, duplicate, Unicode, and missing-field JSON metadata;
- RIS and BibTeX metadata variants;
- structured XML full text with sections, a table, and bibliography links;
- a small valid PDF generated from original synthetic text;
- deliberately invalid JSON/XML and a truncated PDF;
- deterministic local validation with no network or external service dependency.

Validate from the repository root:

```bash
python tools/fixture_corpus_check.py --repo .
```
