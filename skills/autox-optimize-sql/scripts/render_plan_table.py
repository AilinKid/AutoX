#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ELLIPSIS = "..."


def one_line(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(one_line(v) for v in value if one_line(v))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return " ".join(str(value).split())


def shorten(value: Any, limit: int | None) -> str:
    text = one_line(value)
    if limit is None:
        return text
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(ELLIPSIS))] + ELLIPSIS


def number_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return one_line(value)


def task_text(node: dict[str, Any]) -> str:
    task = one_line(node.get("taskType"))
    store = one_line(node.get("storeType"))
    if task and store:
        return f"{task}[{store}]"
    return task or store


def access_object_text(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in node.get("accessObjects") or []:
        if not isinstance(item, dict):
            continue
        scan = item.get("scanObject") or {}
        if not isinstance(scan, dict):
            continue
        db = scan.get("database")
        table = scan.get("table")
        name = ".".join(str(v) for v in (db, table) if v)
        indexes = scan.get("indexes") or []
        if indexes:
            idx_parts = []
            for idx in indexes:
                if not isinstance(idx, dict):
                    continue
                idx_name = idx.get("name")
                cols = idx.get("cols") or []
                if idx_name and cols:
                    idx_parts.append(f"{idx_name}({','.join(map(str, cols))})")
                elif idx_name:
                    idx_parts.append(str(idx_name))
            if idx_parts:
                name = f"{name}, index:{','.join(idx_parts)}" if name else f"index:{','.join(idx_parts)}"
        if name:
            parts.append(name)
    return "; ".join(parts)


def exec_info_text(node: dict[str, Any]) -> str:
    parts = []
    for key in ("rootBasicExecInfo", "rootGroupExecInfo", "copExecInfo"):
        value = one_line(node.get(key))
        if value:
            parts.append(value)
    return "; ".join(parts)


def memory_disk_text(node: dict[str, Any]) -> tuple[str, str]:
    mem = one_line(node.get("memoryBytes"))
    disk = one_line(node.get("diskBytes"))
    return mem, disk


def tree_rows_from_decoded_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    root = plan.get("main", plan)
    rows: list[dict[str, str]] = []

    def walk(node: dict[str, Any], prefix: str, is_last: bool, is_root: bool) -> None:
        if not isinstance(node, dict):
            return
        connector = "" if is_root else ("└─" if is_last else "├─")
        labels = node.get("labels") or []
        label = ""
        if labels and isinstance(labels, list):
            first = str(labels[0])
            if first == "buildSide":
                label = "(Build)"
            elif first == "probeSide":
                label = "(Probe)"
        mem, disk = memory_disk_text(node)
        rows.append(
            {
                "id": f"{prefix}{connector}{one_line(node.get('name'))}{label}",
                "estRows": number_text(node.get("estRows")),
                "estCost": number_text(node.get("cost")),
                "actRows": one_line(node.get("actRows")),
                "task": task_text(node),
                "access": access_object_text(node),
                "exec": exec_info_text(node),
                "operator": one_line(node.get("operatorInfo")),
                "memory": mem,
                "disk": disk,
            }
        )
        children = [c for c in node.get("children") or [] if isinstance(c, dict)]
        child_prefix = prefix if is_root else prefix + ("  " if is_last else "│ ")
        for idx, child in enumerate(children):
            walk(child, child_prefix, idx == len(children) - 1, False)

    if isinstance(root, dict):
        walk(root, "", True, True)
    return rows


def parse_plan_json(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict) and isinstance(value.get("decoded_plan"), str):
        return parse_plan_json(value["decoded_plan"])
    if isinstance(value, dict) and isinstance(value.get("representative_plan"), str):
        return parse_plan_json(value["representative_plan"])
    if isinstance(value, dict) and isinstance(value.get("main"), dict):
        return value
    return None


def find_decoded_plan(data: Any) -> dict[str, Any] | None:
    direct = parse_plan_json(data)
    if direct is not None:
        return direct
    if isinstance(data, dict):
        reps = ((data.get("slow_query") or {}).get("representative_executions") or {})
        if isinstance(reps, dict):
            for key in ("slowest", "largest_process_keys", "latest"):
                values = reps.get(key)
                if isinstance(values, list):
                    for item in values:
                        found = parse_plan_json(item)
                        if found is not None:
                            return found
        for value in data.values():
            found = find_decoded_plan(value)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_decoded_plan(item)
            if found is not None:
                return found
    return None


def load_decoded_plan(path: Path) -> tuple[dict[str, Any], bool]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    data: Any = json.loads(raw)
    if isinstance(data, str):
        data = json.loads(data)
    plan = find_decoded_plan(data)
    if not isinstance(plan, dict):
        raise ValueError("decoded plan input does not contain a decoded plan JSON object")
    return plan, bool(plan.get("withRuntimeStats"))


def parse_mysql_table(text: str) -> tuple[list[str], list[list[str]]]:
    headers: list[str] | None = None
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if re.match(r"^\+[-+]+\+$", line):
            continue
        parts = line.split("|")[1:-1]
        if not parts:
            continue
        cells: list[str] = []
        for idx, raw in enumerate(parts):
            if idx == 0:
                # Remove mysql table cell padding only. Keep the remaining tree
                # prefix in the id column exactly, including leading spaces.
                cell = raw[1:] if raw.startswith(" ") else raw
                cell = cell.rstrip()
            else:
                cell = raw.strip()
            cells.append(cell)
        if headers is None:
            headers = [c.strip() for c in cells]
        else:
            rows.append(cells)
    return headers or [], rows


def rows_from_mysql_table(path: Path) -> list[dict[str, str]]:
    headers, table_rows = parse_mysql_table(path.read_text(encoding="utf-8", errors="replace"))
    if not headers:
        raise ValueError("mysql table input has no header")
    idx = {name: pos for pos, name in enumerate(headers)}
    mapping = {
        "id": "id",
        "estRows": "estRows",
        "estCost": "estCost",
        "actRows": "actRows",
        "task": "task",
        "access object": "access",
        "execution info": "exec",
        "operator info": "operator",
        "memory": "memory",
        "disk": "disk",
    }
    rows: list[dict[str, str]] = []
    for table_row in table_rows:
        out = {v: "" for v in mapping.values()}
        for src, dst in mapping.items():
            if src in idx and idx[src] < len(table_row):
                out[dst] = table_row[idx[src]]
        rows.append(out)
    return rows


def detect_format(path: Path) -> str:
    sample = path.read_text(encoding="utf-8", errors="replace")[:4096].lstrip()
    if sample.startswith("{") or sample.startswith("[") or sample.startswith('"'):
        return "decoded-json"
    if sample.startswith("+") or sample.startswith("|"):
        return "mysql-table"
    raise ValueError("cannot detect plan input format; pass --format explicitly")


def render_fixed_width(rows: list[dict[str, str]], max_line_length: int, include_runtime_footer: bool = False) -> str:
    if not rows:
        return "unavailable"
    preserve_full_text = max_line_length <= 0
    columns = [
        ("id", "id", 42, "left"),
        ("estRows", "estRows", 12, "right"),
        ("estCost", "estCost", 14, "right"),
        ("actRows", "actRows", 8, "right"),
        ("task", "task", 9, "left"),
        ("access", "access", 28, "left"),
        ("exec", "exec", 28, "left"),
        ("operator", "operator", 62, "left"),
        ("memory", "memory", 9, "right"),
        ("disk", "disk", 6, "right"),
    ]
    active = []
    for key, label, cap, align in columns:
        if key in ("id", "estRows", "estCost", "task", "operator") or any(one_line(r.get(key)) for r in rows):
            active.append((key, label, cap, align))

    def build(cols: list[tuple[str, str, int, str]]) -> list[str]:
        shortened: list[dict[str, str]] = []
        for row in rows:
            out: dict[str, str] = {}
            for key, _label, cap, _align in cols:
                value = str(row.get(key) or "") if key == "id" else one_line(row.get(key))
                if preserve_full_text:
                    out[key] = value
                elif key == "id":
                    out[key] = value if len(value) <= cap else value[: max(0, cap - len(ELLIPSIS))] + ELLIPSIS
                else:
                    out[key] = shorten(value, cap)
            shortened.append(out)
        widths = {}
        for key, label, cap, _align in cols:
            full_width = max(len(label), *(len(r[key]) for r in shortened))
            widths[key] = full_width if preserve_full_text else min(cap, full_width)

        def fmt(key: str, value: str, align: str) -> str:
            width = widths[key]
            if align == "right":
                return value.rjust(width)
            return value.ljust(width)

        lines = [
            "  ".join(fmt(key, label, align) for key, label, _cap, align in cols).rstrip(),
            "  ".join("-" * widths[key] for key, _label, _cap, _align in cols).rstrip(),
        ]
        for row in shortened:
            lines.append("  ".join(fmt(key, row[key], align) for key, _label, _cap, align in cols).rstrip())
        return lines

    lines = build(active)
    if not preserve_full_text and max(map(len, lines), default=0) > max_line_length:
        # Prefer shrinking verbose text columns. Never trim id leading tree whitespace.
        caps = {key: cap for key, _label, cap, _align in active}
        overflow = max(map(len, lines)) - max_line_length
        for key, floor in (("operator", 24), ("exec", 18), ("access", 18)):
            if key in caps and overflow > 0 and caps[key] > floor:
                shrink = min(overflow, caps[key] - floor)
                caps[key] -= shrink
                overflow -= shrink
        active = [(key, label, caps.get(key, cap), align) for key, label, cap, align in active]
        lines = build(active)
    if include_runtime_footer:
        lines.extend(["", "withRuntimeStats: True"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render TiDB plans as compact fixed-width tree tables for AutoX reports.")
    parser.add_argument("--input", required=True, help="decoded_plan JSON file or mysql --table EXPLAIN output")
    parser.add_argument("--format", choices=["auto", "decoded-json", "mysql-table"], default="auto")
    parser.add_argument(
        "--max-line-length",
        type=int,
        default=0,
        help="0 means preserve full text; positive values compact long text columns",
    )
    parser.add_argument("--output", help="write rendered table to this file instead of stdout")
    args = parser.parse_args()

    path = Path(args.input)
    fmt = detect_format(path) if args.format == "auto" else args.format
    runtime_footer = False
    if fmt == "decoded-json":
        plan, runtime_footer = load_decoded_plan(path)
        rows = tree_rows_from_decoded_plan(plan)
    elif fmt == "mysql-table":
        rows = rows_from_mysql_table(path)
    else:
        raise AssertionError(fmt)

    rendered = render_fixed_width(rows, args.max_line_length, runtime_footer)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
