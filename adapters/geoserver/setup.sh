#!/usr/bin/env bash
# GeoBench: GeoServer adapter — creates workspace, PostGIS store, publishes layer, disables GWC.
set -euo pipefail

GS_URL="${GS_URL:-http://geoserver:8080}"
GS_USER="${GS_USER:-admin}"
GS_PASS="${GS_PASS:-geoserver}"
AUTH="-u ${GS_USER}:${GS_PASS}"

echo "=== GeoServer Adapter ==="
echo "Server: ${GS_URL}"

# Step 1: Create workspace
echo "[1/5] Creating workspace 'geobench'..."
curl -sf -X POST "${GS_URL}/geoserver/rest/workspaces" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{"workspace":{"name":"geobench"}}' \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (workspace may already exist)"

# Step 2: Create PostGIS datastore
echo "[2/5] Creating PostGIS datastore..."
curl -sf -X POST "${GS_URL}/geoserver/rest/workspaces/geobench/datastores" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{
    "dataStore": {
      "name": "postgis",
      "type": "PostGIS",
      "connectionParameters": {
        "entry": [
          {"@key": "host", "$": "postgis"},
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
echo "[3/5] Publishing bench_points feature type..."
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

# Step 4: Disable GeoWebCache for this layer
echo "[4/5] Disabling GeoWebCache for bench_points..."
curl -sf -X PUT "${GS_URL}/geoserver/gwc/rest/layers/geobench:bench_points" \
  ${AUTH} \
  -H "Content-Type: application/json" \
  -d '{"GeoServerLayer":{"enabled":false}}' \
  -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (GWC disable may have failed — non-critical)"

# Step 5: Verify OGC API Features endpoint
echo "[5/5] Verifying OGC API Features endpoint..."
VERIFY=$(curl -sf "${GS_URL}/geoserver/ogc/features/v1/collections/geobench:bench_points/items?limit=1" \
  | jq -r '.numberReturned // (.features | length)' 2>/dev/null || echo "FAILED")

if [ "${VERIFY}" = "FAILED" ]; then
  echo "  WARNING: OGC endpoint verification failed."
  echo "  Checking available collections..."
  curl -sf "${GS_URL}/geoserver/ogc/features/v1/collections" | jq -r '.collections[].id' 2>/dev/null || true
else
  echo "  OK: geobench:bench_points collection is live (returned ${VERIFY} feature(s))"
fi

echo "=== GeoServer adapter complete ==="
