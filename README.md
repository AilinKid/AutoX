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
  -> fetch cluster metadata and slow queries
  -> collect relevant schema, statistics, plans, and metrics
  -> explore SQL and TiDB optimizer behavior
  -> compare possible optimizations
  -> output prioritized suggestions
```

The environment is prepared outside AutoX. In local development, the user may
provide a matching TiDB instance and TiDB source checkout. In a future cloud
runtime, the platform should provide those dependencies.

## Skills

- `autox-optimize-sql`: fetch slow queries for a cluster and orchestrate the
  analysis.
- `autox-explore-sql`: inspect optimizer behavior and generate candidates.
- `autox-compare-plans`: compare candidates and produce the final suggestions.

## Input

Required:

- `cluster_id`

Optional:

- inspection time range;
- a specific SQL digest;
- an already prepared local TiDB connection;
- a matching TiDB source checkout.

## Output

For each important slow SQL:

- observed symptoms and evidence;
- likely root cause;
- recommended binding, index, statistics, or SQL rewrite;
- expected benefit and risk;
- confidence and missing evidence;
- SQL snippets for review, without executing them.
