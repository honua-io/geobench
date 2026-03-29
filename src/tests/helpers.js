// GeoBench: shared k6 helpers for comparable feature-service benchmarking.

import { deterministicChoice, deterministicRange } from "./deterministic.js";

// Server registry — each entry defines how to reach the OGC API Features endpoint.
var SERVERS = {
  honua: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    itemsPath: function (collection) {
      // Honua uses numeric layer IDs as collection identifiers
      var collectionId = __ENV.HONUA_COLLECTION_ID || "1";
      return "/ogc/features/collections/" + collectionId + "/items";
    },
    filterMode: "cql2",
    offsetParam: "offset",
    sortParam: "sortby",
  },
  geoserver: {
    baseUrl: __ENV.GEOSERVER_URL || "http://geoserver:8080",
    itemsPath: function (collection) {
      return (
        "/geoserver/ogc/features/v1/collections/geobench:" +
        collection +
        "/items"
      );
    },
    filterMode: "cql2",
    offsetParam: "startIndex",
    sortParam: "sortby",
  },
  qgis: {
    baseUrl: __ENV.QGIS_URL || "http://qgis-server:80",
    itemsPath: function (collection) {
      return "/wfs3/collections/" + collection + "/items";
    },
    filterMode: "wfs-fes",
    offsetParam: "offset",
    sortParam: "SORTBY",
    mapPath: __ENV.QGIS_MAP_PATH || "/etc/qgisserver/geobench.qgs",
  },
};

export var COLLECTION = __ENV.COLLECTION || "bench_points";
export var RESULT_LIMIT = parseInt(__ENV.RESULT_LIMIT || "100");
export var SORT_BY = __ENV.SORT_BY || "id";

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

function quoteCqlLiteral(value) {
  return "'" + String(value).replace(/'/g, "''") + "'";
}

function normalizeFilterSpec(spec) {
  if (!spec) {
    return null;
  }

  if (spec.type === "between") {
    var low = parseFloat(spec.low.toFixed(1));
    var high = parseFloat(spec.high.toFixed(1));
    return {
      type: spec.type,
      field: spec.field,
      low: low,
      high: high,
    };
  }

  return spec;
}

function buildCql2Filter(spec) {
  if (!spec) {
    return null;
  }

  if (spec.type === "eq") {
    return spec.field + "=" + quoteCqlLiteral(spec.value);
  }

  if (spec.type === "between") {
    return (
      spec.field +
      " >= " + spec.low.toFixed(1) +
      " AND " +
      spec.field +
      " <= " + spec.high.toFixed(1)
    );
  }

  if (spec.type === "prefix") {
    return spec.field + " LIKE " + quoteCqlLiteral(spec.prefix + "%");
  }

  throw new Error("Unsupported CQL2 filter spec: " + JSON.stringify(spec));
}

function buildQgisFilterXml(spec) {
  if (!spec) {
    return null;
  }

  if (spec.type === "eq") {
    return (
      '<Filter xmlns="http://www.opengis.net/ogc">' +
      "<PropertyIsEqualTo>" +
      "<PropertyName>" + escapeXml(spec.field) + "</PropertyName>" +
      "<Literal>" + escapeXml(spec.value) + "</Literal>" +
      "</PropertyIsEqualTo>" +
      "</Filter>"
    );
  }

  if (spec.type === "between") {
    return (
      '<Filter xmlns="http://www.opengis.net/ogc">' +
      "<PropertyIsBetween>" +
      "<PropertyName>" + escapeXml(spec.field) + "</PropertyName>" +
      "<LowerBoundary><Literal>" + escapeXml(spec.low.toFixed(1)) + "</Literal></LowerBoundary>" +
      "<UpperBoundary><Literal>" + escapeXml(spec.high.toFixed(1)) + "</Literal></UpperBoundary>" +
      "</PropertyIsBetween>" +
      "</Filter>"
    );
  }

  if (spec.type === "prefix") {
    return (
      '<Filter xmlns="http://www.opengis.net/ogc">' +
      '<PropertyIsLike wildCard="%" singleChar="_" escapeChar="\\">' +
      "<PropertyName>" + escapeXml(spec.field) + "</PropertyName>" +
      "<Literal>" + escapeXml(escapeLikePrefix(spec.prefix) + "%") + "</Literal>" +
      "</PropertyIsLike>" +
      "</Filter>"
    );
  }

  throw new Error("Unsupported QGIS filter spec: " + JSON.stringify(spec));
}

function parseFeatureCollection(response) {
  try {
    return response.json();
  } catch (err) {
    return null;
  }
}

function getFeatures(response) {
  var payload = parseFeatureCollection(response);
  return payload && payload.features ? payload.features : [];
}

function extractFeatureId(feature) {
  if (!feature) {
    return null;
  }

  var properties = feature.properties || {};
  if (properties.id !== undefined && properties.id !== null) {
    return parseInt(properties.id, 10);
  }

  if (feature.id !== undefined && feature.id !== null) {
    var rawId = String(feature.id);
    var match = rawId.match(/(\d+)$/);
    if (match) {
      return parseInt(match[1], 10);
    }
  }

  return null;
}

function pointWithinBbox(coords, bbox) {
  return (
    coords &&
    coords.length >= 2 &&
    coords[0] >= bbox.minLon &&
    coords[0] <= bbox.maxLon &&
    coords[1] >= bbox.minLat &&
    coords[1] <= bbox.maxLat
  );
}

function bboxValidator(bboxString) {
  var parts = String(bboxString).split(",").map(function (value) {
    return parseFloat(value);
  });
  var bbox = {
    minLon: parts[0],
    minLat: parts[1],
    maxLon: parts[2],
    maxLat: parts[3],
  };

  return function (response) {
    return getFeatures(response).every(function (feature) {
      return pointWithinBbox(feature.geometry && feature.geometry.coordinates, bbox);
    });
  };
}

function propertyValidator(field, predicate) {
  return function (response) {
    return getFeatures(response).every(function (feature) {
      var properties = feature.properties || {};
      return predicate(properties[field], properties);
    });
  };
}

function defaultValidator() {
  return true;
}

function offsetValidator(offset, limit) {
  var expectedStart = parseInt(offset, 10) + 1;
  var expectedCount = parseInt(limit, 10);

  return function (response) {
    var features = getFeatures(response);
    if (features.length === 0) {
      return false;
    }

    if (features.length > expectedCount) {
      return false;
    }

    return features.every(function (feature, index) {
      return extractFeatureId(feature) === expectedStart + index;
    });
  };
}

export function getServer() {
  var name = __ENV.SERVER || "honua";
  var server = SERVERS[name];
  if (!server) {
    throw new Error("Unknown server: " + name + ". Use: honua, geoserver, qgis");
  }
  return { name: name, config: server };
}

/**
 * Build a comparable feature request URL for the selected server.
 *
 * @param {Object} params - Query parameters.
 * @param {string} [params.bbox] - Bounding box (minx,miny,maxx,maxy).
 * @param {Object} [params.filterSpec] - Logical filter description.
 * @param {number} [params.limit] - Max features to return.
 * @param {number} [params.offset] - Pagination offset.
 * @returns {Object} Request metadata including URL and validator.
 */
export function buildItemsUrl(params) {
  params = params || {};
  var server = getServer();
  var limit = params.limit || RESULT_LIMIT;
  var filterSpec = normalizeFilterSpec(params.filterSpec || null);
  var validator = defaultValidator;
  var url;

  if (filterSpec && server.config.filterMode === "wfs-fes") {
    url = server.config.baseUrl + "/ows/";
    url += "?MAP=" + encodeURIComponent(server.config.mapPath);
    url += "&SERVICE=WFS";
    url += "&VERSION=1.1.0";
    url += "&REQUEST=GetFeature";
    url += "&TYPENAME=" + encodeURIComponent(COLLECTION);
    url += "&MAXFEATURES=" + limit;
    url += "&OUTPUTFORMAT=" + encodeURIComponent("application/vnd.geo+json");
    url += "&FILTER=" + encodeURIComponent(buildQgisFilterXml(filterSpec));
  } else {
    url = server.config.baseUrl + server.config.itemsPath(COLLECTION);
    url += "?f=json";
    url += "&limit=" + limit;

    if (params.bbox) {
      url += "&bbox=" + params.bbox;
    }

    if (filterSpec && server.config.filterMode === "cql2") {
      url += "&filter=" + encodeURIComponent(buildCql2Filter(filterSpec));
      url += "&filter-lang=cql2-text";
    }

    if (params.offset) {
      url += "&" + (server.config.offsetParam || "offset") + "=" + params.offset;
    }
  }

  if (
    params.offset !== undefined &&
    params.offset !== null &&
    server.config.sortParam
  ) {
    url += "&" + server.config.sortParam + "=" + encodeURIComponent(SORT_BY);
  }

  if (params.bbox) {
    validator = bboxValidator(params.bbox);
  } else if (filterSpec && filterSpec.type === "eq") {
    validator = propertyValidator(filterSpec.field, function (value) {
      return String(value) === String(filterSpec.value);
    });
  } else if (filterSpec && filterSpec.type === "between") {
    validator = propertyValidator(filterSpec.field, function (value) {
      var numeric = parseFloat(value);
      return numeric >= filterSpec.low && numeric <= filterSpec.high;
    });
  } else if (filterSpec && filterSpec.type === "prefix") {
    validator = propertyValidator(filterSpec.field, function (value) {
      return String(value).indexOf(filterSpec.prefix) === 0;
    });
  } else if (params.offset !== undefined && params.offset !== null) {
    validator = offsetValidator(params.offset, limit);
  }

  return {
    url: url,
    name: server.name + ":" + COLLECTION,
    validate: validator,
  };
}

/**
 * Standard response checks for feature-service requests.
 */
export function ogcChecks(request) {
  return {
    "status is 200": function (r) {
      return r.status === 200;
    },
    "response matches request": function (r) {
      return request && request.validate ? request.validate(r) : true;
    },
  };
}

// Dataset categories and hotspots (match data/small/generate.py distributions)
export var CATEGORIES = [
  "park", "building", "road", "bridge", "water",
  "forest", "farm", "commercial", "residential", "industrial",
];

export var HOTSPOTS = [
  { lon: -73.98, lat: 40.75 },  // NYC
  { lon: 2.35, lat: 48.86 },    // Paris
  { lon: 139.69, lat: 35.69 },  // Tokyo
  { lon: -46.63, lat: -23.55 }, // Sao Paulo
  { lon: 151.21, lat: -33.87 }, // Sydney
];

/**
 * Generate a deterministic bounding box centered near a hotspot.
 * @param {number} sizeDeg - Size of the bbox in degrees.
 * @param {number} [salt] - Scenario-specific salt for reproducible variation.
 * @returns {string} "minx,miny,maxx,maxy"
 */
export function randomBbox(sizeDeg, salt) {
  var center = deterministicChoice(HOTSPOTS, salt || 0);
  var half = sizeDeg / 2;
  var jitter = deterministicRange(-half, half, (salt || 0) ^ 0x9e3779b9);
  var minLon = Math.max(-180, center.lon - half + jitter);
  var minLat = Math.max(-90, center.lat - half + jitter);
  var maxLon = Math.min(180, minLon + sizeDeg);
  var maxLat = Math.min(90, minLat + sizeDeg);
  return (
    minLon.toFixed(4) + "," + minLat.toFixed(4) + "," +
    maxLon.toFixed(4) + "," + maxLat.toFixed(4)
  );
}
