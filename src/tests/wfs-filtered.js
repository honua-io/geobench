// GeoBench: standards-based WFS filtered-query benchmarks.
//
// Shared profile:
// - Honua WFS 2.0.0 + FES 2.0 KVP FILTER
// - GeoServer WFS 2.0.0 + FES 2.0 KVP FILTER
//
// QGIS is intentionally excluded from this suite because the local benchmark
// image is pinned to WFS 1.1.0 and needs a separate equivalent filter profile.
//
// Usage: k6 run --env SERVER=honua wfs-filtered.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
import { deterministicChoice, deterministicInt, deterministicRange } from "./deterministic.js";
import { CATEGORIES } from "./helpers.js";
import {
  buildFilteredGetFeatureRequest,
  wfsChecks,
  wfsFilteredQueriesSupported,
} from "./wfs-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wfs_filtered_response_time", true);
var scenarioDuration = __ENV.WFS_FILTERED_DURATION || "120s";
var warmupDuration = __ENV.WFS_FILTERED_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WFS_FILTERED_VUS || "10", 10);
var selectedQueryTypes = (__ENV.WFS_FILTERED_SCENARIOS || "equality,range,like")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

if (!wfsFilteredQueriesSupported()) {
  throw new Error(
    "WFS filtered suite currently supports honua and geoserver only; got " +
    (__ENV.SERVER || "unset")
  );
}

var FILTER_VARIANTS = [
  { id: "equality", exec: "equalityFilter" },
  { id: "range", exec: "rangeFilter" },
  { id: "like", exec: "likeFilter" },
].filter(function (variant) {
  return selectedQueryTypes.indexOf(variant.id) !== -1;
});

if (FILTER_VARIANTS.length === 0) {
  throw new Error("No WFS filtered scenarios selected");
}

var scenarioThresholds = {};
FILTER_VARIANTS.forEach(function (variant) {
  scenarioThresholds["http_req_duration{query_type:" + variant.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{query_type:" + variant.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWfsFiltered",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  FILTER_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_filter"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.exec,
      tags: { query_type: variant.id },
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

function runFilteredQuery(filterSpec) {
  var req = buildFilteredGetFeatureRequest({ filterSpec: filterSpec });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, wfsChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function equalityFilter() {
  runFilteredQuery({
    type: "eq",
    field: "category",
    value: deterministicChoice(CATEGORIES, 0xa01),
  });
}

export function rangeFilter() {
  var low = deterministicRange(-20, 40, 0xa02);
  runFilteredQuery({
    type: "between",
    field: "temperature",
    low: low,
    high: low + 10,
  });
}

export function likeFilter() {
  runFilteredQuery({
    type: "prefix",
    field: "feature_name",
    prefix: "feature_" + deterministicInt(1000, 0xa03),
  });
}

export function warmupWfsFiltered() {
  FILTER_VARIANTS.forEach(function (variant) {
    if (variant.id === "equality") {
      equalityFilter();
    } else if (variant.id === "range") {
      rangeFilter();
    } else if (variant.id === "like") {
      likeFilter();
    }
  });
}
