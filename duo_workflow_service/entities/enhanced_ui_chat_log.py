"""Enhanced UI chat log utilities for better error reporting.

This module provides utilities to create enhanced UI chat log entries that include
specific error information instead of generic messages.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from duo_workflow_service.entities.state import (
    MessageTypeEnum,
    ToolStatus,
    UiChatLog,
)
from duo_workflow_service.errors.enhanced_error_models import (
    WorkflowError,
    WorkflowErrorResponse,
)


def create_error_ui_chat_log(
    error_response: WorkflowErrorResponse,
    correlation_id: Optional[str] = None,
) -> UiChatLog:
    """Create a UI chat log entry from an enhanced error response."""
    
    error_info = error_response.error
    
    # Create enhanced content with error details
    content = error_info.user_friendly.message
    
    # Add suggestions if available
    if error_info.user_friendly.suggestions:
        content += "\n\nSuggested actions:"
        for suggestion in error_info.user_friendly.suggestions:
            content += f"\n• {suggestion}"
    
    # Add retry information if applicable
    if error_info.is_retryable and error_info.retry_after:
        content += f"\n\nYou can try again in {error_info.retry_after} seconds."
    elif error_info.is_retryable:
        content += "\n\nYou can try this operation again."
    
    return UiChatLog(
        message_type=MessageTypeEnum.AGENT,
        message_sub_type="error",
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.FAILURE,
        correlation_id=correlation_id,
        tool_info=None,
        additional_context=None,
    )


def create_enhanced_error_ui_chat_log(
    title: str,
    message: str,
    suggestions: Optional[List[str]] = None,
    error_code: Optional[str] = None,
    is_retryable: bool = False,
    retry_after: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> UiChatLog:
    """Create an enhanced error UI chat log entry with specific details."""
    
    # Build enhanced content
    content = message
    
    # Add suggestions if provided
    if suggestions:
        content += "\n\nSuggested actions:"
        for suggestion in suggestions:
            content += f"\n• {suggestion}"
    
    # Add retry information if applicable
    if is_retryable and retry_after:
        content += f"\n\nYou can try again in {retry_after} seconds."
    elif is_retryable:
        content += "\n\nYou can try this operation again."
    
    # Add error code for debugging (if provided)
    if error_code:
        content += f"\n\n(Error code: {error_code})"
    
    return UiChatLog(
        message_type=MessageTypeEnum.AGENT,
        message_sub_type="error",
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.FAILURE,
        correlation_id=correlation_id,
        tool_info=None,
        additional_context=None,
    )


def create_tool_error_ui_chat_log(
    tool_name: str,
    error_message: str,
    suggestions: Optional[List[str]] = None,
    correlation_id: Optional[str] = None,
) -> UiChatLog:
    """Create a UI chat log entry for tool execution errors."""
    
    content = f"The {tool_name} tool encountered an error: {error_message}"
    
    if suggestions:
        content += "\n\nSuggested actions:"
        for suggestion in suggestions:
            content += f"\n• {suggestion}"
    
    return UiChatLog(
        message_type=MessageTypeEnum.TOOL,
        message_sub_type="error",
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.FAILURE,
        correlation_id=correlation_id,
        tool_info={"name": tool_name, "args": {}},
        additional_context=None,
    )


def create_llm_error_ui_chat_log(
    model_name: str,
    error_message: str,
    suggestions: Optional[List[str]] = None,
    is_retryable: bool = False,
    retry_after: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> UiChatLog:
    """Create a UI chat log entry for LLM/AI service errors."""
    
    content = error_message
    
    if suggestions:
        content += "\n\nSuggested actions:"
        for suggestion in suggestions:
            content += f"\n• {suggestion}"
    
    # Add retry information if applicable
    if is_retryable and retry_after:
        content += f"\n\nYou can try again in {retry_after} seconds."
    elif is_retryable:
        content += "\n\nYou can try this operation again."
    
    return UiChatLog(
        message_type=MessageTypeEnum.AGENT,
        message_sub_type="llm_error",
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.FAILURE,
        correlation_id=correlation_id,
        tool_info=None,
        additional_context=None,
    )


def create_validation_error_ui_chat_log(
    validation_errors: List[str],
    suggestions: Optional[List[str]] = None,
    correlation_id: Optional[str] = None,
) -> UiChatLog:
    """Create a UI chat log entry for validation errors."""
    
    content = "There were validation errors with your input:"
    for error in validation_errors:
        content += f"\n• {error}"
    
    if suggestions:
        content += "\n\nSuggested actions:"
        for suggestion in suggestions:
            content += f"\n• {suggestion}"
    
    return UiChatLog(
        message_type=MessageTypeEnum.AGENT,
        message_sub_type="validation_error",
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.FAILURE,
        correlation_id=correlation_id,
        tool_info=None,
        additional_context=None,
    )


def create_permission_error_ui_chat_log(
    resource: str,
    required_permissions: Optional[List[str]] = None,
    correlation_id: Optional[str] = None,
) -> UiChatLog:
    """Create a UI chat log entry for permission errors."""
    
    content = f"You don't have permission to access {resource}."
    
    if required_permissions:
        content += f"\n\nRequired permissions:"
        for permission in required_permissions:
            content += f"\n• {permission}"
    
    content += "\n\nSuggested actions:"
    content += "\n• Contact your administrator to request access"
    content += "\n• Check your role in the project"
    content += "\n• Try a different approach that doesn't require elevated permissions"
    
    return UiChatLog(
        message_type=MessageTypeEnum.AGENT,
        message_sub_type="permission_error",
        content=content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=ToolStatus.FAILURE,
        correlation_id=correlation_id,
        tool_info=None,
        additional_context=None,
    )


def enhance_generic_error_message(
    generic_message: str,
    error_details: Optional[Dict[str, Any]] = None,
) -> str:
    """Enhance a generic error message with specific details if available."""
    
    if not error_details:
        return generic_message
    
    enhanced_message = generic_message
    
    # Add specific error information if available
    if "error_code" in error_details:
        enhanced_message += f" (Error: {error_details['error_code']})"
    
    if "component" in error_details:
        enhanced_message += f" The error occurred in the {error_details['component']} component."
    
    if "suggestions" in error_details and error_details["suggestions"]:
        enhanced_message += "\n\nSuggested actions:"
        for suggestion in error_details["suggestions"]:
            enhanced_message += f"\n• {suggestion}"
    
    return enhanced_message