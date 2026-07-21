#!/usr/bin/env python3
"""Discover active Dedicated clusters and rank their slow-query digests globally."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


COLLECTOR_PATH = Path(__file__).with_name("collect_slow_sql.py")
SPEC = importlib.util.spec_from_file_location("autox_collect_slow_sql", COLLECTOR_PATH)
assert SPEC and SPEC.loader
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)

DEFAULT_TOP_N = 10
DEFAULT_PAGE_SIZE = 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--last-hours", type=float, default=24.0)
    parser.add_argument("--timezone", default=COLLECTOR.DEFAULT_TIMEZONE)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--clinic-api-root")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.top_n <= 0 or args.top_n > 100:
        parser.error("--top-n must be between 1 and 100")
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must be provided together")
    if args.last_hours <= 0:
        parser.error("--last-hours must be positive")
    return args


def cluster_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "cluster_id": str(item.get("clusterID") or ""),
        "cluster_name": item.get("clusterName"),
        "status": item.get("clusterStatus"),
        "tidb_version": item.get("clusterVersion"),
        "deployment_type": item.get("clusterDeployTypeV2")
        or item.get("clusterDeployType"),
        "provider": item.get("clusterProviderName"),
        "region": item.get("clusterRegionName"),
    }


def discover_active_dedicated(api: Any, page_size: int = DEFAULT_PAGE_SIZE) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        response = api._get(
            "/clinic/api/v1/dashboard/clusters",
            {
                "deploy_type_v2": "dedicated",
                "cluster_status": "active",
                "show_deleted": "false",
                "limit": page_size,
                "page": page,
            },
        )
        if response.get("error"):
            raise COLLECTOR.CollectionError(
                f"Clinic Dedicated cluster discovery failed on page {page}: {response['error']}"
            )
        items = response.get("items") or []
        if not isinstance(items, list):
            raise COLLECTOR.CollectionError("Clinic cluster list returned invalid items")
        for item in items:
            if not isinstance(item, dict):
                continue
            record = cluster_record(item)
            deploy_type = str(record.get("deployment_type") or "").lower()
            status = str(record.get("status") or "").lower()
            cluster_id = record["cluster_id"]
            if cluster_id and deploy_type == "dedicated" and status == "active":
                clusters[cluster_id] = record
        if len(items) < page_size:
            break
        page += 1
        if page > 10000:
            raise COLLECTOR.CollectionError("Clinic cluster pagination exceeded 10000 pages")
    return [clusters[key] for key in sorted(clusters)]


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def collect_fleet_ranking(
    api: Any,
    args: argparse.Namespace,
    window: dict[str, Any],
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    clusters = discover_active_dedicated(api, page_size=page_size)
    if not clusters:
        raise COLLECTOR.CollectionError("no accessible active Dedicated clusters found")

    attempted: list[str] = []
    succeeded: list[str] = []
    empty: list[str] = []
    failed: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        attempted.append(cluster_id)
        schema = api.get_schema(cluster_id, "slow_query_logs")
        if schema.get("error"):
            failed.append({
                "cluster_id": cluster_id,
                "blocker": f"Clinic schema query failed: {schema['error']}",
            })
            continue
        slow_columns = COLLECTOR.available_columns(schema, "slow_query_logs")
        if not slow_columns:
            failed.append({
                "cluster_id": cluster_id,
                "blocker": "Slow Query schema is unavailable",
            })
            continue
        cluster_errors: list[dict[str, str]] = []
        cluster_args = argparse.Namespace(cluster_id=cluster_id, limit=args.top_n)
        rows = COLLECTOR.collect_candidates(
            api, cluster_args, window, slow_columns, cluster_errors
        )
        if cluster_errors:
            blocker = "; ".join(error["error"] for error in cluster_errors)
            failed.append({"cluster_id": cluster_id, "blocker": blocker})
            continue
        succeeded.append(cluster_id)
        if not rows:
            empty.append(cluster_id)
        for row in rows:
            candidate = dict(row)
            candidate.update(
                {
                    "cluster_id": cluster_id,
                    "cluster_name": cluster.get("cluster_name"),
                    "tidb_version": cluster.get("tidb_version"),
                    "deployment_type": cluster.get("deployment_type"),
                }
            )
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -number(item.get("total_query_time")),
            str(item.get("cluster_id") or ""),
            str(item.get("digest") or ""),
        )
    )
    selected = candidates[: args.top_n]
    for rank, candidate in enumerate(selected, start=1):
        candidate["rank"] = rank

    cluster_ids = [cluster["cluster_id"] for cluster in clusters]
    return {
        "scope_mode": "dedicated_fleet",
        "query_window": window,
        "cluster_scope": {
            "selection": "all_accessible_active_dedicated",
            "discovered_count": len(cluster_ids),
            "cluster_ids": cluster_ids,
        },
        "ranking_coverage": {
            "attempted_cluster_ids": attempted,
            "succeeded_cluster_ids": succeeded,
            "empty_cluster_ids": empty,
            "failed_clusters": failed,
        },
        "ranking": {
            "key": "total_slow_query_latency",
            "top_n_cap": args.top_n,
            "available_candidate_count": len(candidates),
            "selected_count": len(selected),
            "candidates": selected,
        },
    }


def write_output(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).expanduser().write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main() -> int:
    args = parse_args()
    try:
        window = COLLECTOR.build_window(args)
        clinic_root = COLLECTOR.find_clinic_api_root(args.clinic_api_root)
        clinic_api_class = COLLECTOR.load_clinic_api(clinic_root)
        payload = collect_fleet_ranking(
            clinic_api_class(args.env_file), args, window
        )
        write_output(payload, args.output)
        return 1 if payload["ranking_coverage"]["failed_clusters"] else 0
    except (COLLECTOR.CollectionError, RuntimeError) as exc:
        write_output(
            {
                "scope_mode": "dedicated_fleet",
                "errors": [{"area": "fleet_collection", "error": str(exc)}],
            },
            args.output,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
