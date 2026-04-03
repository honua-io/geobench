// GeoBench: Spatial bounding box benchmarks (small, medium, large).
//
// Usage: k6 run --env SERVER=honua spatial-bbox.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { buildItemsUrl, ogcChecks, randomBbox } from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);
var scenarioThresholds = {
  "http_req_duration{bbox_size:small}": ["max>=0"],
  "http_req_duration{bbox_size:medium}": ["max>=0"],
  "http_req_duration{bbox_size:large}": ["max>=0"],
  "http_reqs{bbox_size:small}": ["count>=0"],
  "http_reqs{bbox_size:medium}": ["count>=0"],
  "http_reqs{bbox_size:large}": ["count>=0"],
};

export var options = {
  discardResponseBodies: true,
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "warmupSpatialBbox",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    small_bbox: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "smallBbox",
      tags: { bbox_size: "small" },
      startTime: "60s",
    },
    medium_bbox: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "mediumBbox",
      tags: { bbox_size: "medium" },
      startTime: "190s",
    },
    large_bbox: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "largeBbox",
      tags: { bbox_size: "large" },
      startTime: "320s",
    },
  },
  thresholds: Object.assign({
    errors: ["rate<0.01"],
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
  smallBbox();
  mediumBbox();
  largeBbox();
}
