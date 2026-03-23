#!/usr/bin/env bash
# GeoBench: Honua Server adapter — creates connection, publishes layer, populates features, enables anonymous access.
set -euo pipefail

HONUA_URL="${HONUA_URL:-http://honua:8080}"
API_KEY="${HONUA_API_KEY:-geobench-admin-key}"
HEADER_KEY="X-Api-Key: ${API_KEY}"
PGURL="${PGURL:-postgresql://geobench:geobench_pass@postgis-honua:5432/geobench}"

echo "=== Honua Server Adapter ==="
echo "Server: ${HONUA_URL}"

# Step 1: Create database connection
echo "[1/6] Creating PostGIS connection..."
CONNECTION_ID=$(curl -sf -X POST "${HONUA_URL}/api/v1/admin/connections/" \
  -H "Content-Type: application/json" \
  -H "${HEADER_KEY}" \
  -d '{
    "name": "geobench-postgis",
    "description": "GeoBench shared PostGIS database",
    "host": "postgis-honua",
    "port": 5432,
    "databaseName": "geobench",
    "username": "geobench",
    "password": "geobench_pass",
    "sslRequired": false,
    "sslMode": "Disable"
  }' | jq -r '.data.connectionId // .connectionId // empty')

if [ -z "${CONNECTION_ID}" ]; then
  echo "  Connection may already exist. Listing..."
  CONNECTION_ID=$(curl -sf "${HONUA_URL}/api/v1/admin/connections/" \
    -H "${HEADER_KEY}" | jq -r '(.data // .)[0].connectionId // empty')
fi

echo "  Connection ID: ${CONNECTION_ID}"

# Step 2: Discover tables
echo "[2/6] Discovering tables..."
curl -sf "${HONUA_URL}/api/v1/admin/connections/${CONNECTION_ID}/tables" \
  -H "${HEADER_KEY}" | jq -r '(.data // .)[] | .table // .tableName' 2>/dev/null || echo "  (table listing format varies)"

# Step 3: Publish bench_points layer
echo "[3/6] Publishing bench_points layer..."
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

LAYER_ID=$(echo "${LAYER_RESPONSE}" | jq -r '.data.layerId // empty' 2>/dev/null || true)
echo "  Layer ID: ${LAYER_ID:-unknown}"

# Step 4: Populate features table
# Honua stores feature data in a centralized 'features' table with JSONB attributes.
# Layer publishing only creates metadata — we need to import the source data.
echo "[4/6] Populating features table from bench_points..."
LAYER_ID_NUM="${LAYER_ID:-1}"

# Use psql if available, otherwise use the Honua admin connection
if command -v psql &>/dev/null; then
  IMPORT_COUNT=$(psql "${PGURL}" -t -A -c "
    INSERT INTO public.features (layer_id, geometry, attributes)
    SELECT
      ${LAYER_ID_NUM},
      geom,
      jsonb_build_object(
        'id', id,
        'feature_name', feature_name,
        'category', category,
        'status', status,
        'priority', priority,
        'temperature', temperature,
        'population', population,
        'created_at', created_at,
        'updated_at', updated_at,
        'country_code', country_code,
        'description', description
      )
    FROM public.bench_points
    ON CONFLICT DO NOTHING
    RETURNING 1;
  " 2>&1 | wc -l)
  echo "  Imported ${IMPORT_COUNT} features via psql"
else
  echo "  psql not available — skipping direct import"
  echo "  NOTE: Features must be imported manually or via Honua's import API"
fi

# Step 5: Enable anonymous access
echo "[5/6] Enabling anonymous access..."
curl -sf -X PUT "${HONUA_URL}/api/v1/admin/services/default/access-policy" \
  -H "Content-Type: application/json" \
  -H "${HEADER_KEY}" \
  -d '{"allowAnonymous":true}' | jq -r '.success // "failed"' 2>/dev/null || echo "  failed"

# Step 6: Verify FeatureServer query
echo "[6/6] Verifying FeatureServer query..."
VERIFY=$(curl -sf "${HONUA_URL}/rest/services/default/FeatureServer/${LAYER_ID_NUM}/query?f=json&where=1%3D1&resultRecordCount=1&outFields=feature_name" \
  | jq -r '.features | length' 2>/dev/null || echo "FAILED")

if [ "${VERIFY}" = "FAILED" ] || [ "${VERIFY}" = "0" ]; then
  echo "  WARNING: FeatureServer query returned ${VERIFY} features."
  echo "  Checking OGC collections..."
  curl -sf "${HONUA_URL}/ogc/features/collections?f=json" | jq -r '.collections[].id' 2>/dev/null || true
else
  echo "  OK: FeatureServer returned ${VERIFY} feature(s)"
fi

echo "=== Honua adapter complete ==="
