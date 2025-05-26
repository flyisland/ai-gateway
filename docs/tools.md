# Duo Workflow Service Tools

The Duo Workflow Service Tools are a collection of LangGraph-compatible tools that enable AI agents to interact with GitLab resources and perform complex workflows. These tools form the foundation of GitLab's AI-powered automation capabilities.

## How These Tools Work in GitLab

### Backend Service Architecture

These tools are **backend services** that power GitLab's AI features in the web interface. They do **not** run in IDEs or local development environments. Instead, they operate as part of GitLab's infrastructure:

```
GitLab Web UI (Frontend)
        ↓
GitLab Rails Backend
        ↓
AI Gateway Service (this repository)
        ↓
Duo Workflow Service
        ↓
Tools (duo_workflow_service/tools/)
        ↓
GitLab REST APIs & External Services
```

### User Interaction Flow

When users interact with GitLab's AI features, these tools execute automatically in the background:

#### **GitLab Duo Chat Example:**
```
User: "Are there security issues in my latest MR?"

Backend Workflow:
1. get_merge_request → Fetches MR details via /api/v4/projects/{id}/merge_requests/{iid}
2. list_merge_request_diffs → Gets changed files via /api/v4/projects/{id}/merge_requests/{iid}/diffs
3. get_repository_file → Analyzes each changed file via /api/v4/projects/{id}/repository/files/{path}
4. (Future) gitlab_security_scanner → Scans for vulnerabilities
5. create_merge_request_note → Adds review comments via /api/v4/projects/{id}/merge_requests/{iid}/notes

Result: User sees AI analysis and comments in GitLab's web interface
```

#### **Automated Code Review Example:**
```
User: Creates a merge request in GitLab web interface

Automatic Backend Workflow:
1. list_merge_request_diffs → Analyzes what changed
2. get_repository_file → Reviews modified files
3. create_merge_request_note → Adds AI review comments
4. update_merge_request → Updates labels (e.g., "ai-reviewed")

Result: Review comments and labels appear automatically in the MR
```

### Integration with GitLab Features

| GitLab Feature | Tools Used | User Experience |
|----------------|------------|-----------------|
| **GitLab Duo Chat** | `search`, `get_repository_file`, `issue`, `merge_request` | Ask questions, get intelligent responses |
| **AI Code Reviews** | `list_merge_request_diffs`, `get_repository_file`, `create_merge_request_note` | Automatic review comments on MRs |
| **Code Suggestions** | `get_repository_file`, `search` | AI-powered code completions in Web IDE |
| **Issue Analysis** | `issue`, `search`, `get_repository_file` | Smart issue recommendations and context |
| **Pipeline Insights** | `pipeline`, `commit`, `get_repository_file` | AI explanations of CI/CD failures |

### Real GitLab API Integration

Each tool makes direct calls to GitLab's REST API endpoints:

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

```
duo_workflow_service/tools/
├── duo_base_tool.py          # Base class for all tools
├── toolset.py               # Tool collection management
├── gitlab_resource_input.py  # Common input schemas
├── search.py                # GitLab search capabilities
├── repository_files.py      # File operations
├── issue.py                 # Issue management
├── merge_request.py         # Merge request operations
├── pipeline.py              # CI/CD pipeline tools
├── commit.py                # Git commit operations
├── filesystem.py            # File system operations
├── epic.py                  # Epic management
├── project.py               # Project operations
├── planner.py               # Workflow planning
├── handover.py              # Agent handover
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
- **Permission Awareness**: Respects GitLab's role-based access control
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

## Adding New Tools

### 1. Basic Tool Implementation

```python
from typing import Type
from pydantic import BaseModel, Field
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

class MyToolInput(BaseModel):
    project_id: str = Field(description="The GitLab project ID")
    parameter: str = Field(description="Tool-specific parameter")

class MyTool(DuoBaseTool):
    name: str = "my_custom_tool"
    description: str = """
    Description of what this tool does.

    Parameters:
    - project_id: The GitLab project ID (required)
    - parameter: Tool-specific parameter (required)

    Example usage:
    {
        'name': 'my_custom_tool',
        'input': {
            'project_id': '123',
            'parameter': 'value'
        }
    }
    """
    args_schema: Type[BaseModel] = MyToolInput

    async def _arun(self, project_id: str, parameter: str) -> str:
        try:
            # Tool implementation
            result = await self.gitlab_client.aget(
                path=f"/api/v4/projects/{project_id}/custom_endpoint",
                params={"param": parameter}
            )
            return json.dumps({"result": result})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: MyToolInput) -> str:
        return f"Executing custom operation on project {args.project_id}"
```

### 2. Register the Tool

Add your tool to `__init__.py`:

```python
# duo_workflow_service/tools/__init__.py
from .my_tool import *
```

### 3. Tool Best Practices

#### Input Validation
```python
class ToolInput(BaseModel):
    # Use descriptive field descriptions for LLM understanding
    project_id: str = Field(description="The GitLab project ID")

    # Provide defaults where appropriate
    ref: Optional[str] = Field(default="HEAD", description="Git reference")

    # Use enums for limited choices
    action: Literal["create", "update", "delete"] = Field(description="Action to perform")

    # Validate complex inputs
    @validator('project_id')
    def validate_project_id(cls, v):
        if not v.isdigit():
            raise ValueError('project_id must be numeric')
        return v
```

#### Error Handling
```python
async def _arun(self, **kwargs) -> str:
    try:
        # Validate inputs using base class methods
        project_id, errors = self._validate_project_url(
            kwargs.get('url'),
            kwargs.get('project_id')
        )

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        # Perform operation
        result = await self.gitlab_client.aget(path=f"/api/v4/projects/{project_id}")

        return json.dumps({"success": True, "data": result})

    except Exception as e:
        return json.dumps({"error": str(e), "tool": self.name})
```

#### Display Messages
```python
def format_display_message(self, args: ToolInput) -> str:
    # Provide context-aware, human-readable messages
    if hasattr(args, 'url') and args.url:
        return f"Processing {self.name} for {args.url}"
    else:
        return f"Executing {self.name} on project {args.project_id}"
```



## Workflow Integration

Tools can be combined in sophisticated workflows:

```python
# Example: Automated Security Review Workflow
async def security_review_workflow(merge_request_url: str):
    # 1. Get MR details
    mr_details = await gitlab_merge_request_get(url=merge_request_url)

    # 2. Get changed files
    changed_files = await gitlab_merge_request_changes(url=merge_request_url)

    # 3. Run security scan on changed files
    security_results = await gitlab_security_scanner(
        project_id=mr_details['project_id'],
        scan_type='vulnerability',
        file_patterns=changed_files
    )

    # 4. If issues found, add review comments
    if security_results['findings_count'] > 0:
        await gitlab_merge_request_note_create(
            url=merge_request_url,
            body=f"🔒 Security Review: Found {security_results['findings_count']} issues"
        )

    # 5. Update MR labels
    await gitlab_merge_request_update(
        url=merge_request_url,
        labels=['security-reviewed']
    )
```

## Testing Tools

The tools ecosystem uses a comprehensive testing strategy with multiple layers to ensure reliability and maintainability. With **409 passing tests**, the framework demonstrates robust coverage across all tool categories.

### Development Environment Setup

**Prerequisites:**
```bash
# Install Poetry (if not already installed)
brew install poetry

# Install Python 3.12 (required version)
brew install python@3.12

# Setup project environment
poetry env use /opt/homebrew/bin/python3.12
poetry install --with test
```

**Verify Installation:**
```bash
# Test that everything works
poetry run python -c "import ai_gateway; print('✅ Environment ready')"
```

### Testing Architecture

```
tests/duo_workflow_service/tools/
├── conftest.py                  # Shared fixtures and test configuration
├── test_duo_base_tool.py        # Base class functionality
├── test_search.py               # Search tools (parametrized tests)
├── test_repository_files.py     # File operations
├── test_issue.py                # Issue management
├── test_merge_request.py        # MR operations
├── test_pipeline.py             # CI/CD pipeline tools
├── test_commit.py               # Git operations
├── test_filesystem.py           # File system operations
└── test_security_scanner.py     # Security tools (example)
```

### Running Tests

**Basic Test Execution:**
```bash
# Run all tool tests (409 tests)
poetry run pytest tests/duo_workflow_service/tools/ -v

# Run specific tool tests
poetry run pytest tests/duo_workflow_service/tools/test_repository_files.py -v

# Run with coverage reporting
poetry run pytest tests/duo_workflow_service/tools/ --cov=duo_workflow_service.tools --cov-report=term-missing
```

**Test Categories:**
```bash
# Run security-related tests
poetry run pytest -k "security" -v

# Run performance tests
poetry run pytest -k "performance" -v

# Run error handling tests
poetry run pytest -k "error" -v
```

### 1. Unit Testing

#### Basic Tool Testing Pattern
```python
import pytest
from unittest.mock import AsyncMock
from duo_workflow_service.tools.my_tool import MyTool, MyToolInput

@pytest.fixture
def gitlab_client_mock():
    return AsyncMock()

@pytest.fixture
def metadata(gitlab_client_mock):
    return {
        "gitlab_client": gitlab_client_mock,
        "gitlab_host": "gitlab.com",
    }

@pytest.fixture
def tool(metadata):
    return MyTool(metadata=metadata)

@pytest.mark.asyncio
async def test_my_tool_success(tool, gitlab_client_mock):
    # Arrange
    gitlab_client_mock.aget.return_value = {"result": "success"}

    # Act
    result = await tool._arun(project_id="123", parameter="test")

    # Assert
    assert "success" in result
    gitlab_client_mock.aget.assert_called_once_with(
        path="/api/v4/projects/123/custom_endpoint",
        params={"param": "test"}
    )

@pytest.mark.asyncio
async def test_my_tool_error_handling(tool, gitlab_client_mock):
    # Arrange
    gitlab_client_mock.aget.side_effect = Exception("API error")

    # Act
    result = await tool._arun(project_id="123", parameter="test")

    # Assert
    error_response = json.loads(result)
    assert "error" in error_response
    assert "API error" in error_response["error"]

def test_format_display_message(tool):
    args = MyToolInput(project_id="123", parameter="test")
    message = tool.format_display_message(args)
    assert message == "Executing custom operation on project 123"
```

#### Parametrized Testing for Multiple Scenarios
```python
@pytest.mark.parametrize(
    "input_params,expected_path,expected_params,mock_response,expected_result",
    [
        (
            {"project_id": "123", "scan_type": "vulnerability"},
            "/api/v4/projects/123/repository/tree",
            {"recursive": True, "per_page": 100},
            [{"path": "app.py", "type": "blob"}],
            {"scan_type": "vulnerability", "findings_count": 0}
        ),
        (
            {"project_id": "456", "scan_type": "secrets", "severity_threshold": "high"},
            "/api/v4/projects/456/repository/tree",
            {"recursive": True, "per_page": 100},
            [{"path": "config.py", "type": "blob"}],
            {"scan_type": "secrets", "findings_count": 1}
        ),
    ],
    ids=["vulnerability_scan", "secrets_scan_high_severity"]
)
@pytest.mark.asyncio
async def test_security_scanner_scenarios(
    tool, gitlab_client_mock, input_params, expected_path,
    expected_params, mock_response, expected_result
):
    gitlab_client_mock.aget.return_value = mock_response

    result = await tool._arun(**input_params)
    result_data = json.loads(result)

    gitlab_client_mock.aget.assert_called_with(
        path=expected_path, params=expected_params
    )
    assert result_data["scan_type"] == expected_result["scan_type"]
    assert result_data["findings_count"] == expected_result["findings_count"]
```

#### Testing Input Validation
```python
@pytest.mark.parametrize(
    "invalid_input,expected_error",
    [
        ({"project_id": "", "scan_type": "vulnerability"}, "project_id must be provided"),
        ({"project_id": "123", "scan_type": "invalid"}, "Invalid scan_type"),
        ({"project_id": "abc", "scan_type": "vulnerability"}, "project_id must be numeric"),
    ]
)
@pytest.mark.asyncio
async def test_input_validation_errors(tool, invalid_input, expected_error):
    result = await tool._arun(**invalid_input)
    error_response = json.loads(result)

    assert "error" in error_response
    assert expected_error in error_response["error"]
```

#### Testing URL Parsing and Validation
```python
@pytest.mark.parametrize(
    "url,project_id,expected_project_id,expected_errors",
    [
        (
            "https://gitlab.com/namespace/project",
            None,
            "namespace%2Fproject",
            []
        ),
        (
            "https://gitlab.com/namespace/project",
            "different_id",
            None,
            ["Project ID mismatch"]
        ),
        (
            "invalid-url",
            None,
            None,
            ["Failed to parse URL"]
        ),
    ]
)
def test_url_validation(tool, url, project_id, expected_project_id, expected_errors):
    result_project_id, errors = tool._validate_project_url(url, project_id)

    assert result_project_id == expected_project_id
    assert len(errors) == len(expected_errors)
    for expected_error in expected_errors:
        assert any(expected_error in error for error in errors)
```

### 2. Integration Testing

#### Testing with Real GitLab API (Mocked)
```python
@pytest.mark.asyncio
async def test_security_scanner_integration(tool, gitlab_client_mock):
    # Mock the complete workflow
    gitlab_client_mock.aget.side_effect = [
        # First call: get repository tree
        [
            {"path": "app.py", "type": "blob"},
            {"path": "config.py", "type": "blob"},
            {"path": "requirements.txt", "type": "blob"}
        ],
        # Second call: get file content for app.py
        "import os\npassword = 'hardcoded_secret'\napi_key = os.getenv('API_KEY')",
        # Third call: get file content for config.py
        "DATABASE_URL = 'postgresql://user:pass@localhost/db'",
        # Fourth call: get file content for requirements.txt
        "flask==1.0.0\nrequests==2.20.0"
    ]

    result = await tool._arun(
        project_id="123",
        scan_type="secrets",
        severity_threshold="medium"
    )

    result_data = json.loads(result)

    # Verify the complete workflow
    assert result_data["scan_type"] == "secrets"
    assert result_data["findings_count"] > 0
    assert any("hardcoded_secret" in str(finding) for finding in result_data["findings"])

    # Verify all expected API calls were made
    assert gitlab_client_mock.aget.call_count == 4
```

#### Testing Tool Composition in Workflows
```python
@pytest.mark.asyncio
async def test_security_review_workflow(
    security_scanner_tool,
    merge_request_tool,
    gitlab_client_mock
):
    # Mock MR details
    gitlab_client_mock.aget.side_effect = [
        # Get MR details
        {"project_id": "123", "iid": 1, "title": "Add new feature"},
        # Get MR changes
        [{"new_path": "app.py", "old_path": "app.py"}],
        # Security scan results
        [{"path": "app.py", "type": "blob"}],
        # File content
        "def process_user_input(data):\n    return eval(data)  # Dangerous!",
        # Add MR comment
        {"id": 456, "body": "Security issues found"}
    ]

    # Execute workflow
    mr_url = "https://gitlab.com/namespace/project/-/merge_requests/1"

    # Step 1: Get MR details
    mr_details = await merge_request_tool._arun(url=mr_url, action="get")

    # Step 2: Run security scan
    security_results = await security_scanner_tool._arun(
        project_id="123",
        scan_type="vulnerability"
    )

    # Step 3: Add comment if issues found
    security_data = json.loads(security_results)
    if security_data["findings_count"] > 0:
        await merge_request_tool._arun(
            url=mr_url,
            action="add_comment",
            body="🔒 Security issues detected"
        )

    # Verify workflow execution
    assert gitlab_client_mock.aget.call_count == 5
```

### 3. Performance Testing

#### Testing Tool Performance
```python
import time
import pytest

@pytest.mark.asyncio
async def test_tool_performance(tool, gitlab_client_mock):
    # Mock large response
    large_file_list = [{"path": f"file_{i}.py", "type": "blob"} for i in range(1000)]
    gitlab_client_mock.aget.return_value = large_file_list

    start_time = time.time()
    result = await tool._arun(project_id="123", scan_type="vulnerability")
    execution_time = time.time() - start_time

    # Performance assertions
    assert execution_time < 5.0  # Should complete within 5 seconds
    assert "findings_count" in json.loads(result)

@pytest.mark.asyncio
async def test_tool_memory_usage(tool, gitlab_client_mock):
    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss

    # Execute tool with large dataset
    large_response = "x" * (10 * 1024 * 1024)  # 10MB response
    gitlab_client_mock.aget.return_value = large_response

    await tool._arun(project_id="123", scan_type="vulnerability")

    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory

    # Memory should not increase by more than 50MB
    assert memory_increase < 50 * 1024 * 1024
```

### 4. Security Testing

#### Testing Security Tool Accuracy
```python
@pytest.fixture
def vulnerable_code_samples():
    return {
        "sql_injection": "query = f'SELECT * FROM users WHERE id = {user_id}'",
        "hardcoded_secret": "api_key = 'sk-1234567890abcdef'",
        "eval_injection": "result = eval(user_input)",
        "safe_code": "result = json.loads(user_input)"
    }

@pytest.mark.asyncio
async def test_vulnerability_detection_accuracy(
    security_scanner_tool,
    gitlab_client_mock,
    vulnerable_code_samples
):
    for vulnerability_type, code in vulnerable_code_samples.items():
        gitlab_client_mock.aget.side_effect = [
            [{"path": "test.py", "type": "blob"}],
            code
        ]

        result = await security_scanner_tool._arun(
            project_id="123",
            scan_type="vulnerability"
        )

        result_data = json.loads(result)

        if vulnerability_type == "safe_code":
            assert result_data["findings_count"] == 0
        else:
            assert result_data["findings_count"] > 0
            # Verify specific vulnerability type is detected
            findings = result_data["findings"]
            assert any(vulnerability_type.replace("_", " ") in str(finding).lower()
                      for finding in findings)
```

### 5. Error Handling Testing

#### Testing Network Failures
```python
@pytest.mark.asyncio
async def test_network_error_handling(tool, gitlab_client_mock):
    import aiohttp

    gitlab_client_mock.aget.side_effect = aiohttp.ClientError("Network error")

    result = await tool._arun(project_id="123", scan_type="vulnerability")
    error_response = json.loads(result)

    assert "error" in error_response
    assert "Network error" in error_response["error"]

@pytest.mark.asyncio
async def test_timeout_handling(tool, gitlab_client_mock):
    import asyncio

    async def slow_response(*args, **kwargs):
        await asyncio.sleep(10)  # Simulate slow response
        return []

    gitlab_client_mock.aget.side_effect = slow_response

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            tool._arun(project_id="123", scan_type="vulnerability"),
            timeout=5.0
        )
```

### 6. Test Configuration and Fixtures

#### Shared Test Configuration
```python
# tests/duo_workflow_service/tools/conftest.py
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def gitlab_client_mock():
    """Mock GitLab client for all tool tests."""
    mock = AsyncMock()
    mock.aget.return_value = []
    return mock

@pytest.fixture
def gitlab_host():
    """Standard GitLab host for testing."""
    return "gitlab.com"

@pytest.fixture
def metadata(gitlab_client_mock, gitlab_host):
    """Standard metadata for tool initialization."""
    return {
        "gitlab_client": gitlab_client_mock,
        "gitlab_host": gitlab_host,
    }

@pytest.fixture
def sample_project_files():
    """Sample project file structure for testing."""
    return [
        {"path": "app.py", "type": "blob"},
        {"path": "config.py", "type": "blob"},
        {"path": "requirements.txt", "type": "blob"},
        {"path": "tests/", "type": "tree"},
        {"path": "README.md", "type": "blob"}
    ]

@pytest.fixture
def security_findings_sample():
    """Sample security findings for testing."""
    return [
        {
            "severity": "high",
            "category": "injection",
            "description": "SQL injection vulnerability",
            "line_number": 42,
            "file_path": "app.py",
            "cwe_id": "CWE-89"
        },
        {
            "severity": "medium",
            "category": "secrets",
            "description": "Hardcoded API key",
            "line_number": 15,
            "file_path": "config.py",
            "cwe_id": "CWE-798"
        }
    ]
```

### 7. Running Tests

#### Local Testing
```bash
# Run all tool tests
make test-tools

# Run specific tool tests
poetry run pytest tests/duo_workflow_service/tools/test_security_scanner.py

# Run with coverage
poetry run pytest tests/duo_workflow_service/tools/ --cov=duo_workflow_service.tools

# Run performance tests
poetry run pytest tests/duo_workflow_service/tools/ -m performance

# Run integration tests
poetry run pytest tests/duo_workflow_service/tools/ -m integration
```

#### CI/CD Testing
```yaml
# .gitlab-ci.yml
test:tools:
  stage: test
  script:
    - poetry install --with test
    - poetry run pytest tests/duo_workflow_service/tools/ --junitxml=report.xml
  artifacts:
    reports:
      junit: report.xml
    paths:
      - htmlcov/
  coverage: '/TOTAL.*\s+(\d+%)$/'
```

### 8. Test Markers and Categories

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests for individual tool functions",
    "integration: Integration tests with mocked GitLab API",
    "performance: Performance and load testing",
    "security: Security-specific test scenarios",
    "slow: Tests that take longer than 1 second"
]
```

#### Using Test Markers
```python
@pytest.mark.unit
def test_tool_initialization():
    pass

@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_with_gitlab_api():
    pass

@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.asyncio
async def test_tool_performance():
    pass

@pytest.mark.security
@pytest.mark.parametrize("vulnerability_type", ["sql_injection", "xss", "csrf"])
def test_vulnerability_detection(vulnerability_type):
    pass
```

### 9. Testing Best Practices

#### Tool Testing Checklist
- ✅ **Input Validation**: Test all input combinations and edge cases
- ✅ **Error Handling**: Test network failures, API errors, timeouts
- ✅ **Output Format**: Verify JSON structure and required fields
- ✅ **GitLab API Integration**: Mock all external API calls
- ✅ **URL Parsing**: Test various GitLab URL formats
- ✅ **Display Messages**: Verify user-friendly messages
- ✅ **Performance**: Test with large datasets and measure execution time
- ✅ **Security**: Test with known vulnerable and safe code samples
- ✅ **Async Behavior**: Test concurrent execution and cancellation

#### Security Tool Testing Specifics
- ✅ **False Positives**: Ensure safe code doesn't trigger alerts
- ✅ **False Negatives**: Ensure known vulnerabilities are detected
- ✅ **Severity Classification**: Test severity threshold filtering
- ✅ **CWE Mapping**: Verify correct vulnerability classification
- ✅ **Remediation Suggestions**: Test quality of fix recommendations
- ✅ **File Type Support**: Test various programming languages
- ✅ **Large Codebases**: Test performance with enterprise-scale projects

## Performance Considerations

### Caching
- Implement caching for frequently accessed data
- Use GitLab's ETag headers for conditional requests
- Cache tool results when appropriate

### Rate Limiting
- Respect GitLab API rate limits
- Implement exponential backoff for retries
- Batch operations when possible

### Error Recovery
- Implement graceful degradation
- Provide meaningful error messages
- Support partial results when full operation fails

## Monitoring and Observability

### Logging
```python
import structlog

log = structlog.stdlib.get_logger("duo_workflow_service.tools")

async def _arun(self, **kwargs) -> str:
    log.info("Tool execution started", tool=self.name, **kwargs)
    try:
        result = await self._perform_operation(**kwargs)
        log.info("Tool execution completed", tool=self.name, success=True)
        return result
    except Exception as e:
        log.error("Tool execution failed", tool=self.name, error=str(e))
        raise
```

### Metrics
- Track tool usage and performance
- Monitor error rates and response times
- Measure workflow success rates

## Contributing

When adding new tools:

1. **Follow the established patterns** in existing tools
2. **Write comprehensive descriptions** for LLM understanding
3. **Include proper error handling** and validation
4. **Add unit and integration tests**
5. **Update this README** with new tool categories
6. **Consider security implications** of new capabilities

## Future Enhancements

### Planned Tool Categories
- **Security Tools**: Vulnerability scanning, threat modeling, compliance checking
- **Performance Tools**: Code analysis, optimization suggestions
- **Documentation Tools**: Auto-generation, consistency checking
- **Deployment Tools**: Infrastructure management, rollback capabilities
- **Analytics Tools**: Code metrics, team productivity insights

### Architecture Improvements
- **Tool Composition**: Higher-level tools that combine multiple operations
- **Conditional Execution**: Tools that adapt behavior based on context
- **Parallel Execution**: Concurrent tool execution for performance
- **Tool Versioning**: Support for multiple tool versions and migrations
