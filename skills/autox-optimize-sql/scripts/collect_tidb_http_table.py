#!/usr/bin/env python3
"""Collect table schema and statistics through TiDB status HTTP API.

This script is intentionally read-only. It only issues HTTP GET requests to a
TiDB status endpoint, such as http://10.0.0.1:10080, and never uses the MySQL
SQL protocol.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IDENT_RE = re.compile(r"^[A-Za-z0-9_$.\-]+$")


class CollectionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only TiDB table schema/stats via status HTTP API."
    )
    parser.add_argument(
        "--tidb-http",
        required=True,
        help="TiDB status HTTP base URL, for example http://10.0.0.1:10080.",
    )
    parser.add_argument("--db", required=True, help="Database name.")
    parser.add_argument("--table", required=True, help="Table name.")
    parser.add_argument(
        "--stats-time",
        help=(
            "Optional snapshot time accepted by TiDB stats dump API, for example "
            "20260623153000 or '2026-06-23 15:30:00'."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path. Defaults to stdout.",
    )
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    validate_identifier(args.db, "--db")
    validate_identifier(args.table, "--table")
    if args.stats_time and "/" in args.stats_time:
        parser.error("--stats-time must not contain '/'")
    return args


def validate_identifier(value: str, label: str) -> None:
    if not value or not IDENT_RE.fullmatch(value):
        raise SystemExit(f"{label} contains unsupported characters: {value!r}")


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CollectionError("--tidb-http must be an http(s) base URL")
    return value


def quote_path_part(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def get_json(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    url = f"{base_url}{path}"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return {
            "ok": False,
            "url": redact_url(url),
            "status": exc.code,
            "error": detail or exc.reason,
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "url": redact_url(url),
            "error": str(exc.reason),
        }

    text = body.decode("utf-8", errors="replace")
    try:
        data: Any = json.loads(text) if text else None
    except json.JSONDecodeError:
        data = text[:2000]
    return {
        "ok": 200 <= status < 300,
        "url": redact_url(url),
        "status": status,
        "content_type": content_type,
        "data": data,
    }


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    safe = parsed._replace(netloc=parsed.hostname or "")
    if parsed.port is not None:
        safe = safe._replace(netloc=f"{safe.netloc}:{parsed.port}")
    return urllib.parse.urlunparse(safe)


def main() -> int:
    args = parse_args()
    try:
        base_url = normalize_base_url(args.tidb_http)
        db = quote_path_part(args.db)
        table = quote_path_part(args.table)

        endpoints: dict[str, str] = {
            "status": "/status",
            "schema": f"/schema/{db}/{table}",
            "stats": f"/stats/dump/{db}/{table}",
        }
        if args.stats_time:
            endpoints["stats"] = (
                f"/stats/dump/{db}/{table}/{quote_path_part(args.stats_time)}"
            )

        result = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "tidb_http": redact_url(base_url),
                "api_reference": "https://github.com/pingcap/tidb/blob/master/docs/tidb_http_api.md",
                "method": "HTTP GET only",
            },
            "target": {
                "db": args.db,
                "table": args.table,
                "stats_time": args.stats_time,
            },
            "endpoints": endpoints,
            "responses": {
                name: get_json(base_url, path, args.timeout)
                for name, path in endpoints.items()
            },
        }

        text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        else:
            sys.stdout.write(text + "\n")
        return 0
    except CollectionError as exc:
        print(f"collect_tidb_http_table.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
