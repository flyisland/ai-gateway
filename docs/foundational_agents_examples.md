# Foundational Agents Examples

This document provides examples of how to work with foundational agents in the Duo Workflow Service, including filtering, configuration, and usage patterns.

## What are Foundational Agents?

Foundational agents are specialized flows designed for the AI Catalog that:
- Use the "chat-partial" environment
- Are typically versioned as "v1" 
- Provide focused, reusable AI capabilities
- Can be easily integrated into various workflows

## Filtering Foundational Agents

### Using grpcurl

#### List All Foundational Agents

```bash
grpcurl -plaintext -d '{"filters": {"environment": ["chat-partial"]}}' localhost:50052 DuoWorkflow/ListFlows
```

#### List Foundational Agents with Specific Version

```bash
grpcurl -plaintext -d '{"filters": {"environment": ["chat-partial"], "version": ["v1"]}}' localhost:50052 DuoWorkflow/ListFlows
```

#### List Specific Foundational Agents by Name

```bash
grpcurl -plaintext -d '{"filters": {"name": ["foundational_agent_example", "code_assistant_foundational_agent"], "environment": ["chat-partial"]}}' localhost:50052 DuoWorkflow/ListFlows
```

### Using Python Client

```python
import grpc
from contract import contract_pb2, contract_pb2_grpc

# Create gRPC channel
channel = grpc.insecure_channel('localhost:50052')
stub = contract_pb2_grpc.DuoWorkflowStub(channel)

# Create filter for foundational agents
filters = contract_pb2.ListFlowsRequestFilter(
    environment=["chat-partial"],
    version=["v1"]
)

# Make request
request = contract_pb2.ListFlowsRequest(filters=filters)
response = stub.ListFlows(request)

# Process results
for config in response.configs:
    print(f"Found foundational agent: {config}")
```

### Using Node.js Client

```javascript
const grpc = require('@grpc/grpc-js');
const { DuoWorkflowClient } = require('@gitlab-org/duo-workflow-service');

const client = new DuoWorkflowClient('localhost:50052', grpc.credentials.createInsecure());

// Filter for foundational agents
const request = {
  filters: {
    environment: ['chat-partial'],
    version: ['v1']
  }
};

client.listFlows(request, (error, response) => {
  if (error) {
    console.error('Error:', error);
    return;
  }
  
  console.log('Foundational agents:', response.configs);
});
```

## Example Foundational Agent Configurations

### General Purpose Foundational Agent

```yaml
version: "v1"
environment: chat-partial
components:
  - name: "foundational_agent"
    type: AgentComponent
    prompt_id: "chat_react"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:goal"
        as: "user_message"
    toolset:
      - "get_merge_request"
      - "list_merge_request_diffs"
      - "get_repository_file"
      - "read_file"
      - "get_issue"
      - "list_issues"
      - "search_system"
      - "documentation_search"
    ui_log_events:
      - "on_tool_execution_success"
      - "on_tool_execution_failed"
      - "on_agent_final_answer"

routers:
  - from: "foundational_agent"
    to: "end"

flow:
  entry_point: "foundational_agent"
  inputs:
    - category: "user_input"
      input_schema:
        message:
          type: "string"
          description: "User's question or request"
```

### Code Assistant Foundational Agent

```yaml
version: "v1"
environment: chat-partial
components:
  - name: "code_assistant"
    type: AgentComponent
    prompt_id: "chat_react"
    prompt_version: "^1.0.0"
    inputs:
      - from: "context:goal"
        as: "user_message"
    toolset:
      - "get_repository_file"
      - "read_file"
      - "list_repository_tree"
      - "find_files"
      - "blob_search"
      - "get_commit"
      - "list_commits"
    ui_log_events:
      - "on_tool_execution_success"
      - "on_tool_execution_failed"
      - "on_agent_final_answer"

routers:
  - from: "code_assistant"
    to: "end"

flow:
  entry_point: "code_assistant"
  inputs:
    - category: "code_context"
      input_schema:
        request:
          type: "string"
          description: "Code-related question or task"
```

## Integration Patterns

### Rails Integration for AI Catalog

When integrating with Rails for the AI Catalog, use the filtering to retrieve only foundational agents:

```ruby
# Example Rails service class
class FoundationalAgentsService
  def self.list_foundational_agents
    # gRPC call to list foundational agents
    filters = {
      environment: ['chat-partial'],
      version: ['v1']
    }
    
    # Make gRPC call and return results
    # Implementation depends on your gRPC client setup
  end
end
```

### Filtering by Capability

You can organize foundational agents by their capabilities and filter accordingly:

```bash
# List code-focused foundational agents
grpcurl -plaintext -d '{"filters": {"name": ["code_assistant_foundational_agent", "code_review_agent"], "environment": ["chat-partial"]}}' localhost:50052 DuoWorkflow/ListFlows

# List general purpose foundational agents
grpcurl -plaintext -d '{"filters": {"name": ["foundational_agent_example", "general_assistant"], "environment": ["chat-partial"]}}' localhost:50052 DuoWorkflow/ListFlows
```

## Best Practices

### Naming Conventions

- Use descriptive names that indicate the agent's purpose
- Include "foundational" or "agent" in the name for clarity
- Use snake_case for consistency

### Configuration Guidelines

1. **Environment**: Always use "chat-partial" for foundational agents
2. **Version**: Use semantic versioning (e.g., "v1", "v2")
3. **Toolset**: Include only the tools necessary for the agent's specific purpose
4. **Input Schema**: Define clear input schemas for better integration

### Performance Considerations

- Use specific filters to reduce response size
- Cache results when possible
- Consider pagination for large result sets

## Troubleshooting

### No Results Returned

If filtering returns no results:

1. Verify the filter criteria match existing flows
2. Check that foundational agents exist with the specified environment
3. Ensure the service is running and accessible

### Common Filter Combinations

```bash
# Debug: List all flows to see what's available
grpcurl -plaintext -d '{}' localhost:50052 DuoWorkflow/ListFlows

# Debug: List all chat-partial flows
grpcurl -plaintext -d '{"filters": {"environment": ["chat-partial"]}}' localhost:50052 DuoWorkflow/ListFlows

# Debug: List all v1 flows
grpcurl -plaintext -d '{"filters": {"version": ["v1"]}}' localhost:50052 DuoWorkflow/ListFlows
```