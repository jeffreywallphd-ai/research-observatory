# Sanitized public copy

This GitHub repository is a privacy-sanitized publication of Research
Observatory. The original local history is retained privately as the canonical
W1 execution and evidence record. Do not merge or push that original history
into this repository.

Historical author names and software source are retained. Identified private
email addresses are replaced with explicit `example.invalid` redaction aliases.
Identified local profile and checkout roots use generic `redacted-user` and
`workspace` paths. These are presentation placeholders, not observed locations.

The rewrite changes Git identities. Historical approval records, signatures,
hash references and generated review pages are documentary derivatives here;
they do not authorize execution or release against the rewritten commits.
Original signatures are not represented as valid signatures of this copy.
Governance-dependent validation may be unavailable in this derivative. The
original private repository retains its unchanged validators and approvals.
A passing publication privacy check is never W1 qualification or release approval.

## Publication safety

- Keep raw machine reports, local runtime data and recovery copies in ignored
  local locations. `.gitignore` does not sanitize tracked content or history.
- Install the versioned privacy hooks with
  `git config --local core.hooksPath .githooks` in this public copy. Hooks are
  local safeguards and can be bypassed deliberately; CI checks remain separate.
- Pin the independently reviewed publication policy digest with
  `git config --local publication.approvedPolicySha256 POLICY_DIGEST`.
  Obtain that digest from the maintainer's reviewed publication record, not an
  unreviewed policy change. The initial digest is `10f8cd52cb61c1464f3e5e335672439ae75b1fcc817c807f9cc59e7b34cfa62b`.
  Index/pushed policy bytes must match the pin. Policy changes and new exceptions
  need independent review and a deliberately updated pin; they cannot approve
  themselves merely by being committed alongside the newly allowed content.
- Use an approved GitHub noreply identity for your own commits. The
  `example.invalid` aliases in historical records are redaction markers, not
  actual GitHub accounts or a change in contributor attribution.
- Run `python tools/publication_privacy.py --staged` before committing and
  `python tools/publication_privacy.py --ref HEAD` before publication. The
  checker reads Git objects, not untracked local documents or credential stores.
- Review any new binary asset for visible personal metadata before adding its
  exact blob ID to the publication policy. Synthetic fixtures and intentionally
  public third-party contact addresses require narrow documented exceptions.
- Future original-history changes must pass the same isolated transformation,
  equivalence review and full published-history scan. Transfer reviewed source
  changes into the public lineage; never merge old private ancestry back in.

Repository branches can be rewritten, but GitHub caches, old Actions artifacts,
forks and downloaded clones are separate copies. This notice is not a claim
that every external copy has been erased. Contact the maintainer before using
historical governance artifacts as evidence of a release.

## Existing CI and historical views

The **Publication privacy (not W1 qualification)** workflow checks this public
copy's privacy boundaries. It does not qualify the application or approve W1.

The retained **Continuous integration** workflow also checks original governance
records. Its September 5, 2026 run reported stale backlog views because their
documentary `source_sha256` fields still identify the original private backlog;
the rest of each generated view matched its sanitized source. Those historical
hashes have deliberately not been rebound to imply transferred authority.
The same run retained pre-existing expired/stale security-exception failures.
These failures remain visible; checks and original approvals have not been
weakened or relabeled as passing.

The new publication Python files are registered with the ordinary quality
inventory and have explicit Python 3.13 formatter targets, matching their
standalone CI runtime. Ordinary formatting, lint, type and privacy checks still
apply to them. Continue governed W1 execution in the private original, not by
regenerating or approving historical public records here.
