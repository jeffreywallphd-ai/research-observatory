# CAP-04.S04.T03 bounded architecture-classifier maintenance

Predecessor: `tools/architecture_check.py` at task candidate base
`6487f8d3`, SHA-256
`112fc52a2d7dbbdd4f199f04b931896890926c181f9189d04a6379352f91ec59`.

The approved T03 implementation adds one root Core SQLite adapter,
`corpus_report_repository.py`. Before maintenance, the architecture checker
classified it as a business module and rejected its SQLite, storage and
concrete-adapter dependencies. This is a low-risk classifier coverage defect,
not authority to broaden where database access is allowed.

The intended delta adds exactly that module basename to the existing root
repository-adapter set. A negative test keeps same-named nested business files,
ports and business imports forbidden. The existing corpus and rights adapter
rules, port/data boundary and deployment profiles remain unchanged. Selected
checks are the focused architecture unit tests and `tools/architecture_check.py`;
the independent T03 review will inspect this bounded control change before
local integration.
