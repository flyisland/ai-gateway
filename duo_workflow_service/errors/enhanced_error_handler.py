"""Enhanced error handling middleware for Duo Workflow Service.

This module provides improved error handling that replaces generic error messages
with specific, actionable error information and ensures proper event tracking.
"""

import uuid
from typing import Any, Dict, Optional

import structlog
from starlette_context import context

from duo_workflow_service.entities.state import WorkflowStatusEnum
from duo_workflow_service.errors.enhanced_error_models import (
    ErrorContext,
    WorkflowErrorResponse,
)
from duo_workflow_service.errors.error_classifier import classify_workflow_error
from duo_workflow_service.tracking.enhanced_event_tracker import track_workflow_failure

log = structlog.stdlib.get_logger("enhanced_error_handler")


class EnhancedErrorHandler:
    """Enhanced error handler that provides structured error responses and event tracking."""
    
    def __init__(self):
        self.correlation_id_header = "X-Correlation-ID"
    
    def handle_workflow_error(
        self,
        exception: Exception,
        component: Optional[str] = None,
        operation: Optional[str] = None,
        tool_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        workflow_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle a workflow error and return structured response with event tracking."""
        
        # Generate correlation ID if not present
        correlation_id = self._get_or_generate_correlation_id()
        
        # Classify the error into a structured response
        error_response = classify_workflow_error(
            exception=exception,
            component=component,
            operation=operation,
            tool_name=tool_name,
            agent_name=agent_name,
            workflow_id=workflow_id,
            correlation_id=correlation_id,
            additional_data=additional_context,
        )
        
        # Log the error with structured information
        self._log_error(exception, error_response, correlation_id)
        
        # Track the failure event
        self._track_failure_event(error_response, workflow_id)
        
        # Return workflow state update
        return self._create_workflow_response(error_response)
    
    def handle_agent_error(
        self,
        exception: Exception,
        agent_name: str,
        workflow_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle an agent-specific error."""
        
        return self.handle_workflow_error(
            exception=exception,
            component="agent",
            operation="agent_execution",
            agent_name=agent_name,
            workflow_id=workflow_id,
            additional_context=additional_context,
        )
    
    def handle_tool_error(
        self,
        exception: Exception,
        tool_name: str,
        workflow_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle a tool-specific error."""
        
        return self.handle_workflow_error(
            exception=exception,
            component="tool",
            operation="tool_execution",
            tool_name=tool_name,
            workflow_id=workflow_id,
            additional_context=additional_context,
        )
    
    def handle_llm_error(
        self,
        exception: Exception,
        model_name: Optional[str] = None,
        workflow_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle an LLM-specific error."""
        
        context_data = additional_context or {}
        if model_name:
            context_data["model_name"] = model_name
        
        return self.handle_workflow_error(
            exception=exception,
            component="llm",
            operation="llm_request",
            workflow_id=workflow_id,
            additional_context=context_data,
        )
    
    def handle_validation_error(
        self,
        exception: Exception,
        component: str,
        workflow_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle a validation error."""
        
        return self.handle_workflow_error(
            exception=exception,
            component=component,
            operation="validation",
            workflow_id=workflow_id,
            additional_context=additional_context,
        )
    
    def _get_or_generate_correlation_id(self) -> str:
        """Get correlation ID from context or generate a new one."""
        try:
            # Try to get from starlette context
            correlation_id = context.get("correlation_id")
            if correlation_id:
                return correlation_id
        except Exception:
            pass
        
        # Generate new correlation ID
        return str(uuid.uuid4())
    
    def _log_error(
        self,
        exception: Exception,
        error_response: WorkflowErrorResponse,
        correlation_id: str,
    ) -> None:
        """Log the error with structured information."""
        
        error_info = error_response.error
        
        log_data = {
            "correlation_id": correlation_id,
            "error_code": error_info.code,
            "error_category": error_info.category,
            "error_severity": error_info.severity,
            "exception_type": type(exception).__name__,
            "user_message": error_info.user_friendly.message,
        }
        
        if error_info.context:
            log_data.update({
                "component": error_info.context.component,
                "operation": error_info.context.operation,
                "tool_name": error_info.context.tool_name,
                "agent_name": error_info.context.agent_name,
                "workflow_id": error_info.context.workflow_id,
            })
        
        # Log at appropriate level based on severity
        if error_info.severity == "critical":
            log.error("Critical workflow error occurred", **log_data, exc_info=True)
        elif error_info.severity == "high":
            log.error("High severity workflow error occurred", **log_data)
        elif error_info.severity == "medium":
            log.warning("Medium severity workflow error occurred", **log_data)
        else:
            log.info("Low severity workflow error occurred", **log_data)
    
    def _track_failure_event(
        self,
        error_response: WorkflowErrorResponse,
        workflow_id: Optional[str],
    ) -> None:
        """Track the failure event for monitoring and analytics."""
        
        try:
            track_workflow_failure(
                error_response=error_response,
                workflow_id=workflow_id,
            )
        except Exception as e:
            log.warning(
                "Failed to track workflow failure event",
                error=str(e),
                workflow_id=workflow_id,
            )
    
    def _create_workflow_response(
        self,
        error_response: WorkflowErrorResponse,
    ) -> Dict[str, Any]:
        """Create the workflow state response."""
        
        return {
            "status": WorkflowStatusEnum.ERROR,
            "ui_chat_log": [error_response.ui_chat_log],
            "error_details": error_response.error.model_dump(),
        }


# Global enhanced error handler instance
enhanced_error_handler = EnhancedErrorHandler()


def handle_workflow_error(
    exception: Exception,
    component: Optional[str] = None,
    operation: Optional[str] = None,
    tool_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    workflow_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to handle workflow errors."""
    
    return enhanced_error_handler.handle_workflow_error(
        exception=exception,
        component=component,
        operation=operation,
        tool_name=tool_name,
        agent_name=agent_name,
        workflow_id=workflow_id,
        additional_context=additional_context,
    )


def handle_agent_error(
    exception: Exception,
    agent_name: str,
    workflow_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to handle agent errors."""
    
    return enhanced_error_handler.handle_agent_error(
        exception=exception,
        agent_name=agent_name,
        workflow_id=workflow_id,
        additional_context=additional_context,
    )


def handle_tool_error(
    exception: Exception,
    tool_name: str,
    workflow_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to handle tool errors."""
    
    return enhanced_error_handler.handle_tool_error(
        exception=exception,
        tool_name=tool_name,
        workflow_id=workflow_id,
        additional_context=additional_context,
    )


def handle_llm_error(
    exception: Exception,
    model_name: Optional[str] = None,
    workflow_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to handle LLM errors."""
    
    return enhanced_error_handler.handle_llm_error(
        exception=exception,
        model_name=model_name,
        workflow_id=workflow_id,
        additional_context=additional_context,
    )


def handle_validation_error(
    exception: Exception,
    component: str,
    workflow_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to handle validation errors."""
    
    return enhanced_error_handler.handle_validation_error(
        exception=exception,
        component=component,
        workflow_id=workflow_id,
        additional_context=additional_context,
    )