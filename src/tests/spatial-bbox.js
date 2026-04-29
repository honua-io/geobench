// GeoBench: Spatial bounding box benchmarks (small, medium, large).
//
// Usage: k6 run --env SERVER=honua spatial-bbox.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
import { buildItemsUrl, ogcChecks, randomBbox } from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);
var scenarioDuration = __ENV.SPATIAL_BBOX_DURATION || "120s";
var warmupDuration = __ENV.SPATIAL_BBOX_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.SPATIAL_BBOX_VUS || "10", 10);
var selectedBboxSizes = (__ENV.SPATIAL_BBOX_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

var BBOX_VARIANTS = [
  { id: "small", exec: "smallBbox" },
  { id: "medium", exec: "mediumBbox" },
  { id: "large", exec: "largeBbox" },
].filter(function (variant) {
  return selectedBboxSizes.indexOf(variant.id) !== -1;
});

if (BBOX_VARIANTS.length === 0) {
  throw new Error("No spatial-bbox scenarios selected");
}

var scenarioThresholds = {};
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
      exec: "warmupSpatialBbox",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  BBOX_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_bbox"] = {
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
  discardResponseBodies: true,
  scenarios: buildScenarios(),
  thresholds: Object.assign({
    errors: ["rate<=0"],
  }, scenarioThresholds),
};

// Small: ~0.1 degree (city-scale)
export function smallBbox() {
  var req = buildItemsUrl({ bbox: randomBbox(0.1, 0x401) });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

// Medium: ~5 degrees (country-scale)
export function mediumBbox() {
  var req = buildItemsUrl({ bbox: randomBbox(5.0, 0x402) });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

// Large: ~30 degrees (continental-scale)
export function largeBbox() {
  var req = buildItemsUrl({ bbox: randomBbox(30.0, 0x403) });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function warmupSpatialBbox() {
  BBOX_VARIANTS.forEach(function (variant) {
    if (variant.id === "small") {
      smallBbox();
    } else if (variant.id === "medium") {
      mediumBbox();
    } else if (variant.id === "large") {
      largeBbox();
    }
  });
}
