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
- `scope_mode`: `single_cluster` or `dedicated_fleet`.
- one unique child `diagnosis_id` per selected `(cluster_id, digest)` target.
- one isolated child workspace per selected digest.

Generic cluster-diagnosis requests use `dedicated_fleet`, a rolling 24-hour window, and a global
top-10 cap unless the user overrides the corresponding value. Fleet discovery must enumerate all
accessible active Dedicated clusters before ranking. Every focused child still requires an exact
`cluster_id`.

AutoX v0 selects read-only `SELECT` statements only. Automatic ranking must exclude write DML,
transaction control, DDL, administrative statements, and locking `SELECT ... FOR UPDATE`. An
explicit ineligible target stops before diagnosis with an unsupported-statement result; it must not
produce an optimizer recommendation.

When the default cap finds fewer than 10 candidates, `requested_top_n` and `effective_top_n` equal
the available selected count; retain `top_n_source: default` and `top_n_cap: 10`. Do not create
placeholder cases to reach the cap.

Batch orchestration may track child states `queued`, `running`, `retry_pending`, `completed`,
`failed`, or `excluded_by_user` in memory or in an optional run-local manifest. Track the batch
itself as `running`, `paused`, `completed`, or `incomplete`.

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
- `workflow/local-validation/SUBSKILL.md` prepares or reuses a version-matched local TiDB
  environment, consumes candidate artifacts, and validates candidates; if preparation or validation
  cannot run, it records exact blockers.
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
    report.md                    # canonical customer-facing report
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
- `observed`: production runtime evidence directly supports the diagnosis, but no candidate plan
  was reproduced. It does not mean an optimization was executed or verified in production.
- `plan_verified`: a target-version local standalone TiDB reproduced the intended plan shape from
  the full SQL after loading the required schema and statistics.

A historical production plan or production-safe static `EXPLAIN` does not count as local plan
verification. AutoX is read-only and currently has no production-verification level.

Validation status examples:

- `locally verified by EXPLAIN`
- `plan already recovered`
- `locally explored by EXPLAIN EXPLORE`
- `observed in production runtime evidence`
- `rejected`
- `inferred`
- `not run`

Rules:

- Local static `EXPLAIN` can prove plan shape only. It does not prove runtime improvement.
- Do not mark a result `plan_verified` without a target-version local TiDB, full SQL, loaded schema
  and stats, a complete baseline `EXPLAIN FORMAT='verbose'`, and all three plan-validation booleans
  set to `true`. Plan-changing actions also require a complete candidate plan. A naturally
  recovered baseline instead records `reproduction_kind: baseline_recovered`.
- Mark a result `observed` only when retained production runtime evidence directly supports the
  diagnosis. Historical plan existence alone is supporting evidence, not an observed diagnosis.
- If matching TiDB version, schema, and stats are available, local validation is mandatory
  before final report.
- If validation cannot run, record the exact blocker.
- `plan already recovered` means the full-SQL local baseline naturally selects the expected plan
  shape before any candidate operation. Use `plan_verified`; final reporting should normally use
  `No optimizer action` unless current production evidence still shows the bad plan active.

Every optimizer candidate plan-validation result must answer:

- `syntax_accepted`: TiDB accepts the candidate syntax.
- `optimizer_selected_expected_path`: the optimizer selects the expected access path, join, or
  engine after applying the candidate locally.
- `plan_shape_matches_diagnosis`: the selected plan shape addresses the diagnosed mechanism.

All three values must be `true` before Binding or TiFlash/MPP SQL may appear in the final
`Review-only SQL` field or any optimizer recommendation may be marked `plan_verified`.

A plan-changing `plan_verified` result must also retain a material semantic delta. Do not compare
only operator names or tree shape. The same tree may be materially better when access conditions,
range bounds, residual filters, lookup behavior, pruning, pushdown, ordering, join semantics, or
task/store placement improves. Operator-ID, plan-digest, `estRows`, or estimated-cost changes alone
are insufficient. The delta must address the diagnosed mechanism and record concrete before/after
values.

Every retained `result.json` must record plan validation and runtime evidence separately:

```json
{
  "plan_validation_status": "not_run | passed | failed",
  "runtime_evidence_status": "not_observed | observed | failed"
}
```

For `validation_level: plan_verified`, retain this compact shape in `result.json`:

```json
{
  "plan_validation": {
    "validation_source": "local_tidb",
    "target_tidb_version": "",
    "local_tidb_version": "",
    "source_commit": "",
    "reproduction_kind": "candidate",
    "version_match": true,
    "schema_loaded": true,
    "stats_loaded": true,
    "full_sql_validated": true,
    "baseline_plan_captured": true,
    "candidate_plan_captured": true,
    "baseline_matches_expected_shape": false,
    "syntax_accepted": true,
    "optimizer_selected_expected_path": true,
    "plan_shape_matches_diagnosis": true,
    "semantic_delta": {
      "material": true,
      "addresses_diagnosed_mechanism": true,
      "changed_fields": ["access_conditions", "access_range"],
      "before": "<concrete baseline values>",
      "after": "<concrete candidate values>",
      "summary": "<why the delta addresses the diagnosed mechanism>"
    }
  }
}
```

For `validation_level: observed`, retain:

```json
{
  "runtime_observation": {
    "observation_source": "production_runtime",
    "runtime_evidence_observed": true,
    "diagnosis_supported": true,
    "evidence_reference": ""
  }
}
```

These fields remain after raw validation artifacts are cleaned.

An Index candidate may instead pass the evidence-backed advisory gate when local validation did
not run. Its candidate artifact must record all of these booleans as `true`:

- `schema_collected`;
- `candidate_columns_verified`;
- `existing_indexes_checked`;
- `production_plan_mechanism_identified`;
- `material_bottleneck_addressed`;
- `target_version_ddl_checked`;
- `operational_risks_recorded`.

The artifact must also include an `advisory_evidence` object that maps every check to source paths
or a target-version documentation/source reference. Documentation references may come from
`pingcap/docs` or the TiDB official website and must include the exact branch, page, or URL used.
The gate fails when any check is false, missing, or unsupported. A completed validation result of
`rejected` cannot fall back to the advisory gate.

An inferred `Index first` requires a concrete DDL, `advisory_gate: passed`, and an exact local
validation blocker. Its DDL may appear as review-only advisory SQL, but the report must state that
the candidate plan was not reproduced and must not claim optimizer selection or runtime gain.
Missing schema, unchecked existing indexes, an absent candidate, or a candidate that does not
address a material production bottleneck is an incomplete workflow, not an inferred Index
recommendation.

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
- `advisory_checks` for Index candidates
- `advisory_evidence` for Index candidates

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
- a concrete material semantic delta for every passing plan-changing candidate;
- comparison artifact path;
- exact blocker when validation cannot run.

`workflow/final-report/SUBSKILL.md` must:

- use only the contracted recommendation vocabulary;
- write the customer-facing report in English only;
- include the exact target SQL digest in the focused report's `Observed evidence`;
- write the customer-facing report to `<workspace>/report/report.md`; other report filenames are
  invalid for new cases;
- keep plan-changing `Conclusion` to `Action` and concrete review-only SQL, and keep
  non-plan-changing `Conclusion` to `Action`;
- put complete before/after plans only in `Plans Before & After` for Binding, Index, or TiFlash/MPP
  actions, and omit that section for other actions;
- put diagnostic `Why`, evidence, inference, validation, and risks in `Analysis`;
- keep plan source, validation, schema/stats, provenance, cleanup, and other audit metadata out of
  `Conclusion` and out of the full-plan preamble;
- read complete plan, candidate, and comparison artifacts by path instead of expecting them to be
  copied into the compact manifest;
- output the selected candidate ID, validation status, validation level, and report path;
- keep concrete review-only SQL out of the report unless all three validation booleans are true or
  an inferred Index candidate passed the advisory gate;
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
    "plan_validation_status": "not_run | passed | failed",
    "runtime_evidence_status": "not_observed | observed | failed",
    "advisory_gate": "not_applicable | passed | failed",
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

For `dedicated_fleet`, retain the complete discovered cluster set and ranking coverage. A fleet is
complete only when every discovered cluster's ranking query succeeded; a successful empty result
counts as covered, while a collection error does not. Rank candidates globally as distinct
`(cluster_id, digest)` targets and never merge equal digests across clusters.

When subagents are available:

- dispatch exactly one digest to each subagent;
- explicitly instruct every subagent to use the complete `$autox-optimize-sql` skill;
- require every subagent to run input resolution, evidence collection, diagnosis and candidate
  generation, local validation when available, final report, and cleanup;
- never place multiple digests in one subagent task;
- reject and rerun child output that skipped a required stage or failed a focused completion gate.

Completion is two-phase. The child validates complete referenced evidence and optimizer candidate
artifacts before cleanup. The parent then validates only the retained handoff with
`scripts/validate_case.py`, including the compact manifest only when one was retained. The parent
must not require a child manifest or other persistent case state. It must resolve
`candidate_artifact_path` rather than assume a directory such as `plans/candidates/`, and it must
not require raw intermediate artifacts after a successful cleanup. Non-optimizer and no-action
recommendations do not require a retained optimizer candidate artifact.

Agent process exit is transport state, not case validity. If a retry exits nonzero, preserve an
already valid retained handoff; classify the transport error only when the final handoff validator
still fails.

Quota exhaustion, transport errors, authentication interruptions, and agent/process interruption
are retryable orchestration events. Keep the affected child `retry_pending` or `running`, set the
batch to `paused` when execution cannot continue immediately, persist the remaining queue, and
resume from the manifest. Do not convert a retryable interruption into child `failed` or batch
`completed`.

Set `batch_status: completed` only when every child in the effective user-authorized scope is
`completed` and passes `scripts/validate_case.py`, the aggregate summary exists, and
`scripts/validate_batch.py` passes. Any child `failed` makes the batch `incomplete`, not completed.
Any `queued`, `running`, or `retry_pending` child keeps the batch `running` or `paused`. Do not send
a final finished message for `running`, `paused`, or `incomplete` batches.

For `dedicated_fleet`, `completed` also requires the attempted and succeeded ranking cluster sets
to equal the discovered Dedicated cluster set and `failed_clusters` to be empty.

Preserve the original requested scope separately from the effective scope. If they differ, require
a recorded user-authorized scope change with the previous count, new count, and reason. Preserve
removed queue entries as `excluded_by_user`. Resource limits alone never authorize silent scope
reduction.

The parent must not diagnose a child digest, invent its candidates, or rewrite its recommendation.
The aggregate summary references focused report paths and does not copy full SQL, plans, or
candidate details.

Use `batch-summary.md` as the only canonical batch main report. Its only top-level sections after
the title are `Batch`, `Summary`, and `Cases`. The Cases table has exactly six columns in this
order: `Rank`, `Cluster`, `Impact`, `Action`, `Validation`, `Report`. Do not expose internal
candidate signals or IDs in the main report.

Write the batch main report in English only. Keep digest out of its six-column table; every linked
focused report carries the exact digest.

Keep the batch manifest compact. Each child record should contain only:

- rank, cluster ID, and digest;
- diagnosis ID;
- orchestration status;
- recommended action and validation level when completed;
- focused report path;
- failed stage and concise blocker when failed.

The batch record should also retain `batch_status`, `requested_top_n`, `effective_top_n`, explicit
scope-change authorization when applicable, derived child-status counts, and for fleet mode the
discovered cluster IDs plus compact ranking coverage.

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
