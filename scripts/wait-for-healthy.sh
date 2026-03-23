#!/usr/bin/env bash
# GeoBench: Wait for all services to become healthy.
set -euo pipefail

TIMEOUT="${TIMEOUT:-300}"
INTERVAL=5
ELAPSED=0

echo "Waiting for services (timeout: ${TIMEOUT}s)..."

while [ "${ELAPSED}" -lt "${TIMEOUT}" ]; do
  ALL_HEALTHY=true

  # Check PostGIS
  if ! docker compose exec -T postgis pg_isready -U geobench -d geobench -q 2>/dev/null; then
    ALL_HEALTHY=false
    echo "  [${ELAPSED}s] PostGIS: not ready"
  fi

  # Check Honua (if running)
  if docker compose ps --status running 2>/dev/null | grep -q honua; then
    if ! curl -sf http://localhost:${HONUA_PORT:-8081}/healthz/live >/dev/null 2>&1; then
      ALL_HEALTHY=false
      echo "  [${ELAPSED}s] Honua: not ready"
    fi
  fi

  # Check GeoServer (if running)
  if docker compose ps --status running 2>/dev/null | grep -q geoserver; then
    if ! curl -sf http://localhost:${GEOSERVER_PORT:-8082}/geoserver/web/ >/dev/null 2>&1; then
      ALL_HEALTHY=false
      echo "  [${ELAPSED}s] GeoServer: not ready"
    fi
  fi

  # Check QGIS Server (if running)
  if docker compose ps --status running 2>/dev/null | grep -q qgis; then
    if ! curl -sf "http://localhost:${QGIS_PORT:-8083}/?SERVICE=WFS&REQUEST=GetCapabilities" >/dev/null 2>&1; then
      ALL_HEALTHY=false
      echo "  [${ELAPSED}s] QGIS Server: not ready"
    fi
  fi

  if [ "${ALL_HEALTHY}" = true ]; then
    echo "All services healthy (${ELAPSED}s)."
    exit 0
  fi

  sleep "${INTERVAL}"
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo "ERROR: Timed out waiting for services after ${TIMEOUT}s."
exit 1
