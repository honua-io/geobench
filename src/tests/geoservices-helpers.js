// GeoBench: shared helpers for GeoServices REST benchmarks.

import { randomBbox } from "./helpers.js";

var SERVERS = {
  honua: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    serviceId: __ENV.HONUA_GSR_SERVICE_ID || __ENV.HONUA_SERVICE_NAME || "default",
    layerId: __ENV.HONUA_GSR_LAYER_ID || __ENV.HONUA_COLLECTION_ID || "1",
    pathPrefix: "/rest/services/",
  },
  geoserver: {
    baseUrl: __ENV.GEOSERVER_GSR_URL || (__ENV.GEOSERVER_URL || "http://geoserver:8080"),
    serviceId: __ENV.GEOSERVER_GSR_SERVICE || "geobench",
    layerId: __ENV.GEOSERVER_GSR_LAYER_ID || "0",
    pathPrefix: "/geoserver/gsr/services/",
  },
};

export var GEOSERVICES_QUERY_SIZES = {
  small: 0.25,
  medium: 0.5,
  large: 1.0,
};

function getServer() {
  var name = (__ENV.SERVER || "honua").toLowerCase();
  var server = SERVERS[name];
  if (!server) {
    throw new Error("Unknown GeoServices server: " + name + ". Use: honua or geoserver");
  }
  return { name: name, config: server };
}

function parsePayload(response) {
  try {
    return response.json();
  } catch (err) {
    return null;
  }
}

function getFeatures(response) {
  var payload = parsePayload(response);
  return payload && payload.features ? payload.features : [];
}

function featurePresenceValidator() {
  return function (response) {
    return getFeatures(response).length > 0;
  };
}

function pointWithinBbox(geometry, bbox) {
  return (
    geometry &&
    typeof geometry.x === "number" &&
    typeof geometry.y === "number" &&
    geometry.x >= bbox.minLon &&
    geometry.x <= bbox.maxLon &&
    geometry.y >= bbox.minLat &&
    geometry.y <= bbox.maxLat
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
    var features = getFeatures(response);
    if (features.length === 0) {
      return false;
    }
    return features.every(function (feature) {
      return pointWithinBbox(feature.geometry, bbox);
    });
  };
}

export function randomGeoservicesBbox(sizeDeg, salt) {
  return randomBbox(sizeDeg, salt);
}

export function buildGeoservicesQueryRequest(params) {
  params = params || {};

  var server = getServer();
  var outFields = params.outFields || "*";
  var returnGeometry = params.returnGeometry !== false;
  var outSr = params.outSr || "4326";
  var url =
    server.config.baseUrl +
    server.config.pathPrefix +
    encodeURIComponent(server.config.serviceId) +
    "/FeatureServer/" +
    encodeURIComponent(server.config.layerId) +
    "/query";

  url += "?f=json";
  url += "&where=" + encodeURIComponent("1=1");
  url += "&outFields=" + encodeURIComponent(outFields);
  url += "&returnGeometry=" + encodeURIComponent(returnGeometry ? "true" : "false");
  url += "&outSR=" + encodeURIComponent(outSr);

  if (!params.bbox) {
    throw new Error("GeoServices query benchmark requires a bbox");
  }

  url += "&geometry=" + encodeURIComponent(params.bbox);
  url += "&geometryType=esriGeometryEnvelope";
  url += "&inSR=4326";
  url += "&spatialRel=esriSpatialRelIntersects";

  return {
    url: url,
    name: server.name + ":feature-query" + (params.nameSuffix ? ":" + params.nameSuffix : ""),
    validate: returnGeometry ? bboxValidator(params.bbox) : featurePresenceValidator(),
  };
}

export function geoservicesChecks(request) {
  return {
    "status is 200": function (response) {
      return response.status === 200;
    },
    "content-type is json": function (response) {
      var contentType = response.headers["Content-Type"] || response.headers["content-type"] || "";
      return contentType.toLowerCase().indexOf("json") !== -1;
    },
    "response matches request": function (response) {
      return request && request.validate ? request.validate(response) : true;
    },
  };
}

function identifyPayloadHasResults(response) {
  var payload = parsePayload(response);
  if (!payload || typeof payload !== "object") {
    return false;
  }

  if (payload.error) {
    return false;
  }

  if (payload.results !== undefined) {
    return true;
  }

  if (payload.layers !== undefined) {
    return Array.isArray(payload.layers);
  }

  if (payload.features !== undefined) {
    return Array.isArray(payload.features);
  }

  return false;
}

export function buildGeoservicesIdentifyRequest(params) {
  params = params || {};
  var server = getServer();

  var mapExtent = params.mapExtent || "";
  if (!mapExtent) {
    throw new Error("Identify request requires mapExtent");
  }

  var geometry = params.geometry || "";
  if (!geometry) {
    throw new Error("Identify request requires geometry");
  }

  var url =
    server.config.baseUrl +
    server.config.pathPrefix +
    encodeURIComponent(server.config.serviceId) +
    "/MapServer/identify";

  url += "?f=json";
  url += "&geometry=" + encodeURIComponent(geometry);
  url += "&geometryType=" + encodeURIComponent(params.geometryType || "esriGeometryPoint");
  url += "&sr=" + encodeURIComponent(params.srid || "4326");
  url += "&mapExtent=" + encodeURIComponent(mapExtent);
  url += "&imageDisplay=" + encodeURIComponent(params.imageWidth || "256") + "," +
    encodeURIComponent(params.imageHeight || "256") + "," +
    encodeURIComponent(params.dpi || "96");
  url += "&tolerance=" + encodeURIComponent(params.tolerance || 2);
  url += "&returnGeometry=" + encodeURIComponent(params.returnGeometry === false ? "false" : "true");
  url += "&layers=" + encodeURIComponent(params.layers || ("all:" + server.config.layerId));

  return {
    url: url,
    name: server.name + ":identify",
    validate: identifyPayloadHasResults,
  };
}

export function geoservicesIdentifyChecks(request) {
  return {
    "status is 200": function (response) {
      return response.status === 200;
    },
    "content-type is json": function (response) {
      var contentType = response.headers["Content-Type"] || response.headers["content-type"] || "";
      return contentType.toLowerCase().indexOf("json") !== -1;
    },
    "response includes identify payload": function (response) {
      return request && request.validate ? request.validate(response) : false;
    },
  };
}
