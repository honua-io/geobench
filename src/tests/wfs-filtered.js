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
var scenarioThresholds = {
  "http_req_duration{query_type:equality}": ["max>=0"],
  "http_req_duration{query_type:range}": ["max>=0"],
  "http_req_duration{query_type:like}": ["max>=0"],
  "http_reqs{query_type:equality}": ["count>=0"],
  "http_reqs{query_type:range}": ["count>=0"],
  "http_reqs{query_type:like}": ["count>=0"],
};

if (!wfsFilteredQueriesSupported()) {
  throw new Error(
    "WFS filtered suite currently supports honua and geoserver only; got " +
    (__ENV.SERVER || "unset")
  );
}

function buildScenarios() {
  var offsetSeconds = parseInt(warmupDuration, 10);

  return {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWfsFiltered",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    equality_filter: {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: "equalityFilter",
      tags: { query_type: "equality" },
      startTime: String(offsetSeconds) + "s",
    },
    range_filter: {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: "rangeFilter",
      tags: { query_type: "range" },
      startTime: String(offsetSeconds + parseInt(scenarioDuration, 10)) + "s",
    },
    like_filter: {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: "likeFilter",
      tags: { query_type: "like" },
      startTime: String(offsetSeconds + (parseInt(scenarioDuration, 10) * 2)) + "s",
    },
  };
}

export var options = {
  discardResponseBodies: true,
  scenarios: buildScenarios(),
  thresholds: Object.assign({
    errors: ["rate<0.01"],
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
  equalityFilter();
  rangeFilter();
  likeFilter();
}
