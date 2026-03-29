// GeoBench: GeoServices REST FeatureServer/query benchmarks.
//
// Comparable native track:
// - bbox-restricted read only
//
// Attribute filters and record-count pagination are intentionally omitted
// because GeoServer GSR does not support them on this surface.
//
// Usage: k6 run --env SERVER=honua geoservices-query.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildGeoservicesQueryRequest,
  GEOSERVICES_QUERY_SIZES,
  geoservicesChecks,
  randomGeoservicesBbox,
} from "./geoservices-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("geoservices_query_response_time", true);
var scenarioDuration = __ENV.GEOSERVICES_QUERY_DURATION || "120s";
var warmupDuration = __ENV.GEOSERVICES_QUERY_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.GEOSERVICES_QUERY_VUS || "10", 10);
var selectedBboxSizes = (__ENV.GEOSERVICES_QUERY_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

function parseSalt(envName, fallback) {
  var raw = __ENV[envName];
  if (!raw) {
    return fallback;
  }

  var parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    throw new Error("Invalid salt for " + envName + ": " + raw);
  }

  return parsed;
}

var BBOX_SALTS = {
  small: parseSalt("GEOSERVICES_QUERY_SALT_SMALL", 0x901),
  medium: parseSalt("GEOSERVICES_QUERY_SALT_MEDIUM", 0x902),
  large: parseSalt("GEOSERVICES_QUERY_SALT_LARGE", 0x903),
};

var BBOX_VARIANTS = [
  { id: "small", exec: "smallBbox" },
  { id: "medium", exec: "mediumBbox" },
  { id: "large", exec: "largeBbox" },
].filter(function (variant) {
  return selectedBboxSizes.indexOf(variant.id) !== -1;
});

if (BBOX_VARIANTS.length === 0) {
  throw new Error("No GeoServices query scenarios selected");
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
      exec: "warmupGeoservicesQuery",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  BBOX_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_bbox"] = {
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
  discardResponseBodies: true,
  scenarios: buildScenarios(),
  thresholds: Object.assign({
    errors: ["rate<0.01"],
  }, scenarioThresholds),
};

function runQuery(bbox) {
  var req = buildGeoservicesQueryRequest({ bbox: bbox });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, geoservicesChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function smallBbox() {
  runQuery(randomGeoservicesBbox(GEOSERVICES_QUERY_SIZES.small, BBOX_SALTS.small));
}

export function mediumBbox() {
  runQuery(randomGeoservicesBbox(GEOSERVICES_QUERY_SIZES.medium, BBOX_SALTS.medium));
}

export function largeBbox() {
  runQuery(randomGeoservicesBbox(GEOSERVICES_QUERY_SIZES.large, BBOX_SALTS.large));
}

export function warmupGeoservicesQuery() {
  if (selectedBboxSizes.indexOf("medium") !== -1) {
    mediumBbox();
    return;
  }

  if (selectedBboxSizes.indexOf("small") !== -1) {
    smallBbox();
    return;
  }

  largeBbox();
}
