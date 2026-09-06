# Committed-work backup and prospective privacy

The owner accepts account/path metadata already present in the original history
through commit `dd8803c0526edfaca53d3a5b25faf4bb0cdf8854`. This supersedes the
earlier private-original/public-derivative restriction for this explicit backup.
It does not authorize credentials, ignored local output, uncommitted files,
or new account/path disclosures. It is not a Wave or release approval.

Local `main` pushes to remote `main`; local `codex/...` branches push to the same
remote branch names. Repository-local `push.default=simple` restores ordinary
`git push`. No renamed backup branches or duplicate working histories are used.
The owner reversed the earlier sanitized-publication-only arrangement. The
already published sanitized tips are preserved in verified local recovery
copies before a one-time exact-lease reconciliation with original branch tips.
Routine future pushes are normal fast-forwards, not force or mirror pushes.
Original local source, approval and evidence history is not rewritten. The three
previously deleted recovery branches are not republished automatically.

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
Restore by cloning the corresponding ordinary branch. Keep the retained
sanitized-history recovery copies separate; do not casually merge them back.

## Reinstalling on a recovered development machine

Run the repository Python environment's interpreter with
`tools/install_privacy_hooks.py --repo . --scanner <verified-gitleaks-executable>`.
The executable must match the policy's SHA-256. Preparation prints a new
`hooksPath` and does not change Git configuration. After checking that output,
set repository-local `core.hooksPath` to it. Also set `push.default` to `simple`
and each supported local branch's upstream to the same remote branch name.
Use `git push --dry-run` to check routing and hooks before uploading.
Do not disable hooks to get around a blocked finding; correct the content or
independently review an exact false positive and deliberately reinstall controls.

## Reviewed synthetic artifacts

New screenshots and scanner false positives remain blocked until an independent
reviewer approves their exact content. The optional registry uses document type
`independent-artifact-privacy-review`; it binds the existing baseline, pinned
scanner/configuration, independent reviewer, rationale, and each artifact's
case-sensitive relative path, regular-file mode, raw Git-blob SHA-256 and length.
Binary review requires inspecting the decoded content and metadata. Credential
false positives bind the complete redacted finding fingerprints; unknown or
changed findings and scanner errors remain denied. Exact relative icon filename
tokens misidentified as email addresses can be adjudicated only for that blob.
There is no global hash, file-extension, email/domain or scanner-rule exemption.

Keep the independently authored registry and raw review diagnostics in ignored
local state. Prepare with `--review <local-review-file> --review-sha256
<independently-supplied-digest>` in addition to the normal installer arguments.
Review the resulting snapshot before activating it. The installer copies and
pins those exact reviewed bytes; editing either the live registry or repository
source does not update installed admissions. Preserve previous snapshots and
review receipts. A new or changed image needs a new explicit review and reinstall.

Admissions never waive protected/private output names, real profile/workspace
paths, raw reports, size/mode restrictions, filenames, refs, author/committer
identity or commit messages. Every admitted artifact still receives the pinned
credential scan. This is privacy admission only, not visual, task or release
approval, and never changes the approved historical baseline or push routing.
