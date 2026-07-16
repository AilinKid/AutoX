# AutoX

AutoX is a small Skill repository for TiDB slow SQL analysis.

The first version has one goal:

> Input a TiDB Cloud `cluster_id`, inspect its slow queries, and output
> actionable optimization suggestions.

AutoX is read-only for the target cluster. It does not create production
bindings, change production indexes, modify a cluster, or verify production
outcomes.

## Workflow

```text
cluster_id
  -> resolve cluster, SQL target, and time range
  -> collect Slow Query, TopSQL, runtime plans, schema, and statistics
  -> classify the bottleneck and generate concrete candidates
  -> optionally prepare a local version-matched TiDB and validate plans
  -> output one evidence-backed, review-only recommendation
```

For Dedicated clusters, AutoX collects each involved user table's schema,
existing indexes, and statistics through the Clinic Dashboard debug API when a
direct read-only TiDB status endpoint is unavailable. Data Proxy observability
schema does not satisfy this evidence requirement.

Top-N requests use the batch workflow, but every selected digest still runs the
complete focused workflow and produces its own report.

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
- `input-resolution`: resolve the required `cluster_id` and optional inputs.
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

Required:

- `cluster_id`

Optional:

- inspection time range;
- a specific SQL digest;
- an already prepared local TiDB connection;
- an existing matching TiDB source checkout.

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
