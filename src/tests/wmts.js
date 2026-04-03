// GeoBench: WMTS GetTile benchmark.
//
// Usage: k6 run --env SERVER=geoserver wmts.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { validateImageResponse } from "./raster-helpers.js";
import { buildWmtsGetTileRequest } from "./wms-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wmts_response_time", true);
var scenarioDuration = __ENV.WMTS_DURATION || "120s";
var warmupDuration = __ENV.WMTS_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WMTS_VUS || "10", 10);
var selectedScenarios = (__ENV.WMTS_SCENARIOS || "z0,z1,z2")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

function supportedServerName() {
  var name = (__ENV.SERVER || "geoserver").toLowerCase();
  if (name !== "geoserver") {
    throw new Error(
      "WMTS suite currently supports geoserver only in this harness; got " + name
    );
  }
  return name;
}

var SERVER_NAME = supportedServerName();

var SCENARIO_DEFINITIONS = [
  { id: "z0", level: 0, tileCol: 0, tileRow: 0 },
  { id: "z1", level: 1, tileCol: 1, tileRow: 0 },
  { id: "z2", level: 2, tileCol: 0, tileRow: 1 },
];

var SCENARIOS = SCENARIO_DEFINITIONS.filter(function (scenario) {
  return selectedScenarios.indexOf(scenario.id) !== -1;
});

if (SCENARIOS.length === 0) {
  throw new Error("No WMTS scenarios selected");
}

var scenarioThresholds = {};
SCENARIOS.forEach(function (scenario) {
  scenarioThresholds["http_req_duration{tile_level:" + scenario.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{tile_level:" + scenario.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWmts",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  SCENARIOS.forEach(function (scenario) {
    scenarios[scenario.id + "_tile"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: scenario.id + "Tile",
      tags: { tile_level: scenario.id },
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

function getScenario(id) {
  return SCENARIOS.find(function (scenario) {
    return scenario.id === id;
  });
}

function runTile(scenario) {
  var req = buildWmtsGetTileRequest(SERVER_NAME, {
    level: scenario.level,
    levelLabel: scenario.id,
    tileCol: scenario.tileCol,
    tileRow: scenario.tileRow,
  });

  var res = http.get(req.url, {
    tags: { name: req.name },
    responseType: "binary",
  });

  var validation = validateImageResponse(res, req.expectedSize);
  var ok = check(res, {
    "status is 200": function () {
      return res.status === 200;
    },
    "content-type is png": function () {
      return validation.details.contentType.indexOf("image/png") !== -1;
    },
    "body looks like png": function () {
      return validation.ok;
    },
  });

  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function z0Tile() {
  runTile(getScenario("z0"));
}

export function z1Tile() {
  runTile(getScenario("z1"));
}

export function z2Tile() {
  runTile(getScenario("z2"));
}

export function warmupWmts() {
  if (selectedScenarios.indexOf("z0") !== -1) {
    z0Tile();
  }
  if (selectedScenarios.indexOf("z1") !== -1) {
    z1Tile();
  }
  if (selectedScenarios.indexOf("z2") !== -1) {
    z2Tile();
  }
}
