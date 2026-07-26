/**
 * Vulcan contract load test (k6).
 *
 * Why k6: matches Argus load nightlies, native HTTP percentiles, handleSummary JSON,
 * and no Python GIL contention beside the SUT. See benchmark/README.md.
 *
 * Env: BASE_URL, MODEL_TYPE (llm|vision), MODEL_ID, VUS, DURATION, BACKEND_NAME, RESULTS_OUT
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("vulcan_errors");
const inferLatency = new Trend("vulcan_infer_latency_ms", true);

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8080";
const MODEL_TYPE = (__ENV.MODEL_TYPE || "llm").toLowerCase();
const MODEL_ID =
  __ENV.MODEL_ID ||
  (MODEL_TYPE === "vision" ? "reference-tiny-vision" : "reference-tiny-llm");
const BACKEND_NAME = __ENV.BACKEND_NAME || "reference";
const RESULTS_OUT = __ENV.RESULTS_OUT || `benchmark/results/${BACKEND_NAME}-${MODEL_TYPE}.json`;
const VUS = Number(__ENV.VUS || 5);
const DURATION = __ENV.DURATION || "15s";

const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

export const options = {
  vus: VUS,
  duration: DURATION,
  summaryTrendStats: ["avg", "min", "med", "max", "p(50)", "p(95)", "p(99)"],
  thresholds: {
    vulcan_errors: ["rate<0.05"],
    http_req_failed: ["rate<0.05"],
  },
};

function llmBody(i) {
  return JSON.stringify({
    request_id: `k6-llm-${__VU}-${i}`,
    modality: "llm",
    model_id: MODEL_ID,
    input: {
      messages: [{ role: "user", content: `ping ${i}` }],
      max_tokens: 16,
      temperature: 0.0,
    },
  });
}

function visionBody(i) {
  return JSON.stringify({
    request_id: `k6-vision-${__VU}-${i}`,
    modality: "vision",
    model_id: MODEL_ID,
    input: {
      images: [{ media_type: "image/png", data_base64: TINY_PNG_B64 }],
      prompt: `describe ${i}`,
      max_tokens: 16,
    },
  });
}

export function setup() {
  const health = http.get(`${BASE_URL}/health`);
  if (health.status !== 200) {
    throw new Error(`setup: /health returned ${health.status}`);
  }
  return { started_at: new Date().toISOString() };
}

export default function () {
  const i = __ITER;
  const payload = MODEL_TYPE === "vision" ? visionBody(i) : llmBody(i);
  const res = http.post(`${BASE_URL}/v1/infer`, payload, {
    headers: { "Content-Type": "application/json" },
    tags: { name: "v1_infer" },
  });
  const ok = check(res, {
    "status 200": (r) => r.status === 200,
    "has modality": (r) => {
      try {
        return JSON.parse(r.body).modality === MODEL_TYPE;
      } catch (e) {
        return false;
      }
    },
  });
  errorRate.add(!ok);
  inferLatency.add(res.timings.duration);
  sleep(0.01);
}

function percentile(arr, p) {
  if (!arr || arr.length === 0) return 0;
  const sorted = arr.slice().sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, idx)];
}

export function handleSummary(data) {
  const reqs = data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0;
  const failRate =
    data.metrics.http_req_failed && data.metrics.http_req_failed.values.rate != null
      ? data.metrics.http_req_failed.values.rate
      : data.metrics.vulcan_errors && data.metrics.vulcan_errors.values.rate != null
        ? data.metrics.vulcan_errors.values.rate
        : 0;

  const durationMs = data.state.testRunDurationMs || 1;
  const durationSec = durationMs / 1000.0;
  const throughput = reqs / durationSec;

  // Prefer custom trend; fall back to http_req_duration.
  const lat = data.metrics.vulcan_infer_latency_ms || data.metrics.http_req_duration;
  const values = lat ? lat.values : {};
  const p50 = values["p(50)"] != null ? values["p(50)"] : values.med || 0;
  const p95 = values["p(95)"] != null ? values["p(95)"] : 0;
  const p99 = values["p(99)"] != null ? values["p(99)"] : 0;
  const avg = values.avg != null ? values.avg : 0;
  const max = values.max != null ? values.max : 0;

  const result = {
    schema_version: 1,
    backend: BACKEND_NAME,
    modality: MODEL_TYPE,
    model_id: MODEL_ID,
    target_url: BASE_URL,
    started_at: new Date(Date.now() - durationMs).toISOString(),
    duration_seconds: Number(durationSec.toFixed(3)),
    vus: VUS,
    runtime_mode: "cpu",
    notes: "k6 harness (phase-1). GPU runs are manual — see docs/benchmarks/.",
    metrics: {
      requests_total: reqs,
      error_rate: Number(Number(failRate).toFixed(6)),
      throughput_rps: Number(throughput.toFixed(3)),
      latency_ms: {
        p50: Number(Number(p50).toFixed(3)),
        p95: Number(Number(p95).toFixed(3)),
        p99: Number(Number(p99).toFixed(3)),
        avg: Number(Number(avg).toFixed(3)),
        max: Number(Number(max).toFixed(3)),
      },
    },
  };

  // Silence unused helper in older k6 if tree-shaken oddly
  void percentile;

  return {
    [RESULTS_OUT]: JSON.stringify(result, null, 2) + "\n",
    stdout: textSummary(result),
  };
}

function textSummary(result) {
  const m = result.metrics;
  return [
    `vulcan benchmark → ${result.backend} / ${result.modality}`,
    `  target: ${result.target_url}`,
    `  requests: ${m.requests_total}  rps: ${m.throughput_rps}  errors: ${m.error_rate}`,
    `  latency_ms p50/p95/p99: ${m.latency_ms.p50} / ${m.latency_ms.p95} / ${m.latency_ms.p99}`,
    `  wrote: ${RESULTS_OUT}`,
    "",
  ].join("\n");
}
