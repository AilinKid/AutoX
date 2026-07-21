#!/usr/bin/env python3
"""Validate that an AutoX batch is not declared complete prematurely."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ALLOWED_BATCH_STATUSES = {"running", "paused", "completed", "incomplete"}
ALLOWED_CHILD_STATUSES = {
    "queued", "running", "retry_pending", "completed", "failed", "excluded_by_user"
}
RETRYABLE_CHILD_STATUSES = {"queued", "running", "retry_pending"}
CASE_VALIDATOR = Path(__file__).with_name("validate_case.py")
SUMMARY_TITLE = "# AutoX Slow SQL Batch Report"
SUMMARY_HEADINGS = ["Batch", "Summary", "Cases"]
SUMMARY_TABLE_HEADER = "| Rank | Cluster | Impact | Action | Validation | Report |"
SUMMARY_TABLE_DIVIDER = "|---:|---|---:|---|---|---|"
ALLOWED_ACTIONS = {
    "Binding first",
    "Index first",
    "TiFlash / MPP first",
    "Investigate non-optimizer bottleneck",
    "No optimizer action",
}
ALLOWED_VALIDATION_LEVELS = {"inferred", "observed", "plan_verified"}


def load_manifest(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append("missing batch-manifest.json")
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid batch-manifest.json: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append("invalid batch-manifest.json: top level must be an object")
        return {}
    return value


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_scope(manifest: dict[str, Any], case_count: int, excluded_count: int,
                   errors: list[str]) -> tuple[int, int]:
    requested = manifest.get("requested_top_n")
    effective = manifest.get("effective_top_n")
    if not positive_int(requested):
        errors.append("invalid or missing requested_top_n")
        requested = 0
    if not positive_int(effective):
        errors.append("invalid or missing effective_top_n")
        effective = 0
    if requested and effective and effective > requested:
        errors.append("effective_top_n exceeds requested_top_n")
    if requested and case_count != requested:
        errors.append("case count does not match requested_top_n")
    if effective and case_count - excluded_count != effective:
        errors.append("included case count does not match effective_top_n")

    if requested and effective and requested != effective:
        change = manifest.get("scope_change")
        if not isinstance(change, dict):
            errors.append("scope reduction missing scope_change")
        else:
            if change.get("authorized_by_user") is not True:
                errors.append("scope reduction was not explicitly authorized by user")
            if change.get("from_top_n") != requested:
                errors.append("scope_change from_top_n does not match requested_top_n")
            if change.get("to_top_n") != effective:
                errors.append("scope_change to_top_n does not match effective_top_n")
            if not isinstance(change.get("reason"), str) or not change.get("reason", "").strip():
                errors.append("scope_change reason must be non-empty")
        if excluded_count != requested - effective:
            errors.append("excluded_by_user count does not match scope reduction")
    elif excluded_count:
        errors.append("excluded_by_user cases require a scope reduction")
    return requested, effective


def validate_cases(cases: Any, errors: list[str]) -> tuple[list[dict[str, Any]], Counter[str]]:
    if not isinstance(cases, list):
        errors.append("invalid or missing cases")
        return [], Counter()

    valid_cases: list[dict[str, Any]] = []
    ranks: set[int] = set()
    targets: set[tuple[str, str]] = set()
    statuses: Counter[str] = Counter()
    for index, case in enumerate(cases):
        label = f"case[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label} must be an object")
            continue
        valid_cases.append(case)
        rank = case.get("rank")
        digest = case.get("digest")
        diagnosis_id = case.get("diagnosis_id")
        status = case.get("status")
        if not positive_int(rank):
            errors.append(f"{label} has invalid rank")
        elif rank in ranks:
            errors.append(f"duplicate case rank: {rank}")
        else:
            ranks.add(rank)
        if not isinstance(digest, str) or not digest:
            errors.append(f"{label} has invalid digest")
        else:
            cluster_id = case.get("cluster_id")
            target = (str(cluster_id or ""), digest)
            if target in targets:
                errors.append(f"duplicate case target: {target[0]}:{digest}")
            else:
                targets.add(target)
        if not isinstance(diagnosis_id, str) or not diagnosis_id:
            errors.append(f"{label} has invalid diagnosis_id")
        if status not in ALLOWED_CHILD_STATUSES:
            errors.append(f"{label} has invalid status")
        else:
            statuses[status] += 1
        if status == "failed" and (
            not isinstance(case.get("blocker"), str) or not case.get("blocker", "").strip()
        ):
            errors.append(f"{label} failed without blocker")
        if status == "retry_pending" and (
            not isinstance(case.get("blocker"), str) or not case.get("blocker", "").strip()
        ):
            errors.append(f"{label} retry_pending without blocker")
    return valid_cases, statuses


def validate_status_counts(manifest: dict[str, Any], statuses: Counter[str],
                           errors: list[str]) -> None:
    recorded = manifest.get("status_counts")
    if not isinstance(recorded, dict):
        errors.append("invalid or missing status_counts")
        return
    for status in ALLOWED_CHILD_STATUSES:
        value = recorded.get(status)
        if value != statuses.get(status, 0):
            errors.append(f"status_counts {status} does not match cases")


def validate_batch_status(manifest: dict[str, Any], effective: int,
                          statuses: Counter[str], errors: list[str]) -> None:
    batch_status = manifest.get("batch_status")
    if batch_status not in ALLOWED_BATCH_STATUSES:
        errors.append("invalid or missing batch_status")
        return
    completed = statuses.get("completed", 0)
    failed = statuses.get("failed", 0)
    retryable = sum(statuses.get(status, 0) for status in RETRYABLE_CHILD_STATUSES)

    if batch_status == "completed":
        if not effective or completed != effective:
            errors.append("completed batch does not have all effective cases completed")
        if failed or retryable:
            errors.append("completed batch still has failed or retryable cases")
    elif batch_status == "paused":
        if retryable == 0:
            errors.append("paused batch has no resumable cases")
        if completed == effective and effective:
            errors.append("fully completed batch cannot be paused")
    elif batch_status == "running":
        if completed == effective and effective:
            errors.append("fully completed batch cannot remain running")
    elif batch_status == "incomplete":
        if failed == 0 and not manifest.get("parent_failure"):
            errors.append("incomplete batch lacks failed child or parent_failure")


def validate_completed_children(workspace: Path, cases: list[dict[str, Any]],
                                errors: list[str]) -> None:
    for case in cases:
        if case.get("status") != "completed":
            continue
        diagnosis_id = case.get("diagnosis_id")
        if not isinstance(diagnosis_id, str) or not diagnosis_id:
            continue
        child_workspace = workspace / "cases" / diagnosis_id
        result = subprocess.run(
            [sys.executable, str(CASE_VALIDATOR), str(child_workspace), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stdout.strip() or result.stderr.strip() or "unknown validation error"
            errors.append(f"completed child {diagnosis_id} failed validate_case.py: {detail}")


def markdown_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def validate_summary(workspace: Path, summary_path: str, effective: int,
                     errors: list[str]) -> None:
    path = workspace / summary_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"completed batch summary_path is not readable: {exc}")
        return
    if not text.startswith(f"{SUMMARY_TITLE}\n"):
        errors.append("batch main report has invalid title")
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    if headings != SUMMARY_HEADINGS:
        errors.append(f"batch main report has invalid section headings: {headings}")

    batch = markdown_section(text, "Batch")
    for label in ("Status", "Scope", "Progress", "Time range", "Ranking", "Coverage", "Safety"):
        if not re.search(rf"^- {re.escape(label)}:\s*\S", batch, re.MULTILINE):
            errors.append(f"batch main report missing {label}")
    if not re.search(r"^- Status:\s*`?completed`?\s*$", batch, re.MULTILINE):
        errors.append("completed batch main report must show Status: completed")

    summary = markdown_section(text, "Summary")
    for label in ("Impact", "Actions", "Validation levels"):
        if not re.search(rf"^- {re.escape(label)}:\s*\S", summary, re.MULTILINE):
            errors.append(f"batch main report missing {label}")

    cases = markdown_section(text, "Cases")
    lines = cases.splitlines()
    if len(lines) < 2 or lines[0] != SUMMARY_TABLE_HEADER:
        errors.append("batch main report must use the canonical six-column Cases header")
        return
    if lines[1] != SUMMARY_TABLE_DIVIDER:
        errors.append("batch main report has invalid Cases table divider")
        return
    rows = [line for line in lines[2:] if line.startswith("|")]
    if len(rows) != effective:
        errors.append("batch main report case row count does not match effective_top_n")
    for index, row in enumerate(rows, start=1):
        columns = [column.strip() for column in row.strip().strip("|").split("|")]
        if len(columns) != 6:
            errors.append(f"batch main report row {index} does not have six columns")
            continue
        rank, cluster, impact, action, validation, report = columns
        if not rank.isdigit() or not cluster or not impact:
            errors.append(f"batch main report row {index} has invalid identity or impact")
        if action not in ALLOWED_ACTIONS:
            errors.append(f"batch main report row {index} has invalid Action")
        if validation not in ALLOWED_VALIDATION_LEVELS:
            errors.append(f"batch main report row {index} has invalid Validation")
        if not re.fullmatch(r"\[report\]\(cases/[^/]+/report/report\.md\)", report):
            errors.append(f"batch main report row {index} has invalid Report link")


def validate(workspace: Path, validate_children: bool = True) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    manifest = load_manifest(workspace / "batch-manifest.json", errors)
    cases, statuses = validate_cases(manifest.get("cases"), errors)
    excluded = statuses.get("excluded_by_user", 0)
    _, effective = validate_scope(manifest, len(cases), excluded, errors)
    validate_status_counts(manifest, statuses, errors)
    validate_batch_status(manifest, effective, statuses, errors)

    if manifest.get("batch_status") == "completed":
        summary_path = manifest.get("summary_path")
        if not isinstance(summary_path, str) or not summary_path:
            errors.append("completed batch missing summary_path")
        elif not (workspace / summary_path).is_file():
            errors.append("completed batch summary_path is not readable")
        else:
            validate_summary(workspace, summary_path, effective, errors)
        if validate_children:
            validate_completed_children(workspace, cases, errors)
    return manifest, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace)
    manifest, errors = validate(workspace)
    output = {
        "valid": not errors,
        "batch_status": manifest.get("batch_status"),
        "workspace": str(workspace.resolve()),
        "errors": errors,
    }
    if args.json_output:
        print(json.dumps(output, indent=2))
    elif errors:
        for error in errors:
            print(error, file=sys.stderr)
    else:
        print(f"valid {output['batch_status']} batch: {output['workspace']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
