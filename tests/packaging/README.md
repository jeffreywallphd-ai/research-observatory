# Packaging tests

Owner: Research Observatory maintainers
Boundary: Install, upgrade, repair, rollback, and removal qualification.

Generated installers and signed artifacts belong in controlled build outputs,
not in version control.

The Core API sidecar test performs a real PyInstaller `onedir` build under the
ignored artifact scratch area, validates the exact portable manifest, runs the
frozen executable with all Python locations removed from `PATH`, and proves
that a missing runtime dependency is detected. Full signed-installer clean-VM
qualification remains a `CAP-01.S05` release responsibility.
