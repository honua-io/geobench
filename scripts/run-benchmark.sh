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
TESTS=("attribute-filter" "spatial-bbox" "concurrent")
RUNS="${RUNS:-1}"

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
echo ""

cd "${PROJECT_DIR}"

# Map server name to its k6 URL
get_server_url() {
  case "$1" in
    honua)     echo "http://honua:8080" ;;
    geoserver) echo "http://geoserver:8080" ;;
    qgis)      echo "http://qgis-server:80" ;;
  esac
}

get_pgurl() {
  echo "postgresql://geobench:geobench_pass@postgis-$1:5432/geobench"
}

wait_for_server() {
  local server="$1"
  local max_wait=300
  local elapsed=0
  echo "  Waiting for ${server}..."
  while [ $elapsed -lt $max_wait ]; do
    if docker compose --profile "${server}" exec -T k6 sh -c "wget -q --spider $(get_server_url ${server})/healthz/live 2>/dev/null || wget -q --spider $(get_server_url ${server})/ 2>/dev/null" 2>/dev/null; then
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

# ─── Main loop: one server at a time, fully isolated ─────────────────

TOTAL_TESTS=$(( ${#SERVERS[@]} * ${#TESTS[@]} * RUNS ))
CURRENT=0

for server in "${SERVERS[@]}"; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  SERVER: ${server}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # 1. Start this server's isolated stack
  echo "[1/4] Starting isolated stack (PostGIS + ${server} + k6)..."
  docker compose --profile "${server}" up -d 2>&1 | tail -5 | sed 's/^/  /'
  wait_for_server "${server}"

  # 2. Run adapter
  echo "[2/4] Setting up ${server}..."
  run_adapter "${server}"

  # 3. Run benchmarks
  echo "[3/4] Running benchmarks..."
  for test in "${TESTS[@]}"; do
    for run in $(seq 1 "${RUNS}"); do
      CURRENT=$((CURRENT + 1))
      LABEL="${server}/${test}/run-${run}"
      echo ""
      echo "  [${CURRENT}/${TOTAL_TESTS}] ${LABEL}"

      docker compose --profile "${server}" exec -T k6 \
        k6 run \
          --summary-export "/results/${server}-${test}-run${run}.json" \
          --env "SERVER=${server}" \
          --tag "server=${server}" \
          --tag "test=${test}" \
          --tag "run=${run}" \
          --quiet \
          "/tests/${test}.js" 2>&1 | grep -E "checks|http_reqs\b|http_req_duration\b" | sed 's/^/    /'
    done
  done

  # 4. Tear down completely — release all resources
  echo ""
  echo "[4/4] Tearing down ${server} stack..."
  docker compose --profile "${server}" down -v 2>&1 | tail -3 | sed 's/^/  /'
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
