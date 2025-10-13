"""Error classification system for Duo Workflow Service.

This module provides functions to classify different types of exceptions and errors
into structured workflow error responses with appropriate user-friendly messages.
"""

import re
from typing import Any, Dict, List, Optional, Type, Union

import structlog
from anthropic import APIStatusError
from pydantic import ValidationError
from pydantic_core import ValidationError as PydanticCoreValidationError

from duo_workflow_service.errors.enhanced_error_models import (
    ErrorContext,
    ErrorResponseBuilder,
    TechnicalError,
    WorkflowErrorCategory,
    WorkflowErrorCode,
    WorkflowErrorResponse,
    WorkflowErrorSeverity,
)
from duo_workflow_service.errors.error_handler import ModelErrorType

log = structlog.stdlib.get_logger("error_classifier")


class ErrorClassifier:
    """Classifies exceptions into structured workflow errors."""
    
    def __init__(self):
        self._classification_rules = self._build_classification_rules()
    
    def classify_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext] = None,
        correlation_id: Optional[str] = None,
    ) -> WorkflowErrorResponse:
        """Classify an exception into a structured workflow error response."""
        
        # Try to find a matching classification rule
        for rule in self._classification_rules:
            if rule["matcher"](exception):
                return rule["handler"](exception, context, correlation_id)
        
        # Fallback to unknown error
        return self._handle_unknown_error(exception, context, correlation_id)
    
    def _build_classification_rules(self) -> List[Dict[str, Any]]:
        """Build the list of error classification rules."""
        return [
            # Anthropic API errors
            {
                "matcher": lambda e: isinstance(e, APIStatusError),
                "handler": self._handle_anthropic_api_error,
            },
            # Pydantic validation errors
            {
                "matcher": lambda e: isinstance(e, (ValidationError, PydanticCoreValidationError)),
                "handler": self._handle_validation_error,
            },
            # Tool execution errors (based on error message patterns)
            {
                "matcher": lambda e: self._is_tool_error(e),
                "handler": self._handle_tool_error,
            },
            # GitLab API errors (based on error message patterns)
            {
                "matcher": lambda e: self._is_gitlab_api_error(e),
                "handler": self._handle_gitlab_api_error,
            },
            # Timeout errors
            {
                "matcher": lambda e: self._is_timeout_error(e),
                "handler": self._handle_timeout_error,
            },
            # Permission errors
            {
                "matcher": lambda e: self._is_permission_error(e),
                "handler": self._handle_permission_error,
            },
        ]
    
    def _handle_anthropic_api_error(
        self,
        exception: APIStatusError,
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle Anthropic API errors."""
        
        status_code = exception.response.status_code
        error_message = str(exception)
        
        builder = ErrorResponseBuilder().with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        # Add technical details
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            stack_trace=None,  # Don't expose stack traces to users
            request_id=correlation_id,
        )
        builder = builder.with_technical_details(technical)
        
        if status_code == 401:
            return builder.with_code(WorkflowErrorCode.LLM_AUTHENTICATION_ERROR).with_severity(
                WorkflowErrorSeverity.CRITICAL
            ).with_category(WorkflowErrorCategory.EXTERNAL_SERVICE).with_user_message(
                "Authentication Error",
                "There was an authentication issue with the AI service. Please contact support if this issue persists.",
            ).with_suggestions([
                "Contact your administrator to check AI service configuration",
                "Try again in a few minutes",
            ]).build()
        
        elif status_code == 429:
            return builder.with_code(WorkflowErrorCode.LLM_RATE_LIMIT).with_severity(
                WorkflowErrorSeverity.MEDIUM
            ).with_category(WorkflowErrorCategory.RESOURCE).with_user_message(
                "Rate Limit Exceeded",
                "The AI service is currently experiencing high demand. Please wait a moment and try again.",
            ).with_suggestions([
                "Wait a few minutes before trying again",
                "Consider breaking down complex requests into smaller parts",
            ]).with_retry_info(retry_after=60, is_retryable=True).build()
        
        elif status_code == 400:
            return builder.with_code(WorkflowErrorCode.LLM_INVALID_REQUEST).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.USER_INPUT).with_user_message(
                "Invalid Request",
                "The request to the AI service was invalid. This might be due to the content being too long or containing unsupported elements.",
            ).with_suggestions([
                "Try simplifying your request",
                "Reduce the amount of context or files included",
                "Check if your input contains any special characters that might cause issues",
            ]).build()
        
        elif status_code in [500, 502, 503]:
            return builder.with_code(WorkflowErrorCode.LLM_API_ERROR).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.EXTERNAL_SERVICE).with_user_message(
                "AI Service Unavailable",
                "The AI service is temporarily unavailable. Please try again in a few minutes.",
            ).with_suggestions([
                "Wait a few minutes and try again",
                "Contact support if the issue persists",
            ]).with_retry_info(retry_after=120, is_retryable=True).build()
        
        else:
            return builder.with_code(WorkflowErrorCode.LLM_API_ERROR).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.EXTERNAL_SERVICE).with_user_message(
                "AI Service Error",
                f"The AI service encountered an error (status: {status_code}). Please try again or contact support if the issue persists.",
            ).with_suggestions([
                "Try again in a few minutes",
                "Contact support with the error details",
            ]).build()
    
    def _handle_validation_error(
        self,
        exception: Union[ValidationError, PydanticCoreValidationError],
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle Pydantic validation errors."""
        
        builder = ErrorResponseBuilder().with_code(
            WorkflowErrorCode.INPUT_VALIDATION_ERROR
        ).with_severity(WorkflowErrorSeverity.MEDIUM).with_category(
            WorkflowErrorCategory.USER_INPUT
        ).with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        # Extract validation error details
        error_details = []
        if isinstance(exception, ValidationError):
            for error in exception.errors():
                field = " -> ".join(str(loc) for loc in error["loc"])
                error_details.append(f"{field}: {error['msg']}")
        else:
            error_details.append(str(exception))
        
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            request_id=correlation_id,
        )
        
        return builder.with_user_message(
            "Input Validation Error",
            "There was an issue with the provided input. Please check your request and try again.",
        ).with_suggestions([
            "Check that all required fields are provided",
            "Verify that input values are in the correct format",
            "Review the request structure and try again",
        ]).with_technical_details(technical).build()
    
    def _handle_tool_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle tool execution errors."""
        
        error_message = str(exception)
        builder = ErrorResponseBuilder().with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            request_id=correlation_id,
        )
        builder = builder.with_technical_details(technical)
        
        # Check for specific tool error patterns
        if "permission" in error_message.lower() or "forbidden" in error_message.lower():
            return builder.with_code(WorkflowErrorCode.TOOL_PERMISSION_DENIED).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.PERMISSION).with_user_message(
                "Permission Denied",
                "The workflow doesn't have permission to perform this action. Please check your access rights.",
            ).with_suggestions([
                "Verify you have the necessary permissions for this operation",
                "Contact your administrator to grant required access",
                "Try a different approach that doesn't require elevated permissions",
            ]).build()
        
        elif "timeout" in error_message.lower():
            return builder.with_code(WorkflowErrorCode.TOOL_TIMEOUT).with_severity(
                WorkflowErrorSeverity.MEDIUM
            ).with_category(WorkflowErrorCategory.RESOURCE).with_user_message(
                "Operation Timeout",
                "The operation took too long to complete and was cancelled. Please try again.",
            ).with_suggestions([
                "Try again with a simpler request",
                "Break down complex operations into smaller steps",
                "Contact support if timeouts persist",
            ]).with_retry_info(retry_after=30, is_retryable=True).build()
        
        else:
            tool_name = context.tool_name if context else "unknown"
            return builder.with_code(WorkflowErrorCode.TOOL_EXECUTION_FAILED).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.SYSTEM).with_user_message(
                "Tool Execution Failed",
                f"The {tool_name} tool encountered an error while executing. Please try again or use an alternative approach.",
            ).with_suggestions([
                "Try the operation again",
                "Use a different approach to achieve the same goal",
                "Contact support if the issue persists",
            ]).build()
    
    def _handle_gitlab_api_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle GitLab API errors."""
        
        error_message = str(exception)
        builder = ErrorResponseBuilder().with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            request_id=correlation_id,
        )
        builder = builder.with_technical_details(technical)
        
        if "401" in error_message or "unauthorized" in error_message.lower():
            return builder.with_code(WorkflowErrorCode.GITLAB_AUTHENTICATION_ERROR).with_severity(
                WorkflowErrorSeverity.CRITICAL
            ).with_category(WorkflowErrorCategory.EXTERNAL_SERVICE).with_user_message(
                "GitLab Authentication Error",
                "Unable to authenticate with GitLab. Please check your access token and permissions.",
            ).with_suggestions([
                "Verify your GitLab access token is valid",
                "Check that your token has the required scopes",
                "Contact your administrator for assistance",
            ]).build()
        
        elif "403" in error_message or "forbidden" in error_message.lower():
            return builder.with_code(WorkflowErrorCode.GITLAB_PERMISSION_DENIED).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.PERMISSION).with_user_message(
                "GitLab Permission Denied",
                "You don't have permission to perform this action in GitLab.",
            ).with_suggestions([
                "Check your role in the project",
                "Request additional permissions from a project maintainer",
                "Try a different approach that doesn't require elevated permissions",
            ]).build()
        
        elif "404" in error_message or "not found" in error_message.lower():
            return builder.with_code(WorkflowErrorCode.GITLAB_RESOURCE_NOT_FOUND).with_severity(
                WorkflowErrorSeverity.MEDIUM
            ).with_category(WorkflowErrorCategory.USER_INPUT).with_user_message(
                "GitLab Resource Not Found",
                "The requested GitLab resource could not be found. Please check the project, branch, or file path.",
            ).with_suggestions([
                "Verify the project name and path are correct",
                "Check that the branch or file exists",
                "Ensure you have access to the resource",
            ]).build()
        
        else:
            return builder.with_code(WorkflowErrorCode.GITLAB_API_ERROR).with_severity(
                WorkflowErrorSeverity.HIGH
            ).with_category(WorkflowErrorCategory.EXTERNAL_SERVICE).with_user_message(
                "GitLab API Error",
                "There was an error communicating with GitLab. Please try again.",
            ).with_suggestions([
                "Try again in a few minutes",
                "Check GitLab's status page for any ongoing issues",
                "Contact support if the issue persists",
            ]).build()
    
    def _handle_timeout_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle timeout errors."""
        
        builder = ErrorResponseBuilder().with_code(
            WorkflowErrorCode.WORKFLOW_TIMEOUT
        ).with_severity(WorkflowErrorSeverity.MEDIUM).with_category(
            WorkflowErrorCategory.RESOURCE
        ).with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            request_id=correlation_id,
        )
        
        return builder.with_user_message(
            "Operation Timeout",
            "The operation took too long to complete and was cancelled. Please try again with a simpler request.",
        ).with_suggestions([
            "Try breaking down complex requests into smaller parts",
            "Reduce the scope of your request",
            "Try again in a few minutes",
        ]).with_technical_details(technical).with_retry_info(
            retry_after=60, is_retryable=True
        ).build()
    
    def _handle_permission_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle permission errors."""
        
        builder = ErrorResponseBuilder().with_code(
            WorkflowErrorCode.TOOL_PERMISSION_DENIED
        ).with_severity(WorkflowErrorSeverity.HIGH).with_category(
            WorkflowErrorCategory.PERMISSION
        ).with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            request_id=correlation_id,
        )
        
        return builder.with_user_message(
            "Permission Denied",
            "You don't have the necessary permissions to perform this action.",
        ).with_suggestions([
            "Check your access rights for this project",
            "Contact your administrator to request additional permissions",
            "Try a different approach that doesn't require elevated permissions",
        ]).with_technical_details(technical).build()
    
    def _handle_unknown_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext],
        correlation_id: Optional[str],
    ) -> WorkflowErrorResponse:
        """Handle unknown/unclassified errors."""
        
        builder = ErrorResponseBuilder().with_code(
            WorkflowErrorCode.UNKNOWN_ERROR
        ).with_severity(WorkflowErrorSeverity.HIGH).with_category(
            WorkflowErrorCategory.SYSTEM
        ).with_correlation_id(correlation_id)
        
        if context:
            builder = builder.with_context(context)
        
        technical = TechnicalError(
            exception_type=type(exception).__name__,
            request_id=correlation_id,
        )
        
        return builder.with_user_message(
            "Unexpected Error",
            "An unexpected error occurred while processing your request. Please try again or contact support if the issue persists.",
        ).with_suggestions([
            "Try your request again",
            "Simplify your request and try again",
            "Contact support with the error details",
        ]).with_technical_details(technical).build()
    
    # Helper methods for error pattern matching
    
    def _is_tool_error(self, exception: Exception) -> bool:
        """Check if this is a tool execution error."""
        error_message = str(exception).lower()
        tool_error_patterns = [
            "tool execution",
            "command failed",
            "execution error",
            "tool error",
            "subprocess",
        ]
        return any(pattern in error_message for pattern in tool_error_patterns)
    
    def _is_gitlab_api_error(self, exception: Exception) -> bool:
        """Check if this is a GitLab API error."""
        error_message = str(exception).lower()
        gitlab_error_patterns = [
            "gitlab",
            "api error",
            "http error",
            "request failed",
            "connection error",
        ]
        return any(pattern in error_message for pattern in gitlab_error_patterns)
    
    def _is_timeout_error(self, exception: Exception) -> bool:
        """Check if this is a timeout error."""
        error_message = str(exception).lower()
        timeout_patterns = [
            "timeout",
            "timed out",
            "connection timeout",
            "read timeout",
            "request timeout",
        ]
        return any(pattern in error_message for pattern in timeout_patterns)
    
    def _is_permission_error(self, exception: Exception) -> bool:
        """Check if this is a permission error."""
        error_message = str(exception).lower()
        permission_patterns = [
            "permission denied",
            "access denied",
            "forbidden",
            "unauthorized",
            "not allowed",
        ]
        return any(pattern in error_message for pattern in permission_patterns)


# Global error classifier instance
error_classifier = ErrorClassifier()


def classify_workflow_error(
    exception: Exception,
    component: Optional[str] = None,
    operation: Optional[str] = None,
    tool_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    workflow_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None,
) -> WorkflowErrorResponse:
    """Convenience function to classify a workflow error with context."""
    
    context = ErrorContext(
        component=component,
        operation=operation,
        tool_name=tool_name,
        agent_name=agent_name,
        workflow_id=workflow_id,
        correlation_id=correlation_id,
        additional_data=additional_data,
    )
    
    return error_classifier.classify_error(exception, context, correlation_id)