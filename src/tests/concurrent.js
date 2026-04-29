// GeoBench: Concurrency ramp benchmarks (1, 10, 50, 100 VUs).
//
// Mixed workload: 40% spatial bbox, 30% equality filter, 20% range filter, 10% prefix filter.
// Usage: k6 run --env SERVER=honua concurrent.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { durationToSeconds } from "./duration-helpers.js";
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
var workloadNames = ["bbox", "equality", "range", "like"];
var scenarioDuration = __ENV.CONCURRENT_DURATION || "120s";
var warmupDuration = __ENV.CONCURRENT_WARMUP || "60s";
var concurrencyLevels = (__ENV.CONCURRENT_LEVELS || "1,10,50,100")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });
var selectedWorkloadNames = (__ENV.CONCURRENT_WORKLOADS || "bbox,equality,range,like")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return workloadNames.indexOf(value) !== -1;
  });

if (concurrencyLevels.length === 0) {
  throw new Error("No concurrent levels selected");
}

if (selectedWorkloadNames.length === 0) {
  throw new Error("No concurrent workloads selected");
}

function buildScenarioThresholds() {
  var thresholds = {};

  for (var i = 0; i < concurrencyLevels.length; i++) {
    var concurrency = concurrencyLevels[i];
    thresholds["http_req_duration{concurrency:" + concurrency + "}"] = ["max>=0"];
    thresholds["http_reqs{concurrency:" + concurrency + "}"] = ["count>=0"];

    for (var j = 0; j < selectedWorkloadNames.length; j++) {
      var workload = selectedWorkloadNames[j];
      thresholds["http_req_duration{concurrency:" + concurrency + ",workload:" + workload + "}"] = ["max>=0"];
      thresholds["http_reqs{concurrency:" + concurrency + ",workload:" + workload + "}"] = ["count>=0"];
    }
  }

  return thresholds;
}
var scenarioThresholds = buildScenarioThresholds();

export var options = {
  discardResponseBodies: true,
  scenarios: buildScenarios(),
  thresholds: Object.assign({
    errors: ["rate<=0"],
  }, scenarioThresholds),
};

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: warmupDuration,
      exec: "warmupConcurrent",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = durationToSeconds(warmupDuration);
  concurrencyLevels.forEach(function (level) {
    var vus = parseInt(level, 10);
    scenarios["vus_" + level] = {
      executor: "constant-vus",
      vus: vus,
      duration: scenarioDuration,
      exec: "mixedWorkload",
      tags: { concurrency: level },
      startTime: String(offsetSeconds) + "s",
    };
    offsetSeconds += durationToSeconds(scenarioDuration);
  });

  return scenarios;
}

function chooseWorkload() {
  if (selectedWorkloadNames.length !== workloadNames.length) {
    return selectedWorkloadNames[deterministicInt(selectedWorkloadNames.length, 0x501)];
  }

  var roll = deterministicUnit(0x501);
  if (roll < 0.4) {
    return "bbox";
  }
  if (roll < 0.7) {
    return "equality";
  }
  if (roll < 0.9) {
    return "range";
  }
  return "like";
}

export function mixedWorkload() {
  var selectedWorkload = chooseWorkload();
  var req;
  var workload;

  if (selectedWorkload === "bbox") {
    // Spatial bbox query (varying sizes)
    var size = deterministicRange(0.5, 10.5, 0x502);
    req = buildItemsUrl({ bbox: randomBbox(size, 0x503) });
    workload = "bbox";
  } else if (selectedWorkload === "equality") {
    // Equality filter query
    var cat = deterministicChoice(CATEGORIES, 0x504);
    req = buildItemsUrl({
      filterSpec: { type: "eq", field: "category", value: cat },
    });
    workload = "equality";
  } else if (selectedWorkload === "range") {
    // Range filter query
    var low = deterministicRange(-20, 40, 0x505);
    req = buildItemsUrl({
      filterSpec: { type: "between", field: "temperature", low: low, high: low + 10 },
    });
    workload = "range";
  } else {
    // Prefix filter query
    var prefix = "feature_" + deterministicInt(1000, 0x506);
    req = buildItemsUrl({
      filterSpec: { type: "prefix", field: "feature_name", prefix: prefix },
    });
    workload = "like";
  }

  var res = http.get(req.url, { tags: { name: req.name, workload: workload }, responseType: "text" });
  var ok = check(res, ogcChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function warmupConcurrent() {
  mixedWorkload();
}
