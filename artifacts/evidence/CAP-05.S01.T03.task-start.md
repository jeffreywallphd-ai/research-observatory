# CAP-05.S01.T03 — acquisition queue, recovery and local access needs

Actual ordinary taskctl claim base: `01bc453237a081392544929364696bac3422e9fb`.
Owner: `codex-w2-implementation`. CAP-05.S01.T02 is DONE and independently
approved. Authority: immutable W2 approval, S01 §9.3 and append-only §22,
ADR-0019/0025/0027/0028/0029, and approved Academic Minimal 1.9 §1.5.
The exact EX01 owner/reference decisions and independent publication-prerequisite
review precede this claim. They authorize neither task completion nor release.

| Material boundary | Implementation and planned proof |
|---|---|
| Durable local/remote intake | Reuse the product workflow queue with distinct run/job/attempt/operation identities. Admit exact selected source/work/version, actor, accepted Intent, privacy, current native session and copy permission. Publish inspected candidate, intake outcome, provenance/dependencies/outbox and queue output atomically. A candidate is not a canonical attachment or reader availability. Test pre-transfer queue visibility, success, rollback and restart. |
| Bounded dispatch and continuation | Preserve T02's one-use exact-copy confirmation, HTTPS/DNS/TLS/redirect limits and sole three-attempt HTTP budget. Queue attempts do not multiply that budget. Generic Task Center Retry and reopening never dispatch acquisition; an interrupted transfer needs a fresh review/confirmation and new attempt identity. Test stale/duplicate/substituted commands, cancellation, security lock, current-rights denial and no implicit egress. |
| Owned partial cleanup | Discard only the intake's owned encrypted partial. Fault a real staging deletion; failed cleanup must override retry, remain visible and block unsafe dispatch. Preserve metadata, prior attempts and adverse outcome. Test no concatenation, no extra HTTP call after cleanup failure and recovery without deleting unrelated entries. |
| Retained candidate recovery | Fresh native-session and current exact association/rights/Intent/privacy review recovers an already inspected candidate without network. Append a new recovery operation/basis; never rewrite its original session, source or download receipt. Commit rechecks that fresh basis, rejects cancellation/changed authority and retains explicit attachment confirmation. Test restart, alternate actor/selection, policy change and late results. |
| Copies and local access annotations | Preserve distinguishable immutable source/license/version observations even for identical stored bytes. Missing full text leaves useful metadata. Unknown, unavailable, denied and entitlement-required remain distinct. Manual/institutional access-need records are local annotations, never permission, verified availability or external requests. Test separate identities, storage deduplication, no canonical availability and no transport calls. |
| Exact predecessor | Captured two literal v24 fixtures before storage edits at the claim base: the inherited v23→v24 baseline and populated v24 with distinct identical-byte acquisitions, one attached and one retained candidate, plus a failed attempt. Preserve original fixtures/history/ciphertext and failed producer setup evidence. Test additive v25 migration, all eight material interruptions, verified backup, repeat/restart and retained row hashes. Synthetic database fixtures are explicitly labeled; production persistence remains protected. |
| Native/Core/desktop journey | Fixed native-only routes and opaque identities; no renderer URL, path, secret, grant or file bytes. Review does not fetch; Download and Attach are separate explicit actions. Existing Ingestion/Task Center return preserves exact selected copy/work/version. Test real protected persistence, owned HTTPS plus signed LPAC inspection, current-session/lock/close races, safe errors, keyboard/focus/announcements and both themes. |
| Evidence and reference admission | Activate only the approved 1.9 product assemblers inside this claim. Keep framework source/shared selectors unchanged. Separately named EX01 authority-lineage, presentation-mapping, desktop-conformance and capture-authority proofs bind paused predecessor→actual claim preparation and actual claim base→final candidate. Preserve every unaffected substantive assertion and all original adverse outcomes; blocked public commands receive no inferred PASS. |

First tests: durable acquisition visibility and candidate outcome; interrupted
transfer with denied owned cleanup; fresh-session retained-candidate recovery;
local access annotation without egress or availability. Add characterization
coverage for existing encrypted staging and explicit attachment semantics.

Selected task coverage: affected documents/service/storage/workflow/contracts,
native bridge and desktop interaction tests, format/type/architecture checks,
and focused real-principal and approved-reference proofs. Full unaffected
profiles remain deferred to slice/checkpoint/W2 qualification. Every qualifying
run uses a fixed committed candidate and closed selected inputs. Expanded
independent review is required for the migration, security and cross-process
boundaries; slice integration remains a separate obligation.

No supplemental refactoring, new parser/provider, institutional login, purchase,
external request, automation-framework source change or generic verification
waiver is planned. No new mandatory authority gate was found at task start.

The independent advisory identified cleanup dominance, atomic queue publication,
Core generic-Retry denial, fresh recovery authority, populated predecessor proof
and the difference between local annotations and permission. Its follow-up found
constructor reconciliation could remove an active encrypted stage. Added a
failing adapter-creation regression; root-shared ownership spans unlocked upload
and inspection. Production adapters use non-destructive construction; abandoned
reconciliation stays at the existing exclusive project-open/upgrade boundary.
Metadata-only recovery creates no read grant. Native-session/current-actor
composition and separate explicit Attach remain required integration assertions.

The next bounded advisory identified reversed native lock acquisition, a lost
ownership fence during connection setup, collapsed acquisition error states and
stale copy context on source change/recovery. Added actual socket zero-dispatch
and cleanup-during-cancellation regressions before their fixes; the adverse runs
remain in ignored development evidence. Native review consumption now follows
the existing application-lock then attachment-state order. A real concurrent
native completion/cancellation proof remains required; a source assertion alone
cannot close that row. Error codes remain safe and distinct across Core/native/UI.
Project-open reconciliation excludes active root-owned intake; ordinary adapters
remain non-destructive. The transport deadline covers the existing bounded
network and inspection phases without expanding either phase's authority.

Development regressions now exercise the real native application/attachment
mutexes with a concurrent pending download and cancellation, and the actual
owned socket rejects every request byte after authorization revocation. They
are bounded native unit/transport proof, not a new native-window journey claim.
The mounted product journey covers copy review focus/Escape, separate explicit
Download/Attach, local annotations, Task Center return and retained recovery;
its opaque native replies are labeled synthetic. Separately, owned HTTPS,
SQLCipher, encrypted object storage and signed LPAC inspection exercise current
Core session admission, queue success and fresh-session recovery without a
second download. Failed development setups and stale-label findings remain.

Download and validation append distinct durable phase events with unknown
quantitative progress. Exact native status and Task Center project those facts,
never canonical availability. Status reconciliation uses the existing queue's
expired-lease recovery for these max-attempts-one activities only. A controlled
fixture advances time past the recorded lease and checks abandonment, unchanged
origin/confirmation, no fabricated transfer result and zero HTTP until a new
explicit confirmation. Cleanup failure is discoverable for the exact source
after reopening; it remains immutable, and safe new intake stays blocked while
the actual encrypted staging boundary requires cleanup.

Production resource admission shares the existing local controller and project
document lane. A real controller/SQLite fixture proves capacity denial admits
no job, sends no HTTP and leaves confirmation unconsumed; terminal release
permits the next bounded intake. Task Center return carries only safe exact IDs.
Final committed-candidate checks, EX01 conformance/capture proof and expanded
independent disposition remain required; these development results do not
complete CAP-05.S01.T03, its slice or W2.

Independent product assessment at `89da746a972d1faa6bd64739d8f9c86c6be21908`
found three missed journey cases (PRODUCT-R01-F01/F02/F03). The immediate causes
were a remote flag on the local begin path, a retained projection without its
origin copy ID, and reuse of the local-attachment denial gate for local notes and
alternative-copy review. Before remediation, add a delayed remote-result mounted
regression for exact phase polling and in-flight Task Center return; a same-name
retained-copy regression for distinct visible identities and exact return context;
and a prior per-copy rights-failure regression for annotation without egress and
fresh alternative-copy review. Local-file attachment stays denied, and actual
download/Attach still recheck current authority. These are corrections of the
approved 1.9 journey, not new scope or verification-framework work.

The first committed-candidate check exposed a missed architecture row: concrete
intake/recovery SQL helpers were placed outside the established document data
adapter. The existing architecture guard rejects those dependencies and calls.
Preserve that failed check and relocate the exact helpers into the existing
`document_attachment_repository.py` adapter; keep transactions, authority, IDs,
SQL and recovery semantics unchanged. The guard is the characterization failure;
replay it plus affected queue/recovery and integration checks. No verifier,
architecture policy, migration, public contract or framework change is required.
