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
import { buildBbox, buildGetFeatureInfoRequest, RASTER_SIZES } from "./raster-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wms_getfeatureinfo_response_time", true);
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
      "WMS GetFeatureInfo suite currently supports honua, geoserver, and qgis only; got " + name
    );
  }
  return name === "honua" ? "honua_wms" : name;
}

var SERVER_NAME = supportedServerName();

export var options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "warmupWmsGetFeatureInfo",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    small_info: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "smallGetFeatureInfo",
      tags: { bbox_size: "small" },
      startTime: "60s",
    },
    medium_info: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "mediumGetFeatureInfo",
      tags: { bbox_size: "medium" },
      startTime: "190s",
    },
    large_info: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "largeGetFeatureInfo",
      tags: { bbox_size: "large" },
      startTime: "320s",
    },
  },
  thresholds: Object.assign({
    errors: ["rate<0.01"],
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
