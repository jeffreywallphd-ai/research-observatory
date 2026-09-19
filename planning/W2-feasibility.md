# W2 bounded feasibility observations

Planning observations, 2026-09-19. These inform selection, not product acceptance.
No real project, user vault, credentials, native window or security setting was
accessed. No parser package/model was installed. Product storage code was unchanged
from `eaa3f93c53b40c7baa47fc3a522dc4936802c2ce` and its predecessor.

## CAP-05.S04.T01 — protected range cost

One disposable synthetic probe exercised real SQLCipher metadata and encrypted
object streams with in-memory test keys. Each range opened/authenticated the
whole source, discarded the prefix where necessary, read 64 KiB and closed.
Three paired observations per size; no OS cold-cache claim and no PDF rendering.

| Source | First range, ms | Last range, ms |
|---|---|---|
| 8 MiB |23.502 /20.170 /19.991|28.517 /28.501 /28.910|
|32 MiB|57.442 /55.119 /54.917|94.912 /92.554 /92.957|
|128 MiB|202.868 /198.806 /203.127|351.199 /388.610 /357.500|

A second real metadata writer was blocked while the read stream was held. It
acquired after closure, 187.935 ms from its request, including a deliberate 150 ms
hold. Therefore response delivery must not retain the object/database lease.

Windows AMD64, Python 3.14.6. Ignored local fixture/report:
`artifacts/tmp/W2-viewer-probe-nw43knr4/report.json`, SHA-256
`7f5afdf518e85009716e0bb2d5ee4a8f511687302b5913f2bfa2d01482be3106`.
Probe: `artifacts/tmp/W2-viewer-probe.py`, SHA-256
`8b3904b689ec5fbc4ae5b4f7d11e7e4f82af101e151255081469670084861614`.
Fixtures retained. Local hashes identify observations, not authenticated receipts.

**Inference:** bounded sequential authenticated reads are a reasonable first
implementation; do not add a chunk cache/storage migration now. This does not
prove the 1.5-second viewer target: renderer/gateway, cold/minimum hardware,
peak memory, bursts, concurrent writes and cancellation still require measurement.
ADR-0029 selects admission limits and cancellation work explicitly. Failure of
those checks remains a defect or an explicit design decision, not a silent cache
addition or threshold relaxation.

## CAP-05.S02.T03 — offline asset selection

The earlier 73-package Windows CPU wheel-resolution observation remains in
[W2 initiation](W2-initiation.md#proposed-shared-architecture-and-bounded-feasibility).
On 2026-09-19 the same bounded resolver configuration with `format-docx` added
resolved 74 packages, including `python-docx==1.2.0`. Output
`artifacts/tmp/W2-parser-probe/requirements-docx.lock`, SHA-256
`df7804bf3561a56da4659e40682fda6b42a5d75a7dc5ffe1e6f496383a070a13`.
This supersedes the selected dependency input, not the earlier observation;
neither run installs or qualifies the runtime.
The following inventory was checked against publisher metadata and the pinned
Docling 2.126.0 code, not downloaded weights. Build qualification must verify every
downloaded file, license/notice and installed runtime; no runtime hub fetch.

| Component | Immutable upstream revision | Runtime files / reported weight SHA-256 |
|---|---|---|
|[Heron layout](https://huggingface.co/docling-project/docling-layout-heron/tree/8f39ad3c0b4c58e9c2d2c84a38465abf757272d8)|`8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`|`config.json`, `preprocessor_config.json`, `model.safetensors`; 171658996 bytes; `00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c`|
|[TableFormer accurate](https://huggingface.co/docling-project/docling-models/tree/fc0f2d45e2218ea24bce5045f58a389aed16dc23/model_artifacts/tableformer/accurate)|`fc0f2d45e2218ea24bce5045f58a389aed16dc23` (v2.3.0)|`model_artifacts/tableformer/accurate/tm_config.json`, `tableformer_accurate.safetensors`; 212758388 bytes; `2a7d6c924b3cd12fb99a09280ca9c33a89c5d60b93253617d2e088c1a40374d9`|

Publisher-reported licenses are Apache-2.0 for Heron and CDLA-Permissive-2.0 for
the table model. Bundle the applicable license/model-card notices and dependency
notices; this observation is not a completed distribution-license audit. The
weights total 384417384 bytes, excluding configuration, runtime and notices.
The pinned table configuration embeds its word maps; no separate vocabulary
download is selected. The default Heron model revision must be explicitly
overridden to the immutable revision above, not left at a moving branch.

Primary implementation sources:
[layout presets](https://github.com/docling-project/docling/blob/v2.126.0/docling/datamodel/layout_model_specs.py),
[pipeline options](https://github.com/docling-project/docling/blob/v2.126.0/docling/datamodel/pipeline_options.py),
[table stage](https://github.com/docling-project/docling/blob/v2.126.0/docling/models/stages/table_structure/table_structure_model.py).
Use only local layout and table inference with cell matching; OCR, VLM,
picture classification/description, code/formula enrichment and remote services
are disabled. Selecting fewer assets does not establish runtime/offline/LPAC
success; packaged adversarial and representative-document checks remain required.
