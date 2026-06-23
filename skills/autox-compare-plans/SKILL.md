---
name: autox-compare-plans
description: Normalize and compare baseline and candidate TiDB execution plans, experiments, expected impact, confidence, and operational risk for an AutoX case. Use when selecting among binding, index, statistics, hint, rewrite, configuration, or recovery candidates.
---

# AutoX Compare Plans

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `candidates_generated`.
2. Record the exact TiDB version, explain format, session variables, bindings,
   stats health, plan digest source, and evidence file for every compared plan.
3. Normalize unstable plan text without discarding semantic fields. Strip only
   volatile operator-id suffixes when needed; preserve operator type, tree
   shape, Build/Probe labels, join side labels, task/store, access object,
   ranges, predicates, ordering, partition access, and stats annotations.
4. Compare only fields the chosen format can actually provide. `plan_tree`
   omits `estRows`; row/brief include estimates; verbose/cost_trace add
   estimated cost; analyze/runtime-stats output adds `actRows`, execution info,
   memory, and disk. Do not infer missing runtime evidence from static output.
5. Treat plan digest as an identity clue, not a quality score. Same digest means
   the normalized physical plan is likely the same; different digest requires a
   field-level explanation before claiming improvement.
6. Compare each plan section independently: main plan, CTEs, scalar subqueries,
   and pushed-down fragments. For each section, check:
   - operator tree, join algorithm, join type, join order, driver/build/probe
     side, join keys, equal conditions, residual conditions, and Cartesian joins;
   - access path: PointGet/BatchPointGet, table/index full scan, table/index
     range scan, IndexReader, IndexLookUp, IndexMerge, covering vs table lookup,
     access object, range bounds, keep order, desc, partition pruning, and pushed
     filters;
   - task placement: root, cop[tikv], batchCop[tiflash], mpp[tiflash], Exchange,
     Sort/TopN/Agg pushdown, and data movement between TiDB, TiKV, and TiFlash;
   - estimates and costs only under the same TiDB version, cost model, stats,
     variables, and explain format;
   - runtime metrics only from production evidence or approved local
     `EXPLAIN ANALYZE`: per-execution latency, actRows, processed/total keys,
     scan rows per returned row, loops, memory, disk spill, and errors.
7. Rank a candidate higher only when the mechanism is explicit and evidence is
   adequate. Strong static signals include simple point plans, narrower range
   scans over full scans, fewer table lookups, fewer processed keys per returned
   row, earlier predicate/TopN/Agg pushdown, better join driver/build side,
   useful ordering that removes Sort, and avoiding unnecessary root/Mpp
   exchanges. Penalize pseudo or partial stats, lookup amplification, Cartesian
   joins, lost partition pruning, forced unsupported hints, wider write/storage
   cost, and high rollback complexity.
8. For `EXPLAIN EXPLORE` output, distinguish historical candidates from newly
   generated candidates. Use `avg_latency`, `exec_times`, scan-row ratios, and
   built-in `recommend` only when their provenance is recorded and `exec_times`
   is nonzero or the run was explicitly analyzed. Otherwise treat them as
   advisory and rank by plan-shape evidence plus required validation.
9. Separate estimated benefit, measured local benefit, production confidence,
   compatibility, write/storage cost, blast radius, and rollback complexity.
   Treat lower estimated cost, lower `estRows`, or a different digest as
   insufficient evidence by itself.
10. Rank candidates and document rejected candidates with reasons. Mark a
   recommendation `validated` only when baseline reproduction and candidate
   validation are both adequate; otherwise mark it `advisory` or `unvalidated`.
11. Save the comparison and selected recommendation under `decision/`.
12. Update manifest recommendation fields, append to `audit.md`, and set
   `current_stage: candidates_compared`.
