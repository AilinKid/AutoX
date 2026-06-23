#!/usr/bin/env python3
"""Collect factual Slow Query and TopSQL evidence from Clinic.

This script is intentionally read-only. It does not diagnose root causes,
connect to TiDB, or execute SQL against the target cluster.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_LAST_HOURS = 24.0
DEFAULT_LIMIT = 5
CLUSTER_ID_RE = re.compile(r"^(?:\d+|bran-[A-Za-z0-9_-]+)$")
DIGEST_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class CollectionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only Clinic evidence for TiDB slow SQL analysis."
    )
    parser.add_argument("--cluster-id", required=True)
    parser.add_argument(
        "--digest",
        help="Optional 64-character SQL digest. Without it, return top digest candidates.",
    )
    parser.add_argument(
        "--start",
        help='Business-time start, for example "2026-06-22 00:00:00".',
    )
    parser.add_argument(
        "--end",
        help='Business-time end, for example "2026-06-23 00:00:00".',
    )
    parser.add_argument(
        "--last-hours",
        type=float,
        default=DEFAULT_LAST_HOURS,
        help="Rolling window used when --start/--end are omitted (default: 24).",
    )
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument(
        "--include-lock-details",
        action="store_true",
        help="Collect transaction retry and lock-wait evidence for the target digest.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Representative row and candidate limit (default: 5).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Clinic environment file passed to clinic_api.py (default: .env).",
    )
    parser.add_argument(
        "--clinic-api-root",
        help="Path to the clinic-api Skill directory.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path. Defaults to stdout.",
    )
    args = parser.parse_args()

    if not CLUSTER_ID_RE.fullmatch(args.cluster_id):
        parser.error("--cluster-id must be numeric or a valid bran-* identifier")
    if args.digest and not DIGEST_RE.fullmatch(args.digest):
        parser.error("--digest must be a 64-character hexadecimal digest")
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must be provided together")
    if args.last_hours <= 0:
        parser.error("--last-hours must be positive")
    if args.limit <= 0 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")
    return args


def find_clinic_api_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("CLINIC_API_SKILL_ROOT"):
        candidates.append(Path(os.environ["CLINIC_API_SKILL_ROOT"]).expanduser())

    home = Path.home()
    candidates.extend(
        [
            home / ".codex/skills/clinic-api",
            home / ".claude/skills/clinic-api",
            home / ".config/opencode/skills/clinic-api",
            Path.cwd() / "skills/platform/clinic-api",
        ]
    )

    for root in candidates:
        if (root / "scripts/clinic_api.py").is_file():
            return root.resolve()

    checked = ", ".join(str(path) for path in candidates)
    raise CollectionError(
        "clinic-api Skill not found. Install it or pass --clinic-api-root. "
        f"Checked: {checked}"
    )


def load_clinic_api(root: Path) -> type:
    module_path = root / "scripts/clinic_api.py"
    spec = importlib.util.spec_from_file_location("autox_clinic_api", module_path)
    if spec is None or spec.loader is None:
        raise CollectionError(f"cannot load Clinic client from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ClinicAPI


def parse_business_time(value: str, zone: ZoneInfo) -> datetime:
    normalized = value.strip().replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CollectionError(f"invalid time {value!r}: {exc}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def build_window(args: argparse.Namespace) -> dict[str, Any]:
    try:
        zone = ZoneInfo(args.timezone)
    except ZoneInfoNotFoundError as exc:
        raise CollectionError(f"unknown timezone: {args.timezone}") from exc

    if args.start:
        business_start = parse_business_time(args.start, zone)
        business_end = parse_business_time(args.end, zone)
    else:
        business_end = datetime.now(zone)
        business_start = business_end - timedelta(hours=args.last_hours)

    if business_start >= business_end:
        raise CollectionError("inspection start must be earlier than end")

    utc_start = business_start.astimezone(timezone.utc)
    utc_end = business_end.astimezone(timezone.utc)
    dates: list[datetime] = []
    cursor = utc_start.replace(hour=0, minute=0, second=0, microsecond=0)
    final_day = utc_end.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor <= final_day:
        dates.append(cursor)
        cursor += timedelta(days=1)

    return {
        "business_timezone": args.timezone,
        "business_start": business_start.isoformat(),
        "business_end": business_end.isoformat(),
        "utc_start": utc_start.isoformat().replace("+00:00", "Z"),
        "utc_end": utc_end.isoformat().replace("+00:00", "Z"),
        "utc_start_unix": int(utc_start.timestamp()),
        "utc_end_unix": int(utc_end.timestamp()),
        "slow_query_partitions": [date.strftime("%Y%m%d") for date in dates],
        "topsql_partitions": [date.strftime("%Y-%m-%d") for date in dates],
    }


def rows_as_dicts(result: dict[str, Any]) -> list[dict[str, Any]]:
    columns = result.get("columns") or []
    return [
        dict(zip(columns, row, strict=False))
        for row in (result.get("rows") or [])
    ]


def record_error(
    errors: list[dict[str, str]], area: str, result: dict[str, Any]
) -> bool:
    error = result.get("error")
    if not error:
        return False
    errors.append({"area": area, "error": str(error)})
    return True


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def partition_list(values: list[str]) -> str:
    return ", ".join(sql_string(value) for value in values)


def available_columns(schema: dict[str, Any], table: str) -> set[str]:
    for item in schema.get("schemas") or []:
        if item.get("table") == table:
            columns = {column["name"] for column in item.get("columns") or []}
            columns.update(partition["name"] for partition in item.get("partitions") or [])
            return columns
    return set()


def select_existing(columns: set[str], requested: list[str]) -> list[str]:
    return [column for column in requested if column in columns]


def numeric_expression(column: str) -> str:
    return f"CAST(NULLIF({column}, '') AS DOUBLE)"


def exact_cluster(api: Any, cluster_id: str) -> dict[str, Any]:
    response = api._get(  # Reuse clinic-api authentication and HTTP handling.
        "/clinic/api/v1/dashboard/clusters",
        {"cluster_id": cluster_id, "show_deleted": "true"},
    )
    if response.get("error"):
        raise CollectionError(f"Clinic cluster lookup failed: {response['error']}")
    matches = [
        item
        for item in response.get("items") or []
        if str(item.get("clusterID")) == cluster_id
    ]
    if not matches:
        raise CollectionError(f"cluster not found: {cluster_id}")
    item = matches[0]
    return {
        "cluster_id": item.get("clusterID"),
        "cluster_name": item.get("clusterName"),
        "status": item.get("clusterStatus"),
        "tidb_version": item.get("clusterVersion"),
        "deployment_type": item.get("clusterDeployTypeV2")
        or item.get("clusterDeployType"),
        "provider": item.get("clusterProviderName"),
        "region": item.get("clusterRegionName"),
        "topology": item.get("topology"),
    }


def query(
    api: Any,
    cluster_id: str,
    sql: str,
    errors: list[dict[str, str]],
    area: str,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    result = api.query_sql(cluster_id, sql.strip(), timeout=timeout)
    if record_error(errors, area, result):
        return []
    return rows_as_dicts(result)


def collect_candidates(
    api: Any,
    args: argparse.Namespace,
    window: dict[str, Any],
    slow_columns: set[str],
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    required = {"date", "time", "digest", "query_time", "query"}
    if not required.issubset(slow_columns):
        errors.append(
            {
                "area": "digest_candidates",
                "error": f"missing Slow Query columns: {sorted(required - slow_columns)}",
            }
        )
        return []

    sql = f"""
SELECT
  digest,
  any_value(query) AS sample_sql,
  COUNT(*) AS slow_exec_count,
  SUM(query_time) AS total_query_time,
  AVG(query_time) AS avg_query_time,
  MAX(query_time) AS max_query_time
FROM slow_query_logs
WHERE date IN ({partition_list(window["slow_query_partitions"])})
  AND time >= {window["utc_start_unix"]}
  AND time < {window["utc_end_unix"]}
GROUP BY digest
ORDER BY total_query_time DESC
LIMIT {args.limit}
"""
    return query(
        api, args.cluster_id, sql, errors, "digest_candidates", timeout=120
    )


def collect_digest(
    api: Any,
    args: argparse.Namespace,
    window: dict[str, Any],
    slow_columns: set[str],
    topsql_columns: set[str],
    errors: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = args.digest.lower()
    slow_filter = f"""
date IN ({partition_list(window["slow_query_partitions"])})
  AND time >= {window["utc_start_unix"]}
  AND time < {window["utc_end_unix"]}
  AND digest = {sql_string(digest)}
"""

    summary_exprs = [
        "digest",
        "any_value(query) AS sample_sql",
        "COUNT(*) AS slow_exec_count",
        "SUM(query_time) AS total_query_time",
        "AVG(query_time) AS avg_query_time",
        "MAX(query_time) AS max_query_time",
    ]
    optional_max = {
        "process_time": "max_process_time",
        "wait_time": "max_wait_time",
        "backoff_time": "max_backoff_time",
        "lockkeys_time": "max_lockkeys_time",
        "exec_retry_time": "max_exec_retry_time",
        "result_rows": "max_result_rows",
        "mem_max": "max_memory",
        "disk_max": "max_disk",
    }
    for column, alias in optional_max.items():
        if column in slow_columns:
            summary_exprs.append(f"MAX({column}) AS {alias}")
    for column, prefix in (("total_keys", "total_keys"), ("process_keys", "process_keys")):
        if column in slow_columns:
            expression = numeric_expression(column)
            summary_exprs.extend(
                [
                    f"SUM({expression}) AS total_{prefix}",
                    f"MAX({expression}) AS max_{prefix}",
                ]
            )
    if "index_names" in slow_columns:
        summary_exprs.append("any_value(index_names) AS indexes_used")
    if "plan_digest" in slow_columns:
        summary_exprs.append("COUNT(DISTINCT plan_digest) AS plan_count")

    summary_sql = f"""
SELECT {", ".join(summary_exprs)}
FROM slow_query_logs
WHERE {slow_filter}
GROUP BY digest
"""
    summary = query(api, args.cluster_id, summary_sql, errors, "slow_query.summary")

    requested_detail = [
        "time",
        "plan_digest",
        "instance",
        "db",
        "query",
        "query_time",
        "parse_time",
        "compile_time",
        "optimize_time",
        "cop_time",
        "process_time",
        "wait_time",
        "backoff_time",
        "backoff_types",
        "backoff_detail",
        "resolve_lock_time",
        "lockkeys_time",
        "exec_retry_count",
        "exec_retry_time",
        "request_count",
        "total_keys",
        "process_keys",
        "result_rows",
        "mem_max",
        "disk_max",
        "index_names",
        "stats",
        "warnings",
        "plan_from_cache",
        "plan_from_binding",
        "is_tiflash",
        "decoded_plan",
    ]
    detail_columns = select_existing(slow_columns, requested_detail)
    detail_select = ", ".join(detail_columns)

    representatives: dict[str, list[dict[str, Any]]] = {}
    orderings = {
        "slowest": "query_time DESC",
        "latest": "time DESC",
    }
    if "process_keys" in slow_columns:
        orderings["largest_process_keys"] = (
            f"{numeric_expression('process_keys')} DESC"
        )
    for name, ordering in orderings.items():
        sql = f"""
SELECT {detail_select}
FROM slow_query_logs
WHERE {slow_filter}
ORDER BY {ordering}
LIMIT {args.limit}
"""
        representatives[name] = query(
            api,
            args.cluster_id,
            sql,
            errors,
            f"slow_query.representative_executions.{name}",
        )

    plan_variants: list[dict[str, Any]] = []
    if "plan_digest" in slow_columns:
        variant_exprs = [
            "plan_digest",
            "COUNT(*) AS slow_exec_count",
            "AVG(query_time) AS avg_query_time",
            "MAX(query_time) AS max_query_time",
        ]
        for column, alias in (
            ("process_keys", "max_process_keys"),
            ("total_keys", "max_total_keys"),
        ):
            if column in slow_columns:
                variant_exprs.append(
                    f"MAX({numeric_expression(column)}) AS {alias}"
                )
        for column, alias in (
            ("result_rows", "max_result_rows"),
            ("index_names", "indexes_used"),
            ("decoded_plan", "representative_plan"),
        ):
            if column in slow_columns:
                aggregate = "MAX" if column == "result_rows" else "any_value"
                variant_exprs.append(f"{aggregate}({column}) AS {alias}")
        variants_sql = f"""
SELECT {", ".join(variant_exprs)}
FROM slow_query_logs
WHERE {slow_filter}
GROUP BY plan_digest
ORDER BY slow_exec_count DESC
LIMIT 100
"""
        plan_variants = query(
            api,
            args.cluster_id,
            variants_sql,
            errors,
            "slow_query.plan_variants",
        )

    lock_details: dict[str, Any] | None = None
    if args.include_lock_details:
        lock_columns = select_existing(
            slow_columns,
            [
                "time",
                "db",
                "instance",
                "query_time",
                "lockkeys_time",
                "exec_retry_count",
                "exec_retry_time",
                "txn_retry",
                "resolve_lock_time",
                "local_latch_wait_time",
                "wait_ts",
                "backoff_time",
                "backoff_types",
                "backoff_detail",
                "total_keys",
                "process_keys",
                "result_rows",
                "plan_digest",
                "query",
            ],
        )
        detail_sql = f"""
SELECT {", ".join(lock_columns)}
FROM slow_query_logs
WHERE {slow_filter}
ORDER BY query_time DESC
LIMIT {max(args.limit, 20)}
"""
        lock_details = {
            "slowest_transaction_details": query(
                api,
                args.cluster_id,
                detail_sql,
                errors,
                "slow_query.lock_details",
            )
        }

    topsql: dict[str, Any] = {
        "available": False,
        "summary": [],
        "plan_variants": [],
    }
    top_required = {"date", "timestamps", "sql_digest"}
    if top_required.issubset(topsql_columns):
        top_filter = f"""
date IN ({partition_list(window["topsql_partitions"])})
  AND timestamps >= {window["utc_start_unix"]}
  AND timestamps < {window["utc_end_unix"]}
  AND sql_digest = {sql_string(digest)}
"""
        top_exprs = ["sql_digest"]
        if "normalized_sql" in topsql_columns:
            top_exprs.append("any_value(normalized_sql) AS normalized_sql")
        top_sums = [
            "topsql_cpu_time_ms",
            "topsql_stmt_exec_count",
            "topsql_stmt_duration_sum_ns",
            "topsql_stmt_duration_count",
            "topsql_read_keys",
            "topsql_write_keys",
            "topsql_logical_read_bytes",
            "topsql_logical_write_bytes",
            "topsql_network_in_bytes",
            "topsql_network_out_bytes",
        ]
        for column in select_existing(topsql_columns, top_sums):
            top_exprs.append(f"SUM({column}) AS {column}")
        if "plan_digest" in topsql_columns:
            top_exprs.append("COUNT(DISTINCT plan_digest) AS plan_count")
        top_summary_sql = f"""
SELECT {", ".join(top_exprs)}
FROM topsql
WHERE {top_filter}
GROUP BY sql_digest
"""
        top_summary = query(
            api, args.cluster_id, top_summary_sql, errors, "topsql.summary"
        )

        top_variants: list[dict[str, Any]] = []
        if "plan_digest" in topsql_columns:
            dimensions = select_existing(
                topsql_columns, ["plan_digest", "component", "instance"]
            )
            variant_exprs = dimensions.copy()
            for column in select_existing(topsql_columns, top_sums):
                variant_exprs.append(f"SUM({column}) AS {column}")
            if "normalized_plan" in topsql_columns:
                variant_exprs.append(
                    "any_value(normalized_plan) AS normalized_plan"
                )
            top_variants_sql = f"""
SELECT {", ".join(variant_exprs)}
FROM topsql
WHERE {top_filter}
GROUP BY {", ".join(dimensions)}
ORDER BY topsql_cpu_time_ms DESC
LIMIT 100
"""
            top_variants = query(
                api,
                args.cluster_id,
                top_variants_sql,
                errors,
                "topsql.plan_variants",
            )
        topsql = {
            "available": bool(top_summary or top_variants),
            "summary": top_summary,
            "plan_variants": top_variants,
        }
    else:
        errors.append(
            {
                "area": "topsql",
                "error": f"missing TopSQL columns: {sorted(top_required - topsql_columns)}",
            }
        )

    slow_query = {
        "summary": summary,
        "representative_executions": representatives,
        "plan_variants": plan_variants,
    }
    if lock_details is not None:
        slow_query["lock_details"] = lock_details
    return slow_query, topsql


def write_output(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).expanduser().write_text(text)
    else:
        sys.stdout.write(text)


def main() -> int:
    args = parse_args()
    try:
        window = build_window(args)
        clinic_root = find_clinic_api_root(args.clinic_api_root)
        clinic_api_class = load_clinic_api(clinic_root)
        api = clinic_api_class(args.env_file)
        cluster = exact_cluster(api, args.cluster_id)
        schema = api.get_schema(args.cluster_id, "slow_query_logs,topsql")
        if schema.get("error"):
            raise CollectionError(f"Clinic schema query failed: {schema['error']}")

        slow_columns = available_columns(schema, "slow_query_logs")
        topsql_columns = available_columns(schema, "topsql")
        if not slow_columns:
            raise CollectionError("Slow Query schema is unavailable")

        errors: list[dict[str, str]] = []
        payload: dict[str, Any] = {
            "query_window": window,
            "cluster": cluster,
            "target": {"digest": args.digest.lower() if args.digest else None},
            "schema": {
                "slow_query_columns": sorted(slow_columns),
                "topsql_columns": sorted(topsql_columns),
            },
            "slow_query": {},
            "topsql": {
                "available": False,
                "summary": [],
                "plan_variants": [],
            },
            "errors": errors,
        }

        if args.digest:
            slow_query, topsql = collect_digest(
                api,
                args,
                window,
                slow_columns,
                topsql_columns,
                errors,
            )
            payload["slow_query"] = slow_query
            payload["topsql"] = topsql
            summaries = slow_query.get("summary") or []
            if summaries:
                payload["target"]["sample_sql"] = summaries[0].get("sample_sql")
        else:
            payload["slow_query"] = {
                "digest_candidates": collect_candidates(
                    api, args, window, slow_columns, errors
                )
            }

        write_output(payload, args.output)
        return 0
    except (CollectionError, RuntimeError) as exc:
        write_output({"errors": [{"area": "collection", "error": str(exc)}]}, args.output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
