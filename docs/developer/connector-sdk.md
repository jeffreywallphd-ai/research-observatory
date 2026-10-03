# Connector SDK: synthetic repository example and conformance

The [sample repository connector](../../plugins/connectors/sample_repository/plugin/connector.py)
shows how to turn public repository metadata into source-reported assertions.
Its domain is `repository.example.invalid`, and every record in its
[fixtures](../../plugins/connectors/sample_repository/fixtures) is synthetic.
It is a developer example, not a live source, trusted publisher, or permission
to retrieve, retain, use, export, or share content.

## Implement the fixed worker entry point

The package manifest names `plugin/connector.py` as its fixed entry point. The
file exports `invoke(input_data, broker, operation)`. Connectors that need to
emit the current invocation label may also declare a keyword-only `context`
parameter, as the sample does:

```python
def invoke(input_data: bytes, broker, operation: str, *, context: dict) -> bytes:
    invocation_id = context["invocationId"]
    ...
```

The worker owns `context`; it supplies only `invocationId`. Existing
three-argument plugins retain their entry point. Neither the label nor any
plugin-authored output grants project, source, network, credential, or rights
authority. Core checks the exact invocation and operation and binds the source
namespace and retrieval time after validating the result.

The sample supports `repository-metadata` with input
`{"repositoryId":"archive-01"}` and `search` with input
`{"query":"synthetic metadata","pageSize":1}`. A continuation additionally
includes `cursor` and `previousInvocationId`. The plugin sends one typed broker
call per page. It never forwards `previousInvocationId` to the broker. The
broker call cannot contain a URL, method, arbitrary header, file path, project
path, or secret; Core checks the signed exact HTTPS destination, current grant,
project/Intent/rights policy, consent, rate limit, and public-address rule.
`repository-metadata` is a bounded public-metadata operation, not general HTTP
or access to a local/project repository. Direct local files, loopback, private
addresses, and plugin-held credentials remain unavailable under ADR-0028.

The result is one `source-assertions-v1` page: `schemaVersion`, `invocationId`,
`operation`, `records`, `continuation`, and `nextCursor` only when another page
exists. Each record has `rawIdentifier`, `identifiers`, `fields`, and `terms`.
`terms.license`, `terms.terms`, and `terms.access` are explicitly
**source-reported observations**. Do not add `projectId`, `sourceId`,
`retrievedAt`, `rightsStatus`, a canonical Work ID, or a use/export grant to the
worker result. Missing terms remain `not-reported`; they do not become open or
permitted. Core validates and publishes a page only under its durable job,
current authorization, and cancellation fence. A returned worker page alone is
not a committed observation.

For search pagination, the sample's synthetic provider returns a bounded
top-level `nextCursor`. The worker may report that cursor only after the broker
has observed it. A new invocation requires the previous committed page, the
same project/package/query/page size, the exact reported cursor, and a fresh
current preview and confirmation. A partial/error page cannot advance the
checkpoint. Replaying a source request produces a new observation; it never
rewrites the earlier one.

## Write and validate a package

Copy the [unsigned draft manifest](../../plugins/connectors/sample_repository/manifest.json)
and the sample file into your own workspace. Change the stable plugin ID,
qualified source ID (`plugin.<pluginId>`), publisher key ID, declared operations,
exact public HTTPS scheme/host/port/path templates, data classes, terms, and
requested permissions to describe your connector. List every packaged file with
its exact SHA-256 digest. The signed manifest does not itself authorize a
network request or a rights action.

Run the static checker on the draft and synthetic cases from the repository
root:

```powershell
.venv\Scripts\python.exe tools\connector_conformance.py `
  --manifest plugins\connectors\sample_repository\manifest.json `
  --case plugins\connectors\sample_repository\fixtures\repository-metadata.case.json `
  --case plugins\connectors\sample_repository\fixtures\search-page-1.case.json `
  --case plugins\connectors\sample_repository\fixtures\search-page-2.case.json
```

The command reports `result`, `caseCount`, and stable `code`/JSON `pointer`
violations. A `pass` requires at least one supplied case for **every** operation
in the manifest. A manifest declaring `search` also needs a first-page case
and a linked continuation case whose `previousInvocationId`, cursor, query,
and page size match that first page. With no cases, the package inspection is
reported as `incomplete`, returns a nonzero exit code, and cannot be used as a
behavioral conformance result. Partial case coverage returns `fail` with
`CASE_OPERATION_COVERAGE_MISSING` or
`SEARCH_CONTINUATION_COVERAGE_MISSING` at the affected manifest operation.
For example, a worker-selected project ID yields
`PAGE_UNKNOWN_FIELD` at `/output/projectId`; a cursor absent from the fixture's
broker response yields `PAGE_CURSOR_UNOBSERVED` at `/output/nextCursor`.
Reports contain no input values, response bodies, credentials, or file paths.
Draft checking verifies declared local file hashes and fixture contracts but
**does not execute** the connector or confer trust.

To validate an archive, create a ZIP containing only `manifest.json`, detached
`manifest.sig`, and every declared package file. Sign the exact manifest bytes
with a publisher-controlled Ed25519 private key kept outside the package and
repository. Supply the corresponding raw 32-byte public key through an
independent local trust decision, then run:

```powershell
.venv\Scripts\python.exe tools\connector_conformance.py `
  --package C:\path\to\connector.zip `
  --publisher-key-id your-publisher-id `
  --publisher-key-file C:\path\to\publisher.pub `
  --case C:\path\to\metadata.case.json `
  --case C:\path\to\search-first.case.json `
  --case C:\path\to\search-next.case.json
```

Archive mode verifies the detached signature, complete declared file set,
hashes, manifest version, and supplied cases. Repeat `--case` to cover every
declared operation and a linked search continuation when applicable. Archive
inspection without cases remains `incomplete` as behavioral conformance. The
public key must come from outside the
archive; a key bundled by a plugin cannot trust itself. The sample manifest
has no signature and the `.invalid` endpoint cannot be enabled as a live
connector. Keep signing keys, actual institution names, private fixture data,
and credentials out of tracked files.

## What the checker proves

A case records the intended operation and opaque invocation ID, exact
scientific `input`, one expected `brokerCall`, a synthetic `brokerResponse`,
and the worker `output`. Search cases must link pages through
`previousInvocationId`; the checker detects missing predecessors, changed
query/page size, non-advancing cursors, broker-unobserved cursors, result-shape
errors, undeclared operations, and changed package bytes. Its diagnostic
locations use JSON Pointer syntax and never echo the offending value.

The checker validates supplied bytes and fixtures without importing candidate
code. It does not prove that a third-party connector actually emits those
bytes, that a remote repository exists, or that an OS boundary denied an
action. Executable conformance must run the signed package inside the
application-pinned Windows x64 LPAC worker with synthetic broker responses,
then validate Core's encrypted publication, denial, cancellation, and restart
behavior. Focused native connector tests must exercise that path; the W2 slice
and Wave gates complete broader security, privacy, rights,
packaging, and platform qualification. Never run an untrusted plugin directly
in the Core process or in a developer-side Python import to claim conformance.

Breaking SDK changes require a new major compatibility policy and explicit
behavior for older packages. Unknown required features, incompatible major
versions, changed package digests, revoked publisher trust, or changed project
permissions deny execution until reviewed and enabled again. There is no
marketplace or automatic key discovery in this local Wave.
