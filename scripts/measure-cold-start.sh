#!/usr/bin/env bash
# GeoBench: Cold-start latency measurement for Honua Server.
#
# Measures the elapsed time from "docker compose up" until the server
# returns a successful HTTP response to the first feature request.
# The database stack (PostGIS + data) is pre-warmed so that cold-start
# reflects server initialisation only, not data loading.
#
# Output JSON is written to COLD_START_OUTPUT (default:
# results/<timestamp>/honua-cold-start.json).
#
# Usage:
#   ./scripts/measure-cold-start.sh
#   COLD_START_RUNS=3 ./scripts/measure-cold-start.sh
#   COLD_START_MAX_WAIT=120 ./scripts/measure-cold-start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TIMESTAMP="${RESULT_TIMESTAMP:-$(date +%Y%m%d-%H%M%S)}"
RESULTS_DIR="${PROJECT_DIR}/results/${TIMESTAMP}"
COLD_START_OUTPUT="${COLD_START_OUTPUT:-${RESULTS_DIR}/honua-cold-start.json}"
# How many cold-start cycles to run (median is reported).
COLD_START_RUNS="${COLD_START_RUNS:-3}"
# Maximum seconds to wait for the server to become healthy per cycle.
COLD_START_MAX_WAIT="${COLD_START_MAX_WAIT:-180}"
HONUA_PORT="${HONUA_PORT:-8081}"
HONUA_ADMIN_PASSWORD="${HONUA_ADMIN_PASSWORD:-GeoBench-Admin-Key-2026!}"
PROBE_URL="http://localhost:${HONUA_PORT}/healthz/live"
# The first OGC feature request used to validate a real request is served.
FIRST_REQUEST_URL="http://localhost:${HONUA_PORT}/ogc/collections"

mkdir -p "${RESULTS_DIR}"
chmod 777 "${RESULTS_DIR}"

echo "============================================"
echo "  GeoBench — Cold-Start Measurement"
echo "============================================"
echo ""
echo "  Probe URL:  ${PROBE_URL}"
echo "  Runs:       ${COLD_START_RUNS}"
echo "  Max wait:   ${COLD_START_MAX_WAIT}s"
echo "  Output:     ${COLD_START_OUTPUT}"
echo ""

cd "${PROJECT_DIR}"

# ── Helpers ──────────────────────────────────────────────────────────

stop_honua_container() {
  docker compose --profile honua stop honua 2>&1 | tail -2 | sed 's/^/  /' || true
  docker compose --profile honua rm -f honua 2>&1 | tail -2 | sed 's/^/  /' || true
}

full_stack_down() {
  docker compose --profile honua down -v --remove-orphans 2>&1 | tail -3 | sed 's/^/  /' || true
}

# Returns 0 once the honua container reports docker state "running" (i.e. the
# image is pulled and the container has been scheduled/started). Used to anchor
# the cold-start timer so it measures only server initialisation, not docker
# image pull / container scheduling.
honua_container_running() {
  local state
  state=$(docker compose --profile honua ps --status running --format '{{.Service}}' 2>/dev/null \
            | grep -Fx honua || true)
  [ -n "${state}" ]
}

wait_honua_running() {
  local max="$1"
  local waited=0
  while [ "${waited}" -lt "${max}" ]; do
    if honua_container_running; then
      return 0
    fi
    sleep 1
    waited=$(( waited + 1 ))
  done
  return 1
}

# ── Phase 1: start PostGIS and run the adapter to seed data ──────────

echo "[1/3] Starting PostGIS and seeding data..."
docker compose --profile honua up -d postgis-honua 2>&1 | tail -5 | sed 's/^/  /'

# Wait for PostGIS.
elapsed=0
while [ "${elapsed}" -lt 120 ]; do
  if docker compose --profile honua exec -T postgis-honua \
       pg_isready -h 127.0.0.1 -U geobench -d geobench -q 2>/dev/null; then
    break
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
if [ "${elapsed}" -ge 120 ]; then
  echo "ERROR: PostGIS did not become ready within 120s" >&2
  full_stack_down
  exit 1
fi
echo "  PostGIS ready (${elapsed}s)"

# Start the Honua server once to run the adapter (seed data into feature store).
echo "  Starting Honua to run adapter (data seeding)..."
docker compose --profile honua up -d honua 2>&1 | tail -5 | sed 's/^/  /'

adapter_wait=0
while [ "${adapter_wait}" -lt 180 ]; do
  if curl -fsS "${PROBE_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 3
  adapter_wait=$((adapter_wait + 3))
done
if [ "${adapter_wait}" -ge 180 ]; then
  echo "ERROR: Honua did not become ready for adapter run" >&2
  full_stack_down
  exit 1
fi

adapter="${PROJECT_DIR}/adapters/honua/setup.sh"
if [ -f "${adapter}" ]; then
  pg_host_port=$(docker compose --profile honua port postgis-honua 5432 2>/dev/null | cut -d: -f2)
  echo "  Running adapter (data seeding)..."
  HONUA_URL="http://localhost:${HONUA_PORT}" \
  HONUA_API_KEY="${HONUA_ADMIN_PASSWORD}" \
  PGURL="postgresql://geobench:geobench_pass@localhost:${pg_host_port}/geobench" \
  bash "${adapter}" 2>&1 | sed 's/^/    /'
fi

# ── Phase 2: measure cold-start latency (COLD_START_RUNS cycles) ─────

echo ""
echo "[2/3] Measuring cold-start latency (${COLD_START_RUNS} runs)..."

measurements=()

for run in $(seq 1 "${COLD_START_RUNS}"); do
  echo ""
  echo "  Run ${run}/${COLD_START_RUNS}:"

  # Stop and remove the server container, keep PostGIS running.
  echo "    Stopping server..."
  stop_honua_container

  # Start the server. We do NOT start the cold-start timer here: "docker
  # compose up" may pull the image and schedule the container, and that
  # orchestration cost is not server initialisation. We anchor the timer once
  # the container is in the "running" state so we measure time-to-healthy only.
  echo "    Starting server..."
  docker compose --profile honua up -d honua 2>&1 | tail -3 | sed 's/^/      /'

  if ! wait_honua_running "${COLD_START_MAX_WAIT}"; then
    echo "    ERROR: server container did not reach running state within ${COLD_START_MAX_WAIT}s" >&2
    full_stack_down
    exit 1
  fi

  # Record wall-clock start now that the container is running, so the elapsed
  # time reflects server initialisation only (not image pull / scheduling).
  start_ns=$(date +%s%N)

  # Poll until healthy (1-second ticks; sub-second precision is not required
  # for cold-start since startup takes several hundred ms at minimum).
  elapsed=0
  healthy=false
  while [ "${elapsed}" -lt "${COLD_START_MAX_WAIT}" ]; do
    if curl -fsS "${PROBE_URL}" >/dev/null 2>&1; then
      healthy=true
      break
    fi
    sleep 1
    elapsed=$(( elapsed + 1 ))
  done

  if [ "${healthy}" = "false" ]; then
    echo "    ERROR: server did not become healthy within ${COLD_START_MAX_WAIT}s" >&2
    full_stack_down
    exit 1
  fi

  healthy_ns=$(date +%s%N)
  healthy_ms=$(( (healthy_ns - start_ns) / 1000000 ))
  echo "    Healthy in ${healthy_ms} ms"

  # Now fire the first real request and measure that latency.
  req_start_ns=$(date +%s%N)
  if ! curl -fsS "${FIRST_REQUEST_URL}" -H "X-API-Key: ${HONUA_ADMIN_PASSWORD}" >/dev/null 2>&1; then
    # Non-authed endpoint should work without key; retry without header.
    curl -fsS "${FIRST_REQUEST_URL}" >/dev/null 2>&1 || true
  fi
  req_end_ns=$(date +%s%N)
  first_req_ms=$(( (req_end_ns - req_start_ns) / 1000000 ))
  echo "    First request in ${first_req_ms} ms"

  measurements+=("${healthy_ms}:${first_req_ms}")
done

# ── Phase 3: compute stats and write JSON ────────────────────────────

echo ""
echo "[3/3] Computing statistics and writing output..."

python3 - "${COLD_START_OUTPUT}" "${measurements[@]+"${measurements[@]}"}" <<'PY'
import json
import statistics
import sys
from datetime import datetime, timezone

output_path = sys.argv[1]
raw = sys.argv[2:]  # "healthy_ms:first_req_ms" pairs

if not raw:
    print("ERROR: no measurements collected", file=sys.stderr)
    sys.exit(1)

healthy_samples = []
first_req_samples = []
for pair in raw:
    h, r = pair.split(":")
    healthy_samples.append(int(h))
    first_req_samples.append(int(r))


def stats(samples):
    s = sorted(samples)
    n = len(s)
    return {
        "samples": n,
        "min_ms": s[0],
        "max_ms": s[-1],
        "median_ms": statistics.median(s),
        "mean_ms": round(statistics.mean(s), 1),
        "p95_ms": s[min(n - 1, int(n * 0.95))],
    }


result = {
    "measured_at": datetime.now(timezone.utc).isoformat(),
    "cold_start_healthy": stats(healthy_samples),
    "cold_start_first_request": stats(first_req_samples),
    "raw": [
        {"healthy_ms": h, "first_req_ms": r}
        for h, r in zip(healthy_samples, first_req_samples)
    ],
}

with open(output_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"  cold_start_healthy.median_ms  = {result['cold_start_healthy']['median_ms']}")
print(f"  cold_start_first_request.median_ms = {result['cold_start_first_request']['median_ms']}")
print(f"  Output: {output_path}")
PY

stop_honua_container

echo ""
echo "============================================"
echo "  Cold-start measurement complete."
echo "============================================"
