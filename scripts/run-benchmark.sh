#!/usr/bin/env bash
# GeoBench: Main benchmark orchestrator.
#
# Usage: ./scripts/run-benchmark.sh
#   RUNS=3 ./scripts/run-benchmark.sh          # override number of runs
#   SERVERS="honua geoserver" ./scripts/run-benchmark.sh  # subset of servers
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULTS_DIR="${PROJECT_DIR}/results/${TIMESTAMP}"
SERVERS=(${SERVERS:-honua geoserver qgis})
TESTS=("attribute-filter" "spatial-bbox" "concurrent")
RUNS="${RUNS:-5}"

mkdir -p "${RESULTS_DIR}"

echo "============================================"
echo "  GeoBench — Geospatial Feature Server Benchmarks"
echo "============================================"
echo ""
echo "  Results:  ${RESULTS_DIR}"
echo "  Servers:  ${SERVERS[*]}"
echo "  Tests:    ${TESTS[*]}"
echo "  Runs:     ${RUNS}"
echo ""

# ------------------------------------------------------------------
# Step 1: Ensure Docker Compose stack is running
# ------------------------------------------------------------------
echo "[1/5] Starting Docker Compose stack..."
cd "${PROJECT_DIR}"

if ! docker compose ps --status running | grep -q postgis; then
  docker compose up -d
  echo "  Waiting for services to become healthy..."
  "${SCRIPT_DIR}/wait-for-healthy.sh"
else
  echo "  Stack already running."
fi

# ------------------------------------------------------------------
# Step 2: Run server adapters
# ------------------------------------------------------------------
echo ""
echo "[2/5] Running server adapters..."
for server in "${SERVERS[@]}"; do
  adapter="${PROJECT_DIR}/adapters/${server}/setup.sh"
  if [ -f "${adapter}" ]; then
    echo "  --- ${server} ---"
    bash "${adapter}" 2>&1 | sed 's/^/  /' | tee "${RESULTS_DIR}/${server}-setup.log"
    echo ""
  fi
done

# ------------------------------------------------------------------
# Step 3: Copy system cards
# ------------------------------------------------------------------
echo "[3/5] Collecting system cards..."
for server in "${SERVERS[@]}"; do
  card="${PROJECT_DIR}/system-cards/${server}.json"
  if [ -f "${card}" ]; then
    cp "${card}" "${RESULTS_DIR}/"
    echo "  Copied ${server}.json"
  fi
done

# ------------------------------------------------------------------
# Step 4: Execute benchmarks
# ------------------------------------------------------------------
echo ""
echo "[4/5] Running benchmarks (${#SERVERS[@]} servers x ${#TESTS[@]} tests x ${RUNS} runs)..."
echo ""

TOTAL=$(( ${#SERVERS[@]} * ${#TESTS[@]} * RUNS ))
CURRENT=0

for server in "${SERVERS[@]}"; do
  for test in "${TESTS[@]}"; do
    for run in $(seq 1 "${RUNS}"); do
      CURRENT=$((CURRENT + 1))
      LABEL="${server}/${test}/run-${run}"
      RESULT_FILE="${server}-${test}-run${run}.json"
      LOG_FILE="${server}-${test}-run${run}.log"

      echo "  [${CURRENT}/${TOTAL}] ${LABEL}"

      docker compose exec -T k6 k6 run \
        --out "json=/results/${RESULT_FILE}" \
        --env "SERVER=${server}" \
        --tag "server=${server}" \
        --tag "test=${test}" \
        --tag "run=${run}" \
        --quiet \
        "/tests/${test}.js" \
        2>&1 | tee "${RESULTS_DIR}/${LOG_FILE}" | tail -5 | sed 's/^/    /'

      echo ""
    done
  done
done

# ------------------------------------------------------------------
# Step 5: Generate report
# ------------------------------------------------------------------
echo "[5/5] Generating report..."
python3 "${SCRIPT_DIR}/generate-report.py" \
  --results-dir "${RESULTS_DIR}" \
  --output "${RESULTS_DIR}/report.md" \
  --runs "${RUNS}"

echo ""
echo "============================================"
echo "  Benchmark complete!"
echo "============================================"
echo ""
cat "${RESULTS_DIR}/report.md"
echo ""
echo "Full results: ${RESULTS_DIR}/"
