#!/usr/bin/env python3
"""Quick validation for AutoX Skill files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"
MARKER_RE = re.compile(r"\{\{[^}]+\}\}|<<[^>]+>>")
BACKTICK_REF_RE = re.compile(r"`([^`\n]+\.md)`")


def skill_root(path: Path) -> Path:
    path = path.resolve()
    for parent in [path.parent, *path.parents]:
        if parent.parent == SKILLS_DIR:
            return parent
    return path.parent


def resolve_ref(source: Path, ref: str) -> Path | None:
    if ref.startswith(("http://", "https://")):
        return None

    candidates = [
        (source.parent / ref).resolve(),
        (skill_root(source) / ref).resolve(),
        (REPO_ROOT / ref).resolve(),
    ]
    for candidate in candidates:
        try:
            candidate.relative_to(REPO_ROOT)
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    return candidates[0]


def iter_skill_markdown(paths: list[str]) -> list[Path]:
    if paths:
        selected = []
        for raw in paths:
            path = (REPO_ROOT / raw).resolve()
            if path.is_dir():
                selected.extend(sorted(path.rglob("*.md")))
            elif path.suffix == ".md":
                selected.append(path)
        return selected
    return sorted(SKILLS_DIR.rglob("*.md"))


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")

    for match in MARKER_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: unresolved marker {match.group(0)!r}")

    for match in BACKTICK_REF_RE.finditer(text):
        ref = match.group(1)
        if "/" not in ref and "\\" not in ref:
            continue
        if "<" in ref or ">" in ref:
            continue
        if ref.startswith(("report/", "cases/")):
            continue
        resolved = resolve_ref(path, ref)
        if resolved is not None and not resolved.exists():
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.relative_to(REPO_ROOT)}:{line}: broken reference {ref!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AutoX Skill markdown files.")
    parser.add_argument("paths", nargs="*", help="Skill files or directories to validate.")
    args = parser.parse_args()

    files = iter_skill_markdown(args.paths)
    errors: list[str] = []
    for path in files:
        errors.extend(validate_file(path))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"validated {len(files)} markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
