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
        (report_dir / "report.md").write_text(
            f"""## Conclusion

Recommended action:
{action}

Review-only SQL:
Review only. Not executed by AutoX.
```sql
CREATE INDEX idx_a ON t (a);
```

Provenance:
- Validation status: {validation_status}
- Validation level: {level}
- Advisory gate: {advisory_gate or 'not applicable'}
- Selected candidate ID: idx_a

## Plans Before & After

Plan before:
complete production plan

Plan after:
The candidate plan was not reproduced.

## Analysis

Raw artifact cleanup: cleaned
""",
            encoding="utf-8",
        )
        return workspace

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def validate(self, workspace: Path,
                 allow_legacy_report_name: bool = False) -> list[str]:
        args = Namespace(
            workspace=str(workspace), rank=None, digest=None,
            diagnosis_id=None, json_output=False,
            allow_legacy_report_name=allow_legacy_report_name,
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


if __name__ == "__main__":
    unittest.main()
