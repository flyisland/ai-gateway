import http from "k6/http";
import { check, group } from "k6";
import { Rate } from "k6/metrics";
import { WebSocket } from "k6/experimental/websockets";
import {
  logError,
  getRpsThresholds,
  getTtfbThreshold,
} from "../../../lib/gpt_k6_modules.js";

// Common thresholds and metrics
export const commonThresholds = {
  'rps': { 'latest': 0.1 },
  'ttfb': { 'latest': 50000 },
};

export const wsConnectingThreshold = 1500; // 1.5s - based on observed performance with a client in Australia and server in us-east1
export const wsDurationThreshold = 40000; // 40s
export const WORKFLOW_COMPLETE_TIMEOUT = wsDurationThreshold + 10000; // 50s

export function createOptions(thresholds = commonThresholds) {
  const rpsThresholds = getRpsThresholds(thresholds['rps']);
  const ttfbThreshold = getTtfbThreshold(thresholds['ttfb']);

  return {
    thresholds: {
      successful_requests: [`rate>${__ENV.SUCCESS_RATE_THRESHOLD}`],
      checks: [`rate>${__ENV.SUCCESS_RATE_THRESHOLD}`],
      http_req_waiting: [`p(90)<${ttfbThreshold}`],
      ws_connecting: [`p(90)<${wsConnectingThreshold}`],
      ws_session_duration: [`p(90)<${wsDurationThreshold}`],
    },
    rpsThresholds,
    ttfbThreshold
  };
}

export function createSetupFunction(options) {
  return function setup() {
    console.log("");
    console.log(`RPS Threshold: ${options.rpsThresholds["mean"]}/s (${options.rpsThresholds["count"]})`);
    console.log(`TTFB P90 Threshold: ${options.ttfbThreshold}ms`);
    console.log(`Success Rate Threshold: ${parseFloat(__ENV.SUCCESS_RATE_THRESHOLD) * 100}%`);
    console.log(`WebSocket Connecting P90 Threshold: ${wsConnectingThreshold}ms`);
    console.log(`WebSocket Duration P90 Threshold: ${wsDurationThreshold}ms`);
  };
}

function logDebug(...args) {
  if (__ENV.DEBUG === 'true') {
    console.log(...args);
  }
}

export function createDuoWorkflowChatTest(config) {
  const { goal, testName = "API - Duo Agent - Chat", scenarioType } = config;
  const successRate = new Rate("successful_requests");

  // Access token logic
  const access_token = __ENV.AI_ACCESS_TOKEN !== null && __ENV.AI_ACCESS_TOKEN !== undefined
    ? __ENV.AI_ACCESS_TOKEN
    : __ENV.ACCESS_TOKEN;

  return function() {
    // Add scenario type to group name if provided
    const groupName = scenarioType ? `${testName} [${scenarioType}]` : testName;

    group(groupName, function () {
      // Create workflow via GraphQL mutation
      const graphqlQuery = {
        query: `mutation createAiDuoWorkflow(
          $projectId: ProjectID
          $goal: String!
          $workflowDefinition: String!
          $agentPrivileges: [Int!]
          $preApprovedAgentPrivileges: [Int!]
        ) {
          aiDuoWorkflowCreate(
            input: {
              projectId: $projectId
              environment: WEB
              goal: $goal
              workflowDefinition: $workflowDefinition
              agentPrivileges: $agentPrivileges
              preApprovedAgentPrivileges: $preApprovedAgentPrivileges
            }
          ) {
            workflow {
              id
            }
            errors
          }
        }`,
        variables: {
          projectId: `gid://gitlab/Project/${__ENV.AI_DUO_WORKFLOW_PROJECT_ID}`,
          goal: goal,
          workflowDefinition: "chat",
          agentPrivileges: [2, 3],
          preApprovedAgentPrivileges: [2]
        }
      };

      let params = {
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access_token}`,
          "X-GitLab-Interface": "duo_chat",
          "X-GitLab-Client-Type": "web_browser"
        },
      };

      let response = http.post(
        `${__ENV.ENVIRONMENT_URL}/api/graphql`,
        JSON.stringify(graphqlQuery),
        params
      );

      if (!check(response, {'is status 200': (r) => r.status === 200})){
        successRate.add(false);
        logError(response);
        return;
      }

      const responseData = response.json();
      const checkOutput = check(responseData, {
        'verify workflow was created': (r) => r.data?.aiDuoWorkflowCreate?.workflow?.id !== undefined,
        'no graphql errors': (r) => !r.data?.aiDuoWorkflowCreate?.errors || r.data.aiDuoWorkflowCreate.errors.length === 0
      });

      if (!checkOutput) {
        successRate.add(false);
        logError(response);
        return;
      }

      // Extract workflow ID from GraphQL response
      const workflowGid = responseData.data.aiDuoWorkflowCreate.workflow.id;
      const workflowId = workflowGid.split('/').pop();

      // Build websocket URL
      const wsUrl = `${__ENV.ENVIRONMENT_URL.replace(/^http/, 'ws')}/api/v4/ai/duo_workflows/ws?project_id=${__ENV.AI_DUO_WORKFLOW_PROJECT_ID}&root_namespace_id=${__ENV.AI_DUO_WORKFLOW_ROOT_NAMESPACE_ID}`;

      // Connect to websocket to receive workflow responses
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
            workflowID: workflowId,
            clientVersion: "1.0",
            workflowDefinition: "chat",
            goal: goal
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
  };
}

export { Rate };
