// GeoBench: shared helpers for standards-based WFS benchmarking.
//
// Supported local capability profile:
// - Honua: WFS 2.0.0 with FES 2.0 KVP FILTER support
// - GeoServer: WFS 2.0.0 with FES 2.0 KVP FILTER support
// - QGIS: WFS 1.1.0
//
// Filter caveat:
// The shared filtered-query suite targets the common Honua/GeoServer
// WFS 2.0 + FES 2.0 profile. QGIS remains excluded from that row because
// the local benchmark image is currently pinned to WFS 1.1.0.

import { deterministicChoice, deterministicRange } from "./deterministic.js";

var DEFAULT_LIMIT = parseInt(__ENV.WFS_RESULT_LIMIT || __ENV.RESULT_LIMIT || "100", 10);
var DEFAULT_COLLECTION = __ENV.WFS_COLLECTION || "bench_points";

var SERVERS = {
  honua: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    path: __ENV.HONUA_WFS_PATH || "/wfs",
    version: "2.0.0",
    typeParam: "TYPENAMES",
    typeName: __ENV.HONUA_WFS_LAYER || DEFAULT_COLLECTION,
    limitParam: "COUNT",
    bboxParam: "BBOX",
    bboxCrsSuffix: "",
    outputFormat: "application/json",
    filterDialect: "fes-2.0",
  },
  geoserver: {
    baseUrl: __ENV.GEOSERVER_URL || "http://geoserver:8080",
    path: __ENV.GEOSERVER_WFS_PATH || "/geoserver/wfs",
    version: "2.0.0",
    typeParam: "TYPENAMES",
    typeName: __ENV.GEOSERVER_WFS_LAYER || "geobench:bench_points",
    limitParam: "COUNT",
    bboxParam: "BBOX",
    bboxCrsSuffix: ",EPSG:4326",
    outputFormat: "application/json",
    filterDialect: "fes-2.0",
  },
  qgis: {
    baseUrl: __ENV.QGIS_URL || "http://qgis-server:80",
    path: __ENV.QGIS_WFS_PATH || "/ows/",
    mapPath: __ENV.QGIS_MAP_PATH || "/etc/qgisserver/geobench.qgs",
    version: "1.1.0",
    typeParam: "TYPENAME",
    typeName: __ENV.QGIS_WFS_LAYER || DEFAULT_COLLECTION,
    limitParam: "MAXFEATURES",
    bboxParam: "BBOX",
    bboxCrsSuffix: "",
    outputFormat: "application/vnd.geo+json",
    filterDialect: null,
  },
};

function escapeXml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function escapeLikePrefix(prefix) {
  return String(prefix)
    .replace(/\\/g, "\\\\")
    .replace(/_/g, "\\_")
    .replace(/%/g, "\\%");
}

function normalizeFilterSpec(spec) {
  if (!spec) {
    return null;
  }

  if (spec.type === "between") {
    return {
      type: spec.type,
      field: spec.field,
      low: parseFloat(spec.low.toFixed(1)),
      high: parseFloat(spec.high.toFixed(1)),
    };
  }

  return spec;
}

function buildFes20Filter(filterSpec) {
  if (!filterSpec) {
    throw new Error("WFS filtered request requires a filter spec");
  }

  if (filterSpec.type === "eq") {
    return (
      '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">' +
      "<fes:PropertyIsEqualTo>" +
      "<fes:ValueReference>" + escapeXml(filterSpec.field) + "</fes:ValueReference>" +
      "<fes:Literal>" + escapeXml(filterSpec.value) + "</fes:Literal>" +
      "</fes:PropertyIsEqualTo>" +
      "</fes:Filter>"
    );
  }

  if (filterSpec.type === "between") {
    return (
      '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">' +
      "<fes:PropertyIsBetween>" +
      "<fes:ValueReference>" + escapeXml(filterSpec.field) + "</fes:ValueReference>" +
      "<fes:LowerBoundary><fes:Literal>" + escapeXml(filterSpec.low.toFixed(1)) + "</fes:Literal></fes:LowerBoundary>" +
      "<fes:UpperBoundary><fes:Literal>" + escapeXml(filterSpec.high.toFixed(1)) + "</fes:Literal></fes:UpperBoundary>" +
      "</fes:PropertyIsBetween>" +
      "</fes:Filter>"
    );
  }

  if (filterSpec.type === "prefix") {
    return (
      '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">' +
      '<fes:PropertyIsLike wildCard="%" singleChar="_" escapeChar="\\">' +
      "<fes:ValueReference>" + escapeXml(filterSpec.field) + "</fes:ValueReference>" +
      "<fes:Literal>" + escapeXml(escapeLikePrefix(filterSpec.prefix) + "%") + "</fes:Literal>" +
      "</fes:PropertyIsLike>" +
      "</fes:Filter>"
    );
  }

  throw new Error("Unsupported WFS filter spec: " + JSON.stringify(filterSpec));
}

export var WFS_BBOX_SIZES = {
  small: 0.1,
  medium: 5.0,
  large: 30.0,
};

// Shared coordinate anchors sampled from the common benchmark dataset.
// These points return hits on Honua, GeoServer, and QGIS in this workspace.
var WFS_HOTSPOTS = [
  { lon: 72.47699, lat: -5.462423 },
  { lon: 13.042113, lat: 66.505049 },
  { lon: -48.660416, lat: -11.876474 },
  { lon: 24.184819, lat: 33.328855 },
  { lon: -28.022412, lat: -51.741398 },
];

function getServer(name) {
  var server = SERVERS[name];
  if (!server) {
    throw new Error("Unknown WFS server: " + name + ". Use: honua, geoserver, qgis");
  }
  return { name: name, config: server };
}

function buildBaseUrl(server) {
  return server.config.baseUrl + server.config.path;
}

function parseJson(response) {
  try {
    return response.json();
  } catch (err) {
    return null;
  }
}

function parseBboxBounds(bbox) {
  var parts = String(bbox).split(",");
  if (parts.length < 4) {
    throw new Error("Invalid bbox: " + bbox);
  }

  return {
    minLon: parseFloat(parts[0]),
    minLat: parseFloat(parts[1]),
    maxLon: parseFloat(parts[2]),
    maxLat: parseFloat(parts[3]),
  };
}

function pointWithinBounds(coords, bounds) {
  return (
    coords &&
    coords.length >= 2 &&
    coords[0] >= bounds.minLon &&
    coords[0] <= bounds.maxLon &&
    coords[1] >= bounds.minLat &&
    coords[1] <= bounds.maxLat
  );
}

function validateFeatureCollection(response, limit) {
  var payload = parseJson(response);
  var features = payload && Array.isArray(payload.features) ? payload.features : [];

  return {
    ok:
      payload !== null &&
      payload.type === "FeatureCollection" &&
      Array.isArray(payload.features) &&
      features.length > 0 &&
      features.length <= limit &&
      features.every(function (feature) {
        return (
          feature &&
          feature.type === "Feature" &&
          feature.geometry &&
          feature.properties &&
          feature.geometry.type === "Point" &&
          Array.isArray(feature.geometry.coordinates)
        );
      }),
    features: features,
    payload: payload,
  };
}

function validateBboxCollection(response, bbox, limit) {
  var validated = validateFeatureCollection(response, limit);
  var bounds = parseBboxBounds(bbox);

  return {
    ok:
      validated.ok &&
      validated.features.every(function (feature) {
        return pointWithinBounds(
          feature.geometry && feature.geometry.coordinates,
          bounds
        );
      }),
    features: validated.features,
    payload: validated.payload,
  };
}

function validateFilteredCollection(response, filterSpec, limit) {
  var normalizedFilter = normalizeFilterSpec(filterSpec);
  var validated = validateFeatureCollection(response, limit);

  if (!validated.ok) {
    return false;
  }

  if (normalizedFilter.type === "eq") {
    return validated.features.every(function (feature) {
      var properties = feature.properties || {};
      return String(properties[normalizedFilter.field]) === String(normalizedFilter.value);
    });
  }

  if (normalizedFilter.type === "between") {
    return validated.features.every(function (feature) {
      var properties = feature.properties || {};
      var numeric = parseFloat(properties[normalizedFilter.field]);
      return numeric >= normalizedFilter.low && numeric <= normalizedFilter.high;
    });
  }

  if (normalizedFilter.type === "prefix") {
    return validated.features.every(function (feature) {
      var properties = feature.properties || {};
      return String(properties[normalizedFilter.field] || "").indexOf(normalizedFilter.prefix) === 0;
    });
  }

  return false;
}

function addCommonParams(url, server, limit) {
  url += (url.indexOf("?") === -1 ? "?" : "&");
  url += "SERVICE=WFS";
  url += "&VERSION=" + server.config.version;
  url += "&REQUEST=GetFeature";
  url += "&" + server.config.typeParam + "=" + encodeURIComponent(server.config.typeName);
  url += "&" + server.config.limitParam + "=" + limit;
  url += "&OUTPUTFORMAT=" + encodeURIComponent(server.config.outputFormat);
  return url;
}

/**
 * Build a WFS GetFeature request for the selected server.
 *
 * Only comparable read operations are emitted here:
 * - base collection read
 * - bbox-restricted read
 *
 * Filtered WFS requests are intentionally omitted because the local server
 * mix does not share one common standards-based filter syntax.
 *
 * @param {Object} params
 * @param {string} [params.bbox] - Bounding box in minx,miny,maxx,maxy form.
 * @param {number} [params.limit] - Max features to return.
 * @returns {Object} request metadata with url, name, and validate().
 */
export function buildGetFeatureRequest(params) {
  params = params || {};
  var server = getServer((__ENV.SERVER || "honua").toLowerCase());
  var limit = params.limit || DEFAULT_LIMIT;
  var url = buildBaseUrl(server);
  var validate = function () {
    return true;
  };

  if (server.name === "qgis") {
    url += "?MAP=" + encodeURIComponent(server.config.mapPath);
  }

  url = addCommonParams(url, server, limit);

  if (params.bbox) {
    url += "&" + server.config.bboxParam + "=" + params.bbox + server.config.bboxCrsSuffix;
    validate = function (response) {
      return validateBboxCollection(response, params.bbox, limit).ok;
    };
  } else {
    validate = function (response) {
      return validateFeatureCollection(response, limit).ok;
    };
  }

  return {
    url: url,
    name: server.name + ":wfs:getfeature",
    validate: validate,
  };
}

export function wfsFilteredQueriesSupported() {
  var server = getServer((__ENV.SERVER || "honua").toLowerCase());
  return !!server.config.filterDialect;
}

export function buildFilteredGetFeatureRequest(params) {
  params = params || {};
  var server = getServer((__ENV.SERVER || "honua").toLowerCase());
  var limit = params.limit || DEFAULT_LIMIT;
  var filterSpec = normalizeFilterSpec(params.filterSpec || null);

  if (!filterSpec) {
    throw new Error("Missing filterSpec for WFS filtered request");
  }

  if (!server.config.filterDialect) {
    throw new Error(
      "WFS filtered queries are not supported for " + server.name +
      " in this harness; use honua or geoserver"
    );
  }

  var url = buildBaseUrl(server);
  if (server.name === "qgis") {
    url += "?MAP=" + encodeURIComponent(server.config.mapPath);
  }

  url = addCommonParams(url, server, limit);
  url += "&FILTER=" + encodeURIComponent(buildFes20Filter(filterSpec));

  return {
    url: url,
    name: server.name + ":wfs:filtered",
    validate: function (response) {
      return validateFilteredCollection(response, filterSpec, limit);
    },
  };
}

/**
 * Generate a deterministic bbox around one of the benchmark hotspots.
 * @param {number} sizeDeg
 * @param {number} [salt]
 * @returns {string} minx,miny,maxx,maxy
 */
export function randomWfsBbox(sizeDeg, salt) {
  var center = deterministicChoice(WFS_HOTSPOTS, salt || 0);
  var half = sizeDeg / 2;
  var jitter = deterministicRange(-half, half, (salt || 0) ^ 0x7f4a7c15);
  var minLon = Math.max(-180, center.lon - half + jitter);
  var minLat = Math.max(-90, center.lat - half + jitter);
  var maxLon = Math.min(180, minLon + sizeDeg);
  var maxLat = Math.min(90, minLat + sizeDeg);
  return (
    minLon.toFixed(5) + "," +
    minLat.toFixed(5) + "," +
    maxLon.toFixed(5) + "," +
    maxLat.toFixed(5)
  );
}

/**
 * Standard response checks for WFS requests.
 */
export function wfsChecks(request) {
  return {
    "status is 200": function (r) {
      return r.status === 200;
    },
    "response matches request": function (r) {
      return request && request.validate ? request.validate(r) : true;
    },
  };
}
