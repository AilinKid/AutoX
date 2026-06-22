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
4. Generate distinct candidates for bindings or hints, indexes, statistics,
   SQL rewrites, configuration, or recovery actions.
5. Create `experiments/<candidate-id>/` with hypothesis, change, expected
   mechanism, risks, validation method, plan output, and result.
6. Reject candidates that only move cost without explaining the mechanism.
7. Record the candidate count, source references, and open questions in
   `audit.md`.
8. Set `current_stage: candidates_generated`.

Do not apply production changes in this Skill.
