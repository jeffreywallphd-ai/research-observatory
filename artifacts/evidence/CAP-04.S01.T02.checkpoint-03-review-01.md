# CAP-04.S01.T02 — checkpoint-03 adverse review

Candidate: `a6219124afd9165414b4ccefd0e0ff9cb714aa76`.
Independent reviewer: `w2_source_packet_preflight`. Disposition: NOT APPROVED.
This bounded checkpoint review is not the formal task R01 submission.

P1: undo could remove current per-record rights. A fresh unchanged-candidate probe
confirmed revision 1 readable → revision 2 inspection denied → direct removal
rejected → restore revision 1 accepted as revision 3 → raw/historical reads expose
the record again. The direct-decision guard did not cover the restore branch.
Required closure: reject permission-broadening restoration or preserve current
restrictions independently, with the exact denial/undo/read sequence retained.
No other blocking finding in the 12-file delta; candidate was not integrated.

Candidate qualification separately passed 28 focused tests in 3.708 seconds,
Ruff/format/Mypy for seven changed Python files, architecture and inventory (253).
These passes did not cover the missing undo/rights boundary and do not override
the adverse independent disposition. Native/runtime/whole-task proof remains open.
