#!/usr/bin/env python3
"""Release-phase Performance: build-host load diagnostic at the Launch Stack Small and Medium shapes.

Runs on the build host inside one remote-run slot, from the geobench checkout root:
    remote-run python3 scripts/gc-cohort-diagnostic.py --image sha256:<digest> --source <revision>
        [--sizes Small,Medium] [--runs 3]

Diagnostic only. It emulates the task and database shapes with container CPU/memory limits on an x86 host;
it is not the AWS qualification in honua-marketplace docs/aws-capacity.md (no Fargate, no RDS, no ALB/CloudFront).
Pool settings are the values the server derives for each size (DeploymentConnectionPoolSizing), set explicitly
because the geobench compose file always passes them. Rate limiting and response caching are off, as in geobench,
so the numbers measure query execution rather than 429s or cache hits.
"""

import argparse
import json
import math
import os
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import threading
import time
from itertools import pairwise
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

KEYRING_DIR = (
    Path.cwd() / ".gc-cohort-keyring"
)  # never under artifacts/, so it is not copied back
BAR_P95_MS = 500.0

# Pool: max(4, int(maxconn_assumed * 0.8) // (tasks * 2)); min 2; MaxConcurrentQueries = min(200, pool).
# Small: 2 GiB*90=180 -> 144//4 = 36. Medium: 4 GiB*90=360 -> 288//8 = 36.
# Database max_connections approximates RDS LEAST(DBInstanceClassMemory/9531392, 5000); shared_buffers is RDS's 25%.
SIZES = {
    "Small": {
        "cpus": "1",
        "mem": "2g",
        "db_cpus": "2",
        "db_mem": "2g",
        "tasks": 2,
        "cls": "db.t4g.small",
        "pool": 36,
        "db_max_conn": 190,
        "shared_buffers": "512MB",
    },
    "Medium": {
        "cpus": "2",
        "mem": "4g",
        "db_cpus": "2",
        "db_mem": "4g",
        "tasks": 4,
        "cls": "db.t4g.medium",
        "pool": 36,
        "db_max_conn": 410,
        "shared_buffers": "1GB",
    },
}


def sh(*args, check=True, env=None, capture=True):
    p = subprocess.run(args, check=False, text=True, capture_output=capture, env=env)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"{args[0]} {args[1] if len(args) > 1 else ''} exit {p.returncode}: {(p.stderr or '')[-400:]}"
        )
    return p


def free_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_keyring():
    """Throwaway self-signed PKCS#12 outside the artifact directory; returns its export password."""
    shutil.rmtree(KEYRING_DIR, ignore_errors=True)
    KEYRING_DIR.mkdir(mode=0o755)
    password = secrets.token_hex(24)
    key, crt, pfx = (
        KEYRING_DIR / n for n in ("keyring.key", "keyring.crt", "operation-keyring.pfx")
    )
    sh(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "2",
        "-subj",
        "/CN=geobench-loadsize-keyring",
        "-keyout",
        str(key),
        "-out",
        str(crt),
    )
    sh(
        "openssl",
        "pkcs12",
        "-export",
        "-in",
        str(crt),
        "-inkey",
        str(key),
        "-out",
        str(pfx),
        "-passout",
        "env:LOADSIZE_KEYRING_PASSWORD",
        env=dict(os.environ, LOADSIZE_KEYRING_PASSWORD=password),
    )
    key.unlink()
    crt.unlink()
    pfx.chmod(
        0o644
    )  # the container user (61001) is not the file owner; the export password still encrypts it
    return password


def capture_server(env, prefix, stop):
    """Keep the latest honua container log and state; run-benchmark.sh removes the stack on failure."""
    while not stop.wait(5):
        cid = subprocess.run(
            ["docker", "compose", "--profile", "honua", "ps", "-aq", "honua"],
            check=False,
            env=env,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not cid:
            continue
        logs = subprocess.run(
            ["docker", "logs", "--tail", "3000", cid],
            check=False,
            capture_output=True,
            text=True,
        )
        if logs.stdout or logs.stderr:
            prefix.with_suffix(".log").write_text(logs.stdout + logs.stderr)
        state = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{end}} started={{.State.StartedAt}} pid={{.State.Pid}}",
                cid,
            ],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if state:
            prefix.with_suffix(".state").write_text(state + "\n")
        sample = {
            "time": time.time(),
            "load": os.getloadavg(),
            "id": cid,
            "state": state,
        }
        stats = sh(
            "docker", "stats", "--no-stream", "--format", "{{json .}}", cid, check=False
        )
        if stats.returncode == 0 and stats.stdout.strip():
            try:
                sample["stats"] = json.loads(stats.stdout)
            except ValueError:
                sample["stats_error"] = "invalid docker stats JSON"
        # Read kernel process RSS and cgroup peak without requiring a shell inside chiseled images.
        inspect = sh(
            "docker", "inspect", "--format", "{{.State.Pid}}", cid, check=False
        )
        try:
            pid = int(inspect.stdout.strip())
            status = Path(f"/proc/{pid}/status").read_text()
            sample["rss_bytes"] = (
                int(
                    next(
                        x.split()[1]
                        for x in status.splitlines()
                        if x.startswith("VmRSS:")
                    )
                )
                * 1024
            )
            cgroup = Path(f"/proc/{pid}/cgroup").read_text().split("0::", 1)[1].strip()
            peak = Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "memory.peak"
            sample["cgroup_peak_bytes"] = int(peak.read_text())
        except (OSError, ValueError, IndexError, StopIteration) as exc:
            sample["memory_read_error"] = str(exc)
        try:
            request = Request(
                f"http://127.0.0.1:{env['HONUA_PORT']}/metrics",
                headers={
                    "Host": f"localhost:{env['HONUA_PORT']}",
                    "X-API-Key": env.get(
                        "HONUA_ADMIN_PASSWORD", "GeoBench-Admin-Key-2026!"
                    ),
                },
            )
            with urlopen(request, timeout=3) as response:
                metrics = response.read(8 * 1024 * 1024).decode()
            sample["gc_metrics"] = [
                line for line in metrics.splitlines() if line.startswith("dotnet_gc_")
            ]
            pauses = [
                float(match.group(1))
                for line in sample["gc_metrics"]
                if (
                    match := re.match(
                        r"dotnet_gc_pause_time(?:_seconds)?(?:_total)?(?:\{[^}]*\})?\s+([0-9.eE+-]+)",
                        line,
                    )
                )
            ]
            if pauses and all(math.isfinite(value) and value >= 0 for value in pauses):
                sample["gc_pause_seconds_total"] = sum(pauses)
        except HTTPError as exc:
            sample["gc_metrics_error"] = f"HTTPError:{exc.code}"
        except (URLError, OSError, ValueError) as exc:
            sample["gc_metrics_error"] = type(exc).__name__
        # Metrics and process evidence must belong to the same container lifetime.
        # Include StartedAt and PID so a restart in progress cannot reuse the earlier identity.
        after = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{end}} started={{.State.StartedAt}} pid={{.State.Pid}}",
                cid,
            ],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not state or state != after:
            sample.pop("gc_pause_seconds_total", None)
            sample.pop("gc_metrics", None)
            sample["gc_metrics_error"] = (
                "container lifetime changed during metrics collection"
            )
        with prefix.with_suffix(".samples.jsonl").open("a") as f:
            f.write(json.dumps(sample) + "\n")


GC_PROFILES = {
    "defaults": {},  # baseline: shipped image/runtime defaults, no GC overrides
    "fixed": {"DOTNET_GCDynamicAdaptationMode": "0"},
    "heap60": {"DOTNET_GCHeapHardLimitPercent": "3C"},
}


def runtime_summary(path):
    samples = (
        [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    )

    def peak(key):
        values = [x[key] for x in samples if key in x]
        return max(values) if values else None

    states = [x.get("state", "") for x in samples]
    pause_groups = {}
    for sample in samples:
        value = sample.get("gc_pause_seconds_total")
        restart = re.search(r"\brestarts=(\d+)\b", sample.get("state", ""))
        if (
            restart
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value >= 0
        ):
            lifetime = (sample["id"], int(restart[1]))
            pause_groups.setdefault(lifetime, []).append(value)
    pause_deltas = [
        values[-1] - values[0]
        for values in pause_groups.values()
        if len(values) >= 2 and all(b >= a for a, b in pairwise(values))
    ]
    return {
        "gc_pause_seconds_observed_delta": sum(pause_deltas) if pause_deltas else None,
        "gc_pause_scope": "sampled cumulative counter delta including startup and warmup; no individual pause distribution",
        "memory_evidence_complete": bool(
            samples
            and peak("rss_bytes") is not None
            and peak("cgroup_peak_bytes") is not None
        ),
        "samples": len(samples),
        "sampled_peak_process_rss_bytes": peak("rss_bytes"),
        "cgroup_peak_bytes": peak("cgroup_peak_bytes"),
        "container_ids": sorted({x["id"] for x in samples}),
        "max_load1": max((x["load"][0] for x in samples), default=None),
        "oom_observed": any("oom=true" in s for s in states),
        "max_restarts": max(
            (
                int(s.split("restarts=")[1].split()[0])
                for s in states
                if "restarts=" in s
            ),
            default=None,
        ),
    }


def override(size, cfg, pg_port, image):
    gc_env = "\n".join(
        f'      {key}: "{value}"'
        for key, value in GC_PROFILES[cfg["gc_profile"]].items()
    )
    return f"""# generated by gc-cohort-diagnostic.py for {size}
services:
  postgis-honua:
    ports: !override
      - "127.0.0.1:{pg_port}:5432"
    command: ["postgres", "-c", "max_connections={cfg["db_max_conn"]}", "-c", "shared_buffers={cfg["shared_buffers"]}",
              "-c", "log_min_duration_statement=-1"]
    deploy:
      resources:
        limits: {{cpus: "{cfg["db_cpus"]}", memory: {cfg["db_mem"]}}}
  honua:
    image: {image}
    pull_policy: never
    # Build-host only: the PR Gate runner hooks pkill UIDs 1001/1002 (the image default), as in cohort compose.cohort-uid.yaml.
    user: "61001:1001"
    volumes:
      - "{KEYRING_DIR}:/keyring:ro"
    environment:
{gc_env}
      # Production refuses to boot without a key-ring certificate (as in load-soak-nightly.yml); this one is per run and deleted after.
      Operations__SecretChannel__KeyRingCertificatePath: /keyring/operation-keyring.pfx
      Operations__SecretChannel__KeyRingCertificatePassword: "${{LOADSIZE_KEYRING_PASSWORD:?driver sets it}}"
      Deployment__MaxTasks: "{cfg["tasks"]}"
      Database__InstanceClass: "{cfg["cls"]}"
      Limits__Connections__MaxConnectionPoolSize: "{cfg["pool"]}"
      Limits__Connections__MinConnectionPoolSize: "2"
      Limits__Connections__MaxConcurrentQueries: "{cfg["pool"]}"
      Limits__Connections__AdaptiveConcurrencyEnabled: "false"
      Limits__Connections__AdaptiveConcurrencyMinQueries: "1"
      Limits__Connections__AdaptiveConcurrencyInitialQueries: "0"
      Limits__Connections__AdaptiveConcurrencyMaxQueries: "0"
    deploy:
      resources:
        limits: {{cpus: "{cfg["cpus"]}", memory: {cfg["mem"]}}}
"""


def metric(m, key, field):
    v = m.get(key) or {}
    return v.get(field)


def summarize(results_dir, levels, duration_s, expected_runs):
    per_level = {}
    runs = sorted(results_dir.glob("honua-concurrent-run*.json"))
    for lvl in levels:
        p95s, p99s, rps, err, failed = [], [], [], [], []
        for r in runs:
            m = json.loads(r.read_text()).get("metrics", {})
            k = f"{{concurrency:{lvl}}}"
            p = metric(m, "http_req_duration" + k, "p(95)")
            p99 = metric(m, "http_req_duration" + k, "p(99)")
            c = metric(m, "http_reqs" + k, "count")
            e = metric(m, "errors" + k, "value")
            f = metric(m, "http_req_failed" + k, "value")
            if p is not None:
                p95s.append(p)
            if p99 is not None:
                p99s.append(p99)
            if c is not None:
                rps.append(c / duration_s)
            if e is not None:
                err.append(e)
            if f is not None:
                failed.append(f)
        row = {
            "runs": len(p95s),
            "p99_ms_median": round(statistics.median(p99s), 1) if p99s else None,
            "p99_ms_range": [round(min(p99s), 1), round(max(p99s), 1)]
            if p99s
            else None,
            "p95_ms_median": round(statistics.median(p95s), 1) if p95s else None,
            "p95_ms_range": [round(min(p95s), 1), round(max(p95s), 1)]
            if p95s
            else None,
            "rps_median": round(statistics.median(rps), 1) if rps else None,
            "error_rate_max": max(err) if err else None,
            "http_failed_rate_max": max(failed) if failed else None,
        }
        row["complete"] = (
            len(runs) == expected_runs
            and all(len(v) == expected_runs for v in (p95s, p99s, rps, err, failed))
            and all(
                math.isfinite(x) and x >= 0
                for v in (p95s, p99s, err, failed)
                for x in v
            )
            and all(math.isfinite(x) and x > 0 for x in rps)
        )
        row["meets_bar"] = bool(
            row["complete"]
            and max(p95s) < BAR_P95_MS
            and not any(err)
            and not any(failed)
        )
        per_level[str(lvl)] = row
    passing = [int(l) for l, r in per_level.items() if r["meets_bar"]]
    return {
        "levels": per_level,
        "highest_vus_meeting_bar": max(passing) if passing else None,
        "run_files": len(runs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--image",
        required=True,
        help="existing immutable Docker image ID or platform digest",
    )
    ap.add_argument(
        "--source", required=True, help="full source revision matching the image label"
    )
    ap.add_argument("--profile", choices=tuple(GC_PROFILES), default="defaults")
    ap.add_argument("--sizes", default="Small,Medium")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--levels", default="1,10,50,100")
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=30)
    ap.add_argument(
        "--max-load",
        type=float,
        default=16.0,
        help="1-minute load ceiling (0 < max-load <= 16); compare only controlled quiet-host runs",
    )
    a = ap.parse_args()
    if a.runs < 1 or a.duration < 1 or a.warmup < 1:
        ap.error("runs, duration and warmup must be positive")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", a.image) or not re.fullmatch(
        r"[0-9a-f]{40}", a.source
    ):
        ap.error(
            "image must be an immutable sha256 digest and source must be a full revision"
        )
    sizes = a.sizes.split(",")
    if (
        not sizes
        or any(size not in SIZES for size in sizes)
        or len(set(sizes)) != len(sizes)
    ):
        ap.error("sizes must be a unique comma-separated selection of Small,Medium")
    try:
        levels = [int(x) for x in a.levels.split(",")]
    except ValueError:
        ap.error("levels must be comma-separated positive integers")
    if not levels or min(levels) < 1 or len(set(levels)) != len(levels):
        ap.error("levels must be unique positive integers")
    if not math.isfinite(a.max_load) or not 0 < a.max_load <= 16:
        ap.error("max-load must be finite, positive and at most 16")
    root = Path.cwd()
    assert (root / "scripts/run-benchmark.sh").exists(), (
        "run from the geobench checkout root"
    )
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + a.profile
    out = root / "artifacts/gc-diagnostic" / stamp
    out.mkdir(parents=True, exist_ok=True)
    result = {
        "kind": "build-host diagnostic, not AWS qualification",
        "image": a.image,
        "source": a.source,
        "bar": f"every request succeeds and p95 < {BAR_P95_MS:.0f} ms per level",
        "started": stamp,
        "gc_profile": a.profile,
        "gc_environment": GC_PROFILES[a.profile],
        "storage_profile": "source (live bench_points table)",
        "levels": a.levels,
        "duration_s": a.duration,
        "warmup_s": a.warmup,
        "runs": a.runs,
        "sizes": {},
    }

    def save():
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    load1 = os.getloadavg()[0]
    result["load_at_start"] = {
        "load1": load1,
        "cpus": os.cpu_count(),
    }
    if load1 > a.max_load:
        result["verdict"] = "NOT_QUIET"
        save()
        print(json.dumps({"verdict": "NOT_QUIET", "load1": load1, "max": a.max_load}))
        return 3
    result["load_at_start"]["containers"] = len(sh("docker", "ps", "-q").stdout.split())
    # Shared-host runs are diagnostics; comparative timing needs a quiet, controlled rerun.
    result["host_quiet"] = load1 <= 16.0
    result["interpretation"] = (
        "quiet host"
        if result["host_quiet"]
        else "busy host: diagnostic only; comparative timing needs a quiet rerun"
    )

    meta = json.loads(sh("docker", "image", "inspect", a.image).stdout)[0]
    if meta["Config"]["Labels"].get("org.opencontainers.image.revision") != a.source:
        raise RuntimeError("image revision mismatch")
    result["runtime"] = meta["Config"]["Labels"].get(
        "honua.runtime.compilation", "unknown"
    )
    result["compose_version"] = sh(
        "docker", "compose", "version", "--short"
    ).stdout.strip()
    # Read the shipped configuration without launching a shell or runtime in the image.
    cid = sh("docker", "create", a.image).stdout.strip()
    try:
        config_path = out / "Honua.Server.runtimeconfig.json"
        copied = sh(
            "docker",
            "cp",
            f"{cid}:/app/Honua.Server.runtimeconfig.json",
            str(config_path),
            check=False,
        )
        if copied.returncode == 0:
            result["shipped_runtimeconfig"] = json.loads(config_path.read_text())
        elif result["runtime"] == "native-aot":
            result["shipped_runtimeconfig"] = None
            result["runtimeconfig_note"] = (
                "Absent in Native AOT; compiled GC configuration requires runtime evidence."
            )
        else:
            raise RuntimeError(
                "JIT or unknown image has no readable runtime configuration"
            )
        result["shipped_gc_environment"] = [
            v
            for v in meta["Config"].get("Env", [])
            if v.lower().startswith(
                ("dotnet_gc", "complus_gc", "dotnet_processorcount")
            )
        ]
        result["gc_activation_caveat"] = (
            "Configuration evidence only; Server GC may fall back on a single CPU. "
            "Do not infer active DATAS from profile names or timing."
        )
    finally:
        sh("docker", "rm", cid, check=False)
    init_sql = root / "data/small/init.sql"
    if not init_sql.exists():
        sh(sys.executable, "data/small/generate.py", "--output", str(init_sql))
    try:
        keyring_password = make_keyring()
        for size in sizes:
            cfg = dict(SIZES[size], gc_profile=a.profile)
            ov = root / f"docker-compose.loadsize-{size.lower()}.yml"
            ov.write_text(override(size, cfg, free_port(), a.image))
            ts = f"loadsize-{size.lower()}-{stamp}"
            env = dict(
                os.environ,
                COMPOSE_FILE=f"docker-compose.yml:{ov.name}",
                COMPOSE_PROJECT_NAME=f"gc-diagnostic-{size.lower()}-{stamp.lower()}",
                SERVERS="honua",
                TESTS="concurrent",
                RUNS=str(a.runs),
                RESULT_TIMESTAMP=ts,
                HONUA_PORT=str(free_port()),
                CONTINUE_ON_K6_FAILURE="1",
                DIAGNOSTICS="1",
                POSTGIS_LOG_MIN_DURATION_STATEMENT="-1",
                AUDIT_SHAPES="1",
                HONUA_STORAGE_PROFILE="source",
                HONUA_IMAGE=a.image,
                LOADSIZE_KEYRING_PASSWORD=keyring_password,
                HONUA_MAX_CONCURRENT_QUERIES=str(cfg["pool"]),
                HONUA_MAX_CONNECTION_POOL_SIZE=str(cfg["pool"]),
                HONUA_MIN_CONNECTION_POOL_SIZE="2",
                CONCURRENT_LEVELS=a.levels,
                CONCURRENT_DURATION=f"{a.duration}s",
                CONCURRENT_WARMUP=f"{a.warmup}s",
            )
            t0 = time.time()
            stop = threading.Event()
            watcher = threading.Thread(
                target=capture_server,
                args=(env, out / f"{size.lower()}-honua", stop),
                daemon=True,
            )
            watcher.start()
            with open(out / f"{size.lower()}-run-benchmark.log", "w") as log:
                rc = subprocess.run(
                    ["bash", "scripts/run-benchmark.sh"],
                    check=False,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                ).returncode
            stop.set()
            watcher.join(timeout=30)
            src = root / "results" / ts
            entry = {
                "runtime_samples": runtime_summary(
                    out / f"{size.lower()}-honua.samples.jsonl"
                ),
                "config": cfg,
                "exit": rc,
                "elapsed_s": round(time.time() - t0),
                "load1_after": os.getloadavg()[0],
            }
            if src.exists():
                shutil.copytree(src, out / size.lower(), dirs_exist_ok=True)
                entry["summary"] = summarize(src, levels, a.duration, a.runs)
            shutil.copy(ov, out / ov.name)
            result["sizes"][size] = entry
            save()
            print(
                json.dumps(
                    {
                        size: {
                            "exit": rc,
                            "highest_vus_meeting_bar": entry.get("summary", {}).get(
                                "highest_vus_meeting_bar"
                            ),
                        }
                    }
                )
            )
    finally:
        for size in sizes:
            ov = root / f"docker-compose.loadsize-{size.lower()}.yml"
            if ov.exists():
                sh(
                    "docker",
                    "compose",
                    "--profile",
                    "honua",
                    "down",
                    "-v",
                    "--remove-orphans",
                    check=False,
                    env=dict(
                        os.environ,
                        COMPOSE_FILE=f"docker-compose.yml:{ov.name}",
                        COMPOSE_PROJECT_NAME=f"gc-diagnostic-{size.lower()}-{stamp.lower()}",
                        LOADSIZE_KEYRING_PASSWORD="unused",
                    ),
                )
                ov.unlink()
        shutil.rmtree(KEYRING_DIR, ignore_errors=True)
    result["host_quiet"] = bool(
        result["host_quiet"]
        and all(
            s["load1_after"] <= 16.0
            and s["runtime_samples"].get("max_load1") is not None
            and s["runtime_samples"]["max_load1"] <= 16.0
            for s in result["sizes"].values()
        )
    )
    result["interpretation"] = (
        "controlled comparisons still require matching runs"
        if result["host_quiet"]
        else "busy host: diagnostic only; comparative timing needs a quiet rerun"
    )
    result["verdict"] = (
        "COLLECTED"
        if len(result["sizes"]) == len(sizes)
        and all(
            s.get("exit") == 0
            and s.get("runtime_samples", {}).get("memory_evidence_complete")
            and s.get("summary", {}).get("levels")
            and all(row.get("complete") for row in s["summary"]["levels"].values())
            for s in result["sizes"].values()
        )
        else "INCOMPLETE"
    )
    save()
    print(json.dumps({"verdict": result["verdict"], "out": str(out.relative_to(root))}))
    return 0 if result["verdict"] == "COLLECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
