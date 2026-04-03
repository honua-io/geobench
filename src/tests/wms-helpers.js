// GeoBench: shared helpers for WMS filtered, WMTS, and WCS benchmarks.

var DEFAULT_4326_BBOX = "0,0,0,0";

var SERVERS = {
  honua: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    path: __ENV.HONUA_WMS_PATH || "/ogc/services/default/wms",
    layer: __ENV.HONUA_WMS_LAYER || "bench_points",
    wmsFilterParam: "FILTER",
  },
  geoserver: {
    baseUrl: __ENV.GEOSERVER_URL || "http://geoserver:8080",
    path: "/geoserver/wms",
    layer: __ENV.GEOSERVER_WMS_LAYER || "geobench:bench_points",
    wmsFilterParam: "FILTER",
    wmts: {
      path: "/geoserver/gwc/service/wmts",
      layer: __ENV.GEOSERVER_WMTS_LAYER || "geobench:bench_points",
      tileMatrixSet: __ENV.GEOSERVER_WMTS_TILE_MATRIX_SET || "EPSG:900913",
      tileFormat: "image/png",
    },
    wcs: {
      path: "/geoserver/wcs",
      format: "GeoTIFF",
      crs: "EPSG:4326",
    },
  },
  qgis: {
    baseUrl: __ENV.QGIS_URL || "http://qgis-server:80",
    path: __ENV.QGIS_WMS_PATH || "/ows/",
    layer: __ENV.QGIS_WMS_LAYER || "bench_points",
    mapPath: __ENV.QGIS_MAP_PATH || "/etc/qgisserver/geobench.qgs",
    wmsFilterParam: "FILTER",
    wmts: null,
    wcs: null,
  },
};

var TILE_DIMENSION = 256;

function getServer(serverName) {
  var server = SERVERS[serverName];
  if (!server) {
    throw new Error("Unknown WMS/WMTS/WCS server: " + serverName);
  }
  return { name: serverName, config: server };
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function toFinite(value, fallback) {
  if (!value) {
    return fallback;
  }

  var parsed = parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  return parsed;
}

export function validateBbox(bbox) {
  if (!bbox || String(bbox).trim().length === 0) {
    throw new Error("WMS/WCS request requires a bbox");
  }
  return bbox;
}

export function buildFilterXml(spec) {
  if (!spec || !spec.type) {
    throw new Error("WMS filter request requires a filter spec");
  }

  if (spec.type === "eq") {
    return (
      "<Filter xmlns=\"http://www.opengis.net/ogc\">" +
      "<PropertyIsEqualTo>" +
      "<PropertyName>" + escapeXml(spec.field) + "</PropertyName>" +
      "<Literal>" + escapeXml(spec.value) + "</Literal>" +
      "</PropertyIsEqualTo>" +
      "</Filter>"
    );
  }

  if (spec.type === "between") {
    return (
      "<Filter xmlns=\"http://www.opengis.net/ogc\">" +
      "<PropertyIsBetween>" +
      "<PropertyName>" + escapeXml(spec.field) + "</PropertyName>" +
      "<LowerBoundary><Literal>" + toFinite(spec.low, 0) + "</Literal></LowerBoundary>" +
      "<UpperBoundary><Literal>" + toFinite(spec.high, 0) + "</Literal></UpperBoundary>" +
      "</PropertyIsBetween>" +
      "</Filter>"
    );
  }

  if (spec.type === "prefix") {
    return (
      "<Filter xmlns=\"http://www.opengis.net/ogc\">" +
      "<PropertyIsLike wildCard=\"%\" singleChar=\"_\" escape=\"\\\\\">" +
      "<PropertyName>" + escapeXml(spec.field) + "</PropertyName>" +
      "<Literal>" + escapeXml(spec.prefix) + "%</Literal>" +
      "</PropertyIsLike>" +
      "</Filter>"
    );
  }

  throw new Error("Unsupported WMS filter type: " + spec.type);
}

export function buildWmsFilteredMapRequest(serverName, params) {
  var server = getServer(serverName);
  params = params || {};
  var filterSpec = params.filterSpec;
  var width = params.width || TILE_DIMENSION;
  var height = params.height || TILE_DIMENSION;
  var crs = params.crs || "CRS:84";
  var bbox = validateBbox(params.bbox || DEFAULT_4326_BBOX);
  var filterType = params.filterType || "custom";
  var layer = params.layer || server.config.layer;
  var url = server.config.baseUrl + server.config.path;
  var filterParam = server.config.wmsFilterParam || "FILTER";

  if (server.config.mapPath) {
    url += "?MAP=" + encodeURIComponent(server.config.mapPath) + "&SERVICE=WMS";
  } else {
    url += "?SERVICE=WMS";
  }

  url += "&VERSION=1.3.0";
  url += "&REQUEST=GetMap";
  url += "&LAYERS=" + encodeURIComponent(layer);
  url += "&STYLES=";
  url += "&CRS=" + encodeURIComponent(crs);
  url += "&BBOX=" + bbox;
  url += "&WIDTH=" + width;
  url += "&HEIGHT=" + height;
  url += "&FORMAT=image/png";
  url += "&TRANSPARENT=true";
  url += "&" + filterParam + "=" + encodeURIComponent(buildFilterXml(filterSpec));

  return {
    url: url,
    name: server.name + ":wms-filtered:" + filterType,
    expectedSize: {
      width: width,
      height: height,
    },
  };
}

export function buildWmtsGetTileRequest(serverName, params) {
  var server = getServer(serverName);
  if (!server.config.wmts) {
    throw new Error("WMTS track is not configured for server: " + server.name);
  }

  params = params || {};
  var tileMatrixSet = params.tileMatrixSet || server.config.wmts.tileMatrixSet;
  var tileMatrix = params.tileMatrix || String(tileMatrixSet) + ":" + (params.level || 0);
  var tileCol = params.tileCol || 0;
  var tileRow = params.tileRow || 0;
  var layer = params.layer || server.config.wmts.layer;
  var format = params.format || server.config.wmts.tileFormat || "image/png";

  var url = server.config.baseUrl + server.config.wmts.path;
  url += "?SERVICE=WMTS";
  url += "&VERSION=1.0.0";
  url += "&REQUEST=GetTile";
  url += "&LAYER=" + encodeURIComponent(layer);
  url += "&STYLE=";
  url += "&TILEMATRIXSET=" + encodeURIComponent(tileMatrixSet);
  url += "&TILEMATRIX=" + encodeURIComponent(tileMatrix);
  url += "&TILECOL=" + encodeURIComponent(tileCol);
  url += "&TILEROW=" + encodeURIComponent(tileRow);
  url += "&FORMAT=" + encodeURIComponent(format);

  return {
    url: url,
    name: server.name + ":wmts:" + (params.levelLabel || String(params.level || 0)),
    expectedSize: {
      width: TILE_DIMENSION,
      height: TILE_DIMENSION,
    },
  };
}

export function buildWcsGetCoverageRequest(serverName, params) {
  var server = getServer(serverName);
  if (!server.config.wcs) {
    throw new Error("WCS track is not configured for server: " + server.name);
  }

  params = params || {};
  if (!params.coverage || String(params.coverage).trim().length === 0) {
    throw new Error("WCS request requires coverage id");
  }

  var bbox = validateBbox(params.bbox || DEFAULT_4326_BBOX);
  var width = params.width || TILE_DIMENSION;
  var height = params.height || TILE_DIMENSION;
  var format = params.format || server.config.wcs.format || "GeoTIFF";
  var crs = params.crs || server.config.wcs.crs || "EPSG:4326";
  var version = params.version || "1.0.0";
  var url = server.config.baseUrl + server.config.wcs.path;

  url += "?SERVICE=WCS";
  url += "&VERSION=" + encodeURIComponent(version);
  url += "&REQUEST=GetCoverage";
  url += "&COVERAGE=" + encodeURIComponent(params.coverage);
  url += "&CRS=" + encodeURIComponent(crs);
  url += "&BBOX=" + bbox;
  url += "&WIDTH=" + width;
  url += "&HEIGHT=" + height;
  url += "&FORMAT=" + encodeURIComponent(format);

  return {
    url: url,
    name: server.name + ":wcs:" + params.coverage,
    expectedSize: {
      width: width,
      height: height,
    },
  };
}
