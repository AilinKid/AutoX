# Architecture

## Boundary

`auto-sql-opt` owns the decision workflow between observability data and a
safe, verified optimization action. Clinic remains the production data plane;
TiDB remains the source of truth for optimizer semantics.

The system does not treat free-form analysis as a durable interface. Each
stage exchanges structured artifacts.

## Core pipeline

### 1. Evidence adapters

Adapters collect and normalize:

- Clinic metrics, slow query, and TopSQL;
- SQL text, digest, execution details, and runtime plans;
- schema, indexes, statistics health, and optimizer variables;
- bindings and plan-cache state;
- cluster topology, resource pressure, and incident timeline;
- TiDB source references for version-specific behavior.

Raw payloads should be retained alongside normalized evidence for audit and
replay.

### 2. Diagnosis graph

The diagnosis graph connects symptoms, hypotheses, evidence, and disproof.
Examples:

- high latency -> high processed keys -> table scan -> missing/selectivity-poor
  index;
- plan regression -> stats change or version change -> cardinality error ->
  join-order change;
- TiKV hotspot -> concentrated key range -> SQL digest -> access-path choice;
- compile pressure -> non-prepared workload or plan-cache miss reason.

A finding is publishable only when its evidence references are complete and
its confidence is explicit.

### 3. Optimizer lab

The optimizer lab is the project's technical center. It should support:

- a TiDB binary or checkout matching the production version;
- schema, statistics, session variables, bindings, and representative SQL
  replay;
- `EXPLAIN`, optimizer trace, and plan-cost comparison;
- controlled candidate bindings and hypothetical index experiments;
- source-level lookup when behavior cannot be explained from exposed plans.

The lab must not maintain a second optimizer implementation. It drives and
observes TiDB's optimizer.

### 4. Candidate generators

Candidate generators may produce:

- plan bindings or hints;
- index additions, removals, or ordering changes;
- statistics refresh or configuration changes;
- SQL rewrites;
- workload or cluster recovery actions.

Generators can use heuristics or models, but output is only a candidate until
validated.

### 5. Validation and ranking

Validation compares a baseline with candidates using:

- plan shape and estimated cost;
- cardinality estimation error;
- runtime samples where safe;
- expected write/storage overhead for indexes;
- compatibility with the target TiDB version;
- blast radius, reversibility, and rollback time.

Ranking must separate expected impact from confidence and operational risk.

### 6. Action safety

The default mode is read-only. Mutation requires:

1. a validated recommendation;
2. an allowlisted action type;
3. explicit approval;
4. precondition checks;
5. a rollback statement or procedure;
6. post-action verification;
7. automatic rollback criteria.

Binding automation should be delivered before index automation because
bindings are generally faster to apply and reverse. Index automation must also
model DDL duration, write amplification, storage, and schema-change risk.

## Integration with nutshell-skills

The optimizer inspection skill in `tidbcloud/nutshell-skills#150` is an
upstream evidence producer. Its strengths are cluster enumeration, metric
collection, baseline comparison, slow-query aggregation, and known Clinic data
pitfalls.

The integration contract should move toward a machine-readable case bundle
rather than parsing its Markdown report:

```text
inspection window + cluster metadata + raw query references
  + normalized metrics + slow SQL groups + TopSQL groups + collection errors
```

The skill can then call `auto-sql-opt diagnose` for deeper SQL-specific
analysis, while this repository remains independently testable.

## Case bundle

A case bundle should eventually contain:

```text
manifest.json
evidence/
schema/
statistics/
plans/
experiments/
recommendations.json
report.md
```

Sensitive SQL literals and customer identifiers must be redacted before a case
is committed or shared.
