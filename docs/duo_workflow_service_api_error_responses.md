# Duo Workflow Service API Error Responses

This document describes the enhanced error response format for the Duo Workflow Service API, which provides specific, actionable error information instead of generic error messages.

## Error Response Format

All error responses from the Duo Workflow Service now follow a consistent structure that includes:

1. **Workflow Status**: Set to "Error"
2. **UI Chat Log**: Contains user-friendly error message with suggestions
3. **Error Details**: Structured error information for debugging and handling

### Standard Error Response

```json
{
  "status": "Error",
  "ui_chat_log": [
    {
      "message_type": "agent",
      "message_sub_type": "error",
      "content": "The AI service is currently experiencing high demand. Please wait a moment and try again.\n\nSuggested actions:\n• Wait a few minutes before trying again\n• Consider breaking down complex requests into smaller parts",
      "timestamp": "2025-01-14T10:30:00.000Z",
      "status": "failure",
      "correlation_id": "req-abc123",
      "tool_info": null,
      "additional_context": null
    }
  ],
  "error_details": {
    "code": "llm_rate_limit",
    "severity": "medium",
    "category": "resource",
    "user_friendly": {
      "title": "Rate Limit Exceeded",
      "message": "The AI service is currently experiencing high demand. Please wait a moment and try again.",
      "suggestions": [
        "Wait a few minutes before trying again",
        "Consider breaking down complex requests into smaller parts"
      ],
      "documentation_url": null
    },
    "technical": {
      "exception_type": "APIStatusError",
      "stack_trace": null,
      "request_id": "req-abc123",
      "timestamp": "2025-01-14T10:30:00.000Z"
    },
    "context": {
      "component": "llm",
      "operation": "api_request",
      "tool_name": null,
      "agent_name": "chat_agent",
      "workflow_id": "workflow-456",
      "correlation_id": "req-abc123",
      "additional_data": {
        "model_name": "claude-3",
        "status_code": 429
      }
    },
    "retry_after": 60,
    "is_retryable": true,
    "created_at": "2025-01-14T10:30:00.000Z"
  }
}
```

## Error Response Fields

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Always "Error" for error responses |
| `ui_chat_log` | array | Array containing user-facing error message |
| `error_details` | object | Detailed error information for debugging |

### UI Chat Log Fields

| Field | Type | Description |
|-------|------|-------------|
| `message_type` | string | Always "agent" for error messages |
| `message_sub_type` | string | Always "error" for error messages |
| `content` | string | User-friendly error message with suggestions |
| `timestamp` | string | ISO 8601 timestamp when error occurred |
| `status` | string | Always "failure" for error messages |
| `correlation_id` | string | Unique identifier for request tracking |
| `tool_info` | object/null | Tool information if error was tool-related |
| `additional_context` | array/null | Additional context information |

### Error Details Fields

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Specific error code (see Error Codes section) |
| `severity` | string | Error severity: "low", "medium", "high", "critical" |
| `category` | string | Error category: "user_input", "external_service", "system", "permission", "resource" |
| `user_friendly` | object | User-facing error information |
| `technical` | object | Technical error details for debugging |
| `context` | object | Context information about where error occurred |
| `retry_after` | number/null | Seconds to wait before retrying (if retryable) |
| `is_retryable` | boolean | Whether the operation can be retried |
| `created_at` | string | ISO 8601 timestamp when error was created |

### User Friendly Error Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Short, descriptive error title |
| `message` | string | Detailed user-friendly error message |
| `suggestions` | array | List of suggested actions user can take |
| `documentation_url` | string/null | Link to relevant documentation |

### Technical Error Fields

| Field | Type | Description |
|-------|------|-------------|
| `exception_type` | string/null | Type of exception that occurred |
| `stack_trace` | string/null | Stack trace (not exposed to users) |
| `request_id` | string/null | Request ID for tracking |
| `timestamp` | string | When the technical error occurred |

### Context Fields

| Field | Type | Description |
|-------|------|-------------|
| `component` | string/null | Component where error occurred |
| `operation` | string/null | Operation that failed |
| `tool_name` | string/null | Tool that caused error (if applicable) |
| `agent_name` | string/null | Agent that encountered error (if applicable) |
| `workflow_id` | string/null | Workflow ID for tracking |
| `correlation_id` | string/null | Request correlation ID |
| `additional_data` | object/null | Additional context-specific data |

## Error Code Categories

### LLM/AI Service Errors (llm_*)

These errors occur when interacting with AI/LLM services:

- `llm_api_error`: General AI service error
- `llm_rate_limit`: Rate limit exceeded
- `llm_authentication_error`: Authentication failed
- `llm_invalid_request`: Invalid request format
- `llm_context_too_large`: Request context too large
- `llm_timeout`: Request timeout

### Tool Execution Errors (tool_*)

These errors occur during tool execution:

- `tool_execution_failed`: Tool execution failed
- `tool_validation_error`: Tool input validation failed
- `tool_permission_denied`: Insufficient permissions for tool
- `tool_timeout`: Tool execution timeout
- `tool_not_found`: Tool not available

### GitLab API Errors (gitlab_*)

These errors occur when interacting with GitLab APIs:

- `gitlab_api_error`: General GitLab API error
- `gitlab_authentication_error`: GitLab authentication failed
- `gitlab_permission_denied`: Insufficient GitLab permissions
- `gitlab_resource_not_found`: GitLab resource not found
- `gitlab_rate_limit`: GitLab rate limit exceeded

### Workflow State Errors (workflow_*)

These errors relate to workflow state and execution:

- `workflow_state_invalid`: Invalid workflow state
- `workflow_cancelled`: Workflow was cancelled
- `workflow_timeout`: Workflow execution timeout

### Input Validation Errors (input_*)

These errors occur during input validation:

- `input_validation_error`: Input validation failed
- `goal_disambiguation_failed`: Could not understand user goal

### System Errors

These are internal system errors:

- `internal_error`: Internal system error
- `service_unavailable`: Service temporarily unavailable
- `configuration_error`: Configuration issue
- `unknown_error`: Unclassified error

## HTTP Status Codes

The Duo Workflow Service API continues to return appropriate HTTP status codes along with the enhanced error response body:

| HTTP Status | Description | Common Error Codes |
|-------------|-------------|-------------------|
| 400 Bad Request | Invalid request format or parameters | `input_validation_error`, `llm_invalid_request` |
| 401 Unauthorized | Authentication failed | `llm_authentication_error`, `gitlab_authentication_error` |
| 403 Forbidden | Insufficient permissions | `tool_permission_denied`, `gitlab_permission_denied` |
| 404 Not Found | Resource not found | `gitlab_resource_not_found`, `tool_not_found` |
| 408 Request Timeout | Request timeout | `llm_timeout`, `tool_timeout`, `workflow_timeout` |
| 429 Too Many Requests | Rate limit exceeded | `llm_rate_limit`, `gitlab_rate_limit` |
| 500 Internal Server Error | Internal system error | `internal_error`, `unknown_error` |
| 502 Bad Gateway | External service error | `llm_api_error`, `gitlab_api_error` |
| 503 Service Unavailable | Service temporarily unavailable | `service_unavailable` |

## Example Error Responses

### Rate Limit Error

```json
{
  "status": "Error",
  "ui_chat_log": [
    {
      "message_type": "agent",
      "message_sub_type": "error",
      "content": "The AI service is currently experiencing high demand. Please wait a moment and try again.\n\nSuggested actions:\n• Wait a few minutes before trying again\n• Consider breaking down complex requests into smaller parts",
      "timestamp": "2025-01-14T10:30:00.000Z",
      "status": "failure",
      "correlation_id": "req-rate-limit-123"
    }
  ],
  "error_details": {
    "code": "llm_rate_limit",
    "severity": "medium",
    "category": "resource",
    "retry_after": 60,
    "is_retryable": true
  }
}
```

### Permission Error

```json
{
  "status": "Error",
  "ui_chat_log": [
    {
      "message_type": "agent",
      "message_sub_type": "error",
      "content": "You don't have permission to perform this action in GitLab.\n\nSuggested actions:\n• Check your role in the project\n• Request additional permissions from a project maintainer\n• Try a different approach that doesn't require elevated permissions",
      "timestamp": "2025-01-14T10:35:00.000Z",
      "status": "failure",
      "correlation_id": "req-permission-456"
    }
  ],
  "error_details": {
    "code": "gitlab_permission_denied",
    "severity": "high",
    "category": "permission",
    "is_retryable": false
  }
}
```

### Tool Execution Error

```json
{
  "status": "Error",
  "ui_chat_log": [
    {
      "message_type": "agent",
      "message_sub_type": "error",
      "content": "The file_reader tool encountered an error while executing. Please try again or use an alternative approach.\n\nSuggested actions:\n• Try the operation again\n• Use a different approach to achieve the same goal\n• Contact support if the issue persists",
      "timestamp": "2025-01-14T10:40:00.000Z",
      "status": "failure",
      "correlation_id": "req-tool-789"
    }
  ],
  "error_details": {
    "code": "tool_execution_failed",
    "severity": "high",
    "category": "system",
    "context": {
      "tool_name": "file_reader",
      "operation": "read_file"
    },
    "is_retryable": true
  }
}
```

### Validation Error

```json
{
  "status": "Error",
  "ui_chat_log": [
    {
      "message_type": "agent",
      "message_sub_type": "error",
      "content": "There was an issue with the provided input. Please check your request and try again.\n\nSuggested actions:\n• Check that all required fields are provided\n• Verify that input values are in the correct format\n• Review the request structure and try again",
      "timestamp": "2025-01-14T10:45:00.000Z",
      "status": "failure",
      "correlation_id": "req-validation-abc"
    }
  ],
  "error_details": {
    "code": "input_validation_error",
    "severity": "medium",
    "category": "user_input",
    "is_retryable": false
  }
}
```

## Client Implementation Guidelines

### Error Handling Best Practices

1. **Check Error Status**: Always check the `status` field to identify error responses
2. **Display User-Friendly Messages**: Use the `ui_chat_log[0].content` for user display
3. **Handle Retryable Errors**: Check `is_retryable` and `retry_after` for retry logic
4. **Log Technical Details**: Log `error_details` for debugging and monitoring
5. **Use Correlation IDs**: Include `correlation_id` in support requests

### Example Client Code

```javascript
// JavaScript example
async function handleWorkflowResponse(response) {
  const data = await response.json();
  
  if (data.status === "Error") {
    // Display user-friendly error message
    const errorMessage = data.ui_chat_log[0].content;
    displayErrorToUser(errorMessage);
    
    // Handle retryable errors
    if (data.error_details.is_retryable) {
      const retryAfter = data.error_details.retry_after || 30;
      scheduleRetry(retryAfter);
    }
    
    // Log technical details
    console.error("Workflow error:", {
      code: data.error_details.code,
      severity: data.error_details.severity,
      correlationId: data.ui_chat_log[0].correlation_id,
      context: data.error_details.context
    });
    
    return;
  }
  
  // Handle successful response
  handleSuccessfulResponse(data);
}
```

```python
# Python example
def handle_workflow_response(response_data):
    if response_data.get("status") == "Error":
        # Display user-friendly error message
        error_message = response_data["ui_chat_log"][0]["content"]
        display_error_to_user(error_message)
        
        # Handle retryable errors
        error_details = response_data["error_details"]
        if error_details.get("is_retryable"):
            retry_after = error_details.get("retry_after", 30)
            schedule_retry(retry_after)
        
        # Log technical details
        logger.error("Workflow error", extra={
            "error_code": error_details["code"],
            "severity": error_details["severity"],
            "correlation_id": response_data["ui_chat_log"][0]["correlation_id"],
            "context": error_details.get("context", {})
        })
        
        return
    
    # Handle successful response
    handle_successful_response(response_data)
```

## Migration from Legacy Error Format

### Legacy Format (Deprecated)

```json
{
  "status": "Error",
  "ui_chat_log": [
    {
      "message_type": "agent",
      "content": "There was an error processing your request. Please try again or contact support if the issue persists.",
      "status": "failure"
    }
  ]
}
```

### Enhanced Format (Current)

The enhanced format includes all the fields described above, providing much more detailed and actionable error information.

### Migration Checklist

- [ ] Update error handling to use new `error_details` structure
- [ ] Implement retry logic based on `is_retryable` and `retry_after`
- [ ] Update error logging to include `correlation_id` and error context
- [ ] Update user interfaces to display enhanced error messages
- [ ] Add monitoring for specific error codes and categories
- [ ] Update documentation and error handling guides

## Monitoring and Analytics

### Recommended Metrics

- Error rate by error code
- Error rate by severity level
- Error rate by category
- Retry success rate for retryable errors
- Average retry delay for rate-limited requests

### Event Tracking

All errors generate `request_duo_workflow_failure` events that can be used for monitoring and analytics. These events include:

- Error code and category
- Workflow and component context
- User impact information
- Retry and resolution data

## Support and Troubleshooting

When contacting support about errors, please include:

1. **Correlation ID**: From the error response
2. **Error Code**: From `error_details.code`
3. **Timestamp**: When the error occurred
4. **Context**: What operation was being performed
5. **Workflow ID**: If available in the error context

This information helps support teams quickly identify and resolve issues.