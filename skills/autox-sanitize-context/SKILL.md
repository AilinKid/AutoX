---
name: autox-sanitize-context
description: Sanitize and prepare TiDB schema, statistics, bindings, variables, SQL, and cluster context for an AutoX local optimizer replay while preserving plan-relevant semantics. Use when production context must be copied into `.autox/current/input/sanitized/` without exposing customer identifiers or literals.
---

# AutoX Sanitize Context

Read the current case contract from
`../autox-optimize-sql/references/case-contract.md`.

1. Require stage `initialized`.
2. Preserve original artifacts under `input/raw/`; never modify them in place.
3. Replace database, table, column, index, user, tenant, and literal identifiers
   consistently. Keep data types, nullability, index order, expression shape,
   partitioning, histogram structure, TopN frequencies, NDV, correlation, and
   row counts plan-equivalent where possible.
4. Save schema, stats, session/global variables, existing bindings, normalized
   SQL, production plan, and provenance under `input/sanitized/`.
5. Record any semantic loss. If sanitization changes predicates, join
   relationships, selectivity, or partition pruning, mark replay fidelity low.
6. Scan sanitized outputs for known raw identifiers and secrets.
7. Append the mapping policy and fidelity assessment to `audit.md`.
8. Set `current_stage: context_sanitized`.

Do not claim data is safe to share merely because SQL literals were removed.
