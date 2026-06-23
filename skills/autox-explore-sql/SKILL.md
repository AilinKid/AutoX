---
name: autox-explore-sql
description: Explore a reproduced or advisory TiDB SQL case, trace optimizer behavior in the matching TiDB source, and generate evidence-backed binding, index, statistics, SQL rewrite, configuration, or recovery candidates. Use after baseline reproduction is checked.
---

# AutoX Explore SQL

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `reproduction_checked`.
2. Form explicit hypotheses from slow log, TopSQL, runtime plan, estimates,
   process keys, latency, resource metrics, schema, stats, and bindings.
3. Use the matching TiDB source checkout when exposed plans cannot explain a
   decision. Record exact file paths, symbols, commit or tag, and verified
   behavior; do not infer semantics from unrelated versions.
4. Run no-ANALYZE `EXPLAIN EXPLORE` in the version-matched lab before inventing
   manual hint candidates. Use the supported forms for the target version:
   `EXPLAIN EXPLORE SELECT ...`, `EXPLAIN EXPLORE 'sql text or digest'`, or
   `EXPLAIN EXPLORE REPLAYER 'replayer-file'` when a plan replayer is available.
   Do not run `EXPLAIN EXPLORE ANALYZE` unless the user explicitly approves
   executing candidate SQL.
5. Treat each `EXPLAIN EXPLORE` row as a candidate source, not a proof of
   improvement. Capture `statement`, `binding_hint`, `plan`, `plan_digest`,
   `recommend`, `reason`, `explain_analyze`, and `binding` under
   `experiments/candidate-id/`. Also capture `avg_latency`, `exec_times`,
   scan-row fields, and whether they came from statement history or are zero
   because no ANALYZE was run.
6. Understand what no-ANALYZE exploration can generate in current TiDB: it
   combines historical bindings with generated SELECT-only binding candidates,
   deduped by plan digest. Generated candidates may vary leading table pairs,
   `use_index` hints over existing indexes, `no_decorrelate`, relevant optimizer
   cost/selectivity variables, and supported optimizer fix controls. They do
   not create new indexes, execute generated plans, or prove runtime benefit.
7. If exploration returns only the baseline plan, record that result and then
   continue with separate hypotheses for indexes, statistics, SQL rewrites,
   configuration, or recovery actions. Do not attribute those broader ideas to
   `EXPLAIN EXPLORE` output.
8. Generate distinct candidates for bindings or hints, indexes, statistics,
   SQL rewrites, configuration, or recovery actions.
9. Create `experiments/candidate-id/` with hypothesis, change, expected
   mechanism, risks, validation method, plan output, and result.
10. Reject candidates that only move cost without explaining the mechanism.
11. Record the candidate count, source references, and open questions in
   `audit.md`.
12. Set `current_stage: candidates_generated`.

Return candidates to `$autox-optimize-sql`. Do not apply production changes.
