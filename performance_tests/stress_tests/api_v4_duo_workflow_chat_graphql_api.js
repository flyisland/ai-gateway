/*global __ENV : true */
/*
@endpoint: `POST /api/v4/ai/duo_workflows/workflows`
@description: API endpoint to begin a Duo Agent workflow for Chat using k6 scenarios.
 This test can run both real LLM responses and mocked responses based on scenario configuration.

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

import {
  createOptions,
  createSetupFunction,
  createDuoWorkflowChatTest,
  Rate
} from "./lib/duo_workflow_chat_base.js";

// Test configuration - use env var to determine which test to run
const scenarioType = __ENV.SCENARIO_TYPE || 'mocked_llm';

const testConfigs = {
  real_llm: {
    goal: "I am new to this project. Could you read the project structure and explain it to me?",
    testName: "API - Duo Agent - Chat (Real LLM)",
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
    testName: "API - Duo Agent - Chat (Mocked Responses)",
    scenarioType: 'mocked_llm'
  }
};

// Get configuration for the selected scenario
const config = testConfigs[scenarioType];
if (!config) {
  throw new Error(`Unknown scenario type: ${scenarioType}. Valid options: real_llm, mocked_llm`);
}

// Setup exports
const optionsConfig = createOptions();

export let options = {
  thresholds: optionsConfig.thresholds
};
export let successRate = new Rate("successful_requests");
export let rpsThresholds = optionsConfig.rpsThresholds;
export let ttfbThreshold = optionsConfig.ttfbThreshold;

// Setup function
export const setup = createSetupFunction(optionsConfig);

// Main test function - uses the selected scenario configuration
export default createDuoWorkflowChatTest(config);
