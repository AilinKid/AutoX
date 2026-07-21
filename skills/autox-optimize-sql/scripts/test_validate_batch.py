#!/usr/bin/env python3
"""Tests for the AutoX batch completion validator."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_batch.py")
SPEC = importlib.util.spec_from_file_location("validate_batch", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATE_BATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE_BATCH)


class ValidateBatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def case(self, rank: int, status: str = "completed") -> dict[str, object]:
        return {
            "rank": rank,
            "digest": f"digest-{rank}",
            "diagnosis_id": f"diagnosis-{rank}",
            "status": status,
            "blocker": "retry later" if status in {"retry_pending", "failed"} else "",
        }

    def manifest(self, statuses: list[str], batch_status: str = "completed",
                 requested: int | None = None, effective: int | None = None,
                 authorized: bool = True) -> dict[str, object]:
        cases = [self.case(index + 1, status) for index, status in enumerate(statuses)]
        requested = requested if requested is not None else len(cases)
        effective = effective if effective is not None else len(cases)
        counts = {status: 0 for status in VALIDATE_BATCH.ALLOWED_CHILD_STATUSES}
        for status in statuses:
            counts[status] += 1
        value: dict[str, object] = {
            "batch_id": "batch",
            "batch_status": batch_status,
            "requested_top_n": requested,
            "effective_top_n": effective,
            "status_counts": counts,
            "summary_path": "batch-summary.md",
            "cases": cases,
        }
        if requested != effective:
            value["scope_change"] = {
                "authorized_by_user": authorized,
                "from_top_n": requested,
                "to_top_n": effective,
                "reason": "user reduced the requested scope",
            }
        return value

    def summary(self, manifest: dict[str, object]) -> str:
        rows = []
        for case in manifest["cases"]:  # type: ignore[union-attr]
            if case["status"] != "completed":
                continue
            rows.append(
                f"| {case['rank']} | cluster | 1h / 1 exec | No optimizer action | "
                f"inferred | [report](cases/{case['diagnosis_id']}/report/report.md) |"
            )
        return """# AutoX Slow SQL Batch Report

## Batch

- Status: `completed`
- Scope: effective test scope
- Progress: completed/effective
- Time range: test window UTC
- Ranking: aggregate latency
- Coverage: not applicable
- Safety: Production read-only; no binding, index, configuration, or DDL changes were applied.

## Summary

- Impact: test impact
- Actions: No optimizer action
- Validation levels: inferred

## Cases

| Rank | Cluster | Impact | Action | Validation | Report |
|---:|---|---:|---|---|---|
""" + "\n".join(rows) + "\n"

    def validate(self, manifest: dict[str, object], summary_override: str | None = None) -> list[str]:
        (self.workspace / "batch-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (self.workspace / "batch-summary.md").write_text(
            summary_override if summary_override is not None else self.summary(manifest),
            encoding="utf-8",
        )
        _, errors = VALIDATE_BATCH.validate(self.workspace, validate_children=False)
        return errors

    def test_completed_batch_requires_every_case_completed(self) -> None:
        manifest = self.manifest(["completed", "retry_pending"], batch_status="completed")
        errors = self.validate(manifest)
        self.assertIn("completed batch does not have all effective cases completed", errors)
        self.assertIn("completed batch still has failed or retryable cases", errors)

    def test_completed_batch_is_valid_after_all_cases_complete(self) -> None:
        self.assertEqual([], self.validate(self.manifest(["completed", "completed"])))

    def test_paused_batch_preserves_retryable_work(self) -> None:
        manifest = self.manifest(["completed", "retry_pending"], batch_status="paused")
        self.assertEqual([], self.validate(manifest))

    def test_paused_batch_requires_resumable_case(self) -> None:
        manifest = self.manifest(["completed", "failed"], batch_status="paused")
        self.assertIn("paused batch has no resumable cases", self.validate(manifest))

    def test_failed_case_prevents_completed_batch(self) -> None:
        manifest = self.manifest(["completed", "failed"], batch_status="completed")
        self.assertIn("completed batch still has failed or retryable cases", self.validate(manifest))

    def test_user_authorized_scope_reduction_is_valid(self) -> None:
        manifest = self.manifest(
            ["completed", "completed", "excluded_by_user"],
            requested=3, effective=2, authorized=True
        )
        self.assertEqual([], self.validate(manifest))

    def test_silent_scope_reduction_is_invalid(self) -> None:
        manifest = self.manifest(
            ["completed", "completed", "excluded_by_user"],
            requested=3, effective=2, authorized=False
        )
        self.assertIn(
            "scope reduction was not explicitly authorized by user",
            self.validate(manifest),
        )

    def test_case_count_must_match_effective_scope(self) -> None:
        manifest = self.manifest(["completed", "completed"])
        manifest["requested_top_n"] = 3
        manifest["effective_top_n"] = 3
        self.assertIn("case count does not match requested_top_n", self.validate(manifest))

    def test_status_counts_must_match_cases(self) -> None:
        manifest = self.manifest(["completed", "retry_pending"], batch_status="paused")
        manifest["status_counts"]["completed"] = 2  # type: ignore[index]
        self.assertIn("status_counts completed does not match cases", self.validate(manifest))

    def test_same_digest_on_different_clusters_is_valid(self) -> None:
        manifest = self.manifest(["completed", "completed"])
        manifest["cases"][0]["digest"] = "shared-digest"  # type: ignore[index]
        manifest["cases"][0]["cluster_id"] = "cluster-a"  # type: ignore[index]
        manifest["cases"][1]["digest"] = "shared-digest"  # type: ignore[index]
        manifest["cases"][1]["cluster_id"] = "cluster-b"  # type: ignore[index]
        self.assertEqual([], self.validate(manifest))

    def test_duplicate_cluster_digest_target_is_invalid(self) -> None:
        manifest = self.manifest(["completed", "completed"])
        manifest["cases"][0]["digest"] = "shared-digest"  # type: ignore[index]
        manifest["cases"][0]["cluster_id"] = "cluster-a"  # type: ignore[index]
        manifest["cases"][1]["digest"] = "shared-digest"  # type: ignore[index]
        manifest["cases"][1]["cluster_id"] = "cluster-a"  # type: ignore[index]
        self.assertTrue(
            any(error.startswith("duplicate case target:") for error in self.validate(manifest))
        )

    def test_incomplete_batch_requires_failure(self) -> None:
        manifest = self.manifest(["completed", "completed"], batch_status="incomplete")
        self.assertIn(
            "incomplete batch lacks failed child or parent_failure",
            self.validate(manifest),
        )

    def test_signal_column_is_rejected_from_main_report(self) -> None:
        manifest = self.manifest(["completed"])
        invalid = self.summary(manifest).replace(
            "| Rank | Cluster | Impact | Action | Validation | Report |",
            "| Rank | Cluster | Impact | Action | Validation | Signal | Report |",
        )
        self.assertIn(
            "batch main report must use the canonical six-column Cases header",
            self.validate(manifest, invalid),
        )


if __name__ == "__main__":
    unittest.main()
