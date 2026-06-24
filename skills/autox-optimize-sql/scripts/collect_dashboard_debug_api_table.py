#!/usr/bin/env python3
"""Download table schema and stats through Clinic Dashboard debug_api proxy.

This script is intentionally read-only and is only for Dedicated TiDB Cloud
clusters. It uses the same Dashboard debug_api proxy flow as the Clinic UI:

1. GET  /debug_api/endpoints
2. GET  /topology/tidb
3. POST /debug_api/endpoint to ask Dashboard to call a read-only TiDB status API
4. GET  /debug_api/download?token=... to download the generated JSON file

The POST request is a Dashboard proxy/token request. It must only be used with
documented read-only debug_api endpoint IDs in this script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLUSTER_ID_RE = re.compile(r"^(?:\d+|bran-[A-Za-z0-9_-]+)$")
IDENT_RE = re.compile(r"^[A-Za-z0-9_$.\-]+$")
READ_ONLY_ENDPOINTS = {
    "tidb_schema_by_table",
    "tidb_stats_by_table",
    "tidb_stats_by_table_timestamp",
}


class CollectionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download TiDB table schema/stats JSON through Clinic Dashboard "
            "debug_api proxy."
        )
    )
    parser.add_argument("--cluster-id", required=True)
    parser.add_argument(
        "--org-id",
        help=(
            "Dashboard orgId/tenantID. If omitted, resolve from Clinic "
            "dashboard cluster metadata. The cluster still must be Dedicated."
        ),
    )
    parser.add_argument("--db", required=True, help="Database name.")
    parser.add_argument("--table", required=True, help="Table name.")
    parser.add_argument(
        "--stats-time",
        help=(
            "Optional snapshot time accepted by TiDB stats dump API, for example "
            "20260623153000."
        ),
    )
    parser.add_argument(
        "--tidb-endpoint",
        help=(
            "Optional TiDB status endpoint from Dashboard topology, as "
            "host:status_port. If omitted, choose the first Up TiDB endpoint."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("CLINIC_DIAGNOSTIC_DOWNLOAD_DIR") or "/tmp",
        help="Directory for downloaded JSON files (default: CLINIC_DIAGNOSTIC_DOWNLOAD_DIR or /tmp).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file containing CLINIC_API_KEY and optional CLINIC_ENV.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds (default: 120).",
    )
    parser.add_argument(
        "--manifest",
        help="Optional path for the output manifest JSON. Defaults to stdout.",
    )
    args = parser.parse_args()

    if not CLUSTER_ID_RE.fullmatch(args.cluster_id):
        parser.error("--cluster-id must be numeric or a valid bran-* identifier")
    if args.org_id and not args.org_id.isdigit():
        parser.error("--org-id must be numeric")
    validate_identifier(args.db, "--db")
    validate_identifier(args.table, "--table")
    if args.stats_time and "/" in args.stats_time:
        parser.error("--stats-time must not contain '/'")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def validate_identifier(value: str, label: str) -> None:
    if not value or not IDENT_RE.fullmatch(value):
        raise SystemExit(f"{label} contains unsupported characters: {value!r}")


def load_env_file(path: str) -> None:
    env_path = Path(path).expanduser()
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def clinic_base() -> str:
    env = os.environ.get("CLINIC_ENV", "prod")
    if env == "dev":
        return "https://dev-clinic.pingcap.com"
    if env == "staging":
        return "https://staging-clinic.pingcap.com"
    return "https://clinic.pingcap.com"


def request_json(
    method: str,
    url: str,
    api_key: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise CollectionError(f"{method} {url} failed: HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        raise CollectionError(f"{method} {url} failed: {exc.reason}") from exc
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text.strip().strip('"')


def request_bytes(url: str, api_key: str, timeout: float) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise CollectionError(f"GET {url} failed: HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        raise CollectionError(f"GET {url} failed: {exc.reason}") from exc


def dashboard_api_base(base: str, org_id: str, cluster_id: str) -> str:
    return (
        f"{base}/clinic/api/v1/dashboard/proxy/orgs/{org_id}"
        f"/clusters/{cluster_id}/pd/dashboard/api"
    )


def resolve_cluster_context(
    base: str,
    api_key: str,
    cluster_id: str,
    timeout: float,
) -> dict[str, str]:
    query = urllib.parse.urlencode(
        {"cluster_id": cluster_id, "show_deleted": "true", "limit": "10", "page": "1"}
    )
    result = request_json(
        "GET",
        f"{base}/clinic/api/v1/dashboard/clusters?{query}",
        api_key,
        timeout,
    )
    items = []
    if isinstance(result, dict):
        for key in ("items", "data", "clusters"):
            if isinstance(result.get(key), list):
                items = result[key]
                break
    exact = None
    for item in items:
        if str(item.get("clusterID") or item.get("clusterId") or item.get("id")) == cluster_id:
            exact = item
            break
    if not exact:
        raise CollectionError(f"could not resolve Dashboard orgId for cluster {cluster_id}")
    org_id = exact.get("tenantID") or exact.get("tenantId") or exact.get("orgID") or exact.get("orgId")
    if not org_id:
        raise CollectionError(f"cluster {cluster_id} metadata does not include tenantID/orgID")
    deploy_type = (
        exact.get("clusterDeployType")
        or exact.get("clusterDeployTypeV2")
        or exact.get("deployType")
        or exact.get("deployTypeV2")
        or ""
    )
    return {"org_id": str(org_id), "deployment_type": normalize_deploy_type(str(deploy_type))}


def normalize_deploy_type(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def ensure_dedicated(deployment_type: str) -> None:
    if deployment_type != "dedicated":
        raise CollectionError(
            "Clinic Dashboard debug_api proxy is supported by this Skill only "
            f"for Dedicated clusters; deployment_type={deployment_type or 'unknown'}"
        )


def endpoint_exists(endpoints: Any, endpoint_id: str) -> bool:
    if not isinstance(endpoints, list):
        return False
    return any(item.get("id") == endpoint_id for item in endpoints if isinstance(item, dict))


def choose_tidb_endpoint(topology: Any, explicit: str | None) -> tuple[str, int, dict[str, Any]]:
    if explicit:
        if ":" not in explicit:
            raise CollectionError("--tidb-endpoint must be host:status_port")
        host, port_text = explicit.rsplit(":", 1)
        return host, int(port_text), {"ip": host, "status_port": int(port_text), "explicit": True}

    if not isinstance(topology, list):
        raise CollectionError("Dashboard /topology/tidb did not return a list")
    for item in topology:
        if not isinstance(item, dict):
            continue
        if item.get("status") == 1 and item.get("ip") and item.get("status_port"):
            return item["ip"], int(item["status_port"]), item
    raise CollectionError("no Up TiDB endpoint with status_port found in Dashboard topology")


def request_debug_api_token(
    api_base: str,
    api_key: str,
    timeout: float,
    endpoint_id: str,
    host: str,
    port: int,
    params: dict[str, Any],
) -> str:
    if endpoint_id not in READ_ONLY_ENDPOINTS:
        raise CollectionError(f"refusing non-read-only debug_api endpoint: {endpoint_id}")
    body = {
        "api_id": endpoint_id,
        "id": endpoint_id,
        "host": host,
        "port": port,
        "param_values": params,
        "params": params,
    }
    token = request_json("POST", f"{api_base}/debug_api/endpoint", api_key, timeout, body)
    if not isinstance(token, str) or not token:
        raise CollectionError(f"debug_api token response for {endpoint_id} is invalid: {token!r}")
    return token


def download_debug_api_file(
    api_base: str,
    api_key: str,
    timeout: float,
    token: str,
    output_path: Path,
) -> dict[str, Any]:
    query = urllib.parse.urlencode({"token": token})
    data, content_type = request_bytes(
        f"{api_base}/debug_api/download?{query}",
        api_key,
        timeout,
    )
    output_path.write_bytes(data)
    try:
        json.loads(data.decode("utf-8"))
        valid_json = True
    except Exception:
        valid_json = False
    return {
        "path": str(output_path),
        "bytes": len(data),
        "content_type": content_type,
        "valid_json": valid_json,
    }


def main() -> int:
    args = parse_args()
    try:
        load_env_file(args.env_file)
        api_key = os.environ.get("CLINIC_API_KEY")
        if not api_key:
            raise CollectionError("CLINIC_API_KEY is not set")
        base = clinic_base()
        context = resolve_cluster_context(base, api_key, args.cluster_id, args.timeout)
        org_id = args.org_id or context["org_id"]
        ensure_dedicated(context["deployment_type"])
        api_base = dashboard_api_base(base, org_id, args.cluster_id)

        endpoints = request_json("GET", f"{api_base}/debug_api/endpoints", api_key, args.timeout)
        for endpoint_id in ("tidb_schema_by_table", "tidb_stats_by_table"):
            if not endpoint_exists(endpoints, endpoint_id):
                raise CollectionError(f"Dashboard debug_api endpoint missing: {endpoint_id}")

        topology = request_json("GET", f"{api_base}/topology/tidb", api_key, args.timeout)
        host, port, node = choose_tidb_endpoint(topology, args.tidb_endpoint)

        output_dir = Path(args.output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"autox-{args.cluster_id}-{args.db}-{args.table}"

        params = {"db": args.db, "table": args.table}
        schema_token = request_debug_api_token(
            api_base,
            api_key,
            args.timeout,
            "tidb_schema_by_table",
            host,
            port,
            params,
        )
        schema = download_debug_api_file(
            api_base,
            api_key,
            args.timeout,
            schema_token,
            output_dir / f"{prefix}-schema.json",
        )

        stats_endpoint = "tidb_stats_by_table"
        stats_params = dict(params)
        if args.stats_time:
            stats_endpoint = "tidb_stats_by_table_timestamp"
            if not endpoint_exists(endpoints, stats_endpoint):
                raise CollectionError(f"Dashboard debug_api endpoint missing: {stats_endpoint}")
            stats_params["yyyyMMddHHmmss"] = args.stats_time
        stats_token = request_debug_api_token(
            api_base,
            api_key,
            args.timeout,
            stats_endpoint,
            host,
            port,
            stats_params,
        )
        stats = download_debug_api_file(
            api_base,
            api_key,
            args.timeout,
            stats_token,
            output_dir / f"{prefix}-stats.json",
        )

        manifest = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "clinic_env": os.environ.get("CLINIC_ENV", "prod"),
                "dashboard_api_base": api_base,
                "method": "Clinic Dashboard debug_api proxy",
                "read_only_tidb_endpoints": [
                    "GET /schema/{db}/{table}",
                    "GET /stats/dump/{db}/{table}",
                ],
            },
            "cluster": {
                "cluster_id": args.cluster_id,
                "org_id": org_id,
                "deployment_type": context["deployment_type"],
            },
            "target": {"db": args.db, "table": args.table, "stats_time": args.stats_time},
            "tidb_endpoint": {
                "host": host,
                "status_port": port,
                "version": node.get("version"),
                "status": node.get("status"),
            },
            "files": {"schema": schema, "stats": stats},
        }
        text = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True)
        if args.manifest:
            Path(args.manifest).write_text(text + "\n", encoding="utf-8")
        else:
            sys.stdout.write(text + "\n")
        return 0
    except CollectionError as exc:
        print(f"collect_dashboard_debug_api_table.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
