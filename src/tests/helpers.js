// GeoBench: shared k6 helpers for OGC API Features benchmarking.

// Server registry — each entry defines how to reach the OGC API Features endpoint.
var SERVERS = {
  honua: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    itemsPath: function (collection) {
      return "/ogc/features/collections/" + collection + "/items";
    },
    supportsCql2: true,
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
    supportsCql2: true,
  },
  qgis: {
    baseUrl: __ENV.QGIS_URL || "http://qgis-server:80",
    itemsPath: function (collection) {
      return "/wfs3/collections/" + collection + "/items";
    },
    supportsCql2: false,
  },
};

export var COLLECTION = __ENV.COLLECTION || "bench_points";
export var RESULT_LIMIT = parseInt(__ENV.RESULT_LIMIT || "100");

export function getServer() {
  var name = __ENV.SERVER || "honua";
  var server = SERVERS[name];
  if (!server) {
    throw new Error("Unknown server: " + name + ". Use: honua, geoserver, qgis");
  }
  return { name: name, config: server };
}

/**
 * Build an OGC API Features items URL.
 *
 * @param {Object} params - Query parameters.
 * @param {string} [params.bbox] - Bounding box (minx,miny,maxx,maxy).
 * @param {string} [params.filter] - CQL2 filter expression.
 * @param {number} [params.limit] - Max features to return.
 * @param {number} [params.offset] - Pagination offset.
 * @returns {string} Full URL.
 */
export function buildItemsUrl(params) {
  params = params || {};
  var server = getServer();
  var url =
    server.config.baseUrl + server.config.itemsPath(COLLECTION) + "?f=json";

  url += "&limit=" + (params.limit || RESULT_LIMIT);

  if (params.bbox) {
    url += "&bbox=" + params.bbox;
  }

  if (params.filter && server.config.supportsCql2) {
    url += "&filter=" + encodeURIComponent(params.filter);
    url += "&filter-lang=cql2-text";
  }

  if (params.offset) {
    url += "&offset=" + params.offset;
  }

  return url;
}

/**
 * Standard response checks for OGC API Features.
 */
export function ogcChecks() {
  return {
    "status is 200": function (r) {
      return r.status === 200;
    },
    "response has features": function (r) {
      return r.body && r.body.length > 0;
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
 * Generate a random bounding box centered near a hotspot.
 * @param {number} sizeDeg - Size of the bbox in degrees.
 * @returns {string} "minx,miny,maxx,maxy"
 */
export function randomBbox(sizeDeg) {
  var center = HOTSPOTS[Math.floor(Math.random() * HOTSPOTS.length)];
  var half = sizeDeg / 2;
  var jitter = (Math.random() - 0.5) * sizeDeg;
  var minLon = Math.max(-180, center.lon - half + jitter);
  var minLat = Math.max(-90, center.lat - half + jitter);
  var maxLon = Math.min(180, minLon + sizeDeg);
  var maxLat = Math.min(90, minLat + sizeDeg);
  return (
    minLon.toFixed(4) + "," + minLat.toFixed(4) + "," +
    maxLon.toFixed(4) + "," + maxLat.toFixed(4)
  );
}
