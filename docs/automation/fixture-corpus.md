# Scholarly fixture corpus

The repository's miniature scholarly corpus is a wholly synthetic, repository-authored test asset. It contains no third-party papers, excerpts, figures, or metadata. Its contents are dedicated under `CC0-1.0`; the corpus manifest records the license and provenance both globally and for every file.

The corpus lives at `tests/fixtures/scholarly-corpus/`. It intentionally covers:

- complete, partial, variant, duplicate-identifier, and Unicode metadata in JSON, RIS, and BibTeX;
- structured XML and plain text with sections, a table, citations, and bibliography entries;
- a small valid PDF with internally consistent object and cross-reference offsets; and
- malformed JSON, XML, and PDF inputs with explicit expected failure modes.

`manifest.json` is the machine-readable inventory. `manifest.schema.json` requires offline and deterministic operation, CC0 licensing, synthetic provenance, SHA-256 digests, byte lengths, media types, feature declarations, and accept/reject expectations. Files outside the exact inventory are denied.

Run the validator from the repository root:

```powershell
.venv\Scripts\python.exe tools\fixture_corpus_check.py --repo .
```

The validator uses no network services. It verifies the schema, inventory, hashes, lengths, content structure, malformed-input behavior, and required semantic feature coverage. It is also a mandatory command in the `foundation` verification profile.

When updating the corpus, keep the material synthetic, update the item digest and byte count in `manifest.json`, preserve the declared edge-case coverage, and run the focused foundation tests plus the full foundation profile. Never copy external scholarly content into this corpus.
