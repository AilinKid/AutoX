# auto-sql-opt

`auto-sql-opt` is an optimizer-integrated diagnosis and remediation system for
TiDB SQL and cluster performance incidents.

The project turns production evidence into reproducible optimizer experiments,
then produces recommendations that are explainable, testable, and guarded by
explicit safety policies. It is not a generic LLM wrapper around dashboards and
slow logs.

## Why this exists

Existing clinic skills provide valuable cloud monitoring, slow-query, TopSQL,
and health-inspection data. The missing layer is the engineering workflow after
data collection:

1. correlate SQL symptoms with cluster and optimizer evidence;
2. reproduce plan selection against the matching TiDB version;
3. generate binding, index, statistics, SQL rewrite, and cluster-level
   candidates;
4. validate candidates with optimizer and workload experiments;
5. rank impact and risk;
6. apply only reversible actions through explicit approval and rollback gates;
7. retain the case as regression data.

## Design principles

- **Evidence before advice**: every finding links to source evidence.
- **Optimizer as an oracle**: recommendations must be checked through TiDB plan
  generation and costing, not only language-model reasoning.
- **Version-aware**: diagnosis records the TiDB version and optimizer settings.
- **Reproducible**: a case bundle should replay offline where data permits.
- **Safe by default**: production mutation is disabled unless a policy,
  approval, verification, and rollback plan all exist.
- **Minimal trust in prose**: structured facts and experiment results drive
  decisions; natural-language reports are views of those facts.

## Initial architecture

```text
clinic / slow log / TopSQL / schema / stats / config
                       |
                       v
               evidence normalization
                       |
                       v
             diagnosis graph + hypotheses
                       |
             +---------+----------+
             | optimizer lab      |
             | plan reproduction   |
             | candidate testing   |
             +---------+----------+
                       |
                       v
       ranked recommendations + safety assessment
                       |
              approval / apply / verify / rollback
```

The first milestone is a read-only diagnosis pipeline. Automated production
changes are intentionally deferred until validation and rollback contracts are
implemented.

## Repository layout

- `cmd/auto-sql-opt`: CLI entrypoint.
- `internal/domain`: stable evidence, finding, recommendation, and safety
  models.
- `internal/engine`: diagnosis orchestration contracts.
- `docs/architecture.md`: component boundaries and integration model.
- `docs/roadmap.md`: delivery milestones and acceptance criteria.

## Quick start

```bash
go test ./...
go run ./cmd/auto-sql-opt doctor
```

The current bootstrap validates the core domain and orchestration contracts.
Clinic and TiDB adapters will be added behind those contracts.

## Non-goals

- replacing Clinic as the monitoring data plane;
- issuing unverified `CREATE INDEX` or `CREATE BINDING` statements;
- treating an LLM's explanation as proof;
- maintaining a forked optimizer outside TiDB.
