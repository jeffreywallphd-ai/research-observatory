# CAP-04.S02.T01 — portable scholarly-source contracts

Claim base: `02e613a5eda87d83fd73f125157395810e6ec2cc`.
Authority: the approved W2 packet at `c85a59f3`, CAP-04.S02 section9.1 and
ADR-0027; ADR-0013/0024 identity/provenance and ADR-0019 current egress policy
remain unchanged. CAP-04.S01 is independently approved; required task dependencies
are DONE. No new approval or experience change is needed for this contract task.

## Acceptance closure

| Material boundary | Outcome and proof |
|---|---|
| Mockable, portable interfaces | Typed adapter/cancellation ports and immutable requests/results; a fake adapter completes a public-schema roundtrip without HTTP, paths, database or credential handles. |
| Scientific identity and resume | Separate invocation ID from project-scoped scientific request hash; provider/version/query/filter/sort/projection/page identity and cursor/project binding have substitution tests. Expired cursors fail explicitly. |
| Provenance and source assertions | Every page, including empty/failed pages, binds its request/provider and observation/retrieval state. Records retain actual raw identifiers and explicit license/terms/access observations, not canonical Work identity or permissions. |
| Empty, partial and failed | Validate page/continuation/error combinations; not-configured, denied, timeout, cancellation and unsupported operations never become empty complete results. |
| Private data and authentication | Closed scientific parameter shapes accept no arbitrary wire URL/header/auth/contact configuration. Payloads remain protected; bounded classified errors and reprs expose no query. Broker redaction/current authorization remain real implementation obligations for later adapters, not claims from these schema tests. |
| Rate, retry, cache and retention | ADR-0027 limits are represented without a scheduler: one in-flight/provider, initially at most one request/second, at most three attempts,30s and10MiB decompressed. Auth/permission denial is terminal; raw retention and cache observations cannot confer rights. |
| Compatibility and delivery | Version1 additive public JSON Schemas follow the existing Pydantic generation pattern; exact generation/fixture checks, unknown-field denial, domain UUID/UTC conventions, quality and schema inventory. No persisted predecessor or migration is introduced. |

First add the contract fixtures and expected-success/adversarial tests, record the
missing implementation failure, then implement the smallest models/ports and
schema-generation extension. Select focused contract/unit, affected generation,
architecture/build inventory and quality checks at the committed candidate.

No provider HTTP calls, credential access, account setup, database publication,
scheduler/cache implementation, UI, canonical reconciliation or licensed-provider
expansion belongs to this task. Real network/broker/persistence/platform integration
and source-slice qualification remain CAP-04.S02.T02/T03 and slice/checkpoint/Wave
work. No completed import suites or benchmark are repeated for this additive seam.

Read-only independent readiness survey found no authority conflict. It recommended
existing Pydantic plus standalone public schemas and Protocol ports, not an extension
of the specialized domain generator or a placeholder HTTP route. Its cursor,
empty/partial and rights/auth separation risks are incorporated above. Independent
commit-bound task review follows implementation; this worksheet grants no authority.
