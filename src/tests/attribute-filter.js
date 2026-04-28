// GeoBench: Attribute filter benchmarks (equality, range, LIKE).
//
// Usage: k6 run --env SERVER=honua attribute-filter.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { deterministicChoice, deterministicInt, deterministicRange } from "./deterministic.js";
import { buildItemsUrl, ogcChecks, CATEGORIES } from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);
var scenarioDuration = __ENV.ATTRIBUTE_FILTER_DURATION || "120s";
var warmupDuration = __ENV.ATTRIBUTE_FILTER_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.ATTRIBUTE_FILTER_VUS || "10", 10);
var selectedQueryTypes = (__ENV.ATTRIBUTE_FILTER_SCENARIOS || "equality,range,like")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

var FILTER_VARIANTS = [
  { id: "equality", exec: "equalityFilter" },
  { id: "range", exec: "rangeFilter" },
  { id: "like", exec: "likeFilter" },
].filter(function (variant) {
  return selectedQueryTypes.indexOf(variant.id) !== -1;
});

if (FILTER_VARIANTS.length === 0) {
  throw new Error("No attribute-filter scenarios selected");
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
      exec: "warmupAttributeFilter",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  FILTER_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_filter"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.exec,
      tags: { query_type: variant.id },
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

// Equality: category = 'X' — rotates through all 10 categories.
export function equalityFilter() {
  var cat = deterministicChoice(CATEGORIES, 0x101);
  var req = buildItemsUrl({
    filterSpec: { type: "eq", field: "category", value: cat },
  });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function warmupAttributeFilter() {
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

// Range: temperature >= X AND temperature <= X+10
export function rangeFilter() {
  var low = deterministicRange(-20, 40, 0x202);
  var high = low + 10;
  var req = buildItemsUrl({
    filterSpec: { type: "between", field: "temperature", low: low, high: high },
  });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

// LIKE: name LIKE 'feature_N%'
export function likeFilter() {
  var prefix = "feature_" + deterministicInt(1000, 0x303);
  var req = buildItemsUrl({
    filterSpec: { type: "prefix", field: "feature_name", prefix: prefix },
  });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}
