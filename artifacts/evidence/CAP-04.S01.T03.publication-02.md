# CAP-04.S01.T03 — publication review remediation and activity wiring

Retains publication-01 CHANGES REQUESTED and its two reproduced findings.
Both regression tests failed before remediation (2 failures, 2.752s).

F01: a bounded manifest-access pass now checks historical and current effective
store/inspect permissions for every member under the final writer transaction.
It also checks current preview state, draft and parse identity. The same access
boundary applies to explicit comparison, scientific reuse and response replay.
Historical approval is not current permission; no rights facts are rewritten.

F02: replay revalidates the actual current draft against staged decisions and
authenticates a sealed manifest with exactly the expected scientific identity.
Generic queue completion still authenticates the immutable attempt/output, but
cannot substitute a parser receipt for a manifest. Valid cross-request reuse
does not require the original manifest attempt to equal the new job attempt.

Added a portable commit port and guarded activity using the established import
action guard. Preparation is paged with heartbeat/cancellation checks; publication
returns the reviewed atomic-completion marker. Tests cover actual publication,
cancellation before publication, nonadvancing-page failure and heartbeat.
No service/API/UI action is exposed yet. These tests use development storage,
not real-principal/native or large-import performance qualification.

Exploratory checks: the two remediated findings, valid replay, cross-request reuse
and strict packaging contract passed (5 tests, 4.903s). Activity initial tests
passed (3, 2.746s); heartbeat passed separately. An initial packaging inventory
check rejected unsorted new module names; reordered them, preserving its strict
assertion. Initial activity lint found a captured loop variable and nested test
contexts; switched to the existing partial-call pattern and combined contexts.
Fresh committed-candidate results follow separately; no task completion claim.
