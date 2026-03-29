// GeoBench: shared helpers for raster/map benchmarks.

import { randomBbox } from "./helpers.js";

var PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

var SERVERS = {
  geoserver: {
    baseUrl: __ENV.GEOSERVER_URL || "http://geoserver:8080",
    layer: __ENV.GEOSERVER_WMS_LAYER || "geobench:bench_points",
    path: "/geoserver/wms",
    kind: "wms",
  },
  qgis: {
    baseUrl: __ENV.QGIS_URL || "http://qgis-server:80",
    layer: __ENV.QGIS_WMS_LAYER || "bench_points",
    path: "/ows/",
    mapPath: __ENV.QGIS_MAP_PATH || "/etc/qgisserver/geobench.qgs",
    kind: "wms",
  },
  honua: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    path: "/rest/services/default/MapServer/export",
    kind: "export",
  },
  honua_wms: {
    baseUrl: __ENV.HONUA_URL || "http://honua:8080",
    layer: __ENV.HONUA_WMS_LAYER || "bench_points",
    path: __ENV.HONUA_WMS_PATH || "/ogc/services/default/wms",
    kind: "wms",
  },
};

export var RASTER_SIZES = {
  small: 0.1,
  medium: 5.0,
  large: 30.0,
};

export function getRasterServer(name) {
  var server = SERVERS[name];
  if (!server) {
    throw new Error("Unknown raster server: " + name);
  }
  return { name: name, config: server };
}

export function toBytes(body) {
  if (!body) {
    return new Uint8Array(0);
  }

  if (typeof body === "string") {
    var bytes = new Uint8Array(body.length);
    for (var i = 0; i < body.length; i++) {
      bytes[i] = body.charCodeAt(i) & 0xff;
    }
    return bytes;
  }

  if (body instanceof ArrayBuffer) {
    return new Uint8Array(body);
  }

  if (body.byteLength !== undefined) {
    return new Uint8Array(body);
  }

  return new Uint8Array(0);
}

export function parsePngDimensions(body) {
  var bytes = toBytes(body);
  if (bytes.length < 24) {
    return null;
  }

  for (var i = 0; i < PNG_SIGNATURE.length; i++) {
    if (bytes[i] !== PNG_SIGNATURE[i]) {
      return null;
    }
  }

  if (
    bytes[12] !== 0x49 ||
    bytes[13] !== 0x48 ||
    bytes[14] !== 0x44 ||
    bytes[15] !== 0x52
  ) {
    return null;
  }

  var width =
    (bytes[16] << 24) |
    (bytes[17] << 16) |
    (bytes[18] << 8) |
    bytes[19];
  var height =
    (bytes[20] << 24) |
    (bytes[21] << 16) |
    (bytes[22] << 8) |
    bytes[23];

  return {
    width: width >>> 0,
    height: height >>> 0,
  };
}

export function buildBbox(sizeDeg, salt) {
  return randomBbox(sizeDeg, salt);
}

export function validateImageResponse(response, expectedSize) {
  var contentType = (response.headers["Content-Type"] || response.headers["content-type"] || "")
    .toLowerCase();
  var bodyBytes = toBytes(response.body);
  var dimensions = parsePngDimensions(bodyBytes);

  return {
    ok:
      response.status === 200 &&
      contentType.indexOf("image/png") !== -1 &&
      bodyBytes.length > 32 &&
      dimensions !== null &&
      (!expectedSize || (
        dimensions.width === expectedSize.width &&
        dimensions.height === expectedSize.height
      )),
    details: {
      contentType: contentType,
      bodyBytes: bodyBytes.length,
      dimensions: dimensions,
    },
  };
}

export function buildMapRequest(serverName, params) {
  params = params || {};
  var server = getRasterServer(serverName);

  if (server.config.kind === "wms") {
    var url = server.config.baseUrl + server.config.path;
    if (server.config.mapPath) {
      url += "?MAP=" + encodeURIComponent(server.config.mapPath);
      url += "&SERVICE=WMS";
    } else {
      url += "?SERVICE=WMS";
    }
    url += "&VERSION=1.3.0";
    url += "&REQUEST=GetMap";
    url += "&LAYERS=" + encodeURIComponent(server.config.layer);
    url += "&STYLES=";
    url += "&CRS=CRS:84";
    url += "&BBOX=" + params.bbox;
    url += "&WIDTH=" + params.width;
    url += "&HEIGHT=" + params.height;
    url += "&FORMAT=image/png";
    url += "&TRANSPARENT=true";
    return {
      url: url,
      name: server.name + ":getmap",
      expectedSize: { width: params.width, height: params.height },
    };
  }

  if (server.config.kind === "export") {
    var exportUrl = server.config.baseUrl + server.config.path;
    exportUrl += "?bbox=" + params.bbox;
    exportUrl += "&bboxSR=4326";
    exportUrl += "&imageSR=4326";
    exportUrl += "&size=" + params.width + "," + params.height;
    exportUrl += "&format=png";
    exportUrl += "&transparent=true";
    exportUrl += "&f=image";
    return {
      url: exportUrl,
      name: server.name + ":export",
      expectedSize: { width: params.width, height: params.height },
    };
  }

  throw new Error("Unsupported raster server kind: " + server.config.kind);
}

export function buildQgisMapRequest(bbox, width, height) {
  return buildMapRequest("qgis", {
    bbox: bbox,
    width: width,
    height: height,
  });
}
