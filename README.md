# AutoX

AutoX is a small Skill repository for TiDB slow SQL analysis.

The first version has one goal:

> Inspect a focused TiDB Cloud target or use the zero-input Dedicated-fleet
> default, then output actionable slow-SQL optimization suggestions.

AutoX is read-only for the target cluster. It does not create production
bindings, change production indexes, modify a cluster, or verify production
outcomes.

AutoX v0 diagnoses read-only `SELECT` statements only. Automatic ranking
excludes write DML, transaction control, DDL, administrative statements, and
locking `SELECT ... FOR UPDATE`.

## Workflow

```text
no explicit input
  -> discover all accessible active Dedicated clusters
  -> select the global top 10 slow-query digests from the rolling last 24 hours

focused input (for example, cluster_id or SQL digest)
  -> resolve cluster, SQL target, and time range

selected cluster_id + SQL digest
  -> collect Slow Query, TopSQL, runtime plans, schema, and statistics
  -> classify the bottleneck and generate concrete candidates
  -> optionally prepare a local version-matched TiDB and validate plans
  -> output one evidence-backed, review-only recommendation
```

For Dedicated clusters, AutoX collects each involved user table's schema,
existing indexes, and statistics through the Clinic Dashboard debug API when a
direct read-only TiDB status endpoint is unavailable. Data Proxy observability
schema does not satisfy this evidence requirement.

Top-N requests and the zero-input default use the batch workflow, but every
selected digest still resolves an exact `cluster_id`, runs the complete focused
workflow, and produces its own report.

When local validation is needed, AutoX first looks for an existing local
`pingcap/tidb` source checkout. If none is available, it may clone one under the
local AutoX work area, create a per-diagnosis `git worktree`, check out the
target cluster version, build TiDB with `make`, and start an isolated standalone
TiDB for schema/stat replay and static `EXPLAIN`.

When optimizer behavior, SQL syntax, hints, statistics, TiFlash, or operational semantics need
documentation, AutoX may consult `pingcap/docs` or the TiDB official website. Treat those sources
as version-sensitive references and record the exact page, branch, or URL used.

## Skills and workflows

- `autox-optimize-sql`: read-only entry Skill and workflow router.
- `autox-optimize-sql/SUBSKILLS_INDEX.md`: subskill catalog and loading rules.
- `input-resolution`: resolve a focused target or the zero-input fleet defaults.
- `evidence-collection`: collect Clinic evidence, including user-table schema
  and statistics.
- `diagnosis-classification`: identify the dominant mechanism and generate
  ready-for-validation candidates.
- `local-validation`: prepare or reuse an isolated, version-matched local TiDB
  and validate full-SQL plan shape.
- `final-report`: produce the customer-facing recommendation and evidence.
- `batch-diagnosis`: orchestrate top-N analysis without skipping per-digest
  workflow steps.

`autox-explore-sql` and `autox-compare-plans` are internal helpers for plan
exploration and normalized candidate comparison. They are not customer-facing
recommendation types.

## Input

No input is required for a generic cluster-diagnosis request. By default, AutoX:

- discovers every accessible active Dedicated cluster;
- uses the rolling last 24 hours;
- ranks `(cluster_id, SQL digest)` candidates globally by total slow-query
  latency; and
- runs the complete workflow for the global top 10 candidates, treating 10 as
  a cap when fewer candidates exist.

Each selected diagnosis still has an exact `cluster_id` and SQL digest.

Optional focused inputs and overrides:

- `cluster_id` or another explicit cluster scope;
- inspection time range;
- a specific SQL digest;
- slow SQL text;
- top-N or ranking instructions;
- an already prepared local TiDB connection;
- an existing matching TiDB source checkout.

An explicit value overrides only the corresponding default. For example, an
explicit `cluster_id` limits the scope to that cluster while retaining the
24-hour and top-10 defaults when those values are omitted.

## Output

Each focused diagnosis returns exactly one primary action:

- `Binding first`;
- `Index first`;
- `TiFlash / MPP first`;
- `Investigate non-optimizer bottleneck`;
- `No optimizer action`.

The report includes:

- observed symptoms and evidence;
- inference separated from observed facts;
- the dominant root cause and concrete operators;
- production plan-before evidence and local plan-after evidence when available;
- expected benefit and risk;
- confidence and missing evidence;
- concrete review-only SQL only after syntax and plan-shape validation.

## Report demo

The demo below uses synthetic cluster names and metrics. Heading levels are
lowered only to fit this README; generated report artifacts use the canonical heading levels and
paths defined by the Skill. The `Report` column is illustrative here; generated batch artifacts
link every row to its own focused report.

> ### AutoX Slow SQL Batch Report
> #### Batch
> - Status: `completed`
> - Scope: global Top 10 across all accessible active Dedicated clusters
> - Progress: `10/10`
> - Time range: `2026-07-21 16:00:00 ~ 2026-07-22 16:00:00 Asia/Shanghai`
> - Ranking: cluster ID + SQL digest, ordered by aggregate slow-query latency
> - Coverage: `8/8` active Dedicated clusters ranked successfully; 2 returned no eligible slow `SELECT` statements
> - Safety: `Production read-only; no binding, index, configuration, or DDL changes were applied.`
> 
> #### Summary
> 
> - Impact: 49,180 slow executions; 138.3 aggregate slow-query hours; Top 10 account for 73.1%
> - Actions: Binding first=2, Index first=3, Investigate non-optimizer bottleneck=3, No optimizer action=2
> - Validation levels: inferred=1, observed=4, plan_verified=5
> 
> #### Cases
> 
> | Rank | Cluster | Impact | Action | Validation | Report |
> |---:|---|---:|---|---|---|
> | 1 | demo-orders-a | 42.8h / 12,840 exec | Index first | plan_verified | report |
> | 2 | demo-payments-b | 31.4h / 8,520 exec | Investigate non-optimizer bottleneck | observed | report |
> | 3 | demo-analytics-a | 18.6h / 740 exec | Binding first | plan_verified | report |
> | 4 | demo-orders-a | 12.1h / 4,920 exec | No optimizer action | observed | report |
> | 5 | demo-catalog-b | 8.7h / 2,310 exec | Index first | inferred | report |
> | 6 | demo-payments-b | 7.9h / 6,080 exec | Investigate non-optimizer bottleneck | observed | report |
> | 7 | demo-search-a | 5.5h / 1,950 exec | Binding first | plan_verified | report |
> | 8 | demo-ledger-a | 4.8h / 1,240 exec | No optimizer action | plan_verified | report |
> | 9 | demo-events-b | 3.6h / 9,820 exec | Investigate non-optimizer bottleneck | observed | report |
> | 10 | demo-profile-a | 2.9h / 760 exec | Index first | plan_verified | report |
