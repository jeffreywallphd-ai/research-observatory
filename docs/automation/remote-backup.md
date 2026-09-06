# Committed-work backup and prospective privacy

The owner accepts account/path metadata already present in the original history
through commit `dd8803c0526edfaca53d3a5b25faf4bb0cdf8854`. This supersedes the
earlier private-original/public-derivative restriction for this explicit backup.
It does not authorize credentials, ignored local output, uncommitted files,
or new account/path disclosures. It is not a Wave or release approval.

The active local branch publishes to the separate remote branch
`codex/w1-windows-local-runtime-original`. Existing sanitized branches remain
unchanged. Repository-local `push.default=upstream` supports the deliberately
different local and remote names. Use plain `git push`, not `--all`, `--mirror`,
or a force push. No historical source, approval, or evidence is rewritten.

The installed, pinned local pre-commit, commit-message and pre-push checks run
`tools/prospective_privacy.py` using an explicit privacy policy and pinned
Gitleaks executable/default-rule configuration. Commit checks read the staged
index, not unstaged working files. Push checks inspect every reachable commit
outside the frozen baseline, including side parents and merge results. New
paths and modified files are inspected in full, even if their blob existed in
old history. Commit metadata is checked as well. Existing unchanged inherited
content is not repeatedly rejected.

The gate blocks concrete profile/workspace paths, non-public email addresses,
raw machine reports, private local output, unsupported modes and unreviewed
binary content. Standard fictional example domains and public GitHub noreply
identities remain usable. Credential matches require review; they are never
automatically dismissed merely because a value resembles a hash or test token.
Editing a legacy file may require removing its embedded local paths first.

The protected untracked witness must not be read, staged, or backed up. Filename
inventory checks precede content reads. `.local` and scratch exclusions stay in
`.gitignore`; ignore rules do not remove existing history. New raw reports should
be written in ignored locations, with publishable evidence using relative or
symbolic roots.

Local hook installation pins the checker, policy, and scanner configuration in
ignored local state. Updating them requires a deliberate reviewed reinstall;
ordinary repository edits cannot quietly change the installed policy. Hooks
are developer accident-prevention, not a security boundary against the machine
owner: Git permits explicit bypass and other clones need the same installation.
Detection cannot guarantee the absence of all sensitive information.

The backup contains committed Git objects only. It does not contain ignored
environments, databases, credentials, work-in-progress edits or local toolchains.
Restore by cloning the original-history branch; do not merge the sanitized
publication branches merely to resolve their intentionally different history.

## Reinstalling on a recovered development machine

Run the repository Python environment's interpreter with
`tools/install_privacy_hooks.py --repo . --scanner <verified-gitleaks-executable>`.
The executable must match the policy's SHA-256. Preparation prints a new
`hooksPath` and does not change Git configuration. After checking that output,
set repository-local `core.hooksPath` to it. Also set `push.default` to `upstream`
and the active runtime branch's upstream to the original-history backup branch.
Use `git push --dry-run` to check routing and hooks before uploading.
Do not disable hooks to get around a blocked finding; correct the content or
independently review an exact false positive and deliberately reinstall controls.
