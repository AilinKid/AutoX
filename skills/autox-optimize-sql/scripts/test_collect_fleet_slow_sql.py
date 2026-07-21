#!/usr/bin/env python3
"""Tests for Dedicated fleet Slow Query ranking."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("collect_fleet_slow_sql.py")
SPEC = importlib.util.spec_from_file_location("collect_fleet_slow_sql", MODULE_PATH)
assert SPEC and SPEC.loader
FLEET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FLEET)


class FakeClinicAPI:
    def __init__(self) -> None:
        self.pages = {
            1: [
                {
                    "clusterID": "2",
                    "clusterName": "dedicated-b",
                    "clusterStatus": "active",
                    "clusterDeployTypeV2": "dedicated",
                },
                {
                    "clusterID": "shared",
                    "clusterName": "shared",
                    "clusterStatus": "active",
                    "clusterDeployTypeV2": "shared",
                },
            ],
            2: [
                {
                    "clusterID": "1",
                    "clusterName": "dedicated-a",
                    "clusterStatus": "active",
                    "clusterDeployTypeV2": "dedicated",
                }
            ],
        }

    def _get(self, _path: str, params: dict[str, object]) -> dict[str, object]:
        return {"items": self.pages.get(int(params["page"]), [])}

    def get_schema(self, _cluster_id: str, _tables: str) -> dict[str, object]:
        return {
            "schemas": [{
                "table": "slow_query_logs",
                "columns": [
                    {"name": "date"},
                    {"name": "time"},
                    {"name": "digest"},
                    {"name": "query_time"},
                    {"name": "query"},
                ],
            }]
        }

    def query_sql(self, cluster_id: str, _sql: str, timeout: int = 120) -> dict[str, object]:
        del timeout
        rows = {
            "1": [
                ["a" * 64, "select 1", 1, 30, 30, 30],
                ["b" * 64, "select 2", 1, 10, 10, 10],
            ],
            "2": [["c" * 64, "select 3", 1, 20, 20, 20]],
        }[cluster_id]
        return {
            "columns": [
                "digest", "sample_sql", "slow_exec_count", "total_query_time",
                "avg_query_time", "max_query_time",
            ],
            "rows": rows,
        }


class CollectFleetSlowSQLTest(unittest.TestCase):
    def test_cli_defaults_to_top_10_and_last_24_hours(self) -> None:
        with patch.object(sys, "argv", ["collect_fleet_slow_sql.py"]):
            args = FLEET.parse_args()
        self.assertEqual(10, args.top_n)
        self.assertEqual(24.0, args.last_hours)

    def test_discovers_all_pages_and_ranks_globally(self) -> None:
        args = argparse.Namespace(top_n=2)
        window = {
            "slow_query_partitions": ["20260720", "20260721"],
            "utc_start_unix": 1,
            "utc_end_unix": 2,
        }
        payload = FLEET.collect_fleet_ranking(
            FakeClinicAPI(), args, window, page_size=2
        )
        self.assertEqual(["1", "2"], payload["cluster_scope"]["cluster_ids"])
        self.assertEqual(["1", "2"], payload["ranking_coverage"]["succeeded_cluster_ids"])
        candidates = payload["ranking"]["candidates"]
        self.assertEqual(["1", "2"], [item["cluster_id"] for item in candidates])
        self.assertEqual([30, 20], [item["total_query_time"] for item in candidates])
        self.assertEqual([1, 2], [item["rank"] for item in candidates])

    def test_schema_failure_is_retained_as_failed_coverage(self) -> None:
        api = FakeClinicAPI()
        original = api.get_schema

        def get_schema(cluster_id: str, tables: str) -> dict[str, object]:
            if cluster_id == "2":
                return {"error": "unavailable"}
            return original(cluster_id, tables)

        api.get_schema = get_schema  # type: ignore[method-assign]
        payload = FLEET.collect_fleet_ranking(
            api,
            argparse.Namespace(top_n=10),
            {
                "slow_query_partitions": ["20260721"],
                "utc_start_unix": 1,
                "utc_end_unix": 2,
            },
            page_size=2,
        )
        self.assertEqual(["1"], payload["ranking_coverage"]["succeeded_cluster_ids"])
        self.assertEqual("2", payload["ranking_coverage"]["failed_clusters"][0]["cluster_id"])


if __name__ == "__main__":
    unittest.main()
