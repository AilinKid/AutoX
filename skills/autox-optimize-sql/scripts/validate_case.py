#!/usr/bin/env python3
"""Validate an AutoX case's retained post-cleanup handoff."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_ACTIONS = {
    "Binding first",
    "Index first",
    "TiFlash / MPP first",
    "Investigate non-optimizer bottleneck",
    "No optimizer action",
}
ALLOWED_VALIDATION_LEVELS = {"inferred", "plan_verified", "prod_verified"}
PLAN_CHANGING_ACTIONS = {"Binding first", "Index first", "TiFlash / MPP first"}
PLAN_REPORT_HEADINGS = ["Conclusion", "Plans Before & After", "Analysis"]
NON_PLAN_REPORT_HEADINGS = ["Conclusion", "Analysis"]
CANONICAL_REPORT_PATH = Path("report/report.md")


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        errors.append(f"missing {path.name}")
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"invalid {path.name}: top level must be an object")
        return {}
    return value


def resolved_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def workspace_path(raw_path: str, workspace: Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else workspace / path


def require_keys(value: dict[str, Any], keys: tuple[str, ...], label: str,
                 errors: list[str]) -> None:
    for key in keys:
        if key not in value:
            errors.append(f"{label} missing {key}")


def report_section(report_text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        report_text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def validate_conclusion(action: str, report_text: str, errors: list[str],
                        allow_legacy_report_format: bool) -> None:
    if allow_legacy_report_format:
        action_markers = (f"Action:\n{action}", f"Recommended action:\n{action}")
        if action and not any(marker in report_text for marker in action_markers):
            errors.append("report recommendation does not match result.json")
        return

    conclusion = report_section(report_text, "Conclusion")
    if action in PLAN_CHANGING_ACTIONS:
        pattern = re.compile(
            rf"\AAction:\s*\n{re.escape(action)}\s*\n+"
            r"Review-only SQL:\s*\n"
            r"Review only\. Not executed by AutoX\.\s*\n"
            r"```sql[ \t]*\n(.+?)\n```\Z",
            re.DOTALL,
        )
        match = pattern.fullmatch(conclusion)
        if not match:
            errors.append(
                "plan-changing Conclusion must contain only Action and concrete review-only SQL"
            )
        elif match.group(1).strip().lower() == "none":
            errors.append("plan-changing Conclusion must contain concrete review-only SQL")
    else:
        pattern = re.compile(rf"\AAction:\s*\n{re.escape(action)}\Z")
        if not pattern.fullmatch(conclusion):
            errors.append("non-plan-changing Conclusion must contain only Action")


def validate_plans(action: str, report_text: str, errors: list[str]) -> None:
    if action not in PLAN_CHANGING_ACTIONS:
        return
    plans = report_section(report_text, "Plans Before & After")
    pattern = re.compile(
        r"\APlan before:\s*\n```text[ \t]*\n(.+?)\n```\s*\n+"
        r"Plan after:\s*\n```text[ \t]*\n(.+?)\n```\Z",
        re.DOTALL,
    )
    if not pattern.fullmatch(plans):
        errors.append(
            "Plans Before & After must contain only complete Plan before and Plan after blocks"
        )


def validate_analysis(report_text: str, errors: list[str]) -> None:
    analysis = report_section(report_text, "Analysis")
    pattern = re.compile(
        r"\AWhy:\s*\n(.+?)\n+"
        r"Observed evidence:\s*\n(.+?)\n+"
        r"Inference:\s*\n(.+?)\n+"
        r"Validation and risks:\s*\n(.+)\Z",
        re.DOTALL,
    )
    if not pattern.fullmatch(analysis):
        errors.append(
            "Analysis must contain only Why, Observed evidence, Inference, and Validation and risks"
        )


def validate_report(workspace: Path, result: dict[str, Any], errors: list[str],
                    allow_legacy_report_name: bool = False,
                    allow_legacy_report_format: bool = False) -> str:
    raw_path = result.get("report_path")
    if not isinstance(raw_path, str) or not raw_path:
        errors.append("result.json missing report_path")
        return ""
    report = workspace_path(raw_path, workspace)
    if not resolved_under(report, workspace / "report"):
        errors.append("report_path is not under the case report directory")
        return ""
    canonical_report = workspace / CANONICAL_REPORT_PATH
    if not allow_legacy_report_name and report.resolve() != canonical_report.resolve():
        errors.append("report_path must resolve to report/report.md")
    try:
        text = report.read_text(errors="replace")
    except OSError as exc:
        errors.append(f"report_path is not readable: {exc}")
        return ""
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    action = result.get("recommended_action")
    expected_headings = (
        PLAN_REPORT_HEADINGS if action in PLAN_CHANGING_ACTIONS else NON_PLAN_REPORT_HEADINGS
    )
    legacy_headings = (PLAN_REPORT_HEADINGS, NON_PLAN_REPORT_HEADINGS)
    headings_valid = (
        headings in legacy_headings
        if allow_legacy_report_format
        else headings == expected_headings
    )
    if not headings_valid:
        errors.append(f"invalid top-level report headings: {headings}")
    return text


def validate_completed(workspace: Path, result: dict[str, Any], report_text: str,
                       expected_digest: str | None, expected_diagnosis_id: str | None,
                       errors: list[str], warnings: list[str],
                       allow_legacy_report_format: bool = False) -> None:
    action = result.get("recommended_action")
    level = result.get("validation_level")
    if action not in ALLOWED_ACTIONS:
        errors.append("invalid or missing recommended_action")
    if level not in ALLOWED_VALIDATION_LEVELS:
        errors.append("invalid or missing validation_level")

    manifest_path = workspace / "manifest.json"
    manifest = load_json(manifest_path, errors) if manifest_path.is_file() else {}
    if manifest:
        require_keys(
            manifest,
            ("diagnosis_id", "cluster", "target", "time_range", "evidence_summary",
             "recommendation", "cleanup", "redaction"),
            "optional manifest.json",
            warnings,
        )
    if (expected_diagnosis_id and manifest.get("diagnosis_id") is not None
            and manifest.get("diagnosis_id") != expected_diagnosis_id):
        errors.append("child manifest diagnosis_id mismatch")
    target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}
    if expected_digest and target.get("digest") is not None and target.get("digest") != expected_digest:
        errors.append("child manifest digest mismatch")

    recommendation = (
        manifest.get("recommendation")
        if isinstance(manifest.get("recommendation"), dict)
        else {}
    )
    if (recommendation.get("recommended_action") is not None
            and recommendation.get("recommended_action") != action):
        errors.append("manifest recommendation does not match result.json")
    if (recommendation.get("validation_level") is not None
            and recommendation.get("validation_level") != level):
        errors.append("manifest validation_level does not match result.json")
    if (recommendation.get("advisory_gate") is not None
            and recommendation.get("advisory_gate") != result.get("advisory_gate")):
        errors.append("manifest advisory_gate does not match result.json")
    manifest_report = recommendation.get("report_path")
    if isinstance(manifest_report, str) and manifest_report and workspace_path(
        manifest_report, workspace
    ).resolve() != workspace_path(
        str(result.get("report_path", "")), workspace
    ).resolve():
        errors.append("manifest report_path does not match result.json")

    evidence = (
        manifest.get("evidence_summary")
        if isinstance(manifest.get("evidence_summary"), dict)
        else {}
    )
    if manifest:
        require_keys(
            evidence,
            ("slow_query_sample_count", "plan_variant_count", "schema_tables",
             "stats_snapshot_time"),
            "optional manifest evidence_summary",
            warnings,
        )
    cleanup = manifest.get("cleanup") if isinstance(manifest.get("cleanup"), dict) else {}
    if manifest and not isinstance(cleanup.get("raw_artifacts_cleaned"), bool):
        warnings.append("optional manifest cleanup missing raw_artifacts_cleaned boolean")
    if cleanup.get("raw_artifacts_cleaned") is False:
        retained = cleanup.get("retained_at_user_request") is True
        leftovers = cleanup.get("leftover_paths")
        if not retained and not leftovers:
            warnings.append("optional manifest cleanup lacks retained reason or leftover paths")

    validate_conclusion(
        str(action or ""), report_text, errors, allow_legacy_report_format
    )
    if not allow_legacy_report_format:
        validate_plans(str(action or ""), report_text, errors)
        validate_analysis(report_text, errors)
    markers = ["Validation level:"]
    if action in PLAN_CHANGING_ACTIONS or allow_legacy_report_format:
        markers.extend(("Plan before:", "Plan after:"))
    for marker in markers:
        if marker not in report_text:
            errors.append(f"report missing {marker}")
    if not allow_legacy_report_format:
        if action not in PLAN_CHANGING_ACTIONS and "Review-only SQL:" in report_text:
            errors.append("non-plan-changing report must omit Review-only SQL")
        if action not in PLAN_CHANGING_ACTIONS and re.search(
            r"^Plan (?:before|after):", report_text, re.MULTILINE
        ):
            errors.append("non-plan-changing report must omit before/after plans")

    if action in {"Binding first", "Index first", "TiFlash / MPP first"}:
        report_candidate = re.search(r"Selected candidate ID:\s*`?([^`\n]+)", report_text)
        if not recommendation.get("selected_candidate_id") and not report_candidate:
            errors.append("optimizer action missing selected_candidate_id")
    if action == "Index first":
        if level == "inferred":
            if result.get("advisory_gate") != "passed":
                errors.append("inferred Index first lacks passed advisory_gate")
            if not re.search(r"^\s*- Advisory gate:\s*passed\s*$", report_text,
                             re.MULTILINE | re.IGNORECASE):
                errors.append("inferred Index first report lacks Advisory gate: passed")
            if not re.search(r"^\s*- Validation status:\s*(?:not run|inferred)\s*$",
                             report_text, re.MULTILINE | re.IGNORECASE):
                errors.append("inferred Index first has invalid validation status")
            if not re.search(r"candidate plan was not reproduced|plan was not reproduced",
                             report_text, re.IGNORECASE):
                errors.append("inferred Index first does not disclose missing plan reproduction")
        elif level not in {"plan_verified", "prod_verified"}:
            errors.append("Index first has invalid validation level")
        if re.search(r"Review-only SQL:\s*(?:Review only[^\n]*\n)?```sql\s*none\s*```",
                     report_text, re.IGNORECASE):
            errors.append("Index first uses Review-only SQL: none")
        if not re.search(r"create\s+index", report_text, re.IGNORECASE):
            errors.append("Index first lacks concrete review-only CREATE INDEX")
    elif action in {"Binding first", "TiFlash / MPP first"}:
        if level not in {"plan_verified", "prod_verified"}:
            errors.append("optimizer action is not plan_verified or prod_verified")


def validate(args: argparse.Namespace) -> tuple[dict[str, Any], list[str], list[str]]:
    workspace = Path(args.workspace)
    errors: list[str] = []
    warnings: list[str] = []
    result = load_json(workspace / "result.json", errors)
    require_keys(
        result,
        ("rank", "digest", "diagnosis_id", "status", "report_path"),
        "result.json",
        errors,
    )
    if args.rank is not None and result.get("rank") != args.rank:
        errors.append("result rank mismatch")
    if args.digest and result.get("digest") != args.digest:
        errors.append("result digest mismatch")
    if args.diagnosis_id and result.get("diagnosis_id") != args.diagnosis_id:
        errors.append("result diagnosis_id mismatch")
    status = result.get("status")
    if status not in {"completed", "failed"}:
        errors.append("result status must be completed or failed")
    report_text = validate_report(
        workspace,
        result,
        errors,
        allow_legacy_report_name=getattr(args, "allow_legacy_report_name", False),
        allow_legacy_report_format=getattr(args, "allow_legacy_report_format", False),
    )
    if status == "failed":
        if not result.get("failed_stage"):
            errors.append("failed result missing failed_stage")
        if not result.get("blocker"):
            errors.append("failed result missing exact blocker")
    elif status == "completed":
        validate_completed(
            workspace,
            result,
            report_text,
            args.digest,
            args.diagnosis_id,
            errors,
            warnings,
            allow_legacy_report_format=getattr(
                args, "allow_legacy_report_format", False
            ),
        )
    return result, errors, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("--rank", type=int)
    parser.add_argument("--digest")
    parser.add_argument("--diagnosis-id")
    parser.add_argument(
        "--allow-legacy-report-name",
        action="store_true",
        help="audit a case created before report/report.md became canonical",
    )
    parser.add_argument(
        "--allow-legacy-report-format",
        action="store_true",
        help="audit a case created before the current action-specific report contract",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result, errors, warnings = validate(args)
    output = {
        "valid": not errors,
        "status": result.get("status"),
        "workspace": str(Path(args.workspace).resolve()),
        "errors": errors,
        "warnings": warnings,
    }
    if args.json_output:
        print(json.dumps(output, indent=2))
    elif errors:
        for error in errors:
            print(error, file=sys.stderr)
    else:
        print(f"valid {output['status']} case: {output['workspace']}")
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
