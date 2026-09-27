# CAP-04.S02 independent integrated slice review 01

Reviewer: `agent:/root/w2_t03_review`, independent of the campaign owner.
Date: 2026-09-27.
Disposition: **approved for CAP-04.S02 slice completion and the corresponding
taskctl campaign transition**. No criterion-bound blocking finding remains.
This is not Wave exit, release, live-provider, minimum-hardware or full-profile
approval. Taskctl must separately record the slice disposition; this note does
not mutate planning state.

Reviewed matrix delivery: `c53e45037bb712e6b46eb8b1f7d4ccfd002a3918`.
Fresh performance candidate: `c01247db9badded2d098ad86a17c9e454f00d5fa`.
Latest product/correction candidate: `b17bc9d868e4e9ee672dbac7b765514403949b9d`.
Authority is the complete W2 packet at
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, approved CAP-04.S02 sections 8
and 10–17, accepted ADR-0027 and the applicable inherited security, persistence
and experience decisions. Presentation reference 1.7 and inherited semantic
workflow catalog 1.5 remain distinct. The slice plan's substantive approved
content is unchanged; later plan metadata records its existing approval.

## Authenticated matrix and candidate continuity

| Committed matrix artifact | SHA-256 |
|---|---|
| `artifacts/evidence/CAP-04.S02.qualification-01.md` | `45777ed101da837d0b332811ba1b5dc1aae91f1da3136f766a871b5aa68fe9f6` |
| `artifacts/evidence/CAP-04.S02.qualification-01.json` | `39f145b51544dae71fb90540ebac421ddef0b19d8924d635347c7b2c786594be` |

Both files match their exact delivery Git blobs. All 19 index bindings were
independently authenticated using their declared mode: tracked artifacts against
Git bytes at the named commit and local execution artifacts against raw bytes.
The three ordinary task ledgers and linked correction ledger remain approved,
and the actual backlog records all four tasks DONE/approved. Their candidate
and manifest bindings agree with the consolidated index:

| Task | Actual reviewed candidate |
|---|---|
| CAP-04.S02.T01 | `e5c57e9784d7f06957d9e5e850a916002110d87f` |
| CAP-04.S02.T02 | `16b1524278b9e9ad9e52c322aa4b0fba0bb6fef0` |
| CAP-04.S02.T03 | `1e68cab433f194bf5d834bedc974bdac5a4f7cb6` |
| W2.C02.T01 | `b17bc9d868e4e9ee672dbac7b765514403949b9d` |

Product trees under `apps/`, `services/` and `packages/` are unchanged from the
reviewed correction through this delivery. After the performance candidate,
only the two consolidated matrix files changed. The reviewer composes the prior
expanded independent task/control/visual reviews with their original candidate
and principal limits; no old execution is relabeled fresh or reused as a new
whole-profile pass. No additional broad suite or provider call was run during
this review. Shared HEAD stayed fixed; this note is the reviewer's only edit.

Initial matrix delivery `c53461502fafdfcc65ebbad0d0a15ea0ad4a2c44` bound the
physical T03 manifest checkout hash
`76870f5358458073b7fe720673515a28fc7fda73cf9ad0ff4c1897b6e004932c`.
The reviewer reproduced its CRLF conversion and verified canonical LF equality
with the historical Git hash
`e7455ced5e7d7495dbb0b28c8b77bf7da3522ef65d946c982e834fa2b1edd88c`.
The corrected explicit hash modes and `publicationCorrection` retain both facts.
This pre-review publication observation is closed for the index; no original
manifest, approval, product or measured input was altered to resolve it.

## Criterion disposition and prior findings

| Approved requirement | Independent assessment and actual proof |
|---|---|
| Sections 5, 9, 10: portable contracts and four source adapters | Approved T01/T02/T03 proof covers identity, versions, cursor/result invariants, OpenAlex/Crossref mapping, graph direction/source and OA host/license. W2.C02.T01's authenticated fresh 100-case connector and 20-case contract runs preserve these boundaries at the latest product candidate. Source candidates and observed terms do not become canonical Works or action permissions. |
| Sections 8, 10: material failures, denial and cleanup | Named broker, transport, authority and persistence checks cover 429/Retry-After, bounded 5xx recovery, circuit behavior, timeout/reset, malformed/missing/schema-drift responses, cursor/duplicate conflicts, current Intent/privacy/configuration/rights denial and redaction. Actual interrupted stream/lease/lane cleanup and protected failed-page/checkpoint preservation close F-SLICE-01. |
| Sections 10, 17: integrated vertical behavior, cancellation and restart | The real protected Core/DPAPI/SQLCipher/worker fixture exercises all four providers from a clean project, cold/cache publication, failure/recovery, in-flight cancellation and reopened runtime. The reviewer independently read and hashed `source-slice-2v0j68jz/result.json`: `98a86d4ac9d30b27eedb6d136e3996832e82bbb57a25766f010f304874129e9b`. Eight count-five/singleton phases, nine boundary-inclusive dispatches, retained timeout/reset, absent cancelled observation and unchanged checkpoint establish the stated outcomes. HTTP and ASGI/native context are explicit substitutes; this is not an OS process-kill or fresh installer run. |
| Sections 10, 13: downstream handoff and rights | The executed `source_public_handoff.py` consumer uses public JSON schemas without Core/storage imports. Assertions verify actual provider/version/query/cursor/retrieval identities, distinct observations, OA locations/licenses/hosts and graph direction/seed. Provider, partial-result and retrieval substitutions fail. Model-use/export/share remain unknown; current authorization is still required. |
| Sections 6, 10: user workflow and accessibility | T03 actual native supervisor/Core and GUI evidence covers protected configuration and focus/cancel/reopen behavior at its own candidate. The correction's strict client/native route, renderer and browser checks cover matching/late diagnostics, failure/unavailable fallback, explicit confirmation and focus. Independently approved correction captures cover 144 primary and 22 supplementary images, both themes/three widths and measured contrast. The documented offscreen skip-link capture artifact is nonblocking under its viewport/DOM corroboration; no functional or accessibility requirement is waived. |
| Sections 11, 12: timing guidance and operational visibility | Approved W2.C02.T01 R01 closes F-SLICE-02 with selected request limits and explicitly unavailable completion prediction before confirmation, plus actual dispatch/retry counts, distinct exchange/broker elapsed times, size/status/outcome/cache/rate/warning/cursor facts for the matching protected observation. Historical absence remains unavailable; cache no-dispatch is zero. Limits are not presented as an end-to-end deadline, and benchmark timings are not product telemetry. |
| Sections 10, 14: compatibility, migration and history | Existing upgrade/rollback tests and historical fixtures retain their task bindings. The correction introduces optional operational measurements without migration or scientific identity change; exact historical bytes/hash/revision count and same-invocation replay survive reopening. No hidden reconstructive consumer or new canonical store is required. |
| Sections 10, 15, 17: architecture, documentation, conformance and evidence | Reviewed generated API/client parity, exact native admission, architecture, affected quality/build and separately approved reference/control restoration evidence retain their proper candidates. The committed matrix supplies the task, correction, control, visual, integrated and performance chains with selected/deferred rationale. No new material architecture, security, scope or reference change is introduced. |
| Sections 10, 11: performance | The independently approved immutable baseline is followed by separately fresh, authenticated three-process qualification below. All samples meet every reviewed and absolute ceiling. |

**F-SLICE-01 remains closed at
`1ccf0f923572aab5f553b2b7de6879d75a0a326c`.** The existing independent control
review identifies the real partial-read deadline, reset and hanging cancellation
regressions and protected persistence/restart proof. Those tests are also in the
correction's fresh connector run. The original adverse finding is preserved.

**F-SLICE-02 remains closed at
`b17bc9d868e4e9ee672dbac7b765514403949b9d`.** The independently recorded correction
R01 supplies its explicit pre-submission closure; telemetry, bounded timing
guidance, authority and immutable historical behavior were reviewed together.
The subsequent benchmark closes the separate performance obligation, rather
than being substituted for the missing product behavior. Original task/control
pre-submission findings and adverse execution attempts remain immutable.

No hidden production follow-up or disabled failing check needed for this bounded
slice outcome was identified. Later full qualification remains an explicit Wave
obligation, not concealed unfinished source-slice implementation.

## Fresh performance qualification authentication

| Evidence | SHA-256 |
|---|---|
| `artifacts/tmp/CAP-04.S02.performance-qualification-01.json` | `17be1883e4813bef9e10546dbdccbd4c3b507fd953426150212a326e84c52721` |
| `artifacts/tmp/CAP-04.S02.performance-qualification-01.execution.json` | `f857184c4e9e4a0b140def28d8b00bf8508703f6510120cfbe62bab5a9234b08` |
| `artifacts/tmp/CAP-04.S02.performance-qualification-01.log` | `86d3e5f9778e60019b4343182464f14f228a13236ba1928ec8a5bfd3b25d3cb5` |
| Executing `tools/source_performance_check.py` | `08139bc4f503b42c5fbae9ed2f550a24a7da3738ad8d172a4a353c014f955346` |
| Immutable reviewed baseline | `d21fc40e3fedb71ecf0e0b274055d047b2fec4bb4278a1642894534d3c323822` |

The actual execution record binds a qualifying invocation without `--calibrate`,
exit 0 and identical starting/ending candidate. The final aggregate is PASS with
`performanceQualifying: true`, three repetitions and reuse disabled. Producer
elapsed time is 203.16890079993755 seconds; wrapper elapsed time is
214.28128460003063 seconds. These describe different measured boundaries.

All 381 source/test/fixture/contract/tool inputs independently match both the
tested Git blobs and current raw checkout bytes. Their canonical map digest is
`b1b59f337ea9b50c68a3f6e9a217b1cd90c891d62407ddba17b3ad05f1e29dff`.
The extra input relative to calibration is the committed baseline. The hardware
and method match the reviewed baseline exactly. Current runtime identity and
the 6,218-file installed dependency aggregate match the retained report:
`a33f2b7e2f65de1ae295caca7441834038d7283580384846a02b36ee7d2be243`.
`stdlibAndOsClosureAuthenticated: false` remains explicitly bounded and does not
authorize result caching.

The reviewed producer holds its selected input/dependency locks for execution,
uses fresh parent/child bytecode prefixes and runs the source/runtime/dependency,
HEAD and directory guards before atomic final publication. The final PASS is
consistent with this exact guarded producer and retained exit record; it is not
inferred from an unchecked self-declared receipt alone.

After ordinary sandbox denial, the reviewer independently read and hashed all
three original protected child reports and logs in an approved owner context.
Each original report equals its aggregate raw sample and its consolidated
projection. Paths are below `artifacts/tmp/source-performance-sjp58yev/`:

| Sample | `sample-N/result.json` SHA-256 | `sample-N/raw.log` SHA-256 |
|---|---|---|
| 1 | `a35882ba55b4e02d4c444ca9c78d91ebb0a24bb8dac2b3faccfcf126d37b1ff8` | `8d48d2caad0dd72af2d4aacc7b2958c2cfaa9a2dd8e719d69efd9c7c34cbf253` |
| 2 | `08ddd96200132edc92490e6759b67ffc341432b4edef03d4e9db76427257ceaa` | `567f24aaf1657f4faec5d07c10f0e3c1309a0cdcc76b975707bd2dc4c03e955e` |
| 3 | `981b88a3f1695f880624881b99b6fe4363320477254e5ad819eec262422d6faf` | `587c941217e55c5e66a403a6c1b3fcdb286a8fa87420b632c5e628c680e37699` |

The reviewer recomputed all 30 raw values, ten min/median/max distributions and
limits. Every value passes the smaller of the baseline maximum plus 20% and
30 seconds/512 MiB. The matrix's ten maxima and ceilings agree exactly; no sample
is omitted or averaged away. Largest observed provider-page time is
3.077802999992855 seconds; largest cache time is 2.778798400075175 seconds;
largest peak working set is 189566976 bytes. These are bounded synthetic local
measurements, not live-provider predictions.

Every child has the complete 100/100/1/100 record cold/cache matrix, one dispatch
per cold phase and zero per cache phase, four integrated calls, preserved restart
state and eight retained diagnostics. Separate broker probes each make two calls
with maximum concurrency one. Wire-start intervals are 1.0752498999936506,
1.0656664000125602 and 1.0749285001074895 seconds; all actual sleeps exceed their
requested waits. The largest probe duration is 1.1478734998963773 seconds, below
its reviewed 1.3701023999601603-second ceiling.

## Preserved limits and remaining Wave gates

This disposition approves the local Windows slice within its approved scope.
The actual measured workstation is Windows 11 build 10.0.26200, AMD64, Intel64
Family 6 Model 183 Stepping 1, 20 logical CPUs and 16984227840 bytes physical
memory. No minimum-hardware, OS-cache-flush, installer-performance or live-service
result is inferred. Synthetic provider transport and the separate real-clock
broker probe retain their declared substitutions; no protected concurrent-runtime
performance claim is made. Live calls remain outside the selected authorization.

Historical native manual Save is only the original observation at
`a8955b86f75d628f2e23c7eac336de66c332b098`. Later actual native API/GUI proof stays
bound to `1e68cab433f194bf5d834bedc974bdac5a4f7cb6`; browser doubles, native unit
tests and real protected Core checks retain separate meanings. Prior incomplete
retention traversal remains preserved and superseded by its strict owner reads.
No fresh native GUI, spoken screen-reader session, OS process-kill or live TLS
provider run is claimed. Earlier isolated TLS and reference-history evidence
retain their actual candidates.

The disclosed 55 broad-quality errors in 13 unchanged files and two unavailable
Windows-token symlink checks remain unresolved Wave qualification obligations,
not passing or waived checks. W2 still requires fresh full repository/affected
profile checks, required Windows packaging/platform and cross-capability happy,
failure, denial, cancellation, migration, restart and recovery qualification,
independent Wave review and the separate human G2 release decision. This slice
approval authorizes none of those dispositions in advance.
