// GeoBench: standards-based WFS GetFeature benchmarks.
//
// Comparable track:
// - base collection read
// - bbox-restricted read
//
// Filtered WFS queries are intentionally omitted from this suite because the
// local Honua, GeoServer, and QGIS servers do not share one clean, common
// standards-based filter syntax in this environment.
//
// Usage: k6 run --env SERVER=honua wfs-getfeature.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildGetFeatureRequest,
  randomWfsBbox,
  wfsChecks,
  WFS_BBOX_SIZES,
} from "./wfs-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wfs_response_time", true);
var scenarioDuration = __ENV.WFS_GETFEATURE_DURATION || "120s";
var warmupDuration = __ENV.WFS_GETFEATURE_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WFS_GETFEATURE_VUS || "10", 10);
var selectedScenarios = (__ENV.WFS_GETFEATURE_SCENARIOS || "base,small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

var VARIANTS = [
  { id: "base", exec: "baseRead", tagName: "query_type", tagValue: "base" },
  { id: "small", exec: "smallBbox", tagName: "bbox_size", tagValue: "small" },
  { id: "medium", exec: "mediumBbox", tagName: "bbox_size", tagValue: "medium" },
  { id: "large", exec: "largeBbox", tagName: "bbox_size", tagValue: "large" },
].filter(function (variant) {
  return selectedScenarios.indexOf(variant.id) !== -1;
});

if (VARIANTS.length === 0) {
  throw new Error("No WFS GetFeature scenarios selected");
}

var scenarioThresholds = {};
VARIANTS.forEach(function (variant) {
  scenarioThresholds["http_req_duration{" + variant.tagName + ":" + variant.tagValue + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{" + variant.tagName + ":" + variant.tagValue + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWfsGetFeature",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  VARIANTS.forEach(function (variant) {
    var tags = {};
    tags[variant.tagName] = variant.tagValue;
    scenarios[variant.id + "_read"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.exec,
      tags: tags,
      startTime: String(offsetSeconds) + "s",
    };
    offsetSeconds += parseInt(scenarioDuration, 10);
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

function runGetFeature(bbox) {
  var req = buildGetFeatureRequest({
    bbox: bbox,
  });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, wfsChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function baseRead() {
  var req = buildGetFeatureRequest();
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, wfsChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function smallBbox() {
  runGetFeature(randomWfsBbox(WFS_BBOX_SIZES.small, 0x601));
}

export function mediumBbox() {
  runGetFeature(randomWfsBbox(WFS_BBOX_SIZES.medium, 0x602));
}

export function largeBbox() {
  runGetFeature(randomWfsBbox(WFS_BBOX_SIZES.large, 0x603));
}

export function warmupWfsGetFeature() {
  VARIANTS.forEach(function (variant) {
    if (variant.id === "base") {
      baseRead();
    } else if (variant.id === "small") {
      smallBbox();
    } else if (variant.id === "medium") {
      mediumBbox();
    } else if (variant.id === "large") {
      largeBbox();
    }
  });
}
