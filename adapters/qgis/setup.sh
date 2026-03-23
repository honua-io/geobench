#!/usr/bin/env bash
# GeoBench: QGIS Server adapter — verifies the pre-configured project file is serving data.
set -euo pipefail

QGIS_URL="${QGIS_URL:-http://qgis-server:80}"

echo "=== QGIS Server Adapter ==="
echo "Server: ${QGIS_URL}"

# The QGIS project file (geobench.qgs) is mounted at startup.
# This script only verifies the endpoint is working.

echo "[1/2] Checking collections..."
COLLECTIONS=$(curl -sf "${QGIS_URL}/ogc/features/collections" \
  | jq -r '.collections[].id' 2>/dev/null || echo "FAILED")

if [ "${COLLECTIONS}" = "FAILED" ]; then
  echo "  WARNING: Failed to list collections. QGIS Server may not support OGC API Features."
  echo "  Falling back to WFS check..."
  curl -sf "${QGIS_URL}/?SERVICE=WFS&REQUEST=GetCapabilities" | head -5 || true
else
  echo "  Collections: ${COLLECTIONS}"
fi

echo "[2/2] Verifying bench_points items endpoint..."
VERIFY=$(curl -sf "${QGIS_URL}/ogc/features/collections/bench_points/items?limit=1" \
  | jq -r '.numberReturned // (.features | length)' 2>/dev/null || echo "FAILED")

if [ "${VERIFY}" = "FAILED" ]; then
  echo "  WARNING: Items endpoint failed. Check QGIS project file configuration."
else
  echo "  OK: bench_points collection is live (returned ${VERIFY} feature(s))"
fi

echo "=== QGIS adapter complete ==="
