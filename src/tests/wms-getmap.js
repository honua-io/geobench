// GeoBench: WMS GetMap raster benchmarks.
//
// Common track for servers that expose standards-based WMS.
// Usage: k6 run --env SERVER=geoserver wms-getmap.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { buildBbox, buildMapRequest, RASTER_SIZES, validateImageResponse } from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("raster_response_time", true);
var scenarioDuration = __ENV.WMS_GETMAP_DURATION || "120s";
var warmupDuration = __ENV.WMS_GETMAP_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WMS_GETMAP_VUS || "10", 10);
var scenarioThresholds = {
  "http_req_duration{bbox_size:small}": ["max>=0"],
  "http_req_duration{bbox_size:medium}": ["max>=0"],
  "http_req_duration{bbox_size:large}": ["max>=0"],
  "http_reqs{bbox_size:small}": ["count>=0"],
  "http_reqs{bbox_size:medium}": ["count>=0"],
  "http_reqs{bbox_size:large}": ["count>=0"],
};

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
  var offsetSeconds = parseInt(warmupDuration, 10);
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWmsGetMap",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    small_map: {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: "smallMap",
      tags: { bbox_size: "small" },
      startTime: String(offsetSeconds) + "s",
    },
  };

  offsetSeconds += parseInt(scenarioDuration, 10);
  scenarios.medium_map = {
    executor: "constant-vus",
    vus: scenarioVus,
    duration: scenarioDuration,
    exec: "mediumMap",
    tags: { bbox_size: "medium" },
    startTime: String(offsetSeconds) + "s",
  };

  offsetSeconds += parseInt(scenarioDuration, 10);
  scenarios.large_map = {
    executor: "constant-vus",
    vus: scenarioVus,
    duration: scenarioDuration,
    exec: "largeMap",
    tags: { bbox_size: "large" },
    startTime: String(offsetSeconds) + "s",
  };

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

export function smallMap() {
  runMap(RASTER_SIZES.small, 0x701);
}

export function mediumMap() {
  runMap(RASTER_SIZES.medium, 0x702);
}

export function largeMap() {
  runMap(RASTER_SIZES.large, 0x703);
}

export function warmupWmsGetMap() {
  smallMap();
  mediumMap();
  largeMap();
}
