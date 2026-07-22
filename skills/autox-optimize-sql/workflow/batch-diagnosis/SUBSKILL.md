---
name: batch-diagnosis
description: Orchestrate AutoX top-N and multi-digest slow-SQL diagnosis with isolated per-digest workflows, bounded concurrency, focused reports, and a compact aggregate summary.
---

# Batch Diagnosis

Use this workflow subskill when the user asks for top slow queries, Top SQL, top-N digests,
multiple digests, a batch such as top 40 or top 200, or a generic fleet-wide cluster diagnosis.

Read `../../references/case-contract.md` before applying this workflow.

This is an orchestration workflow, not a batch-triage shortcut. Rank the target digests, then run
the complete focused AutoX workflow for every selected digest. Never replace per-digest diagnosis
with aggregate heuristics or one generic recommendation.

## Batch Inputs

Require one scope:

- one exact `cluster_id`; or
- generic fleet scope resolved to all accessible active Dedicated cluster IDs.

Accept:

- requested `top_n` or an explicit digest list;
- business time range and timezone;
- ranking preference when explicitly provided by the user;
- `max_concurrency`;
- prepared local TiDB binaries or source checkouts.

Use these defaults:

- generic cluster diagnosis: all accessible active Dedicated clusters;
- `top_n`: `10` when omitted, treated as a cap when fewer ranked candidates exist;
- time range: rolling last 24 hours when omitted;
- `max_concurrency`: `5`, unless the user explicitly chooses another value;
- ranking: total slow-query latency in the target time range;
- output: one focused report per digest plus one compact batch summary.

Apply these defaults independently. An explicit value overrides only that value. Do not ask the
user to confirm the default fleet, top-10, or 24-hour scope before making read-only Clinic calls.

Do not silently reduce an explicit `top_n`. If resource or execution limits prevent completing the
requested count in one run, preserve the full queue and resume from the batch manifest.

When the default top-10 cap is used and fewer than 10 candidates exist, select every available
candidate and record `top_n_source: default`, `top_n_cap: 10`, and the available count. This is not
a user-scope reduction. Keep `requested_top_n` and `effective_top_n` equal to the selected available
count so the completion gate reflects real work rather than nonexistent candidates.

Preserve the original request as `requested_top_n` and the currently authorized scope as
`effective_top_n`. They start equal. Change `effective_top_n` only after the user explicitly
authorizes a smaller scope; retain `from_top_n`, `to_top_n`, authorization, and reason in
`scope_change`. Preserve removed queue records with `status: excluded_by_user` for audit.

## Parent Resolution and Ranking

Resolve the shared batch context once.

For one cluster:

1. Resolve the exact cluster ID and collect cluster metadata.
2. Resolve the business and UTC time range, including Slow Query and TopSQL partitions.
3. Run digest-level Slow Query aggregation without selecting a single digest.
4. Exclude write DML, transaction control, DDL, administrative statements, and locking
   `SELECT ... FOR UPDATE`; AutoX v0 ranks read-only `SELECT` statements only.
5. Rank unique digests by total slow-query latency unless the user requested another ranking.
6. Preserve execution count, total/average/max latency, representative SQL, plan-digest count,
   processed keys, total keys, memory, and disk when available.
7. Select the requested number of unique digests after ranking. Multiple plan variants for one
   digest belong to the same focused case.

For generic fleet mode:

1. List all Clinic pages using `deploy_type_v2=dedicated`, `cluster_status=active`, and
   `show_deleted=false`; recheck each returned record and deduplicate by cluster ID.
2. Record the complete discovered cluster set before Slow Query collection.
3. Run digest-level Slow Query aggregation for every discovered cluster over the same exact
   rolling 24-hour window.
4. Exclude write DML, transaction control, DDL, administrative statements, and locking
   `SELECT ... FOR UPDATE`; AutoX v0 ranks read-only `SELECT` statements only.
5. Preserve per-cluster ranking status as succeeded, empty, or failed with the exact blocker.
6. Merge candidates as distinct `(cluster_id, digest)` targets and rank them globally by total
   slow-query latency. Do not combine the same digest across clusters.
7. Select up to 10 global targets unless the user supplied another top-N.

Use `../../scripts/collect_fleet_slow_sql.py` for fleet discovery and ranking. A completed fleet
must have successful ranking coverage for every discovered Dedicated cluster. Empty Slow Query
results count as successful coverage; collection failures do not. Keep retryable failures pending
or paused and never present partial cluster coverage as a completed fleet diagnosis.

Use the bundled `scripts/collect_slow_sql.py` ranking output for one cluster. Preserve API errors
explicitly and do not interpret collection failure as an empty ranking.

If parent cluster resolution, authentication, or ranking fails, stop the single-cluster batch
before creating child cases and report the exact failure. In fleet mode, preserve successful
cluster rankings but keep the fleet paused or incomplete until every discovered cluster has a
successful or explicitly empty ranking result. Do not create placeholder diagnoses without target
digests.

## Workspace and Isolation

Generate one globally unique `batch_id` and one globally unique `diagnosis_id` per selected
`(cluster_id, digest)` target.

Use a parent workspace with isolated child workspaces:

```text
${AUTOX_WORKDIR:-${TMPDIR:-/tmp}/autox-batch/<batch_id>}/
  batch-manifest.json           # optional run-local audit/resume index
  ranking.json
  batch-summary.md
  cases/
    <diagnosis_id>/
      manifest.json             # optional run-local audit index
      evidence/
      plans/
      experiments/
      decision/
      report/
      cleanup/
```

Never share between active digest cases:

- local TiDB data directories;
- local TiDB source worktrees;
- local schema databases;
- ports;
- generated SQL files;
- hypothetical indexes;
- hypothetical TiFlash metadata;
- candidate experiments;
- report files.

Schema and statistics artifacts may be reused read-only only when the cache key includes:

- cluster ID;
- TiDB version;
- database;
- table;
- statistics snapshot time.

Copy or reference cached artifacts read-only from each child's output or optional manifest. Never
allow one child to modify shared cache state.

## Per-Digest Workflow

Each child case owns exactly one digest and must run the focused workflow in order:

1. `../input-resolution/SUBSKILL.md`
2. `../evidence-collection/SUBSKILL.md`
3. `../diagnosis-classification/SUBSKILL.md`
4. `../local-validation/SUBSKILL.md`
5. `../final-report/SUBSKILL.md`

The child may inherit resolved cluster and time-range values from the parent, but it must return
them with its output and validate that the `(cluster_id, digest)` target belongs to the ranked
result. It may also record
them in an optional child manifest. Inherited context does not remove any evidence, diagnosis,
validation, report, or cleanup step.

For each digest:

- collect representative executions and all important plan variants;
- collect schema and statistics for every involved user table; for Dedicated clusters without a
  direct TiDB status endpoint, run `scripts/collect_dashboard_debug_api_table.py` once per table;
- preserve complete production runtime plan and execution details;
- diagnose from the full artifacts, not only the aggregate ranking row;
- generate concrete candidates in diagnosis-classification;
- run full-SQL local validation when matching version, schema, and stats are available;
- produce one complete focused report;
- write the focused report in English and include the exact digest under `Observed evidence`;
- remove child-created hypothetical state and complete run-local artifact cleanup before marking
  the case complete; stop and clean up any local TiDB process, data directory, and source worktree
  created for that child diagnosis.

Do not share a recommendation between digests merely because SQL text, table names, or plan shapes
look similar.

## Subagent Dispatch and Concurrency

When subagent orchestration is available, use one subagent per digest. Do not let the parent agent
execute a partial diagnosis on behalf of a child.

Each subagent task must explicitly instruct the subagent to use the complete
`$autox-optimize-sql` skill for exactly one digest. The dispatch prompt must provide:

- cluster ID;
- one digest;
- business and UTC time range with timezone;
- the child `diagnosis_id` and workspace;
- inherited ranking and cluster-context artifact paths;
- an explicit requirement to run the full focused workflow through final report and cleanup.

Use a task instruction equivalent to:

```text
Use $autox-optimize-sql to diagnose exactly this one digest. Run the complete focused workflow:
input resolution, evidence collection, diagnosis and candidate generation, local validation when
available, final report, and cleanup. Do not return aggregate triage or skip phases. Write all
artifacts into the provided diagnosis workspace. The Data Proxy schema is not user-table schema;
for a Dedicated cluster, collect each user table through the bundled Clinic Dashboard debug API
collector when direct status HTTP is unavailable. Return the focused report path and final
recommendation/validation status directly; update an optional run-local manifest when one is used.
```

Dispatch rules:

1. Create one subagent task per digest.
2. Give each subagent exactly one digest; never place multiple digests in one subagent task.
3. Keep at most `max_concurrency` subagents active.
4. Use only isolated validation endpoints or schemas assigned to the child. If no endpoint is
   assigned, the child may allocate a per-diagnosis port, source worktree, and data directory for
   local validation.
5. Start the next queued digest only after an active subagent releases its assigned validation
   session and run-local workspace resources.
6. Reject and rerun a subagent result that did not use the complete `$autox-optimize-sql` workflow
   or failed a per-digest completion gate.

The parent orchestrator may resolve shared context, manage the queue, validate completion gates,
and retry an incomplete child. It must not diagnose a digest, invent candidates, or rewrite a
child's recommendation.

If subagents are unavailable, run child cases sequentially in the parent under the same complete
`$autox-optimize-sql` contract and record that fallback in the direct output or optional batch
manifest. Lack of subagents does not permit skipped workflow steps or generic suggestions.

For long batches, persist progress after every child stage transition so the run can resume without
repeating completed focused cases.

## Child Status

Track only the run-local orchestration status needed by the current batch:

- `queued`;
- `running`;
- `retry_pending`;
- `completed`;
- `failed`;
- `excluded_by_user` after an explicit user-authorized scope reduction.

Use `retry_pending`, not `failed`, for quota exhaustion, transport errors, authentication
interruptions, agent/process interruption, and other retryable orchestration failures. Persist the
current stage, blocker, and resume point before yielding. Resume automatically when execution can
continue.

A failed child must preserve:

- exact failed stage;
- exact blocker or collection error;
- retained artifact path when cleanup cannot safely remove diagnostic state;
- focused report path when a report could be produced.

Do not use `More evidence is required` or `No safe recommendation`. When Cloud-side evidence for a
digest was collected but does not justify an optimizer change, use `No optimizer action`. If the
workflow itself failed before a diagnosis could be made, keep `status: failed` and expose the
blocker in the batch summary; do not fabricate an optimizer recommendation.

## Per-Digest Completion Gate

Use two completion checks because final cleanup intentionally removes raw evidence and intermediate
decision artifacts. Do not run a raw-artifact gate after cleanup.

Before cleanup, the child self-audit must confirm all applicable checks:

- Slow Query and representative production plan collection was attempted and errors were
  preserved explicitly;
- schema and statistics collection has a `collected` or exact `failed` record for every involved
  user table; system tables may use `not_applicable`, but a missing record fails the gate;
- diagnosis opened the complete plan and execution artifacts;
- the root cause names concrete bottleneck operators and tables when evidence provides them;
- optimizer candidates were generated concretely before validation, and every
  `candidate_artifact_path` resolved to a file inside the diagnosis workspace;
- `Index first` has either a plan-validated candidate or an inferred candidate with every Index
  advisory check true; it does not use `Review-only SQL: none`;
- local validation ran when matching TiDB version, schema, and statistics were available;
- validation used the full original SQL without removing joins, subqueries, predicates, or UNION
  arms;
- `plan_verified` retains target/local version, source commit, schema/stats/full-SQL flags,
  complete baseline/candidate plan flags, and all three successful plan-validation booleans;
- `observed` retains production runtime evidence that directly supports the diagnosis and does not
  imply that an optimization was executed or verified in production;
- `Plan before` contains the complete production runtime plan, preferably slow-log
  `decoded_plan`, rendered as a TiDB EXPLAIN-style operator table/tree rather than raw JSON;
- `Plan before` preserves `actRows`, execution info, process/total keys, cop details, memory, and
  disk when available;
- `Plan after` contains complete local `EXPLAIN FORMAT='verbose'` output when validation ran, or
  the exact blocker and best available complete EXPLAIN evidence;
- the focused report follows `../final-report/SUBSKILL.md` exactly;
- the focused report resolves to the canonical child path `report/report.md`;
- the report was rendered from the complete referenced artifacts before they were removed.

`Investigate non-optimizer bottleneck` and `No optimizer action` do not require a retained optimizer
candidate artifact. Never infer an artifact location from a filename or require a fixed directory
such as `plans/candidates/`; resolve the path declared by the candidate record. Candidate records
and artifacts may live under `decision/`, `experiments/`, or another workspace-local path.

After cleanup, the parent must run `../../scripts/validate_case.py` against the retained handoff.
The post-cleanup gate validates `result.json`, the focused report, identity, recommendation,
validation level, cleanup state, report structure, and the optional compact manifest when present.
New cases must pass without compatibility flags; `--allow-legacy-report-name` is only for auditing
reports created before the canonical `report/report.md` contract, and
`--allow-legacy-report-format` is only for auditing reports created before the current
action-specific contract. `--allow-legacy-validation-evidence` is only for auditing cases created
before independent plan validation and runtime evidence status were retained.
It must not require a child manifest or other persistent case state, and it must not require
`plans/production_before`, `decision`, evidence files, or candidate artifacts when the compact
manifest says raw artifacts were cleaned.

Treat agent process exit and completion validity separately. A nonzero retry exit caused by quota,
transport, or authentication does not invalidate an already valid retained handoff. Run the final
gate first, preserve the last valid result, and record transport failure only when the handoff is
still invalid.

If a gate fails, leave the child `running` for retry or mark it `failed` with the blocker. Do not
merge an incomplete case as a completed recommendation.

Mark a child `failed` only for a non-retryable workflow failure after safe in-scope retries are
exhausted. A retryable failure remains `retry_pending`.

## Batch Completion Gate

Track `batch_status` independently from child status:

- `running`: work can continue and at least one child is not completed;
- `paused`: work is expected to resume but cannot continue immediately because of quota,
  transport, authentication, approval, or agent/process interruption;
- `completed`: every child in `effective_top_n` is `completed` and has a valid retained handoff;
- `incomplete`: at least one child has a non-retryable `failed` result or parent resolution failed.

Before claiming completion:

1. Recompute child-status counts from the manifest.
2. Confirm the case count equals `requested_top_n`, the non-excluded count equals
   `effective_top_n`, and target identities `(cluster_id, digest)` are unique.
3. For fleet mode, confirm every discovered Dedicated cluster has successful or explicitly empty
   ranking coverage and no failed ranking record.
4. If `effective_top_n` differs from `requested_top_n`, confirm `scope_change.authorized_by_user`
   is `true` and its previous/new counts match.
5. Run `../../scripts/validate_case.py` for every completed child.
6. Confirm `batch-summary.md` exists and includes explicit requested/effective scope and progress.
7. Run `../../scripts/validate_batch.py <batch-workspace>` and require success.

Never use `completed`, `finished`, `done`, or equivalent user-facing wording while any child is
`queued`, `running`, `retry_pending`, `failed`, or invalid. For `paused`, provide only a progress
snapshot and resume information; do not produce or present a final aggregate report. For
`incomplete`, state explicitly that the batch did not finish and list the blockers.

## Batch Main Report

Use `batch-summary.md` as the only canonical batch main report. Do not create a second
`final-report.md`, executive report, or alternate aggregate report with a different format. The
main report is an index of focused results, not a substitute for them; do not copy full SQL, plans,
candidate artifacts, detailed diagnoses, synthesized findings, or priority advice into it.

Write the main report in English only. Keep the exact SQL digest in each linked focused report,
not in the six-column main table.

Use exactly this structure and heading order:

```markdown
# AutoX Slow SQL Batch Report

## Batch

- Status: `<completed>`
- Scope: `<effective scope; include original requested scope and authorized reduction>`
- Progress: `<completed>/<effective_top_n>`
- Time range: `<business time range and timezone>`
- Ranking: `<ranking key>`
- Coverage: `<collection coverage or not applicable>`
- Safety: `Production read-only; no binding, index, configuration, or DDL changes were applied.`

## Summary

- Impact: `<aggregate executions and latency>`
- Actions: `<counts by contracted recommended_action>`
- Validation levels: `<counts for inferred, observed, and plan_verified>`

## Cases

| Rank | Cluster | Impact | Action | Validation | Report |
|---:|---|---:|---|---|---|
| 1 | <cluster name> | <latency / executions> | <recommended_action> | <validation_level> | [report](cases/<diagnosis_id>/report/report.md) |
```

The Cases table must contain exactly these six columns in this order. Do not add Digest, Status,
Stage, Signal, Candidate, Confidence, Blocker, or other columns. Include one row per completed case
inside `effective_top_n`; keep detailed evidence, blockers, candidate IDs, and recommendations in
the linked focused report or internal manifest.

Render the focused report as a Markdown link relative to `batch-summary.md`, for example
`[report.md](cases/<diagnosis_id>/report/report.md)`. Do not emit an absolute filesystem path in
the summary because Markdown previewers may not navigate local absolute paths.

Use only the contracted recommendation vocabulary. For non-optimizer cases, preserve
`Investigate non-optimizer bottleneck`; do not leave the action blank. For completed cases with no
justified optimizer action, use `No optimizer action`.

Reference each focused report path instead of summarizing its plans. Do not rewrite or normalize a
child's recommendation in the aggregate summary.

Only completed children count toward completed recommendation totals. Do not render a canonical
main report for `running`, `paused`, or `incomplete` batches; provide a progress update from the
manifest instead so a partial batch cannot look complete.

The Batch section must preserve original `requested_top_n`, `effective_top_n`, explicit
user-authorized scope reduction when applicable, and collection coverage. The internal manifest,
not the six-column Cases table, retains queued, running, retry-pending, failed, excluded, blocker,
and candidate details.

For fleet mode, render `Coverage` as the discovered and successfully ranked Dedicated cluster
counts, including any empty clusters. Do not say `completed` when any discovered cluster lacks a
successful ranking query.

## Optional Resume Rules

Resume is optional and requires a valid run-local `batch-manifest.json`. A fresh diagnosis never
requires this file. When the user asks to resume and the file exists:

1. Read `batch-manifest.json`.
2. Verify the batch cluster, time range, ranking artifact, and selected digest list.
3. Skip children with `status: completed` and a valid focused report path.
4. Resume `running` children only when their workspace and required artifacts still exist and the
   immediately preceding workflow output is complete; otherwise restart that digest diagnosis.
5. Resume `retry_pending` children from the recorded stage when artifacts are trustworthy;
   otherwise restart that digest diagnosis without changing the selected scope.
6. Retry or restart failed children only within their existing digest scope; generate a new
   `diagnosis_id` if isolation artifacts are no longer trustworthy.
7. Continue queued children under the same concurrency limit.

Do not silently change the selected digest set, ranking window, or top-N count during resume.

## Output Contract

Optionally keep a run-local `batch-manifest.json` compact for audit or explicit resume. Detailed
evidence and reports remain in child workspaces.

```json
{
  "batch_id": "",
  "scope_mode": "single_cluster | dedicated_fleet",
  "cluster_id": "",
  "cluster_scope": {
    "selection": "all_accessible_active_dedicated",
    "discovered_count": 0,
    "cluster_ids": []
  },
  "ranking_coverage": {
    "attempted_cluster_ids": [],
    "succeeded_cluster_ids": [],
    "empty_cluster_ids": [],
    "failed_clusters": []
  },
  "batch_status": "running | paused | completed | incomplete",
  "time_range": {
    "business": "",
    "utc": "",
    "timezone": ""
  },
  "requested_top_n": 0,
  "effective_top_n": 0,
  "top_n_source": "default | explicit",
  "top_n_cap": 0,
  "scope_change": {
    "authorized_by_user": true,
    "from_top_n": 0,
    "to_top_n": 0,
    "reason": ""
  },
  "status_counts": {
    "queued": 0,
    "running": 0,
    "retry_pending": 0,
    "completed": 0,
    "failed": 0,
    "excluded_by_user": 0
  },
  "max_concurrency": 5,
  "dispatch_mode": "subagent_per_digest",
  "ranking_path": "",
  "summary_path": "",
  "cases": [
    {
      "rank": 0,
      "cluster_id": "",
      "digest": "",
      "diagnosis_id": "",
      "status": "queued | running | retry_pending | completed | failed | excluded_by_user",
      "recommended_action": "",
      "validation_level": "",
      "plan_validation_status": "not_run | passed | failed",
      "runtime_evidence_status": "not_observed | observed | failed",
      "candidate_signal": {
        "type": "",
        "candidate_id": "",
        "status": "none | advisory | observed | plan_verified | rejected"
      },
      "report_path": "",
      "failed_stage": "",
      "blocker": ""
    }
  ]
}
```

When the optional manifest is used, update the corresponding child record and `status_counts` after
each orchestration status change. A batch is complete only when every selected digest in the
effective user-authorized scope is `completed`, every retained child handoff validates, the
aggregate summary references every selected digest, and `validate_batch.py` passes. A batch with
any failed child is `incomplete`, not completed.
