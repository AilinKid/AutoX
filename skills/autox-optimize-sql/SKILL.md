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

## External and local validation environment

The production target cluster is read-only. AutoX must not modify it.

For local validation, AutoX may use a local TiDB environment when the user has
approved it or when the workspace already contains the needed binaries/source.
Call this the `local tidb env`.

Optional local inputs include:

- a TiDB binary or source checkout matching the target cluster version;
- a local standalone TiDB process using the default local storage engine, not
  TiKV;
- exported schema JSON and statistics JSON;
- a schema/statistics replay workspace;
- `json2schema` from `https://github.com/time-and-fate/json2schema`.

The local TiDB version must match the target cluster TiDB version as closely as
possible. If it does not match, mark all validation as advisory.

The local TiDB env may be started, stopped, and cleaned up only on the local
machine. Never point local validation commands at the production cluster.

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

Exception: local-only DDL in the `local tidb env` is allowed for validation,
including generated `CREATE TABLE`, `LOAD STATS`, hypothetical index
statements, and hypothetical TiFlash replica statements. This exception never
applies to the target cluster.

# Phase 0: Pre-check and input confirmation

Complete this phase before querying Clinic.

When the user provides a `cluster_id` and a SQL digest, treat that as sufficient
authorization to run the read-only diagnostic workflow to completion and produce
recommendations. Do not stop mid-workflow to ask the user to confirm optional
inputs such as time range, local TiDB availability, source checkout, schema
files, or whether to continue.

This Skill is an oncall workflow. Move quickly from evidence collection to
analysis to final recommendations. Use sensible defaults and mark missing or
unavailable evidence explicitly.

Only ask a blocking question when a required input is missing or ambiguous, such
as no `cluster_id`, no way to identify the target digest/query, or multiple
possible target clusters with the same identifier. Do not ask for confirmation
before read-only Clinic queries, dashboard debug API downloads, local static
`EXPLAIN`, or generating review-only SQL.

Never use this autonomy to perform production mutations. Binding SQL, Index DDL,
settings, and TiFlash replica changes are always review-only unless the user
separately and explicitly asks for execution.

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

## Step 2.6: Historical plan comparison

Before generating new Binding or Index ideas, answer:

```text
Are all executions slow, or only some plan shapes / parameter shapes slow?
```

Slow Query is biased toward slow executions. A better plan may be faster and
therefore absent from Slow Query. When Slow Query does not show enough plan
diversity, also inspect statement summary and TopSQL data exposed through Clinic
Data Proxy, after checking the available schema.

For the target digest, group executions by plan digest or normalized plan
fingerprint and compare:

- execution count and slow-query count;
- average, p95, and maximum latency when available;
- total duration or CPU contribution;
- representative SQL parameters or tenant/table suffixes when visible;
- plan tree shape;
- logical join order and physical join algorithm;
- build/probe side and outer-row count;
- first access table or driving table;
- access path for every table;
- pushed-down predicates and residual `Selection`;
- estimated rows and actual rows where `EXPLAIN ANALYZE` evidence exists;
- processed keys, total keys, scan bytes, read bytes, and memory/disk.

For every important variant, explain why it is better or worse. Useful signals
include:

- a better logical join order caused by different base-table cardinality
  estimates;
- more tables using their own selective access conditions before joining;
- avoiding a large outer side that drives many IndexJoin probes;
- avoiding lookup or probe amplification;
- effective TiFlash MPP full scan when a table has no useful access predicate
  and the scan is small enough or well-pruned;
- lower processed keys per returned row;
- lower actual latency under comparable parameters.

If an existing historical plan is materially better, prefer it as the first
candidate for stabilization. Derive Binding or hint candidates from that known
plan shape before inventing a new plan.

If the better plan appears only in statement summary or TopSQL and lacks full
runtime plan details, mark the comparison as `inferred` and list the missing
evidence. Do not claim it is verified until a representative plan and runtime
evidence are available.

Example judgment:

- Bad shape: a large filtered table becomes the outer input, causing many
  IndexJoin probe tasks and high KV read time.
- Better historical shape: the table with no useful access predicate is chosen
  first and read through TiFlash MPP, while the other tables still use their own
  index access conditions. This can reduce outer-row probe amplification and be
  a better plan both logically and in observed runtime.

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

## Step 3.6: Locate the execution bottleneck

After historical plan comparison, locate the bottleneck in the current slow
plan before deciding whether the remedy is Binding, Index, statistics, rewrite,
or MPP/TiFlash.

Use this order:

1. If the SQL has joins or correlated subqueries, analyze join bottlenecks first.
2. If join order is bad, trace it back to base-table logical cardinality
   estimates and statistics quality.
3. If logical join order is reasonable, analyze the physical join type:
   HashJoin, IndexJoin, IndexHashJoin, MergeJoin, Apply, SemiJoin, AntiSemiJoin,
   and their build/probe sides.
4. If the SQL is simple or join is not the bottleneck, analyze single-table
   access-path efficiency.
5. If the SQL has `ORDER BY`, `LIMIT`, `TopN`, window ordering, ordered
   aggregation, or a plan with `keep order:true`, analyze the order-preserving
   path.
6. Finally classify the low-level bottleneck as:
   - too many rows or bytes must objectively be read;
   - too many cop requests, Region seeks, point/range probes, or lookup tasks
     are generated.

For join-heavy plans, inspect:

- whether the optimizer sorted base relations by reasonable logical estimates;
- which table becomes the first/outer/driving side;
- whether each base table can apply its own selective predicates before joining;
- whether a large outer side drives many IndexJoin or Apply probe tasks;
- whether the probe side performs repeated index range scans, table lookups, or
  complex pushed-down work;
- `inner.total`, `fetch`, `build`, `join`, `probe`, `task`, `concurrency`, and
  cop task counts in `execution info`;
- per-probe `process_keys`, `total_keys`, read bytes, RocksDB read time, and
  `max/p95` cop task latency.

IndexJoin and Apply bottlenecks are often amplification problems. Explain:

```text
outer rows
  -> probe task count / cop request count
  -> keys or bytes read per probe
  -> total KV/TiKV wall time
  -> observed latency
```

For single-table or access-path bottlenecks, inspect:

- existing indexes and their column order;
- which predicates become index access conditions;
- which predicates remain residual filters;
- why residual filters cannot become access conditions: column order, range
  cut-off, expression/function, implicit cast, collation/type mismatch, prefix
  index, OR condition, non-sargable predicate, or unsupported pushdown;
- index scan rows versus table lookup rows;
- whether IndexLookup amplification dominates;
- whether IndexMerge could combine multiple selective predicates better than a
  single weak access path;
- whether a full scan or MPP scan is preferable because index selectivity is too
  low.

Do not assume TiKV index access is always the right answer. If the query must
read a large fraction of a table, or every candidate index still has poor
selectivity, TiFlash MPP may be the better plan when TiFlash replicas exist and
the plan can benefit from parallel scan, pushed-down filters, joins, aggregation,
or exchange.

For order-sensitive plans, trace the complete order-preserving path from the
root requirement down to the access path that supplies order. Do not assume the
order supplier is adjacent to `Limit`, `TopN`, or `Selection`; order can be
passed through several physical operators.

Answer:

- Is ordering produced by an explicit `Sort` or `TopN`, or naturally supplied by
  an ordered table/index access path?
- Which access path is chosen mainly to satisfy ordering?
- Does that choice prevent a more selective filter index or access path?
- Is there a residual `Selection` above the ordered scan whose actual rows are
  much smaller than the ordered scan output?
- Does `LIMIT` rely on early shutdown, and does skew make early shutdown fail?
- Would a non-ordered but more selective access path plus explicit `Sort` or
  `TopN` read less data overall?
- Would a composite index that satisfies both filtering and ordering be the best
  direction?
- In a join plan, which operators preserve or destroy order between the order
  supplier and the root requirement?

For `LIMIT + filter + ordered index` patterns, compare:

```text
ordered index scan actual rows / process_keys / read bytes
  -> rows after Selection
  -> LIMIT count
```

If the ordered scan reads many rows before finding enough qualifying rows, the
optimizer may have overvalued early shutdown. This is often a skew problem:
the order index looks attractive, but the filter values are sparse or clustered
unfavorably in that order.

When a matching TiDB source checkout is available, verify order propagation
against the target-version source instead of relying on a fixed memory-based
operator list. Start from:

- `pkg/planner/property/physical_property.go` for `SortItems`,
  `AdvisorySortItems`, partial order, and `NeedKeepOrder`;
- `pkg/planner/core/task.go` for `KeepOrder`, TopN/Limit pushdown, and access
  path order handling;
- `pkg/planner/core/optimizer.go` for Apply/order behavior such as reorder
  buffering;
- target-version physical operator implementations for child required
  properties and order preservation.

## Step 3.7: Build the problem profile

Summarize:

- why an individual execution is slow;
- how much workload-wide impact the digest causes;
- whether the plan is stable;
- the dominant execution bottleneck;
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

or:

```text
scan/read bytes are high
IndexLookup/table lookup rows are high
IndexRangeScan output is much larger than rows after Selection
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

Distinguish unavoidable large reads from avoidable scan amplification. If the
query legitimately needs a large fraction of the data, a narrower index may not
help enough; consider whether TiFlash MPP or aggregation/join pushdown is the
better direction.

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

For join plans, base-table logical estimates are especially important because
they directly influence join order. If stale or skewed statistics make one base
table look much smaller or larger than it really is, expect the chosen join
order to be suspect.

## 4.3 Wrong access path

Examples:

- TableFullScan when a selective range path exists;
- IndexFullScan over a large index;
- wrong index selection;
- expensive IndexLookup;
- inappropriate IndexMerge;
- scan caused by unusable predicates.

For every wrong-access-path diagnosis, document:

- current index access conditions;
- residual filters that could not become access conditions;
- the exact reason each important filter is not usable as index access;
- existing indexes that were considered;
- whether a new composite index, extending an existing index, IndexMerge, or
  TiFlash MPP is the more plausible direction.

## 4.4 Wrong join plan

Inspect:

- join order;
- join algorithm;
- build and probe sides;
- estimated and actual input sizes;
- join key compatibility;
- filter pushdown;
- intermediate row amplification.

Analyze join problems in two layers.

Logical layer:

- Did the optimizer choose a reasonable join order from base-table estimates?
- Are the base estimates wrong because statistics are stale, missing, pseudo, or
  skewed?
- Does the chosen driving table have too many actual rows after filters?
- Are selective predicates applied before the join, or delayed until after a
  large intermediate result is formed?

Physical layer:

- If the logical order is reasonable, is the physical join algorithm reasonable?
- Does IndexJoin or Apply create many probe tasks or cop requests?
- Does the probe side perform expensive range scans, table lookups, or complex
  residual filtering for each outer batch?
- Would HashJoin, IndexHashJoin, MergeJoin, a different build/probe side, or MPP
  join avoid probe amplification?

When reporting IndexJoin or Apply bottlenecks, include outer rows, probe task
count, cop request count, keys/bytes read on the probe side, and whether the
probe side is simple index access or complex access plus filter/lookup.

## 4.5 Plan instability

Evidence may include:

- multiple plan digests;
- materially different latency between plans;
- version or statistics changes;
- parameter-sensitive behavior;
- existing good and bad plans for the same digest.

## 4.6 Cop request and seek amplification

Evidence may include:

- high cop task count or RPC count relative to returned rows;
- many IndexJoin or Apply probe tasks;
- high `max/p95` cop task latency with many small ranges;
- high RocksDB seek/read activity;
- large `total_keys` relative to `process_keys` or result rows;
- high `tikv_wall_time` mostly accumulated across many requests;
- latency dominated by probe fetch rather than join CPU.

This is a TiDB/TiKV architecture-sensitive bottleneck: even if each individual
probe is small, many Region/range seeks and cop requests can queue and dominate
latency.

Possible directions:

- reduce outer rows before probe;
- change join order or join algorithm;
- make the probe side more selective or covering;
- batch or rewrite correlated Apply patterns;
- use MPP/TiFlash when data volume is large and index probes are not selective;
- avoid forcing IndexJoin when the probe side is complex or poorly selective.

## 4.7 Order-preserving access path tradeoff

Evidence may include:

- `ORDER BY`, `LIMIT`, `TopN`, ordered aggregation, window ordering, or
  `keep order:true` in the plan;
- an index/table path chosen mainly because it can provide order;
- a residual `Selection` above an ordered scan;
- scan actual rows, `process_keys`, or read bytes much larger than rows after
  the residual filter;
- low `LIMIT` count but high ordered-scan work;
- skewed distribution where qualifying rows are sparse in the chosen order;
- a selective alternative index exists but would require explicit `Sort` or
  `TopN`.

This problem is an order-vs-filter tradeoff. The optimizer may choose an ordered
path expecting `LIMIT` to stop early, but skew can make it scan far more rows
than expected before enough rows pass the filter.

Analyze both options:

1. Ordered path:
   - avoids or reduces explicit `Sort`/`TopN`;
   - may read many rows that fail filters.
2. Filter path:
   - uses a more selective access condition;
   - may require explicit `Sort`/`TopN`;
   - can still be faster when it dramatically reduces rows before sorting.

Possible directions:

- use or create a composite index that matches both filtering and ordering;
- prefer a selective filter index plus explicit `Sort`/`TopN`;
- use hints or Binding only if a better historical ordered/non-ordered plan is
  proven suitable for the parameter range;
- update statistics or extended statistics when skew/correlation causes wrong
  early-shutdown estimates;
- consider MPP/TiFlash when the post-filter data volume is still large and
  ordering can be handled efficiently after parallel filtering.

For join plans, identify the full order-preservation chain. Some operators may
preserve a child's order under specific physical-property requirements, while
others destroy order and require a new Sort/TopN. Verify this against the
target-version source when it materially affects the recommendation.

## 4.8 Non-optimizer bottleneck

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
- historical plan comparison finds a materially better plan shape for the same
  digest;
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
- storage-engine hints when the better historical plan intentionally uses TiKV
  or TiFlash for a specific table and the target TiDB version supports the hint;
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
2. whether the candidate reproduces a known better historical plan;
3. available evidence;
4. local validation;
5. expected benefit;
6. parameter coverage;
7. regression risk;
8. reversibility.

Generate Binding SQL for review only.

# Phase 6: Generate Index recommendations

Before generating a new index, follow this decision order:

1. If historical plan comparison found a materially better plan, prefer
   stabilizing that known plan through Binding or hints.
2. If bottleneck analysis suggests a specific index can improve access, validate
   that candidate index in the local TiDB env with schema, stats, and
   hypothetical index.
3. If no good historical plan exists and no index candidate is convincing,
   evaluate whether TiFlash/MPP is a better direction with hypothetical TiFlash
   replicas in the local TiDB env.
4. If there is still no clear index or TiFlash direction, use local
   `EXPLAIN EXPLORE` as the final fallback to search for alternative plans.
5. If local validation cannot reproduce the expected index, MPP, or explored
   plan, report the idea as inferred and request production-safe validation
   rather than presenting it as verified.

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

When `ORDER BY`, `LIMIT`, or `TopN` exists, do not mechanically prioritize
ordering columns over selective filters. Evaluate:

- whether the candidate index supplies order, filter, or both;
- whether ordering columns before filtering columns would force a large scan;
- whether filtering columns before ordering columns would require an explicit
  `Sort`/`TopN` but reduce rows enough to be faster;
- whether data skew makes `LIMIT` early shutdown unreliable;
- whether the SQL needs a composite index that supports both the selective
  predicates and the required order;
- whether the plan could benefit from a non-ordered selective path plus TopN,
  rather than an ordered weakly selective path.

### Selection-to-access-path candidates

When a `Selection` sits immediately above an `IndexRangeScan` or `TableRangeScan`,
do not mechanically recommend adding the `Selection` predicate column into the
index access path.

First classify whether the predicate is a broad optimization or only a partial
optimization:

1. Check whether moving the predicate into index access can actually narrow the
   scan range. It is usually useful only when preceding index columns are bound
   by equality or a tight range that still allows the predicate column to
   participate in the access range.
2. Compare `actRows`, `process_keys`, `total_keys`, and scan bytes before and
   after the `Selection`. A useful signal is a meaningful drop between the scan
   output and the rows that survive the `Selection`.
3. Check whether this access path is a dominant latency contributor. If most
   time is spent in a different join probe, lookup, Sort, Agg, TiFlash exchange,
   lock/backoff, or cluster-level bottleneck, the index change may be secondary.
4. Look for same-shape evidence across related plans or tenants when available.
   If the same `Selection` predicate barely reduces rows in comparable plans,
   classify the candidate as partial or workload-dependent.
5. Use schema and stats JSON to confirm cardinality, histogram/CMSketch/top-N,
   and correlation when available. Do not rely only on column names such as
   `site_code`, `tenant_id`, or `currency`.

Example judgment:

- If `IndexRangeScan(create_ymd, currency, user_idx, site_code)` scans about
  479k rows for one day and the parent `Selection(site_code = ...)` leaves about
  108k rows, adding or reordering `site_code` into the useful access prefix may
  reduce scan work for that tenant/query shape.
- If a same-shape plan scans about 145k rows and the parent
  `Selection(site_code = ...)` also leaves about 145k rows, the same idea is only
  a partial optimization and must not be presented as generally effective.

In the report, explicitly say when such an index is a partial optimization:
describe which predicates/tenants benefit, which comparable evidence does not
benefit, and what validation is still required before DDL.

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

## Step 6.4: Validate index candidates in local tidb env

When analysis suggests a candidate index may improve the slow query, validate it
in a local TiDB environment before presenting it as more than an inferred idea.

Use the `local tidb env`:

1. Start a local standalone TiDB node whose version matches the target cluster.
   Use TiDB's default local storage; do not start TiKV.
2. Convert every involved `tidb_schema_by_table` JSON file into `CREATE TABLE`
   SQL using `json2schema`:

   ```bash
   go build .
   ./json2schema tidb_schema_by_table_1688114034.json
   ```

   Run this according to the `json2schema` README. Capture the generated DDL as
   evidence.
3. Execute the generated `CREATE DATABASE` / `CREATE TABLE` statements in the
   local TiDB env.
4. Load the corresponding statistics JSON after schema creation:

   ```sql
   LOAD STATS '<stats-json-file>';
   ```

   Load stats before creating hypothetical indexes so the optimizer evaluates
   candidates against production-like statistics.
5. Capture the local baseline `EXPLAIN` for the target SQL with the loaded
   schema and stats.
6. Simulate the candidate index with the target-version hypothetical index
   feature. Confirm syntax against the matching TiDB source or tests. In current
   TiDB versions the syntax is:

   ```sql
   CREATE INDEX <hypo_index_name> TYPE HYPO ON <db>.<table>(<columns>);
   DROP HYPO INDEX <hypo_index_name> ON <db>.<table>;
   ```

7. Capture the local candidate `EXPLAIN`.
8. Compare the local baseline and candidate plans:
   - whether the candidate index is selected;
   - access object and range;
   - keep order / Sort / TopN changes;
   - join order and join algorithm;
   - estimated rows and cost;
   - whether the plan matches the expected mechanism.
9. Save the generated DDL, loaded stats filenames, hypothetical index DDL,
   baseline `EXPLAIN`, and candidate `EXPLAIN` as evidence.

If no prepared environment exists, set:

```text
validation_status: inferred
```

If local TiDB validation succeeds, set:

```text
validation_status: locally verified by EXPLAIN
validation_source: local tidb env
```

Do not mark it `Verified` unless production-safe runtime validation or a
representative `EXPLAIN ANALYZE` exists. Local `EXPLAIN` with loaded statistics
proves only that the optimizer can choose the expected static plan under the
local schema and stats; it does not prove actual runtime improvement.

If the candidate index is not selected in local `EXPLAIN`, do not recommend it
as the primary Index recommendation unless there is a clear explanation, such as
missing session variables, version mismatch, incomplete stats, or a different
candidate that should be tested.

## Step 6.5: Validate TiFlash or MPP candidates in local tidb env

Use this step when:

- historical plan comparison does not find a good plan to stabilize;
- no candidate index has a convincing mechanism, or local hypothetical-index
  validation does not choose the expected plan;
- bottleneck analysis suggests the query reads a large volume of data, index
  selectivity is weak, probe amplification is high, or MPP may outperform TiKV
  index access.

First collect TiFlash availability evidence:

- cluster topology: whether TiFlash nodes exist;
- table metadata/schema: whether involved tables already have TiFlash replicas;
- historical plans: whether the digest has ever used `mpp[tiflash]`;
- slow plan evidence: whether TiKV index access is doing large reads or many
  probes that MPP could avoid.

If historical plan comparison found a better hybrid TiFlash plan, reproduce that
plan shape as closely as possible. Do not automatically force all involved
tables to TiFlash. The default validation target is the historical shape, not a
new all-in MPP shape.

Build a per-table storage map from the historical good plan:

```text
table alias -> historical storage path
a -> TiKV index / TiKV table / TiFlash MPP
p -> TiKV index / TiKV table / TiFlash MPP
c -> TiKV index / TiKV table / TiFlash MPP
```

When validating locally, apply `READ_FROM_STORAGE(TIFLASH[...])` only to the
aliases that used TiFlash in the good historical plan. Leave aliases that used
TiKV index access on TiKV, and preserve their useful index paths when possible.
For example, if the good plan used TiFlash only for alias `p`, validate with:

```sql
/*+ READ_FROM_STORAGE(TIFLASH[p]) */
```

and not:

```sql
/*+ READ_FROM_STORAGE(TIFLASH[a,p,c]) */
```

All-in TiFlash may be a materially different candidate plan and should not be
used as evidence for a historical p-only hybrid plan.

Extra TiFlash validation for other aliases is allowed only when Step 3.6
bottleneck analysis provides a concrete reason. For example, if an alias that
used TiKV in the historical good plan now has weak index access, many lookup
tasks, poor access/filter selectivity, large read bytes, or high cop/seek
amplification, run an additional candidate validation for that alias's TiFlash
path. Report it as a separate candidate, not as the historical-plan validation.

The two valid reasons to choose a TiFlash validation shape are:

1. `history plan cmp`: the shape closely follows a better historical plan;
2. `skill infer`: Step 3.6 bottleneck analysis identifies another table whose
   TiKV access path is likely inefficient and worth testing with TiFlash.

When both exist, validate and report them separately:

```text
Candidate A:
  source: historical plan
  validation shape: TIFLASH[p]
  strategy: history plan cmp

Candidate B:
  source: bottleneck analysis
  validation shape: TIFLASH[p,c] or TIFLASH[c]
  strategy: skill infer
```

Do not merge these into one conclusion. The historical-shape candidate answers
"can we stabilize a known better plan?" The analysis-driven candidate answers
"is there an even better plausible plan based on the current bottleneck?"

If production metadata shows the relevant tables already have available
TiFlash replicas, do not diagnose the issue as missing replicas. Diagnose it as
the optimizer cost model not choosing the TiFlash/hybrid path, unless other
evidence shows replica unavailability, lag, or topology problems. In that case,
the likely operational action is reviewed hint or Binding validation, not adding
replicas.

Then validate locally:

1. Use the same local TiDB env prepared for schema and stats validation.
2. Load schema and stats first.
3. Add a hypothetical TiFlash replica for each involved table that should be
   considered for MPP. Confirm syntax against the target TiDB version. In
   current TiDB versions:

   ```sql
   ALTER TABLE <db>.<table> SET HYPO TIFLASH REPLICA 1;
   ALTER TABLE <db>.<table> SET HYPO TIFLASH REPLICA 0;
   ```

4. Run candidate `EXPLAIN <sql>`.
5. Check whether the plan uses the expected MPP shape, for example
   `mpp[tiflash]`, `ExchangeSender`, `TableFullScan`/`Selection`/`HashJoin`
   pushed to TiFlash, and a lower-cost plan consistent with the bottleneck.
6. Save baseline and hypothetical TiFlash `EXPLAIN` as evidence.

If local hypothetical TiFlash validation produces the expected MPP plan, the
recommendation may be:

```text
Consider TiFlash / MPP.
validation_status: locally verified by EXPLAIN
validation_source: local tidb env
```

Phrase the operational recommendation carefully. Depending on current topology
and table metadata, the action might be:

- add TiFlash capacity/nodes;
- add TiFlash replicas for the involved tables;
- adjust query hints or create a reviewed Binding to select the proven hybrid
  plan shape;
- validate MPP behavior in production with safe `EXPLAIN` before rollout.

If the table already has TiFlash replicas in production but the optimizer still
does not choose MPP, and local validation also cannot make the desired MPP plan
appear, do not claim local validation success. Mark it:

```text
validation_status: inferred
validation_source: local tidb env could not verify
```

In that case, recommend that the user run a production-safe validation, such as
`EXPLAIN` under reviewed settings/hints, and clearly state that the MPP
recommendation is inferred from bottleneck analysis rather than locally
verified.

Do not recommend TiFlash/MPP when:

- the query is point/range selective and TiKV index access is already cheap;
- MPP would require scanning much more data without compensating parallelism;
- the cluster lacks TiFlash capacity and the workload value does not justify
  adding it;
- the local plan only improves estimated cost without matching the expected
  execution mechanism.

## Step 6.6: Run local plan explore as final fallback

Use this step only when all of the following are true:

1. historical plan comparison did not find a good plan to stabilize;
2. bottleneck analysis did not produce a convincing index idea;
3. bottleneck analysis did not produce a convincing TiFlash/MPP idea, or local
   hypothetical TiFlash validation did not produce the expected MPP plan;
4. schema and stats have already been loaded into the local TiDB env.

Run `EXPLAIN EXPLORE` in the same local TiDB env that already has the generated
schema and loaded statistics:

```sql
EXPLAIN EXPLORE <sql>;
```

When the target TiDB version supports it, `EXPLAIN EXPLORE '<digest>'` or
`EXPLAIN EXPLORE REPLAYER '<replayer-file>'` may also be used, but prefer the
exact SQL text when it is available and representative.

Do not run `EXPLAIN EXPLORE ANALYZE` unless local data has intentionally been
loaded and execution is safe. The normal AutoX local validation path uses static
`EXPLAIN EXPLORE` only.

Inspect the explored candidates:

- candidate plan text;
- plan digest;
- estimated cost/latency fields when present;
- generated candidate hint or binding SQL when present;
- access path changes;
- join order and join algorithm changes;
- order-preserving path changes;
- TiKV vs TiFlash / MPP changes;
- whether the candidate's mechanism matches the diagnosed bottleneck.

If `EXPLAIN EXPLORE` finds a plausible better plan, report it as:

```text
validation_status: locally explored by EXPLAIN EXPLORE
validation_source: local tidb env
strategy: plan explore
```

Do not automatically execute generated `EXPLAIN ANALYZE` statements or
`CREATE GLOBAL BINDING` statements returned by `EXPLAIN EXPLORE`. They are
review-only evidence.

If `EXPLAIN EXPLORE` returns no better candidate, say so explicitly and set the
recommendation to `More evidence is required` or the most appropriate
not-recommended conclusion.

## Step 6.7: Select the Index recommendation

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

Use exactly four top-level sections in the final report:

1. `Conclusion`
2. `Evidence`
3. `Local Validation`
4. `Recommendation`

Write the report as a factual diagnosis, not a process log. Do not use
first-person self-narration such as "I tried", "I later found", or "the previous
direction was wrong". Do not add separate `Not Recommended` or
`Missing Evidence` sections. Put caveats, risks, and missing production
validation inside `Recommendation`.

Every recommendation must include provenance inside the `Recommendation`
section:

```text
Provenance:
- Recommendation source: history plan / local tidb env / skill inference / production evidence
- Strategy: history plan cmp / skill infer / plan explore
- Validation status: production verified / locally verified by EXPLAIN / locally explored by EXPLAIN EXPLORE / partially verified / inferred
- Production safety: review only; AutoX did not execute binding, create indexes, modify TiFlash replicas, or change production settings.
```

Use:

- `history plan cmp` when the recommendation comes from comparing existing good
  and bad historical plans;
- `skill infer` when the recommendation comes from bottleneck analysis,
  optionally validated by local hypothetical index or hypothetical TiFlash
  `EXPLAIN`;
- `plan explore` when the recommendation comes from local `EXPLAIN EXPLORE`.

## 1. Conclusion

Include:

```text
Recommended action:
Binding first / Index first / TiFlash or MPP validation first / Plan explore
candidate first / Fix statistics first / Investigate non-optimizer bottleneck /
More evidence is required

Recommended plan shape:
- <alias/table>: <expected storage path and index/table access>
- <join>: <expected join type and build/probe behavior>

Why:
<one short paragraph that names the main mechanism>
```

For a historical hybrid TiFlash plan, state the exact per-alias shape. Example:

```text
Recommended plan shape:
- a = dh_user_day_report: TiKV index access on udx_ymd_currency_user_site(...)
- p = dh_account_ext_parentinfo: TiFlash scan with pushed filter p.site_code = ?
- a LEFT JOIN p: HashJoin
- c = dh_account_basic: TiKV covering index access on idx_uidx_sc_uname_rgid(...)
```

## 2. Evidence

Always include these fixed evidence blocks. Fill unknown fields with
`unknown` or `unavailable`; do not drop the field.

```text
Cluster and SQL:
- Cluster:
- TiDB version:
- Deployment type:
- Digest:
- SQL:

Current slow plan:
- Main bottleneck:
- Slow operator:
- Probe side:
- Process keys:
- Total keys:
- Cop tasks:
- Query time:
- Plan digest:

Best historical plan:
- Plan source:
- Query time:
- Plan digest:
- Key difference:

TiFlash availability:
- Cluster has TiFlash nodes:
- Involved tables have TiFlash replicas:

Interpretation:
<one short paragraph; for example, replica exists so the issue is plan selection,
not missing replica>
```

If no good historical plan exists, replace `Best historical plan` with the most
relevant bottleneck evidence from Step 3.6 but keep the block title and set:

```text
Best historical plan:
- Plan source: unavailable
- Query time: unavailable
- Plan digest: unavailable
- Key difference: no better historical plan found; recommendation is based on
  bottleneck analysis / local validation / plan explore.
```

## 3. Local Validation

Include local validation only when it was actually run. If it was not run, keep
this section short and state `Not run`.

```text
Validation environment:
- TiDB version:
- Schema source:
- Stats source:
- Validation type: local static EXPLAIN / EXPLAIN EXPLORE / not run

Validated candidate:
<hint, hypothetical index, hypothetical TiFlash shape, or explored candidate>

Observed local plan shape:
- <alias/operator>: <observed path>

Validation result:
Locally verified by EXPLAIN / Locally explored by EXPLAIN EXPLORE / Inferred /
Not verified / Not run

Validation limitation:
Local EXPLAIN verifies optimizer plan shape only. It does not prove runtime
improvement unless representative local execution data exists.
```

Do not claim runtime improvement from local static `EXPLAIN` alone.

## 4. Recommendation

Include one primary recommendation. Add optional stricter or alternative
candidates only when they are useful and clearly labeled.

Do not output concrete hint SQL, Binding SQL, or Index DDL as the primary
recommendation unless static `EXPLAIN`, `EXPLAIN EXPLORE`, production-safe
`EXPLAIN`, or stronger evidence has verified that the candidate produces the
intended plan shape. If a hint idea has not been verified, or if local
validation cannot reproduce the production plan, report it only as a validation
direction and write `none` for candidate SQL. If a tested hint is accepted by
TiDB but produces an unsafe or materially worse plan shape, explicitly report
that it was rejected and do not include it as a candidate for rollout.

```text
Primary recommendation:
<recommended reviewed action>

Candidate hint / Binding SQL / Index DDL:
<review-only SQL or none>

Optional stricter candidate:
<review-only SQL or none>

Caveats:
- <parameter scope, partial optimization scope, missing production EXPLAIN, or
  why not to use all-in TiFlash/add replica/new index as the first action>

Provenance:
- Recommendation source:
- Strategy:
- Validation status:
- Production safety:
```

Any executable-looking SQL must be labeled:

```text
Review only. Not executed by AutoX.
```

For TiFlash recommendations, avoid separate "not recommended" blocks. Put
negative guidance in `Caveats`, for example:

- do not use all-in TiFlash as evidence for a p-only historical hybrid plan;
- do not recommend adding TiFlash replicas when replicas already exist;
- do not choose a new index as the first action when a better historical plan is
  available and locally reproducible.

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
| Only slow plans found in Slow Query | Check statement summary or TopSQL before concluding no better historical plan exists |
| Better plan appears only outside Slow Query | Mark historical comparison inferred until representative plan/runtime evidence is collected |
| Ordered path with residual filter | Compare ordered access plus early shutdown against selective access plus explicit Sort/TopN |
| `LIMIT` early shutdown fails because of skew | Treat as order-vs-filter tradeoff; consider filter index, composite filter+order index, stats/extended stats, or MPP |
| Hypo TiFlash produces expected MPP plan locally | Mark as locally verified by EXPLAIN and recommend TiFlash/MPP with local-validation caveats |
| Production already has TiFlash but optimizer does not choose MPP | If local validation also cannot choose MPP, mark as inferred and request production-safe EXPLAIN validation |
| Cluster lacks TiFlash capacity | Do not recommend TiFlash unless workload value justifies adding capacity and local/static evidence supports MPP |
| No historical, index, or TiFlash direction | Run local `EXPLAIN EXPLORE` after schema and stats are loaded |
| `EXPLAIN EXPLORE` returns generated Binding SQL | Treat it as review-only; do not execute it automatically |
| `EXPLAIN EXPLORE` finds no useful candidate | Report no better explored plan and request more evidence or non-plan investigation |
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
11. Query statement summary or other available plan-variant sources for the
    same digest when Slow Query does not show enough plan diversity.
12. Preserve API errors explicitly.
13. Output structured JSON for this Skill.
14. When `--output` is provided and collection fails, write the error JSON to
    that file and print a concise stderr message that names the output path.

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

Use a `local tidb env` only for local validation of candidate plans. This is
allowed after schema and stats have been collected, and it must never connect to
the production cluster.

Local validation workflow:

1. Prepare or build a TiDB binary matching the target cluster version.
2. Start one standalone local TiDB process with the default local storage engine.
   Do not start TiKV.
3. Convert `tidb_schema_by_table` JSON to SQL using `json2schema`:

   ```bash
   go build .
   ./json2schema tidb_schema_by_table_1688114034.json
   ```

4. Execute the generated DDL locally.
5. Execute `LOAD STATS '<stats-json-file>'` locally for each involved table.
   When using the MySQL client to load a local stats JSON file, enable local
   infile support, for example:

   ```bash
   mysql --local-infile=1 ... -e "LOAD STATS '/path/to/stats.json';"
   ```

   If the client returns `LOAD DATA LOCAL INFILE file request rejected`, treat
   it as a client-side local infile restriction and retry with
   `--local-infile=1`; do not misreport it as a TiDB `LOAD STATS` rejection.
6. Run baseline `EXPLAIN <sql>`.
7. Create hypothetical indexes locally and run candidate `EXPLAIN <sql>`.
8. When evaluating MPP, set hypothetical TiFlash replicas locally and run
   candidate `EXPLAIN <sql>`:

   ```sql
   ALTER TABLE <db>.<table> SET HYPO TIFLASH REPLICA 1;
   ALTER TABLE <db>.<table> SET HYPO TIFLASH REPLICA 0;
   ```

9. When no historical, index, or TiFlash direction is convincing, run local
   plan exploration:

   ```sql
   EXPLAIN EXPLORE <sql>;
   ```

10. Save the baseline, hypothetical-index, hypothetical-TiFlash, and
    `EXPLAIN EXPLORE` candidate plans as evidence.
11. Stop the local TiDB process when done.

The local validation script or manual commands must not:

- execute the target SQL against production;
- run `EXPLAIN ANALYZE` unless local data is intentionally loaded and safe;
- create real indexes in production;
- set real TiFlash replicas in production;
- execute generated Binding SQL from `EXPLAIN EXPLORE` automatically;
- claim runtime improvement from local `EXPLAIN` alone.

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
