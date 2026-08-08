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

The validator uses no network services. It confines the manifest, schema, and every fixture path to non-redirected files inside the corpus; excludes only the two root control files from inventory; and binds filename extensions, media types, declared features, and expected outcomes. Normal scholarly features must belong to accepted fixtures, while malformed feature labels must belong to rejected fixtures, so invalid content cannot satisfy positive corpus coverage. The validator verifies hashes, lengths, JSON/XML/RIS/BibTeX structure, PDF cross-reference counts/states/generations/offsets, per-item scholarly semantics, malformed-input behavior, and required feature coverage. It is also a mandatory command in the `foundation` verification profile.

When updating the corpus, keep the material synthetic, update the item digest and byte count in `manifest.json`, preserve the declared edge-case coverage, and run the focused foundation tests plus the full foundation profile. Never copy external scholarly content into this corpus.
