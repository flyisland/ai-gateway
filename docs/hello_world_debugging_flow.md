# Hello World Debugging Flow and Tool

This directory contains a simple debugging flow and tool for GitLab Duo Workflow Service that can be used to test and debug flow execution.

## Components Created

### 1. HelloWorld Tool (`duo_workflow_service/tools/hello_world.py`)

A simple debugging tool that:
- Returns a greeting message with an emoji (🎉)
- Accepts an optional custom message parameter
- Provides clear display messages for the UI
- Is designed to be easily identifiable in logs and traces

**Usage:**
```python
from duo_workflow_service.tools.hello_world import HelloWorld

tool = HelloWorld()
result = await tool._arun("Testing the flow!")
# Returns: "🎉 Testing the flow!"
```

### 2. Hello World Flow (`duo_workflow_service/agent_platform/experimental/flows/configs/hello_world.yml`)

An Interactive Chat Flow that:
- Uses the `hello_world` tool to verify tool execution works
- Provides clear feedback about flow execution
- Uses a local prompt (defined in the YAML file)
- Is configured for the `ide` environment for interactive debugging

**Features:**
- **Environment**: `ide` - for interactive debugging sessions
- **Component Type**: `AgentComponent` - AI-powered agent that can use tools
- **Toolset**: `["hello_world"]` - only includes the debugging tool
- **UI Logging**: Captures tool execution success/failure and agent responses

### 3. Test Coverage (`tests/duo_workflow_service/tools/test_hello_world.py`)

Comprehensive tests covering:
- Default message behavior
- Custom message handling
- Display message formatting
- Tool properties validation
- Error handling

## How to Use

### Running the Flow

1. **Set up local Agent Platform** following the [Agent Platform documentation](https://gitlab.com/gitlab-org/gitlab-development-kit/-/blob/main/doc/howto/duo_agent_platform.md)

2. **Start the flow** using curl:
```bash
export DEFINITION="hello_world/experimental"
export GOAL="Test the debugging flow"
export PROJECT_ID="10000"

curl -X POST \
    -H "Authorization: Bearer $GDK_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"project_id\": \"$PROJECT_ID\",
        \"agent_privileges\": [1,2,3,4,5],
        \"goal\": \"$GOAL\",
        \"start_workflow\": true,
        \"workflow_definition\": \"$DEFINITION\",
        \"environment\": \"ide\",
        \"source_branch\": \"main\"
    }" \
    http://gdk.test:3443/api/v4/ai/duo_workflows/workflows
```

### Running as a default chat flow tool

1. Open GDK window with **GitLab Duo Agentic Chat**
1. Ask it `What tools do you have available?` and confirm that `Hello world` is listed
1. Reply `Run Hello world` and it should reply with

```
Hello, World! 🎉
The hello world tool is working perfectly. This is a simple debugging tool that confirms the tool system is functioning correctly. Is there anything specific you'd like to work on with your GitLab project?
```

### Debugging Features

- **Easy Identification**: The tool name `hello_world` and emoji output make it easy to spot in logs
- **Clear Feedback**: The agent provides detailed information about what's happening
- **Tool Verification**: Demonstrates that tool calling is working correctly
- **Flow Validation**: Confirms that the entire flow execution pipeline is functional

### Expected Behavior

When the flow runs, you should see:
1. The agent receives the debugging request
2. The agent calls the `hello_world` tool
3. The tool returns a greeting with emoji
4. The agent provides a summary of the debugging session
5. UI logs show successful tool execution

## Integration Details

### Tool Registration

The `HelloWorld` tool is registered in the `read_only_gitlab` privilege group in `duo_workflow_service/components/tools_registry.py`, making it:
- Available to flows with GitLab read permissions
- Pre-approved (no human approval required)
- Safe for debugging purposes

### Security Considerations

- **No External Dependencies**: The tool doesn't make any external API calls
- **No File System Access**: The tool doesn't read or write files
- **No Sensitive Data**: The tool only processes simple text messages
- **Read-Only Classification**: Registered as a read-only tool with minimal security risk

## Troubleshooting

If the flow doesn't work as expected:

1. **Check Tool Registration**: Verify `hello_world` appears in the tools registry
2. **Verify Flow Configuration**: Ensure the YAML syntax is correct
3. **Check Logs**: Look for the `hello_world` tool execution in Agent Platform logs
4. **Test Tool Directly**: Run the tool tests to ensure basic functionality works

## Testing

Run the tests to verify everything works:

```bash
# Test the tool
poetry run pytest tests/duo_workflow_service/tools/test_hello_world.py -v

# Test tools registry integration
poetry run pytest tests/duo_workflow_service/components/test_tools_registry.py -v

# Test flow configuration
poetry run pytest tests/duo_workflow_service/agent_platform/experimental/flows/ -v
```

All tests should pass, confirming that the debugging flow and tool are properly integrated and functional.