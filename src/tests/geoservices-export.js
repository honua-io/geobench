// GeoBench: GeoServices REST raster/export benchmark.
//
// Honua-native only. GeoServer GSR does not support MapServer/export.
// Usage: k6 run --env SERVER=honua geoservices-export.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { buildBbox, buildMapRequest, RASTER_SIZES, validateImageResponse } from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("raster_response_time", true);
var scenarioThresholds = {
  "http_req_duration{bbox_size:small}": ["max>=0"],
  "http_req_duration{bbox_size:medium}": ["max>=0"],
  "http_req_duration{bbox_size:large}": ["max>=0"],
  "http_reqs{bbox_size:small}": ["count>=0"],
  "http_reqs{bbox_size:medium}": ["count>=0"],
  "http_reqs{bbox_size:large}": ["count>=0"],
};

function selectedServer() {
  var name = (__ENV.SERVER || "honua").toLowerCase();
  if (name !== "honua") {
    throw new Error("GeoServices export suite currently supports honua only; got " + name);
  }
  return "honua";
}

var SERVER_NAME = selectedServer();

export var options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "warmupGeoservicesExport",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    small_export: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "smallExport",
      tags: { bbox_size: "small" },
      startTime: "60s",
    },
    medium_export: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "mediumExport",
      tags: { bbox_size: "medium" },
      startTime: "190s",
    },
    large_export: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "largeExport",
      tags: { bbox_size: "large" },
      startTime: "320s",
    },
  },
  thresholds: Object.assign({
    errors: ["rate<0.01"],
  }, scenarioThresholds),
};

function runExport(sizeDeg, salt) {
  var req = buildMapRequest(SERVER_NAME, {
    bbox: buildBbox(sizeDeg, salt),
    width: 256,
    height: 256,
  });

  var res = http.get(req.url, {
    tags: { name: req.name },
    responseType: "binary",
  });
  var validation = validateImageResponse(res, req.expectedSize);
  var ok = check(res, {
    "status is 200": function (r) {
      return r.status === 200;
    },
    "content-type is png": function () {
      return validation.details.contentType.indexOf("image/png") !== -1;
    },
    "body looks like png": function () {
      return validation.ok;
    },
  });

  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function smallExport() {
  runExport(RASTER_SIZES.small, 0x801);
}

export function mediumExport() {
  runExport(RASTER_SIZES.medium, 0x802);
}

export function largeExport() {
  runExport(RASTER_SIZES.large, 0x803);
}

export function warmupGeoservicesExport() {
  smallExport();
  mediumExport();
  largeExport();
}
