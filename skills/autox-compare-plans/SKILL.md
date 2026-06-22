---
name: autox-compare-plans
description: Normalize and compare baseline and candidate TiDB execution plans, experiments, expected impact, confidence, and operational risk for an AutoX case. Use when selecting among binding, index, statistics, hint, rewrite, configuration, or recovery candidates.
---

# AutoX Compare Plans

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `candidates_generated`.
2. Normalize unstable plan text without discarding semantic fields. Compare
   plan digest, operator tree, join order, access path, task type, partitions,
   predicates, estimated and actual rows, loops, time, memory, disk, and keys.
3. Separate estimated benefit, measured local benefit, production confidence,
   compatibility, write/storage cost, blast radius, and rollback complexity.
4. Explain why each plan changed. Treat lower cost or a different digest as
   insufficient evidence.
5. Rank candidates and document rejected candidates with reasons.
6. Save the comparison and selected recommendation under `decision/`.
7. Mark the recommendation `validated` only when baseline reproduction and
   candidate validation are both adequate.
8. Update manifest recommendation fields, append to `audit.md`, and set
   `current_stage: candidates_compared`.
