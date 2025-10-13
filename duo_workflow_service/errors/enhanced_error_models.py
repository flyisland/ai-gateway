"""Enhanced error response models for Duo Workflow Service.

This module provides structured error response models that replace generic error messages
with specific, actionable error information for users.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from duo_workflow_service.entities.state import MessageTypeEnum, ToolStatus, UiChatLog


class WorkflowErrorCode(StrEnum):
    """Specific error codes for different types of workflow failures."""
    
    # LLM/Model related errors
    LLM_API_ERROR = "llm_api_error"
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_AUTHENTICATION_ERROR = "llm_authentication_error"
    LLM_INVALID_REQUEST = "llm_invalid_request"
    LLM_CONTEXT_TOO_LARGE = "llm_context_too_large"
    LLM_TIMEOUT = "llm_timeout"
    
    # Tool execution errors
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    TOOL_VALIDATION_ERROR = "tool_validation_error"
    TOOL_PERMISSION_DENIED = "tool_permission_denied"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_NOT_FOUND = "tool_not_found"
    
    # GitLab API errors
    GITLAB_API_ERROR = "gitlab_api_error"
    GITLAB_AUTHENTICATION_ERROR = "gitlab_authentication_error"
    GITLAB_PERMISSION_DENIED = "gitlab_permission_denied"
    GITLAB_RESOURCE_NOT_FOUND = "gitlab_resource_not_found"
    GITLAB_RATE_LIMIT = "gitlab_rate_limit"
    
    # Workflow state errors
    WORKFLOW_STATE_INVALID = "workflow_state_invalid"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_TIMEOUT = "workflow_timeout"
    
    # Input validation errors
    INPUT_VALIDATION_ERROR = "input_validation_error"
    GOAL_DISAMBIGUATION_FAILED = "goal_disambiguation_failed"
    
    # System errors
    INTERNAL_ERROR = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    CONFIGURATION_ERROR = "configuration_error"
    
    # Unknown/fallback
    UNKNOWN_ERROR = "unknown_error"


class WorkflowErrorSeverity(StrEnum):
    """Error severity levels for workflow errors."""
    
    LOW = "low"          # Minor issues that don't prevent workflow continuation
    MEDIUM = "medium"    # Issues that may affect workflow quality but allow continuation
    HIGH = "high"        # Issues that prevent workflow continuation but are recoverable
    CRITICAL = "critical"  # Issues that require immediate attention and stop workflow


class WorkflowErrorCategory(StrEnum):
    """High-level categories for workflow errors."""
    
    USER_INPUT = "user_input"      # Errors related to user input or configuration
    EXTERNAL_SERVICE = "external_service"  # Errors from external APIs/services
    SYSTEM = "system"              # Internal system errors
    PERMISSION = "permission"      # Authorization/permission errors
    RESOURCE = "resource"          # Resource availability/limits errors


class ErrorContext(BaseModel):
    """Additional context information for errors."""
    
    component: Optional[str] = Field(None, description="Component where error occurred")
    operation: Optional[str] = Field(None, description="Operation that failed")
    tool_name: Optional[str] = Field(None, description="Tool that caused the error")
    agent_name: Optional[str] = Field(None, description="Agent that encountered the error")
    workflow_id: Optional[str] = Field(None, description="Workflow ID for tracking")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID")
    additional_data: Optional[Dict[str, Any]] = Field(None, description="Additional error data")


class UserFriendlyError(BaseModel):
    """User-friendly error information."""
    
    title: str = Field(..., description="Short, user-friendly error title")
    message: str = Field(..., description="Detailed user-friendly error message")
    suggestions: List[str] = Field(default_factory=list, description="Suggested actions for the user")
    documentation_url: Optional[str] = Field(None, description="Link to relevant documentation")


class TechnicalError(BaseModel):
    """Technical error information for debugging."""
    
    exception_type: Optional[str] = Field(None, description="Type of exception that occurred")
    stack_trace: Optional[str] = Field(None, description="Stack trace (if available)")
    request_id: Optional[str] = Field(None, description="Request ID for tracking")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowError(BaseModel):
    """Comprehensive workflow error model."""
    
    code: WorkflowErrorCode = Field(..., description="Specific error code")
    severity: WorkflowErrorSeverity = Field(..., description="Error severity level")
    category: WorkflowErrorCategory = Field(..., description="Error category")
    
    user_friendly: UserFriendlyError = Field(..., description="User-friendly error information")
    technical: Optional[TechnicalError] = Field(None, description="Technical error details")
    context: Optional[ErrorContext] = Field(None, description="Error context information")
    
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retrying")
    is_retryable: bool = Field(False, description="Whether this error is retryable")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowErrorResponse(BaseModel):
    """Complete error response for workflow failures."""
    
    error: WorkflowError = Field(..., description="Error details")
    ui_chat_log: UiChatLog = Field(..., description="UI chat log entry for the error")
    
    @classmethod
    def create_error_response(
        cls,
        error_code: WorkflowErrorCode,
        user_title: str,
        user_message: str,
        severity: WorkflowErrorSeverity = WorkflowErrorSeverity.HIGH,
        category: WorkflowErrorCategory = WorkflowErrorCategory.SYSTEM,
        suggestions: Optional[List[str]] = None,
        context: Optional[ErrorContext] = None,
        technical: Optional[TechnicalError] = None,
        retry_after: Optional[int] = None,
        is_retryable: bool = False,
        correlation_id: Optional[str] = None,
    ) -> "WorkflowErrorResponse":
        """Create a complete error response with UI chat log."""
        
        user_friendly = UserFriendlyError(
            title=user_title,
            message=user_message,
            suggestions=suggestions or [],
        )
        
        workflow_error = WorkflowError(
            code=error_code,
            severity=severity,
            category=category,
            user_friendly=user_friendly,
            technical=technical,
            context=context,
            retry_after=retry_after,
            is_retryable=is_retryable,
        )
        
        # Create UI chat log entry
        ui_chat_log = UiChatLog(
            message_type=MessageTypeEnum.AGENT,
            message_sub_type="error",
            content=user_message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=ToolStatus.FAILURE,
            correlation_id=correlation_id,
            tool_info=None,
            additional_context=None,
        )
        
        return cls(error=workflow_error, ui_chat_log=ui_chat_log)


class ErrorResponseBuilder:
    """Builder class for creating structured error responses."""
    
    def __init__(self):
        self._error_code: Optional[WorkflowErrorCode] = None
        self._severity: WorkflowErrorSeverity = WorkflowErrorSeverity.HIGH
        self._category: WorkflowErrorCategory = WorkflowErrorCategory.SYSTEM
        self._user_title: Optional[str] = None
        self._user_message: Optional[str] = None
        self._suggestions: List[str] = []
        self._context: Optional[ErrorContext] = None
        self._technical: Optional[TechnicalError] = None
        self._retry_after: Optional[int] = None
        self._is_retryable: bool = False
        self._correlation_id: Optional[str] = None
    
    def with_code(self, code: WorkflowErrorCode) -> "ErrorResponseBuilder":
        """Set the error code."""
        self._error_code = code
        return self
    
    def with_severity(self, severity: WorkflowErrorSeverity) -> "ErrorResponseBuilder":
        """Set the error severity."""
        self._severity = severity
        return self
    
    def with_category(self, category: WorkflowErrorCategory) -> "ErrorResponseBuilder":
        """Set the error category."""
        self._category = category
        return self
    
    def with_user_message(self, title: str, message: str) -> "ErrorResponseBuilder":
        """Set the user-friendly error message."""
        self._user_title = title
        self._user_message = message
        return self
    
    def with_suggestions(self, suggestions: List[str]) -> "ErrorResponseBuilder":
        """Add user suggestions."""
        self._suggestions = suggestions
        return self
    
    def with_context(self, context: ErrorContext) -> "ErrorResponseBuilder":
        """Set error context."""
        self._context = context
        return self
    
    def with_technical_details(self, technical: TechnicalError) -> "ErrorResponseBuilder":
        """Set technical error details."""
        self._technical = technical
        return self
    
    def with_retry_info(self, retry_after: int, is_retryable: bool = True) -> "ErrorResponseBuilder":
        """Set retry information."""
        self._retry_after = retry_after
        self._is_retryable = is_retryable
        return self
    
    def with_correlation_id(self, correlation_id: str) -> "ErrorResponseBuilder":
        """Set correlation ID."""
        self._correlation_id = correlation_id
        return self
    
    def build(self) -> WorkflowErrorResponse:
        """Build the error response."""
        if not self._error_code:
            raise ValueError("Error code is required")
        if not self._user_title or not self._user_message:
            raise ValueError("User title and message are required")
        
        return WorkflowErrorResponse.create_error_response(
            error_code=self._error_code,
            user_title=self._user_title,
            user_message=self._user_message,
            severity=self._severity,
            category=self._category,
            suggestions=self._suggestions,
            context=self._context,
            technical=self._technical,
            retry_after=self._retry_after,
            is_retryable=self._is_retryable,
            correlation_id=self._correlation_id,
        )