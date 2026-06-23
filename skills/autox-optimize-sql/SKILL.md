---
name: autox-optimize-sql
description: Analyze slow SQL for a TiDB Cloud cluster and output prioritized optimization suggestions. Use when a user provides a cluster_id and asks to inspect slow queries, diagnose SQL performance, investigate plan behavior, or recommend bindings, indexes, statistics changes, or SQL rewrites. This Skill is read-only and assumes Clinic access and any local TiDB or source environment are prepared externally.
---

# AutoX Optimize SQL

Take a `cluster_id`, inspect slow queries, and return recommendations. Do not
create persistent case state and do not modify the target cluster.

## Inputs

- Require `cluster_id`.
- Default the inspection window to the latest 24 hours unless the user provides
  another range.
- Accept an optional SQL digest to narrow the analysis.
- Use a prepared local TiDB connection or TiDB source checkout when available;
  do not prepare or download them.

## Workflow

1. Verify Clinic access and resolve cluster metadata, including TiDB version.
2. Fetch slow queries for the inspection window. If a digest is provided,
   analyze only that digest; otherwise rank queries by total latency, maximum
   latency, execution count, processed keys, and CPU when available.
3. Select a small set of high-impact queries. Do not analyze every query when
   the workload is large.
4. For each selected query, collect the available normalized SQL, sample SQL,
   plan, schema, indexes, statistics health, existing bindings, TopSQL, and
   relevant cluster metrics.
5. Invoke `$autox-explore-sql` to explain the likely cause and generate
   candidates.
6. Invoke `$autox-compare-plans` to rank candidates and produce the final
   suggestions.

## Evidence rules

- Separate observed facts from inference.
- Treat collection errors as unknown, not zero.
- Use the matching TiDB version when reading source or testing locally.
- If schema, statistics, plan, or local reproduction is unavailable, continue
  with lower confidence and say exactly what is missing.
- Never describe a candidate as verified unless it was actually tested.

## Output

Return a concise report containing:

- cluster, version, and inspection window;
- selected slow SQL and why each was selected;
- symptoms and supporting evidence;
- likely root cause;
- prioritized suggestions with expected benefit, risk, confidence, and missing
  evidence;
- suggested SQL for human review when useful.

Do not execute suggested SQL.
