---
name: autox-explore-sql
description: Explore a reproduced or advisory TiDB SQL case, trace optimizer behavior in the matching TiDB source, and generate evidence-backed binding, index, statistics, SQL rewrite, configuration, or recovery candidates. Use after baseline reproduction is checked.
---

# AutoX Explore SQL

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require a reproduced or advisory TiDB SQL case with the minimum
   optimizer context needed for plan-space search:
   - bare SQL text;
   - TiDB version;
   - schema;
   - statistics.
2. Plan exploration must use bare SQL. Remove all SQL hints from the statement
   before exploration. Do not load, create, or apply SQL bindings before
   exploration. If a replayer or workspace carries active bindings or forced
   hints, disable or ignore them; if that is impossible, report the replayer as
   unsuitable for bare-SQL exploration.
3. Use the matching TiDB source checkout only when exposed plans cannot explain
   a decision. Record exact file paths, symbols, commit or tag, and verified
   behavior; do not infer semantics from unrelated versions.
   When documentation is needed to confirm target-version syntax or behavior,
   consult `pingcap/docs` or the TiDB official website and record the exact
   branch, page, or URL used.
4. Run no-ANALYZE `EXPLAIN EXPLORE` in the version-matched lab before inventing
   manual hint candidates. Use the supported forms for the target version:
   `EXPLAIN EXPLORE <bare_sql>` or `EXPLAIN EXPLORE '<bare_sql_text>'`. Use
   `EXPLAIN EXPLORE REPLAYER '<replayer-file>'` only when the replayer
   represents the same bare-SQL context and does not carry active bindings or
   forced hints.
5. Do not run `EXPLAIN EXPLORE ANALYZE` unless local data has intentionally been
   loaded and the user explicitly approves executing candidate SQL.
6. Treat each `EXPLAIN EXPLORE` row as a candidate source, not proof of runtime
   improvement. Capture `statement`, `binding_hint`, `plan`, `plan_digest`,
   `recommend`, `reason`, `explain_analyze`, and `binding` under
   `experiments/candidate-id/`. Also capture `avg_latency`, `exec_times`,
   scan-row fields, and whether they came from statement history or are zero
   because no ANALYZE was run.
7. Understand that no-ANALYZE exploration searches candidate plan shapes under
   the bare-SQL optimizer context. Generated hints or Binding SQL from
   `EXPLAIN EXPLORE` are review-only outputs. Do not execute generated
   `EXPLAIN ANALYZE` statements or `CREATE GLOBAL BINDING` statements.
8. Evaluate each explored candidate by mechanism: access path, join order, join
   algorithm, order-preserving path, TiKV/TiFlash path, estimated cost, and
   whether it addresses the diagnosed bottleneck.
9. If exploration returns only the baseline plan, record that result and then
   continue with separate hypotheses for indexes, statistics, SQL rewrites,
   TiFlash/MPP validation, configuration, or recovery actions. Do not attribute
   those broader ideas to `EXPLAIN EXPLORE` output unless the explored plan
   directly supports them.
10. Reject candidates that only move cost without explaining the mechanism.
11. Record the candidate count, source references, and open questions in
    `audit.md`.
12. Return the generated candidates, evidence references, and open questions to
    `$autox-optimize-sql`.

Do not apply production changes.
