# Synthetic native parser fixtures

These repository-authored fixtures are test data, not scholarly publications,
sources, citations, methods or results. Their reference strings and identifiers
are deliberately synthetic and must never be promoted to research evidence.
No external document text or participant data is included.

Gold expectations live in `tests/parsing/test_native_parsing.py` and precede
the implementation. The fixtures exercise JATS, TEI, generic XML and inert HTML
structure, source positions, mixed text, unknown elements and explicit source
references. Namespace variants, hostile content and Unicode boundary cases are
constructed by the tests from these declared synthetic inputs.
