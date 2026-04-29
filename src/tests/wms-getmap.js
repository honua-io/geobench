// GeoBench: WMS GetMap raster benchmarks.
//
// Common track for servers that expose standards-based WMS.
// Usage: k6 run --env SERVER=geoserver wms-getmap.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
import { buildBbox, buildMapRequest, RASTER_SIZES, validateImageResponse } from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("raster_response_time", true);
var scenarioDuration = __ENV.WMS_GETMAP_DURATION || "120s";
var warmupDuration = __ENV.WMS_GETMAP_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WMS_GETMAP_VUS || "10", 10);
var logFailures = (__ENV.LOG_FAILURES || "").toLowerCase() === "1";
var selectedBboxSizes = (__ENV.WMS_GETMAP_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

var MAP_VARIANTS = [
  { id: "small", exec: "smallMap" },
  { id: "medium", exec: "mediumMap" },
  { id: "large", exec: "largeMap" },
].filter(function (variant) {
  return selectedBboxSizes.indexOf(variant.id) !== -1;
});

if (MAP_VARIANTS.length === 0) {
  throw new Error("No WMS GetMap scenarios selected");
}

var scenarioThresholds = {};
MAP_VARIANTS.forEach(function (variant) {
  scenarioThresholds["errors{bbox_size:" + variant.id + "}"] = ["rate<=0"];
  scenarioThresholds["http_req_duration{bbox_size:" + variant.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{bbox_size:" + variant.id + "}"] = ["count>=0"];
});

function supportedServerName() {
  var name = (__ENV.SERVER || "geoserver").toLowerCase();
  if (name !== "geoserver" && name !== "qgis" && name !== "honua") {
    throw new Error(
      "WMS GetMap suite currently supports honua, geoserver, and qgis only; got " + name
    );
  }
  return name === "honua" ? "honua_wms" : name;
}

var SERVER_NAME = supportedServerName();

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWmsGetMap",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  MAP_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_map"] = {
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

function runMap(sizeDeg, salt, bboxSize) {
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

  if (!ok && logFailures) {
    var contentType = res.headers["Content-Type"] || res.headers["content-type"] || "";
    var bodySize = res.body && res.body.byteLength !== undefined
      ? res.body.byteLength
      : (res.body ? String(res.body).length : 0);
    console.error(JSON.stringify({
      test: "wms-getmap",
      bbox_size: bboxSize,
      status: res.status,
      error: res.error || "",
      error_code: res.error_code || 0,
      content_type: contentType,
      body_bytes: bodySize,
      duration_ms: res.timings.duration,
      url: req.url,
    }));
  }

  errorRate.add(!ok, { bbox_size: bboxSize });
  responseTime.add(res.timings.duration, { bbox_size: bboxSize });
}

export function smallMap() {
  runMap(RASTER_SIZES.small, 0x701, "small");
}

export function mediumMap() {
  runMap(RASTER_SIZES.medium, 0x702, "medium");
}

export function largeMap() {
  runMap(RASTER_SIZES.large, 0x703, "large");
}

export function warmupWmsGetMap() {
  MAP_VARIANTS.forEach(function (variant) {
    if (variant.id === "small") {
      smallMap();
    } else if (variant.id === "medium") {
      mediumMap();
    } else if (variant.id === "large") {
      largeMap();
    }
  });
}
