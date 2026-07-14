# AutoX Workflow Contract

## Purpose

Define the run-local artifact layout, validation vocabulary, and handoff requirements for AutoX
skills and subskills. AutoX does not require pre-existing case state or a persisted state machine.

This file is a contract only. Do not put optimizer rules, index design rules, TiFlash/MPP
decision logic, Clinic API instructions, or final report templates here.

## Case Identity

Every AutoX diagnosis must have:

- `diagnosis_id`: globally unique ID for one diagnosis run.
- `cluster_id`: target TiDB Cloud cluster ID.
- `digest`: target SQL digest when available.
- `sql_text`: original or redacted SQL text when available.
- `tidb_version`: target cluster TiDB version.
- `business_time_range`: user-facing time range with timezone.
- `utc_time_range`: Clinic query time range in UTC.
- `workspace`: per-diagnosis workspace path.

Never reuse a workspace, local TiDB data directory, generated schema, stats file, or port
across different `diagnosis_id` values.

For a batch diagnosis, also require:

- `batch_id`: globally unique ID for the parent batch.
- one unique child `diagnosis_id` per selected digest.
- one isolated child workspace per selected digest.

Batch orchestration may track `queued`, `running`, `completed`, or `failed` in memory or in an
optional run-local manifest.

## Workflow Handoffs

Each subskill consumes the output of the preceding workflow step directly:

- `workflow/input-resolution/SUBSKILL.md` resolves the cluster, SQL target, time range, and
  optional run-local workspace.
- `workflow/evidence-collection/SUBSKILL.md` builds a problem profile only after every involved
  user table has schema and
  statistics collection records. Each record must be `collected` or preserve an exact `failed`
  error; system tables may use `not_applicable`. A missing record is a workflow failure.
- `workflow/diagnosis-classification/SUBSKILL.md` consumes the problem profile and generates any
  concrete ready-for-validation candidates.
- `workflow/local-validation/SUBSKILL.md` consumes and validates those candidates when an
  externally prepared matching environment is available; otherwise it records exact blockers.
- `autox-explore-sql` may run only after baseline reproduction was checked and recorded.
- `autox-compare-plans` requires at least one generated candidate or compared plan set.
- `workflow/final-report/SUBSKILL.md` requires production prior plan collection attempted,
  candidate validation attempted when possible, and exact blockers recorded when validation
  cannot run. It then produces the report and performs run-local artifact cleanup.

No step requires the user to provide a case file, manifest, workflow stage, local TiDB, or source
checkout. A `manifest.json` may be written for run-local audit and handoff, but it is never a
required input to start or continue a diagnosis.

## Artifact Layout

Use this layout under the per-diagnosis workspace:

```text
<workspace>/
  manifest.json                 # optional run-local audit index
  evidence/
    slow_query/
    topsql/
    schema/
    stats/
    plan_history/
  plans/
    production_before/
    local_baseline/
    candidates/
  experiments/
    <candidate_id>/
  decision/
  report/
  cleanup/
```

Raw Clinic, Dashboard, schema, stats, slow-log, and plan artifacts must stay under this
workspace. Do not write raw artifacts into the skill directory or repository root.

## Manifest Shape

An optional run-local `manifest.json` may include these top-level fields when available:

```json
{
  "diagnosis_id": "",
  "cluster": {
    "cluster_id": "",
    "cluster_name": "",
    "tidb_version": "",
    "deployment_type": ""
  },
  "target": {
    "digest": "",
    "sql_text": "",
    "normalized_sql": ""
  },
  "time_range": {
    "business": "",
    "utc": "",
    "timezone": ""
  },
  "evidence": {
    "slow_query": {},
    "topsql": {},
    "schema": { "table_collection": [] },
    "stats": { "table_collection": [] },
    "plan_history": {}
  },
  "evidence_summary": {
    "slow_query_sample_count": 0,
    "plan_variant_count": 0,
    "schema_tables": [],
    "stats_snapshot_time": ""
  },
  "diagnosis": {
    "dominant_bottleneck": "",
    "key_operators": [],
    "root_cause_candidates": [],
    "recommended_direction": ""
  },
  "candidates": [],
  "validation": {},
  "recommendation": {},
  "cleanup": {},
  "redaction": {}
}
```

## Recommendation Vocabulary

Customer-facing `recommended_action` must be one of:

- `Binding first`
- `Index first`
- `TiFlash / MPP first`
- `Investigate non-optimizer bottleneck`
- `No optimizer action`

Do not use internal workflow states as customer-facing recommendations.

Invalid customer-facing recommendations:

- `Plan explore candidate first`
- `Fix statistics first`
- `More evidence is required`
- `No safe recommendation`

Use `No optimizer action` when cloud-side evidence does not support an actionable optimizer
change, including cases where the available evidence cannot justify Binding, Index, TiFlash/MPP,
or statistics work.

## Supporting Actions

Supporting actions may appear in report caveats or next validation fields, but they must not
replace `recommended_action`.

Allowed examples:

- `Refresh statistics`
- `Validate statistics health`
- `Run production-safe EXPLAIN`
- `Validate binding in local or staging environment`
- `Check TiKV MVCC / compaction / coprocessor latency`
- `Check lock / backoff / transaction contention`

## Internal Workflow States

Ephemeral internal workflow progress may be recorded separately from the customer-facing
recommendation, but no subskill may require persisted state to run.

Allowed `internal_step` examples:

- `plan_explore`
- `local_validation`
- `compare_candidates`
- `collection_failed`
- `evidence_gap_recorded`

These values are for orchestration and audit only.

## Validation Vocabulary

Use these validation levels consistently:

- `inferred`: no candidate plan was reproduced; recommendation follows from evidence and
  optimizer reasoning.
- `plan_verified`: local or production-safe static `EXPLAIN` shows the intended plan shape.
- `prod_verified`: production read-only observation or approved production validation confirms
  the intended improvement.

Validation status examples:

- `locally verified by EXPLAIN`
- `plan already recovered`
- `locally explored by EXPLAIN EXPLORE`
- `production verified`
- `rejected`
- `inferred`
- `not run`

Rules:

- Local static `EXPLAIN` can prove plan shape only. It does not prove runtime improvement.
- Do not mark a candidate `prod_verified` without production runtime or approved production
  validation evidence.
- If matching TiDB version, schema, and stats are available, local validation is mandatory
  before final report.
- If validation cannot run, record the exact blocker.
- `plan already recovered` means the full-SQL local baseline naturally selects the expected plan
  shape before any candidate operation. Use `plan_verified`; final reporting should normally use
  `No optimizer action` unless current production evidence still shows the bad plan active.

Every optimizer candidate validation result must answer:

- `syntax_accepted`: TiDB accepts the candidate syntax.
- `optimizer_selected_expected_path`: the optimizer selects the expected access path, join, or
  engine after applying the candidate locally.
- `plan_shape_matches_diagnosis`: the selected plan shape addresses the diagnosed mechanism.

All three values must be `true` before concrete candidate SQL may appear in the final
`Review-only SQL` field. An inferred direction may still be explained, but its unverified SQL must
not be printed as a rollout candidate.

`Index first` requires a concrete index candidate whose DDL passed this gate. It must not appear
with `Review-only SQL: none`. Missing schema, an unchecked existing-index set, or an absent
candidate is an incomplete workflow, not an inferred Index recommendation.

## Handoff Requirements

`workflow/diagnosis-classification/SUBSKILL.md` must output:

- `dominant_bottleneck`
- `key_operators`
- `key_metrics`
- `root_cause_candidates`
- `recommended_direction`
- concrete `candidates` when the recommendation requires validation.

Candidate records must be ready for validation. Local validation must not invent new candidates.

Common candidate fields:

- `id`
- `type`: `binding`, `index`, `tiflash_mpp`, `non_optimizer`, or `no_action`
- `status`: `ready_for_validation`, `not_applicable`, or `no_action`
- `review_only_sql`
- `mechanism`
- `evidence_paths`
- `expected_plan_change`
- `validation_steps`
- `candidate_artifact_path`

Keep candidate-specific detail such as existing-index checks, hinted SQL, hypothetical-index SQL,
hypothetical TiFlash SQL, expected per-alias shape, and risk notes in the candidate artifact. The
manifest should point to that artifact instead of copying all details.

`workflow/local-validation/SUBSKILL.md` must output:

- validation status;
- validation level;
- three validation booleans;
- baseline plan path;
- candidate plan path;
- one concise comparison summary;
- comparison artifact path;
- exact blocker when validation cannot run.

`workflow/final-report/SUBSKILL.md` must:

- use only the contracted recommendation vocabulary;
- read complete plan, candidate, and comparison artifacts by path instead of expecting them to be
  copied into the compact manifest;
- output the selected candidate ID, validation status, validation level, and report path;
- keep concrete review-only SQL out of the report unless all three validation booleans are true;
- retain only the redacted final report after cleanup unless the user explicitly requested raw
  artifact retention. If an optional run-local manifest was used, retain its compact redacted form
  with diagnosis and cluster identity, digest, business/UTC time range and timezone, evidence
  summary, recommendation, cleanup, and redaction state.

Final recommendation handoff should remain compact. When an optional manifest is used, the
following object is a partial update merged into it; it is not a replacement for the complete
retained manifest:

```json
{
  "recommendation": {
    "recommended_action": "",
    "selected_candidate_id": "",
    "validation_status": "",
    "validation_level": "",
    "report_path": ""
  },
  "cleanup": {
    "raw_artifacts_cleaned": true,
    "retained_at_user_request": false,
    "leftover_paths": []
  }
}
```

After cleanup, an optional retained compact manifest must still include:

```json
{
  "diagnosis_id": "",
  "cluster": {
    "cluster_id": "",
    "cluster_name": "",
    "tidb_version": "",
    "deployment_type": ""
  },
  "target": { "digest": "" },
  "time_range": { "business": "", "utc": "", "timezone": "" },
  "evidence_summary": {
    "slow_query_sample_count": 0,
    "plan_variant_count": 0,
    "schema_tables": [],
    "stats_snapshot_time": ""
  },
  "recommendation": {},
  "cleanup": {},
  "redaction": {}
}
```

## Batch Contract

`workflow/batch-diagnosis/SUBSKILL.md` owns only parent ranking, dispatch, concurrency,
completion checks, resume state, and aggregate summary.

When subagents are available:

- dispatch exactly one digest to each subagent;
- explicitly instruct every subagent to use the complete `$autox-optimize-sql` skill;
- require every subagent to run input resolution, evidence collection, diagnosis and candidate
  generation, local validation when available, final report, and cleanup;
- never place multiple digests in one subagent task;
- reject and rerun child output that skipped a required stage or failed a focused completion gate.

The parent must not diagnose a child digest, invent its candidates, or rewrite its recommendation.
The aggregate summary references focused report paths and does not copy full SQL, plans, or
candidate details.

Keep the batch manifest compact. Each child record should contain only:

- rank and digest;
- diagnosis ID;
- orchestration status;
- recommended action and validation level when completed;
- focused report path;
- failed stage and concise blocker when failed.

If subagents are unavailable, record a sequential fallback and run each digest under the same
complete focused workflow. This fallback does not permit skipped stages.

## Safety Rules

AutoX is read-only for the target cluster.

Use a least-privilege, read-only Clinic credential. If the available credential is broader than
read-only, AutoX must still call only read endpoints and must never use its mutation capability.
Keep debug logging disabled by default. Never log credentials, authorization headers, signed URLs,
database passwords, tokens, or unredacted secret-bearing responses.

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

Local-only DDL is allowed only inside the isolated local TiDB validation environment.
