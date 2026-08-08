# Foundation tests

Owner: Research Observatory maintainers
Boundary: Repository structure, generated-state, and automation boundary tests.

These tests stay dependency-light so a fresh checkout can detect structural and
governance failures before application toolchains are bootstrapped.

`test_bootstrap.py` models a clean checkout with controlled command results. It
verifies Windows command selection, the documented generated-file boundary, and
fail-closed behavior without resolving dependencies during the unit test.

`test_backlog_views.py` verifies source-derived totals and statuses, idempotent
no-rewrite generation, generated-file drift detection, and repair of manual edits.

`test_fixture_corpus_check.py` verifies the synthetic scholarly corpus contract,
including licensing and provenance, exact inventory, content hashes, semantic edge
cases, malformed-input behavior, and valid PDF cross-reference integrity.

`test_benchmark_registry.py` runs the golden parser and contract benchmark end to
end and verifies deterministic reports, hash tampering, baseline immutability,
version/history/approval requirements, distinct human approval, and path confinement.

`test_build_manifest.py` verifies single-source version compatibility, deterministic
clean and dirty build identities, dependency/schema/model-set provenance, manifest
inventory drift, and output confinement.
