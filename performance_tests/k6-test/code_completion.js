import http from 'k6/http';
import { check, sleep } from 'k6';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';
export const TTFB_THRESHOLD= 25;
export const RPS_THRESHOLD= 2;
export const TEST_NAME='v2_code_completions'
export const MR_IID = __ENV.PARENT_PIPELINE_MR_IID || 'unknown';
export const COMMIT_SHA = __ENV.COMPONENT_MR_CI_COMMIT_SHA || 'unknown';

export const options = {
  vus: 2, // Number of virtual users
  duration: '60s', // Test duration
};

export default function () {
  const url = `http://${__ENV.AI_GATEWAY_IP}:5052/v2/code/completions`; // Replace with your API endpoint
  const payload = JSON.stringify({
    "project_path": "string",
    "project_id": 0,
    "current_file": {
      "file_name": "test",
      "language_identifier": "string",
      "content_above_cursor": "func hello_world(){\n\t",
      "content_below_cursor": "\n}"
    },
    "stream": true,
    "choices_count": 0,
    "context": [],
    "prompt_id": "code_suggestions/generations",
    "prompt_version": 2
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  const res = http.post(url, payload, params);

  console.log(`Request ${__ITER}: ${res.request.method} ${res.request.url} - Status ${res.status} - Duration ${res.timings.duration}ms`);

  sleep(1);
}

export function handleSummary(data) {
  const SUMMARY_OUTPUT_PATH = `results/${TEST_NAME}.json`;
  console.log(data.metrics.http_reqs)  
  
  // Create structured log entries
  const structuredLogs = {
    test_execution: {
      timestamp: new Date().toISOString(),
      level: "info",
      service: "k6-performance-test",
      test_name: TEST_NAME,
      gitlab_mr_iid: MR_IID,
      gitlab_commit_sha: COMMIT_SHA,
      message: "Performance test execution completed",
      metrics: {
        http_requests_rate: data.metrics.http_reqs.values["rate"],
        ttfb_avg_ms: data.metrics.http_req_waiting.values["avg"],
        ttfb_p90_ms: data.metrics.http_req_waiting.values["p(90)"],
        http_req_duration_avg_ms: data.metrics.http_req_duration.values["avg"],
        http_req_duration_p90_ms: data.metrics.http_req_duration.values["p(90)"],
        http_req_failed_rate: data.metrics.http_req_failed.values["rate"]
      },
      status: data.metrics.http_req_waiting.values["p(90)"] < TTFB_THRESHOLD && 
              data.metrics.http_reqs.values["rate"] > RPS_THRESHOLD ? "passed" : "failed"
    }
  };

  // Log to console in structured format
  console.log(JSON.stringify(structuredLogs.test_execution));


  // Create an object for the return value
  const summaryOutput = {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }) +
              `\nConstants:\n` +
              `TTFB_THRESHOLD: ${TTFB_THRESHOLD}\n` +
              `RPS_THRESHOLD: ${RPS_THRESHOLD}\n` +
              `VUs: ${options.vus}\n` +
              `Duration: ${options.duration}\n`+
              `TTFB p90: ${data.metrics.http_req_waiting.values["p(90)"]}ms\n`+
              `TTFB Avg: ${data.metrics.http_req_waiting.values["avg"]}ms\n`+
              `http_requests: ${data.metrics.http_reqs.values["rate"]}\n`+
              `MR IID: ${MR_IID}\n`+
              `Commit SHA: ${COMMIT_SHA}\n,`
  };

  // Add the JSON output using the variable path
  summaryOutput[SUMMARY_OUTPUT_PATH] = JSON.stringify({
    metrics: data.metrics,
    constants: {
      ttfb_threshold: TTFB_THRESHOLD,
      rps_threshold: RPS_THRESHOLD,
      vus: options.vus,
      duration: options.duration,
      gitlab_mr_iid: MR_IID,
      gitlab_commit_sha: COMMIT_SHA
    }
  }, null, 2);

  return summaryOutput;
}
