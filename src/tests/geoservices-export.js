// GeoBench: GeoServices REST raster/export benchmark.
//
// Honua-native only. GeoServer GSR does not support MapServer/export.
// Usage: k6 run --env SERVER=honua geoservices-export.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
import { buildBbox, buildMapRequest, RASTER_SIZES, validateImageResponse } from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("raster_response_time", true);
var scenarioDuration = __ENV.GEOSERVICES_EXPORT_DURATION || "120s";
var warmupDuration = __ENV.GEOSERVICES_EXPORT_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.GEOSERVICES_EXPORT_VUS || "10", 10);
var selectedBboxSizes = (__ENV.GEOSERVICES_EXPORT_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });
var scenarioThresholds = {};

function selectedServer() {
  var name = (__ENV.SERVER || "honua").toLowerCase();
  if (name !== "honua") {
    throw new Error("GeoServices export suite currently supports honua only; got " + name);
  }
  return "honua";
}

var SERVER_NAME = selectedServer();
var BBOX_VARIANTS = [
  { id: "small", exec: "smallExport" },
  { id: "medium", exec: "mediumExport" },
  { id: "large", exec: "largeExport" },
].filter(function (variant) {
  return selectedBboxSizes.indexOf(variant.id) !== -1;
});

if (BBOX_VARIANTS.length === 0) {
  throw new Error("No GeoServices export scenarios selected");
}

BBOX_VARIANTS.forEach(function (variant) {
  scenarioThresholds["http_req_duration{bbox_size:" + variant.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{bbox_size:" + variant.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupGeoservicesExport",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  BBOX_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_export"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.exec,
      tags: { bbox_size: variant.id },
      startTime: String(offsetSeconds) + "s",
    };
    offsetSeconds += durationToSeconds(scenarioDuration);
  });

  return scenarios;
}

export var options = {
  scenarios: buildScenarios(),
  thresholds: Object.assign({
    errors: ["rate<=0"],
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
  BBOX_VARIANTS.forEach(function (variant) {
    if (variant.id === "small") {
      smallExport();
    } else if (variant.id === "medium") {
      mediumExport();
    } else if (variant.id === "large") {
      largeExport();
    }
  });
}
