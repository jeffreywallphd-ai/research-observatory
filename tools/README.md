# Repository automation tools

- `planctl.py` - prepare, review, apply feedback, approve, validate, and gate capability plans.
- `taskctl.py` - select, claim, track, and evidence capability/slice/task execution.
- `capability_plan_check.py` and `slice_plan_check.py` - validate canonical plans.
- `plan_review_site.py` and `plan_review_check.py` - generate and validate the static review site.
- `ui_reference_check.py` - validate the approved experience reference.
- `repository_structure_check.py` - validate declared module boundaries and reject deferred implementation or committed binaries.
- `runtime_check.py` - validate exact runtime/package-manager pins and report actionable mismatches.
- `bootstrap.py` - verify prerequisites, perform frozen installs, generate local development configuration, and run the foundation smoke gate.
- `verify.py` - run the bootstrap `foundation` profile; CAP-00.S03 expands it into the complete profile runner.

Run these from the repository root after the setup kit has installed `repo-seed/`. The external setup package is not the repository.
