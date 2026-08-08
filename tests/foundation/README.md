# Foundation tests

Owner: Research Observatory maintainers
Boundary: Repository structure, generated-state, and automation boundary tests.

These tests stay dependency-light so a fresh checkout can detect structural and
governance failures before application toolchains are bootstrapped.

`test_bootstrap.py` models a clean checkout with controlled command results. It
verifies Windows command selection, the documented generated-file boundary, and
fail-closed behavior without resolving dependencies during the unit test.
