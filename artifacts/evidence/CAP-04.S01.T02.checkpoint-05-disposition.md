# CAP-04.S01.T02 — native recovery checkpoint disposition

Candidate `ca524fb2709e52395e1cddb9b8a12a13f8665f7e` closes the preserved
checkpoint-05 P1 at `4e328d5f41c63c8abae9270168407cc52e0d0ebb`. Initial
locked/invalid state now advances the recovery latch before session arming;
unlocked ordinary restart still retains the epoch. The composed regression
failed before remediation and passed afterward.

Fresh, fixed-candidate checks: 57 scoped native tests passed, with one existing
renderer-witness test ignored (not renderer proof); three Python composition and
startup-authentication tests passed in 1.215 seconds. Native integration-harness
compilation, Rust formatting and clean version-bound build metadata passed.

Independent reviewer `w2_source_packet_preflight` approved this bounded checkpoint
at the exact candidate after reviewing the prior finding and incremental risk.
Independent replay of the new startup regression passed in 0.04 seconds; HEAD and
reviewed inputs stayed unchanged. No other incremental blocker was found.

Local main was fast-forwarded to that candidate. No remote push, formal task R01,
task completion, native/UI/principal or packaging qualification is claimed.
