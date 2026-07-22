#!/usr/bin/env python3
"""Tests for Slow Query statement eligibility and ranking."""

from __future__ import annotations

import argparse
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("collect_slow_sql.py")
SPEC = importlib.util.spec_from_file_location("collect_slow_sql", MODULE_PATH)
assert SPEC and SPEC.loader
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


class FakeClinicAPI:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.sql = ""

    def query_sql(self, _cluster_id: str, sql: str, timeout: int = 120) -> dict[str, object]:
        del timeout
        self.sql = sql
        return {
            "columns": [
                "digest",
                "sample_sql",
                "slow_exec_count",
                "total_query_time",
                "avg_query_time",
                "max_query_time",
            ],
            "rows": self.rows,
        }


class CollectSlowSQLTest(unittest.TestCase):
    def test_read_only_statement_classifier(self) -> None:
        allowed = [
            "SELECT * FROM t",
            "/* trace */ WITH cte AS (SELECT * FROM t) SELECT * FROM cte",
            "-- comment\nSELECT 'update' FROM t",
        ]
        excluded = [
            "INSERT INTO t VALUES (1)",
            "UPDATE t SET a = 1",
            "DELETE FROM t",
            "REPLACE INTO t VALUES (1)",
            "WITH cte AS (SELECT 1) UPDATE t SET a = 1",
            "SELECT * FROM t FOR UPDATE",
            "EXPLAIN SELECT * FROM t",
            "COMMIT",
        ]
        for sql in allowed:
            with self.subTest(sql=sql):
                self.assertTrue(COLLECTOR.is_read_only_query(sql))
        for sql in excluded:
            with self.subTest(sql=sql):
                self.assertFalse(COLLECTOR.is_read_only_query(sql))

    def test_candidate_ranking_excludes_write_statements(self) -> None:
        api = FakeClinicAPI(
            [
                ["a" * 64, "INSERT INTO t VALUES (1)", 1, 100, 100, 100],
                ["b" * 64, "SELECT * FROM t WHERE a = 1", 1, 80, 80, 80],
                ["c" * 64, "UPDATE t SET a = 1", 1, 60, 60, 60],
                ["d" * 64, "WITH c AS (SELECT 1) SELECT * FROM c", 1, 40, 40, 40],
            ]
        )
        errors: list[dict[str, str]] = []
        rows = COLLECTOR.collect_candidates(
            api,
            argparse.Namespace(cluster_id="1", limit=2),
            {
                "slow_query_partitions": ["20260722"],
                "utc_start_unix": 1,
                "utc_end_unix": 2,
            },
            {"date", "time", "digest", "query_time", "query"},
            errors,
        )
        self.assertEqual([], errors)
        self.assertEqual(["b" * 64, "d" * 64], [row["digest"] for row in rows])
        self.assertIn("LIMIT 200", api.sql)

    def test_candidate_ranking_reports_incomplete_filtered_scan(self) -> None:
        rows = [
            [str(index).zfill(64), "UPDATE t SET a = 1", 1, 1, 1, 1]
            for index in range(COLLECTOR.MIN_CANDIDATE_SCAN_LIMIT)
        ]
        errors: list[dict[str, str]] = []
        candidates = COLLECTOR.collect_candidates(
            FakeClinicAPI(rows),
            argparse.Namespace(cluster_id="1", limit=10),
            {
                "slow_query_partitions": ["20260722"],
                "utc_start_unix": 1,
                "utc_end_unix": 2,
            },
            {"date", "time", "digest", "query_time", "query"},
            errors,
        )
        self.assertEqual([], candidates)
        self.assertEqual("digest_candidates.statement_filter", errors[0]["area"])

    def test_explicit_write_digest_stops_before_detail_collection(self) -> None:
        api = FakeClinicAPI(
            [["a" * 64, "UPDATE t SET a = 1", 1, 100, 100, 100]]
        )
        errors: list[dict[str, str]] = []
        slow_query, topsql = COLLECTOR.collect_digest(
            api,
            argparse.Namespace(
                cluster_id="1",
                digest="a" * 64,
                limit=5,
                include_lock_details=False,
            ),
            {
                "slow_query_partitions": ["20260722"],
                "topsql_partitions": ["2026-07-22"],
                "utc_start_unix": 1,
                "utc_end_unix": 2,
            },
            {"date", "time", "digest", "query_time", "query"},
            set(),
            errors,
        )
        self.assertEqual("target.statement_type", errors[0]["area"])
        self.assertEqual({}, slow_query["representative_executions"])
        self.assertFalse(topsql["available"])


if __name__ == "__main__":
    unittest.main()
