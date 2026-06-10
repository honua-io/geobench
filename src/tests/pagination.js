// GeoBench: OGC API Features pagination benchmarks (shallow, medium, deep offset).
//
// Deep offset/limit paging is a well-known stress pattern for feature servers:
// the database still scans and discards every skipped row, so tail latency
// typically grows with offset depth even when the returned page is small. This
// suite exercises the comparable `offset`/`startIndex` + `sortby` paging surface
// the OGC API Features track already supports via helpers.js.
//
// Usage: k6 run --env SERVER=honua pagination.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
import { buildItemsUrl, ogcChecks, RESULT_LIMIT } from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);
var scenarioDuration = __ENV.PAGINATION_DURATION || "120s";
var warmupDuration = __ENV.PAGINATION_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.PAGINATION_VUS || "10", 10);
var selectedDepths = (__ENV.PAGINATION_SCENARIOS || "shallow,medium,deep")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

// Offsets are expressed as page indices scaled by the result limit so the
// same depth lands on a comparable row across servers regardless of limit.
var SHALLOW_OFFSET = parseInt(__ENV.PAGINATION_SHALLOW_OFFSET || String(RESULT_LIMIT), 10);
var MEDIUM_OFFSET = parseInt(__ENV.PAGINATION_MEDIUM_OFFSET || String(RESULT_LIMIT * 100), 10);
var DEEP_OFFSET = parseInt(__ENV.PAGINATION_DEEP_OFFSET || String(RESULT_LIMIT * 900), 10);

var PAGE_VARIANTS = [
  { id: "shallow", exec: "shallowPage", offset: SHALLOW_OFFSET },
  { id: "medium", exec: "mediumPage", offset: MEDIUM_OFFSET },
  { id: "deep", exec: "deepPage", offset: DEEP_OFFSET },
].filter(function (variant) {
  return selectedDepths.indexOf(variant.id) !== -1;
});

if (PAGE_VARIANTS.length === 0) {
  throw new Error("No pagination scenarios selected");
}

var scenarioThresholds = {};
PAGE_VARIANTS.forEach(function (variant) {
  scenarioThresholds["http_req_duration{page_depth:" + variant.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{page_depth:" + variant.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupPagination",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  PAGE_VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_page"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.exec,
      tags: { page_depth: variant.id },
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

function pageRequest(offset) {
  // buildItemsUrl applies the server-specific offset param (offset/startIndex)
  // and sortby, and attaches an offsetValidator that confirms the returned page
  // is the contiguous, ordered window starting at offset+1.
  var req = buildItemsUrl({ offset: offset });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

// Shallow: first non-zero page — establishes the no-skip baseline.
export function shallowPage() {
  pageRequest(SHALLOW_OFFSET);
}

// Medium: ~100 pages deep — server skips tens of thousands of rows per request.
export function mediumPage() {
  pageRequest(MEDIUM_OFFSET);
}

// Deep: near the tail of the 100K dataset — maximal skip cost.
export function deepPage() {
  pageRequest(DEEP_OFFSET);
}

export function warmupPagination() {
  PAGE_VARIANTS.forEach(function (variant) {
    pageRequest(variant.offset);
  });
}
