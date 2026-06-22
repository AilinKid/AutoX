# AutoX Current Case Contract

## Location

The active serial case is always `.autox/current/`. A stage receives no case
identifier; it discovers the case from this fixed location.

Generate `case_id` once at initialization, using a stable UTC timestamp plus a
sanitized cluster or SQL digest suffix. Keep it unchanged through archive.

## Layout

```text
.autox/current/
├── manifest.yaml
├── input/
│   ├── raw/
│   └── sanitized/
├── baseline/
├── experiments/
├── decision/
├── outcome/
└── audit.md
```

## Manifest fields

```yaml
schema_version: 1
case_id: ""
status: active
current_stage: initialized
created_at: ""
updated_at: ""
target:
  cluster_id: ""
  cluster_name: ""
  tidb_version: ""
  sql_digest: ""
  inspection_window: ""
  baseline_window: ""
reproduction:
  status: pending
  production_plan_digest: ""
  local_plan_digest: ""
recommendation:
  status: pending
  selected_candidate: ""
implementation:
  status: not_started
  approved_by: ""
  applied_at: ""
outcome:
  status: pending
  verdict: ""
```

Allowed stage order:

```text
initialized
-> context_sanitized
-> lab_prepared
-> reproduction_checked
-> candidates_generated
-> candidates_compared
-> decision_recorded
-> archived
```

For an approved implementation, use the longer branch:

```text
decision_recorded
-> implementation_completed
-> outcome_verified
-> archived
```

Use `blocked` status plus an audit entry when a required stage cannot finish.
Do not skip a state silently.

## File rules

- Preserve raw source responses under `input/raw/`.
- Put shareable or local-lab inputs under `input/sanitized/`.
- Save baseline plans and environment checks under `baseline/`.
- Give every candidate a directory under `experiments/`.
- Save recommendation, apply SQL, rollback SQL, and approval under `decision/`.
- Save post-change evidence and verdict under `outcome/`.
- Append every significant action and decision to `audit.md`.
- Use UTC timestamps.
- Never commit `.autox/` or unredacted archived cases.
