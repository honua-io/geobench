#!/usr/bin/env bash
# GeoBench: Isolated benchmark orchestrator.
#
# Runs each server in complete isolation: starts PostGIS + server + k6,
# runs all test categories, tears everything down, then moves to the next server.
# No shared database, no shared buffers, no cross-contamination.
#
# Usage:
#   ./scripts/run-benchmark.sh
#   RUNS=3 ./scripts/run-benchmark.sh
#   SERVERS="honua geoserver" ./scripts/run-benchmark.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TIMESTAMP="${RESULT_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
RESULTS_DIR="${PROJECT_DIR}/results/${TIMESTAMP}"
IFS=' ' read -r -a SERVERS <<< "${SERVERS:-honua geoserver qgis}"
if [ -n "${TESTS:-}" ]; then
  IFS=' ' read -r -a TESTS <<< "${TESTS}"
else
  TESTS=("attribute-filter" "spatial-bbox" "concurrent")
fi
RUNS="${RUNS:-5}"
AUDIT_SHAPES="${AUDIT_SHAPES:-1}"
DIAGNOSTICS="${DIAGNOSTICS:-0}"
DIAGNOSTICS_INTERVAL_SECONDS="${DIAGNOSTICS_INTERVAL_SECONDS:-2}"
RESUME_EXISTING="${RESUME_EXISTING:-0}"
CACHE_TIER_DEFAULT="${CACHE_TIER_DEFAULT:-${CACHE_TIER:-baseline}}"
WMTS_CACHE_TIER="${WMTS_CACHE_TIER:-warm_tile_cache}"
WMTS_CACHE_POLICY="${WMTS_CACHE_POLICY:-warm}"

if [ "${DIAGNOSTICS}" = "1" ]; then
  export POSTGIS_LOG_MIN_DURATION_STATEMENT="${POSTGIS_LOG_MIN_DURATION_STATEMENT:-0}"
fi

mkdir -p "${RESULTS_DIR}"
chmod 777 "${RESULTS_DIR}"

echo "============================================"
echo "  GeoBench — Isolated Server Benchmarks"
echo "============================================"
echo ""
echo "  Results:    ${RESULTS_DIR}"
echo "  Servers:    ${SERVERS[*]}"
echo "  Tests:      ${TESTS[*]}"
echo "  Runs:       ${RUNS}"
echo "  Isolation:  each server gets its own PostGIS"
echo "  Audit:      response-shape samples ${AUDIT_SHAPES}"
echo "  Cache:      default=${CACHE_TIER_DEFAULT}; wmts=${WMTS_CACHE_TIER}"
echo "  Diagnostics:${DIAGNOSTICS}"
echo "  Resume:     ${RESUME_EXISTING}"
echo ""

cd "${PROJECT_DIR}"

STACK_ACTIVE=0
DIAGNOSTICS_MONITOR_PID=""
DIAGNOSTICS_SENTINEL=""

compose_down_all() {
  docker compose \
    --profile honua \
    --profile geoserver \
    --profile qgis \
    down -v --remove-orphans
}

cleanup_k6_runs() {
  docker compose exec -T k6 sh -lc '
    pids=$(ps -ef | awk "/[k]6 run/ { print $2 }")
    if [ -z "$pids" ]; then
      exit 0
    fi

    kill $pids >/dev/null 2>&1 || true
    sleep 1

    pids=$(ps -ef | awk "/[k]6 run/ { print $2 }")
    if [ -n "$pids" ]; then
      kill -9 $pids >/dev/null 2>&1 || true
    fi
  ' >/dev/null 2>&1 || true
}

cleanup_stack() {
  stop_diagnostics_monitor >/dev/null 2>&1 || true
  cleanup_k6_runs
  compose_down_all >/dev/null 2>&1 || true
  STACK_ACTIVE=0
}

teardown_stack() {
  local server="$1"
  stop_diagnostics_monitor >/dev/null 2>&1 || true
  cleanup_k6_runs
  docker compose --profile "${server}" down -v --remove-orphans 2>&1 | tail -3 | sed 's/^/  /' || true
  STACK_ACTIVE=0
}

diagnostics_dir_for_server() {
  echo "${RESULTS_DIR}/diagnostics/$1"
}

start_diagnostics_monitor() {
  local server="$1"

  if [ "${DIAGNOSTICS}" != "1" ]; then
    return 0
  fi

  local diag_dir
  diag_dir="$(diagnostics_dir_for_server "${server}")"
  mkdir -p "${diag_dir}"
  write_diagnostics_marker "${server}" "start" || true
  DIAGNOSTICS_SENTINEL="${diag_dir}/.monitor-running"
  touch "${DIAGNOSTICS_SENTINEL}"

  python3 "${SCRIPT_DIR}/diagnostics-monitor.py" \
    --server "${server}" \
    --output "${diag_dir}/runtime-monitor.ndjson" \
    --sentinel "${DIAGNOSTICS_SENTINEL}" \
    --interval "${DIAGNOSTICS_INTERVAL_SECONDS}" \
    --honua-url "http://localhost:${HONUA_PORT:-8081}" \
    --honua-api-key "${HONUA_ADMIN_PASSWORD:-GeoBench-Admin-Key-2026!}" &
  DIAGNOSTICS_MONITOR_PID="$!"
}

stop_diagnostics_monitor() {
  if [ "${DIAGNOSTICS}" = "1" ] && [ -n "${DIAGNOSTICS_SENTINEL}" ]; then
    local marker_server
    marker_server="$(basename "$(dirname "${DIAGNOSTICS_SENTINEL}")")"
    write_diagnostics_marker "${marker_server}" "end" || true
  fi

  if [ -n "${DIAGNOSTICS_SENTINEL}" ]; then
    rm -f "${DIAGNOSTICS_SENTINEL}"
  fi

  if [ -n "${DIAGNOSTICS_MONITOR_PID}" ]; then
    wait "${DIAGNOSTICS_MONITOR_PID}" 2>/dev/null || true
  fi

  DIAGNOSTICS_MONITOR_PID=""
  DIAGNOSTICS_SENTINEL=""
}

write_diagnostics_marker() {
  local server="$1"
  local marker="$2"

  if [ "${DIAGNOSTICS}" != "1" ]; then
    return 0
  fi

  docker compose --profile "${server}" exec -T "postgis-${server}" \
    psql -U geobench -d geobench -At \
    -c "select 'geobench_diagnostics_${marker}:$(date -Iseconds)';" >/dev/null 2>&1 || true
}

write_diagnostics_artifacts() {
  local server="$1"

  if [ "${DIAGNOSTICS}" != "1" ]; then
    return 0
  fi

  local diag_dir
  diag_dir="$(diagnostics_dir_for_server "${server}")"
  mkdir -p "${diag_dir}"

  local server_service="${server}"
  if [ "${server}" = "qgis" ]; then
    server_service="qgis-server"
  fi

  docker compose --profile "${server}" logs --no-color "${server_service}" > "${diag_dir}/server.log" 2>&1 || true
  docker compose --profile "${server}" logs --no-color "postgis-${server}" > "${diag_dir}/postgis.log" 2>&1 || true
  grep -E "duration: .*statement:" "${diag_dir}/postgis.log" > "${diag_dir}/sql-statements.log" 2>/dev/null || true

  if [ -f "${RESULTS_DIR}/${server}-response-shapes.json" ]; then
    cp "${RESULTS_DIR}/${server}-response-shapes.json" "${diag_dir}/output-shape.json"
  fi
}

result_file_successful() {
  local result_file="$1"

  if [ ! -f "${result_file}" ]; then
    return 1
  fi

  python3 - "${result_file}" <<'PY2'
import json
import sys

path = sys.argv[1]

try:
    with open(path) as f:
        data = json.load(f)
except Exception:
    sys.exit(1)

metrics = data.get("metrics")
if not isinstance(metrics, dict):
    sys.exit(1)

def metric_value(name):
    metric = metrics.get(name)
    if not isinstance(metric, dict):
        return 0.0
    value = metric.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

checks = metrics.get("checks")
check_fails = 0
if isinstance(checks, dict):
    try:
        check_fails = int(checks.get("fails") or 0)
    except (TypeError, ValueError):
        check_fails = 1

if check_fails == 0 and metric_value("errors") <= 0 and metric_value("http_req_failed") <= 0:
    sys.exit(0)

sys.exit(1)
PY2
}

cleanup_on_exit() {
  local status=$?

  if [ "${STACK_ACTIVE}" = "1" ] && [ "${status}" -ne 0 ]; then
    echo ""
    echo "Cleaning up benchmark stack after failure..."
  fi

  cleanup_stack
  return "${status}"
}

trap cleanup_on_exit EXIT

build_k6_env_flags() {
  local flags=()
  local names=(
    GEOSERVICES_DIAG_DURATION
    GEOSERVICES_DIAG_WARMUP
    GEOSERVICES_DIAG_VARIANTS
    GEOSERVICES_QUERY_DURATION
    GEOSERVICES_QUERY_WARMUP
    GEOSERVICES_EXPORT_DURATION
    GEOSERVICES_EXPORT_WARMUP
    GEOSERVICES_EXPORT_VUS
    GEOSERVICES_EXPORT_SCENARIOS
    GEOSERVICES_IDENTIFY_DURATION
    GEOSERVICES_IDENTIFY_WARMUP
    GEOSERVICES_IDENTIFY_VUS
    GEOSERVICES_IDENTIFY_SCENARIOS
    GEOSERVER_GSR_ENABLED
    GEOSERVER_GSR_LAYER_ID
    GEOSERVER_GSR_SERVICE
    GEOSERVER_GSR_URL
    GEOSERVICES_QUERY_VUS
    GEOSERVICES_QUERY_SCENARIOS
    GEOSERVICES_QUERY_SALT_SMALL
    GEOSERVICES_QUERY_SALT_MEDIUM
    GEOSERVICES_QUERY_SALT_LARGE
    ATTRIBUTE_FILTER_DURATION
    ATTRIBUTE_FILTER_WARMUP
    ATTRIBUTE_FILTER_VUS
    ATTRIBUTE_FILTER_SCENARIOS
    SPATIAL_BBOX_DURATION
    SPATIAL_BBOX_WARMUP
    SPATIAL_BBOX_VUS
    SPATIAL_BBOX_SCENARIOS
    CONCURRENT_DURATION
    CONCURRENT_WARMUP
    CONCURRENT_LEVELS
    CONCURRENT_WORKLOADS
    LOG_FAILURES
    WFS_FILTERED_DURATION
    WFS_FILTERED_WARMUP
    WFS_FILTERED_VUS
    WFS_FILTERED_SCENARIOS
    WFS_GETFEATURE_DURATION
    WFS_GETFEATURE_WARMUP
    WFS_GETFEATURE_VUS
    WFS_GETFEATURE_SCENARIOS
    WMS_GETMAP_DURATION
    WMS_GETMAP_WARMUP
    WMS_GETMAP_VUS
    WMS_GETMAP_SCENARIOS
    WMS_GETFEATUREINFO_DURATION
    WMS_GETFEATUREINFO_WARMUP
    WMS_GETFEATUREINFO_VUS
    WMS_GETFEATUREINFO_SCENARIOS
    WMS_FILTERED_DURATION
    WMS_FILTERED_WARMUP
    WMS_FILTERED_VUS
    WMS_FILTERED_SCENARIOS
    WMS_REPROJECTION_DURATION
    WMS_REPROJECTION_WARMUP
    WMS_REPROJECTION_VUS
    WMS_REPROJECTION_SCENARIOS
    WMTS_DURATION
    WMTS_WARMUP
    WMTS_VUS
    WMTS_SCENARIOS
    WCS_DURATION
    WCS_WARMUP
    WCS_VUS
    WCS_SCENARIOS
    WCS_FORMAT
    GEOSERVER_WCS_COVERAGE
    WCS_COVERAGE
    BBOX_TOLERANCE_DEG
  )

  for name in "${names[@]}"; do
    if [ -n "${!name:-}" ]; then
      flags+=(--env "${name}=${!name}")
    fi
  done

  if [ "${#flags[@]}" -eq 0 ]; then
    return 0
  fi

  printf '%s\n' "${flags[@]}"
}

echo "  Resetting any leftover benchmark stack..."
cleanup_stack

# Map server name to its k6 URL
get_server_url() {
  case "$1" in
    honua)     echo "http://honua:8080" ;;
    geoserver) echo "http://geoserver:8080" ;;
    qgis)      echo "http://qgis-server:80" ;;
  esac
}

get_server_probe_url() {
  case "$1" in
    honua)     echo "http://localhost:${HONUA_PORT:-8081}/healthz/live" ;;
    geoserver) echo "http://localhost:${GEOSERVER_PORT:-8082}/geoserver/ogc/features/v1/collections" ;;
    qgis)      echo "http://localhost:${QGIS_PORT:-8083}/wfs3/collections" ;;
  esac
}

get_pgurl() {
  echo "postgresql://geobench:geobench_pass@postgis-$1:5432/geobench"
}

supports_test_for_server() {
  local server="$1"
  local test="$2"

  case "${test}" in
    attribute-filter|spatial-bbox|concurrent|wfs-getfeature)
      return 0
      ;;
    wfs-filtered)
      [[ "${server}" == "honua" || "${server}" == "geoserver" ]]
      return
      ;;
    wms-getmap|wms-reprojection|wms-getfeatureinfo)
      [[ "${server}" == "honua" || "${server}" == "geoserver" || "${server}" == "qgis" ]]
      return
      ;;
    wms-filtered)
      [[ "${server}" == "honua" || "${server}" == "geoserver" ]]
      return
      ;;
    wmts)
      [[ "${server}" == "geoserver" ]]
      return
      ;;
    wcs)
      [[ "${server}" == "geoserver" ]]
      return
      ;;
    geoservices-query)
      if [[ "${server}" == "honua" ]]; then
        return 0
      fi
      if [[ "${server}" == "geoserver" && "${GEOSERVER_GSR_ENABLED:-0}" == "1" ]]; then
        return 0
      fi
      return 1
      ;;
    geoservices-query-diagnostics)
      if [[ "${server}" == "honua" ]]; then
        return 0
      fi
      if [[ "${server}" == "geoserver" && "${GEOSERVER_GSR_ENABLED:-0}" == "1" ]]; then
        return 0
      fi
      return 1
      ;;
    geoservices-export)
      [[ "${server}" == "honua" ]]
      return
      ;;
    geoservices-identify)
      if [[ "${server}" == "honua" ]]; then
        return 0
      fi
      if [[ "${server}" == "geoserver" && "${GEOSERVER_GSR_ENABLED:-0}" == "1" ]]; then
        return 0
      fi
      return 1
      ;;
    *)
      echo "Unknown test: ${test}" >&2
      return 1
      ;;
  esac
}

is_cache_sensitive_spatial_test() {
  case "$1" in
    spatial-bbox|concurrent|wfs-getfeature|wms-getmap|wms-reprojection|wms-getfeatureinfo|wms-filtered|wcs|geoservices-query|geoservices-query-diagnostics|geoservices-export|geoservices-identify)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

validate_cache_policy() {
  case "${CACHE_TIER_DEFAULT}" in
    baseline|warm_service)
      return 0
      ;;
  esac

  local selected=()
  local test
  for test in "${TESTS[@]}"; do
    if is_cache_sensitive_spatial_test "${test}"; then
      selected+=("${test}")
    fi
  done

  if [ "${#selected[@]}" -eq 0 ]; then
    return 0
  fi

  if [ "${ALLOW_SPATIAL_CACHE_ASSISTED:-0}" = "1" ]; then
    echo "  WARNING: cache-assisted spatial/render track explicitly enabled for: ${selected[*]}"
    return 0
  fi

  echo "ERROR: CACHE_TIER_DEFAULT=${CACHE_TIER_DEFAULT} selected for high-cardinality spatial/render test(s): ${selected[*]}" >&2
  echo "Use the baseline default, or set ALLOW_SPATIAL_CACHE_ASSISTED=1 only for a separate cache-assisted track." >&2
  exit 1
}

wait_for_server() {
  local server="$1"
  local max_wait=300
  local elapsed=0
  echo "  Waiting for ${server}..."
  while [ $elapsed -lt $max_wait ]; do
    if curl -fsS "$(get_server_probe_url "${server}")" >/dev/null 2>&1; then
      echo "  ${server} ready (${elapsed}s)"
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "  ERROR: ${server} not ready after ${max_wait}s"
  return 1
}

run_adapter() {
  local server="$1"
  local adapter="${PROJECT_DIR}/adapters/${server}/setup.sh"
  if [ ! -f "${adapter}" ]; then
    echo "  No adapter for ${server}, skipping"
    return 0
  fi

  echo "  Running ${server} adapter..."
  # Run adapter from inside k6 container (has network access to all services)
  case "${server}" in
    honua)
      # Honua needs psql for feature import — run from host with mapped port
      local pg_host_port
      pg_host_port=$(docker compose --profile honua port postgis-honua 5432 2>/dev/null | cut -d: -f2)
      HONUA_URL="http://localhost:${HONUA_PORT:-8081}" \
      HONUA_API_KEY="${HONUA_ADMIN_PASSWORD:-GeoBench-Admin-Key-2026!}" \
      PGURL="postgresql://geobench:geobench_pass@localhost:${pg_host_port}/geobench" \
      bash "${adapter}" 2>&1 | sed 's/^/    /'
      ;;
    geoserver)
      local wmts_cache_policy
      wmts_cache_policy="${WMTS_CACHE_POLICY:-warm}"
      GS_URL="http://localhost:${GEOSERVER_PORT:-8082}" \
      GEOBENCH_TESTS="${TESTS[*]}" \
      WMTS_CACHE_POLICY="${wmts_cache_policy}" \
      bash "${adapter}" 2>&1 | sed 's/^/    /'
      ;;
    qgis)
      QGIS_URL="http://localhost:${QGIS_PORT:-8083}" \
      bash "${adapter}" 2>&1 | sed 's/^/    /'
      ;;
  esac
}

run_response_shape_audit() {
  local server="$1"
  local audit_script="${SCRIPT_DIR}/response-shape-audit.py"
  local output_path="${RESULTS_DIR}/${server}-response-shapes.json"

  if [ "${AUDIT_SHAPES}" = "0" ]; then
    echo "  Response-shape audit disabled"
    return 0
  fi

  if [ ! -f "${audit_script}" ]; then
    echo "  No response-shape audit script found, skipping"
    return 0
  fi

  echo "  Capturing response-shape samples..."
  python3 "${audit_script}" \
    --server "${server}" \
    --tests "${TESTS[@]}" \
    --output "${output_path}" 2>&1 | sed 's/^/    /'
}

write_run_metadata() {
  local output_path="${RESULTS_DIR}/benchmark-metadata.json"

  GEOBENCH_SERVERS="${SERVERS[*]}" \
  GEOBENCH_TESTS="${TESTS[*]}" \
  GEOBENCH_RUNS="${RUNS}" \
  GEOBENCH_AUDIT_SHAPES="${AUDIT_SHAPES}" \
  GEOBENCH_CACHE_TIER_DEFAULT="${CACHE_TIER_DEFAULT}" \
  GEOBENCH_WMTS_CACHE_TIER="${WMTS_CACHE_TIER}" \
  GEOBENCH_WMTS_CACHE_POLICY="${WMTS_CACHE_POLICY}" \
  GEOBENCH_BBOX_TOLERANCE_DEG="${BBOX_TOLERANCE_DEG:-0.0001}" \
  GEOBENCH_ATTRIBUTE_FILTER_SCENARIOS="${ATTRIBUTE_FILTER_SCENARIOS:-equality,range,like}" \
  GEOBENCH_CONCURRENT_LEVELS="${CONCURRENT_LEVELS:-1,10,50,100}" \
  GEOBENCH_CONCURRENT_WORKLOADS="${CONCURRENT_WORKLOADS:-bbox,equality,range,like}" \
  GEOBENCH_HONUA_MAX_CONCURRENT_QUERIES="${HONUA_MAX_CONCURRENT_QUERIES:-6}" \
  GEOBENCH_HONUA_MAX_CONNECTION_POOL_SIZE="${HONUA_MAX_CONNECTION_POOL_SIZE:-6}" \
  GEOBENCH_HONUA_MIN_CONNECTION_POOL_SIZE="${HONUA_MIN_CONNECTION_POOL_SIZE:-3}" \
  GEOBENCH_HONUA_ADAPTIVE_ADMISSION_ENABLED="${HONUA_ADAPTIVE_ADMISSION_ENABLED:-false}" \
  GEOBENCH_HONUA_ADAPTIVE_ADMISSION_MIN_TARGET="${HONUA_ADAPTIVE_ADMISSION_MIN_TARGET:-3}" \
  GEOBENCH_HONUA_ADAPTIVE_ADMISSION_MAX_TARGET="${HONUA_ADAPTIVE_ADMISSION_MAX_TARGET:-6}" \
  GEOBENCH_HONUA_ADAPTIVE_ADMISSION_INITIAL_TARGET="${HONUA_ADAPTIVE_ADMISSION_INITIAL_TARGET:-6}" \
  GEOBENCH_HONUA_ADAPTIVE_ADMISSION_TARGET_DURATION_MS="${HONUA_ADAPTIVE_ADMISSION_TARGET_DURATION_MS:-100}" \
  GEOBENCH_HONUA_ADAPTIVE_ADMISSION_UPDATE_INTERVAL_MS="${HONUA_ADAPTIVE_ADMISSION_UPDATE_INTERVAL_MS:-1000}" \
  GEOBENCH_GEOSERVER_MAX_CONNECTIONS="${GEOSERVER_MAX_CONNECTIONS:-6}" \
  GEOBENCH_GEOSERVER_MIN_CONNECTIONS="${GEOSERVER_MIN_CONNECTIONS:-3}" \
  GEOBENCH_HONUA_IMAGE="${HONUA_IMAGE:-honuaio/honua-server:latest}" \
  GEOBENCH_GEOSERVER_IMAGE="${GEOSERVER_IMAGE:-docker.osgeo.org/geoserver:2.28.0}" \
  GEOBENCH_QGIS_IMAGE="${QGIS_IMAGE:-qgis/qgis-server:3.38}" \
  GEOBENCH_POSTGIS_IMAGE="${POSTGIS_IMAGE:-postgis/postgis:17-3.5}" \
  GEOBENCH_K6_IMAGE="${K6_IMAGE:-grafana/k6:0.54.0}" \
  python3 - "${output_path}" <<'PY2'
import json
import os
import sys

output_path = sys.argv[1]
default_cache_tier = os.environ.get("GEOBENCH_CACHE_TIER_DEFAULT", "baseline")
wmts_cache_tier = os.environ.get("GEOBENCH_WMTS_CACHE_TIER", "warm_tile_cache")
wmts_cache_policy = os.environ.get("GEOBENCH_WMTS_CACHE_POLICY", "warm")
default_concurrent_workloads = ["bbox", "equality", "range", "like"]
default_concurrent_mix = {
    "bbox": 0.40,
    "equality": 0.30,
    "range": 0.20,
    "like": 0.10,
}


def csv_values(name, default):
    raw = os.environ.get(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def duration_seconds(value, default):
    raw = os.environ.get(value, default)
    text = str(raw).strip().lower()
    if text.endswith("ms"):
        return float(text[:-2]) / 1000.0
    if text.endswith("s"):
        return float(text[:-1])
    if text.endswith("m"):
        return float(text[:-1]) * 60.0
    if text.endswith("h"):
        return float(text[:-1]) * 3600.0
    return float(text)


TEST_PROFILES = {
    "attribute-filter": ("ATTRIBUTE_FILTER_DURATION", "120s", "ATTRIBUTE_FILTER_WARMUP", "60s", "ATTRIBUTE_FILTER_VUS", "10", "ATTRIBUTE_FILTER_SCENARIOS", "equality,range,like"),
    "spatial-bbox": ("SPATIAL_BBOX_DURATION", "120s", "SPATIAL_BBOX_WARMUP", "60s", "SPATIAL_BBOX_VUS", "10", "SPATIAL_BBOX_SCENARIOS", "small,medium,large"),
    "concurrent": ("CONCURRENT_DURATION", "120s", "CONCURRENT_WARMUP", "60s", None, None, None, None),
    "wfs-getfeature": ("WFS_GETFEATURE_DURATION", "120s", "WFS_GETFEATURE_WARMUP", "60s", "WFS_GETFEATURE_VUS", "10", "WFS_GETFEATURE_SCENARIOS", "base,small,medium,large"),
    "wfs-filtered": ("WFS_FILTERED_DURATION", "120s", "WFS_FILTERED_WARMUP", "60s", "WFS_FILTERED_VUS", "10", "WFS_FILTERED_SCENARIOS", "equality,range,like"),
    "wms-getmap": ("WMS_GETMAP_DURATION", "120s", "WMS_GETMAP_WARMUP", "60s", "WMS_GETMAP_VUS", "10", "WMS_GETMAP_SCENARIOS", "small,medium,large"),
    "wms-reprojection": ("WMS_REPROJECTION_DURATION", "120s", "WMS_REPROJECTION_WARMUP", "60s", "WMS_REPROJECTION_VUS", "10", "WMS_REPROJECTION_SCENARIOS", "small,medium,large"),
    "wms-getfeatureinfo": ("WMS_GETFEATUREINFO_DURATION", "120s", "WMS_GETFEATUREINFO_WARMUP", "60s", "WMS_GETFEATUREINFO_VUS", "10", "WMS_GETFEATUREINFO_SCENARIOS", "small,medium,large"),
    "wms-filtered": ("WMS_FILTERED_DURATION", "120s", "WMS_FILTERED_WARMUP", "60s", "WMS_FILTERED_VUS", "10", "WMS_FILTERED_SCENARIOS", "equality,range,like"),
    "wmts": ("WMTS_DURATION", "120s", "WMTS_WARMUP", "60s", "WMTS_VUS", "10", "WMTS_SCENARIOS", "z0,z1,z2"),
    "wcs": ("WCS_DURATION", "120s", "WCS_WARMUP", "60s", "WCS_VUS", "10", "WCS_SCENARIOS", "small,medium,large"),
    "geoservices-query": ("GEOSERVICES_QUERY_DURATION", "120s", "GEOSERVICES_QUERY_WARMUP", "60s", "GEOSERVICES_QUERY_VUS", "10", "GEOSERVICES_QUERY_SCENARIOS", "small,medium,large"),
    "geoservices-query-diagnostics": ("GEOSERVICES_DIAG_DURATION", "20s", "GEOSERVICES_DIAG_WARMUP", "15s", None, None, "GEOSERVICES_DIAG_VARIANTS", "medium-full-1vu,medium-full-10vu,medium-attrs-10vu,medium-geom-oid-10vu,large-full-1vu,large-full-10vu,large-attrs-10vu,large-geom-oid-10vu"),
    "geoservices-export": ("GEOSERVICES_EXPORT_DURATION", "120s", "GEOSERVICES_EXPORT_WARMUP", "60s", "GEOSERVICES_EXPORT_VUS", "10", "GEOSERVICES_EXPORT_SCENARIOS", "small,medium,large"),
    "geoservices-identify": ("GEOSERVICES_IDENTIFY_DURATION", "120s", "GEOSERVICES_IDENTIFY_WARMUP", "60s", "GEOSERVICES_IDENTIFY_VUS", "10", "GEOSERVICES_IDENTIFY_SCENARIOS", "small,medium,large"),
}

tests = os.environ.get("GEOBENCH_TESTS", "").split()
test_metadata = {}
for test in tests:
    entry = {
        "cache_tier": wmts_cache_tier if test == "wmts" else default_cache_tier,
    }
    profile = TEST_PROFILES.get(test)
    if profile:
        duration_env, duration_default, warmup_env, warmup_default, vus_env, vus_default, scenarios_env, scenarios_default = profile
        entry["scenario_duration_seconds"] = duration_seconds(duration_env, duration_default)
        entry["warmup_duration_seconds"] = duration_seconds(warmup_env, warmup_default)
        if vus_env:
            entry["vus"] = int(os.environ.get(vus_env, vus_default))
        if scenarios_env:
            entry["selected_scenarios"] = csv_values(scenarios_env, scenarios_default)
    if test == "wmts":
        entry["wmts_cache_policy"] = wmts_cache_policy
    if test == "concurrent":
        selected_workloads = csv_values("GEOBENCH_CONCURRENT_WORKLOADS", "bbox,equality,range,like")
        selected_levels = csv_values("GEOBENCH_CONCURRENT_LEVELS", "1,10,50,100")
        if selected_workloads == default_concurrent_workloads:
            workload_mix = default_concurrent_mix
            workload_profile = "canonical_mixed"
        else:
            share = round(1 / len(selected_workloads), 6) if selected_workloads else 0
            workload_mix = {workload: share for workload in selected_workloads}
            workload_profile = "focused"
        entry["concurrent_levels"] = selected_levels
        entry["concurrent_workloads"] = selected_workloads
        entry["concurrent_workload_profile"] = workload_profile
        entry["concurrent_mix"] = workload_mix
    test_metadata[test] = entry

metadata = {
    "servers": os.environ.get("GEOBENCH_SERVERS", "").split(),
    "runs": int(os.environ.get("GEOBENCH_RUNS", "0")),
    "audit_shapes": int(os.environ.get("GEOBENCH_AUDIT_SHAPES", "0")),
    "default_cache_tier": default_cache_tier,
    "wmts_cache_policy": wmts_cache_policy,
    "bbox_tolerance_deg": float(os.environ.get("GEOBENCH_BBOX_TOLERANCE_DEG", "0.0001")),
    "measurement_policy": {
        "response_body_policy": "k6 discards default bodies; measured feature requests set responseType=text so checks can validate payload semantics",
        "spatial_bbox_semantics": "viewport_windowing",
        "spatial_response_caching_default": False,
        "concurrent_mix": default_concurrent_mix,
    },
    "server_images": {
        "honua": os.environ.get("GEOBENCH_HONUA_IMAGE", "honuaio/honua-server:latest"),
        "geoserver": os.environ.get("GEOBENCH_GEOSERVER_IMAGE", "docker.osgeo.org/geoserver:2.28.0"),
        "qgis": os.environ.get("GEOBENCH_QGIS_IMAGE", "qgis/qgis-server:3.38"),
        "postgis": os.environ.get("GEOBENCH_POSTGIS_IMAGE", "postgis/postgis:17-3.5"),
        "k6": os.environ.get("GEOBENCH_K6_IMAGE", "grafana/k6:0.54.0"),
    },
    "server_tuning": {
        "honua": {
            "max_concurrent_queries": int(os.environ.get("GEOBENCH_HONUA_MAX_CONCURRENT_QUERIES", "6")),
            "max_connection_pool_size": int(os.environ.get("GEOBENCH_HONUA_MAX_CONNECTION_POOL_SIZE", "6")),
            "min_connection_pool_size": int(os.environ.get("GEOBENCH_HONUA_MIN_CONNECTION_POOL_SIZE", "3")),
            "adaptive_admission_enabled": env_bool("GEOBENCH_HONUA_ADAPTIVE_ADMISSION_ENABLED"),
            "adaptive_admission_min_target": int(os.environ.get("GEOBENCH_HONUA_ADAPTIVE_ADMISSION_MIN_TARGET", "3")),
            "adaptive_admission_max_target": int(os.environ.get("GEOBENCH_HONUA_ADAPTIVE_ADMISSION_MAX_TARGET", "6")),
            "adaptive_admission_initial_target": int(os.environ.get("GEOBENCH_HONUA_ADAPTIVE_ADMISSION_INITIAL_TARGET", "6")),
            "adaptive_admission_target_duration_ms": int(os.environ.get("GEOBENCH_HONUA_ADAPTIVE_ADMISSION_TARGET_DURATION_MS", "100")),
            "adaptive_admission_update_interval_ms": int(os.environ.get("GEOBENCH_HONUA_ADAPTIVE_ADMISSION_UPDATE_INTERVAL_MS", "1000")),
            "response_caching_enabled": False,
        },
        "geoserver": {
            "max_connections": int(os.environ.get("GEOBENCH_GEOSERVER_MAX_CONNECTIONS", "6")),
            "min_connections": int(os.environ.get("GEOBENCH_GEOSERVER_MIN_CONNECTIONS", "3")),
        },
    },
    "tests": test_metadata,
}

with open(output_path, "w") as f:
    json.dump(metadata, f, indent=2)
PY2
}

copy_system_cards() {
  local cards_dir="${RESULTS_DIR}/system-cards"
  mkdir -p "${cards_dir}"

  local server
  local card
  for server in "${SERVERS[@]}"; do
    case "${server}" in
      honua) card="${PROJECT_DIR}/system-cards/honua.json" ;;
      geoserver) card="${PROJECT_DIR}/system-cards/geoserver.json" ;;
      qgis) card="${PROJECT_DIR}/system-cards/qgis-server.json" ;;
      *) card="" ;;
    esac

    if [ -n "${card}" ] && [ -f "${card}" ]; then
      cp "${card}" "${cards_dir}/"
    else
      echo "WARNING: no system card found for ${server}" >&2
    fi
  done
}

# ─── Main loop: one server at a time, fully isolated ─────────────────

validate_cache_policy

TOTAL_TESTS=0
for server in "${SERVERS[@]}"; do
  for test in "${TESTS[@]}"; do
    if supports_test_for_server "${server}" "${test}"; then
      TOTAL_TESTS=$((TOTAL_TESTS + RUNS))
    fi
  done
done

if [ "${TOTAL_TESTS}" -eq 0 ]; then
  echo "ERROR: no supported server/test combinations selected" >&2
  exit 1
fi

write_run_metadata
copy_system_cards

CURRENT=0

for server in "${SERVERS[@]}"; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  SERVER: ${server}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # 1. Start this server's isolated stack
  echo "[1/4] Starting isolated stack (PostGIS + ${server} + k6)..."
  docker compose --profile "${server}" up -d 2>&1 | tail -5 | sed 's/^/  /'
  STACK_ACTIVE=1
  wait_for_server "${server}"
  cleanup_k6_runs

  # 2. Run adapter
  echo "[2/4] Setting up ${server}..."
  run_adapter "${server}"

  # 2b. Capture lightweight response shapes before timed load
  run_response_shape_audit "${server}"
  start_diagnostics_monitor "${server}"

  # 3. Run benchmarks
  echo "[3/4] Running benchmarks..."
  for test in "${TESTS[@]}"; do
    if ! supports_test_for_server "${server}" "${test}"; then
      echo "  Skipping unsupported combination: ${server}/${test}"
      continue
    fi

    for run in $(seq 1 "${RUNS}"); do
      CURRENT=$((CURRENT + 1))
      LABEL="${server}/${test}/run-${run}"
      RESULT_FILE="${server}-${test}-run${run}.json"
      RESULT_PATH="/results/${TIMESTAMP}/${RESULT_FILE}"
      HOST_RESULT_PATH="${RESULTS_DIR}/${RESULT_FILE}"
      echo ""
      echo "  [${CURRENT}/${TOTAL_TESTS}] ${LABEL}"

      if [ "${RESUME_EXISTING}" = "1" ] && result_file_successful "${HOST_RESULT_PATH}"; then
        echo "    Existing successful result found, skipping"
        continue
      fi

      cleanup_k6_runs
      mapfile -t K6_ENV_FLAGS < <(build_k6_env_flags)
      set +e
      docker compose --profile "${server}" exec -T k6 \
        k6 run \
          --summary-trend-stats "avg,min,med,max,p(90),p(95),p(99)" \
          --summary-export "${RESULT_PATH}" \
          --env "SERVER=${server}" \
          "${K6_ENV_FLAGS[@]}" \
          --tag "server=${server}" \
          --tag "test=${test}" \
          --tag "run=${run}" \
          --quiet \
          "/tests/${test}.js" 2>&1 | grep -E 'checks|errors\b|http_reqs\b|http_req_duration\b|level=error msg=.*test' | sed 's/^/    /'
      k6_status=${PIPESTATUS[0]}
      set -e

      if [ "${k6_status}" -ne 0 ]; then
        echo "    ERROR: k6 exited with status ${k6_status}"
        if [ "${CONTINUE_ON_K6_FAILURE:-0}" = "1" ]; then
          echo "    Continuing because CONTINUE_ON_K6_FAILURE=1; result JSON is retained for diagnostics"
        else
          exit "${k6_status}"
        fi
      fi
    done
  done

  # 4. Tear down completely — release all resources
  echo ""
  echo "[4/4] Tearing down ${server} stack..."
  stop_diagnostics_monitor
  write_diagnostics_artifacts "${server}"
  teardown_stack "${server}"
  echo ""
done

# ─── Generate report ─────────────────────────────────────────────────

echo "Generating report..."
python3 "${SCRIPT_DIR}/generate-report.py" \
  --results-dir "${RESULTS_DIR}" \
  --output "${RESULTS_DIR}/report.md" \
  --runs "${RUNS}" 2>&1

if [ -x "${SCRIPT_DIR}/audit-fairness.py" ]; then
  echo "Auditing fairness..."
  FAIRNESS_SERVERS="$(IFS=,; echo "${SERVERS[*]}")"
  FAIRNESS_ARGS=(
    --results-dir "${RESULTS_DIR}"
    --servers "${FAIRNESS_SERVERS}"
  )
  if [ "${STRICT_EQUAL_DB_BUDGET:-0}" = "1" ]; then
    FAIRNESS_ARGS+=(--strict-equal-db-budget)
  fi
  if [ "${STRICT_PAYLOAD_COMPARABLE:-0}" = "1" ]; then
    FAIRNESS_ARGS+=(--strict-payload-comparable)
  fi
  python3 "${SCRIPT_DIR}/audit-fairness.py" "${FAIRNESS_ARGS[@]}" 2>&1 || {
    status="$?"
    if [ "${STRICT_FAIRNESS:-0}" = "1" ]; then
      exit "${status}"
    fi
  }
fi

if [ "${DIAGNOSTICS}" = "1" ]; then
  python3 "${SCRIPT_DIR}/generate-diagnostics-summary.py" \
    --results-dir "${RESULTS_DIR}" 2>&1
fi

echo ""
echo "============================================"
echo "  Benchmark complete!"
echo "============================================"
echo ""
if [ -f "${RESULTS_DIR}/report.md" ]; then
  cat "${RESULTS_DIR}/report.md"
fi
echo ""
echo "Full results: ${RESULTS_DIR}/"
