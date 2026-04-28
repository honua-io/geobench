#!/usr/bin/env python3
"""Sample lightweight runtime diagnostics while a GeoBench stack is active."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample Docker/Postgres/Honua diagnostics.")
    parser.add_argument("--server", required=True, choices=("honua", "geoserver", "qgis"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sentinel", required=True, type=Path)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--honua-url", default="http://localhost:8081")
    parser.add_argument("--honua-api-key", default="GeoBench-Admin-Key-2026!")
    return parser.parse_args()


def run(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def compose_service_id(server: str, service: str) -> str | None:
    result = run(["docker", "compose", "--profile", server, "ps", "-q", service])
    cid = result.stdout.strip()
    return cid or None


def docker_stats(container_ids: list[str]) -> list[dict[str, Any]]:
    if not container_ids:
        return []

    result = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *container_ids], timeout=10.0)
    stats = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            stats.append(json.loads(line))
        except json.JSONDecodeError:
            stats.append({"parseError": line})
    return stats


def pg_activity(server: str) -> dict[str, Any] | None:
    service = f"postgis-{server}"
    sql = """
select json_build_object(
  'active', count(*) filter (where state = 'active'),
  'idle', count(*) filter (where state = 'idle'),
  'idleInTransaction', count(*) filter (where state = 'idle in transaction'),
  'waiting', count(*) filter (where wait_event_type is not null),
  'waitEventTypes', coalesce(json_agg(distinct wait_event_type) filter (where wait_event_type is not null), '[]'::json)
)::text
from pg_stat_activity
where datname = 'geobench';
""".strip()
    result = run(
        [
            "docker",
            "compose",
            "--profile",
            server,
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            "geobench",
            "-d",
            "geobench",
            "-At",
            "-c",
            sql,
        ],
        timeout=10.0,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip() or result.stdout.strip()}
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"parseError": text}


def honua_connection_pool(url: str, api_key: str) -> dict[str, Any] | None:
    request = urllib.request.Request(
        f"{url.rstrip('/')}/monitoring/metrics/connection-pool",
        headers={"X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - diagnostics should record and continue.
        return {"error": str(exc)}

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"parseError": body[:500]}


def service_names(server: str) -> list[str]:
    services = [f"postgis-{server}", "k6"]
    if server == "qgis":
        services.insert(1, "qgis-server")
    else:
        services.insert(1, server)
    return services


def sample(args: argparse.Namespace) -> dict[str, Any]:
    services = service_names(args.server)
    service_ids = {service: compose_service_id(args.server, service) for service in services}
    container_ids = [cid for cid in service_ids.values() if cid]
    payload: dict[str, Any] = {
        "sampledAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "server": args.server,
        "services": service_ids,
        "dockerStats": docker_stats(container_ids),
        "postgres": pg_activity(args.server),
    }
    if args.server == "honua":
        payload["honuaConnectionPool"] = honua_connection_pool(args.honua_url, args.honua_api_key)
    return payload


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as handle:
        while args.sentinel.exists():
            handle.write(json.dumps(sample(args), separators=(",", ":")) + "\n")
            handle.flush()
            time.sleep(max(args.interval, 0.5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
