// GeoBench: standards-based WFS GetFeature benchmarks.
//
// Comparable track:
// - base collection read
// - bbox-restricted read
//
// Filtered WFS queries are intentionally omitted from this suite because the
// local Honua, GeoServer, and QGIS servers do not share one clean, common
// standards-based filter syntax in this environment.
//
// Usage: k6 run --env SERVER=honua wfs-getfeature.js

import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";
import {
  buildGetFeatureRequest,
  randomWfsBbox,
  wfsChecks,
  WFS_BBOX_SIZES,
} from "./wfs-helpers.js";

var errorRate = new Rate("errors");
var responseTime = new Trend("wfs_response_time", true);
var scenarioThresholds = {
  "http_req_duration{query_type:base}": ["max>=0"],
  "http_req_duration{bbox_size:small}": ["max>=0"],
  "http_req_duration{bbox_size:medium}": ["max>=0"],
  "http_req_duration{bbox_size:large}": ["max>=0"],
  "http_reqs{query_type:base}": ["count>=0"],
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
      exec: "warmupWfsGetFeature",
      tags: { phase: "warmup" },
      startTime: "0s",
    },
    base_read: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "baseRead",
      tags: { query_type: "base" },
      startTime: "60s",
    },
    small_bbox: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "smallBbox",
      tags: { bbox_size: "small" },
      startTime: "190s",
    },
    medium_bbox: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "mediumBbox",
      tags: { bbox_size: "medium" },
      startTime: "320s",
    },
    large_bbox: {
      executor: "constant-vus",
      vus: 10,
      duration: "120s",
      exec: "largeBbox",
      tags: { bbox_size: "large" },
      startTime: "450s",
    },
  },
  thresholds: Object.assign({
    errors: ["rate<0.01"],
  }, scenarioThresholds),
};

function runGetFeature(bbox) {
  var req = buildGetFeatureRequest({
    bbox: bbox,
  });
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, wfsChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function baseRead() {
  var req = buildGetFeatureRequest();
  var res = http.get(req.url, { tags: { name: req.name }, responseType: "text" });
  var ok = check(res, wfsChecks(req));
  errorRate.add(!ok);
  responseTime.add(res.timings.duration);
}

export function smallBbox() {
  runGetFeature(randomWfsBbox(WFS_BBOX_SIZES.small, 0x601));
}

export function mediumBbox() {
  runGetFeature(randomWfsBbox(WFS_BBOX_SIZES.medium, 0x602));
}

export function largeBbox() {
  runGetFeature(randomWfsBbox(WFS_BBOX_SIZES.large, 0x603));
}

export function warmupWfsGetFeature() {
  baseRead();
  smallBbox();
  mediumBbox();
  largeBbox();
}
