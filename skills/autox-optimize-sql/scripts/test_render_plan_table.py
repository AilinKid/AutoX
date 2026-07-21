#!/usr/bin/env python3
"""Tests for TiDB plan table rendering."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("render_plan_table.py")
SPEC = importlib.util.spec_from_file_location("render_plan_table", MODULE_PATH)
assert SPEC and SPEC.loader
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


class RenderPlanTableTest(unittest.TestCase):
    def test_renders_decoded_plan_as_tidb_explain_tree(self) -> None:
        plan = {
            "main": {
                "name": "IndexLookUp_10",
                "estRows": 2,
                "actRows": "1",
                "taskType": "root",
                "rootBasicExecInfo": "time:2ms, loops:2",
                "children": [
                    {
                        "name": "IndexRangeScan_8",
                        "estRows": 2,
                        "actRows": "1",
                        "taskType": "cop",
                        "storeType": "tikv",
                        "accessObjects": [{
                            "scanObject": {
                                "database": "test",
                                "table": "t",
                                "indexes": [{"name": "idx_a", "cols": ["a"]}],
                            }
                        }],
                        "copExecInfo": "scan_detail: {total_process_keys: 1}",
                    }
                ],
            },
            "withRuntimeStats": True,
        }
        rows = RENDERER.tree_rows_from_decoded_plan(plan)
        text = RENDERER.render_fixed_width(rows, 0, include_runtime_footer=True)
        self.assertTrue(text.startswith("id"))
        self.assertIn("access object", text.splitlines()[0])
        self.assertIn("IndexLookUp_10", text)
        self.assertIn("└─IndexRangeScan_8", text)
        self.assertIn("cop[tikv]", text)
        self.assertIn("table:test.t, index:idx_a(a)", text)
        self.assertIn("total_process_keys: 1", text)
        self.assertNotIn('"main"', text)

    def test_rejects_value_without_decoded_plan(self) -> None:
        self.assertIsNone(RENDERER.find_decoded_plan({"withRuntimeStats": True}))


if __name__ == "__main__":
    unittest.main()
