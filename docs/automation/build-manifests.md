# Product versions and build manifests

`packaging/product-version.json` is the only product-version authority. The
versions in `package.json`, `pyproject.toml`, and `[workspace.package]` in
`Cargo.toml` are ecosystem mirrors. Desktop, Core API, and worker
`component-manifest.json` files are generated contracts that must carry the same
version and major/minor compatibility line.

`CHANGELOG.md` starts with its title, keeps one `Unreleased` section, and lists
unique semantic versions newest-to-oldest using exact
`## [version] - YYYY-MM-DD` headings with real calendar dates. The first dated
release is the current product version. Versions use the SemVer 2.0 core and
prerelease grammar without leading-zero numeric identifiers, empty identifiers,
or build metadata. A version change updates the authority, all mirrors, the three
component manifests, and the changelog in one reviewed task. Other change
categories use level-three headings beneath these canonical level-two headings;
ATX variants and setext level-two headings are rejected.

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
The reserved `packaging/model-manifests/` tree must also remain absent or empty;
arbitrary or prematurely installed files cannot be substituted as model
manifests. Desktop and both sidecars are embedded with compatible versions.

Clean builds use `<version>+g<commit7>`. Any tracked or untracked source change
produces `<version>+g<commit7>.dirty` and records the affected repository-relative
paths. No wall-clock time is used, so the same repository state produces identical
JSON and manifest identifiers. Clean generation verifies captured governed bytes
against `HEAD`, while every generation checks that Git and captured file state
remain stable through collection. On Windows, governed input handles deny writes
and deletes during final confirmation, and canonical ancestor-directory handles
deny rename/delete swaps through atomic output replacement. The final stability
cycles also re-enumerate schemas and the reserved model tree, and any unreadable
schema directory fails closed. Temporary JSON is write-locked and byte-verified
through replacement. Output is permitted
only under a canonical, nonredirected `artifacts/tmp/`;
normal validation never edits tracked files. Only the explicit
`--write-components` operation changes tracked component contracts; it never
edits version sources, changelogs, or packaging inputs.
