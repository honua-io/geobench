// GeoBench: GeoServices REST MapServer/identify benchmark.
//
// Usage:
//   k6 run --env SERVER=honua geoservices-identify.js
//   k6 run --env SERVER=geoserver --env GEOSERVER_GSR_ENABLED=1 geoservices-identify.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildGeoservicesIdentifyRequest,
  GEOSERVICES_QUERY_SIZES,
  geoservicesIdentifyChecks,
  randomGeoservicesBbox,
} from "./geoservices-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("geoservices_identify_response_time", true);
var scenarioDuration = __ENV.GEOSERVICES_IDENTIFY_DURATION || "120s";
var warmupDuration = __ENV.GEOSERVICES_IDENTIFY_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.GEOSERVICES_IDENTIFY_VUS || "10", 10);
var selectedScenarios = (__ENV.GEOSERVICES_IDENTIFY_SCENARIOS || "small,medium,large")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

function supportedServerName() {
  var name = (__ENV.SERVER || "honua").toLowerCase();
  if (name === "honua") {
    return name;
  }
  if (name === "geoserver" && __ENV.GEOSERVER_GSR_ENABLED === "1") {
    return name;
  }
  throw new Error(
    "MapServer/identify suite currently supports honua, and geoserver with GSR enabled; got " + name
  );
}

var SERVER_NAME = supportedServerName();

var BBOX_SALTS = {
  small: 0xB11,
  medium: 0xB12,
  large: 0xB13,
};

var IDENTIFY_VARIANTS = [
  { id: "small", bboxSize: GEOSERVICES_QUERY_SIZES.small, salt: BBOX_SALTS.small, tolerance: 2 },
  { id: "medium", bboxSize: GEOSERVICES_QUERY_SIZES.medium, salt: BBOX_SALTS.medium, tolerance: 3 },
  { id: "large", bboxSize: GEOSERVICES_QUERY_SIZES.large, salt: BBOX_SALTS.large, tolerance: 5 },
];

var SCENARIOS = IDENTIFY_VARIANTS.filter(function (variant) {
  return selectedScenarios.indexOf(variant.id) !== -1;
});

if (SCENARIOS.length === 0) {
  throw new Error("No identify scenarios selected");
}

var scenarioThresholds = {};
SCENARIOS.forEach(function (scenario) {
  scenarioThresholds["http_req_duration{bbox_size:" + scenario.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{bbox_size:" + scenario.id + "}"] = ["count>=0"];
});

function parseBboxCenter(bbox) {
  var parts = String(bbox).split(",").map(function (value) {
    return parseFloat(value);
  });
  if (parts.length !== 4 || parts.some(function (value) {
      return !Number.isFinite(value);
    })) {
    throw new Error("Invalid bbox: " + bbox);
  }

  var minX = parts[0];
  var minY = parts[1];
  var maxX = parts[2];
  var maxY = parts[3];
  return ((minX + maxX) / 2).toFixed(6) + "," + ((minY + maxY) / 2).toFixed(6);
}

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupIdentify",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  SCENARIOS.forEach(function (scenario) {
    scenarios[scenario.id + "_identify"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: scenario.id + "Identify",
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

function runIdentify(sizeKey, scenario) {
  var bbox = randomGeoservicesBbox(scenario.bboxSize, scenario.salt);
  var req = buildGeoservicesIdentifyRequest({
    geometry: parseBboxCenter(bbox),
    mapExtent: bbox,
    tolerance: scenario.tolerance,
    imageWidth: "256",
    imageHeight: "256",
    dpi: "96",
    srid: "4326",
  });
  var res = http.get(req.url, {
    tags: { name: req.name },
    responseType: "text",
  });

  var ok = check(res, geoservicesIdentifyChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

function getScenario(id) {
  return SCENARIOS.find(function (scenario) {
    return scenario.id === id;
  });
}

export function smallIdentify() {
  runIdentify("small", getScenario("small"));
}

export function mediumIdentify() {
  runIdentify("medium", getScenario("medium"));
}

export function largeIdentify() {
  runIdentify("large", getScenario("large"));
}

export function warmupIdentify() {
  if (selectedScenarios.indexOf("small") !== -1) {
    smallIdentify();
  }
  if (selectedScenarios.indexOf("medium") !== -1) {
    mediumIdentify();
  }
  if (selectedScenarios.indexOf("large") !== -1) {
    largeIdentify();
  }
}
