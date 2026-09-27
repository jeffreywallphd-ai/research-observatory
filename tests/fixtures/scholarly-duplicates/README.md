# Frozen duplicate retrieval benchmark

These CSVs contain the Leipzig Database Group public DBLP-ACM entity
resolution benchmark. It is **not synthetic** and is not covered by the CC0
declaration in the separate `scholarly-metadata` fixture directory.

Source and attribution: [Leipzig benchmark dataset page](https://dbs.uni-leipzig.de/research/projects/benchmark-datasets-for-entity-resolution),
Hanna Köpcke, Andreas Thor, Erhard Rahm, *Evaluation of entity resolution
approaches on real-world match problems*, VLDB 2010. The dataset page licenses
these datasets under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
The archive was obtained from the page's
[DBLP-ACM download](https://dbs.uni-leipzig.de/files/datasets/DBLP-ACM.zip).
License/provenance was checked on 2026-09-27 before scoring or tuning.

`benchmark-v1.json` freezes the upstream archive/member and local fixture SHA-256 values, actual row
counts, targets, split membership, metric definitions and limitations before
algorithm implementation. The website's DBLP count is 2614; the actual frozen
archive has 2616 rows. That discrepancy is retained, not silently corrected.
Each upstream CSV is decoded reversibly as ISO-8859-1 and stored as readable
UTF-8 without changing characters or line endings. Tests reconstruct every
upstream member's exact bytes and authenticate its original SHA-256 offline.
The original ZIP remains unchanged in ignored local artifacts; its digest is
provenance and the ZIP is not a required test input. Readable text fixtures avoid
the repository's binary-admission requirement without changing privacy controls.
Source-qualified IDs and component-disjoint development/qualification splits
are derived locally; supplied gold pairs are unchanged. No other data changes
were made in creating this fixture.

Retrieval targets are precision >=0.90 and recall >=0.95 on each split. Only
development results may guide initial tuning. Freeze algorithm/configuration
before opening qualification results and retain every outcome. Changes after
qualification require explicit disclosure; the holdout cannot silently become
fresh unseen evidence again. Benchmark identifiers and supplied mapping labels
are identity/oracle data, never matching features.

The gold labels cover cross-source bibliographic pairs. Pair metrics use all
returned cross-source pairs in the split, and recall uses every supplied gold
pair in that split, including pairs missed by blocking. Report overmerge and
fragmentation for connected components derived from those pairs separately,
including transitive-closure pair errors. Those are a derived cluster oracle,
not independently labeled multi-source/version clusters. No universal scholarly
accuracy claim follows from this benchmark. Pages and abstracts are absent;
separate explicitly synthetic functional tests cover those features, same-source
behavior, conflicting identities, and three-record ambiguity.
