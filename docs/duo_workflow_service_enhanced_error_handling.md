# Enhanced Error Handling for Duo Workflow Service

This document describes the enhanced error handling system implemented for the Duo Workflow Service to replace generic error messages with specific, actionable error information.

## Overview

The enhanced error handling system addresses the issue described in [GitLab Issue #1452](https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/-/issues/1452) where users received generic error messages like "There was an error processing your request..." instead of specific, actionable error information.

### Key Improvements

1. **Specific Error Messages**: Replace generic messages with detailed, context-aware error descriptions
2. **Actionable Suggestions**: Provide users with specific steps they can take to resolve issues
3. **Reliable Event Tracking**: Ensure all errors generate appropriate `request_duo_workflow_failure` events
4. **Structured Error Responses**: Use consistent error response format across all components
5. **Enhanced UI Chat Logs**: Include detailed error information in `ui_chat_log` responses

## Error Response Structure

### Enhanced Error Response Format

```python
{
    "status": "Error",
    "ui_chat_log": [
        {
            "message_type": "agent",
            "message_sub_type": "error",
            "content": "The AI service is currently experiencing high demand. Please wait a moment and try again.\n\nSuggested actions:\n• Wait a few minutes before trying again\n• Consider breaking down complex requests into smaller parts",
            "timestamp": "2025-01-14T10:30:00Z",
            "status": "failure",
            "correlation_id": "req-12345",
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
            ]
        },
        "technical": {
            "exception_type": "APIStatusError",
            "request_id": "req-12345"
        },
        "context": {
            "component": "llm",
            "operation": "api_request",
            "agent_name": "chat_agent",
            "workflow_id": "workflow-123"
        },
        "retry_after": 60,
        "is_retryable": true,
        "created_at": "2025-01-14T10:30:00Z"
    }
}
```

## Error Codes

### LLM/Model Errors

| Error Code | Description | Severity | Retryable |
|------------|-------------|----------|-----------|
| `llm_api_error` | General AI service error | High | Yes (for 5xx errors) |
| `llm_rate_limit` | Rate limit exceeded | Medium | Yes |
| `llm_authentication_error` | Authentication failed | Critical | No |
| `llm_invalid_request` | Invalid request format | High | No |
| `llm_context_too_large` | Request context too large | High | No |
| `llm_timeout` | Request timeout | Medium | Yes |

### Tool Execution Errors

| Error Code | Description | Severity | Retryable |
|------------|-------------|----------|-----------|
| `tool_execution_failed` | Tool execution failed | High | Sometimes |
| `tool_validation_error` | Tool input validation failed | Medium | No |
| `tool_permission_denied` | Insufficient permissions | High | No |
| `tool_timeout` | Tool execution timeout | Medium | Yes |
| `tool_not_found` | Tool not available | High | No |

### GitLab API Errors

| Error Code | Description | Severity | Retryable |
|------------|-------------|----------|-----------|
| `gitlab_api_error` | General GitLab API error | High | Sometimes |
| `gitlab_authentication_error` | GitLab authentication failed | Critical | No |
| `gitlab_permission_denied` | Insufficient GitLab permissions | High | No |
| `gitlab_resource_not_found` | GitLab resource not found | Medium | No |
| `gitlab_rate_limit` | GitLab rate limit exceeded | Medium | Yes |

### Workflow State Errors

| Error Code | Description | Severity | Retryable |
|------------|-------------|----------|-----------|
| `workflow_state_invalid` | Invalid workflow state | High | No |
| `workflow_cancelled` | Workflow was cancelled | Medium | No |
| `workflow_timeout` | Workflow execution timeout | Medium | Yes |

### Input Validation Errors

| Error Code | Description | Severity | Retryable |
|------------|-------------|----------|-----------|
| `input_validation_error` | Input validation failed | Medium | No |
| `goal_disambiguation_failed` | Could not understand goal | Medium | No |

### System Errors

| Error Code | Description | Severity | Retryable |
|------------|-------------|----------|-----------|
| `internal_error` | Internal system error | Critical | Sometimes |
| `service_unavailable` | Service temporarily unavailable | High | Yes |
| `configuration_error` | Configuration issue | Critical | No |
| `unknown_error` | Unclassified error | High | Sometimes |

## Error Severity Levels

- **Low**: Minor issues that don't prevent workflow continuation
- **Medium**: Issues that may affect workflow quality but allow continuation
- **High**: Issues that prevent workflow continuation but are recoverable
- **Critical**: Issues that require immediate attention and stop workflow

## Error Categories

- **user_input**: Errors related to user input or configuration
- **external_service**: Errors from external APIs/services
- **system**: Internal system errors
- **permission**: Authorization/permission errors
- **resource**: Resource availability/limits errors

## Usage Examples

### Basic Error Handling

```python
from duo_workflow_service.errors.enhanced_error_handler import handle_workflow_error

try:
    # Some workflow operation
    result = perform_operation()
except Exception as error:
    return handle_workflow_error(
        exception=error,
        component="workflow_executor",
        operation="execute_step",
        workflow_id="workflow-123"
    )
```

### Agent Error Handling

```python
from duo_workflow_service.errors.enhanced_error_handler import handle_agent_error

try:
    # Agent processing
    response = await agent.process()
except Exception as error:
    return handle_agent_error(
        exception=error,
        agent_name="chat_agent",
        workflow_id="workflow-456"
    )
```

### Tool Error Handling

```python
from duo_workflow_service.errors.enhanced_error_handler import handle_tool_error

try:
    # Tool execution
    result = tool.execute()
except Exception as error:
    return handle_tool_error(
        exception=error,
        tool_name="file_reader",
        workflow_id="workflow-789"
    )
```

## Event Tracking

All errors automatically generate `request_duo_workflow_failure` events with detailed information:

```python
{
    "event": "request_duo_workflow_failure",
    "workflow_id": "workflow-123",
    "error_code": "llm_rate_limit",
    "error_category": "resource",
    "error_severity": "medium",
    "error_message": "The AI service is currently experiencing high demand...",
    "is_retryable": true,
    "component": "llm",
    "operation": "api_request"
}
```

## Migration Guide

### For Existing Code

1. **Replace Generic Error Handling**:
   ```python
   # Old approach
   return {
       "status": WorkflowStatusEnum.ERROR,
       "ui_chat_log": [UiChatLog(
           content="There was an error processing your request..."
       )]
   }
   
   # New approach
   from duo_workflow_service.errors.enhanced_error_handler import handle_workflow_error
   return handle_workflow_error(exception=error, component="my_component")
   ```

2. **Update Agent Classes**:
   - Use `EnhancedAgent` instead of `Agent`
   - Use `EnhancedChatAgent` instead of `ChatAgent`
   - These classes automatically use the enhanced error handling

3. **Update Exception Handling**:
   ```python
   # Old approach
   except Exception as error:
       log.error(f"Error: {error}")
       return create_generic_error_response()
   
   # New approach
   except Exception as error:
       return handle_workflow_error(
           exception=error,
           component="my_component",
           operation="my_operation",
           workflow_id=workflow_id
       )
   ```

## Troubleshooting Guide

### Common Error Scenarios

#### Rate Limit Errors
**Error Code**: `llm_rate_limit`
**User Message**: "The AI service is currently experiencing high demand. Please wait a moment and try again."
**Solutions**:
- Wait 1-2 minutes before retrying
- Break down complex requests into smaller parts
- Contact support if issue persists

#### Authentication Errors
**Error Code**: `llm_authentication_error` or `gitlab_authentication_error`
**User Message**: "There was an authentication issue with the [service]. Please contact support if this issue persists."
**Solutions**:
- Check service configuration
- Verify API tokens are valid
- Contact administrator

#### Permission Errors
**Error Code**: `tool_permission_denied` or `gitlab_permission_denied`
**User Message**: "You don't have permission to perform this action."
**Solutions**:
- Check user role in project
- Request additional permissions from maintainer
- Try alternative approach

#### Validation Errors
**Error Code**: `input_validation_error`
**User Message**: "There was an issue with the provided input. Please check your request and try again."
**Solutions**:
- Check all required fields are provided
- Verify input format is correct
- Review request structure

### Debugging

1. **Check Error Details**: Look at the `error_details` field for technical information
2. **Use Correlation ID**: Track requests using the `correlation_id` field
3. **Review Event Tracking**: Check `request_duo_workflow_failure` events for patterns
4. **Check Component Context**: Use `context` field to identify where error occurred

### Monitoring

- Monitor `request_duo_workflow_failure` events for error patterns
- Track error codes and categories for trending
- Set up alerts for critical errors
- Monitor retry rates for retryable errors

## Configuration

### Error Message Customization

Error messages can be customized by modifying the error classification rules in `duo_workflow_service/errors/error_classifier.py`.

### Event Tracking Configuration

Event tracking is automatically enabled. To customize tracking behavior, modify `duo_workflow_service/tracking/enhanced_event_tracker.py`.

### Logging Configuration

Enhanced error handling uses structured logging. Configure log levels in your application configuration:

```python
# Log all error handling at INFO level
logging.getLogger("enhanced_error_handler").setLevel(logging.INFO)

# Log error classification at DEBUG level
logging.getLogger("error_classifier").setLevel(logging.DEBUG)
```

## Best Practices

1. **Always Use Enhanced Error Handling**: Replace generic error responses with enhanced error handling
2. **Provide Context**: Include component, operation, and workflow_id when possible
3. **Use Appropriate Error Codes**: Choose the most specific error code available
4. **Include Actionable Suggestions**: Help users understand what they can do to resolve issues
5. **Monitor Error Patterns**: Use event tracking to identify and address common issues
6. **Test Error Scenarios**: Include error handling tests in your test suite
7. **Document Custom Errors**: Document any custom error codes or handling you add

## API Reference

### Enhanced Error Handler

- `handle_workflow_error()`: General workflow error handling
- `handle_agent_error()`: Agent-specific error handling
- `handle_tool_error()`: Tool-specific error handling
- `handle_llm_error()`: LLM/AI service error handling
- `handle_validation_error()`: Input validation error handling

### Error Models

- `WorkflowError`: Complete error information
- `WorkflowErrorResponse`: Error response with UI chat log
- `ErrorContext`: Error context information
- `UserFriendlyError`: User-facing error information
- `TechnicalError`: Technical error details

### Error Classification

- `ErrorClassifier`: Classifies exceptions into structured errors
- `classify_workflow_error()`: Convenience function for error classification

### Event Tracking

- `track_workflow_failure()`: Track workflow failure events
- `track_tool_failure()`: Track tool failure events
- `track_agent_failure()`: Track agent failure events