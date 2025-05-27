# Duo Workflow Service Tools

> **Note**: This documentation was generated with AI assistance to provide comprehensive coverage of the tools architecture and usage patterns.

The Duo Workflow Service Tools are a collection of LangGraph-compatible tools that enable AI agents to interact with GitLab resources and perform complex workflows. These tools form the foundation of GitLab AI-powered automation capabilities.

## How These Tools Work in GitLab

### Backend Service Architecture

These tools are **backend services** that power GitLab AI features in the web interface. Instead, they operate as part of GitLab infrastructure:

```plaintext
Workflow Started
        ↓
GitLab Rails Backend
        ↓
AI Gateway Service (this repository)
        ↓
Duo Workflow Service
        ↓
Tools (duo_workflow_service/tools/)
        ↓
GitLab REST APIs & Local Operations
```

### User Interaction Flow

When users interact with GitLab AI features, these tools execute automatically in the background:

#### **GitLab Duo Chat Example:**

```plaintext
User: "Are there security issues in my latest MR?"

Backend Workflow:
1. get_merge_request → Fetches MR details via /api/v4/projects/{id}/merge_requests/{iid}
2. list_merge_request_diffs → Gets changed files via /api/v4/projects/{id}/merge_requests/{iid}/diffs
3. get_repository_file → Analyzes each changed file via /api/v4/projects/{id}/repository/files/{path}
4. create_merge_request_note → Adds review comments via /api/v4/projects/{id}/merge_requests/{iid}/notes

Result: User sees AI analysis and comments in GitLab web interface
```

#### **Automated Code Review Example:**

```plaintext
User: Creates a merge request in GitLab web interface

Automatic Backend Workflow:
1. list_merge_request_diffs → Analyzes what changed
2. get_repository_file → Reviews modified files
3. create_merge_request_note → Adds AI review comments
4. update_merge_request → Updates labels (e.g., "ai-reviewed")

Result: Review comments and labels appear automatically in the MR
```

### Integration with GitLab Features

| GitLab Feature | User Experience |
|----------------|-----------------|
| **GitLab Duo Chat** | Ask questions, get intelligent responses |
| **AI Code Reviews** | Automatic review comments on MRs |
| **Code Suggestions** | AI-powered code completions in Web IDE |
| **Issue Analysis** | Smart issue recommendations and context |
| **Pipeline Insights** | AI explanations of CI/CD failures |

### Real GitLab API Integration

Each tool makes direct calls to GitLab REST API endpoints:

```python
# Example from merge_request.py
async def _arun(self, **kwargs) -> str:
    # Direct API call to GitLab backend
    response = await self.gitlab_client.aget(
        path=f"/api/v4/projects/{project_id}/merge_requests/{iid}",
        parse_json=False,
    )
    return json.dumps({"merge_request": response})
```

## Architecture Overview

### Core Components

```plaintext
duo_workflow_service/tools/
├── duo_base_tool.py          # Base class for all tools
├── toolset.py               # Tool collection management
├── gitlab_resource_input.py  # Common input schemas
├── search.py                # GitLab search capabilities
├── search_system.py         # Advanced search system
├── repository_files.py      # File operations
├── issue.py                 # Issue management
├── merge_request.py         # Merge request operations
├── pipeline.py              # CI/CD pipeline tools
├── job.py                   # CI/CD job operations
├── commit.py                # Git commit operations
├── git.py                   # Git operations
├── filesystem.py            # File system operations
├── command.py               # Command execution
├── epic.py                  # Epic management
├── project.py               # Project data retrieval
├── planner.py               # Workflow planning
├── handover.py              # Agent handover
├── previous_context.py      # Workflow history access
└── request_user_clarification.py  # User interaction
```

### Tool Architecture Pattern

All tools follow a consistent architecture pattern:

```python
class ExampleTool(DuoBaseTool):
    name: str = "tool_name"                    # Unique tool identifier
    description: str = "Tool description"      # LLM-readable description
    args_schema: Type[BaseModel] = InputModel  # Pydantic input validation

    async def _arun(self, **kwargs) -> str:    # Async execution method
        # Tool implementation
        pass

    def format_display_message(self, args) -> str:  # User-friendly messages
        # Format execution feedback
        pass
```

## Key Advantages

### 1. **LangGraph Integration**

- **Native Compatibility**: Built specifically for LangGraph workflows
- **Agent Orchestration**: Tools can be chained and combined intelligently
- **State Management**: Maintains context across multi-step operations
- **Error Recovery**: Graceful handling of failures with retry mechanisms

### 2. **GitLab-Native Operations**

- **Deep Integration**: Direct access to GitLab APIs with proper authentication
- **Permission Awareness**: Respects GitLab role-based access control
- **Resource Validation**: Built-in URL parsing and resource validation
- **Consistent Error Handling**: Standardized error responses across all tools

### 3. **Extensible Design**

- **Plugin Architecture**: Easy addition of new tools without core changes
- **Composable Operations**: Tools can be combined for complex workflows
- **Configurable Behavior**: Tools adapt to different project/group contexts
- **Type Safety**: Full Pydantic validation for all inputs and outputs

### 4. **Developer Experience**

- **Rich Documentation**: Comprehensive descriptions for LLM understanding
- **Display Messages**: Human-readable execution feedback
- **Error Context**: Detailed error messages with actionable information
- **Debugging Support**: Structured logging and monitoring integration

## Tool Categories

### Search and Discovery

- **`gitlab_*_search`**: Search across issues, MRs, commits, files, users
- **`search_system`**: Advanced search capabilities
- **`previous_context`**: Access to workflow history

### Code and Repository Management

- **`get_repository_file`**: Retrieve file contents
- **`filesystem`**: File system operations
- **`git`**: Git operations
- **`commit`**: Commit analysis and operations

### Project Management

- **`issue`**: Issue creation, updates, and management
- **`merge_request`**: MR operations and reviews
- **`epic`**: Epic management for larger initiatives
- **`pipeline`**: CI/CD pipeline operations

### Workflow Orchestration

- **`planner`**: Workflow planning and task breakdown
- **`handover`**: Agent-to-agent communication
- **`request_user_clarification`**: Interactive user input

## Development and Testing

For comprehensive development instructions, testing strategies, architecture details, and examples of adding new tools, see:

**[📋 Duo Workflow Service Tools Documentation](../duo_workflow_service/tools/README.md)**

### Quick Start

```shell
# Setup development environment
poetry install --with test

# Run all tool tests
poetry run pytest tests/duo_workflow_service/tools/ -v

# Run specific tool tests
poetry run pytest tests/duo_workflow_service/tools/test_repository_files.py -v
```

### Testing Architecture

```plaintext
tests/duo_workflow_service/tools/
├── test_duo_base_tool.py        # Base class functionality
├── test_toolset.py              # Tool collection management
├── test_search.py               # Search tools (parametrized tests)
├── test_search_system.py        # Advanced search system
├── test_repository_files.py     # File operations
├── test_issue.py                # Issue management
├── test_merge_request.py        # MR operations
├── test_pipeline.py             # CI/CD pipeline tools
├── test_job.py                  # CI/CD job operations
├── test_commit.py               # Git operations
├── test_git.py                  # Git operations
├── test_filesystem.py           # File system operations
├── test_run_command.py          # Command execution
├── test_epic.py                 # Epic management
├── test_project.py              # Project data retrieval
├── test_planner.py              # Workflow planning
├── test_previous_context.py     # Workflow history access
└── test_action.py               # Action handling
```

## Contributing

When adding new tools:

1. **Follow the established patterns** in existing tools
1. **Write comprehensive descriptions** for LLM understanding
1. **Include proper error handling** and validation
1. **Add unit and integration tests**
1. **Update documentation** with new tool categories
1. **Consider security implications** of new capabilities

For detailed contribution guidelines, see the [tools documentation](../duo_workflow_service/tools/README.md).
