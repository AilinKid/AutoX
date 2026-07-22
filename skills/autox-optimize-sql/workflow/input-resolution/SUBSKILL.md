---
name: input-resolution
description: Resolve AutoX cluster, SQL target, timezone, time range, diagnosis ID, and workspace before collecting slow-SQL evidence.
---

# Input Resolution

Use this workflow subskill before any Clinic, Dashboard, Slow Query, TopSQL, schema, or
statistics collection.

Read `../../references/case-contract.md` before applying this workflow.

## Input Modes

Focused mode requires:

- `cluster_id`

Generic fleet mode requires no user-supplied cluster ID. Use it when the user makes a broad
cluster-diagnosis request such as `帮我看下集群诊断` without specifying cluster scope, digest, SQL
text, time range, or top-N. In that mode:

- list every accessible active Dedicated cluster through Clinic metadata, following all pages;
- use a rolling 24-hour interval ending at the current time;
- rank `(cluster_id, digest)` candidates globally by total slow-query latency;
- select up to 10 candidates across the fleet;
- hand off to `workflow/batch-diagnosis/SUBSKILL.md`.

Explicit user input overrides only the corresponding default. For example, `top 20` changes the
cap but keeps the all-Dedicated and 24-hour defaults; a supplied cluster ID changes the scope to
that cluster but keeps the 24-hour and top-10 defaults when those values are omitted.

Optional:

- SQL digest;
- slow SQL text;
- inspection start and end time;
- business timezone;
- prepared local TiDB connection;
- existing TiDB source checkout or binary.

AutoX v0 supports read-only `SELECT` statements only. Exclude write DML, transaction control, DDL,
administrative statements, and `SELECT ... FOR UPDATE` from automatic ranking. If an explicit SQL
or digest resolves to an ineligible statement, return an unsupported-statement result and stop
before diagnosis or candidate generation.

When the user provides a `cluster_id`, treat it as sufficient authorization to run the
read-only diagnostic workflow.

Only ask a blocking question when required focused input is missing or ambiguous:

- no `cluster_id` and the request is not a generic fleet diagnosis;
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

For focused mode, use exact `cluster_id` lookup through Clinic cluster metadata.

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
- source checkout version used for investigation and local validation;
- local validation compatibility.

If the cluster is not found, stop.

If the cluster is deleted or unavailable, report the state and continue only with historical
data that can still be collected.

For generic fleet mode, use Clinic's paginated cluster list with `deploy_type_v2=dedicated`,
`cluster_status=active`, and `show_deleted=false`. Recheck returned metadata and retain only exact
Dedicated, active records. Do not rely on the endpoint's default page size. Record every discovered
cluster ID and the success, empty result, or exact failure of its ranking query. Run
`../../scripts/collect_fleet_slow_sql.py` for this read-only discovery and global ranking step.

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

If neither digest nor SQL text is provided, hand off to
`workflow/batch-diagnosis/SUBSKILL.md`, rank digest candidates by total slow-query latency, and
select up to 10 by default. This applies to one-cluster and generic fleet scope.

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
