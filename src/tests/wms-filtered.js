// GeoBench: WMS filtered GetMap benchmark.
//
// Supports:
// - OGC Filter (equality)
// - OGC Filter (between)
// - OGC Filter (prefix/like)
//
// Usage: k6 run --env SERVER=geoserver wms-filtered.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import { deterministicInt, deterministicRange } from "./deterministic.js";
import { buildBbox, validateImageResponse } from "./raster-helpers.js";
import { buildWmsFilteredMapRequest } from "./wms-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wms_filtered_response_time", true);
var scenarioDuration = __ENV.WMS_FILTERED_DURATION || "120s";
var warmupDuration = __ENV.WMS_FILTERED_WARMUP || "60s";
var scenarioVus = parseInt(__ENV.WMS_FILTERED_VUS || "10", 10);
var selectedScenarios = (__ENV.WMS_FILTERED_SCENARIOS || "equality,range,like")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

function supportedServerName() {
  var name = (__ENV.SERVER || "geoserver").toLowerCase();
  if (name !== "geoserver" && name !== "honua") {
    throw new Error(
      "WMS filtered suite currently supports honua and geoserver only; got " + name
    );
  }
  return name;
}

var SERVER_NAME = supportedServerName();

var FILTER_VARIANTS = [
  {
    id: "equality",
    filterType: "equality",
    width: 256,
    height: 256,
    bboxSize: 5.0,
    salt: 0xA11,
    spec: { type: "eq", field: "category", value: "park" },
  },
  {
    id: "range",
    filterType: "range",
    width: 256,
    height: 256,
    bboxSize: 5.0,
    salt: 0xA12,
    spec: {
      type: "between",
      field: "temperature",
      low: deterministicRange(-20, 40, 0xA12),
      high: deterministicRange(-20, 40, 0xA12) + 10,
    },
  },
  {
    id: "like",
    filterType: "like",
    width: 256,
    height: 256,
    bboxSize: 5.0,
    salt: 0xA13,
    spec: { type: "prefix", field: "feature_name", prefix: "feature_" + deterministicInt(1000, 0xA13) },
  },
];

var VARIANTS = FILTER_VARIANTS.filter(function (variant) {
  return selectedScenarios.indexOf(variant.id) !== -1;
});

if (VARIANTS.length === 0) {
  throw new Error("No WMS filtered scenarios selected");
}

var scenarioThresholds = {};
VARIANTS.forEach(function (variant) {
  scenarioThresholds["http_req_duration{query_type:" + variant.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{query_type:" + variant.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: Math.max(1, Math.min(5, scenarioVus)),
      duration: warmupDuration,
      exec: "warmupWmsFiltered",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  VARIANTS.forEach(function (variant) {
    scenarios[variant.id + "_filter"] = {
      executor: "constant-vus",
      vus: scenarioVus,
      duration: scenarioDuration,
      exec: variant.id + "Filter",
      tags: { query_type: variant.id },
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

function getVariant(id) {
  return VARIANTS.find(function (variant) {
    return variant.id === id;
  });
}

function runFilter(variant) {
  var req = buildWmsFilteredMapRequest(SERVER_NAME, {
    bbox: buildBbox(variant.bboxSize, variant.salt),
    width: variant.width,
    height: variant.height,
    filterSpec: variant.spec,
    filterType: variant.filterType,
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

export function equalityFilter() {
  runFilter(getVariant("equality"));
}

export function rangeFilter() {
  runFilter(getVariant("range"));
}

export function likeFilter() {
  runFilter(getVariant("like"));
}

export function warmupWmsFiltered() {
  if (selectedScenarios.indexOf("equality") !== -1) {
    equalityFilter();
  }
  if (selectedScenarios.indexOf("range") !== -1) {
    rangeFilter();
  }
  if (selectedScenarios.indexOf("like") !== -1) {
    likeFilter();
  }
}
