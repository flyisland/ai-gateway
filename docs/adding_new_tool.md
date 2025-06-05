# Adding a New Tool to Duo Workflow Service

This guide provides step-by-step instructions for implementing and integrating a new tool into the GitLab Duo Workflow Service.

## Overview

The Duo Workflow Service uses a modular tool system to provide AI agents with the ability to perform various operations. Tools are implemented as Python classes and are organized by functionality.

## Prerequisites

Before adding a new tool, ensure you have:

- Understanding of the tool's purpose and required functionality
- Familiarity with GitLab Duo Workflow Service architecture
- Development environment set up for the project

## Implementation Steps

### 1. Design Your Tool

Before writing any code, clearly define:

- What your tool will do
- What inputs it requires
- What outputs it will produce
- What permissions or agent privileges it needs

### 2. Create the Tool Class

1. **Choose the Right Location**:
   - Create a new file in `duo_workflow_service/tools/` for a new category of tools
   - Or add to an existing file for related functionality

2. **Define Input Schema**:
   Create a Pydantic model for your tool's input parameters:

   ```python
   from pydantic import BaseModel, Field
   
   class YourToolInput(BaseModel):
       param1: str = Field(description="Description of the first parameter")
       param2: int = Field(description="Description of the second parameter")
       optional_param: str = Field(None, description="Description of an optional parameter")
   ```

3. **Implement the Tool Class**:
   Extend the `DuoBaseTool` class:

   ```python
   from typing import Type
   
   from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
   from contract import contract_pb2
   from duo_workflow_service.executor.action import _execute_action
   
   class YourTool(DuoBaseTool):
       name: str = "your_tool_name"
       description: str = """
       Detailed description of what your tool does.
       Include usage examples and any important notes.
       """
       args_schema: Type[BaseModel] = YourToolInput  # type: ignore
       
       async def _arun(self, param1: str, param2: int, optional_param: str = None) -> str:
           # Implement the tool logic here
           
           # If interacting with the executor:
           return await _execute_action(
               self.metadata,  # type: ignore
               contract_pb2.Action(
                   yourToolAction=contract_pb2.YourToolAction(
                       param1=param1,
                       param2=param2,
                       optionalParam=optional_param or "",
                   )
               ),
           )
           
           # If interacting with GitLab API:
           # result = await self.gitlab_client.make_request(...)
           # return result
           
       def format_display_message(self, args: YourToolInput) -> str:
           # Format a user-friendly message for the UI
           return f"Performing action with {args.param1}"
   ```

### 3. Update Protocol Buffers (if needed)

If your tool requires communication with the Duo Workflow Executor, you'll need to update the protocol buffer definitions:

1. **Edit Contract Definition**:
   Modify `contract/contract.proto` to add your new action:

   ```protobuf
   message YourToolAction {
     string param1 = 1;
     int32 param2 = 2;
     string optional_param = 3;
   }
   
   message Action {
     // Existing actions...
     oneof action {
       // Other actions...
       YourToolAction yourToolAction = 123; // Use next available number
     }
   }
   ```

2. **Generate Protobuf Files**:
   ```bash
   make gen-proto
   ```

### 4. Register the Tool

Add your tool to the appropriate list in `duo_workflow_service/components/tools_registry.py`:

```python
from duo_workflow_service.tools.your_tool_file import YourTool

# For read-only tools
_READ_ONLY_GITLAB_TOOLS: list[Type[BaseTool]] = [
    # Existing tools...
    YourTool,
]

# For read-write tools
_AGENT_PRIVILEGES: dict[str, list[Type[BaseTool]]] = {
    "read_write_files": [
        # Existing tools...
    ],
    "use_git": [
        # Existing tools...
    ],
    "read_write_gitlab": [
        # Existing tools...
        YourTool,  # Add here if it modifies GitLab resources
    ],
    "read_only_gitlab": [
        # Existing tools...
        YourTool,  # Add here if it only reads GitLab resources
    ],
    "run_commands": [
        # Existing tools...
    ],
}
```

### 5. Add the Tool to Workflows

Add your tool to the appropriate workflow tool lists in:
- `duo_workflow_service/workflows/software_development/workflow.py` (for executor tools)
- `duo_workflow_service/workflows/chat/workflow.py` (for chat tools)

```python
EXECUTOR_TOOLS = [
    # Existing tools...
    "your_tool_name",
]

# Or for context builder tools
CONTEXT_BUILDER_TOOLS = [
    # Existing tools...
    "your_tool_name",
]
```

### 6. Write Tests

Create unit tests for your tool in the `tests/duo_workflow_service/tools/` directory:

```python
# tests/duo_workflow_service/tools/test_your_tool.py
import pytest
from unittest.mock import AsyncMock, patch

from duo_workflow_service.tools.your_tool_file import YourTool, YourToolInput

@pytest.fixture
def tool():
    return YourTool(
        metadata={
            "gitlab_client": AsyncMock(),
            "gitlab_host": "gitlab.com",
        }
    )

@patch("duo_workflow_service.executor.action._execute_action")
async def test_your_tool(mock_execute_action, tool):
    # Setup
    mock_execute_action.return_value = "Success!"
    
    # Execute
    result = await tool._arun(param1="test", param2=123)
    
    # Assert
    assert result == "Success!"
    mock_execute_action.assert_called_once()
    # Add more assertions based on your tool's behavior
```

## Best Practices

1. **Follow Naming Conventions**:
   - Use descriptive names for your tool and input classes
   - Use snake_case for tool names (e.g., `get_file_content`, `update_issue`)
   - Use PascalCase for classes (e.g., `GetFileContent`, `UpdateIssue`)

2. **Write Clear Documentation**:
   - Provide detailed descriptions for your tool
   - Document parameters thoroughly with examples
   - Explain any side effects or permissions required

3. **Error Handling**:
   - Handle errors gracefully and provide useful error messages
   - Validate inputs before executing operations
   - Return clear error information to the agent

4. **Security Considerations**:
   - Add the tool to the appropriate privilege group based on what it does
   - Consider whether the tool should require human approval before execution
   - Sanitize and validate all inputs to prevent injection attacks

5. **Performance**:
   - Keep tools focused on a single responsibility
   - Optimize for minimal API calls when possible
   - Use async properly to avoid blocking operations

## Example Implementation

Here's a complete example of a simple tool that retrieves repository statistics:

```python
from typing import Type

from pydantic import BaseModel, Field

from duo_workflow_service.tools.duo_base_tool import DuoBaseTool, ProjectURLValidationResult


class RepoStatsInput(BaseModel):
    project_id: int = None
    url: str = None


class GetRepositoryStats(DuoBaseTool):
    name: str = "get_repository_stats"
    description: str = """
    Get statistics about a repository like number of commits, branches, etc.
    
    To identify a repository you must provide either:
    - project_id parameter, or
    - A GitLab URL like:
      - https://gitlab.com/namespace/project
      - https://gitlab.com/group/subgroup/project
    """
    args_schema: Type[BaseModel] = RepoStatsInput  # type: ignore
    
    async def _arun(self, project_id: int = None, url: str = None) -> str:
        # Validate inputs
        validation_result: ProjectURLValidationResult = self._validate_project_url(url, project_id)
        if validation_result.errors:
            return "\n".join(validation_result.errors)
        
        project_id = validation_result.project_id
        
        # Make GitLab API request
        result = await self.gitlab_client.make_request(
            "GET", f"/api/v4/projects/{project_id}"
        )
        
        if result.status_code != 200:
            return f"Error fetching repository stats: {result.status_code} {result.reason}"
        
        data = result.json()
        
        # Format the response
        return f"""
        Repository Statistics for {data['name']}:
        - Stars: {data['star_count']}
        - Forks: {data['forks_count']}
        - Open Issues: {data['open_issues_count']}
        - Last Activity: {data['last_activity_at']}
        - Default Branch: {data['default_branch']}
        """
    
    def format_display_message(self, args: RepoStatsInput) -> str:
        if args.url:
            return f"Getting repository stats for {args.url}"
        return f"Getting repository stats for project ID {args.project_id}"
```

## Troubleshooting

### Common Issues

1. **Tool Not Appearing in Agent Interface**:
   - Verify the tool is registered in `tools_registry.py`
   - Check that the tool name is included in the appropriate workflow tool list
   - Ensure the workflow is using the right agent privileges

2. **Tool Failing to Execute**:
   - Check for missing parameters in the tool call
   - Verify the GitLab client is properly configured
   - Look for API permission issues

3. **Protocol Buffer Errors**:
   - Make sure you've regenerated the protocol buffers with `make gen-proto`
   - Check that your action is properly defined in the proto file
   - Verify field numbers don't conflict with existing ones

## Conclusion

Adding a new tool to the Duo Workflow Service involves implementing the tool class, potentially updating protocol buffers, registering the tool, and updating workflow configurations. By following this guide, you should be able to successfully integrate your new tool into the system.

Remember to thoroughly test your tool before deploying it to production, as tools are a critical part of the AI agent's capabilities and directly impact user experience.