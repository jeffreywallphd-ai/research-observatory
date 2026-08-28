# Service verification

Owner: Core API maintainers. Boundary: application use cases, ports, adapters, and API composition tests.

`fixtures/valid-intent-draft-request.json` is the canonical service-boundary
request fixture for CAP-03.S02 draft persistence and impact-preview tests. Tests
replace only the temporary project root, expected revision, and criterion-owned
fields; the remaining shape must continue to cross the generated API contract.
