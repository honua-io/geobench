// GeoBench: Concurrency ramp benchmarks (1, 10, 50, 100 VUs).
//
// Mixed workload: 40% spatial bbox, 30% equality filter, 20% range filter, 10% prefix filter.
// Usage: k6 run --env SERVER=honua concurrent.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  deterministicChoice,
  deterministicInt,
  deterministicRange,
  deterministicUnit,
} from "./deterministic.js";
import {
  buildItemsUrl,
  ogcChecks,
  randomBbox,
  CATEGORIES,
} from "./helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("ogc_response_time", true);
var scenarioThresholds = {
  "http_req_duration{concurrency:1}": ["max>=0"],
  "http_req_duration{concurrency:10}": ["max>=0"],
  "http_req_duration{concurrency:50}": ["max>=0"],
  "http_req_duration{concurrency:100}": ["max>=0"],
  "http_reqs{concurrency:1}": ["count>=0"],
  "http_reqs{concurrency:10}": ["count>=0"],
  "http_reqs{concurrency:50}": ["count>=0"],
  "http_reqs{concurrency:100}": ["count>=0"],
};

export var options = {
  discardResponseBodies: true,
  scenarios: {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: "60s",
      exec: "warmupConcurrent",
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
  thresholds: Object.assign({
    errors: ["rate<0.05"],
  }, scenarioThresholds),
};

export function mixedWorkload() {
  var roll = deterministicUnit(0x501);
  var req;

  if (roll < 0.4) {
    // Spatial bbox query (varying sizes)
    var size = deterministicRange(0.5, 10.5, 0x502);
    req = buildItemsUrl({ bbox: randomBbox(size, 0x503) });
  } else if (roll < 0.7) {
    // Equality filter query
    var cat = deterministicChoice(CATEGORIES, 0x504);
    req = buildItemsUrl({
      filterSpec: { type: "eq", field: "category", value: cat },
    });
  } else if (roll < 0.9) {
    // Range filter query
    var low = deterministicRange(-20, 40, 0x505);
    req = buildItemsUrl({
      filterSpec: { type: "between", field: "temperature", low: low, high: low + 10 },
    });
  } else {
    // Prefix filter query
    var prefix = "feature_" + deterministicInt(1000, 0x506);
    req = buildItemsUrl({
      filterSpec: { type: "prefix", field: "feature_name", prefix: prefix },
    });
  }

  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function warmupConcurrent() {
  mixedWorkload();
}
