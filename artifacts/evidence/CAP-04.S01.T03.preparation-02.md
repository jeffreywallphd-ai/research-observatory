# CAP-04.S01.T03 — adapter ownership registration

At exact candidate `8f104eda74ce0f5357487e537f01fc12eb0bcc3e`, nine fresh
commit-workflow/preparation/packaging-contract tests passed in 7.654 seconds,
and mypy passed both product modules. Architecture correctly rejected the new
unregistered concrete adapter; the candidate was not integrated.

Register only `import_commit_repository` beside the existing preview/draft/summary
Core adapters. This does not allow business modules or ports to use concrete
storage, and a same-named file outside the Core adapter location is still denied.
The new ownership/leakage regression failed before registration, then all eight
architecture-control tests passed in 0.233 seconds and repository architecture
passed. This is the necessary inventory update for the planned adapter, not a
new security authority or general check suppression. Qualifying checks and
independent review must bind the successor candidate.
