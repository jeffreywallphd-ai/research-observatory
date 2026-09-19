# CAP-04.S01.T02 — checkpoint-05 adverse review

Candidate `4e328d5f41c63c8abae9270168407cc52e0d0ebb`, base
`09c99d1346ef1e67cf8e2f490a22d55bdfa9a271`. Independent reviewer
`w2_source_packet_preflight`: NOT APPROVED for local integration; one P1.

Startup security lock did not invalidate the import recovery epoch. The lock
manager initialized its protected ApplicationRestart state before the session
latch was bound. Binding only stored the latch, leaving generation zero. A prior
Ordinary marker could therefore retain its epoch; unlock and explicit project
open could resume the old pending run across an actual security-lock boundary.
ADR-0018/0025 require that boundary to invalidate same-run automatic recovery.

Root cause: incremental lock events were covered, but initial locked state was
omitted when connecting the two authorities. Required regression: real policy
initialization plus Ordinary marker, startup lock, latch binding and epoch
rotation; preserve retention for genuinely unlocked ordinary restart.

Other candidate checks: 56 native tests passed, one renderer witness explicitly
ignored (not UI proof); 28 Python tests passed in 13.101 seconds; six-file Python
quality, Rust format, architecture and clean build identity passed. Independent
API attach-failure and drain-failure probes passed in 0.653 seconds. These passes
do not override the P1. Candidate was not integrated. No task R01/DONE claim.
