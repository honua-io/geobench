// GeoBench: WMS GetFeatureInfo benchmarks.
//
// Secondary raster-equivalent track:
// - compares WMS GetFeatureInfo around deterministic hotspots
// - small / medium / large hot regions
//
// Usage: k6 run --env SERVER=geoserver wms-getfeatureinfo.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
import { buildBbox, buildGetFeatureInfoRequest, RASTER_SIZES } from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wms_getfeatureinfo_response_time", true);
var scenarioDuration = __ENV.WMS_GETFEATUREINFO_DURATION || "120s";
var warmupDuration = __ENV.WMS_GETFEATUREINFO_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WMS_GETFEATUREINFO_VUS || "10", 10);
var selectedBboxSizes = (__ENV.WMS_GETFEATUREINFO_SCENARIOS || "small,medium,large")
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
      "WMS GetFeatureInfo suite currently supports honua, geoserver, and qgis only; got " + name
    );
  }
  return name === "honua" ? "honua_wms" : name;
}

var SERVER_NAME = supportedServerName();
var BBOX_VARIANTS = [
  { id: "small", exec: "smallGetFeatureInfo", size: RASTER_SIZES.small, salt: 0x901 },
  { id: "medium", exec: "mediumGetFeatureInfo", size: RASTER_SIZES.medium, salt: 0x902 },
  { id: "large", exec: "largeGetFeatureInfo", size: RASTER_SIZES.large, salt: 0x903 },
].filter(function (variant) {
  return selectedBboxSizes.indexOf(variant.id) !== -1;
});

if (BBOX_VARIANTS.length === 0) {
  throw new Error("No WMS GetFeatureInfo scenarios selected");
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
      exec: "warmupWmsGetFeatureInfo",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  BBOX_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_info"] = {
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

function runGetFeatureInfo(sizeDeg, salt) {
  var req = buildGetFeatureInfoRequest(SERVER_NAME, {
    bbox: buildBbox(sizeDeg, salt),
    width: 256,
    height: 256,
    crs: "CRS:84",
    infoFormat: "application/json",
    i: 128,
    j: 128,
    featureCount: 10,
  });

  var res = http.get(req.url, { tags: { name: req.name } });
  var ok = check(res, {
    "status is 200": function () {
      return res.status === 200;
    },
    "body is present": function () {
      return (res.body || "").length > 0;
    },
  });

  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function smallGetFeatureInfo() {
  runGetFeatureInfo(RASTER_SIZES.small, 0x901);
}

export function mediumGetFeatureInfo() {
  runGetFeatureInfo(RASTER_SIZES.medium, 0x902);
}

export function largeGetFeatureInfo() {
  runGetFeatureInfo(RASTER_SIZES.large, 0x903);
}

export function warmupWmsGetFeatureInfo() {
  smallGetFeatureInfo();
  mediumGetFeatureInfo();
  largeGetFeatureInfo();
}
