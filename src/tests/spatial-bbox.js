// GeoBench: Spatial bounding box benchmarks (small, medium, large).
//
// Usage: k6 run --env SERVER=honua spatial-bbox.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { buildItemsUrl, ogcChecks, randomBbox } from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);

export var options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "mediumBbox",
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
  thresholds: {
    errors: ["rate<0.01"],
  },
};

// Small: ~0.1 degree (city-scale)
export function smallBbox() {
  var url = buildItemsUrl({ bbox: randomBbox(0.1) });
  var res = http.get(url);
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}

// Medium: ~5 degrees (country-scale)
export function mediumBbox() {
  var url = buildItemsUrl({ bbox: randomBbox(5.0) });
  var res = http.get(url);
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}

// Large: ~30 degrees (continental-scale)
export function largeBbox() {
  var url = buildItemsUrl({ bbox: randomBbox(30.0) });
  var res = http.get(url);
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}
