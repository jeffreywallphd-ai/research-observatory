# CAP-04.S01.T03 groundwork — identity and exact predecessor

Work in progress, not task completion or canonical commit proof.

- Added the pure, one-pass `import-identity/1` serialization and project-local
  source-assertion lookup key. Neither hash is a UUID, Work match or permission.
  The complete existing effective-draft digest remains unchanged and included.
- Initial new test failed because the implementation module did not exist;
  after implementation, 13 focused identity/draft tests passed in 0.008 seconds.
  One test-line formatting finding was corrected; Ruff and product mypy passed.
- Captured literal v12 metadata/summary DDL from unchanged storage at claim base
  `b55c1285b33d17fca7b8ef37ed8ce16d1c83610a`. The fixture retains exact schema
  `42a9886d0b9d132071cebe3170d12b46a048148f9c69dcf624178d4f281840fa`
  and profile `9d6ac8532068f3271c42140525a6c106208f92ca6f8362c36eee4e25b02d863f`.
- First predecessor assertion run completed its assertions but failed temporary
  fixture cleanup: SQLite's transaction context manager does not close its
  connection. Explicit `closing()` fixed the test-owned handle lifetime; the
  unchanged fingerprint/retention/FK test then passed in 0.140 seconds.

These are exploratory working-tree observations. Exact-candidate checks and
independent task disposition remain required. No v13 migration, canonical
commit, worker/API action or final wizard step is claimed by this increment.
