// GeoBench: WMS GetMap reprojection benchmarks.
//
// Comparable cross-server raster track:
// - same deterministic hotspot views as the base WMS suite
// - requested in EPSG:3857 to force server-side reprojection
//
// Usage: k6 run --env SERVER=geoserver wms-reprojection.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildMapRequest,
  buildProjectedBbox,
  RASTER_SIZES,
  validateImageResponse,
} from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("raster_reprojection_response_time", true);
var scenarioDuration = __ENV.WMS_REPROJECTION_DURATION || "120s";
var warmupDuration = __ENV.WMS_REPROJECTION_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WMS_REPROJECTION_VUS || "10", 10);
var selectedBboxSizes = (__ENV.WMS_REPROJECTION_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });
var scenarioThresholds = {};

function supportedServerName() {
  var name = (__ENV.SERVER || "geoserver").toLowerCase();
  if (name !== "geoserver" && name !== "qgis" && name !== "honua") {
    throw new Error(
      "WMS reprojection suite currently supports honua, geoserver, and qgis only; got " + name
    );
  }
  return name === "honua" ? "honua_wms" : name;
}

var SERVER_NAME = supportedServerName();
var BBOX_VARIANTS = [
  { id: "small", exec: "smallMap", size: RASTER_SIZES.small, salt: 0x711 },
  { id: "medium", exec: "mediumMap", size: RASTER_SIZES.medium, salt: 0x712 },
  { id: "large", exec: "largeMap", size: RASTER_SIZES.large, salt: 0x713 },
].filter(function (variant) {
  return selectedBboxSizes.indexOf(variant.id) !== -1;
});

if (BBOX_VARIANTS.length === 0) {
  throw new Error("No WMS reprojection scenarios selected");
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
      exec: "warmupWmsReprojection",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  BBOX_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_map"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.exec,
      tags: { bbox_size: variant.id },
      startTime: String(offsetSeconds) + "s",
    };
    offsetSeconds += parseInt(scenarioDuration, 10);
  });

  return scenarios;
}

export var options = {
  scenarios: buildScenarios(),
  thresholds: Object.assign({
    errors: ["rate<0.01"],
  }, scenarioThresholds),
};

function runMap(sizeDeg, salt) {
  var req = buildMapRequest(SERVER_NAME, {
    bbox: buildProjectedBbox(sizeDeg, salt, "EPSG:3857"),
    crs: "EPSG:3857",
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

export function smallMap() {
  runMap(RASTER_SIZES.small, 0x711);
}

export function mediumMap() {
  runMap(RASTER_SIZES.medium, 0x712);
}

export function largeMap() {
  runMap(RASTER_SIZES.large, 0x713);
}

export function warmupWmsReprojection() {
  if (selectedBboxSizes.indexOf("medium") !== -1) {
    mediumMap();
    return;
  }

  if (selectedBboxSizes.indexOf("small") !== -1) {
    smallMap();
    return;
  }

  largeMap();
}
