"""Owned Docker resources and lightweight five-second observations."""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

LABEL = "io.geobench.campaign"


def command(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def inspect(container):
    return json.loads(command("docker", "inspect", container))[0]


def owned_ids(owner, kind="container"):
    return command("docker", kind, "ls", "-q", *(["-a"] if kind == "container" else []), "--filter", f"label={LABEL}={owner}").split()


def cleanup(owner, identities):
    """Delete only exact IDs recorded by this campaign, after checking ownership."""
    for kind in ("container", "volume", "network"):
        for identity in identities.get(kind, []):
            try:
                info = json.loads(command("docker", kind, "inspect", identity))[0]
            except subprocess.CalledProcessError:
                continue  # Already removed, never substitute a name or project-wide match.
            labels = info.get("Config", {}).get("Labels", {}) if kind == "container" else info.get("Labels", {})
            if (labels or {}).get(LABEL) != owner:
                raise ValueError(f"Refusing cleanup of unowned {kind}: {identity}")
            args = ["docker", kind, "rm"] + (["-f"] if kind == "container" else [])
            command(*args, identity)


def sql(container, statement):
    output = command("docker", "exec", "-e", "PGAPPNAME=geobench-observer", container,
                     "psql", "-X", "-U", "geobench", "-d", "geobench", "-At", "-v", "ON_ERROR_STOP=1", "-c", statement)
    return json.loads(output) if output else None


DB_FINGERPRINT_SQL = """
SELECT json_build_object(
 'version',version(),'postgis',PostGIS_Full_Version(),
 'rows',(SELECT count(*) FROM public.bench_points),
 'content',(SELECT md5(string_agg(row_to_json(p)::text,'' ORDER BY id)) FROM public.bench_points p),
 'indexes',(SELECT json_agg(indexdef ORDER BY indexname) FROM pg_indexes WHERE schemaname='public' AND tablename='bench_points'),
 'settings',(SELECT json_object_agg(name,setting ORDER BY name) FROM pg_settings
  WHERE name IN ('max_connections','shared_buffers','work_mem','maintenance_work_mem','effective_cache_size',
                'max_parallel_workers','max_parallel_workers_per_gather','random_page_cost','jit','default_statistics_target')),
 'analyzed',(SELECT last_analyze IS NOT NULL FROM pg_stat_user_tables WHERE relname='bench_points'))
"""
PRESSURE_SQL = """
SELECT json_build_object(
 'sessions',count(*) FILTER (WHERE backend_type='client backend'),
 'active',count(*) FILTER (WHERE state='active'),
 'source_sessions',count(*) FILTER (WHERE backend_type='client backend' AND query ILIKE '%bench_points%'),
 'source_active',count(*) FILTER (WHERE state='active' AND query ILIKE '%bench_points%'),
 'parallel_workers',count(*) FILTER (WHERE backend_type='parallel worker'),
 'background',count(*) FILTER (WHERE backend_type NOT IN ('client backend','parallel worker')),
 'applications',COALESCE(json_agg(json_build_object('application',application_name,'state',state,'backend_type',backend_type)), '[]'::json))
FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND application_name<>'geobench-observer'
"""


class Observer:
    def __init__(self, directory, containers, database):
        self.path = Path(directory) / "telemetry.jsonl"
        self.containers = containers
        self.database = database
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.failures = []
        self.max_pressure = {"source_sessions": 0, "source_active": 0, "parallel_workers": 0}
        self.samples = 0

    def run(self):
        deadline = time.monotonic()
        with self.path.open("a") as output:
            while not self.stop_event.is_set():
                start = time.monotonic()
                try:
                    pressure = sql(self.database, PRESSURE_SQL)
                    stats = command("docker", "stats", "--no-stream", "--format", "{{json .}}", *self.containers)
                    row = {"time": time.time(), "database": pressure,
                           "containers": [json.loads(line) for line in stats.splitlines()],
                           "host": {"load": os.getloadavg(), "memory": Path('/proc/meminfo').read_text(),
                                    "cpu": Path('/proc/stat').read_text().splitlines()[0]},
                           "observer_seconds": time.monotonic() - start}
                    for key in self.max_pressure:
                        self.max_pressure[key] = max(self.max_pressure[key], pressure[key])
                    self.samples += 1
                except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
                    row = {"time": time.time(), "error": str(exc)}
                    self.failures.append(str(exc))
                output.write(json.dumps(row) + "\n")
                output.flush()
                deadline += 5
                self.stop_event.wait(max(0, deadline - time.monotonic()))

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop_event.set()
        self.thread.join(timeout=45)
        if self.thread.is_alive():
            self.failures.append("observer did not drain")

    def summary(self):
        return {"samples": self.samples, "max_database_pressure": self.max_pressure,
                "failures": self.failures,
                "interpretation": "Sampled pressure, not an exact session peak; SQL tracing runs separately. CPU, memory and throttling need correlation with raw five-second samples."}
