#!/usr/bin/env bash
# GeoBench: Quick smoke test — 1 VU, 5 seconds per server.
# Validates the entire pipeline without running a full benchmark.
set -euo pipefail

SERVERS=(${SERVERS:-honua geoserver qgis})
FAILED=0

echo "=== GeoBench Smoke Test ==="
echo ""

for server in "${SERVERS[@]}"; do
  echo "--- ${server} ---"
  if docker compose exec -T k6 k6 run \
    --vus 1 --duration 5s \
    --env "SERVER=${server}" \
    --quiet \
    /tests/attribute-filter.js 2>&1 | tail -3; then
    echo "  PASS"
  else
    echo "  FAIL"
    FAILED=$((FAILED + 1))
  fi
  echo ""
done

if [ "${FAILED}" -gt 0 ]; then
  echo "ERROR: ${FAILED} server(s) failed smoke test."
  exit 1
fi

echo "All smoke tests passed."
