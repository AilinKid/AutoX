---
name: batch-diagnosis
description: Orchestrate AutoX top-N and multi-digest slow-SQL diagnosis with isolated per-digest workflows, bounded concurrency, focused reports, and a compact aggregate summary.
---

# Batch Diagnosis

Use this workflow subskill when the user asks for top slow queries, Top SQL, top-N digests,
multiple digests, or a batch such as top 40 or top 200.

Read `../../references/case-contract.md` before applying this workflow.

This is an orchestration workflow, not a batch-triage shortcut. Rank the target digests, then run
the complete focused AutoX workflow for every selected digest. Never replace per-digest diagnosis
with aggregate heuristics or one generic recommendation.

## Batch Inputs

Require:

- `cluster_id`.

Accept:

- requested `top_n` or an explicit digest list;
- business time range and timezone;
- ranking preference when explicitly provided by the user;
- `max_concurrency`;
- prepared local TiDB binaries or source checkouts.

Use these defaults:

- `top_n`: the user-requested count; when omitted, choose a small high-impact set from ranked
  slow-query candidates;
- `max_concurrency`: `5`, unless the user explicitly chooses another value;
- ranking: total slow-query latency in the target time range;
- output: one focused report per digest plus one compact batch summary.

Do not silently reduce an explicit `top_n`. If resource or execution limits prevent completing the
requested count in one run, preserve the full queue and resume from the batch manifest.

## Parent Resolution and Ranking

Resolve the shared batch context once:

1. Resolve the exact cluster ID and collect cluster metadata.
2. Resolve the business and UTC time range, including Slow Query and TopSQL partitions.
3. Run digest-level Slow Query aggregation without selecting a single digest.
4. Rank unique digests by total slow-query latency unless the user requested another ranking.
5. Preserve execution count, total/average/max latency, representative SQL, plan-digest count,
   processed keys, total keys, memory, and disk when available.
6. Select the requested number of unique digests after ranking. Multiple plan variants for one
   digest belong to the same focused case.

Use the bundled `scripts/collect_slow_sql.py` ranking output. Preserve API errors explicitly and do
not interpret collection failure as an empty ranking.

If parent cluster resolution, authentication, or ranking fails, stop the batch before creating
child cases and report the exact failure. Do not create placeholder diagnoses without target
digests.

## Workspace and Isolation

Generate one globally unique `batch_id` and one globally unique `diagnosis_id` per digest.

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
them with its output and validate that the digest belongs to the ranked result. It may also record
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
- remove child-created hypothetical state and complete run-local artifact cleanup before marking
  the case complete; do not stop or reconfigure an externally managed local TiDB environment.

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
4. Use only isolated validation endpoints or schemas assigned by the externally prepared
   environment. Do not allocate ports, create data directories, or provision TiDB.
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
- `completed`;
- `failed`.

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
- `Plan before` contains the complete production runtime plan, preferably slow-log
  `decoded_plan`;
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
reports created before the canonical `report/report.md` contract.
It must not require a child manifest or other persistent case state, and it must not require
`plans/production_before`, `decision`, evidence files, or candidate artifacts when the compact
manifest says raw artifacts were cleaned.

Treat agent process exit and completion validity separately. A nonzero retry exit caused by quota,
transport, or authentication does not invalidate an already valid retained handoff. Run the final
gate first, preserve the last valid result, and record transport failure only when the handoff is
still invalid.

If a gate fails, leave the child `running` for retry or mark it `failed` with the blocker. Do not
merge an incomplete case as a completed recommendation.

## Aggregate Summary

Create `batch-summary.md` only as an index of focused results. It is not a substitute for the
focused report and must not copy full SQL, plans, candidate artifacts, or detailed diagnosis.

Include one row per selected digest with:

- rank;
- digest;
- aggregate impact used for ranking;
- child status and current stage;
- customer-facing recommended action when diagnosis completed;
- validation level;
- strongest concrete candidate signal, including an unselected advisory Index candidate;
- focused report path;
- concise blocker when failed.

Use only the contracted recommendation vocabulary. For non-optimizer cases, preserve
`Investigate non-optimizer bottleneck`; do not leave the action blank. For completed cases with no
justified optimizer action, use `No optimizer action`.

Reference each focused report path instead of summarizing its plans. Do not rewrite or normalize a
child's recommendation in the aggregate summary.

Only completed children count toward completed recommendation totals. Keep failed and queued cases
visible so a partial batch cannot look complete.

## Optional Resume Rules

Resume is optional and requires a valid run-local `batch-manifest.json`. A fresh diagnosis never
requires this file. When the user asks to resume and the file exists:

1. Read `batch-manifest.json`.
2. Verify the batch cluster, time range, ranking artifact, and selected digest list.
3. Skip children with `status: completed` and a valid focused report path.
4. Resume `running` children only when their workspace and required artifacts still exist and the
   immediately preceding workflow output is complete; otherwise restart that digest diagnosis.
5. Retry or restart failed children only within their existing digest scope; generate a new
   `diagnosis_id` if isolation artifacts are no longer trustworthy.
6. Continue queued children under the same concurrency limit.

Do not silently change the selected digest set, ranking window, or top-N count during resume.

## Output Contract

Optionally keep a run-local `batch-manifest.json` compact for audit or explicit resume. Detailed
evidence and reports remain in child workspaces.

```json
{
  "batch_id": "",
  "cluster_id": "",
  "time_range": {
    "business": "",
    "utc": "",
    "timezone": ""
  },
  "top_n": 0,
  "max_concurrency": 5,
  "dispatch_mode": "subagent_per_digest",
  "ranking_path": "",
  "summary_path": "",
  "cases": [
    {
      "rank": 0,
      "digest": "",
      "diagnosis_id": "",
      "status": "queued",
      "recommended_action": "",
      "validation_level": "",
      "candidate_signal": {
        "type": "",
        "candidate_id": "",
        "status": "none | advisory | plan_verified | rejected"
      },
      "report_path": "",
      "failed_stage": "",
      "blocker": ""
    }
  ]
}
```

When the optional manifest is used, update the corresponding child record after each orchestration
status change. A batch is complete only when every selected digest is `completed` or `failed` and
the aggregate summary references the final state of every selected digest.
