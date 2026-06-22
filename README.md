# AutoX

AutoX is a Skill-first repository for audited TiDB SQL diagnosis, optimizer
reproduction, recommendation, implementation, and outcome verification.

The repository deliberately does not implement a second optimizer or a
standalone diagnosis service. Skills drive Clinic, local version-matched TiDB,
TiDB source exploration, SQL experiments, and production verification.

## Workflow

```text
collect and sanitize context
  -> prepare matching local TiDB
  -> reproduce the production plan
  -> explore optimizer behavior
  -> compare candidates
  -> recommend and approve
  -> apply reversible change
  -> verify outcome or roll back
  -> archive audit record
```

The workflow is serial. All Skills read and update `.autox/current/`; callers
do not pass a case identifier between stages. A `case_id` is generated once
when the case starts and retained only for audit, recovery, and archive
identity.

## Skills

- `autox-optimize-sql`: orchestrate the complete serial workflow.
- `autox-sanitize-context`: sanitize schema, statistics, and cluster context.
- `autox-prepare-lab`: prepare a TiDB environment matching production.
- `autox-verify-reproduction`: prove whether the production plan is reproduced.
- `autox-explore-sql`: inspect optimizer behavior and generate candidates.
- `autox-compare-plans`: normalize and compare baseline and candidate plans.
- `autox-apply-binding`: prepare, approve, apply, verify, and roll back bindings.
- `autox-verify-outcome`: measure implementation impact.
- `autox-audit-optimization`: maintain and archive the file-based audit trail.

## Local case data

Case data is sensitive and ignored by Git:

```text
.autox/current/
├── manifest.yaml
├── input/
├── baseline/
├── experiments/
├── decision/
├── outcome/
└── audit.md
```

Completed cases may be copied to `cases/<case_id>/`; `cases/` is also ignored
except for its placeholder. Redact customer identifiers and SQL literals before
sharing any case.

## Safety boundary

Failure to reproduce the production plan blocks claims of validated
optimization. Production mutation requires explicit approval, precondition
checks, rollback SQL, and post-change verification.
