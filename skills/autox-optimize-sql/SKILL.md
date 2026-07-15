---
name: autox-optimize-sql
description: Diagnose slow SQL in a TiDB Cloud cluster and produce evidence-backed execution recommendations such as Binding, Index, TiFlash/MPP, non-optimizer investigation, or no optimizer action. Use when the user provides a cluster_id, optionally with a SQL digest, slow SQL text, or time range, and asks for slow-query diagnosis, execution-plan analysis, binding suggestions, index recommendations, or automatic cluster slow-SQL triage. Query cluster metadata, Slow Query, TopSQL, schema, and statistics through the clinic-api skill. This skill is read-only for the target cluster and must not execute bindings, create indexes, or modify production.
---

# AutoX Slow SQL Optimization

AutoX diagnoses TiDB Cloud slow SQL and returns one customer-facing recommendation:

- `Binding first`
- `Index first`
- `TiFlash / MPP first`
- `Investigate non-optimizer bottleneck`
- `No optimizer action`

Do not expose internal workflow states such as plan explore, local validation, evidence gaps,
or candidate comparison as the final recommended action.

## Safety Boundary

AutoX is read-only for the target cluster.

Never:

- create or drop production bindings;
- create or drop production indexes;
- execute production DDL;
- change production statistics;
- change production variables;
- apply TiFlash replica changes in production;
- execute generated SQL from `EXPLAIN EXPLORE`.

Generated SQL is review-only. AutoX never executes production SQL that creates or drops
bindings, indexes, statistics, TiFlash replicas, variables, or other cluster state.

Local-only DDL is allowed only inside an isolated local TiDB validation environment.

## Required First Reads

Before doing task work, read:

1. `SUBSKILLS_INDEX.md`
2. `references/case-contract.md`

Use `SUBSKILLS_INDEX.md` to choose the minimum required workflow subskills.

## Dependencies

Use the `$clinic-api` skill for read-only cluster metadata, Slow Query, TopSQL, schema,
statistics, metrics, and diagnostic files.

Do not copy Clinic authentication, API implementation, or endpoint details into AutoX.
Use the scripts and client supplied by `clinic-api` or the bundled AutoX collection scripts.

## Cloud Evidence Gate

The Clinic Data Proxy schema describes observability tables such as `slow_query_logs` and
`topsql`; it is not user-table schema and does not prove which indexes exist.

After Slow Query identifies the involved user tables:

- use direct read-only TiDB status HTTP when the user supplied a reachable endpoint;
- otherwise, for a Dedicated cluster, run
  `scripts/collect_dashboard_debug_api_table.py` once for every involved user table to collect
  schema, existing indexes, and statistics through the Clinic Dashboard debug API;
- record `collected`, exact `failed` error, or `not_applicable` for schema and stats per table.

Do not continue to `problem_profile_built` while an involved user table has no collection record.
Running only `collect_slow_sql.py` does not satisfy this gate.

## Operating Model

For every diagnosis:

1. Generate a globally unique `diagnosis_id`.
2. Create a per-diagnosis workspace.
3. Resolve input, cluster, SQL digest, and time range.
4. Collect evidence from Cloud-side sources.
5. Build a problem profile.
6. Classify the root cause.
7. Generate ready-for-validation candidates when the diagnosis supports an optimizer action.
8. Validate candidates locally when matching TiDB version, schema, and stats are available.
9. Produce the final report.
10. Clean up raw temporary artifacts, or report the retained path if cleanup fails.

Prefer this workspace layout:

```text
${AUTOX_WORKDIR:-${TMPDIR:-/tmp}/autox/<diagnosis_id>}
```

Never reuse local TiDB data directories, ports, generated schema, stats files, or report
workspaces across different diagnosis IDs.

## Workflow Routing

Follow this order for a focused digest or SQL:

1. `workflow/input-resolution/SUBSKILL.md`
2. `workflow/evidence-collection/SUBSKILL.md`
3. `workflow/diagnosis-classification/SUBSKILL.md`
4. `workflow/local-validation/SUBSKILL.md`
5. `workflow/final-report/SUBSKILL.md`

For top-N or batch diagnosis, read `workflow/batch-diagnosis/SUBSKILL.md` first. The batch
subskill must still run the full focused workflow for each selected digest.

## Diagnosis Loading Rule

After `problem_profile_built`, read `workflow/diagnosis-classification/SUBSKILL.md`.
Root-cause classes such as `scan_amplification`, `wrong_access_path`, and
`non_optimizer_bottleneck` are labels inside that workflow, not separate subskills.

## Candidate Routing

`workflow/diagnosis-classification/SUBSKILL.md` owns candidate design. It must generate concrete
ready-for-validation candidates from full evidence before local validation starts.

General routing:

- Known better historical plan, plan regression, join/order/access path stabilizable by hints
  -> generate Binding or hinted-SQL candidate.
- Missing or ineffective access path with clear scan reduction mechanism
  -> check existing indexes and generate Index candidate DDL plus hypothetical-index SQL.
- Large read volume, weak selectivity, mixed-engine issue, or MPP-suitable shape
  -> generate TiFlash / MPP candidate with target aliases, hints, and hypothetical TiFlash SQL.
- Evidence points outside optimizer behavior
  -> generate no optimizer candidate and recommend `Investigate non-optimizer bottleneck`.
- Cloud-side evidence does not justify an optimizer action
  -> generate no optimizer candidate and recommend `No optimizer action`.

Do not set `Index first` unless schema was collected, existing indexes were checked, and a
concrete Index candidate is ready for validation. When local validation is unavailable, an Index
candidate may still become an inferred `Index first` recommendation only after it passes the
evidence-backed Index advisory gate in `references/case-contract.md`.

`autox-explore-sql` is an internal fallback after local reproduction is checked. It is not a
customer-facing recommendation.

`autox-compare-plans` is used by validation or final decision work when multiple candidate plans
need normalized comparison.

## Validation Gate

If the matching TiDB version, schema, and statistics are available, local validation is mandatory
before presenting an optimizer recommendation as plan-verified.

Local validation must use the full production SQL shape. Do not simplify joins, predicates,
subqueries, UNION arms, or parameter structure and then claim the result validates the original SQL.

If validation cannot run, record the exact blocker. Do not ask the customer for more evidence
when Cloud-side evidence was available to AutoX. Missing externally prepared local TiDB keeps the
validation level at `inferred`; it does not by itself demote an Index candidate. Use `No optimizer
action` or `Investigate non-optimizer bottleneck` only when the collected evidence and applicable
advisory gate do not justify an optimizer action.

## Final Report

The final report is owned by `workflow/final-report/SUBSKILL.md`.
Write it to the canonical artifact path `report/report.md`; do not choose another filename.

The report must include:

- `## Conclusion`
- `## Plans Before & After`
- `## Analysis`

Do not add extra top-level headings.

Keep `Conclusion` compact. Every action includes `Action` and a short diagnostic `Why`.
Plan-changing actions also include one-line `Plan before` and `Plan after` summaries. Do not put
SQL, provenance, validation metadata, diagnosis metadata, cluster metadata, cleanup state, or
evidence lists in `Conclusion`.

`Plan before` must use production runtime evidence when available, preferably the slow-log
`decoded_plan`.

`Plan after` must use complete local `EXPLAIN FORMAT='verbose'` output when local validation
was run.

Do not claim runtime improvement from local static `EXPLAIN` alone.
