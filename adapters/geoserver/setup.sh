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
GEOBENCH_TESTS="${GEOBENCH_TESTS:-}"
WMTS_CACHE_POLICY="${WMTS_CACHE_POLICY:-warm}"
WCS_COVERAGE_ID="${GEOSERVER_WCS_COVERAGE:-${WCS_COVERAGE:-geobench:bench_raster}}"
WCS_COVERAGE_NAME="${WCS_COVERAGE_ID#*:}"
WCS_STORE_NAME="${GEOSERVER_WCS_STORE:-${WCS_COVERAGE_NAME}}"
ENABLE_WMTS=0
ENABLE_WCS=0

case " ${GEOBENCH_TESTS} " in
  *" wmts "*)
    ENABLE_WMTS=1
    ;;&
  *" wcs "*)
    ENABLE_WCS=1
    ;;
esac

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

# Step 5: Set explicit tile-cache policy for the current benchmark selection.
if [ "${ENABLE_WCS}" = "1" ]; then
  echo "[optional] Publishing self-contained WCS coverage..."
  TMPDIR="$(mktemp -d)"
  TIF_PATH="${TMPDIR}/${WCS_STORE_NAME}.tif"
  WCS_COVERAGE_PARAM="${WCS_COVERAGE_ID//:/%3A}"

  python3 - "${TIF_PATH}" <<'PY2'
import sys
import numpy as np
from osgeo import gdal, osr

output_path = sys.argv[1]
cols = 7200
rows = 3600
pixel_size = 0.05

driver = gdal.GetDriverByName("GTiff")
dataset = driver.Create(
    output_path,
    cols,
    rows,
    1,
    gdal.GDT_UInt16,
    options=["TILED=YES", "COMPRESS=DEFLATE"],
)
dataset.SetGeoTransform((-180.0, pixel_size, 0.0, 90.0, 0.0, -pixel_size))
spatial_ref = osr.SpatialReference()
spatial_ref.ImportFromEPSG(4326)
dataset.SetProjection(spatial_ref.ExportToWkt())
band = dataset.GetRasterBand(1)
band.SetNoDataValue(0)
base_row = np.arange(cols, dtype=np.uint16)
for row in range(rows):
    values = ((base_row + row) % 2047) + 1
    band.WriteArray(values.reshape(1, cols), 0, row)
band.FlushCache()
dataset.FlushCache()
dataset = None
PY2

  WCS_UPLOAD_URL="${GS_URL}/geoserver/rest/workspaces/geobench/coveragestores/${WCS_STORE_NAME}/file.geotiff?configure=first&coverageName=${WCS_COVERAGE_NAME}"
  WCS_UPLOAD_CODE="$({ curl -s -o /dev/null -w "%{http_code}" -X PUT "${WCS_UPLOAD_URL}" ${AUTH} -H "Content-Type: image/tiff" --data-binary @"${TIF_PATH}"; } || true)"
  if [ "${WCS_UPLOAD_CODE}" != "200" ] && [ "${WCS_UPLOAD_CODE}" != "201" ]; then
    echo "ERROR: WCS coverage upload failed (HTTP ${WCS_UPLOAD_CODE})" >&2
    rm -rf "${TMPDIR}"
    exit 1
  fi
  echo "  Uploaded ${WCS_COVERAGE_ID} (HTTP ${WCS_UPLOAD_CODE})"

  WCS_VERIFY_URL="${GS_URL}/geoserver/wcs?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&COVERAGE=${WCS_COVERAGE_PARAM}&CRS=EPSG:4326&BBOX=139.2325,35.2325,139.3325,35.3325&WIDTH=64&HEIGHT=64&FORMAT=GeoTIFF"
  WCS_VERIFY_PATH="${TMPDIR}/verify.tif"
  WCS_VERIFY_CODE="$({ curl -s -o "${WCS_VERIFY_PATH}" -w "%{http_code}" "${WCS_VERIFY_URL}"; } || true)"
  WCS_VERIFY_SIZE="$(wc -c < "${WCS_VERIFY_PATH}" 2>/dev/null | tr -d ' ' || echo 0)"
  if [ "${WCS_VERIFY_CODE}" != "200" ] || [ "${WCS_VERIFY_SIZE}" -le 0 ]; then
    echo "ERROR: WCS GetCoverage verification failed for ${WCS_COVERAGE_ID} (HTTP ${WCS_VERIFY_CODE}, bytes ${WCS_VERIFY_SIZE})" >&2
    rm -rf "${TMPDIR}"
    exit 1
  fi
  echo "  OK: WCS GetCoverage returned ${WCS_VERIFY_SIZE} byte(s)"
  rm -rf "${TMPDIR}"
fi

if [ "${ENABLE_WMTS}" = "1" ]; then
  echo "[5/6] Keeping GeoWebCache enabled for bench_points..."
  echo "  WMTS cache policy: ${WMTS_CACHE_POLICY}"
  if [ "${WMTS_CACHE_POLICY}" != "warm" ]; then
    echo "ERROR: unsupported WMTS cache policy '${WMTS_CACHE_POLICY}'" >&2
    echo "  Supported values: warm" >&2
    exit 1
  fi
else
  echo "[5/6] Disabling GeoWebCache for bench_points..."
  curl -sf -X PUT "${GS_URL}/geoserver/gwc/rest/layers/geobench:bench_points" \
    ${AUTH} \
    -H "Content-Type: application/json" \
    -d '{"GeoServerLayer":{"enabled":false}}' \
    -o /dev/null -w "  HTTP %{http_code}\n" || echo "  (GWC disable may have failed — non-critical)"
fi

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

if [ "${ENABLE_WMTS}" = "1" ]; then
  echo "[optional] Verifying and warming WMTS tiles..."
  WMTS_BASE="${GS_URL}/geoserver/gwc/service/wmts"
  for TILE in \
    "EPSG:900913:0 0 0" \
    "EPSG:900913:1 1 0" \
    "EPSG:900913:2 0 1"
  do
    set -- ${TILE}
    TILE_MATRIX="$1"
    TILE_COL="$2"
    TILE_ROW="$3"
    TILE_URL="${WMTS_BASE}?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile&LAYER=geobench:bench_points&STYLE=&TILEMATRIXSET=EPSG:900913&TILEMATRIX=${TILE_MATRIX}&TILECOL=${TILE_COL}&TILEROW=${TILE_ROW}&FORMAT=image/png"
    HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${TILE_URL}")"
    if [ "${HTTP_CODE}" != "200" ]; then
      echo "ERROR: WMTS tile verification failed for ${TILE_MATRIX}/${TILE_COL}/${TILE_ROW} (HTTP ${HTTP_CODE})" >&2
      exit 1
    fi
    echo "  Warmed ${TILE_MATRIX}/${TILE_COL}/${TILE_ROW}"
  done
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
