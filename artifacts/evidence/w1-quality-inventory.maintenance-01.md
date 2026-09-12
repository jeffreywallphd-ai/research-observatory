# W1 quality-inventory correction

Bounded control maintenance; no product, acceptance, reference or gate change.

Predecessor: `f731c96159d5ee214c21412922df7e5c6198e6cf`.
`quality-scope.json` predecessor SHA-256:
`468ac29172d21fc4f8e9bc3ee3599761623e0262fb7f5d5ff26bc347a2ef8dc7`.

Fresh full qualification attempt 03 stopped at `foundation:quality`: the existing
`tests/desktop/test_application_lock_recovery.py` was absent from the explicit
Python quality inventory. Its predecessor SHA-256 is
`432377f1c9f03233dc2479fdf0b5af0116058dc4621eb19a0b69ed43189a70f9`.
The retained attempt report is `artifacts/tmp/W1.full-qualification-03.json`,
SHA-256 `806a72e6cd41dedee51eab6d3030bdc6675795aa5c0412a231a12a49124e6f90`.
The owned process tree drained; no timeout or passing Wave result is claimed.

Correction: add that test to the inventory. Keep the governed roots, unlisted-file
rejection, formatter, linter, type checker and existing test assertions unchanged.
If the newly admitted file exposes type/format defects, correct only those
annotations/formatting and retain the diagnostic result.

Verification: existing `tests.foundation.test_quality_check` covers actual scope
closure and rejection of omissions; run it and the full governed quality command
at the committed candidate. The failed Wave invocation supplies the regression
characterization. Independent control review precedes local integration. Resume
fresh full Wave qualification afterward, retaining attempt 03. This bookkeeping
repair is not structural refactoring, a new product task or W1 acceptance.

The inventory addition exposed two `attr-defined` diagnostics for the test's
shared HTML document. Development attempt 01 retained both failures at
`artifacts/tmp/W1.quality-inventory-01.json` (SHA-256
`2eba9b7e0611327402945d0465d3afb32a11a3d5c03cb9931462d9e9b58f0c8d`).
Declare the existing shared value as `ClassVar[str]`; no test behavior or
assertions change. Include the four recovery regressions in candidate checks.
