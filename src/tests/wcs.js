// GeoBench: WCS GetCoverage benchmark.
//
// Usage: k6 run --env SERVER=geoserver wcs.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { buildBbox } from "./raster-helpers.js";
import { buildWcsGetCoverageRequest } from "./wms-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wcs_response_time", true);
var scenarioDuration = __ENV.WCS_DURATION || "120s";
var warmupDuration = __ENV.WCS_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WCS_VUS || "10", 10);
var coverageId = __ENV.GEOSERVER_WCS_COVERAGE || __ENV.WCS_COVERAGE || "geobench:bench_raster";
var selectedScenarios = (__ENV.WCS_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

var SERVER_NAME = (function () {
  var name = (__ENV.SERVER || "geoserver").toLowerCase();
  if (name !== "geoserver") {
    throw new Error("WCS suite currently supports geoserver only in this harness; got " + name);
  }
  return name;
}());

var COVERAGE_SIZES = {
  small: 0.1,
  medium: 5.0,
  large: 30.0,
};

var COVERAGE_SALTS = {
  small: 0xC11,
  medium: 0xC12,
  large: 0xC13,
};

var SCENARIOS = [
  { id: "small", width: 256, height: 256, salt: COVERAGE_SALTS.small },
  { id: "medium", width: 256, height: 256, salt: COVERAGE_SALTS.medium },
  { id: "large", width: 256, height: 256, salt: COVERAGE_SALTS.large },
].filter(function (scenario) {
  return selectedScenarios.indexOf(scenario.id) !== -1;
});

if (SCENARIOS.length === 0) {
  throw new Error("No WCS scenarios selected");
}

var scenarioThresholds = {};
SCENARIOS.forEach(function (scenario) {
  scenarioThresholds["http_req_duration{bbox_size:" + scenario.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{bbox_size:" + scenario.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWcs",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  SCENARIOS.forEach(function (scenario) {
    scenarios[scenario.id + "_coverage"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: scenario.id + "Coverage",
      tags: { bbox_size: scenario.id },
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
    errors: ["rate<0.01"],
  }, scenarioThresholds),
};

function findScenario(id) {
  return SCENARIOS.find(function (scenario) {
    return scenario.id === id;
  });
}

function runCoverage(scenario) {
  var req = buildWcsGetCoverageRequest(SERVER_NAME, {
    coverage: coverageId,
    bbox: buildBbox(COVERAGE_SIZES[scenario.id], scenario.salt),
    width: scenario.width,
    height: scenario.height,
    format: __ENV.WCS_FORMAT || "GeoTIFF",
  });

  var res = http.get(req.url, {
    tags: { name: req.name },
    responseType: "binary",
  });

  var contentType = (res.headers["Content-Type"] || res.headers["content-type"] || "").toLowerCase();
  var ok = check(res, {
    "status is 200": function () {
      return res.status === 200;
    },
    "content-type is present": function () {
      return contentType.length > 0;
    },
    "content-type is not xml": function () {
      return contentType.indexOf("xml") === -1;
    },
  });

  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function smallCoverage() {
  runCoverage(findScenario("small"));
}

export function mediumCoverage() {
  runCoverage(findScenario("medium"));
}

export function largeCoverage() {
  runCoverage(findScenario("large"));
}

export function warmupWcs() {
  if (selectedScenarios.indexOf("small") !== -1) {
    smallCoverage();
  }
  if (selectedScenarios.indexOf("medium") !== -1) {
    mediumCoverage();
  }
  if (selectedScenarios.indexOf("large") !== -1) {
    largeCoverage();
  }
}
