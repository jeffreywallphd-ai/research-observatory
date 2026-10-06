# Open-access acquisition

CAP-05.S01.T02 provides Core-owned selection and acquisition behind
`DocumentAttachmentRuntime`. The queue, alternative-copy journey and entitlement
placeholders are the CAP-05.S01.T03 handoff. ADR-0019, ADR-0027, ADR-0028 and
ADR-0029 govern privacy, source identity, isolation and content limits.

Acquisition orchestration depends on portable persistence and inspected-staging
ports. The document attachment data adapter owns acquisition projections and
current association checks; main composes both with the existing encrypted store.

Core resolves exact locations from the retained connector record and its source
assertion/address/ordinal. OpenAlex, Unpaywall and Semantic Scholar observations
retain their own URL, field key, license and version. Crossref metadata is not an
open-access grant. Missing license/version/checksum remain missing. Unsafe URLs
remain source metadata but cannot be selected. An OA flag or license observation
does not create store, inspect, export, model or sharing permission.

The location UUID identifies one provider-hosted full-text copy. Existing
action-specific rights policy must currently allow store and inspect. Accepted
Intent must allow approved content from that provider; current project privacy
must allow approved providers. Core previews bind the exact location, Work/version
revisions, expected checksum, explicit redirect hosts, policy revision, actor,
Intent, privacy and native session. Opaque confirmation expires after ten minutes
and is consumed once. Restart/close never restores it. T03 must request fresh
selection/confirmation before retrying an interrupted admitted operation.

The broker performs HTTPS GET on port 443. It checks every DNS answer and pins the
actual socket to a public numeric address while verifying TLS against the original
hostname. It uses no proxy/environment, browser cookie, credential or referrer
authority. Cross-host redirects require exact hosts in the confirmed selection.
The complete transfer permits at most five redirects, three attempts, 120 seconds,
128 MiB total wire bytes across attempts and 128 MiB expanded content. Identity
encoding avoids implicit decompression; unsupported encoding fails closed. Each
socket phase rechecks authority and caps its timeout to the remaining deadline.
One acquisition per project runs at a time; cancellation and current authority
are checked during stream and retry waits. Network retries discard their owned
encrypted partial and start from fresh bytes; range concatenation is not used.

Each confirmed operation is recorded before the first request as an existing
canonical workflow revision with atomic provenance, outbox and material
dependencies. Success appends a terminal workflow revision atomically with the
candidate, operation binding and protected source receipt. Failure/cancellation
records a bounded code when current authority permits; a revoked session retains
the admitted request for T03 recovery rather than fabricating a terminal result.
Typed staging or inspector cancellation records cancelled with the bounded
acquisition-cancelled code, including cancellation after network transfer.
These append-only facts are not reusable dispatch authority.

Bytes stream into the existing encrypted object store. Response MIME is only a
claim; the signed LPAC inspector validates the actual format and bounded structure.
Content-Disposition filenames are ignored. The receipt retains selected source,
license/version, actual and optional expected checksum, media, byte counts,
redirects, attempts, transfer time and confirmation/policy digests. Failed content
has no canonical document association, and its metadata remains usable.

Final document commit still requires exact Work/version confirmation and explicit
local permitted use. It rechecks the provider-copy policy and includes its revision
and the receipt digest in canonical provenance/dependencies. A changed provider
policy requires renewed acquisition; it never silently relabels old permission.
`AcquisitionRepository.source_for_revision` returns the retained location and
receipt after restart. T03 should map bounded acquisition errors to its approved
unavailable, denied, failed, cancelled and retry states.

Portable selection/location/receipt schemas live under
`packages/contracts/documents/`. URLs and source observations are protected
research data, never diagnostics. Public commands accept exact identities, not
arbitrary destination URLs or filesystem paths. Schema v24 adds immutable
location, admitted-attempt, attempt-result and candidate-source projections;
existing canonical aggregates own durable operation identity. The literal
populated v23 fixture preserves prior rows and ciphertext. Migrations are
forward-only; recovery restores the verified predecessor backup. Earlier recovery
schemas and histories remain immutable and interpretable.

Focused tests distinguish pure behavior and unit transports from the owned real
HTTPS, SQLCipher, encrypted-object and signed-LPAC boundary. Test DNS/socket routing,
CA trust and signing inventory are synthetic test authority; they do not establish
public provider availability or production installation/package qualification.
