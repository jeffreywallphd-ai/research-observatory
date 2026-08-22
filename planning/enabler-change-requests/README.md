# Enabler change requests

ECR packets are inert append-only proposals for bounded changes discovered
during an approved Wave. Version 1 remains the immutable historical W1.A02
format. New requests use `enabler-change-request.v2.schema.json`, freeze the
complete ordered predecessor authority chain, and propose exactly the next
amendment and ordered task identities. Requests following a released recovery
hold use `enabler-change-request.v3.schema.json`; v3 additionally freezes the
sole active successor hold and its exact independently approved bootstrap.

Independent packet review and exact-commit human approval precede bootstrap
submission. `taskctl amendment bootstrap-submit` appends a later amendment; it
must never replace, reorder, duplicate, fork, or silently migrate a predecessor.
Ordinary Wave work remains held through bootstrap, task, exit-review, adoption,
and the control/security checkpoint.
