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
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULTS_DIR="${PROJECT_DIR}/results/${TIMESTAMP}"
SERVERS=(${SERVERS:-honua geoserver qgis})
if [ -n "${TESTS:-}" ]; then
  IFS=' ' read -r -a TESTS <<< "${TESTS}"
else
  TESTS=("attribute-filter" "spatial-bbox" "concurrent")
fi
RUNS="${RUNS:-1}"
AUDIT_SHAPES="${AUDIT_SHAPES:-1}"

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
echo ""

cd "${PROJECT_DIR}"

STACK_ACTIVE=0

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
  cleanup_k6_runs
  compose_down_all >/dev/null 2>&1 || true
  STACK_ACTIVE=0
}

teardown_stack() {
  local server="$1"
  cleanup_k6_runs
  docker compose --profile "${server}" down -v --remove-orphans 2>&1 | tail -3 | sed 's/^/  /' || true
  STACK_ACTIVE=0
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
    GEOSERVICES_QUERY_VUS
    GEOSERVICES_QUERY_SCENARIOS
    GEOSERVICES_QUERY_SALT_SMALL
    GEOSERVICES_QUERY_SALT_MEDIUM
    GEOSERVICES_QUERY_SALT_LARGE
    WMS_REPROJECTION_DURATION
    WMS_REPROJECTION_WARMUP
    WMS_REPROJECTION_VUS
    WMS_REPROJECTION_SCENARIOS
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
    wms-getmap|wms-reprojection)
      [[ "${server}" == "honua" || "${server}" == "geoserver" || "${server}" == "qgis" ]]
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
    *)
      echo "Unknown test: ${test}" >&2
      return 1
      ;;
  esac
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
      HONUA_API_KEY="${HONUA_ADMIN_PASSWORD:-geobench-admin-key}" \
      PGURL="postgresql://geobench:geobench_pass@localhost:${pg_host_port}/geobench" \
      bash "${adapter}" 2>&1 | sed 's/^/    /'
      ;;
    geoserver)
      GS_URL="http://localhost:${GEOSERVER_PORT:-8082}" \
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

# ─── Main loop: one server at a time, fully isolated ─────────────────

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
      echo ""
      echo "  [${CURRENT}/${TOTAL_TESTS}] ${LABEL}"

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
          "/tests/${test}.js" 2>&1 | grep -E "checks|errors\b|http_reqs\b|http_req_duration\b" | sed 's/^/    /'
      k6_status=${PIPESTATUS[0]}
      set -e

      if [ "${k6_status}" -ne 0 ] && [ "${k6_status}" -ne 99 ]; then
        echo "    ERROR: k6 exited with status ${k6_status}"
        exit "${k6_status}"
      fi
    done
  done

  # 4. Tear down completely — release all resources
  echo ""
  echo "[4/4] Tearing down ${server} stack..."
  teardown_stack "${server}"
  echo ""
done

# ─── Generate report ─────────────────────────────────────────────────

echo "Generating report..."
python3 "${SCRIPT_DIR}/generate-report.py" \
  --results-dir "${RESULTS_DIR}" \
  --output "${RESULTS_DIR}/report.md" \
  --runs "${RUNS}" 2>&1

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
