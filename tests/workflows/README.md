# Workflow tests

Owner: Workflow maintainers. Boundary: portable workflow authority, the local
durable queue, lease fencing, activity supervision, cancellation, retry,
checkpoint, restart, and accepted-output semantics.

These tests use the real canonical SQLite adapter at the principal boundary.
They do not stand in for the complete W1 Wave-exit profile.
