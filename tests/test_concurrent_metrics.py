"""Concurrent workload attribution must retain failed response checks."""

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from k6_results import point_stream_failures, validation_failures


class ConcurrentMetricsTests(unittest.TestCase):
    def test_runtime_attributes_successes_and_failures_to_every_workload(self):
        subprocess.run(["node", "--input-type=module", "-e", r'''
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
let source = fs.readFileSync("src/tests/concurrent.js", "utf8")
  .replace(/^import[\s\S]*?;\s*/gm, "")
  .replace(/export (var|function) /g, "$1 ");
const workloads = ["bbox", "equality", "range", "like"];
const samples = { errors: [], ogc_response_time: [], requests: [] };
let scenarioTags;
let response;
function Metric(name) {
  this.add = (value, tags) => samples[name].push({ value, tags: { ...scenarioTags, ...tags } });
}
for (const workload of workloads) {
  const context = {
    __ENV: { CONCURRENT_WORKLOADS: workload, CONCURRENT_LEVELS: "1,10" },
    Rate: Metric, Trend: Metric, durationToSeconds: () => 1,
    deterministicInt: () => 0, deterministicRange: () => 1,
    deterministicChoice: () => "A", deterministicUnit: () => 0,
    CATEGORIES: ["A"], randomBbox: () => [0, 0, 1, 1],
    buildItemsUrl: () => ({ url: "http://fixture/items", name: "items" }),
    ogcChecks: () => ({ status: res => res.status === 200, body: res => res.valid }),
    check: (res, checks) => Object.values(checks).map(fn => fn(res)).every(Boolean),
    http: { get: (_url, options) => {
      samples.requests.push({ tags: { ...scenarioTags, ...options.tags } });
      return response;
    } },
  };
  vm.runInNewContext(source, context);
  for (const level of ["1", "10"]) {
    scenarioTags = context.options.scenarios["vus_" + level].tags;
    for (const [status, valid] of [[200, true], [503, false], [200, false]]) {
      response = { status, valid, timings: { duration: status === 503 ? 20 : 5 } };
      context.mixedWorkload();
    }
  }
  scenarioTags = context.options.scenarios.warmup.tags;
  response = { status: 200, valid: true, timings: { duration: 5 } };
  context.warmupConcurrent();
}
for (const level of ["1", "10"]) {
  const total = samples.errors.filter(s => s.tags.concurrency === level);
  assert.equal(total.length, 12);
  assert.equal(total.filter(s => s.value).length, 8);
  let workloadCount = 0;
  for (const workload of workloads) {
    const select = s => s.tags.concurrency === level && s.tags.workload === workload;
    const errors = samples.errors.filter(select);
    assert.equal(errors.length, samples.requests.filter(select).length);
    assert.equal(errors.length, 3);
    assert.equal(errors.filter(s => s.value).length, 2);
    assert.equal(samples.ogc_response_time.filter(select).length, 3);
    workloadCount += errors.length;
  }
  assert.equal(workloadCount, total.length);
}
assert.equal(samples.errors.filter(s => s.tags.phase === "warmup").length, 4);
assert.equal(samples.errors.filter(s => s.tags.phase === "warmup" && s.tags.concurrency).length, 0);
'''], cwd=ROOT, check=True)

    def summary(self):
        metrics = {
            "http_reqs": {"count": 8}, "checks": {"value": 1},
            "errors": {"value": 0}, "http_req_failed": {"value": 0},
        }
        for workload in ("bbox", "equality", "range", "like"):
            suffix = "{concurrency:10,workload:" + workload + "}"
            metrics["http_reqs" + suffix] = {"count": 2}
            metrics["http_req_duration" + suffix] = {"med": 1, "p(95)": 2, "p(99)": 3}
            metrics["errors" + suffix] = {"value": 0, "passes": 0, "fails": 2}
        return {"metrics": metrics}

    def test_summary_rejects_empty_missing_or_incomplete_workload_errors(self):
        data = self.summary()
        self.assertEqual([], validation_failures(data))
        key = "errors{concurrency:10,workload:bbox}"
        for metric in (None, {"value": 0, "passes": 0, "fails": 0},
                       {"value": 0, "passes": 0, "fails": 1},
                       {"value": 0, "passes": -1, "fails": 3}):
            broken = copy.deepcopy(data)
            if metric is None:
                del broken["metrics"][key]
            else:
                broken["metrics"][key] = metric
            with self.subTest(metric=metric):
                self.assertTrue(validation_failures(broken))
        data["metrics"][key] = {"value": 0.5, "passes": 1, "fails": 1}
        self.assertTrue(validation_failures(data))

    def test_point_stream_requires_one_workload_error_sample_per_request(self):
        records = []
        for workload in ("bbox", "equality", "range", "like"):
            for name, value in (("http_reqs", 1), ("http_req_duration", 2),
                                ("errors", 0), ("http_req_failed", 0), ("checks", 1)):
                records.append({"type": "Point", "metric": name, "data": {
                    "value": value, "tags": {"concurrency": "10", "workload": workload},
                }})
        encode = lambda rows: "\n".join(json.dumps(row) for row in rows)
        self.assertEqual([], point_stream_failures(encode(records)))
        broken = copy.deepcopy(records)
        for record in broken:
            if record["metric"] == "errors":
                del record["data"]["tags"]["workload"]
        self.assertTrue(point_stream_failures(encode(broken)))
        self.assertTrue(point_stream_failures(encode(records + [records[2]])))
