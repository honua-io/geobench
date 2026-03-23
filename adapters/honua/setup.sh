#!/usr/bin/env bash
# GeoBench: Honua Server adapter — creates a PostGIS connection and publishes the bench_points layer.
set -euo pipefail

HONUA_URL="${HONUA_URL:-http://honua:8080}"
API_KEY="${HONUA_API_KEY:-geobench-admin-key}"
HEADER_KEY="X-Api-Key: ${API_KEY}"

echo "=== Honua Server Adapter ==="
echo "Server: ${HONUA_URL}"

# Step 1: Create database connection
echo "[1/4] Creating PostGIS connection..."
CONNECTION_ID=$(curl -sf -X POST "${HONUA_URL}/api/v1/admin/connections/" \
  -H "Content-Type: application/json" \
  -H "${HEADER_KEY}" \
  -d '{
    "name": "geobench-postgis",
    "description": "GeoBench shared PostGIS database",
    "host": "postgis",
    "port": 5432,
    "databaseName": "geobench",
    "username": "geobench",
    "password": "geobench_pass",
    "sslRequired": false,
    "sslMode": "Disable"
  }' | jq -r '.data.connectionId // .connectionId // empty')

if [ -z "${CONNECTION_ID}" ]; then
  echo "ERROR: Failed to create connection. Attempting to list existing..."
  CONNECTION_ID=$(curl -sf "${HONUA_URL}/api/v1/admin/connections/" \
    -H "${HEADER_KEY}" | jq -r '(.data // .)[0].connectionId // empty')
fi

echo "  Connection ID: ${CONNECTION_ID}"

# Step 2: Discover tables
echo "[2/4] Discovering tables..."
curl -sf "${HONUA_URL}/api/v1/admin/connections/${CONNECTION_ID}/tables" \
  -H "${HEADER_KEY}" | jq -r '(.data // .)[] | .table // .tableName' 2>/dev/null || echo "  (table listing format varies)"

# Step 3: Publish bench_points layer
echo "[3/4] Publishing bench_points layer..."
LAYER_RESPONSE=$(curl -sf -X POST "${HONUA_URL}/api/v1/admin/connections/${CONNECTION_ID}/layers/" \
  -H "Content-Type: application/json" \
  -H "${HEADER_KEY}" \
  -d '{
    "schema": "public",
    "table": "bench_points",
    "layerName": "bench_points",
    "description": "GeoBench 100K point dataset",
    "geometryColumn": "geom",
    "geometryType": "Point",
    "srid": 4326,
    "enabled": true
  }' 2>&1) || true

echo "  Layer response: $(echo "${LAYER_RESPONSE}" | jq -c '.' 2>/dev/null || echo "${LAYER_RESPONSE}")"

# Step 4: Verify OGC API Features endpoint
echo "[4/4] Verifying OGC API Features endpoint..."
VERIFY=$(curl -sf "${HONUA_URL}/ogc/features/collections/bench_points/items?limit=1&f=json" \
  | jq -r '.numberReturned // .features | length' 2>/dev/null || echo "FAILED")

if [ "${VERIFY}" = "FAILED" ]; then
  echo "  WARNING: OGC endpoint verification failed. The collection may use a different name."
  echo "  Checking available collections..."
  curl -sf "${HONUA_URL}/ogc/features/collections?f=json" | jq -r '.collections[].id' 2>/dev/null || true
else
  echo "  OK: bench_points collection is live (returned ${VERIFY} feature(s))"
fi

echo "=== Honua adapter complete ==="
