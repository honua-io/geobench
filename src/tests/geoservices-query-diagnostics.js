// GeoBench: GeoServices REST FeatureServer/query diagnostic benchmarks.
//
// Purpose:
// - distinguish 1 VU vs 10 VU behavior
// - isolate full responses vs attrs-only vs geometry+objectid
// - focus on the medium/large cases where sustained-load losses appear

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildGeoservicesQueryRequest,
  GEOSERVICES_QUERY_SIZES,
  geoservicesChecks,
  randomGeoservicesBbox,
} from "./geoservices-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("geoservices_query_diagnostic_response_time", true);
var phaseDuration = __ENV.GEOSERVICES_DIAG_DURATION || "20s";
var warmupDuration = __ENV.GEOSERVICES_DIAG_WARMUP || "15s";
var selectedVariantIds = (__ENV.GEOSERVICES_DIAG_VARIANTS || "")
  .split(",")
  .map(function (value) {
    return value.trim();
  })
  .filter(function (value) {
    return value.length > 0;
  });

var VARIANTS = [
  {
    id: "medium-full-1vu",
    exec: "medium_full_1vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.medium,
    salt: 0xA01,
    vus: 1,
    nameSuffix: "medium-full-1vu",
  },
  {
    id: "medium-full-10vu",
    exec: "medium_full_10vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.medium,
    salt: 0xA02,
    vus: 10,
    nameSuffix: "medium-full-10vu",
  },
  {
    id: "medium-attrs-10vu",
    exec: "medium_attrs_10vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.medium,
    salt: 0xA03,
    vus: 10,
    outFields: "*",
    returnGeometry: false,
    nameSuffix: "medium-attrs-10vu",
  },
  {
    id: "medium-geom-oid-10vu",
    exec: "medium_geom_oid_10vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.medium,
    salt: 0xA04,
    vus: 10,
    outFields: "objectid",
    returnGeometry: true,
    nameSuffix: "medium-geom-oid-10vu",
  },
  {
    id: "large-full-1vu",
    exec: "large_full_1vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.large,
    salt: 0xB01,
    vus: 1,
    nameSuffix: "large-full-1vu",
  },
  {
    id: "large-full-10vu",
    exec: "large_full_10vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.large,
    salt: 0xB02,
    vus: 10,
    nameSuffix: "large-full-10vu",
  },
  {
    id: "large-attrs-10vu",
    exec: "large_attrs_10vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.large,
    salt: 0xB03,
    vus: 10,
    outFields: "*",
    returnGeometry: false,
    nameSuffix: "large-attrs-10vu",
  },
  {
    id: "large-geom-oid-10vu",
    exec: "large_geom_oid_10vu",
    bboxSize: GEOSERVICES_QUERY_SIZES.large,
    salt: 0xB04,
    vus: 10,
    outFields: "objectid",
    returnGeometry: true,
    nameSuffix: "large-geom-oid-10vu",
  },
];

if (selectedVariantIds.length > 0) {
  VARIANTS = VARIANTS.filter(function (variant) {
    return selectedVariantIds.indexOf(variant.id) !== -1;
  });
}

if (VARIANTS.length === 0) {
  throw new Error("No GeoServices diagnostic variants selected");
}

var scenarioThresholds = {};
VARIANTS.forEach(function (variant) {
  scenarioThresholds["http_req_duration{variant:" + variant.id + "}"] = ["max>=0"];
  scenarioThresholds["http_reqs{variant:" + variant.id + "}"] = ["count>=0"];
});

function buildScenarios() {
  var scenarios = {
    warmup: {
      executor: "constant-vus",
      vus: 5,
      duration: warmupDuration,
      exec: "warmupGeoservicesDiagnostics",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
  };

  var offsetSeconds = parseInt(warmupDuration, 10);
  VARIANTS.forEach(function (variant) {
    scenarios[variant.id] = {
      executor: "constant-vus",
      vus: variant.vus,
      duration: phaseDuration,
      exec: variant.exec,
      tags: { variant: variant.id },
      startTime: String(offsetSeconds) + "s",
    };
    offsetSeconds += parseInt(phaseDuration, 10);
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

function runVariant(variant) {
  var bbox = randomGeoservicesBbox(variant.bboxSize, variant.salt);
  var req = buildGeoservicesQueryRequest({
    bbox: bbox,
    outFields: variant.outFields,
    returnGeometry: variant.returnGeometry,
    nameSuffix: variant.nameSuffix,
  });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, geoservicesChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

function getVariant(id) {
  return VARIANTS.find(function (variant) {
    return variant.id === id;
  });
}

export function medium_full_1vu() {
  runVariant(getVariant("medium-full-1vu"));
}

export function medium_full_10vu() {
  runVariant(getVariant("medium-full-10vu"));
}

export function medium_attrs_10vu() {
  runVariant(getVariant("medium-attrs-10vu"));
}

export function medium_geom_oid_10vu() {
  runVariant(getVariant("medium-geom-oid-10vu"));
}

export function large_full_1vu() {
  runVariant(getVariant("large-full-1vu"));
}

export function large_full_10vu() {
  runVariant(getVariant("large-full-10vu"));
}

export function large_attrs_10vu() {
  runVariant(getVariant("large-attrs-10vu"));
}

export function large_geom_oid_10vu() {
  runVariant(getVariant("large-geom-oid-10vu"));
}

export function warmupGeoservicesDiagnostics() {
  var warmupVariant = getVariant("medium-full-10vu") || VARIANTS[0];
  runVariant(warmupVariant);
}
