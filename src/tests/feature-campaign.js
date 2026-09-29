import http from 'k6/http';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';
import { validateFeatureResponse } from './feature-validation.js';

const config = JSON.parse(open(__ENV.CAMPAIGN_INPUT));
const started = new Counter('feature_started');
const completed = new Counter('feature_completed');
const invalid = new Counter('feature_invalid');
const latency = new Trend('feature_latency', true);
const selected = config.scenario === 'mixed' ? config.mixed : [config.scenario];
const requests = Object.fromEntries(config.requests.map(r => [r.id, r]));
const scenario = config.rate ? {
  executor: 'constant-arrival-rate', rate: config.rate, timeUnit: '1s',
  preAllocatedVUs: 100, maxVUs: 100,
} : {executor: 'constant-vus', vus: config.vus};
export const options = {
  scenarios: {feature: {...scenario, duration: config.duration + 's', gracefulStop: config.drain + 's'}},
  summaryTrendStats: ['min', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: {feature_invalid: ['count==0']},
  systemTags: ['scenario', 'status'],
};

function query(request) {
  const response = http.get(request.url, {headers: {'Accept': 'application/geo+json, application/json',
    'Accept-Encoding': 'identity'}, timeout: '30s', responseType: 'text', redirects: 0});
  let failure = response.status !== 200 ? 'HTTP ' + response.status : null;
  let payload;
  try { payload = response.json(); } catch (_) { failure = 'malformed JSON'; }
  failure = failure || validateFeatureResponse(payload, request.expected, config.protocol, config.fields);
  if (response.headers['Content-Encoding'] && response.headers['Content-Encoding'] !== 'identity') failure = 'unexpected compression';
  return {response, failure, payload};
}

export function setup() {
  const results = config.requests.map(request => {
    const result = query(request);
    return {id: request.id, failure: result.failure,
      failureBody: result.failure ? String(result.response.body).slice(0, 500) : undefined,
      countMetadata: result.payload && typeof result.payload.numberMatched,
      encoding: result.response.headers['Content-Encoding'] || 'identity'};
  });
  console.log('PREFLIGHT ' + JSON.stringify(results));
  if (results.some(r => r.failure)) throw new Error('Corpus validation failed');
}

export default function () {
  const request = requests[selected[exec.scenario.iterationInTest % selected.length]];
  // Executor progress uses Go time.Since (monotonic), unlike JS wall time.
  const begin = exec.scenario.progress;
  started.add(1, {phase: config.phase, request: request.id});
  const result = query(request);
  const finish = exec.scenario.progress;
  const phase = finish < 1 ? config.phase : 'drain';
  const tags = {phase, request: request.id, valid: String(!result.failure)};
  completed.add(1, tags);
  invalid.add(result.failure ? 1 : 0, tags);
  // Progress is capped at 1 during drain: record late counts, never a truncated latency.
  if (phase !== 'drain') latency.add((finish - begin) * config.duration * 1000, tags);
  if (result.failure && exec.scenario.iterationInTest < 3) console.error(result.failure);
}
