---
name: autox-optimize-sql
description: Analyze a specified slow SQL in a TiDB Cloud cluster and produce evidence-backed Binding and Index recommendations. Use when the user provides a cluster_id together with a SQL digest or slow SQL text and asks for slow-query diagnosis, execution-plan analysis, binding suggestions, or index recommendations. Query cluster metadata, Slow Query, TopSQL, schema, and statistics through the clinic-api skill; optionally use an externally prepared version-matched TiDB instance and TiDB source checkout. This skill is read-only and must not execute bindings, create indexes, or modify the target cluster.
---

# AutoX Slow SQL Optimization

Analyze one specified slow SQL in a TiDB Cloud cluster.

Produce only:

1. Binding recommendation.
2. Index recommendation.

Do not modify the target cluster.

## Dependencies

Require and invoke the `$clinic-api` skill from:

```text
https://github.com/tidbcloud/nutshell-skills/tree/main/skills/platform/clinic-api
```

Before collecting data, invoke
`$clinic-api`, read its `SUBSKILLS_INDEX.md`,
then use these sub-skills:

- `cluster-metadata/SUBSKILL.md`
  - Resolve the exact cluster.
  - Obtain TiDB version and deployment metadata.
- `data-proxy/SUBSKILL.md`
  - Query Slow Query and TopSQL.
  - Inspect the available schema before assuming fields exist.
- `metrics/SUBSKILL.md`
  - Use only when cluster metrics are necessary to distinguish SQL-plan
    problems from cluster-level bottlenecks.

Use the scripts and Python client supplied by `clinic-api`. Do not copy Clinic
authentication or API implementation into AutoX.

## External environment

The execution environment is prepared outside AutoX.

Optional external inputs include:

- A TiDB connection matching the target cluster version.
- A TiDB source checkout matching the target cluster version.
- A schema and statistics replay environment.
- Exported schema or statistics files.

Do not install, download, start, stop, or clean up TiDB.

If no local TiDB environment is available, continue the analysis and mark
candidate recommendations as `inferred`.

## Safety boundary

This Skill is read-only.

Never:

- create or drop a binding;
- create or drop an index;
- execute DDL against the target cluster;
- change statistics;
- change TiDB variables;
- claim a candidate was verified when it was only inferred.

Generated SQL is for human review only.

# Phase 0: Pre-check and input confirmation

Complete this phase before querying Clinic.

## Step 0.1: Verify clinic-api

Verify:

1. The `clinic-api` skill is installed.
2. `CLINIC_API_KEY` is available.
3. The configured Clinic environment is correct:
   - `prod`
   - `staging`
   - `dev`
4. The API key can successfully query Clinic.

If authentication or the API probe fails, stop.

Do not interpret API failure as empty data.

## Step 0.2: Confirm the target SQL

Require:

- `cluster_id`

Optional:

- SQL digest;
- slow SQL text;
- inspection start and end time;
- business timezone;
- prepared local TiDB connection;
- matching TiDB source checkout.

If neither a digest nor SQL text is provided, rank digest candidates by total
slow-query latency and select only a small high-impact set for analysis.

If the user provides SQL text without a digest, resolve the matching digest in
Phase 2.

If multiple digests match, show the candidates and ask the user to choose. Do
not silently select one.

## Step 0.3: Confirm timezone and time range

Clinic queries use UTC.

Users normally describe time in a business timezone. Before collecting data,
confirm the user's timezone.

Example confirmation:

```text
Please confirm the business timezone and inspection range.

Business time:
2026-06-22 00:00:00 ~ 2026-06-23 00:00:00 Asia/Shanghai

Clinic query time:
2026-06-21 16:00:00 ~ 2026-06-22 16:00:00 UTC
```

If the user requests “the latest 24 hours”:

- use a rolling 24-hour interval ending at the current time;
- still confirm the timezone used to display results;
- query Clinic using UTC.

Convert the confirmed range into:

- UTC start timestamp;
- UTC end timestamp;
- Slow Query UTC partitions in `YYYYMMDD`;
- TopSQL UTC partitions in `YYYY-MM-DD`.

Example:

```text
Business time:
2026-06-22 00:00 ~ 2026-06-23 00:00 Asia/Shanghai

UTC:
2026-06-21 16:00 ~ 2026-06-22 16:00

Slow Query partitions:
20260621, 20260622

TopSQL partitions:
2026-06-21, 2026-06-22
```

Always use both:

1. the `date` partition predicate;
2. the exact execution timestamp predicate.

The partition predicate limits the scan. The timestamp predicate limits the
result to the exact requested interval.

# Phase 1: Resolve cluster context

Use the exact `cluster_id` lookup supported by the Clinic cluster metadata API.

Do not use the first result of a fuzzy `query` search.

Collect:

- cluster ID;
- cluster name;
- cluster status;
- TiDB version;
- deployment type;
- cloud provider;
- region.

The TiDB version determines:

- supported optimizer hints;
- binding syntax;
- statistics behavior;
- plan format;
- source code version used for investigation.

If the cluster is not found, stop.

If the cluster is deleted or unavailable, report the state and ask whether to
continue with historical data.

# Phase 2: Resolve and characterize the target digest

## Step 2.1: Inspect the Slow Query schema

Use the Clinic Data Proxy schema API for `slow_query_logs`.

Confirm the available columns before constructing queries.

At minimum, attempt to locate:

- `digest`
- `time`
- `query`
- `query_time`
- `decoded_plan`
- `stats`
- `warnings`
- `index_names`
- `process_time`
- `wait_time`
- `backoff_time`
- `backoff_types`
- `total_keys`
- `process_keys`
- `result_rows`
- `mem_max`
- `disk_max`
- `date`

Use only fields confirmed by the schema API.

## Step 2.2: Resolve SQL text to digest

Skip this step when the user already supplied a digest.

When the user supplies SQL text:

1. Query Slow Query records in the confirmed UTC window.
2. Compare normalized SQL shape, table references, predicates, and digest.
3. Return all plausible matches when more than one digest matches.
4. Ask the user to select the target digest.

Do not rely on exact literal equality because Slow Query records may contain
different parameter values.

## Step 2.3: Aggregate the target digest

Query the target digest over the exact UTC window.

Collect:

- execution count;
- total query time;
- average query time;
- maximum query time;
- maximum process time;
- maximum wait time;
- maximum backoff time;
- total and maximum process keys;
- total and maximum total keys;
- maximum result rows;
- maximum memory;
- maximum disk;
- indexes used.

`slow_query_logs.date` uses UTC `YYYYMMDD`.

`total_keys` and `process_keys` may be strings. Convert defensively and handle
empty values.

Example query shape:

```sql
SELECT
  digest,
  any_value(query) AS sample_sql,
  COUNT(*) AS exec_count,
  SUM(query_time) AS total_query_time,
  AVG(query_time) AS avg_query_time,
  MAX(query_time) AS max_query_time,
  MAX(process_time) AS max_process_time,
  MAX(wait_time) AS max_wait_time,
  MAX(backoff_time) AS max_backoff_time,
  SUM(CAST(total_keys AS double)) AS total_total_keys,
  MAX(CAST(total_keys AS double)) AS max_total_keys,
  SUM(CAST(process_keys AS double)) AS total_process_keys,
  MAX(CAST(process_keys AS double)) AS max_process_keys,
  MAX(result_rows) AS max_result_rows,
  MAX(mem_max) AS max_memory,
  MAX(disk_max) AS max_disk,
  any_value(index_names) AS indexes_used
FROM slow_query_logs
WHERE date IN ('<UTC_YYYYMMDD>', '<UTC_YYYYMMDD>')
  AND time >= <UTC_START_UNIX>
  AND time < <UTC_END_UNIX>
  AND digest = '<TARGET_DIGEST>'
GROUP BY digest
```

Adapt the query to the actual schema and Data Proxy SQL dialect.

## Step 2.4: Select representative executions

Do not use one arbitrary aggregated plan to represent all executions.

Fetch at least:

1. the slowest execution;
2. the execution with the largest `process_keys`;
3. the latest execution.

If plan digest information is available, fetch one representative execution
for each important plan digest.

For each representative execution, collect:

- SQL text;
- decoded execution plan;
- execution time;
- process and wait time;
- backoff;
- total and process keys;
- result rows;
- memory and disk;
- stats information;
- optimizer warnings;
- indexes used.

Always use `decoded_plan`.

Do not use `plan`; it commonly contains only `"default"`.

## Step 2.5: Detect plan variation

Determine whether the digest used more than one execution plan during the
window.

Use, in order of preference:

1. plan digest provided by Slow Query;
2. plan digest from TopSQL;
3. a stable fingerprint derived from normalized `decoded_plan`.

For each important plan variant, compare:

- execution count;
- average latency;
- maximum latency;
- CPU when available;
- processed keys;
- representative plan.

If one plan is consistently better, treat plan stabilization as a potential
Binding use case.

# Phase 3: Collect diagnostic evidence

## Step 3.1: Analyze Slow Query execution details

For each representative execution, inspect:

- total query time;
- compile time;
- process time;
- wait time;
- backoff time and type;
- total keys;
- process keys;
- result rows;
- memory;
- disk;
- warnings;
- indexes used.

Distinguish:

- optimizer or access-path problems;
- execution-engine problems;
- KV wait or backoff;
- lock contention;
- resource saturation;
- disk spill;
- network or storage effects.

Do not force a Binding or Index recommendation when the dominant problem is not
an optimizer access-path problem.

## Step 3.2: Obtain schema

Identify all tables referenced by the target SQL and execution plan.

Preferred read-only source: if any TiDB status HTTP endpoint is reachable,
fetch table schema through TiDB HTTP API:

```text
GET http://<tidb-ip>:10080/schema/<db>/<table>
```

The default TiDB status port is `10080`; clusters may configure a different
status port.

For Dedicated TiDB Cloud clusters, prefer the Dashboard debug_api proxy when
direct TiDB status HTTP access is unavailable or requires cluster TLS:

```text
GET  /debug_api/endpoints
GET  /topology/tidb
POST /debug_api/endpoint
GET  /debug_api/download?token=<token>
```

Use only the read-only endpoint ID `tidb_schema_by_table`. The POST above only
asks the Dashboard proxy to call a read-only TiDB status API and prepare a
download token; do not use mutation endpoint IDs.

Do not use Dashboard debug_api proxy for Premium, Starter, Essential, shared,
or unknown deployment types. Report it as unavailable and use other read-only
evidence sources.

If TiDB HTTP API is unavailable but a prepared read-only SQL connection exists,
obtain:

```sql
SHOW CREATE TABLE <qualified_table>;
```

Use the `SHOW CREATE TABLE` result as the schema source of truth.

It already contains:

- columns and data types;
- primary key and clustered attributes;
- indexes and index column order;
- partition definitions;
- generated columns.

Do not issue redundant schema queries unless `SHOW CREATE TABLE` is incomplete
or unavailable.

If schema cannot be obtained:

- continue Binding analysis when possible;
- lower Index recommendation confidence;
- do not generate definitive `CREATE INDEX` SQL.

## Step 3.3: Obtain statistics

Preferred read-only source: if any TiDB status HTTP endpoint is reachable,
fetch statistics JSON through TiDB HTTP API:

```text
GET http://<tidb-ip>:10080/stats/dump/<db>/<table>
GET http://<tidb-ip>:10080/stats/dump/<db>/<table>/<yyyyMMddHHmmss>
GET http://<tidb-ip>:10080/stats/dump/<db>/<table>/<yyyy-MM-dd HH:mm:ss>
```

For Dedicated TiDB Cloud clusters, prefer the Dashboard debug_api proxy when
direct TiDB status HTTP access is unavailable or requires cluster TLS. Use only
these read-only endpoint IDs:

- `tidb_stats_by_table`
- `tidb_stats_by_table_timestamp`

Do not use Dashboard debug_api proxy for Premium, Starter, Essential, shared,
or unknown deployment types.

Otherwise, obtain the statistics JSON for the involved tables from a
plan_replayer artifact, prepared replay environment, or other available
diagnostic source.

Use statistics metadata or metrics only as supporting evidence.

If available, also collect:

- table row count;
- `modify_count`;
- last analyze time;
- statistics-related warnings or metrics.

The primary analysis is not a checklist of statistics fields. The primary task
is to explain cardinality estimation behavior in the execution plan.

## Step 3.4: Analyze cardinality estimation

Traverse the execution plan from the leaf operators upward.

For each important operator, compare:

```text
estRows
actRows
```

Classify the estimate:

- accurate;
- underestimated;
- severely underestimated;
- overestimated;
- severely overestimated;
- unknown because actual rows are unavailable.

Use a ratio as a diagnostic aid, not an absolute rule.

Examples:

```text
actRows / estRows >= 10
    -> significant underestimation

estRows / actRows >= 10
    -> significant overestimation
```

Find the earliest lower-level operator where a major estimation error appears.

Then determine whether the error caused:

- the wrong access path;
- the wrong join order;
- the wrong join algorithm;
- an undersized build side;
- unexpected intermediate-result amplification;
- an inappropriate plan chosen for skewed parameter values.

Explicitly check for pseudo statistics.

From the stats JSON, examine only the information necessary to explain the
estimate, such as:

- missing statistics;
- pseudo statistics;
- histogram coverage;
- TopN coverage for skewed values;
- NDV;
- column correlation;
- statistics/table row-count mismatch.

When `count` and `modify_count` are available, use their relationship as an
auxiliary staleness signal.

Do not diagnose stale statistics from a health percentage alone.

The required reasoning chain is:

```text
statistics state
  -> estimation error
  -> optimizer decision
  -> observed slow execution
```

## Step 3.5: Query TopSQL

Inspect the TopSQL schema before assuming fields exist.

`topsql.date` uses UTC `YYYY-MM-DD`, unlike Slow Query's `YYYYMMDD`.

Query the same SQL digest over the exact UTC window.

When available, collect:

- statement execution count;
- total CPU;
- total duration;
- read keys;
- write keys;
- logical read bytes;
- logical write bytes;
- network input and output;
- plan digest distribution;
- TiDB and TiKV component distribution;
- instance, table, or Region distribution when relevant.

Use TopSQL to answer:

1. Is the slow execution isolated or representative?
2. Is the SQL high frequency?
3. How much total CPU or IO does it consume?
4. Does it use multiple plan digests?
5. Is the workload concentrated on TiDB, TiKV, an instance, a table, or a
   Region?

If TopSQL returns no rows, report:

```text
TopSQL data is unavailable, disabled, unsupported, or empty for this window.
The workload-wide impact cannot be fully evaluated.
```

Never interpret missing TopSQL as zero CPU or zero executions.

## Step 3.6: Build the problem profile

Summarize:

- why an individual execution is slow;
- how much workload-wide impact the digest causes;
- whether the plan is stable;
- where cardinality estimation first diverges;
- whether the problem is suitable for Binding;
- whether the problem is suitable for a new Index.

Separate every statement into:

- observed fact;
- inference;
- missing evidence.

# Phase 4: Classify the root cause

Classify the SQL into one or more categories.

## 4.1 Scan amplification

Evidence may include:

```text
process_keys >> result_rows
```

Possible causes:

- missing index;
- ineffective index column order;
- predicate cannot form a range;
- function on an indexed column;
- implicit type conversion;
- low-selectivity index;
- failed partition pruning;
- excessive lookup or table-row fetches.

## 4.2 Cardinality estimation error

Evidence may include:

- `actRows >> estRows`;
- `actRows << estRows`;
- pseudo statistics;
- skewed TopN values;
- missing histogram;
- column correlation;
- stale table statistics;
- parameter-sensitive distribution.

Explain the first operator where the error occurs and the optimizer decision it
affects.

## 4.3 Wrong access path

Examples:

- TableFullScan when a selective range path exists;
- IndexFullScan over a large index;
- wrong index selection;
- expensive IndexLookup;
- inappropriate IndexMerge;
- scan caused by unusable predicates.

## 4.4 Wrong join plan

Inspect:

- join order;
- join algorithm;
- build and probe sides;
- estimated and actual input sizes;
- join key compatibility;
- filter pushdown;
- intermediate row amplification.

## 4.5 Plan instability

Evidence may include:

- multiple plan digests;
- materially different latency between plans;
- version or statistics changes;
- parameter-sensitive behavior;
- existing good and bad plans for the same digest.

## 4.6 Non-optimizer bottleneck

Examples:

- lock wait;
- KV backoff;
- hot Region;
- network wait;
- TiDB or TiKV saturation;
- disk spill;
- storage latency.

When the dominant cause is outside access-path selection, Binding and Index may
both be inappropriate.

# Phase 5: Generate Binding recommendations

## Step 5.1: Decide whether Binding is applicable

Binding is appropriate when:

- a known better plan already exists;
- the SQL has a clear plan regression;
- the optimizer intermittently chooses a bad index;
- join order or join algorithm is demonstrably wrong;
- a fast reversible mitigation is needed;
- the same forced plan is suitable for the relevant parameter range.

Binding is not appropriate when:

- no better plan is known;
- the root cause is a missing access path;
- statistics should be corrected first;
- the SQL is strongly parameter-sensitive;
- the problem is lock, backoff, IO, hotspot, or cluster saturation;
- forcing the plan could harm other parameter values.

The valid conclusion may be:

```text
Binding not recommended.
```

## Step 5.2: Generate candidates

Use only hints supported by the target TiDB version.

Possible candidates include:

- `USE_INDEX`;
- `IGNORE_INDEX`;
- `HASH_JOIN`;
- `INL_JOIN`;
- join order hints;
- other target-version-supported TiDB optimizer hints.

Verify hint names and Binding syntax against the matching TiDB version or source
checkout.

Do not invent syntax from memory.

## Step 5.3: Validate when a prepared environment exists

If a matching local TiDB environment is supplied:

1. Capture the baseline plan.
2. Apply the candidate hint in a test statement or local Binding.
3. Capture the candidate plan.
4. Compare access path, estimates, rows, keys, join order, and operators.
5. Use `EXPLAIN ANALYZE` only when the local data and execution are safe and
   representative.

If no prepared environment exists, set:

```text
validation_status: inferred
```

A lower estimated cost alone is not validation.

## Step 5.4: Select the Binding recommendation

Rank candidates by:

1. root-cause fit;
2. available evidence;
3. local validation;
4. expected benefit;
5. parameter coverage;
6. regression risk;
7. reversibility.

Generate Binding SQL for review only.

# Phase 6: Generate Index recommendations

## Step 6.1: Extract access requirements

From the SQL and plan, identify:

- equality predicates;
- range predicates;
- join keys;
- ordering requirements;
- grouping requirements;
- projected columns relevant to covering.

Do not apply a fixed index-column ordering mechanically.

Consider:

- selectivity;
- predicate combination;
- range cut-off;
- data distribution;
- existing index prefixes;
- lookup cost;
- ordering elimination;
- covering width.

## Step 6.2: Compare with existing indexes

Use `SHOW CREATE TABLE`.

For every candidate, determine:

- whether the same index already exists;
- whether an existing composite index covers it;
- whether the candidate only duplicates an existing prefix;
- whether extending an existing index is better;
- whether the candidate could make an old index redundant;
- whether additional access paths could increase plan instability.

## Step 6.3: Estimate operational cost

Consider:

- table size;
- index width;
- write amplification;
- storage cost;
- DDL duration;
- maintenance cost;
- whether the SQL is frequent enough to justify the index;
- impact on insert, update, and delete workloads.

Use TopSQL execution count and resource consumption when available to estimate
the value of the optimization.

## Step 6.4: Validate when a prepared environment exists

If a matching local TiDB environment is supplied:

1. Capture the baseline plan.
2. Create or simulate the candidate index using available target-version
   capabilities.
3. Refresh relevant local statistics if required.
4. Capture the candidate plan.
5. Compare scan type, processed keys, lookup behavior, sorting, grouping, and
   join strategy.

If no prepared environment exists, set:

```text
validation_status: inferred
```

## Step 6.5: Select the Index recommendation

Rank candidates by:

1. root-cause fit;
2. scan reduction;
3. workload-wide value;
4. overlap with existing indexes;
5. write and storage cost;
6. local validation;
7. regression risk.

The valid conclusion may be:

```text
Index not recommended.
```

# Phase 7: Produce the final report

Use this exact top-level structure.

## Cluster and query context

Include:

- cluster ID;
- cluster name;
- TiDB version;
- business timezone;
- business inspection range;
- UTC Clinic query range;
- target digest;
- representative SQL.

## Problem summary

Include:

- observed symptoms;
- Slow Query evidence;
- TopSQL evidence;
- plan variation;
- cardinality estimation findings;
- likely root cause;
- missing evidence.

## Binding recommendation

Include:

```text
Conclusion:
Recommended / Not recommended

Candidate hint:
Candidate Binding SQL:

Reason:
Current plan:
Expected plan:
Expected benefit:

Validation status:
Verified / Partially verified / Inferred

Applicable parameter range:
Risks:
Missing evidence:
```

Do not emit executable-looking Binding SQL without the warning:

```text
Review only. Not executed by AutoX.
```

## Index recommendation

Include:

```text
Conclusion:
Recommended / Not recommended

Candidate index:
CREATE INDEX ...

Predicate/index mapping:
Existing-index relationship:
Expected plan change:
Expected scan reduction:
Workload-wide value:

Validation status:
Verified / Partially verified / Inferred

Write cost:
Storage cost:
Risks:
Missing evidence:
```

Do not emit executable-looking DDL without the warning:

```text
Review only. Not executed by AutoX.
```

## Final priority

Choose one:

- Binding first, Index later.
- Index first.
- Fix statistics first; neither Binding nor Index is currently recommended.
- Investigate non-optimizer bottleneck; neither is currently recommended.
- More evidence is required.

Explain the priority in one short paragraph.

# Phase 8: Edge cases

| Condition | Required handling |
|---|---|
| Timezone missing | Confirm timezone before interpreting user-provided dates |
| Clinic API fails | Stop and report collection failure |
| Slow Query returns no rows | Report no matching slow query in the exact UTC window |
| SQL text matches multiple digests | Ask the user to select a digest |
| `decoded_plan` missing | Continue with lower confidence |
| `plan` equals `"default"` | Ignore it; do not treat it as a real plan |
| Schema unavailable | Do not produce a definitive Index DDL |
| Stats JSON unavailable | Mark estimation diagnosis incomplete |
| Pseudo stats detected | Explain its effect on estimates |
| TopSQL unavailable | Mark workload-wide impact unknown |
| Multiple plan digests | Analyze the important variants separately |
| Local TiDB unavailable | Mark candidates inferred |
| Local TiDB version mismatch | Treat results as advisory only |
| Root cause is non-optimizer | Binding and Index may both be not recommended |
| Data Proxy returns `error` | Do not interpret it as an empty result |
| Numeric fields are empty strings | Convert defensively; do not crash or invent zero |

# Script guidance

Run `scripts/collect_slow_sql.py` for deterministic Clinic collection. Reuse
this bundled script instead of generating temporary Python collectors.

The Clinic collection script:

1. Import and reuse `clinic-api/scripts/clinic_api.py`.
2. Validate Clinic authentication.
3. Resolve the exact cluster ID.
4. Convert user time and timezone into UTC.
5. Calculate Slow Query and TopSQL UTC partitions.
6. Inspect the Data Proxy schema.
7. Accept a digest or return ranked digest candidates when it is omitted.
8. Query digest aggregates.
9. Query representative Slow Query executions.
10. Query TopSQL for the same digest.
11. Preserve API errors explicitly.
12. Output structured JSON for this Skill.

Run `scripts/collect_tidb_http_table.py` when the user provides a reachable
TiDB status HTTP endpoint and table identity. It collects table schema and
statistics through documented TiDB HTTP `GET` APIs only.

Example:

```bash
python3 scripts/collect_tidb_http_table.py \
  --tidb-http "http://<tidb-ip>:10080" \
  --db "<db>" \
  --table "<table>"
```

For historical statistics accepted by the TiDB HTTP API:

```bash
python3 scripts/collect_tidb_http_table.py \
  --tidb-http "http://<tidb-ip>:10080" \
  --db "<db>" \
  --table "<table>" \
  --stats-time "2026-06-23 15:30:00"
```

This script must not issue `POST`, connect through the MySQL SQL protocol, or
call mutating TiDB HTTP endpoints.

Run `scripts/collect_dashboard_debug_api_table.py` for Dedicated TiDB Cloud
clusters when Clinic Dashboard can access the TiDB status endpoint but the
agent cannot access it directly. Do not use it for Premium, Starter,
Essential, shared, or unknown deployment types. It follows the Dashboard UI
flow:

1. resolve `org_id` from Clinic metadata when not provided;
2. verify the cluster deployment type is `dedicated`;
3. call Dashboard proxy `GET /debug_api/endpoints`;
4. call Dashboard proxy `GET /topology/tidb`;
5. choose an Up TiDB `ip:status_port` from topology;
6. call Dashboard proxy `POST /debug_api/endpoint` only for read-only endpoint
   IDs;
7. download the generated JSON through `GET /debug_api/download?token=...`.

Example:

```bash
python3 scripts/collect_dashboard_debug_api_table.py \
  --cluster-id <cluster_id> \
  --db "<db>" \
  --table "<table>" \
  --output-dir /tmp
```

If the Dashboard URL already contains `orgId`, pass it explicitly:

```bash
python3 scripts/collect_dashboard_debug_api_table.py \
  --org-id <dashboard_org_id> \
  --cluster-id <cluster_id> \
  --db "<db>" \
  --table "<table>"
```

The Dashboard proxy script must not use debug_api mutation endpoints. Allowed
endpoint IDs are:

- `tidb_schema_by_table`
- `tidb_stats_by_table`
- `tidb_stats_by_table_timestamp`

Suggested interface:

```bash
python3 scripts/collect_slow_sql.py \
  --cluster-id <cluster_id> \
  --digest <digest> \
  --start "<business start time>" \
  --end "<business end time>" \
  --timezone "Asia/Shanghai"
```

For the default rolling 24-hour window:

```bash
python3 scripts/collect_slow_sql.py \
  --cluster-id <cluster_id> \
  --digest <digest>
```

With only the required `cluster_id`:

```bash
python3 scripts/collect_slow_sql.py \
  --cluster-id <cluster_id>
```

This returns ranked digest candidates. Add
`--include-lock-details` only when the base evidence suggests transaction
retry, `FOR UPDATE`, lock wait, or lock-related runtime plan operators.

The script reads Clinic credentials from `.env` by default. Use
`--env-file <path>` to select another file. If `clinic-api` is not installed in
a standard Skill location, pass `--clinic-api-root <path>`.

The script must not:

- diagnose the root cause;
- generate hints;
- generate indexes;
- connect to production TiDB directly;
- execute Binding SQL;
- execute DDL.

Expected JSON shape:

```json
{
  "query_window": {
    "business_timezone": "Asia/Shanghai",
    "business_start": "2026-06-22T00:00:00+08:00",
    "business_end": "2026-06-23T00:00:00+08:00",
    "utc_start": "2026-06-21T16:00:00Z",
    "utc_end": "2026-06-22T16:00:00Z",
    "slow_query_partitions": ["20260621", "20260622"],
    "topsql_partitions": ["2026-06-21", "2026-06-22"]
  },
  "cluster": {
    "cluster_id": "",
    "cluster_name": "",
    "tidb_version": "",
    "status": "",
    "deployment_type": "",
    "provider": "",
    "region": ""
  },
  "target": {
    "digest": "",
    "sample_sql": ""
  },
  "slow_query": {
    "summary": [],
    "representative_executions": {},
    "plan_variants": []
  },
  "topsql": {
    "available": false,
    "summary": [],
    "plan_variants": []
  },
  "errors": []
}
```

Keep script output factual. Perform all diagnosis and recommendations in the
Skill.
