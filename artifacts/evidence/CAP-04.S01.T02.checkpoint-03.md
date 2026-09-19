# CAP-04.S01.T02 — immutable preview decisions checkpoint

Parent: `e85ba0990851af11884efff16fcc798dd13dc555`.
This is bounded implementation progress, not task completion or a human gate.

The existing v11 tables now support compare-and-swap draft revisions, immutable
mapping-profile identities, bounded group decisions and history-preserving undo.
Accepted corrections/exclusions/rights survive remapping; newly conflicting
suggestions are explicit and excluded. Record membership and the exact profile
are checked before a group transaction publishes. Reports cover all records in
bounded pages with mapping/exclusion codes and no bibliographic content or paths.
Current global/per-record inspect rights constrain historical and raw reads.
No new schema version or canonical import is introduced.

Eight focused tests were added, initially reproducing the missing draft command
and methods. Implementation testing exposed and fixed a method/instance-field
name collision. Static typing exposed a reused fixture lifecycle annotation;
tests now compose its existing unittest lifecycle rather than duplicating or
re-running inherited test methods. These exploratory failures are not passes.

Selected candidate checks: draft and existing preview repository tests, unchanged
pure mapping/digest tests because the new adapter consumes them, affected lint/
format/type checks, packaging metadata, architecture and quality inventory.
The migration bytes are unchanged; their checkpoint-02 evidence remains historical
and is not represented as a fresh run. Broad W1 and packaged/native tests are not
selected for this persistence-only increment.

Next scope: runtime durable parse activity and trusted project authorization,
native file intake, byte-bounded API/client projections, duplicate candidates and
desktop wizard, followed by focused real-boundary acceptance. The new internal
draft page is not a native API response and does not relax the 1 MiB bridge cap.
No native, authentication, performance-at-100k or whole-task qualification claim.
