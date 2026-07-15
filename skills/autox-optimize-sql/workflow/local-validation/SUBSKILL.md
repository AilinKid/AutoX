---
name: local-validation
description: Validate AutoX ready-for-validation candidates in an isolated local TiDB environment using full SQL, schema, stats, hypothetical indexes, hypothetical TiFlash, and EXPLAIN output.
---

# Local Validation

Use this workflow subskill after `workflow/diagnosis-classification/SUBSKILL.md` has classified
the root cause and generated candidate records.

Read `../../references/case-contract.md` before applying this workflow.

This subskill validates candidates. It must not invent new Binding, Index, TiFlash/MPP, or
non-optimizer candidates. If a candidate is underspecified, record the exact blocker and return to
diagnosis-classification instead of guessing.

## Candidate Artifact Loading

Treat the compact candidate record as routing metadata, not as the complete validation payload.
For every `ready_for_validation` candidate:

1. Read `id`, `type`, `status`, `review_only_sql`, `mechanism`, `evidence_paths`,
   `expected_plan_change`, `validation_steps`, and `candidate_artifact_path` from the candidate
   record returned by diagnosis-classification or referenced by an optional run-local manifest.
2. Resolve `candidate_artifact_path` inside the current diagnosis workspace and open the complete
   candidate artifact.
3. Verify that the artifact identifies the same candidate ID and type.
4. Read all type-specific SQL, checks, expected shape, and risks from the artifact.
5. If a value is duplicated in the compact record and artifact, require the values to agree. Treat
   a mismatch as a blocker; do not merge conflicting values.

Type-specific artifact payloads include:

- Binding: source-plan evidence path, full hinted SQL, optional local-only Binding SQL, exact
  review-only Binding SQL, expected access/join/engine shape, and parameter/risk notes.
- Index: existing-index checks, review-only DDL, exact hypothetical-index create/drop SQL, current
  access conditions, predicates expected to move into access, and expected plan shape.
- TiFlash/MPP: target aliases and tables, exact hypothetical-TiFlash set/reset SQL, full validation
  SQL or hint, historical-versus-inferred source, and expected per-alias MPP shape.

The artifact path must exist and be readable. If it is missing, outside the diagnosis workspace,
has a mismatched ID/type, lacks a required type-specific field, or cannot support full-SQL
validation, record:

```text
validation_status: not run
validation_level: inferred
blocker: <exact artifact or field failure>
```

Return the candidate to diagnosis-classification for correction. Do not reconstruct missing SQL,
index columns, hint placement, target aliases, or validation steps in this subskill.

## Validation Goal

Validation answers three yes/no questions for each optimizer candidate:

1. **Syntax accepted:** Can the target TiDB version accept the candidate syntax?
2. **Optimizer selection:** Does the optimizer choose the expected access path, join, or engine?
3. **Mechanism match:** Does the resulting plan shape match the diagnosis mechanism?

Local validation proves plan shape only. It does not prove runtime improvement.

## Baseline-First Rule

Before applying any candidate operation, run baseline `EXPLAIN FORMAT='verbose'` for the full
original SQL against the loaded schema and stats.

If the baseline plan already matches the candidate's expected plan shape, stop candidate
application for that case and mark:

```text
validation_status: plan already recovered
validation_level: plan_verified
```

This means the current optimizer, schema, and statistics already choose the desired plan without
Binding, Index, TiFlash hints, or other candidate operations. In the final report, treat this as
`No optimizer action` unless production evidence still shows the bad plan is active in the target
time window.

If the baseline plan still matches the slow-log bad plan or still misses the expected mechanism,
continue to candidate validation.

Important distinction:

- If a newly added hypothetical index is selected naturally after it exists, that is the expected
  index validation path.
- If a suitable existing index already exists but the optimizer only chooses it with a hint, the
  issue is likely CBO choice, plan binding, or statistics. Validate the hinted/binding candidate
  rather than treating it as a pure new-index case.
- If a suitable existing index already exists and the baseline now chooses it without a hint, the
  plan has recovered under current stats. Do not force a new index or binding from stale slow-log
  evidence.

## Safety Boundary

The production target cluster is read-only. Never point local validation commands at production.

Never:

- execute target SQL against production;
- create or drop production bindings;
- create or drop production indexes;
- execute production DDL;
- change production statistics;
- change production variables;
- set real TiFlash replicas in production;
- execute generated Binding SQL from `EXPLAIN EXPLORE`;
- claim runtime improvement from local static `EXPLAIN` alone.

Local-only DDL is allowed only inside the isolated local TiDB validation environment:

- generated `CREATE DATABASE` / `CREATE TABLE`;
- `LOAD STATS`;
- hypothetical index statements;
- hypothetical TiFlash replica statements;
- local-only binding or hinted SQL for plan-shape validation.

## Local TiDB Environment

Local validation is optional and may use only an externally prepared isolated TiDB environment.
AutoX must not install, download, build, or provision TiDB, TiDB source, `json2schema`, or other
environment dependencies. If a suitable environment is unavailable, record the exact blocker and
continue without claiming plan verification.

Environment absence changes only validation status and level. Preserve the diagnosis direction
and the Index candidate's advisory checks. An Index candidate whose advisory gate passed remains
eligible for an inferred `Index first`; do not replace it with a no-action candidate solely because
local TiDB was not prepared. A candidate actually rejected by completed validation is not eligible
for this fallback.

Optional local inputs:

- a TiDB binary or source checkout matching the target cluster version;
- a local standalone TiDB process using the default local storage engine, not TiKV;
- exported schema JSON and statistics JSON;
- a schema/statistics replay workspace;
- `json2schema` from `https://github.com/time-and-fate/json2schema`.

The local TiDB version must match the target cluster TiDB version as closely as possible. If it
does not match, mark validation as advisory or `inferred`.

Never reuse a local TiDB data directory, port, generated schema, stats file, or validation
workspace across diagnosis IDs.

## Full SQL Requirement

Never simplify the SQL for validation.

Always use the exact production SQL shape from slow log or diagnosis output:

- full join structure;
- all subqueries;
- all UNION arms;
- all predicates;
- original parameter placeholders or representative literal values;
- same aliases needed for hints.

Do not reduce a 6-table join to a 3-table subset, strip subqueries, remove UNION arms, or replace
complex OR/AND trees. The optimizer can choose different plans under different query complexity.

If placeholders lack usable sample arguments, an involved table schema is missing, or another
blocker prevents full-SQL validation, record the exact blocker. Do not validate a simplified query
and present it as the final candidate plan.

## Prepare Schema and Stats

For candidates requiring local plan-shape validation, and only when all required tools and the
isolated TiDB endpoint were prepared externally:

1. Connect to the externally prepared standalone local TiDB endpoint. Do not start or provision
   an environment as part of AutoX.
2. Convert each involved `tidb_schema_by_table` JSON file into `CREATE TABLE` SQL using the
   externally prepared `json2schema` executable:

   ```bash
   json2schema tidb_schema_by_table_1688114034.json
   ```

3. Execute the generated `CREATE DATABASE` and `CREATE TABLE` statements locally.
4. Load corresponding statistics JSON after schema creation and before hypothetical indexes:

   ```sql
   LOAD STATS '<stats-json-file>';
   ```

   When using the MySQL client, enable local infile support:

   ```bash
   mysql --local-infile=1 ... -e "LOAD STATS '/path/to/stats.json';"
   ```

   If the client returns `LOAD DATA LOCAL INFILE file request rejected`, treat it as a client-side
   local infile restriction and retry with `--local-infile=1`. Do not misreport it as TiDB
   rejecting `LOAD STATS`.

5. Save generated DDL, loaded stats filenames, local TiDB version, and the non-secret endpoint
   identifier as validation evidence.

## Baseline Plan

For every optimizer candidate, capture the local baseline plan before applying the candidate:

```sql
EXPLAIN FORMAT='verbose' <full SQL>;
```

Save the complete raw output. Do not summarize or truncate it.

Compare the baseline plan to the candidate's `expected_plan_change` before applying the candidate.
If the expected shape is already present, use the Baseline-First Rule and skip candidate
application.

If local baseline cannot be produced, record:

- candidate ID;
- exact blocker;
- local TiDB version;
- schema files loaded;
- stats files loaded;
- best available EXPLAIN output if any.

Set:

```text
validation_status: inferred
validation_level: inferred
```

## Binding Candidate Validation

For `type: binding` candidates:

1. Open `candidate_artifact_path`. Read the full hinted SQL, optional local-only Binding SQL,
   review-only Binding SQL, source-plan evidence path, expected plan shape, and risk notes from the
   artifact. Do not require these type-specific fields in the compact candidate record.
2. Capture baseline `EXPLAIN FORMAT='verbose'` for the full original SQL.
3. Apply the candidate locally by either:
   - running `EXPLAIN FORMAT='verbose'` on the full hinted SQL; or
   - creating a local-only binding only when the artifact explicitly provides exact local Binding
     SQL.
4. Capture candidate `EXPLAIN FORMAT='verbose'`.
5. Compare:
   - access paths;
   - join order;
   - join algorithm;
   - build/probe sides;
   - task/store placement;
   - estimates and cost;
   - whether the shape matches the source or historical better plan.

Use `EXPLAIN ANALYZE` only when local data is intentionally loaded, safe, and representative.

Lower estimated cost alone is not validation.

## Index Candidate Validation

For `type: index` candidates:

1. Open `candidate_artifact_path`. Confirm it contains existing-index checks, review-only DDL,
   exact hypothetical-index create/drop SQL, expected plan change, and the diagnosed access-path
   mechanism.
2. Capture baseline `EXPLAIN FORMAT='verbose'` for the full SQL with loaded schema and stats.
3. Execute the exact local hypothetical-index SQL from the artifact. Verify that it uses syntax
   accepted by the target TiDB version; do not derive index columns or synthesize replacement SQL
   in validation. In current TiDB versions, the reference syntax is:

   ```sql
   CREATE INDEX <hypo_index_name> ON <db>.<table>(<columns>) TYPE HYPO;
   DROP HYPO INDEX <hypo_index_name> ON <db>.<table>;
   ```

4. Capture candidate `EXPLAIN FORMAT='verbose'`.
5. Compare:
   - whether the candidate index is selected;
   - access object and access range;
   - predicates moved from residual filter to access condition;
   - table lookup reduction or covering behavior;
   - keep order, Sort, or TopN changes;
   - join order and join algorithm changes;
   - estimated rows and cost;
   - whether the plan matches the expected mechanism.
6. Execute the exact hypothetical-index cleanup SQL from the artifact.
7. Save hypothetical index DDL, baseline plan, candidate plan, and comparison notes.

If the candidate index is not selected, mark the candidate rejected or inferred unless the
blocker is clear, such as missing session variables, version mismatch, incomplete stats, or a
different candidate that should be generated by diagnosis-classification.

## TiFlash / MPP Candidate Validation

For `type: tiflash_mpp` candidates:

1. Open `candidate_artifact_path`. Confirm it contains target aliases, target tables, exact
   hypothetical-TiFlash set/reset SQL, expected per-alias MPP shape, and full validation SQL or
   hint.
2. Use the same local TiDB env prepared for schema and stats validation.
3. Execute the artifact's exact hypothetical-TiFlash setup SQL only for its specified tables. Do
   not add aliases or tables during validation.

   In current TiDB versions:

   ```sql
   ALTER TABLE <db>.<table> SET HYPO TIFLASH REPLICA 1;
   ALTER TABLE <db>.<table> SET HYPO TIFLASH REPLICA 0;
   ```

4. Wait 1-2 seconds after setting hypothetical TiFlash replicas before running `EXPLAIN`.
   Metadata needs time to propagate. If `EXPLAIN` still shows TiKV operators, retry with a longer
   wait before concluding the MPP shape cannot be selected.
5. Run candidate `EXPLAIN FORMAT='verbose'` for the full SQL or full hinted SQL.
6. Check whether the plan uses the expected shape, such as:
   - `mpp[tiflash]`;
   - `ExchangeSender`;
   - TiFlash `TableFullScan`;
   - pushed `Selection`;
   - pushed or MPP `HashJoin`;
   - expected per-alias storage path.
7. Execute the artifact's exact hypothetical-TiFlash reset SQL.
8. Save baseline and hypothetical TiFlash plans as evidence.

Do not use an all-in TiFlash validation shape as evidence for a narrower historical hybrid plan.
If the candidate targets only alias `p`, validate only that shape unless another candidate was
generated for a broader MPP shape.

If production already has TiFlash replicas but local validation cannot make the desired MPP plan
appear, do not claim local validation success.

## Plan Explore Fallback

Use `autox-explore-sql` only when diagnosis-classification or prior validation has produced an
explicit `plan_explore` internal step and all of these are true:

1. no historical plan candidate is good enough to stabilize;
2. no index candidate has a convincing mechanism, or index validation failed;
3. no TiFlash/MPP candidate is convincing, or MPP validation failed;
4. schema and stats have already been loaded into the local TiDB env.

Invoke `$autox-explore-sql` with the local TiDB env, full target SQL, TiDB version, and evidence
workspace. `$autox-explore-sql` owns detailed `EXPLAIN EXPLORE` rules.

Do not execute generated `EXPLAIN ANALYZE` or `CREATE GLOBAL BINDING` statements from
`EXPLAIN EXPLORE`. They are review-only evidence.

If explore produces a concrete candidate, save it under `experiments/` and require the same compact
candidate record plus `candidate_artifact_path` contract before validation. Return it to
diagnosis-classification for normalization when that contract is incomplete; local validation must
not fill the missing candidate fields. If explore does not produce a useful candidate, final report
should use `No optimizer action` or `Investigate non-optimizer bottleneck`, not `More evidence is
required`.

## Validation Result Vocabulary

Use validation levels from `case-contract.md`:

- `inferred`: no candidate plan was reproduced.
- `plan_verified`: local or production-safe static `EXPLAIN` shows the intended plan shape.
- `prod_verified`: production read-only observation or approved production validation confirms
  the intended improvement.

Use validation status examples:

- `locally verified by EXPLAIN`
- `plan already recovered`
- `locally explored by EXPLAIN EXPLORE`
- `production verified`
- `rejected`
- `inferred`
- `not run`

Do not mark a candidate `Verified` unless production-safe runtime validation or representative
`EXPLAIN ANALYZE` exists. Local static `EXPLAIN` only proves plan shape.

## Plan Comparison

For every candidate with baseline and candidate plans, compare:

- operator tree;
- access object and access range;
- pushed and residual predicates;
- task/store placement;
- join order;
- join algorithm;
- build/probe side;
- Sort/TopN/Agg pushdown;
- estimated rows and cost;
- whether the expected plan change occurred.

Record the three validation answers explicitly:

```json
{
  "syntax_accepted": true,
  "optimizer_selected_expected_path": true,
  "plan_shape_matches_diagnosis": true
}
```

If any answer is `false`, record the exact reason and mark the candidate `rejected` or `inferred`
depending on whether validation was complete.

Use `$autox-compare-plans` when multiple candidates or plan variants need normalized comparison,
ranking, or rejection reasons.

## Cleanup

Do not stop or reconfigure an externally managed TiDB environment.

Best-effort cleanup:

- temporary schema/stat replay files;
- hypothetical index state;
- hypothetical TiFlash state;
- temporary validation SQL files.

If cleanup fails, record the exact leftover path and what remains.

## Output Contract

Return this validation result directly. Optionally write or update run-local `manifest.json` with:

```json
{
  "validation": {
    "local_tidb_version": "",
    "version_match": false,
    "schema_loaded": false,
    "stats_loaded": false,
    "results": [
      {
        "candidate_id": "",
        "candidate_type": "",
        "validation_status": "",
        "validation_level": "",
        "validation_source": "local tidb env",
        "syntax_accepted": false,
        "optimizer_selected_expected_path": false,
        "plan_shape_matches_diagnosis": false,
        "baseline_plan_path": "",
        "candidate_plan_path": "",
        "comparison_summary": "",
        "comparison_path": "",
        "blocker": "",
        "rejected_reason": ""
      }
    ]
  },
  "cleanup": {
    "external_environment_unchanged": true,
    "raw_artifacts_cleaned": false,
    "leftover_paths": []
  }
}
```

Hand off to `workflow/final-report/SUBSKILL.md`.
