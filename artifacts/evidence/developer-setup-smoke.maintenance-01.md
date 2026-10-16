# Developer setup smoke maintenance

This bounded, owner-requested setup correction starts from commit
`3541a4b0e842727c0b54af1e4043af2989845134`. An observed fork invocation reached
Foundation unit discovery while ordinary setup selected all 16 Foundation checks;
nested captured output hid its progress. The running fork was inspected only.

`tools/bootstrap.py` retains the four frozen dependency steps and exact runtime
validation, then checks Python dependencies/native SQLCipher, the desktop Vite
executable, and existing locked packaging/workspace metadata. Every step inherits
stdout/stderr, reports elapsed time and status, and fails closed. Development
configuration is still published only after all steps pass. The full Foundation
profile and its assertions/settings are unchanged and remain an explicit
`tools/verify.py --profile foundation` invocation.

Two pre-change regressions reproduced the overly broad selection and delayed
output. Focused format/lint/type checks and all ten bootstrap/Windows entrypoint
tests passed after correction. A real child handshake proves progress arrives
before child completion; a real exit-23 child preserves stdout/stderr and failure
status. Existing install/last-smoke failure tests retain atomic configuration
publication coverage. The Python dependency/SQLCipher in-memory smoke also ran
with the existing read-only test interpreter.

Raw commands, UTC start/end, statuses, and adverse preparation results are kept
in ignored `artifacts/tmp/setup-fast-smoke-01/`. No dependency installation, full
Foundation run, Rust compilation, product/project/model launch, or user-process
termination was performed. The isolated checkout intentionally has no installed
Node workspace, so the real Vite and Cargo smoke invocations were not run here;
frozen install/smoke wiring and fail-closed behavior are tested using controlled
runners. Concurrent existing machine workloads are disclosed in the local record;
no timing guarantee is inferred. Independent commit-bound review precedes
integration.
