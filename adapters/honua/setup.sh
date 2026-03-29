#!/usr/bin/env bash
# GeoBench: Honua Server adapter for honuaio/honua-server:latest.
# Creates a managed PostGIS connection, publishes the benchmark layer,
# imports source rows into Honua's feature store, adds benchmark-aligned indexes,
# and enables anonymous OGC access.
set -euo pipefail

HONUA_URL="${HONUA_URL:-http://honua:8080}"
API_KEY="${HONUA_API_KEY:-geobench-admin-key}"
HEADER_KEY="X-API-Key: ${API_KEY}"
PGURL="${PGURL:-postgresql://geobench:geobench_pass@postgis-honua:5432/geobench}"
CONNECTION_NAME="${HONUA_CONNECTION_NAME:-geobench-postgis}"
SERVICE_NAME="${HONUA_SERVICE_NAME:-default}"
COLLECTION_ID="${HONUA_COLLECTION_ID:-1}"
POINT_STYLE_COLOR="${HONUA_POINT_STYLE_COLOR:-#2D69A5}"
POINT_STYLE_RADIUS="${HONUA_POINT_STYLE_RADIUS:-3}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 1
  fi
}

api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local url="${HONUA_URL}${path}"

  if [ -n "${data}" ]; then
    curl -sS -X "${method}" "${url}" \
      -H "Content-Type: application/json" \
      -H "${HEADER_KEY}" \
      -d "${data}"
  else
    curl -sS -X "${method}" "${url}" \
      -H "${HEADER_KEY}"
  fi
}

wait_for_admin() {
  local attempts=30
  local delay=2

  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS "${HONUA_URL}/api/v1/admin/services" -H "${HEADER_KEY}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${delay}"
  done

  echo "ERROR: Honua admin API did not become ready" >&2
  return 1
}

find_connection_id() {
  api GET "/api/v1/admin/connections" \
    | jq -r --arg name "${CONNECTION_NAME}" '.data[]? | select(.name == $name) | .connectionId' \
    | head -n1
}

find_layer_id() {
  local connection_id="$1"
  api GET "/api/v1/admin/connections/${connection_id}/layers?serviceName=${SERVICE_NAME}" \
    | jq -r '.data[]? | select(.layerName == "bench_points") | .layerId' \
    | head -n1
}

wait_for_public_items() {
  local attempts="${1:-10}"
  local delay="${2:-2}"
  local response=""

  for _ in $(seq 1 "${attempts}"); do
    response="$(
      curl -sf "${HONUA_URL}/ogc/features/collections/${COLLECTION_ID}/items?f=json&limit=1" \
        | jq -r '.features | length' 2>/dev/null || true
    )"

    if [ -n "${response}" ] && [ "${response}" != "0" ]; then
      echo "${response}"
      return 0
    fi

    sleep "${delay}"
  done

  echo "FAILED"
  return 1
}

require_cmd curl
require_cmd jq
require_cmd psql

echo "=== Honua Server Adapter ==="
echo "Server: ${HONUA_URL}"
wait_for_admin

# Step 1: Create database connection
echo "[1/7] Creating PostGIS connection..."
CONNECTION_ID="$(find_connection_id || true)"
if [ -z "${CONNECTION_ID}" ]; then
  CONNECTION_ID="$(
    api POST "/api/v1/admin/connections" '{
      "name": "'"${CONNECTION_NAME}"'",
      "description": "GeoBench shared PostGIS database",
      "host": "postgis-honua",
      "port": 5432,
      "databaseName": "geobench",
      "username": "geobench",
      "password": "geobench_pass",
      "sslRequired": false,
      "sslMode": "Disable"
    }' | jq -r '.data.connectionId // .connectionId // empty'
  )"
fi

if [ -z "${CONNECTION_ID}" ]; then
  echo "ERROR: failed to create or locate Honua connection" >&2
  exit 1
fi

echo "  Connection ID: ${CONNECTION_ID}"

# Step 2: Discover tables
echo "[2/7] Discovering tables..."
api GET "/api/v1/admin/connections/${CONNECTION_ID}/tables" \
  | jq -r '.tables[]? | select(.schema == "public" and .table == "bench_points") | "\(.schema).\(.table) (\(.estimatedRows) rows est.)"'

# Step 3: Publish bench_points layer
echo "[3/7] Publishing bench_points layer..."
LAYER_ID="$(find_layer_id "${CONNECTION_ID}" || true)"
if [ -z "${LAYER_ID}" ]; then
  LAYER_ID="$(
    api POST "/api/v1/admin/connections/${CONNECTION_ID}/layers" '{
      "schema": "public",
      "table": "bench_points",
      "layerName": "bench_points",
      "description": "GeoBench 100K point dataset",
      "geometryColumn": "geom",
      "geometryType": "Point",
      "srid": 4326,
      "primaryKey": "id",
      "fields": [
        "id",
        "feature_name",
        "category",
        "status",
        "priority",
        "temperature",
        "population",
        "created_at",
        "updated_at",
        "country_code",
        "description"
      ],
      "serviceName": "'"${SERVICE_NAME}"'",
      "enabled": true
    }' | jq -r '.data.layerId // empty'
  )"
fi

if [ -z "${LAYER_ID}" ]; then
  echo "ERROR: failed to publish or locate bench_points layer" >&2
  exit 1
fi

echo "  Layer ID: ${LAYER_ID}"

# Step 4: Apply explicit benchmark style
echo "[4/8] Applying benchmark point style..."
STYLE_PAYLOAD="$(
  jq -n \
    --argjson layerId "${LAYER_ID}" \
    --arg color "${POINT_STYLE_COLOR}" \
    --argjson radius "${POINT_STYLE_RADIUS}" \
    '{
      mapLibreStyle: {
        version: 8,
        name: "geobench-simple-point",
        sources: {
          ("layer-" + ($layerId | tostring)): {
            type: "vector",
            tiles: ["/tiles/" + ($layerId | tostring) + "/{z}/{x}/{y}.mvt"],
            minzoom: 0,
            maxzoom: 22
          }
        },
        layers: [
          {
            id: ("layer-" + ($layerId | tostring) + "-circle"),
            type: "circle",
            source: ("layer-" + ($layerId | tostring)),
            "source-layer": "layer",
            paint: {
              "circle-color": $color,
              "circle-radius": $radius,
              "circle-stroke-width": 0
            }
          }
        ]
      }
    }'
)"
api PUT "/api/v1/admin/metadata/layers/${LAYER_ID}/style" "${STYLE_PAYLOAD}" >/dev/null
echo "  Applied explicit default style: color=${POINT_STYLE_COLOR}, radius=${POINT_STYLE_RADIUS}"

# Step 5: Populate features table
echo "[5/8] Populating features table from bench_points..."
psql "${PGURL}" -v ON_ERROR_STOP=1 -c "
  DELETE FROM public.features WHERE layer_id = ${LAYER_ID};
  INSERT INTO public.features (layer_id, geometry, attributes)
  SELECT
    ${LAYER_ID},
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
  FROM public.bench_points;
" >/dev/null

IMPORT_COUNT="$(psql "${PGURL}" -t -A -c "SELECT count(*) FROM public.features WHERE layer_id = ${LAYER_ID};")"
echo "  Imported ${IMPORT_COUNT} features"

# Step 6: Add benchmark-aligned expression indexes
echo "[6/8] Creating benchmark expression indexes..."
psql "${PGURL}" -v ON_ERROR_STOP=1 -c "
  DROP INDEX IF EXISTS public.idx_features_layer_category_expr;
  DROP INDEX IF EXISTS public.idx_features_layer_temperature_expr;
  DROP INDEX IF EXISTS public.idx_features_layer_feature_name_expr;
  DROP INDEX IF EXISTS public.idx_features_layer_sort_id_expr;
  DROP INDEX IF EXISTS public.idx_features_geometry_ogc_items_expr;

  CREATE INDEX IF NOT EXISTS idx_features_layer_category_objectid_expr
    ON public.features (layer_id, (attributes->>'category'), objectid);
  CREATE INDEX IF NOT EXISTS idx_features_layer_temperature_objectid_expr
    ON public.features (
      layer_id,
      ((NULLIF(attributes->>'temperature', ''))::double precision),
      objectid
    );
  CREATE INDEX IF NOT EXISTS idx_features_layer_feature_name_objectid_expr
    ON public.features (
      layer_id,
      ((attributes->>'feature_name')) text_pattern_ops,
      objectid
    );
  CREATE INDEX IF NOT EXISTS idx_features_geometry_ogc_items_expr
    ON public.features
    USING gist ((ST_SetSRID(ST_GeomFromEWKB((geometry)::bytea), 4326)));
  ANALYZE public.features;
" >/dev/null
echo "  Indexed hot filter and spatial fields to match Honua's real OGC query shape"

# Step 7: Enable anonymous access
echo "[7/8] Enabling anonymous access..."
api PUT "/api/v1/admin/services/${SERVICE_NAME}/access-policy" '{"allowAnonymous":true,"allowAnonymousWrite":false}' \
  | jq -r '.success // "failed"' 2>/dev/null || echo "  failed"
api POST "/api/v1/admin/cache/invalidate" '{"scope":"all"}' >/dev/null 2>&1 || true

# Step 8: Verify benchmark path
echo "[8/8] Verifying anonymous OGC items query..."
VERIFY="$(wait_for_public_items 5 2 || true)"

if [ "${VERIFY}" = "FAILED" ] && [ "${HONUA_RESTART_ON_VERIFY_FAIL:-1}" = "1" ] && command -v docker >/dev/null 2>&1; then
  echo "  OGC items path not visible yet; restarting Honua to refresh catalog state..."
  docker compose restart honua >/dev/null 2>&1 || true
  wait_for_admin
  api POST "/api/v1/admin/cache/invalidate" '{"scope":"all"}' >/dev/null 2>&1 || true
  VERIFY="$(wait_for_public_items 10 2 || true)"
fi

if [ "${VERIFY}" = "FAILED" ] || [ "${VERIFY}" = "0" ]; then
  echo "ERROR: OGC items query returned ${VERIFY} feature(s)" >&2
  exit 1
else
  echo "  OK: OGC items returned ${VERIFY} feature(s)"
fi

echo "=== Honua adapter complete ==="
