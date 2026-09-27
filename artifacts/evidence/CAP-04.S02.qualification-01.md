# CAP-04.S02 integrated qualification

The source-slice qualification evidence is complete. The separate independent
slice disposition and taskctl transition remain required; this evidence does
not itself approve the slice, Wave exit or release.

Authority: the complete approved W2 packet at
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`, particularly
`planning/slice-plans/CAP-04/CAP-04.S02-open-scholarly-source-adapters.md`
sections 8 and 10–17, accepted ADR-0027 and approved presentation reference 1.7.
The inherited semantic workflow catalog remains 1.5. All three ordinary tasks
and the linked W2.C02.T01 correction have independent approved dispositions.

## Evidence matrix

| Requirement | Actual proof and limits |
|---|---|
| Provider-neutral contracts, identities, cursor/outcome invariants | CAP-04.S02.T01.json and review-R01 bind e5c57e9784d7f06957d9e5e850a916002110d87f. T02/T03 extend these contracts; W2.C02.T01 preserves historical missing-measurement serialization and strict optional measurements. |
| Four provider adapters, OA host/license and graph source/direction | T02 at 16b1524278b9e9ad9e52c322aa4b0fba0bb6fef0 and T03 at 1e68cab433f194bf5d834bedc974bdac5a4f7cb6 have exact independent task dispositions. The correction's fresh 100-test connector and 20-test contract runs preserve these outcomes at b17bc9d868e4e9ee672dbac7b765514403949b9d. |
| Material failure, denial and bounded retries | Named broker/transport/authority/persistence checks cover 429/Retry-After, 5xx, auth/configuration/privacy/rights denial, malformed bounded responses, cursor conflicts, duplicate publication and circuit recovery. Retained F-SLICE-01 closes in qualification-controls-review-01.md at 1ccf0f923572aab5f553b2b7de6879d75a0a326c through actual exchange deadline/reset/cancellation exception paths; these are also included in the correction's fresh connector suite. |
| Protected integration, cancellation and restart | At b17bc9d, source-slice-2v0j68jz/result.json SHA256 98a86d4ac9d30b27eedb6d136e3996832e82bbb57a25766f010f304874129e9b records eight cold/cache samples, 5/5/1/5 records by provider, one cold dispatch/zero cache dispatch, nine total boundary-inclusive synthetic dispatches, retained timeout/provider-unavailable, cancellation and restart. DPAPI, SQLCipher, durable workers and publication are real; HTTP and ASGI/native context are explicit substitutes. Restart reopens Core over retained state, not an OS process kill. |
| Public downstream handoff and restrictive rights | source_public_handoff.py consumes public JSON schemas without Core/storage imports. The integrated test checks actual OA locations, graph direction/seed, provider/version/query/cursor identity and unknown model-use/export/share rights, rejects substituted provider/retrieval/partial outcome, and requires current authorization. No canonical Work or downstream acquisition right is inferred. |
| Source operational visibility | Independent W2.C02.T01 R01 closes retained F-SLICE-02: actual HTTP requests/retries and exchange/broker elapsed times, cache absence, historical unavailable values, matching protected observation and context-safe UI. Preview names selected limits and explicitly unavailable completion estimate. Benchmark timings are separate. |
| Native principal and accessibility/visual behavior | T03's actual native supervisor/Core protected integration and GUI18 retain their original 1e68 candidate and limitations, including historical manual Save. Correction browser/native/client tests prove their own boundaries. Independent correction visual review covers 144 primary and 22 supplementary captures, both themes/three widths, focus and contrast, with minimum measured text contrast 4.7152481724354205. The recorded tall-element offscreen skip-link capture artifact remains an explicit nonblocking capture limitation, corroborated by actual viewport/DOM observations. No new spoken screen-reader session is claimed. |
| Compatibility, history and recovery | Existing migrations remain unchanged by the correction. Original task evidence retains real compatible Intent/project upgrade and rollback checks. Correction persistence checks preserve exact old serialized page bytes/hash/revision count and same-invocation replay after reopening; absent historical metrics remain unavailable. |
| Architecture, generated contracts and clean build | Exact task/control/correction evidence records generated API/client parity, native route admission, architecture, affected quality, actual sidecar build and approved-reference conformance at their actual candidates. No renderer storage/secret authority or hosted infrastructure is introduced. |
| Performance | Independently approved immutable baseline at c81c63f2760a97368f00bb993a9559b18681b5c7; separate fresh three-process qualification PASS at c01247db9badded2d098ad86a17c9e454f00d5fa. Every raw metric meets the unchanged reviewed and absolute ceilings. Exact bindings and measurements follow below. |

## Preserved scope and remaining Wave work

Prior evidence is authenticated and composed with its actual candidate and
principal limits; it is not relabeled fresh execution or cached qualification.
The original task approvals, adverse preflight findings, failed ADR/status-locator
checks and later accepted control/restoration dispositions remain unchanged.
Source measurements do not grant execution, rights or scientific authority.

Synthetic transport proves deterministic provider mapping and boundaries. No live
provider traffic, minimum-hardware result, OS cache flush, installer performance
or protected concurrent-runtime result is claimed. The separate real-clock rate
probe uses a shared broker with synthetic authority/store/HTTP.

The earlier 55 quality errors in 13 unchanged files and two unavailable Windows
symlink-token tests remain explicit Wave obligations. Fresh full repository and
affected profiles, cross-capability, packaging, required platform qualification,
independent Wave review and human G2 release decision remain due. Final slice
disposition follows the completed performance evidence and committed matrix.

## Fresh performance qualification

Clean fixed candidate `c01247db9badded2d098ad86a17c9e454f00d5fa`; all three samples passed and
`performanceQualifying: true`. Producer elapsed 203.16890079993755 seconds;
wrapper elapsed 214.28128460003063 seconds. The run held source/installed-runtime
inputs fixed, used fresh process/project and bytecode prefixes, and completed
final identity checks with unchanged HEAD. No heavy verification competed.

```text
python -B -s -X pycache_prefix=artifacts/tmp/CAP-04.S02.performance-qualification-01-unused-bytecode tools/source_performance_check.py --report artifacts/tmp/CAP-04.S02.performance-qualification-01.json
```

Report SHA256 `17be1883e4813bef9e10546dbdccbd4c3b507fd953426150212a326e84c52721`;
executing tool SHA256 `08139bc4f503b42c5fbae9ed2f550a24a7da3738ad8d172a4a353c014f955346`;
reviewed baseline SHA256 `d21fc40e3fedb71ecf0e0b274055d047b2fec4bb4278a1642894534d3c323822`.
The report binds 381 source/test/fixture/contract/tool inputs, actual installed
dependencies and runtime, the exact reviewed hardware, methodology and all raw
child reports/logs. The new input relative to calibration is the baseline itself.
No sample was omitted or averaged away.

| Metric | Largest fresh observation | Reviewed ceiling |
|---|---:|---:|
| openalex:cold | 3.060325799975544 | 4.07051268001087 |
| openalex:cache | 2.778798400075175 | 3.678903119964525 |
| crossref:cold | 2.9628820000216365 | 4.014907920034602 |
| crossref:cache | 2.709722700063139 | 3.7441223999485373 |
| unpaywall:cold | 2.933384499978274 | 3.858154800022021 |
| unpaywall:cache | 2.6097941000480205 | 3.2815895999316127 |
| semantic-scholar:cold | 3.077802999992855 | 3.8862421200145034 |
| semantic-scholar:cache | 2.6650509999599308 | 3.3584441999439147 |
| rateWait | 1.1478734998963773 | 1.3701023999601603 |
| peakWorkingSetBytes | 189566976 | 226585804.79999998 |

Times are seconds; peak working set is bytes. Ceilings are the smaller of
the immutable measured baseline plus 20% and 30 seconds/512 MiB. The recorded
distribution is min/median/max of three repetitions, not an inferred percentile.
Raw metrics and each original report/log digest are retained in
`artifacts/evidence/CAP-04.S02.qualification-01.json`, alongside exact digests of
the task/review, correction, baseline/review and execution records.

## Candidate continuity and disposition

After correction qualification at b17bc9d, later commits record its submission,
independent approval, generated views and ordinary campaign resume. The only
subsequent executable change is the independently reviewed benchmark baseline
hash pin, with the new measured fixture. Product/runtime/native/client/renderer
inputs are unchanged; existing task, native, TLS, protected integration and
visual observations retain their original candidates and stated limits. The
performance run above is separately fresh at the final benchmark candidate.
The calibrated baseline and control checks have their own exact candidate and
independent disposition; they are not relabeled qualifying measurements.

The source slice has no remaining known criterion-bound finding. Independent
review must authenticate this complete matrix and its measured evidence before
taskctl records slice approval. The original task approvals, adverse findings
and Wave release/qualification obligations remain intact.
