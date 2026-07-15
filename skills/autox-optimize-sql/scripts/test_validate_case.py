#!/usr/bin/env python3
"""Tests for the retained AutoX case validator."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_case.py")
SPEC = importlib.util.spec_from_file_location("validate_case", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATE_CASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE_CASE)


class ValidateCaseTest(unittest.TestCase):
    def write_case(self, action: str, level: str, advisory_gate: str | None,
                   validation_status: str = "not run") -> Path:
        workspace = Path(self.tempdir.name)
        report_dir = workspace / "report"
        report_dir.mkdir()
        result = {
            "rank": 1,
            "digest": "digest",
            "diagnosis_id": "diagnosis",
            "status": "completed",
            "recommended_action": action,
            "validation_level": level,
            "report_path": "report/report.md",
        }
        if advisory_gate is not None:
            result["advisory_gate"] = advisory_gate
        (workspace / "result.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
        if action in VALIDATE_CASE.PLAN_CHANGING_ACTIONS:
            conclusion = f"""Action:
{action}

Plan before:
IndexLookUp with table-row fetch

Plan after:
Covering IndexReader; candidate plan was not reproduced

Why:
The candidate removes the diagnosed table-row fetch while preserving the required order."""
            review_sql = """Review-only SQL:
Review only. Not executed by AutoX.
```sql
CREATE INDEX idx_a ON t (a);
```

"""
        else:
            conclusion = f"""Action:
{action}

Why:
The observed plan already uses the useful access path, so no plan-changing action addresses the dominant runtime mechanism."""
            review_sql = ""
        (report_dir / "report.md").write_text(
            f"""## Conclusion

{conclusion}

## Plans Before & After

Plan before:
```text
complete production plan
```

Plan after:
```text
The candidate plan was not reproduced.
```

## Analysis

{review_sql}Observed evidence:
The production plan performs a table-row fetch.

Inference:
The covering candidate targets that fetch.

Validation and risks:
- Validation status: {validation_status}
- Validation level: {level}
- Advisory gate: {advisory_gate or 'not applicable'}
- Selected candidate ID: idx_a
- Missing evidence or blocker: candidate plan was not reproduced
- Risk and next validation: validate plan shape before rollout
""",
            encoding="utf-8",
        )
        return workspace

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def validate(self, workspace: Path, allow_legacy_report_name: bool = False,
                 allow_legacy_report_format: bool = False) -> list[str]:
        args = Namespace(
            workspace=str(workspace), rank=None, digest=None,
            diagnosis_id=None, json_output=False,
            allow_legacy_report_name=allow_legacy_report_name,
            allow_legacy_report_format=allow_legacy_report_format,
        )
        _, errors, _ = VALIDATE_CASE.validate(args)
        return errors

    def rename_report(self, workspace: Path, filename: str) -> None:
        canonical = workspace / "report" / "report.md"
        legacy = canonical.with_name(filename)
        canonical.rename(legacy)
        result_path = workspace / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["report_path"] = f"report/{filename}"
        result_path.write_text(json.dumps(result), encoding="utf-8")

    def test_inferred_index_with_passed_advisory_gate_is_valid(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        self.assertEqual([], self.validate(workspace))

    def test_inferred_index_without_passed_advisory_gate_is_invalid(self) -> None:
        workspace = self.write_case("Index first", "inferred", None)
        self.assertIn(
            "inferred Index first lacks passed advisory_gate",
            self.validate(workspace),
        )

    def test_rejected_index_cannot_use_advisory_fallback(self) -> None:
        workspace = self.write_case(
            "Index first", "inferred", "passed", validation_status="rejected"
        )
        self.assertIn(
            "inferred Index first has invalid validation status",
            self.validate(workspace),
        )

    def test_inferred_binding_is_invalid(self) -> None:
        workspace = self.write_case("Binding first", "inferred", "passed")
        self.assertIn(
            "optimizer action is not plan_verified or prod_verified",
            self.validate(workspace),
        )

    def test_noncanonical_report_name_is_invalid(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        self.rename_report(workspace, "final_report.md")
        self.assertIn(
            "report_path must resolve to report/report.md",
            self.validate(workspace),
        )

    def test_legacy_report_name_requires_explicit_compatibility_flag(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        self.rename_report(workspace, "final-report.md")
        self.assertEqual(
            [],
            self.validate(workspace, allow_legacy_report_name=True),
        )

    def test_no_action_with_compact_reason_is_valid(self) -> None:
        workspace = self.write_case("No optimizer action", "inferred", None)
        self.assertEqual([], self.validate(workspace))

    def test_no_action_without_reason_is_invalid(self) -> None:
        workspace = self.write_case("No optimizer action", "inferred", None)
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "\nWhy:\nThe observed plan already uses the useful access path, so no "
            "plan-changing action addresses the dominant runtime mechanism.",
            "",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "non-plan-changing Conclusion must contain only Action and Why",
            self.validate(workspace),
        )

    def test_no_action_conclusion_rejects_plan_fields(self) -> None:
        workspace = self.write_case("No optimizer action", "inferred", None)
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "\nWhy:\nThe observed plan",
            "\nPlan before:\nIndexLookUp\n\nWhy:\nThe observed plan",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "non-plan-changing Conclusion must contain only Action and Why",
            self.validate(workspace),
        )

    def test_plan_action_requires_before_and_after_summaries(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "\nPlan after:\nCovering IndexReader; candidate plan was not reproduced\n",
            "\n",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "plan-changing Conclusion must contain only Action, one-line Plan before, "
            "one-line Plan after, and Why",
            self.validate(workspace),
        )

    def test_plan_section_rejects_verbose_metadata(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "Plan before:\n```text",
            "Plan before:\n- Source: slow log decoded_plan\n```text",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "plan section contains verbose metadata field Source:",
            self.validate(workspace),
        )

    def test_legacy_report_format_requires_explicit_compatibility_flag(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        conclusion_end = text.index("\n## Plans Before & After")
        legacy = """## Conclusion

Recommended action:
Index first

Review-only SQL:
Review only. Not executed by AutoX.
```sql
CREATE INDEX idx_a ON t (a);
```
""" + text[conclusion_end:]
        report.write_text(legacy, encoding="utf-8")
        self.assertIn(
            "plan-changing Conclusion must contain only Action, one-line Plan before, "
            "one-line Plan after, and Why",
            self.validate(workspace),
        )
        self.assertEqual(
            [],
            self.validate(workspace, allow_legacy_report_format=True),
        )


if __name__ == "__main__":
    unittest.main()
