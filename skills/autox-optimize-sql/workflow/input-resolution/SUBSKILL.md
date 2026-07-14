---
name: input-resolution
description: Resolve AutoX cluster, SQL target, timezone, time range, diagnosis ID, and workspace before collecting slow-SQL evidence.
---

# Input Resolution

Use this workflow subskill before any Clinic, Dashboard, Slow Query, TopSQL, schema, or
statistics collection.

Read `../../references/case-contract.md` before applying this workflow.

## Required Input

Require:

- `cluster_id`

Optional:

- SQL digest;
- slow SQL text;
- inspection start and end time;
- business timezone;
- prepared local TiDB connection;
- matching TiDB source checkout or binary.

When the user provides a `cluster_id`, treat it as sufficient authorization to run the
read-only diagnostic workflow.

Only ask a blocking question when required input is missing or ambiguous:

- no `cluster_id`;
- multiple possible target clusters with the same identifier;
- SQL text matches multiple digests equally and no digest was provided;
- user provided an explicit business time range without timezone.

Do not ask for confirmation before read-only Clinic queries, Dashboard debug API downloads,
local static `EXPLAIN`, or generating review-only SQL.

## Diagnosis ID and Workspace

Generate a globally unique `diagnosis_id` for every run. Use a UUID, ULID, KSUID, or another
collision-resistant ID. Do not derive it only from cluster ID, digest, SQL text, or timestamp.

Create a per-diagnosis workspace before collection:

```text
${AUTOX_WORKDIR:-${TMPDIR:-/tmp}/autox/<diagnosis_id>}
```

If `AUTOX_WORKDIR` is set, it must either already be scoped to the current `diagnosis_id`, or
AutoX must create a `diagnosis_id` child directory under it.

Return the workspace path to the next workflow step. Record it in the optional run-local
`manifest.json` only when that audit artifact is being used.

## Clinic API Readiness

Verify:

1. The `clinic-api` skill is installed.
2. `CLINIC_API_KEY` is available and is a least-privilege, read-only credential.
3. The configured Clinic environment is correct: `prod`, `staging`, or `dev`.
4. The API key can successfully query Clinic.

If the available key appears to have broader permissions, continue to enforce the read-only AutoX
boundary: call only read endpoints and never invoke a mutation API. Keep debug logging disabled by
default, and never print the key, authorization headers, signed URLs, passwords, or tokens.

If authentication or the API probe fails, stop input resolution and preserve the exact error.
Do not interpret API failure as empty data.

If a read-only Clinic or Dashboard collection command fails with a sandbox or network-layer
error, preserve the original error. Do not downgrade it to missing data.

## Resolve Cluster Context

Use exact `cluster_id` lookup through Clinic cluster metadata.

Do not use the first result of a fuzzy query search.

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
- source code version used for investigation;
- local validation compatibility.

If the cluster is not found, stop.

If the cluster is deleted or unavailable, report the state and continue only with historical
data that can still be collected.

## Resolve Time Range

Clinic queries use UTC. Users often describe incidents in a business timezone.

If the user provides an explicit business time range without timezone, ask for the timezone
before querying.

If the user does not provide a time range, use a rolling 24-hour interval ending at the current
time. Display results in the user's locale timezone when available, otherwise UTC.

Convert the confirmed range into:

- UTC start timestamp;
- UTC end timestamp;
- Slow Query UTC partitions in `YYYYMMDD`;
- TopSQL UTC partitions in `YYYY-MM-DD`.

Always use both:

1. the date partition predicate;
2. the exact execution timestamp predicate.

The partition predicate limits the scan. The timestamp predicate limits the result to the exact
requested interval.

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

## Resolve SQL Target

If a digest is provided, use it as the target digest.

If SQL text is provided without a digest, resolve the matching digest during Slow Query
schema-aware collection. If multiple digests match, show the candidates and ask the user to
choose. Do not silently select one.

If neither digest nor SQL text is provided, rank digest candidates by total slow-query latency
and select a small high-impact set for analysis. For explicit top-N requests, hand off to
`workflow/batch-diagnosis/SUBSKILL.md`.

## Output Contract

Return the resolved input directly. Optionally write or update a run-local `manifest.json` with:

```json
{
  "diagnosis_id": "",
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
    "sql_text": "",
    "normalized_sql": ""
  },
  "time_range": {
    "business": "",
    "utc": "",
    "timezone": "",
    "slow_query_partitions": [],
    "topsql_partitions": []
  },
  "workspace": ""
}
```

Hand off to `workflow/evidence-collection/SUBSKILL.md`.
