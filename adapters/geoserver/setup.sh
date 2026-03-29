#!/usr/bin/env bash
# GeoBench: GeoServer adapter — creates workspace, PostGIS store, publishes layer, disables GWC.
set -euo pipefail

GS_URL="${GS_URL:-http://geoserver:8080}"
GS_USER="${GS_USER:-admin}"
GS_PASS="${GS_PASS:-geoserver}"
AUTH="-u ${GS_USER}:${GS_PASS}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STYLE_NAME="${GEOBENCH_STYLE_NAME:-geobench_simple_point}"
STYLE_FILE="${SCRIPT_DIR}/geobench_simple_point.sld"

echo "=== GeoServer Adapter ==="
echo "Server: ${GS_URL}"

# Step 1: Create workspace
echo "[1/6] Creating workspace 'geobench'..."
curl -sf -X POST "${GS_URL}/geoserver/rest/workspaces" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{"workspace":{"name":"geobench"}}' \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (workspace may already exist)"

# Step 2: Create PostGIS datastore
echo "[2/6] Creating PostGIS datastore..."
curl -sf -X POST "${GS_URL}/geoserver/rest/workspaces/geobench/datastores" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{
    "dataStore": {
      "name": "postgis",
      "type": "PostGIS",
      "connectionParameters": {
        "entry": [
          {"@key": "host", "$": "postgis-geoserver"},
          {"@key": "port", "$": "5432"},
          {"@key": "database", "$": "geobench"},
          {"@key": "user", "$": "geobench"},
          {"@key": "passwd", "$": "geobench_pass"},
          {"@key": "dbtype", "$": "postgis"},
          {"@key": "schema", "$": "public"},
          {"@key": "Loose bbox", "$": "false"},
          {"@key": "Estimated extends", "$": "true"},
          {"@key": "encode functions", "$": "true"},
          {"@key": "max connections", "$": "20"},
          {"@key": "min connections", "$": "5"}
        ]
      }
    }
  }' \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (datastore may already exist)"

# Step 3: Publish bench_points feature type
echo "[3/6] Publishing bench_points feature type..."
curl -sf -X POST "${GS_URL}/geoserver/rest/workspaces/geobench/datastores/postgis/featuretypes" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{
    "featureType": {
      "name": "bench_points",
      "nativeName": "bench_points",
      "title": "GeoBench 100K Points",
      "srs": "EPSG:4326",
      "nativeBoundingBox": {
        "minx": -180, "maxx": 180, "miny": -90, "maxy": 90,
        "crs": "EPSG:4326"
      },
      "latLonBoundingBox": {
        "minx": -180, "maxx": 180, "miny": -90, "maxy": 90,
        "crs": "EPSG:4326"
      }
    }
  }' \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (feature type may already exist)"

# Step 4: Upload and bind explicit benchmark style
echo "[4/6] Uploading benchmark point style..."
curl -sf -X POST "${GS_URL}/geoserver/rest/workspaces/geobench/styles" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d "{\"style\":{\"name\":\"${STYLE_NAME}\",\"filename\":\"${STYLE_NAME}.sld\"}}" \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (style may already exist)"

curl -sf -X PUT "${GS_URL}/geoserver/rest/workspaces/geobench/styles/${STYLE_NAME}" \
  ${AUTH} \
  -H "Content-Type: application/vnd.ogc.sld+xml" \
  --data-binary @"${STYLE_FILE}" \
  -o /dev/null -w "  HTTP %{http_code}\n"

curl -sf -X PUT "${GS_URL}/geoserver/rest/layers/geobench:bench_points" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d "{\"layer\":{\"defaultStyle\":{\"name\":\"${STYLE_NAME}\",\"workspace\":\"geobench\"}}}" \
  -o /dev/null -w "  HTTP %{http_code}\n"

# Step 5: Disable GeoWebCache for this layer
echo "[5/6] Disabling GeoWebCache for bench_points..."
curl -sf -X PUT "${GS_URL}/geoserver/gwc/rest/layers/geobench:bench_points" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{"GeoServerLayer":{"enabled":false}}' \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (GWC disable may have failed — non-critical)"

# Step 6: Verify OGC API Features endpoint
echo "[6/6] Verifying OGC API Features endpoint..."
VERIFY=$(curl -sf "${GS_URL}/geoserver/ogc/features/v1/collections/geobench:bench_points/items?limit=1" \
  | jq -r '.numberReturned // (.features | length)' 2>/dev/null || echo "FAILED")

if [ "${VERIFY}" = "FAILED" ]; then
  echo "  WARNING: OGC endpoint verification failed."
  echo "  Checking available collections..."
  curl -sf "${GS_URL}/geoserver/ogc/features/v1/collections" | jq -r '.collections[].id' 2>/dev/null || true
else
  echo "  OK: geobench:bench_points collection is live (returned ${VERIFY} feature(s))"
fi

if [ "${GEOSERVER_GSR_ENABLED:-0}" = "1" ]; then
  GSR_SERVICE="${GEOSERVER_GSR_SERVICE:-geobench}"
  GSR_LAYER_ID="${GEOSERVER_GSR_LAYER_ID:-0}"
  GSR_URL="${GS_URL}/geoserver/gsr/services/${GSR_SERVICE}/FeatureServer/${GSR_LAYER_ID}/query"
  GSR_BBOX="${GEOSERVER_GSR_VERIFY_BBOX:-139.5650,35.5650,139.8150,35.8150}"

  echo "[optional] Verifying GeoServices REST FeatureServer query..."
  GSR_VERIFY="$(
    curl -sf "${GSR_URL}?f=json&where=1%3D1&outFields=*&returnGeometry=true&geometryType=esriGeometryEnvelope&geometry=${GSR_BBOX}&inSR=4326&outSR=4326&spatialRel=esriSpatialRelIntersects" \
      | jq -r '.features | length' 2>/dev/null || echo "FAILED"
  )"

  if [ "${GSR_VERIFY}" = "FAILED" ]; then
    echo "ERROR: GeoServer GSR query verification failed." >&2
    echo "  Expected endpoint: ${GSR_URL}" >&2
    echo "  Make sure GEOSERVER_IMAGE points at a matching GeoServer nightly build and" >&2
    echo "  GEOSERVER_COMMUNITY_EXTENSIONS includes gsr." >&2
    exit 1
  fi

  echo "  OK: GeoServices query returned ${GSR_VERIFY} feature(s)"
fi

echo "=== GeoServer adapter complete ==="
