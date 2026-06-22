---
name: autox-verify-reproduction
description: Verify whether a version-matched local TiDB environment reproduces the production execution plan and optimizer context for an AutoX case. Use before claiming that any binding, index, statistics, hint, or SQL rewrite candidate is validated.
---

# AutoX Verify Reproduction

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `lab_prepared`.
2. Capture the production and local plan in comparable formats, including
   access paths, join order, task types, estimates, predicates, partitions, and
   plan digest when available.
3. Compare TiDB version, schema, stats, variables, bindings, parameter values,
   prepared/text protocol behavior, and isolation engines.
4. Distinguish exact reproduction, structurally equivalent reproduction, and
   failure.
5. Save plans, normalization notes, and mismatch evidence under `baseline/`.
6. Set manifest reproduction status and both plan digests.
7. Append the verdict and all mismatches to `audit.md`.
8. Set `current_stage: reproduction_checked`.

If reproduction fails, do not block source exploration, but mark later
recommendations advisory and ineligible for automatic production action.
