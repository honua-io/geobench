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
var scenarioThresholds = {
  "http_req_duration{query_type:equality}": ["max>=0"],
  "http_req_duration{query_type:range}": ["max>=0"],
  "http_req_duration{query_type:like}": ["max>=0"],
  "http_reqs{query_type:equality}": ["count>=0"],
  "http_reqs{query_type:range}": ["count>=0"],
  "http_reqs{query_type:like}": ["count>=0"],
};

export var options = {
  discardResponseBodies: true,
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "warmupAttributeFilter",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    equality_filter: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "equalityFilter",
      tags: { query_type: "equality" },
      startTime: "60s",
    },
    range_filter: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "rangeFilter",
      tags: { query_type: "range" },
      startTime: "190s",
    },
    like_filter: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "likeFilter",
      tags: { query_type: "like" },
      startTime: "320s",
    },
  },
  thresholds: Object.assign({
    errors: ["rate<0.01"],
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
  equalityFilter();
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
