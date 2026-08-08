# Product versions and build manifests

`packaging/product-version.json` is the only product-version authority. The
versions in `package.json`, `pyproject.toml`, and `[workspace.package]` in
`Cargo.toml` are ecosystem mirrors. Desktop, Core API, and worker
`component-manifest.json` files are generated contracts that must carry the same
version and major/minor compatibility line.

`CHANGELOG.md` keeps an `Unreleased` section and one dated heading for each
released product version. A version change updates the authority, all mirrors,
the three component manifests, and the changelog in one reviewed task.

After updating the authority and ecosystem mirrors, regenerate the component
contracts with:

```powershell
.venv\Scripts\python.exe tools\build_manifest.py --repo . --write-components
```

The command accepts only the canonical component destinations declared by the
repository and writes each contract atomically before validating the complete
build contract.

Generate deterministic build provenance with:

```powershell
.venv\Scripts\python.exe tools\build_manifest.py --repo . --output artifacts\tmp\build-manifest.json
```

The output binds the full Git commit and commit time, all dependency lockfile
hashes, the exact repository schema inventory and identifiers, and the governed
model-manifest set. CAP-07 owns the model-manifest contract and installation
workflow; until that capability installs the contract, build inputs must declare
an empty model-manifest set, which still receives a stable SHA-256 set identifier.
Arbitrary files cannot be substituted as model manifests. Desktop and both
sidecars are embedded with compatible versions.

Clean builds use `<version>+g<commit7>`. Any tracked or untracked source change
produces `<version>+g<commit7>.dirty` and records the affected repository-relative
paths. No wall-clock time is used, so the same repository state produces identical
JSON and manifest identifiers. Clean generation verifies captured governed bytes
against `HEAD`, while every generation checks that Git and captured file state
remain stable through collection. Output is permitted only under a canonical,
nonredirected `artifacts/tmp/`;
normal validation never edits tracked files. Only the explicit
`--write-components` operation changes tracked component contracts; it never
edits version sources, changelogs, or packaging inputs.
