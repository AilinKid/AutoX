# Roadmap

## Milestone 0: contracts and replay format

- define evidence, finding, recommendation, validation, and safety schemas;
- define the case-bundle format and redaction policy;
- add deterministic unit tests and example cases;
- define version compatibility and provenance fields.

Exit criteria: a captured case can be loaded, validated, and rendered without
calling an LLM.

## Milestone 1: read-only SQL diagnosis

- Clinic adapter for slow query, TopSQL, metrics, and collection errors;
- TiDB adapter for schema, statistics, variables, bindings, and plans;
- diagnosis rules for scan amplification, cardinality error, plan regression,
  hotspot correlation, and resource bottlenecks;
- evidence-linked reports.

Exit criteria: known historical incidents are diagnosed with measurable
precision and no production mutation.

## Milestone 2: optimizer lab

- launch or connect to a TiDB version matching the target cluster;
- restore minimal schema/statistics/session context;
- reproduce baseline plans;
- compare binding, hint, rewrite, and hypothetical-index candidates;
- retain experiment artifacts for regression testing.

Exit criteria: recommendations include reproducible baseline and candidate
results.

## Milestone 3: binding recommendation and guarded automation

- generate binding candidates;
- score plan stability and blast radius;
- preview SQL and rollback SQL;
- require approval for apply;
- verify production impact and rollback automatically on configured failure.

Exit criteria: a binding can complete preview -> approval -> apply -> verify ->
rollback in a test environment.

## Milestone 4: index recommendation

- workload-aware index generation and deduplication;
- selectivity and cardinality validation;
- write, storage, and DDL-cost modeling;
- redundant-index detection;
- test-environment execution and workload comparison.

Exit criteria: index recommendations beat the baseline on replay while staying
inside configured operational budgets.

## Milestone 5: incident recovery and continuous learning

- correlate cluster bottlenecks with SQL causes;
- encode safe recovery runbooks;
- convert completed incidents into redacted replay cases;
- track recommendation acceptance, impact, rollback, and false positives;
- maintain versioned evaluation suites tied to TiDB optimizer changes.

Exit criteria: every automated action has an auditable decision path and every
incident can improve the regression corpus.
