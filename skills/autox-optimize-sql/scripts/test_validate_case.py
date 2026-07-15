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

Review-only SQL:
Review only. Not executed by AutoX.
```sql
CREATE INDEX idx_a ON t (a);
```"""
            plans = """\n\n## Plans Before & After

Plan before:
```text
IndexLookUp with table-row fetch
```

Plan after:
```text
Covering IndexReader; candidate plan was not reproduced
```"""
        else:
            conclusion = f"""Action:
{action}"""
            plans = ""
        (report_dir / "report.md").write_text(
            f"""## Conclusion

{conclusion}{plans}

## Analysis

Why:
The candidate targets the diagnosed runtime mechanism, or no plan-changing action is justified by the observed plan.

Observed evidence:
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
            "\nWhy:\nThe candidate targets the diagnosed runtime mechanism, or no "
            "plan-changing action is justified by the observed plan.",
            "",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "Analysis must contain only Why, Observed evidence, Inference, and Validation and risks",
            self.validate(workspace),
        )

    def test_no_action_conclusion_rejects_plan_fields(self) -> None:
        workspace = self.write_case("No optimizer action", "inferred", None)
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "No optimizer action\n\n## Analysis",
            "No optimizer action\n\nPlan before:\nIndexLookUp\n\n## Analysis",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "non-plan-changing Conclusion must contain only Action",
            self.validate(workspace),
        )

    def test_plan_action_requires_before_and_after_plans(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "\nPlan after:\n```text\n"
            "Covering IndexReader; candidate plan was not reproduced\n```\n",
            "\n",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "Plans Before & After must contain only complete Plan before and Plan after blocks",
            self.validate(workspace),
        )

    def test_plan_action_requires_review_sql_in_conclusion(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        sql_start = text.index("\nReview-only SQL:")
        plans_start = text.index("\n## Plans Before & After")
        review_sql = text[sql_start:plans_start]
        text = text[:sql_start] + text[plans_start:]
        text = text.replace("\n## Analysis\n", f"\n## Analysis\n{review_sql}\n", 1)
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "plan-changing Conclusion must contain only Action and concrete review-only SQL",
            self.validate(workspace),
        )

    def test_plan_action_rejects_review_sql_none(self) -> None:
        workspace = self.write_case("Binding first", "plan_verified", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace("CREATE INDEX idx_a ON t (a);", "none", 1)
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "plan-changing Conclusion must contain concrete review-only SQL",
            self.validate(workspace),
        )

    def test_no_action_rejects_plans_in_analysis(self) -> None:
        workspace = self.write_case("No optimizer action", "inferred", None)
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        text = text.replace(
            "Observed evidence:\n",
            "Observed evidence:\nPlan before: IndexLookUp\n",
            1,
        )
        report.write_text(text, encoding="utf-8")
        self.assertIn(
            "non-plan-changing report must omit before/after plans",
            self.validate(workspace),
        )

    def test_conclusion_rejects_verbose_plan_metadata(self) -> None:
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
            "Plans Before & After must contain only complete Plan before and Plan after blocks",
            self.validate(workspace),
        )

    def test_legacy_report_format_requires_explicit_compatibility_flag(self) -> None:
        workspace = self.write_case("Index first", "inferred", "passed")
        report = workspace / "report" / "report.md"
        text = report.read_text(encoding="utf-8")
        analysis_start = text.index("\n## Analysis")
        legacy = """## Conclusion

Action:
Index first

Plan before:
```text
IndexLookUp with table-row fetch
```

Plan after:
```text
Covering IndexReader; candidate plan was not reproduced
```

Why:
The candidate removes the diagnosed table-row fetch.
""" + text[analysis_start:].replace(
            "## Analysis\n\nWhy:",
            "## Analysis\n\nReview-only SQL:\nReview only. Not executed by AutoX.\n"
            "```sql\nCREATE INDEX idx_a ON t (a);\n```\n\nWhy:",
            1,
        )
        report.write_text(legacy, encoding="utf-8")
        self.assertTrue(
            any(
                error.startswith("invalid top-level report headings")
                for error in self.validate(workspace)
            )
        )
        self.assertEqual(
            [],
            self.validate(workspace, allow_legacy_report_format=True),
        )


if __name__ == "__main__":
    unittest.main()
