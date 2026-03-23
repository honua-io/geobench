// GeoBench: Attribute filter benchmarks (equality, range, LIKE).
//
// Usage: k6 run --env SERVER=honua attribute-filter.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { buildItemsUrl, ogcChecks, CATEGORIES } from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);

export var options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "equalityFilter",
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
  thresholds: {
    errors: ["rate<0.01"],
  },
};

// Equality: category = 'X' — rotates through all 10 categories.
export function equalityFilter() {
  var cat = CATEGORIES[Math.floor(Math.random() * CATEGORIES.length)];
  var req = buildItemsUrl({ filter: "category='" + cat + "'" });
  var res = http.get(req.url, { tags: { name: req.name } });
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}

// Range: temperature >= X AND temperature <= X+10
export function rangeFilter() {
  var low = -20 + Math.random() * 60; // -20 to 40
  var high = low + 10;
  var filter =
    "temperature >= " + low.toFixed(1) + " AND temperature <= " + high.toFixed(1);
  var req = buildItemsUrl({ filter: filter });
  var res = http.get(req.url, { tags: { name: req.name } });
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}

// LIKE: name LIKE 'feature_N%'
export function likeFilter() {
  var prefix = "feature_" + Math.floor(Math.random() * 1000);
  var req = buildItemsUrl({ filter: "feature_name LIKE '" + prefix + "%'" });
  var res = http.get(req.url, { tags: { name: req.name } });
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}
