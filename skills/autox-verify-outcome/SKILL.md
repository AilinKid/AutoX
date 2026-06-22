---
name: autox-verify-outcome
description: Collect and compare post-implementation TiDB slow log, TopSQL, plan, latency, processed keys, execution count, CPU, errors, and workload evidence for an AutoX case. Use after an approved optimization is implemented to determine success, regression, insufficient evidence, or rollback.
---

# AutoX Verify Outcome

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `implementation_completed`.
2. Use the predefined observation and baseline windows. Adjust for workload
   volume, business cycle, deploy events, and collection failures.
3. Confirm the target SQL uses the intended plan and binding.
4. Compare latency distribution, execution count, process and total keys,
   result rows, CPU time, memory, disk spill, errors, and relevant cluster
   bottlenecks.
5. Separate workload-driven changes from per-execution improvements.
6. Save raw queries, outputs, calculations, and verdict under `outcome/`.
7. Classify the result as `improved`, `neutral`, `regressed`, or
   `insufficient_evidence`.
8. If rollback criteria are met, present evidence and execute the documented
   rollback only under the previously approved policy or fresh approval.
9. Append result and rollback status to `audit.md`.
10. Set `current_stage: outcome_verified`.
