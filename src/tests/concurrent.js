// GeoBench: Concurrency ramp benchmarks (1, 10, 50, 100 VUs).
//
// Mixed workload: 40% spatial bbox, 40% attribute filter, 20% paginated scan.
// Usage: k6 run --env SERVER=honua concurrent.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildItemsUrl,
  ogcChecks,
  randomBbox,
  CATEGORIES,
} from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);

export var options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "mixedWorkload",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    vus_1: {
      executor: "constant-vus",
      vus: 1,
      duration: "120s",
      exec: "mixedWorkload",
      tags: { concurrency: "1" },
      startTime: "60s",
    },
    vus_10: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "mixedWorkload",
      tags: { concurrency: "10" },
      startTime: "190s",
    },
    vus_50: {
      executor: "constant-vus",
      vus: 50,
      duration: "120s",
      exec: "mixedWorkload",
      tags: { concurrency: "50" },
      startTime: "320s",
    },
    vus_100: {
      executor: "constant-vus",
      vus: 100,
      duration: "120s",
      exec: "mixedWorkload",
      tags: { concurrency: "100" },
      startTime: "450s",
    },
  },
  thresholds: {
    errors: ["rate<0.05"],
  },
};

export function mixedWorkload() {
  var roll = Math.random();
  var url;

  if (roll < 0.4) {
    // Spatial bbox query (varying sizes)
    var size = 0.5 + Math.random() * 10;
    url = buildItemsUrl({ bbox: randomBbox(size) });
  } else if (roll < 0.8) {
    // Attribute filter query
    var cat = CATEGORIES[Math.floor(Math.random() * CATEGORIES.length)];
    url = buildItemsUrl({ filter: "category='" + cat + "'" });
  } else {
    // Unfiltered paginated scan
    var offset = Math.floor(Math.random() * 1000);
    url = buildItemsUrl({ offset: offset });
  }

  var res = http.get(url);
  check(res, ogcChecks());
  errorRate.add(res.status !== 200);
  responseTime.add(res.timings.duration);
}
