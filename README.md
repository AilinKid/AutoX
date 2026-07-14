# AutoX

AutoX is a small Skill repository for TiDB slow SQL analysis.

The first version has one goal:

> Input a TiDB Cloud `cluster_id`, inspect its slow queries, and output
> actionable optimization suggestions.

AutoX is read-only. It does not create bindings, change indexes, modify a
cluster, prepare a local TiDB environment, or verify production outcomes.

## Workflow

```text
cluster_id
  -> resolve cluster, SQL target, and time range
  -> collect Slow Query, TopSQL, runtime plans, schema, and statistics
  -> classify the bottleneck and generate concrete candidates
  -> optionally validate plans on an externally prepared, version-matched TiDB
  -> output one evidence-backed, review-only recommendation
```

For Dedicated clusters, AutoX collects each involved user table's schema,
existing indexes, and statistics through the Clinic Dashboard debug API when a
direct read-only TiDB status endpoint is unavailable. Data Proxy observability
schema does not satisfy this evidence requirement.

Top-N requests use the batch workflow, but every selected digest still runs the
complete focused workflow and produces its own report.

The environment is prepared outside AutoX. In local development, the user may
provide a matching TiDB instance and TiDB source checkout. In a future cloud
runtime, the platform should provide those dependencies.

## Skills and workflows

- `autox-optimize-sql`: read-only entry Skill and workflow router.
- `autox-optimize-sql/SUBSKILLS_INDEX.md`: subskill catalog and loading rules.
- `input-resolution`: resolve the required `cluster_id` and optional inputs.
- `evidence-collection`: collect Clinic evidence, including user-table schema
  and statistics.
- `diagnosis-classification`: identify the dominant mechanism and generate
  ready-for-validation candidates.
- `local-validation`: validate full-SQL plan shape only when an isolated,
  externally prepared matching environment is available.
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
- a matching TiDB source checkout.

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

## Evaluation records

Use [docs/iteration-records.md](docs/iteration-records.md) to record each
AutoX SQL digest evaluation, including inputs, observed evidence, inference,
validation results, recommendation quality, missing evidence, and follow-up
decisions.
