#!/usr/bin/env python3
"""Oracle-validated, paired source-backed 100K-point campaigns."""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
import platform
import random
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from feature_contract import (
    ARRIVAL_RATES,
    BUDGET,
    CONCURRENCY,
    DRAIN_SECONDS,
    HONUA_PROFILES,
    MODES,
    fingerprint,
    generator_budget,
    immutable_image,
    oracle,
    request_url,
    validate_plugin_jars,
)
from feature_evidence import calibration_failures, report, summarize
from feature_geoserver import geoserver_sorting
from feature_runtime import (
    DB_FINGERPRINT_SQL,
    LABEL,
    Observer,
    cleanup,
    command,
    inspect,
    owned_ids,
    sql,
)
from feature_sql_evidence import validate_source_trace

ROOT = Path(__file__).resolve().parents[1]
CONTROL_HOSTS = ("localhost", "host.docker.internal")


def write(path, data):
    temp = Path(str(path) + ".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def source_fingerprint():
    paths = command("git", "ls-files", "--cached", "--others", "--exclude-standard", cwd=ROOT).splitlines()
    return fingerprint({path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                        for path in paths if (ROOT / path).is_file()})


def tree_hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def verify_snapshot(directory, manifest):
    if tree_hashes(directory / "harness") != manifest.get("snapshot_sha256"):
        raise ValueError("Archived harness snapshot is missing or has changed")


def docker_engine_identity():
    engine = json.loads(command("docker", "info", "--format", "{{json .}}"))
    keys = ("ID", "Name", "OperatingSystem", "OSType", "Architecture", "KernelVersion",
            "NCPU", "MemTotal", "ServerVersion", "CgroupDriver", "CgroupVersion")
    if any(not engine.get(key) for key in keys) or any(type(engine[key]) is not int or engine[key] <= 0 for key in ("NCPU", "MemTotal")):
        raise ValueError("Missing Docker engine identity/resource evidence")
    # Select explicitly: docker info can also contain proxy URLs with credentials.
    return {key: engine[key] for key in keys}


def host_identity():
    cpu = Path('/proc/cpuinfo').read_text().split("\n\n", 1)[0]
    stable_cpu = [line for line in cpu.splitlines() if line.startswith(("vendor_id", "model name", "cpu family", "model\t", "stepping"))]
    return {"node": platform.node(), "platform": platform.platform(), "logical_cpus": os.cpu_count(),
            "cpu": stable_cpu, "memory_total": Path('/proc/meminfo').read_text().splitlines()[0],
            "docker_engine": docker_engine_identity()}


def resolve_images(args):
    images = {}
    for key in (*args.servers, "postgis", "k6"):
        value = getattr(args, key + "_image")
        if not immutable_image(value):
            raise ValueError(f"{key} image must be pinned by digest (registry@sha256 or local sha256 ID)")
        image = json.loads(command("docker", "image", "inspect", value))[0]
        images[key] = {"reference": value, "id": image["Id"], "digests": image.get("RepoDigests", []), "architecture": image["Architecture"], "os": image["Os"],
                       "labels": image.get("Config", {}).get("Labels", {}) or {}}
    if args.mode == "comparison":
        labels = images["honua"]["labels"]
        if labels.get("honua.runtime.compilation") != "native-aot" or not labels.get("org.opencontainers.image.revision"):
            raise ValueError("Comparison requires a revision-labelled production Honua Native AOT image")
    return images


def make_compose(owner, server, images, honua_profile="baseline", generator_cpus=BUDGET["cpus"], control_host="localhost"):
    load_budget = generator_budget(generator_cpus)
    if control_host not in CONTROL_HOSTS:
        raise ValueError(f"Unknown control host: {control_host}")
    if honua_profile not in HONUA_PROFILES:
        raise ValueError(f"Unknown Honua profile: {honua_profile}")
    env = {**os.environ, **{key.upper() + "_IMAGE": value["reference"] for key, value in images.items()},
           "HONUA_ADAPTIVE_ADMISSION_ENABLED": "false", "HONUA_MAX_CONCURRENT_QUERIES": "6",
           "HONUA_MAX_CONNECTION_POOL_SIZE": "6", "HONUA_MIN_CONNECTION_POOL_SIZE": "3",
           "GEOSERVER_INSTALL_EXTENSIONS": "false", "GEOSERVER_STABLE_EXTENSIONS": "",
           "GEOSERVER_COMMUNITY_EXTENSIONS": "", "POSTGIS_LOG_MIN_DURATION_STATEMENT": "-1"}
    original = json.loads(command("docker", "compose", "-f", str(ROOT / "docker-compose.yml"),
                                  "--profile", server, "config", "--format", "json", env=env, cwd=ROOT))
    services = {key: original["services"][key] for key in (server, "postgis-" + server, "k6")}
    labels = {LABEL: owner}
    for name, service in services.items():
        service.pop("profiles", None)
        service.pop("ports", None)
        service["labels"] = labels
        service["networks"] = {"default": {"aliases": [name]}}
        service["pull_policy"] = "never"
        budget = load_budget if name == "k6" else BUDGET
        service["deploy"] = {"resources": {"limits": {"cpus": str(budget["cpus"]), "memory": str(budget["memory_bytes"])}}}
        if name == server:
            service["ports"] = [{"target": 8080, "host_ip": "127.0.0.1", "published": "0", "protocol": "tcp"}]
        if name.startswith("postgis-"):
            service["command"] = ["postgres", "-c", "max_connections=200"]
        if name == "k6":
            service["user"] = f"{os.getuid()}:{os.getgid()}"
    # Compare the same exact count-metadata policy. Oracle preflight verifies the result.
    if server == "honua":
        services[server]["environment"]["OgcFeatures__NumberMatchedPolicy"] = "Exact"
        # Owned, isolated databases use production connection reset behavior.
        services[server]["environment"]["HONUA_TEST_SCHEMA_HEADERS"] = "false"
        if control_host == "host.docker.internal":
            services[server]["environment"]["HostValidation__AllowedHosts__2"] = control_host
        services[server]["environment"].update(HONUA_PROFILES[honua_profile])
    return {"services": services,
            "volumes": {f"pgdata-{server}": {"labels": labels}},
            "networks": {"default": {"labels": labels}}}


def record_resources(owner):
    return {kind: owned_ids(owner, kind) for kind in ("container", "volume", "network")}


def runtime_receipt(ids, images, honua_profile=None, generator_cpus=BUDGET["cpus"]):
    load_budget = generator_budget(generator_cpus)
    if honua_profile is not None and honua_profile not in HONUA_PROFILES:
        raise ValueError(f"Unknown Honua profile: {honua_profile}")
    # Capture only profile-owned keys: other Database values may contain secrets.
    planner_keys = {key for options in HONUA_PROFILES.values() for key in options}
    result = {"docker_engine": docker_engine_identity()}
    for name, identity in ids.items():
        info = inspect(identity)
        role = "postgis" if name.startswith("postgis-") else name
        result[name] = {"container": identity, "image": info["Image"],
                        "cpus": info["HostConfig"]["NanoCpus"] / 1e9,
                        "memory": info["HostConfig"]["Memory"],
                        "environment": [e for e in info["Config"].get("Env", [])
                                        if e.partition("=")[0] in planner_keys or e.startswith(("Limits__", "Cache__", "OgcFeatures__", "INSTALL_EXTENSIONS=", "STABLE_EXTENSIONS=", "COMMUNITY_EXTENSIONS=", "ASPNETCORE_ENVIRONMENT=", "HONUA_TEST_SCHEMA_HEADERS=", "HostValidation__AllowedHosts__"))]}
        if name == "honua":
            schema_entries = [e for e in result[name]["environment"]
                              if e.partition("=")[0] == "HONUA_TEST_SCHEMA_HEADERS"]
            if schema_entries != ["HONUA_TEST_SCHEMA_HEADERS=false"]:
                raise ValueError("Honua test-schema configuration drift: production setting required")
            planner_entries = [e.split("=", 1) for e in result[name]["environment"]
                               if e.partition("=")[0] in planner_keys]
            if honua_profile is not None and (len(planner_entries) != len(dict(planner_entries)) or
                    dict(planner_entries) != HONUA_PROFILES[honua_profile]):
                raise ValueError(f"Honua planner configuration drift: {honua_profile}")
            maps = command("docker", "exec", identity, "cat", "/proc/1/maps")
            result[name]["coreclr_mapped"] = "libcoreclr" in maps or "libclrjit" in maps
            result[name]["command"] = command("docker", "exec", identity, "cat", "/proc/1/cmdline").replace("\x00", " ").strip()
            if images[role]["labels"].get("honua.runtime.compilation") == "native-aot" and result[name]["coreclr_mapped"]:
                raise ValueError("Honua runtime contradicts its Native AOT image label")
        budget = load_budget if name == "k6" else BUDGET
        if info["Image"] != images[role]["id"] or result[name]["cpus"] != budget["cpus"] or result[name]["memory"] != budget["memory_bytes"]:
            raise ValueError(f"Runtime image/resource drift: {name}")
    return result


def geoserver_store(base, password):
    request = Request(base + "/geoserver/rest/workspaces/geobench/datastores/postgis.json",
                      headers={"Authorization": "Basic " + base64.b64encode(("admin:" + password).encode()).decode()})
    with urlopen(request, timeout=30) as response:
        entries = json.load(response)["dataStore"]["connectionParameters"]["entry"]
    params = {entry["@key"]: entry["$"] for entry in entries}
    if int(params.get("max connections", 0)) != BUDGET["source_connections"] or int(params.get("min connections", -1)) != 3:
        raise ValueError("GeoServer effective source pool differs from bounded profile")
    if str(params.get("Expose primary keys", "")).lower() != "true":
        raise ValueError("GeoServer must expose the id property for explicit query ordering")
    return {key: value for key, value in params.items() if key not in {"passwd", "password", "user"}}


def preflight_results(log):
    for line in log.splitlines():
        # k6 JSON console output keeps messages machine-readable.
        try:
            message = json.loads(line).get("msg", "")
        except (ValueError, AttributeError):
            continue
        if message.startswith("PREFLIGHT "):
            return json.loads(message[len("PREFLIGHT "):])
    raise ValueError("Missing semantic preflight receipt")


def run_k6(ids, directory, config, name):
    config_file = directory / (name + "-input.json")
    output = directory / (name + ".jsonl")
    write(config_file, config)
    relative = directory.relative_to(ROOT / "results")
    args = ["docker", "exec", ids["k6"], "k6", "run", "--quiet", "--log-format", "json",
            "--out", f"json=/results/{relative}/{output.name}",
            "--env", f"CAMPAIGN_INPUT=/results/{relative}/{config_file.name}",
            "/tests/feature-campaign.js"]
    with (directory / (name + ".log")).open("w") as log:
        process = subprocess.run(args, check=False, stdout=log, stderr=subprocess.STDOUT, timeout=config["duration"] + DRAIN_SECONDS + 180)
    checks = preflight_results((directory / (name + ".log")).read_text())
    write(directory / (name + "-preflight.json"), checks)
    expected_ids = {r["id"] for r in config["requests"] + config.get("preflight_requests", [])}
    observed_ids = [row["id"] for row in checks]
    if set(observed_ids) != expected_ids or len(observed_ids) != len(expected_ids):
        raise ValueError(f"{name}: incomplete or duplicated semantic preflight receipt")
    if process.returncode or any(row["failure"] for row in checks):
        if config["protocol"] == "gsr":
            write(directory / "coverage-gaps.json", [{"request": r["id"], "reason": r["failure"]}
                  for r in checks if r["failure"]])
        raise ValueError(f"{name}: semantic preflight/load failed; see retained log")
    return output, checks


def wait_ready(compose, server, log):
    subprocess.run([*compose, "up", "-d", "--wait", "--wait-timeout", "300"], check=True,
                   stdout=log, stderr=subprocess.STDOUT, timeout=360)


def execute_attempt(directory, manifest, attempt, save, calibration_workload=None):
    verify_snapshot(directory, manifest)
    generator_cpus = manifest.get("generator_budget", generator_budget())["cpus"]
    server = attempt["server"]
    fixture = manifest.setdefault("fixtures", {}).get(server) if manifest.get("reuse_fixture") else None
    owner = manifest["owner"] + ("-fixture-" + server if manifest.get("reuse_fixture") else "-" + attempt["id"])
    if fixture and (fixture["binding"] != manifest["binding"] or record_resources(owner) != fixture["resources"]):
        raise ValueError("Owned fixture identity or fingerprint has changed")
    path = directory / attempt["id"]
    path.mkdir()
    compose_file = path / "compose.json"
    composition = make_compose(owner, server, manifest["images"], manifest.get("honua_profile", "baseline"), generator_cpus, manifest.get("control_host", "localhost"))
    for volume in composition["services"]["k6"]["volumes"]:
        if volume.get("target") == "/tests":
            volume["source"] = str(directory / "harness" / "src/tests")
    write(compose_file, composition)
    compose = ["docker", "compose", "-p", owner, "-f", str(compose_file)]
    identities = {}
    ids = {}
    attempt.update({"status": "running", "owner": owner, "rows": {}, "fairness_failures": []})
    save()
    try:
        with (path / "provision.log").open("w") as log:
            try:
                wait_ready(compose, server, log)
            finally:
                identities = record_resources(owner)
                attempt["resources"] = identities
                save()
            ids = {name: command(*compose, "ps", "-q", name) for name in (server, "postgis-" + server, "k6")}
            runtime = runtime_receipt(ids, manifest["images"], manifest.get("honua_profile", "baseline"), generator_cpus)
            write(path / "runtime.json", runtime)
            if runtime["docker_engine"] != manifest["host_identity"]["docker_engine"]:
                raise ValueError("Docker engine identity/resource drift from prepared campaign")
            if server == "geoserver":
                jars = command("docker", "exec", ids[server], "sh", "-c",
                               "find /usr/local/tomcat/webapps/geoserver/WEB-INF/lib -name '*.jar' -exec sha256sum {} +").splitlines()
                versions = validate_plugin_jars(jars, manifest["protocol"] == "gsr")
                write(path / "plugins.json", {"versions": versions, "sha256": sorted(jars),
                      "java": command("docker", "exec", ids[server], "java", "-version", stderr=subprocess.STDOUT)})
            if fixture and (runtime != fixture["runtime"] or fingerprint(sql(ids["postgis-" + server], DB_FINGERPRINT_SQL)) != fixture["database_fingerprint"]):
                raise ValueError("Reused fixture runtime/database fingerprint changed")
            port = inspect(ids[server])["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
            base = f"http://{manifest.get('control_host', 'localhost')}:{port}"
            env = {**os.environ, "COMPOSE_PROJECT_NAME": owner, "COMPOSE_FILE": str(compose_file),
                   "HONUA_URL": base, "GS_URL": base, "HONUA_STORAGE_PROFILE": "source",
                   "HONUA_API_KEY": composition["services"][server]["environment"].get("HONUA_ADMIN_PASSWORD", "GeoBench-Admin-Key-2026!"),
                   "GS_PASS": composition["services"][server]["environment"].get("GEOSERVER_ADMIN_PASSWORD", "geoserver"),
                   "HONUA_RESTART_ON_VERIFY_FAIL": "0", "GEOBENCH_TESTS": "attribute-filter",
                   "GEOSERVER_MAX_CONNECTIONS": "6", "GEOSERVER_MIN_CONNECTIONS": "3"}
            if not fixture:
                subprocess.run(["bash", str(directory / "harness" / "adapters" / server / "setup.sh")], env=env, cwd=ROOT,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        store = geoserver_store(base, env["GS_PASS"]) if server == "geoserver" else None
        service = None
        if store:
            write(path / "effective-store.json", store)
            if manifest["protocol"] == "ogc":
                service = geoserver_sorting(base, env["GS_PASS"], configure=not fixture)
                write(path / "effective-service.json", service)
        db = ids["postgis-" + server]
        command("docker", "exec", db, "psql", "-U", "geobench", "-d", "geobench", "-c", "ANALYZE public.bench_points")
        database = sql(db, DB_FINGERPRINT_SQL)
        write(path / "database.json", database)
        if database["rows"] != 100000 or not database["analyzed"]:
            raise ValueError("Dataset must contain 100K analyzed points")
        attempt["database_fingerprint"] = fingerprint(database)
        expected = oracle(manifest["corpus"], lambda statement: sql(db, statement))
        # Ascending IDs can coincide with natural database order even when sortby
        # is ignored. This reverse-order probe is preflight-only for both servers.
        probe_corpus = {**manifest["corpus"], "requests": [{"id": "ordering-desc", "order": "desc"}]}
        expected["preflight_requests"] = oracle(probe_corpus, lambda statement: sql(db, statement))["requests"]
        for request in expected["requests"] + expected["preflight_requests"]:
            request["url"] = request_url(server, manifest["protocol"], request, f"http://{server}:8080", expected["limit"])
        write(path / "oracle.json", expected)
        config = {**expected, "protocol": manifest["protocol"], "duration": 1, "drain": DRAIN_SECONDS,
                  "phase": "warmup", "scenario": "equality", "vus": 1}
        # Separate SQL diagnostic pass: inspect actual reads, then disable tracing before warmup.
        for statement in ("ALTER SYSTEM SET log_min_duration_statement=0", "SELECT pg_reload_conf()"):
            command("docker", "exec", db, "psql", "-U", "geobench", "-d", "geobench", "-c", statement)
        since = datetime.now(timezone.utc).isoformat()
        _, checks = run_k6(ids, path, config, "preflight")
        trace = command("docker", "logs", "--since", since, db, stderr=subprocess.STDOUT)
        (path / "source-query.log").write_text(trace)
        for statement in ("ALTER SYSTEM SET log_min_duration_statement=-1", "SELECT pg_reload_conf()"):
            command("docker", "exec", db, "psql", "-U", "geobench", "-d", "geobench", "-c", statement)
        profile = manifest.get("honua_profile", "baseline") if server == "honua" else None
        write(path / "source-query.json", validate_source_trace(trace, profile))
        attempt["response_contract"] = [{k: v for k, v in row.items() if k != "failure"} for row in checks]
        # Pressure probe is diagnostic traffic before any timed comparison.
        config.update({"duration": 6, "vus": 10, "phase": "warmup"})
        with Observer(path, list(ids.values()), db) as pressure_observer:
            run_k6(ids, path, config, "pressure-probe")
        pressure_receipt = pressure_observer.summary()
        write(path / "pressure-probe.json", pressure_receipt)
        pressure = pressure_receipt["max_database_pressure"]
        if pressure_receipt["failures"] or not pressure_receipt["samples"]:
            raise ValueError("Pressure diagnostic has missing observations")
        if pressure["source_sessions"] > BUDGET["source_connections"] or pressure["source_active"] > BUDGET["source_connections"]:
            raise ValueError("Fairness preflight: observed source-query pressure exceeds six connections")

        if calibration_workload is not None:
            # Separate calibration ledger: this never creates comparison measurement rows.
            summary = calibration_workload(path, ids, db, config, attempt, save)
        else:
            if manifest["mode"] == "comparison":
                reasons = calibration_failures(manifest.get("calibration"), manifest["binding"])
                if reasons:
                    raise ValueError("Comparison calibration prerequisite: " + "; ".join(reasons))
            with Observer(path, list(ids.values()), db) as observer:
                for scenario in manifest["scenarios"]:
                    parts = scenario.split(":")
                    config.update({"scenario": parts[0], "vus": int(parts[2]) if len(parts) == 3 and parts[1] == "vus" else 10,
                                   "rate": int(parts[2]) if len(parts) == 3 and parts[1] == "rate" else None})
                    print(f"{attempt['id']} {scenario}: warmup, measurement, drain", flush=True)
                    observer.activity = scenario + ":warmup-and-drain"
                    config.update({"phase": "warmup", "duration": manifest["warmup"]})
                    warm_path, _ = run_k6(ids, path, config, scenario + "-warmup")
                    warm = summarize(warm_path, manifest["warmup"], "warmup")
                    if warm["failures"]:
                        raise ValueError(f"Warmup failed: {warm['failures']}")
                    observer.activity = scenario + ":measurement-and-drain"
                    config.update({"phase": "measurement", "duration": manifest["measurement"]})
                    measured_path, _ = run_k6(ids, path, config, scenario + "-measurement")
                    row = summarize(measured_path, manifest["measurement"])
                    row.update({"warmup": warm, "offered_rate": config["rate"], "offered_iterations": config["rate"] * manifest["measurement"] if config["rate"] else None, "vus": config["vus"]})
                    required = set(manifest["corpus"]["mixed"]) if parts[0] == "mixed" else {parts[0]}
                    if not required <= set(row["requests"]):
                        row["failures"].append("missing measured corpus requests")
                    attempt["rows"][scenario] = row
                    save()
                    if row["failures"]:
                        raise ValueError(f"Measured scenario failed: {row['failures']}")
            summary = observer.summary()
        write(path / "bottlenecks.json", summary)
        if summary["failures"] or not summary["samples"]:
            attempt["fairness_failures"].append("missing/failed five-second telemetry")
        pressure = summary["max_database_pressure"]
        if pressure["source_sessions"] > BUDGET["source_connections"] or pressure["source_active"] > BUDGET["source_connections"]:
            attempt["fairness_failures"].append("observed source-query pressure exceeds six connections")
        # Verify effective settings and image/resource identity again after traffic.
        if runtime_receipt(ids, manifest["images"], manifest.get("honua_profile", "baseline"), generator_cpus) != runtime or fingerprint(sql(db, DB_FINGERPRINT_SQL)) != attempt["database_fingerprint"]:
            attempt["fairness_failures"].append("runtime/database configuration drift")
        if server == "geoserver":
            current_jars = command("docker", "exec", ids[server], "sh", "-c",
                "find /usr/local/tomcat/webapps/geoserver/WEB-INF/lib -name '*.jar' -exec sha256sum {} +").splitlines()
            if sorted(jars) != sorted(current_jars) or geoserver_store(base, env["GS_PASS"]) != store:
                attempt["fairness_failures"].append("GeoServer plugin or datastore configuration drift")
            if service is not None:
                current_service = geoserver_sorting(base, env["GS_PASS"])
                write(path / "effective-service-after.json", current_service)
                if current_service != service:
                    attempt["fairness_failures"].append("GeoServer feature service configuration drift")
        attempt["status"] = "passed" if not attempt["fairness_failures"] else "failed"
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        attempt.update({"status": "failed", "error": str(exc)})
        if (path / "coverage-gaps.json").exists():
            attempt["coverage_gaps"] = json.loads((path / "coverage-gaps.json").read_text())
        print(f"{attempt['id']}: {exc}", flush=True)
    except KeyboardInterrupt:
        attempt.update({"status": "interrupted", "error": "interrupted; retained as failed evidence"})
        raise
    finally:
        for name, identity in ids.items():
            if name != "k6":
                with contextlib.suppress(subprocess.SubprocessError):
                    (path / (name + "-container.log")).write_text(command("docker", "logs", identity, stderr=subprocess.STDOUT))
        # Recover IDs even when provisioning was interrupted. Never remove other projects.
        identities = record_resources(owner)
        attempt["resources"] = identities
        save()
        if manifest.get("reuse_fixture") and attempt["status"] == "passed":
            command("docker", "stop", *identities["container"])
            manifest["fixtures"][server] = {"owner": owner, "resources": identities, "runtime": runtime,
                "binding": manifest["binding"], "database_fingerprint": attempt["database_fingerprint"]}
            write(directory / "campaign.json", manifest)
            attempt["cleaned"] = False
        else:
            cleanup(owner, identities)
            manifest.get("fixtures", {}).pop(server, None)
            attempt["cleaned"] = True
        attempt["artifact_sha256"] = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in path.rglob("*") if p.is_file()}
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="diagnostic")
    parser.add_argument("--servers", nargs="+", choices=("honua", "geoserver"), default=["honua", "geoserver"])
    parser.add_argument("--protocol", choices=("ogc", "gsr"), default="ogc")
    parser.add_argument("--honua-profile", choices=HONUA_PROFILES, default="baseline",
                        help="Separate explicit database-planner controls from automatic bounded planning")
    parser.add_argument("--generator-cpus", type=int, default=BUDGET["cpus"],
                        help="Positive integer k6 CPU budget, equal for both products; server/database budgets stay fixed")
    parser.add_argument("--control-host", choices=CONTROL_HOSTS, default="localhost",
                        help="Host for provisioning HTTP only; Docker Desktop coordinators use host.docker.internal")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Write immutable inputs and calibration binding without starting stacks")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenarios", help="Comma-separated corpus IDs or mixed:vus:N / mixed:rate:N")
    parser.add_argument("--arrival-rates", action="store_true")
    parser.add_argument("--reuse-fixture", action="store_true", help="Diagnostic only: reuse owned fingerprint-verified fixtures between repetitions")
    parser.add_argument("--smoke", action="store_true", help="Diagnostic only: one repetition, 2s warmup, 3s measurement")
    parser.add_argument("--calibration", type=Path)
    for key in ("honua", "geoserver", "postgis", "k6"):
        parser.add_argument("--" + key + "-image", default=os.environ.get(key.upper() + "_IMAGE", ""))
    args = parser.parse_args()
    try:
        load_budget = generator_budget(args.generator_cpus)
    except ValueError as exc:
        parser.error(str(exc))
    if len(set(args.servers)) != len(args.servers) or (args.mode == "comparison" and set(args.servers) != {"honua", "geoserver"}):
        parser.error("Comparison requires both servers; duplicate servers are invalid")
    if args.reuse_fixture and args.mode != "diagnostic":
        parser.error("Fixture reuse is diagnostic only")
    if args.smoke and args.mode != "diagnostic":
        parser.error("Smoke overrides are diagnostic only")
    if args.honua_profile != "baseline" and "honua" not in args.servers:
        parser.error("A tuned Honua profile requires Honua in --servers")
    os.chdir(ROOT)
    corpus = json.loads((ROOT / "config/feature-corpus-v1.json").read_text())
    scenarios = args.scenarios.split(",") if args.scenarios else [r["id"] for r in corpus["requests"]] + [f"mixed:vus:{v}" for v in CONCURRENCY]
    if args.arrival_rates:
        scenarios += [f"mixed:rate:{rate}" for rate in ARRIVAL_RATES]
    valid = {r["id"] for r in corpus["requests"]} | {f"mixed:vus:{v}" for v in CONCURRENCY} | {f"mixed:rate:{v}" for v in ARRIVAL_RATES}
    if not scenarios or len(set(scenarios)) != len(scenarios) or not set(scenarios) <= valid:
        parser.error("Unknown or duplicate scenarios")
    images = resolve_images(args)
    dataset = ROOT / "data/small/init.sql"
    if not dataset.exists():
        subprocess.run([sys.executable, "data/small/generate.py"], check=True)
    manifest = {"schema": 1, "mode": args.mode, "protocol": args.protocol,
                "reuse_fixture": args.reuse_fixture, "control_host": args.control_host,
                "honua_profile": args.honua_profile,
                "profile": ("stable-ogc" if args.protocol == "ogc" else "community-gsr") + "-source-bounded",
                **MODES[args.mode], "scenarios": scenarios, "servers": args.servers,
                "budget": BUDGET, "generator_budget": load_budget,
                "seed": args.seed, "images": images, "corpus": corpus,
                "host_identity": host_identity(),
                "harness": {"commit": command("git", "rev-parse", "HEAD"), "content": source_fingerprint()},
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "honua_compilation": images.get("honua", {}).get("labels", {}).get("honua.runtime.compilation", "unverified-diagnostic"),
                "effective_compose": {s: make_compose("fingerprint", s, images, args.honua_profile, args.generator_cpus, args.control_host) for s in args.servers}}
    if args.honua_profile != "baseline":
        manifest["profile"] += "-honua-" + args.honua_profile
    if args.generator_cpus != BUDGET["cpus"]:
        manifest["profile"] += f"-generator-{args.generator_cpus}cpu"
    if "honua" in args.servers and manifest["honua_compilation"] != "native-aot":
        manifest["profile"] += "-honua-jit-or-unverified-diagnostic"
    if args.smoke:
        manifest.update({"repetitions": 1, "warmup": 2, "measurement": 3, "smoke": True})
    manifest["binding"] = fingerprint(manifest)
    directory = (args.output or ROOT / "results" / ("features-" + time.strftime("%Y%m%dT%H%M%S"))).resolve()
    if not directory.is_relative_to(ROOT / "results"):
        parser.error("Output must be under results/ for the read-only input/output mount")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        existing_manifest = directory / "campaign.json"
        if existing_manifest.exists():
            existing = json.loads(existing_manifest.read_text())
            if not args.resume or existing["binding"] != manifest["binding"]:
                raise ValueError("Resume refused before writing artifacts: configuration/harness fingerprint differs, or --resume missing")
        if args.calibration:
            calibration = json.loads(args.calibration.read_text())
            archive = directory / "calibration"
            archive.mkdir(exist_ok=True)
            for key in ("observer_off", "observer_on", "isolated_generator"):
                for index, row in enumerate(calibration.get(key, [])):
                    source = args.calibration.resolve().parent / row["raw_points"]
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    if digest != row["sha256"]:
                        raise ValueError("Calibration source artifact hash mismatch")
                    target = archive / f"{key}-{index}-{digest}.jsonl"
                    if target.exists() and target.read_bytes() != source.read_bytes():
                        raise ValueError("Calibration archive cannot overwrite different evidence")
                    if not target.exists():
                        shutil.copyfile(source, target)
                    row["raw_points"] = str(target)
            manifest["calibration"] = calibration
        manifest_file = directory / "campaign.json"
        attempts_file = directory / "attempts.json"
        if manifest_file.exists():
            previous = json.loads(manifest_file.read_text())
            if not args.resume or previous["binding"] != manifest["binding"]:
                raise ValueError("Resume refused: workload/image/dataset/configuration/harness fingerprint differs, or --resume missing")
            if args.calibration:
                previous["calibration"] = manifest["calibration"]
                write(manifest_file, previous)
            manifest = previous
            attempts = json.loads(attempts_file.read_text())
            for attempt in attempts:
                if attempt["status"] in {"running", "scheduled"}:
                    attempt.update({"status": "interrupted", "error": "interrupted attempt retained; new campaign required for publication"})
                if not attempt.get("cleaned") and attempt.get("owner"):
                    cleanup(attempt["owner"], record_resources(attempt["owner"]))
                    attempt["cleaned"] = True
            manifest["fixtures"] = {}
        else:
            manifest["owner"] = "gb-" + uuid.uuid4().hex[:12]
            manifest["host"] = {"platform": platform.platform(), "cpu_count": os.cpu_count(), "load": os.getloadavg(),
                                "cpuinfo": Path('/proc/cpuinfo').read_text(), "memory": Path('/proc/meminfo').read_text()}
            first = random.Random(args.seed).randrange(len(args.servers))
            manifest["order"] = [manifest["servers"][(first + i) % len(args.servers):] + manifest["servers"][:(first + i) % len(args.servers)]
                                 for i in range(manifest["repetitions"])]
            attempts = []
            for folder in ("src/tests", "adapters", "scripts", "config"):
                shutil.copytree(ROOT / folder, directory / "harness" / folder, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copyfile(ROOT / "docker-compose.yml", directory / "harness" / "docker-compose.yml")
            manifest["snapshot_sha256"] = tree_hashes(directory / "harness")
            write(manifest_file, manifest)
        verify_snapshot(directory, manifest)
        def save():
            write(attempts_file, attempts)
        save()
        if args.prepare_only:
            print(f"Prepared {directory}; calibration binding: {manifest['binding']}")
            return 0
        try:
            for rep, order in enumerate(manifest["order"], 1):
                for server in order:
                    if any(a["repetition"] == rep and a["server"] == server for a in attempts):
                        continue  # Never silently replace a failed attempt.
                    attempt = {"id": f"pair{rep}-{server}", "server": server, "repetition": rep, "status": "scheduled"}
                    attempts.append(attempt)
                    save()
                    execute_attempt(directory, manifest, attempt, save)
                if args.mode == "comparison" and any(a["repetition"] == rep and a["status"] != "passed" for a in attempts):
                    # Avoid hours of load after a reproducibility/correctness prerequisite fails.
                    for pending_rep in range(rep + 1, manifest["repetitions"] + 1):
                        for pending_server in manifest["order"][pending_rep - 1]:
                            if not any(a["repetition"] == pending_rep and a["server"] == pending_server for a in attempts):
                                attempts.append({"id": f"pair{pending_rep}-{pending_server}", "repetition": pending_rep,
                                                 "server": pending_server, "status": "not-run", "rows": {},
                                                 "error": "earlier pair failed prerequisites; scheduled repetition remains missing"})
                    save()
                    break
        finally:
            for fixture in manifest.get("fixtures", {}).values():
                cleanup(fixture["owner"], fixture["resources"])
                for attempt in attempts:
                    if attempt.get("owner") == fixture["owner"]:
                        attempt["cleaned"] = True
            manifest["fixtures"] = {}
            write(manifest_file, manifest)
            save()
            result = report(directory, manifest, attempts)
            print(f"Evidence: {directory}/report.md; valid={result['valid']}, publishable={result['publishable']}", flush=True)
        return 0 if (result["publishable"] if args.mode == "comparison" else result["valid"]) else 1


if __name__ == "__main__":
    def interrupt(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    with contextlib.suppress(BrokenPipeError), open(f"/tmp/geobench-feature-campaign-{os.getuid()}.lock", "a") as host_lock:
        try:
            fcntl.flock(host_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit("Another feature campaign owns this host's measurement lock")
        sys.exit(main())
