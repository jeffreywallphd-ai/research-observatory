# Governance recovery requests

This directory contains inert, hash-bound Governance Recovery Request packets,
their canonical proposals, schemas, independent packet-review ledgers, and human
review surfaces. A GRR is exceptional: use it only when the ordinary ECR lane
cannot represent or safely enforce the next amendment.

Approval authorizes only the packet's named `GRR-NNNN.B00`. Bootstrap evidence
and independent review are controlled by `tools/recoveryctl.py`. An ACTIVE hold
denies ordinary execution. The later ECR/amendment always requires separate
review and human approval, and the hold remains until amendment adoption records
a bound control/security checkpoint.

Never rewrite an approved packet, prior review, evidence, approval, or terminal
disposition. Create a new versioned schema path for future formats.

If approved B00 execution exposes a latent control defect that blocks only the
exact approved repair amendment, use a sequential `GRR-NNNN.SNN` supplement
under the same ACTIVE hold. A supplement is independently reviewed and
exact-commit approved before `recoveryctl supplement-start`; it authorizes only
the sequential `GRR-NNNN.BNN` and never materialization, task execution, Wave
resume, hold release, or a gate. Supplemental evidence and review use separate
schemas and append-only RNN histories. A non-approved latest supplement denies
all ordinary taskctl mutations.
