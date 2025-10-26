/*global __ENV : true */
/*
@endpoint: `POST /api/v4/ai/duo_workflows/workflows`
@description: API endpoint to begin a Duo Agent workflow for Chat using REST API, then connect via WebSocket to receive messages.
 This test combines REST API workflow initiation with WebSocket-based message retrieval.
 It expects the GitLab instance to have a runner available to act as remote executor.

 For mocked responses, the Duo Workflow Service should be configured with:
 AIGW_MOCK_MODEL_RESPONSES=true
 AIGW_USE_AGENTIC_MOCK=true

 It uses WebSocket connections to receive LLM responses and has thresholds for establishing WebSocket
 connections and for WebSocket session duration.

 The test requires the following environment variables:
 - `ACCESS_TOKEN`: A personal access token with API scope
 - `AI_DUO_WORKFLOW_ROOT_NAMESPACE_ID`: The id of a namespace with Duo Agent Platform enabled
 - `AI_DUO_WORKFLOW_PROJECT_ID`: The id of a project in the above namespace

 Optionally, set `SCENARIO_TYPE=real_llm` for actual LLM responses, otherwise it uses mocked responses by default.

@gpt_data_version: 1
@stressed_components: Duo Workflow Service, Postgres, Rails
*/

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate } from "k6/metrics";
import { WebSocket } from "k6/experimental/websockets";
import {
  logError,
  getRpsThresholds,
  getTtfbThreshold,
} from "../../lib/gpt_k6_modules.js";

// Thresholds and metrics
const commonThresholds = {
  'rps': { 'latest': 0.1 },
  'ttfb': { 'latest': 50000 },
};

const wsConnectingThreshold = 1500; // 1.5s
const wsDurationThreshold = 40000; // 40s
const WORKFLOW_COMPLETE_TIMEOUT = wsDurationThreshold + 10000; // 50s

const rpsThresholds = getRpsThresholds(commonThresholds['rps']);
const ttfbThreshold = getTtfbThreshold(commonThresholds['ttfb']);

export let successRate = new Rate("successful_requests");
export let options = {
  thresholds: {
    successful_requests: [`rate>${__ENV.SUCCESS_RATE_THRESHOLD}`],
    checks: [`rate>${__ENV.SUCCESS_RATE_THRESHOLD}`],
    http_req_waiting: [`p(90)<${ttfbThreshold}`],
    ws_connecting: [`p(90)<${wsConnectingThreshold}`],
    ws_session_duration: [`p(90)<${wsDurationThreshold}`],
  },
};

// Test configuration
const scenarioType = __ENV.SCENARIO_TYPE || 'mocked_llm';

const testConfigs = {
  real_llm: {
    goal: "I am new to this project. Could you read the project structure and explain it to me?",
    testName: "API - Duo Agent - Chat Hybrid (Real LLM)",
    scenarioType: 'real_llm'
  },
  mocked_llm: {
    goal: `
Multiple tool calls test
<response latency_ms='2432'>I need to search for data to complete this task.
<tool_calls>[{"name": "test_search", "args": {"query": "workflow execution test"}}]</tool_calls>
Initiating search...</response>
<response latency_ms='5432'>Now I'll analyze the search results.
<tool_calls>[{"name": "test_analysis", "args": {"query": "search results analysis"}}]</tool_calls>
Performing analysis...</response>
<response latency_ms='5678'>
Analysis complete. The workflow graph execution test is successful.</response>
`,
    testName: "API - Duo Agent - Chat Hybrid (Mocked Responses)",
    scenarioType: 'mocked_llm'
  }
};

// Get configuration for the selected scenario
const config = testConfigs[scenarioType];
if (!config) {
  throw new Error(`Unknown scenario type: ${scenarioType}. Valid options: real_llm, mocked_llm`);
}

// Access token logic
const access_token = __ENV.AI_ACCESS_TOKEN !== null && __ENV.AI_ACCESS_TOKEN !== undefined
  ? __ENV.AI_ACCESS_TOKEN
  : __ENV.ACCESS_TOKEN;

export function setup() {
  console.log("");
  console.log(`RPS Threshold: ${rpsThresholds["mean"]}/s (${rpsThresholds["count"]})`);
  console.log(`TTFB P90 Threshold: ${ttfbThreshold}ms`);
  console.log(`Success Rate Threshold: ${parseFloat(__ENV.SUCCESS_RATE_THRESHOLD) * 100}%`);
  console.log(`WebSocket Connecting P90 Threshold: ${wsConnectingThreshold}ms`);
  console.log(`WebSocket Duration P90 Threshold: ${wsDurationThreshold}ms`);
}

function logDebug(...args) {
  if (__ENV.DEBUG === 'true') {
    console.log(...args);
  }
}

export default function () {
  const groupName = config.scenarioType ? `${config.testName} [${config.scenarioType}]` : config.testName;

  group(groupName, function () {
    // Step 1: Create workflow via REST API
    let params = {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${access_token}`,
      },
    };

    let body = {
      project_id: __ENV.AI_DUO_WORKFLOW_PROJECT_ID,
      goal: config.goal,
      start_workflow: true,
      workflow_definition: "chat",
      allow_agent_to_request_user: false,
      pre_approved_agent_privileges: [1,2,3,4,5],
      agent_privileges: [1,2,3,4,5]
    };

    let response = http.post(
      `${__ENV.ENVIRONMENT_URL}/api/v4/ai/duo_workflows/workflows`,
      JSON.stringify(body),
      params
    );

    if (!check(response, {'is status 201': (r) => r.status === 201})){
      successRate.add(false);
      logError(response);
      return;
    }

    const checkOutput = check(response, {
      'verify that a workload id was provided for created job': (r) => r.json().workload.id !== undefined,
      'verify response has a created status': (r) => r.json().status == "created"
    });

    if (!checkOutput) {
      successRate.add(false);
      logError(response);
      return;
    }

    // Extract workflow ID from REST API response
    const workflowId = response.json().id;
    logDebug(`Created workflow with ID: ${workflowId}`);

    // Step 2: Poll workflow status until it's no longer in CREATED state
    const workflowGid = `gid://gitlab/Ai::DuoWorkflows::Workflow/${workflowId}`;
    const statusQuery = {
      query: `query getDuoWorkflowEvents($workflowId: AiDuoWorkflowsWorkflowID!) {
        duoWorkflowEvents(workflowId: $workflowId) {
          nodes {
            checkpoint
            errors
            workflowGoal
            workflowStatus
          }
        }
        duoWorkflowWorkflows(workflowId: $workflowId) {
          nodes {
            id
            status
          }
        }
      }`,
      variables: {
        workflowId: workflowGid
      }
    };

    let workflowReady = false;
    let pollAttempts = 0;
    const maxPollAttempts = 30;
    const pollInterval = 1000; // 1s between polls

    sleep(30); // It takes at least 30 seconds for a workflow to start running in a remote executor

    while (!workflowReady && pollAttempts < maxPollAttempts) {
      const statusResponse = http.post(
        `${__ENV.ENVIRONMENT_URL}/api/graphql`,
        JSON.stringify(statusQuery),
        params
      );

      if (statusResponse.status === 200) {
        const statusData = statusResponse.json();
        const workflows = statusData.data?.duoWorkflowWorkflows?.nodes;

        if (workflows && workflows.length > 0) {
          const currentStatus = workflows[0].status;
          logDebug(`Workflow status (attempt ${pollAttempts + 1}): ${currentStatus}`);

          if (currentStatus === 'RUNNING') {
            workflowReady = true;
            logDebug('Workflow is running, proceeding to WebSocket connection');
          }
        }
      }

      if (!workflowReady) {
        pollAttempts++;
        if (pollAttempts < maxPollAttempts) {
          sleep(pollInterval / 1000);
        }
      }
    }

    if (!workflowReady) {
      console.error(`Workflow did not start after ${maxPollAttempts} attempts`);
      check(null, {
        'workflow started processing': () => false
      });
      successRate.add(false);
      return;
    }

    // Step 3: Connect to WebSocket to receive messages
    const wsUrl = `${__ENV.ENVIRONMENT_URL.replace(/^http/, 'ws')}/api/v4/ai/duo_workflows/ws?project_id=${__ENV.AI_DUO_WORKFLOW_PROJECT_ID}&root_namespace_id=${__ENV.AI_DUO_WORKFLOW_ROOT_NAMESPACE_ID}`;

    const ws = new WebSocket(wsUrl, null, {
      headers: {
        Authorization: `Bearer ${access_token}`,
      },
    });
    ws.binaryType = 'blob';

    let receivedMessages = 0;
    let hasError = false;
    let workflowCompleted = false;

    ws.addEventListener('open', () => {
      logDebug('WebSocket connected');

      const startRequest = {
        startRequest: {
          workflowID: String(workflowId),
          clientVersion: "1.0",
          workflowDefinition: "chat",
          goal: ""
        }
      };

      ws.send(JSON.stringify(startRequest));

      ws.addEventListener('message', async (event) => {
        try {
          logDebug('Received message, data type:', typeof event.data);

          const messageText = typeof event.data === 'string' ? event.data : await event.data.text();
          logDebug('Message text:', messageText.substring(0, 100));

          const data = JSON.parse(messageText);
          logDebug('Parsed data:', JSON.stringify(data).substring(0, 200));

          // Messages are found in workflow checkpoint updates
          if (data.newCheckpoint && data.newCheckpoint.checkpoint) {
            const checkpoint = JSON.parse(data.newCheckpoint.checkpoint);

            if (checkpoint.channel_values && checkpoint.channel_values.ui_chat_log) {
              receivedMessages = checkpoint.channel_values.ui_chat_log.length;
              logDebug(`Received ${receivedMessages} chat messages`);
            }

            if (data.newCheckpoint.status) {
              const status = data.newCheckpoint.status.toLowerCase();
              logDebug(`Workflow status: ${data.newCheckpoint.status}`);

              // Mark workflow as completed for valid end states
              if (status === 'completed' || status === 'failed' || status === 'input_required') {
                workflowCompleted = true;
              }
            }
          }
        } catch (err) {
          console.error('Error parsing websocket message:', err.message || err.toString());
          console.error('Error stack:', err.stack);
          hasError = true;
          ws.close();
        }
      });

      ws.addEventListener('error', (err) => {
        console.error('WebSocket error:', err);
        hasError = true;
      });

      const timeoutId = setTimeout(() => {
        if (!workflowCompleted) {
          console.log('Timeout reached, closing connection');
          ws.close();
        }
      }, WORKFLOW_COMPLETE_TIMEOUT);

      ws.addEventListener('close', () => {
        clearTimeout(timeoutId);
        logDebug('WebSocket closed');

        const wsCheckOutput = check(null, {
          'received workflow messages via websocket': () => receivedMessages > 0,
          'workflow completed successfully': () => workflowCompleted,
          'no websocket errors': () => !hasError
        });

        wsCheckOutput ? successRate.add(true) : successRate.add(false);
      });
    });
  });
}
